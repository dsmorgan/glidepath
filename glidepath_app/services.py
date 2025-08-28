import csv
import io
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from django.db import transaction

from .models import (
    AssetCategory,
    AssetClass,
    CategoryAllocation,
    ClassAllocation,
    GlidepathRule,
)

ASSET_CLASSES = ["Stocks", "Bonds", "Crypto", "Other"]


def _parse_percent(value: str) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    value = value.strip()
    if value.endswith("%"):
        value = value[:-1]
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def import_glidepath_rules(file_obj) -> None:
    text = io.TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(text)
    required = {"gt-retire-age", "lt-retire-age"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Missing required columns: gt-retire-age and lt-retire-age")

    class_cols = [c for c in reader.fieldnames if c in ASSET_CLASSES]
    category_cols = [c for c in reader.fieldnames if ":" in c]

    with transaction.atomic():
        GlidepathRule.objects.all().delete()
        for row in reader:
            gt = int(row["gt-retire-age"])
            lt = int(row["lt-retire-age"])
            gt = max(-100, gt)
            lt = min(100, lt)
            if gt >= lt:
                raise ValueError("gt-retire-age must be less than lt-retire-age")
            rule = GlidepathRule.objects.create(gt_retire_age=gt, lt_retire_age=lt)

            # class allocations
            class_pcts: Dict[str, Decimal] = {}
            total_class = Decimal("0")
            for col in class_cols:
                pct = _parse_percent(row.get(col, "0"))
                if pct:
                    class_pcts[col] = pct
                    total_class += pct
            if total_class > Decimal("100"):
                raise ValueError("Class allocations exceed 100%")
            if "Other" not in class_pcts:
                class_pcts["Other"] = (Decimal("100") - total_class).quantize(
                    Decimal("0.01")
                )
            total_class = sum(class_pcts.values())
            if total_class != Decimal("100"):
                raise ValueError("Class allocations must total 100%")

            # categories
            category_totals: Dict[str, Dict[str, Decimal]] = {}
            total_category = Decimal("0")
            for col in category_cols:
                cls, cat = col.split(":", 1)
                if cls not in ASSET_CLASSES:
                    raise ValueError(f"Invalid asset class '{cls}' in column '{col}'")
                pct = _parse_percent(row.get(col, "0"))
                if pct:
                    category_totals.setdefault(cls, {})[cat] = pct
                    total_category += pct
            if total_category != Decimal("100"):
                raise ValueError("Category allocations must total 100%")

            for cls, cats in category_totals.items():
                cat_sum = sum(cats.values())
                cls_pct = class_pcts.get(cls, Decimal("0"))
                if cls_pct != cat_sum:
                    raise ValueError(
                        f"Category allocations for {cls} ({cat_sum}%) do not match class allocation ({cls_pct}%)"
                    )

            # ensure asset classes exist
            existing_classes = {
                ac.name: ac for ac in AssetClass.objects.filter(name__in=ASSET_CLASSES)
            }
            for name in ASSET_CLASSES:
                if name not in existing_classes:
                    existing_classes[name] = AssetClass.objects.create(name=name)

            for cls_name, pct in class_pcts.items():
                ClassAllocation.objects.create(
                    rule=rule, asset_class=existing_classes[cls_name], percentage=pct
                )

            for cls_name, cats in category_totals.items():
                for cat_name, pct in cats.items():
                    category, _ = AssetCategory.objects.get_or_create(
                        name=cat_name, asset_class=existing_classes[cls_name]
                    )
                    CategoryAllocation.objects.create(
                        rule=rule, asset_category=category, percentage=pct
                    )


def export_glidepath_rules() -> str:
    asset_classes = list(AssetClass.objects.order_by("name"))
    categories = list(
        AssetCategory.objects.order_by("asset_class__name", "name")
    )

    headers = ["gt-retire-age", "lt-retire-age"]
    headers += [ac.name for ac in asset_classes]
    headers += [f"{c.asset_class.name}:{c.name}" for c in categories]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for rule in GlidepathRule.objects.order_by("gt_retire_age"):
        row = {
            "gt-retire-age": rule.gt_retire_age,
            "lt-retire-age": rule.lt_retire_age,
        }
        class_map = {
            ca.asset_class.name: ca.percentage for ca in rule.class_allocations.all()
        }
        category_map = {
            f"{ca.asset_category.asset_class.name}:{ca.asset_category.name}": ca.percentage
            for ca in rule.category_allocations.all()
        }
        for ac in asset_classes:
            row[ac.name] = f"{class_map.get(ac.name, Decimal('0'))}%"
        for cat in categories:
            key = f"{cat.asset_class.name}:{cat.name}"
            row[key] = f"{category_map.get(key, Decimal('0'))}%"
        writer.writerow(row)
    return output.getvalue()
