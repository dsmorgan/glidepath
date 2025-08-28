import io

from django.conf import settings
from django.test import TestCase

from .models import AssetClass, GlidepathRule, RuleSet
from .services import export_glidepath_rules, import_glidepath_rules


class ImportRulesTests(TestCase):
    def test_import_sample_csv(self):
        sample = settings.BASE_DIR / "sample-glidepath-rule.csv"
        with open(sample, "rb") as f:
            rs = import_glidepath_rules(f)
        self.assertTrue(GlidepathRule.objects.filter(ruleset=rs).exists())
        self.assertTrue(AssetClass.objects.filter(name="Stocks").exists())
        first_rule = GlidepathRule.objects.filter(ruleset=rs).order_by("gt_retire_age").first()
        self.assertEqual(first_rule.gt_retire_age, -100)
        self.assertEqual(rs.name, "sample-glidepath-rule")

    def test_import_normalizes_and_export_skips_zero(self):
        csv_data = (
            "gt-retire-age,lt-retire-age,Stocks,Bonds,Stocks : Large Cap\n"
            "0,1,100%,0%,100%\n"
        )
        f = io.BytesIO(csv_data.encode("utf-8"))
        f.name = "rules.csv"
        rs = import_glidepath_rules(f)
        exported = export_glidepath_rules(rs)
        header = exported.splitlines()[0]
        self.assertIn("Stocks:Large Cap", header)
        self.assertNotIn("Bonds", header)

    def test_unique_ruleset_names(self):
        data = "gt-retire-age,lt-retire-age,Stocks,Stocks:Large Cap\n0,1,100%,100%\n"
        for _ in range(2):
            f = io.BytesIO(data.encode("utf-8"))
            f.name = "rules.csv"
            import_glidepath_rules(f)
        names = list(RuleSet.objects.order_by("id").values_list("name", flat=True))
        self.assertEqual(names[0], "rules")
        self.assertEqual(names[1], "rules (1)")
