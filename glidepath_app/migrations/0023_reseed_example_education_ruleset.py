"""Re-seed the example education rule set under the new sign convention.

Migration 0021 originally seeded the example 529 glide path with an inverted sign
(positive = before enrollment). The convention has since flipped to match
retirement (negative = before the milestone, 0 = milestone, positive = after).
Databases that already applied the old 0021 still hold the inverted bands, so this
deletes the example by name and recreates it with the corrected bands.

Idempotent: on a fresh database (where 0021 already seeds the new bands) this just
replaces an identical record.
"""
from decimal import Decimal

from django.db import migrations


RULESET_NAME = "Example 529 Education Glide Path"

# (gt_years, lt_years, stocks_pct, bonds_pct) — years from enrollment.
# Negative = before college (aggressive); positive = during/after (conservative).
BANDS = [
    (-100, -15, 90, 10),
    (-15, -10, 80, 20),
    (-10, -5, 70, 30),
    (-5, -2, 50, 50),
    (-2, 0, 30, 70),
    (0, 100, 20, 80),
]

STOCK_SPLIT = [("US Total Market", Decimal("0.6")), ("International Market", Decimal("0.4"))]
BOND_SPLIT = [("US Investment Grade", Decimal("0.7")), ("International Market", Decimal("0.3"))]


def reseed(apps, schema_editor):
    RuleSet = apps.get_model("glidepath_app", "RuleSet")
    GlidepathRule = apps.get_model("glidepath_app", "GlidepathRule")
    AssetClass = apps.get_model("glidepath_app", "AssetClass")
    AssetCategory = apps.get_model("glidepath_app", "AssetCategory")
    ClassAllocation = apps.get_model("glidepath_app", "ClassAllocation")
    CategoryAllocation = apps.get_model("glidepath_app", "CategoryAllocation")

    # Drop any prior copy (old-convention or otherwise) and rebuild.
    RuleSet.objects.filter(name=RULESET_NAME).delete()

    stocks, _ = AssetClass.objects.get_or_create(name="Stocks")
    bonds, _ = AssetClass.objects.get_or_create(name="Bonds")

    def category(asset_class, name):
        return AssetCategory.objects.get_or_create(name=name, asset_class=asset_class)[0]

    ruleset = RuleSet.objects.create(
        name=RULESET_NAME, account_type="education",
        description="Example aggressive-to-conservative 529 glide path keyed on years from enrollment.",
    )

    for gt, lt, stocks_pct, bonds_pct in BANDS:
        rule = GlidepathRule.objects.create(ruleset=ruleset, gt_retire_age=gt, lt_retire_age=lt)
        for asset_class, pct in ((stocks, stocks_pct), (bonds, bonds_pct)):
            ClassAllocation.objects.create(
                rule=rule, asset_class=asset_class, percentage=Decimal(pct)
            )
        for cat_name, frac in STOCK_SPLIT:
            CategoryAllocation.objects.create(
                rule=rule, asset_category=category(stocks, cat_name),
                percentage=(Decimal(stocks_pct) * frac).quantize(Decimal("0.01")),
            )
        for cat_name, frac in BOND_SPLIT:
            CategoryAllocation.objects.create(
                rule=rule, asset_category=category(bonds, cat_name),
                percentage=(Decimal(bonds_pct) * frac).quantize(Decimal("0.01")),
            )


def unseed(apps, schema_editor):
    RuleSet = apps.get_model("glidepath_app", "RuleSet")
    RuleSet.objects.filter(name=RULESET_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("glidepath_app", "0022_remove_portfolio_years_to_enrollment_and_more"),
    ]

    operations = [
        migrations.RunPython(reseed, unseed),
    ]
