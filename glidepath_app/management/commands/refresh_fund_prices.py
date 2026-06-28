"""Manually refresh virtual-fund unit prices by scraping provider price pages.

Usage:
    python manage.py refresh_fund_prices --provider nysaves
    python manage.py refresh_fund_prices            # all active providers with a scraper
"""
from django.core.management.base import BaseCommand

from glidepath_app.models import FundProvider
from glidepath_app.scraper_service import refresh_virtual_fund_prices


class Command(BaseCommand):
    help = "Scrape and update unit prices for virtual funds (e.g. NYSaves 529 portfolios)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider", help="Provider slug to refresh (default: all with a scraper)."
        )

    def handle(self, *args, **options):
        if options.get("provider"):
            slugs = [options["provider"]]
        else:
            slugs = list(
                FundProvider.objects.exclude(price_scraper="")
                .values_list("slug", flat=True)
            )
            if not slugs:
                self.stdout.write("No providers with a configured scraper.")
                return

        for slug in slugs:
            try:
                result = refresh_virtual_fund_prices(slug)
            except Exception as exc:  # surface, don't crash the whole run
                self.stderr.write(self.style.ERROR(f"{slug}: refresh failed: {exc}"))
                continue

            self.stdout.write(self.style.SUCCESS(
                f"{slug}: updated {result['updated']} fund(s) "
                f"from {result['scraped_count']} scraped row(s)."
            ))
            if result["not_updated"]:
                self.stdout.write(
                    f"  No price for {len(result['not_updated'])} fund(s): "
                    + ", ".join(result["not_updated"])
                )
            if result["unmatched_scraped"]:
                self.stdout.write(
                    f"  {len(result['unmatched_scraped'])} scraped row(s) matched no fund: "
                    + ", ".join(result["unmatched_scraped"])
                )
