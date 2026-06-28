"""Seed an example education (529) glide-path rule set.

An aggressive-to-conservative path keyed on years *from* enrollment, using the
same sign convention as retirement: negative = before college (accumulating),
0 = enrollment (college start), positive = during/after college (drawing down).
Covers -100..100 with no gaps. Class allocations split into the same asset
categories the NYSaves 529 funds explode into, so the education dashboard's
current-vs-target drift is meaningful out of the box.

Idempotent: skipped if a rule set with the same name already exists.
"""
from decimal import Decimal

from django.db import migrations


RULESET_NAME = "Example 529 Education Glide Path"

# (gt_years, lt_years, stocks_pct, bonds_pct) — years from enrollment.
# Negative = before college (aggressive); positive = during/after (conservative).
BANDS = [
    (-100, -15, 90, 10),  # 15+ years out: very aggressive
    (-15, -10, 80, 20),
    (-10, -5, 70, 30),
    (-5, -2, 50, 50),
    (-2, 0, 30, 70),
    (0, 100, 20, 80),     # enrolled / drawing down
]

# How each class splits across categories (must sum to 1 within a class).
STOCK_SPLIT = [("US Total Market", Decimal("0.6")), ("International Market", Decimal("0.4"))]
BOND_SPLIT = [("US Investment Grade", Decimal("0.7")), ("International Market", Decimal("0.3"))]


def seed(apps, schema_editor):
    RuleSet = apps.get_model("glidepath_app", "RuleSet")
    GlidepathRule = apps.get_model("glidepath_app", "GlidepathRule")
    AssetClass = apps.get_model("glidepath_app", "AssetClass")
    AssetCategory = apps.get_model("glidepath_app", "AssetCategory")
    ClassAllocation = apps.get_model("glidepath_app", "ClassAllocation")
    CategoryAllocation = apps.get_model("glidepath_app", "CategoryAllocation")

    if RuleSet.objects.filter(name=RULESET_NAME).exists():
        return

    stocks, _ = AssetClass.objects.get_or_create(name="Stocks")
    bonds, _ = AssetClass.objects.get_or_create(name="Bonds")

    def category(asset_class, name):
        return AssetCategory.objects.get_or_create(name=name, asset_class=asset_class)[0]

    ruleset = RuleSet.objects.create(
        name=RULESET_NAME, account_type="education",
        description="Example aggressive-to-conservative 529 glide path keyed on years to enrollment.",
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
        ("glidepath_app", "0020_seed_nysaves_catalog"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
