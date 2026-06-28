import io
from datetime import date
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import (
    AssetClass, AssetCategory, GlidepathRule, RuleSet, ClassAllocation,
    User, AccountUpload, AccountPosition, FundProvider, VirtualFund, Fund,
    Portfolio, PortfolioItem,
)
from .services import export_glidepath_rules, import_glidepath_rules
from .account_services import (
    parse_nysaves_csv, get_portfolio_analysis, resolve_position_asset_categories,
)
from .forms import PortfolioForm, VirtualFundCompositionFormSet
from .models import VirtualFundComposition
from .education_projection import (
    calculate_education_projection, calculate_required_contribution,
)
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
        self.assertIn("unmatched portfolio names", str(cm.exception))

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

    def test_unvaluable_rows_reported_not_imported(self):
        # Income Portfolio has no seeded price; bad units can't be parsed. Both are
        # skipped and reported, not silently imported as $0.
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-1,Kid,Growth Stock Index Portfolio,5,12.00,\n"   # valid (price given)
            "NYS-1,Kid,Income Portfolio,10,,\n"                    # no price available
            "NYS-1,Kid,Bond Market Index Portfolio,abc,5.00,\n"   # invalid units
        )
        result = parse_nysaves_csv(_csv_file(text), self.user, "n.csv")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(AccountPosition.objects.filter(upload=result["upload"]).count(), 1)

    def test_all_unvaluable_raises(self):
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "NYS-1,Kid,Income Portfolio,10,,\n"  # no price, never scraped
        )
        with self.assertRaises(ValueError):
            parse_nysaves_csv(_csv_file(text), self.user, "n.csv")


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


class PortfolioAnalysisTests(TestCase):
    """Composition explosion and education-ruleset support in get_portfolio_analysis."""

    def setUp(self):
        self.user = User.objects.create(username="p", email="p@example.com")

    def _upload_529(self, units="50", price="20.00"):
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            f"NYS-1,Kid,Moderate Growth Portfolio,{units},{price},\n"
        )
        return parse_nysaves_csv(_csv_file(text), self.user, "n.csv")

    def test_resolve_position_asset_categories_explodes_virtual(self):
        pos = AccountPosition.objects.get(upload=self._upload_529()["upload"])
        contributions = resolve_position_asset_categories(pos)
        # Moderate Growth has 4 composition rows; value portions sum to the holding.
        self.assertEqual(len(contributions), 4)
        self.assertAlmostEqual(float(sum(v for (_c, _p, v) in contributions)), 1000.0, places=2)

    def test_virtual_fund_explodes_into_categories(self):
        self._upload_529()  # 50 units x $20 = $1000 in Moderate Growth
        pf = Portfolio.objects.create(user=self.user, name="529", account_type="education")
        PortfolioItem.objects.create(portfolio=pf, account_number="NYS-1", symbol="moderate-growth")

        a = get_portfolio_analysis(pf)
        self.assertAlmostEqual(a["total_value"], 1000.0, places=2)
        # Moderate Growth: Stocks 36+24=60%, Bonds 28+12=40%
        self.assertAlmostEqual(a["class_breakdown"]["Stocks"], 600.0, places=2)
        self.assertAlmostEqual(a["class_breakdown"]["Bonds"], 400.0, places=2)
        self.assertAlmostEqual(a["category_breakdown"]["Stocks:US Total Market"], 360.0, places=2)
        self.assertAlmostEqual(a["category_breakdown"]["Bonds:US Investment Grade"], 280.0, places=2)
        self.assertEqual(a["account_type"], "education")

    def test_education_ruleset_target_keyed_on_enrollment(self):
        self._upload_529()
        rs = RuleSet.objects.create(name="edu", account_type="education")
        rule = GlidepathRule.objects.create(ruleset=rs, gt_retire_age=-100, lt_retire_age=100)
        ClassAllocation.objects.create(rule=rule, asset_class=AssetClass.objects.get(name="Stocks"),
                                       percentage=Decimal("50"))
        ClassAllocation.objects.create(rule=rule, asset_class=AssetClass.objects.get(name="Bonds"),
                                       percentage=Decimal("50"))
        pf = Portfolio.objects.create(user=self.user, name="529b", account_type="education",
                                      ruleset=rs, years_to_enrollment=10)
        PortfolioItem.objects.create(portfolio=pf, account_number="NYS-1", symbol="moderate-growth")

        a = get_portfolio_analysis(pf)
        self.assertEqual(a["target_class_breakdown"], {"Stocks": 50.0, "Bonds": 50.0})
        self.assertIsNone(a["years_to_retirement"])  # retirement framing not used for education
        self.assertEqual(a["years_to_enrollment"], 10)

    def test_retirement_real_fund_path_unchanged(self):
        """Regression lock: the real-ticker retirement path still aggregates as before."""
        stocks = AssetClass.objects.get(name="Stocks")
        cat = AssetCategory.objects.create(name="Test Large Cap", asset_class=stocks)
        Fund.objects.create(ticker="VTI", name="Vanguard Total", category=cat)
        upload = AccountUpload.objects.create(user=self.user, file_datetime="x",
                                              upload_type="fidelity", filename="f.csv", entry_count=1)
        AccountPosition.objects.create(upload=upload, account_number="ACC1", symbol="VTI",
                                       description="", quantity="10", current_value="1000")

        rs = RuleSet.objects.create(name="ret-rs")  # default account_type='retirement'
        rule = GlidepathRule.objects.create(ruleset=rs, gt_retire_age=-100, lt_retire_age=100)
        ClassAllocation.objects.create(rule=rule, asset_class=stocks, percentage=Decimal("100"))
        pf = Portfolio.objects.create(user=self.user, name="ret", account_type="retirement",
                                      ruleset=rs, year_born=1990, retirement_age=65)
        PortfolioItem.objects.create(portfolio=pf, account_number="ACC1", symbol="VTI")

        a = get_portfolio_analysis(pf)
        self.assertAlmostEqual(a["class_breakdown"]["Stocks"], 1000.0, places=2)
        # retirement time-window still resolves via year_born/retirement_age
        self.assertEqual(a["years_to_retirement"], a["current_year"] - 1990 - 65)
        self.assertEqual(a["target_class_breakdown"], {"Stocks": 100.0})
        self.assertEqual(a["account_type"], "retirement")


class PortfolioFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="f", email="f@example.com")

    def test_create_education_portfolio_saves_fields(self):
        form = PortfolioForm(
            {
                "name": "Edu1", "account_type": "education",
                "years_to_enrollment": "10", "annual_withdrawal": "30000",
                "annual_contribution": "5000", "return_assumption": "6.00",
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        portfolio = form.save(commit=False)
        portfolio.user = self.user
        portfolio.save()
        self.assertEqual(portfolio.account_type, "education")
        self.assertEqual(portfolio.years_to_enrollment, 10)
        self.assertEqual(portfolio.college_duration_years, 4)  # default applied when blank
        self.assertEqual(portfolio.annual_withdrawal, Decimal("30000"))

    def test_retirement_portfolio_does_not_require_education_fields(self):
        form = PortfolioForm(
            {"name": "Ret1", "account_type": "retirement",
             "year_born": "1990", "retirement_age": "65"},
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        portfolio = form.save(commit=False)
        portfolio.user = self.user
        portfolio.save()
        self.assertEqual(portfolio.account_type, "retirement")
        self.assertEqual(portfolio.college_duration_years, 4)

    def test_ruleset_options_tagged_with_account_type(self):
        RuleSet.objects.create(name="edu-rs", account_type="education")
        form = PortfolioForm(user=self.user)
        html = str(form["ruleset"])
        self.assertIn('data-account-type="education"', html)


class EducationProjectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="e", email="e@example.com")

    def test_required_contribution_zero_return(self):
        # 10 accumulation years + 4 withdrawals of 10k at 0% return -> 10C = 40k -> C = 4000
        req = calculate_required_contribution(Decimal("0"), 10, 4, Decimal("10000"), Decimal("0"))
        self.assertEqual(req, Decimal("4000"))

    def test_required_contribution_none_when_enrolled(self):
        self.assertIsNone(
            calculate_required_contribution(Decimal("0"), 0, 4, Decimal("10000"), Decimal("0"))
        )

    def test_projection_on_track(self):
        pf = Portfolio.objects.create(
            user=self.user, name="529proj", account_type="education",
            years_to_enrollment=10, college_duration_years=4,
            annual_withdrawal=Decimal("10000"), annual_contribution=Decimal("4000"),
            return_assumption=Decimal("0"),
        )
        proj = calculate_education_projection(pf)
        self.assertTrue(proj["available"])
        self.assertEqual(len(proj["rows"]), 15)  # 10 accumulation + 4 withdrawal + start
        self.assertAlmostEqual(proj["projected_balance_at_enrollment"], 40000.0, places=2)
        self.assertAlmostEqual(proj["projected_balance_at_graduation"], 0.0, places=2)
        self.assertFalse(proj["shortfall"])
        self.assertAlmostEqual(proj["required_annual_contribution"], 4000.0, places=2)

    def test_projection_shortfall(self):
        pf = Portfolio.objects.create(
            user=self.user, name="529short", account_type="education",
            years_to_enrollment=5, college_duration_years=4,
            annual_withdrawal=Decimal("20000"), annual_contribution=Decimal("0"),
            return_assumption=Decimal("0"),
        )
        proj = calculate_education_projection(pf)
        self.assertTrue(proj["shortfall"])
        self.assertGreater(proj["funding_gap"], 0)

    def test_projection_unavailable_when_inputs_missing(self):
        pf = Portfolio.objects.create(
            user=self.user, name="529bad", account_type="education",
        )  # no years_to_enrollment / return / withdrawal
        proj = calculate_education_projection(pf)
        self.assertFalse(proj["available"])
        self.assertIn("Years to Enrollment", proj["missing"])

    def test_dashboard_view_renders(self):
        pf = Portfolio.objects.create(
            user=self.user, name="529view", account_type="education",
            years_to_enrollment=8, annual_withdrawal=Decimal("15000"),
            return_assumption=Decimal("6"),
        )
        session = self.client.session
        session["user_id"] = str(self.user.id)
        session.save()
        resp = self.client.get(reverse("education_dashboard", args=[pf.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "529 dashboard")

    def test_dashboard_holdings_uses_nysaves_upload(self):
        # A later Fidelity upload shares the account number and symbol; the dashboard
        # must still source holdings from the NYSaves upload (virtual_fund set).
        text = (
            "Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value\n"
            "ACCT-X,Kid,Growth Stock Index Portfolio,5,12.00,\n"
        )
        parse_nysaves_csv(_csv_file(text), self.user, "n.csv")
        fid = AccountUpload.objects.create(user=self.user, file_datetime="x",
                                           upload_type="fidelity", filename="f.csv", entry_count=1)
        AccountPosition.objects.create(upload=fid, account_number="ACCT-X",
                                       symbol="growth-stock-index", description="",
                                       quantity="1", current_value="999")
        pf = Portfolio.objects.create(user=self.user, name="dash", account_type="education",
                                      years_to_enrollment=5, annual_withdrawal=Decimal("1"),
                                      return_assumption=Decimal("6"))
        PortfolioItem.objects.create(portfolio=pf, account_number="ACCT-X", symbol="growth-stock-index")
        session = self.client.session
        session["user_id"] = str(self.user.id)
        session.save()
        resp = self.client.get(reverse("education_dashboard", args=[pf.id]))
        self.assertContains(resp, "Growth Stock Index Portfolio")  # fund name => NYSaves upload used

    def test_dashboard_denies_other_users_portfolio(self):
        owner = User.objects.create(username="owner", email="owner@example.com")
        pf = Portfolio.objects.create(user=owner, name="theirs", account_type="education",
                                      years_to_enrollment=8, annual_withdrawal=Decimal("1"),
                                      return_assumption=Decimal("6"))
        # self.user is logged in but does not own the portfolio -> redirected away.
        session = self.client.session
        session["user_id"] = str(self.user.id)
        session.save()
        resp = self.client.get(reverse("education_dashboard", args=[pf.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/portfolios/", resp["Location"])


class AccessControlTests(TestCase):
    """Owner-only scoping on portfolio/account-upload routes (IDOR hardening)."""

    def setUp(self):
        self.owner = User.objects.create(username="owner", email="owner@example.com")
        self.other = User.objects.create(username="other", email="other@example.com")
        self.upload = AccountUpload.objects.create(
            user=self.owner, file_datetime="x", upload_type="fidelity",
            filename="f.csv", entry_count=0,
        )
        self.portfolio = Portfolio.objects.create(user=self.owner, name="owned")

    def _login(self, user):
        session = self.client.session
        session["user_id"] = str(user.id)
        session.save()

    def test_non_owner_cannot_view_or_delete_upload(self):
        self._login(self.other)
        self.assertEqual(
            self.client.get(reverse("view_account_upload", args=[self.upload.id])).status_code, 302
        )
        self.client.post(reverse("delete_account_upload", args=[self.upload.id]))
        self.assertTrue(AccountUpload.objects.filter(id=self.upload.id).exists())

    def test_non_owner_cannot_edit_delete_or_download_portfolio(self):
        self._login(self.other)
        self.assertEqual(
            self.client.get(reverse("edit_portfolio", args=[self.portfolio.id])).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("download_portfolio_csv", args=[self.portfolio.id])).status_code, 302
        )
        self.client.post(reverse("delete_portfolio", args=[self.portfolio.id]))
        self.assertTrue(Portfolio.objects.filter(id=self.portfolio.id).exists())

    def test_owner_can_access(self):
        self._login(self.owner)
        self.assertEqual(
            self.client.get(reverse("view_account_upload", args=[self.upload.id])).status_code, 200
        )
        resp = self.client.get(reverse("download_portfolio_csv", args=[self.portfolio.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_admin_can_access_other_users_portfolio(self):
        admin = User.objects.create(username="admin", email="admin@example.com", role=0)
        session = self.client.session
        session["user_id"] = str(admin.id)
        session["is_admin"] = True
        session.save()
        self.assertEqual(
            self.client.get(reverse("edit_portfolio", args=[self.portfolio.id])).status_code, 200
        )


class VirtualFundAdminTests(TestCase):
    """Admin CRUD for providers/funds/compositions + price refresh."""

    def setUp(self):
        self.admin = User.objects.create(username="adm", email="adm@example.com", role=0)
        self.provider = FundProvider.objects.get(slug="nysaves")  # seeded

    def _login(self, admin=True):
        session = self.client.session
        session["user_id"] = str(self.admin.id)
        if admin:
            session["is_admin"] = True
        session.save()

    def test_list_view_renders(self):
        self._login(admin=False)
        resp = self.client.get(reverse("virtual_funds"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "NY 529 Direct Plan")

    def test_non_admin_cannot_create_provider(self):
        self._login(admin=False)
        resp = self.client.post(reverse("fund_provider_add"),
                                {"name": "X", "slug": "x", "price_source_url": "",
                                 "price_scraper": "", "notes": ""})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(FundProvider.objects.filter(slug="x").exists())

    def test_admin_creates_provider(self):
        self._login()
        resp = self.client.post(reverse("fund_provider_add"),
                                {"name": "Vanguard 529", "slug": "vanguard-529",
                                 "price_source_url": "", "price_scraper": "", "notes": ""})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(FundProvider.objects.filter(slug="vanguard-529").exists())

    def _composition_data(self, p1, p2):
        cat1 = AssetCategory.objects.get(name="US Total Market", asset_class__name="Stocks")
        cat2 = AssetCategory.objects.get(name="International Market", asset_class__name="Stocks")
        return {
            "composition-TOTAL_FORMS": "2", "composition-INITIAL_FORMS": "0",
            "composition-MIN_NUM_FORMS": "0", "composition-MAX_NUM_FORMS": "1000",
            "composition-0-asset_category": str(cat1.id), "composition-0-percentage": str(p1), "composition-0-id": "",
            "composition-1-asset_category": str(cat2.id), "composition-1-percentage": str(p2), "composition-1-id": "",
        }

    def test_composition_formset_requires_100(self):
        fund = VirtualFund.objects.create(provider=self.provider, name="T", slug="t-fund")
        self.assertTrue(VirtualFundCompositionFormSet(self._composition_data(60, 40), instance=fund).is_valid())
        bad = VirtualFundCompositionFormSet(self._composition_data(60, 30), instance=fund)
        self.assertFalse(bad.is_valid())
        self.assertIn("100%", str(bad.non_form_errors()))

    def test_refresh_provider_prices(self):
        from datetime import date
        feed = {"Growth Stock Index Portfolio": (Decimal("23.45"), date(2026, 6, 26))}
        self._login()
        with mock.patch.dict(scraper_service.SCRAPERS, {"nysaves": lambda p: feed}):
            resp = self.client.post(reverse("refresh_provider_prices", args=[self.provider.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(VirtualFund.objects.get(slug="growth-stock-index").unit_price, Decimal("23.45"))

    def test_non_admin_cannot_refresh(self):
        self._login(admin=False)
        resp = self.client.post(reverse("refresh_provider_prices", args=[self.provider.id]))
        self.assertEqual(resp.status_code, 403)

    def test_refresh_throttled_within_cooldown(self):
        from datetime import date
        from django.utils import timezone
        self.provider.last_price_refresh = timezone.now()  # just refreshed
        self.provider.save(update_fields=["last_price_refresh"])
        self._login()
        feed = {"Growth Stock Index Portfolio": (Decimal("99.99"), date(2026, 6, 26))}
        with mock.patch.dict(scraper_service.SCRAPERS, {"nysaves": lambda p: feed}):
            resp = self.client.post(reverse("refresh_provider_prices", args=[self.provider.id]))
        self.assertEqual(resp.status_code, 302)
        # Throttled: price was NOT re-fetched.
        self.assertNotEqual(
            VirtualFund.objects.get(slug="growth-stock-index").unit_price, Decimal("99.99")
        )

    def test_list_disables_refresh_within_cooldown(self):
        from django.utils import timezone
        self._login()
        # No recent refresh -> enabled form present.
        resp = self.client.get(reverse("virtual_funds"))
        self.assertContains(resp, "startRefresh(this)")
        # Recent refresh -> disabled button with tooltip.
        self.provider.last_price_refresh = timezone.now()
        self.provider.save(update_fields=["last_price_refresh"])
        resp = self.client.get(reverse("virtual_funds"))
        self.assertContains(resp, "prices update infrequently")
