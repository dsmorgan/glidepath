import io
from datetime import date
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import TestCase

from .models import (
    AssetClass, GlidepathRule, RuleSet,
    User, AccountUpload, AccountPosition, FundProvider, VirtualFund,
)
from .services import export_glidepath_rules, import_glidepath_rules
from .account_services import parse_nysaves_csv
from . import scraper_service


class ImportRulesTests(TestCase):
    def test_import_sample_csv(self):
        sample = settings.BASE_DIR / "sample_input" / "sample-glidepath-rule.csv"
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
            "-100,100,100%,0%,100%\n"
        )
        f = io.BytesIO(csv_data.encode("utf-8"))
        f.name = "rules.csv"
        rs = import_glidepath_rules(f)
        exported = export_glidepath_rules(rs)
        header = exported.splitlines()[0]
        self.assertIn("Stocks:Large Cap", header)
        self.assertNotIn("Bonds", header)

    def test_unique_ruleset_names(self):
        data = "gt-retire-age,lt-retire-age,Stocks,Stocks:Large Cap\n-100,100,100%,100%\n"
        for _ in range(2):
            f = io.BytesIO(data.encode("utf-8"))
            f.name = "rules.csv"
            import_glidepath_rules(f)
        names = list(RuleSet.objects.order_by("id").values_list("name", flat=True))
        self.assertEqual(names[0], "rules")
        self.assertEqual(names[1], "rules (1)")

    def test_missing_years_raise_error(self):
        data = (
            "gt-retire-age,lt-retire-age,Stocks,Stocks:Large Cap\n"
            "-100,0,100%,100%\n"
            "1,100,100%,100%\n"
        )
        f = io.BytesIO(data.encode("utf-8"))
        with self.assertRaises(ValueError) as cm:
            import_glidepath_rules(f)
        self.assertIn("Missing", str(cm.exception))

    def test_overlapping_years_raise_error(self):
        data = (
            "gt-retire-age,lt-retire-age,Stocks,Stocks:Large Cap\n"
            "-100,10,100%,100%\n"
            "5,100,100%,100%\n"
        )
        f = io.BytesIO(data.encode("utf-8"))
        with self.assertRaises(ValueError) as cm:
            import_glidepath_rules(f)
        self.assertIn("Overlapping", str(cm.exception))


def _csv_file(text, name="nysaves.csv"):
    f = io.BytesIO(text.encode("utf-8"))
    f.name = name
    return f


class NYSavesParserTests(TestCase):
    """The NYSaves catalog is seeded by migration 0020, so funds exist in the test DB."""

    def setUp(self):
        self.user = User.objects.create(username="parent", email="parent@example.com")

    def test_matched_and_unmatched(self):
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-001,Child 1 529,Growth Stock Index Portfolio,45.231,20.00,\n"
            "NYS-001,Child 1 529,Bond Market Index Portfolio,12.5,10.00,\n"
            "NYS-002,Child 2 529,Totally Made Up Portfolio,5,,\n"
        )
        result = parse_nysaves_csv(_csv_file(text), self.user, "nysaves.csv")

        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["unmatched"], ["Totally Made Up Portfolio"])

        upload = result["upload"]
        self.assertEqual(upload.upload_type, "nysaves")
        self.assertEqual(upload.account_type, "education")
        self.assertEqual(upload.fund_provider.slug, "nysaves")
        self.assertEqual(upload.entry_count, 2)

        pos = AccountPosition.objects.get(upload=upload, account_number="NYS-001",
                                          symbol="growth-stock-index")
        self.assertIsNotNone(pos.virtual_fund)
        self.assertEqual(pos.current_value, str(Decimal("45.231") * Decimal("20.00")))

    def test_price_fallback_to_scraped_unit_price(self):
        fund = VirtualFund.objects.get(slug="moderate-growth")
        fund.unit_price = Decimal("15.00")
        fund.save(update_fields=["unit_price"])

        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-001,529,Moderate Growth Portfolio,10,,\n"  # no price/value -> use 15.00
        )
        result = parse_nysaves_csv(_csv_file(text), self.user, "nysaves.csv")
        fund.refresh_from_db()  # unit_price is stored at 4 decimal places
        pos = AccountPosition.objects.get(upload=result["upload"])
        self.assertEqual(pos.last_price, str(fund.unit_price))
        self.assertEqual(pos.current_value, str(Decimal("10") * fund.unit_price))

    def test_all_unmatched_raises(self):
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-001,529,Not A Real Fund,5,,\n"
        )
        with self.assertRaises(ValueError) as cm:
            parse_nysaves_csv(_csv_file(text), self.user, "nysaves.csv")
        self.assertIn("No portfolio names matched", str(cm.exception))

    def test_reupload_replaces_prior(self):
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-001,529,Income Portfolio,10,5.00,\n"
        )
        parse_nysaves_csv(_csv_file(text), self.user, "same.csv")
        parse_nysaves_csv(_csv_file(text), self.user, "same.csv")
        self.assertEqual(
            AccountUpload.objects.filter(user=self.user, filename="same.csv").count(), 1
        )

    def test_missing_required_column_raises(self):
        text = "Account Number,Account Name,Units\nNYS-001,529,10\n"
        with self.assertRaises(ValueError) as cm:
            parse_nysaves_csv(_csv_file(text), self.user, "bad.csv")
        self.assertIn("Portfolio Name", str(cm.exception))


class ScraperServiceTests(TestCase):
    def test_parse_nysaves_performance(self):
        records = [
            {"fundName": "Growth Stock Index Portfolio", "price": 129.79, "priceDate": "2026-06-26"},
            {"fundName": "Bond Market Index Portfolio", "price": "19.44", "priceDate": "2026-06-26T00:00:00"},
            {"fundName": "Broken", "price": "n/a", "priceDate": ""},  # skipped (unparseable)
        ]
        prices = scraper_service.parse_nysaves_performance(records)
        self.assertEqual(prices["Growth Stock Index Portfolio"][0], Decimal("129.79"))
        self.assertEqual(prices["Bond Market Index Portfolio"][0], Decimal("19.44"))
        self.assertEqual(prices["Growth Stock Index Portfolio"][1].isoformat(), "2026-06-26")
        self.assertNotIn("Broken", prices)

    def test_normalize_bridges_feed_naming(self):
        # Feed uses 'US ... ' and 'Global Equity Fund'; catalog uses 'U.S. ...' and '... Portfolio'.
        norm = scraper_service._normalize_name
        self.assertEqual(norm("U.S. Stock Market Index Portfolio"),
                         norm("US Stock Market Index Portfolio"))
        self.assertEqual(norm("Global Equity Portfolio"), norm("Global Equity Fund"))

    def test_refresh_updates_matching_funds(self):
        feed = {
            "US Stock Market Index Portfolio": (Decimal("12.39"), date(2026, 6, 26)),  # 'U.S.' in catalog
            "Global Equity Fund": (Decimal("85.55"), date(2026, 6, 26)),  # 'Portfolio' in catalog
            "New York Target Enrollment 2031 Portfolio": (Decimal("13.5"), None),  # not seeded
        }
        with mock.patch.dict(scraper_service.SCRAPERS,
                             {"nysaves": lambda provider: feed}):
            result = scraper_service.refresh_virtual_fund_prices("nysaves")

        self.assertEqual(result["updated"], 2)
        self.assertIn("New York Target Enrollment 2031 Portfolio", result["unmatched_scraped"])

        fund = VirtualFund.objects.get(slug="us-stock-market-index")
        self.assertEqual(fund.unit_price, Decimal("12.39"))
        self.assertEqual(fund.price_as_of, date(2026, 6, 26))

        provider = FundProvider.objects.get(slug="nysaves")
        self.assertIsNotNone(provider.last_price_refresh)
