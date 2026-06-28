"""Seed the NYSaves fund provider, its virtual-fund catalog, and the asset
categories those compositions reference.

Category names intentionally match the naming convention used by the glidepath
rule CSV importer so that a later rule import dedupes against these rows via
get_or_create rather than creating parallel duplicates. Growth/Value large-cap
funds collapse into "US Large-Cap"; cash "Short-Term Reserves" lives under the
existing "Other" asset class (see the 529 architecture spec reconciliation).

Target Enrollment portfolios (2023-2044) are intentionally NOT seeded here -
their compositions shift along the NYSaves glide path and are not yet captured.
They will be added in a follow-up once current allocations are supplied.
"""
from decimal import Decimal

from django.db import migrations


PROVIDER = {
    "slug": "nysaves",
    "name": "NY 529 Direct Plan",
    "price_source_url": "https://www.nysaves.org/price-and-performance/",
    "price_scraper": "nysaves",
}

# (asset_class_name, category_name) referenced by the compositions below.
CATEGORIES = [
    ("Stocks", "US Total Market"),
    ("Stocks", "US Large-Cap"),
    ("Stocks", "US Medium-Cap"),
    ("Stocks", "US Small-Cap"),
    ("Stocks", "International Market"),
    ("Bonds", "US Investment Grade"),
    ("Bonds", "International Market"),
    ("Bonds", "Inflation Protected"),
    ("Bonds", "US Short-term Investment-grade"),
    ("Other", "Short-Term Reserves"),
]

# name, slug, [(asset_class, category, percentage), ...]  -- each must sum to 100.
VIRTUAL_FUNDS = [
    ("Growth Stock Index Portfolio", "growth-stock-index",
        [("Stocks", "US Large-Cap", 100)]),
    ("Global Equity Portfolio", "global-equity",
        [("Stocks", "US Total Market", 60), ("Stocks", "International Market", 40)]),
    ("U.S. Stock Market Index Portfolio", "us-stock-market-index",
        [("Stocks", "US Total Market", 100)]),
    ("Value Stock Index Portfolio", "value-stock-index",
        [("Stocks", "US Large-Cap", 100)]),
    ("Mid-Cap Stock Index Portfolio", "mid-cap-stock-index",
        [("Stocks", "US Medium-Cap", 100)]),
    ("Small-Cap Stock Index Portfolio", "small-cap-stock-index",
        [("Stocks", "US Small-Cap", 100)]),
    ("International Stock Market Index Portfolio", "international-stock-market-index",
        [("Stocks", "International Market", 100)]),
    ("Developed Markets Index Portfolio", "developed-markets-index",
        [("Stocks", "International Market", 100)]),
    ("Social Index Portfolio", "social-index",
        [("Stocks", "US Total Market", 100)]),
    ("Growth Portfolio", "growth",
        [("Stocks", "US Total Market", 48), ("Stocks", "International Market", 32),
         ("Bonds", "US Investment Grade", 14), ("Bonds", "International Market", 6)]),
    ("Moderate Growth Portfolio", "moderate-growth",
        [("Stocks", "US Total Market", 36), ("Stocks", "International Market", 24),
         ("Bonds", "US Investment Grade", 28), ("Bonds", "International Market", 12)]),
    ("Conservative Growth Portfolio", "conservative-growth",
        [("Stocks", "US Total Market", 24), ("Stocks", "International Market", 16),
         ("Bonds", "US Investment Grade", 42), ("Bonds", "International Market", 18)]),
    ("Income Portfolio", "income",
        [("Stocks", "US Total Market", 12), ("Stocks", "International Market", 8),
         ("Bonds", "US Investment Grade", 56), ("Bonds", "International Market", 24)]),
    ("Bond Market Index Portfolio", "bond-market-index",
        [("Bonds", "US Investment Grade", 100)]),
    ("International Bond Market Index Portfolio", "international-bond-market-index",
        [("Bonds", "International Market", 100)]),
    ("Short-Term Bond Market Index Portfolio", "short-term-bond-market-index",
        [("Bonds", "US Short-term Investment-grade", 100)]),
    ("Conservative Income Portfolio", "conservative-income",
        [("Bonds", "US Investment Grade", "34.5"), ("Bonds", "International Market", "22.5"),
         ("Bonds", "Inflation Protected", 18), ("Other", "Short-Term Reserves", 25)]),
    ("Interest Accumulation Portfolio", "interest-accumulation",
        [("Other", "Short-Term Reserves", 100)]),
]


def seed(apps, schema_editor):
    AssetClass = apps.get_model("glidepath_app", "AssetClass")
    AssetCategory = apps.get_model("glidepath_app", "AssetCategory")
    FundProvider = apps.get_model("glidepath_app", "FundProvider")
    VirtualFund = apps.get_model("glidepath_app", "VirtualFund")
    VirtualFundComposition = apps.get_model("glidepath_app", "VirtualFundComposition")

    # Asset classes / categories (idempotent; reuses existing rows where present).
    category_lookup = {}
    for class_name, category_name in CATEGORIES:
        asset_class, _ = AssetClass.objects.get_or_create(name=class_name)
        category, _ = AssetCategory.objects.get_or_create(
            name=category_name, asset_class=asset_class
        )
        category_lookup[(class_name, category_name)] = category

    provider, _ = FundProvider.objects.update_or_create(
        slug=PROVIDER["slug"],
        defaults={
            "name": PROVIDER["name"],
            "price_source_url": PROVIDER["price_source_url"],
            "price_scraper": PROVIDER["price_scraper"],
        },
    )

    for name, slug, composition in VIRTUAL_FUNDS:
        fund, _ = VirtualFund.objects.update_or_create(
            provider=provider, slug=slug, defaults={"name": name},
        )
        total = Decimal("0")
        for class_name, category_name, pct in composition:
            percentage = Decimal(str(pct))
            total += percentage
            VirtualFundComposition.objects.update_or_create(
                virtual_fund=fund,
                asset_category=category_lookup[(class_name, category_name)],
                defaults={"percentage": percentage},
            )
        if total != Decimal("100"):
            raise ValueError(f"{name} composition sums to {total}, not 100")


def unseed(apps, schema_editor):
    # Remove the provider (cascades to its virtual funds + compositions). Leave
    # asset classes/categories in place since other data may reference them.
    FundProvider = apps.get_model("glidepath_app", "FundProvider")
    FundProvider.objects.filter(slug=PROVIDER["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("glidepath_app", "0019_fundprovider_virtualfund_accountupload_account_type_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
