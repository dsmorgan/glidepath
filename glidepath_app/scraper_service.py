"""Virtual-fund price scraping.

The NYSaves Price & Performance page is an Alpine.js shell that loads data from a
public JSON API (Ascensus College Savings). We hit that API directly rather than
scraping rendered HTML:

    https://api.acs529.com/api/v1/plans/newyork/fundperformance?style=external

returns a list of records with `fundName`, `price`, and `priceDate`.

New providers register a scraper in SCRAPERS keyed by FundProvider.price_scraper
and reuse refresh_virtual_fund_prices() unchanged. A scraper returns
{fund_name: (Decimal price, date_or_None)}.

Matching is name-based and the upstream feed can change without notice, so every
refresh returns a summary (updated / unmatched / stale) instead of failing
silently, and logs at WARNING when a scraped row can't be matched.
"""
import logging
import re
from datetime import date
from decimal import Decimal

import requests
from django.utils import timezone

from .models import FundProvider, VirtualFund

logger = logging.getLogger(__name__)

USER_AGENT = "GlidepathBot/1.0 (+education-portfolio price refresh)"
REQUEST_TIMEOUT = 20  # seconds

# NYSaves ("newyork" brand) fund performance feed behind the public price page.
NYSAVES_PERFORMANCE_URL = (
    "https://api.acs529.com/api/v1/plans/newyork/fundperformance?style=external"
)


def _normalize_name(name: str) -> str:
    """Normalize a fund name for matching: lowercase, strip all non-alphanumerics,
    and drop a trailing 'portfolio'/'fund'. This bridges feed-vs-catalog naming
    differences like 'U.S. ... Portfolio' vs 'US ... Portfolio' and
    'Global Equity Portfolio' vs 'Global Equity Fund'."""
    s = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    for suffix in ("portfolio", "fund"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _parse_price(value):
    """Parse a price (number or string like '$20.45') into a Decimal, or None."""
    if value is None:
        return None
    s = str(value).replace("$", "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", s or ""):
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def parse_nysaves_performance(records) -> dict:
    """Map the acs529 fundperformance payload (a list of dicts) to
    {fund_name: (Decimal price, date_or_None)}. Pure function for unit testing."""
    prices = {}
    for record in records or []:
        name = (record.get("fundName") or "").strip()
        price = _parse_price(record.get("price"))
        if not name or price is None:
            continue
        as_of = None
        raw_date = (record.get("priceDate") or "")[:10]
        if raw_date:
            try:
                as_of = date.fromisoformat(raw_date)
            except ValueError:
                as_of = None
        prices[name] = (price, as_of)
    return prices


def _scrape_nysaves_prices(provider: FundProvider) -> dict:
    """Fetch the NYSaves performance feed -> {fund_name: (price, as_of)}."""
    response = requests.get(
        NYSAVES_PERFORMANCE_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    prices = parse_nysaves_performance(response.json())
    if not prices:
        logger.warning("NYSaves feed returned 0 usable prices (%s)", NYSAVES_PERFORMANCE_URL)
    return prices


# Provider scraper registry, keyed by FundProvider.price_scraper.
SCRAPERS = {
    "nysaves": _scrape_nysaves_prices,
}


def refresh_virtual_fund_prices(provider_slug: str) -> dict:
    """Scrape and update unit prices for all active virtual funds under a provider.

    Returns a summary dict:
        {updated: int, updated_funds: [name...], unmatched_scraped: [name...],
         not_updated: [fund_name...], scraped_count: int}
    """
    provider = FundProvider.objects.filter(slug=provider_slug).first()
    if provider is None:
        raise ValueError(f"No fund provider with slug '{provider_slug}'.")

    scraper = SCRAPERS.get(provider.price_scraper)
    if scraper is None:
        raise ValueError(
            f"No price scraper registered for '{provider.price_scraper}' "
            f"(provider {provider_slug})."
        )

    scraped = scraper(provider)  # {raw_name: (Decimal, date_or_None)}
    scraped_by_norm = {}
    for name, (price, as_of) in scraped.items():
        norm = _normalize_name(name)
        if norm in scraped_by_norm:
            logger.warning(
                "%s feed: two entries normalize to '%s' ('%s' and '%s'); keeping the latter",
                provider_slug, norm, scraped_by_norm[norm][0], name,
            )
        scraped_by_norm[norm] = (name, price, as_of)

    funds = list(VirtualFund.objects.filter(provider=provider, is_active=True))
    today = timezone.now().date()

    updated_funds = []
    not_updated = []
    matched_norms = set()

    for fund in funds:
        match = scraped_by_norm.get(_normalize_name(fund.name))
        if match is None:
            not_updated.append(fund.name)
            continue
        _, price, as_of = match
        matched_norms.add(_normalize_name(fund.name))
        fund.unit_price = price
        fund.price_as_of = as_of or today
        fund.save(update_fields=["unit_price", "price_as_of"])
        updated_funds.append(fund.name)

    unmatched_scraped = [
        raw for norm, (raw, _p, _d) in scraped_by_norm.items() if norm not in matched_norms
    ]
    if unmatched_scraped:
        logger.warning(
            "%s refresh: %d scraped row(s) matched no seeded fund: %s",
            provider_slug, len(unmatched_scraped), ", ".join(sorted(unmatched_scraped)),
        )

    # Only stamp last_price_refresh when prices were actually retrieved. A run that
    # updates nothing (scrape returned nothing / matched no fund) is not treated as a
    # successful fetch, so callers throttling on this timestamp allow an immediate retry.
    if updated_funds:
        provider.last_price_refresh = timezone.now()
        provider.save(update_fields=["last_price_refresh"])

    return {
        "updated": len(updated_funds),
        "updated_funds": updated_funds,
        "unmatched_scraped": unmatched_scraped,
        "not_updated": not_updated,
        "scraped_count": len(scraped),
    }
