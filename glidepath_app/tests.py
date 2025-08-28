from django.test import TestCase
from django.conf import settings

from .models import AssetClass, GlidepathRule
from .services import import_glidepath_rules


class ImportRulesTests(TestCase):
    def test_import_sample_csv(self):
        sample = settings.BASE_DIR / "sample-glidepath-rule.csv"
        with open(sample, "rb") as f:
            import_glidepath_rules(f)
        self.assertTrue(GlidepathRule.objects.exists())
        self.assertTrue(AssetClass.objects.filter(name="Stocks").exists())
        first_rule = GlidepathRule.objects.order_by("gt_retire_age").first()
        self.assertEqual(first_rule.gt_retire_age, -100)
