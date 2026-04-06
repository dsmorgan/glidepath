# Glidepath: 529 & Multi-Account-Type Architecture Spec

**Status:** Draft
**Author:** David Morgan
**Last Updated:** April 2026

---

## 1. Overview

This document specifies the architectural changes required to extend Glidepath beyond retirement portfolio management to support education savings accounts (529s), starting with NYSaves (nysaves.org). The extension introduces three major concepts:

1. **Virtual Funds** — portfolio products that don’t have public tickers but have known compositions (e.g., NY 529 portfolios backed by Vanguard funds)
2. **Account Types** — a typed system for portfolios and rule sets that supports retirement, education, and future types, each with their own terminology and time windows
3. **Education Portfolio Modeling** — a parallel to retirement modeling but with a college-enrollment time horizon, fixed annual withdrawal amounts, and school duration

The underlying rule engine, fund/asset-class taxonomy, and Monte Carlo projection infrastructure are shared across account types — distinguished by an `account_type` flag rather than separate systems.

---

## 2. Goals

- Support NYSaves 529 accounts as a first-class account type alongside Fidelity and E-Trade retirement accounts
- Introduce "virtual funds" as an extensible pattern for non-publicly-traded fund products (529s, pension funds, etc.)
- Allow a portfolio to contain mixed account types (e.g., analyze a parent’s IRA and a child’s 529 together)
- Support education-specific glide path rules using the same rule engine as retirement, keyed by years to enrollment
- Model 529 growth with annual contributions, return assumptions, and fixed annual withdrawals over a college duration period
- Make the architecture extensible: adding a new 529 provider (e.g., Vanguard 529, Fidelity 529) or brokerage should require adding a parser and a fund catalog, not structural changes
- Keep NYSaves portfolio unit prices current via a manual on-demand scrape of the public Price & Performance page

---

## 3. Core Concepts

### 3.1 Account Types

Every `AccountUpload` and every `Portfolio` has an `account_type`. The system supports the following types:

| Type | Description | Time Window | Terminology |
|------|-------------|-------------|-------------|
| `retirement` | 401k, IRA, taxable brokerage | Years to retirement | "Retirement age", "Years to retirement" |
| `education` | 529 plans, ESAs | Years to enrollment | "Enrollment year", "Years to enrollment" |
| `general` | Unclassified/generic accounts | None | — |

Account type drives: which glide path rules apply, how projections are calculated, and which UI fields are shown.

### 3.2 Virtual Funds

A **Virtual Fund** is a fund-like instrument that:
- Has no public ticker symbol
- Has a unit price that must be fetched from a provider-specific source (e.g., scraping nysaves.org)
- Has a known composition expressed as percentage allocations to standard `AssetCategory` entities
- Is tied to a specific **Fund Provider** (e.g., NYSaves, Vanguard 529)

Virtual funds are stored in the database and are admin-editable. Their composition (the underlying asset breakdown) is also stored in the database, allowing updates if a provider changes fund allocations without requiring a code deployment.

**Example:** The NY 529 "Moderate Growth Portfolio" is a virtual fund with the composition:
- Stocks: US Total Market — 36%
- Stocks: International Market — 24%
- Bonds: US Total Market — 28%
- Bonds: International — 12%

When Glidepath needs to analyze this fund’s contribution to an asset allocation, it "explodes" the virtual fund into its underlying categories using this stored composition.

### 3.3 Portfolio Types and the Time Window

Both retirement and education portfolios share the same rule engine but use different time windows:

- **Retirement portfolios:** time window = `retirement_age - current_age` (years to retirement). Already implemented.
- **Education portfolios:** time window = `years_to_enrollment` (a manually entered integer, e.g. 10 years until the child starts college). Negative values indicate the student is already enrolled.

The rule engine maps a time window value to a target asset allocation. For education, the glide path typically starts aggressive (high equity when enrollment is 15+ years away) and becomes conservative (high bonds/cash) as enrollment approaches, then holds conservative through the college withdrawal period.

### 3.4 Fund Providers

A **Fund Provider** represents an institution that offers virtual funds — i.e., a 529 plan or similar product. Each provider has:
- A name and identifier (e.g., `nysaves`, `vanguard-529`, `fidelity-529`)
- A price source URL and scraping strategy
- A catalog of virtual funds

Fund providers are extensible: adding a new 529 provider means adding a new `FundProvider` record, a new set of `VirtualFund` + `VirtualFundComposition` records, and a new price-scraping parser.

---

## 4. Data Model Changes

### 4.1 New Model: `FundProvider`

Stores information about institutions that offer virtual funds (529 plans, etc.).

```python
class FundProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)                      # "NY 529 Direct Plan"
    slug = models.CharField(max_length=50, unique=True)          # "nysaves"
    price_source_url = models.URLField(blank=True)               # Public price page URL
    price_scraper = models.CharField(max_length=50, blank=True)  # Scraper identifier, e.g. "nysaves"
    notes = models.TextField(blank=True)
    last_price_refresh = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
```

### 4.2 New Model: `VirtualFund`

Represents a non-publicly-traded fund product (e.g., a NY 529 portfolio).

```python
class VirtualFund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(FundProvider, on_delete=models.CASCADE,
                                  related_name="virtual_funds")
    name = models.CharField(max_length=200)       # "NY 529 Growth Stock Index Portfolio"
    slug = models.CharField(max_length=100)        # "growth-stock-index"
    unit_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    price_as_of = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)  # Hide retired funds
    notes = models.TextField(blank=True)           # E.g., underlying Vanguard fund name

    class Meta:
        unique_together = ("provider", "slug")
        ordering = ["provider", "name"]

    def __str__(self):
        return f"{self.provider.name}: {self.name}"
```

### 4.3 New Model: `VirtualFundComposition`

Stores the asset category breakdown for a virtual fund. Admin-editable so it can be updated if provider changes allocations.

```python
class VirtualFundComposition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    virtual_fund = models.ForeignKey(VirtualFund, on_delete=models.CASCADE,
                                      related_name="composition")
    asset_category = models.ForeignKey(AssetCategory, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)  # e.g., 36.00

    class Meta:
        unique_together = ("virtual_fund", "asset_category")

    def __str__(self):
        return f"{self.virtual_fund.name} -> {self.asset_category}: {self.percentage}%"
```

**Validation:** Sum of percentages for a given `VirtualFund` must equal 100%.

### 4.4 Changes to `Fund`

Add an optional link to a `VirtualFund`, and an `is_virtual` flag to distinguish real-ticker funds from virtual ones.

```python
class Fund(models.Model):
    # existing fields ...
    ticker = models.CharField(max_length=20, unique=True, blank=True)  # blank for virtual funds
    virtual_fund = models.OneToOneField(VirtualFund, on_delete=models.SET_NULL,
                                         null=True, blank=True, related_name="fund")
    is_virtual = models.BooleanField(default=False)
```

When `is_virtual=True`, the fund's ticker is auto-generated from the virtual fund's slug (e.g., `NYSAVES_GROWTH_STOCK`). The asset category mapping is driven by `VirtualFundComposition` rather than a single `category` FK.

### 4.5 Changes to `AccountUpload`

Add `account_type` to indicate what kind of account the upload represents.

```python
class AccountUpload(models.Model):
    UPLOAD_TYPE_CHOICES = [
        ('fidelity', 'Fidelity'),
        ('etrade', 'E-Trade'),
        ('nysaves', 'NY 529 (NYSaves)'),
        # future: ('vanguard_529', 'Vanguard 529'), ('fidelity_529', 'Fidelity 529')
    ]

    ACCOUNT_TYPE_CHOICES = [
        ('retirement', 'Retirement'),
        ('education', 'Education / 529'),
        ('general', 'General'),
    ]

    # existing fields ...
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES,
                                     default='retirement')
    fund_provider = models.ForeignKey(FundProvider, on_delete=models.SET_NULL,
                                       null=True, blank=True)  # set for 529 uploads
```

### 4.6 Changes to `AccountPosition`

For virtual fund positions (529 accounts), the `symbol` field stores the virtual fund's slug, and a new FK links directly to the `VirtualFund` when applicable. Unit price and quantity are always stored; `current_value` is derived.

```python
class AccountPosition(models.Model):
    # existing fields ...
    virtual_fund = models.ForeignKey(VirtualFund, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="positions")
    # 'symbol' stores virtual fund slug for 529 positions, ticker for real funds
```

### 4.7 Changes to `RuleSet`

Add `account_type` to scope rule sets to a specific portfolio type. Education rule sets use the same `GlidepathRule` rows but interpret the `gt_retire_age` / `lt_retire_age` fields as years-to-enrollment bounds.

```python
class RuleSet(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('retirement', 'Retirement'),
        ('education', 'Education / 529'),
        ('general', 'General'),
    ]

    name = models.CharField(max_length=100, unique=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES,
                                     default='retirement')
    description = models.TextField(blank=True)
```

### 4.8 Changes to `GlidepathRule`

Rename fields for clarity while keeping backward compatibility. The rule time-window fields are generalized to represent "years relative to target event" (negative = before, positive = after/in-drawdown).

```python
class GlidepathRule(models.Model):
    ruleset = models.ForeignKey(RuleSet, related_name="rules", on_delete=models.CASCADE)

    # Renamed conceptually (keep DB column names for migration simplicity,
    # but expose as 'gt_years' / 'lt_years' in the UI and serializers)
    gt_retire_age = models.IntegerField()  # "greater than N years before target"
    lt_retire_age = models.IntegerField()  # "less than N years before target"

    # Existing class/category allocations unchanged
```

For education: a rule with `gt_retire_age=-4, lt_retire_age=0` means "student is currently enrolled (0 to 4 years in)". This maps naturally to the existing structure.

### 4.9 Changes to `Portfolio`

Add `account_type` and education-specific fields.

```python
class Portfolio(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('retirement', 'Retirement'),
        ('education', 'Education / 529'),
        ('general', 'General'),
    ]

    # existing fields ...
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES,
                                     default='retirement')

    # --- Education-specific fields (null for retirement portfolios) ---
    years_to_enrollment = models.IntegerField(
        null=True, blank=True,
        help_text="Years until the student starts college (negative = already enrolled)"
    )
    college_duration_years = models.IntegerField(
        default=4,
        help_text="Number of years funds will be withdrawn for school"
    )
    annual_withdrawal = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Fixed dollar amount withdrawn per year of school"
    )
    annual_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Annual savings contribution to this portfolio (portfolio-level)"
    )
    return_assumption = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Annual return assumption percentage used for projection (e.g., 6.00)"
    )
```

**Note:** `annual_contribution` and `return_assumption` also apply to retirement portfolios for projection purposes. These fields can be populated for both types and will be used by the projection engine.

---

## 5. NYSaves Integration

### 5.1 Virtual Fund Catalog

The 18 individual NY 529 portfolios (plus Target Enrollment portfolios) are seeded into the database as `VirtualFund` records under a `FundProvider` with `slug="nysaves"`. The `VirtualFundComposition` for each portfolio maps to existing `AssetCategory` entities.

**NYSaves Individual Portfolio Compositions (to be seeded):**

| Portfolio | Asset Categories |
|-----------|-----------------|
| Growth Stock Index Portfolio | Stocks: US Large-Cap Growth (100%) |
| Global Equity Portfolio | Stocks: US Total Market (60%), Stocks: International Market (40%) |
| U.S. Stock Market Index Portfolio | Stocks: US Total Market (100%) |
| Value Stock Index Portfolio | Stocks: US Large-Cap Value (100%) |
| Mid-Cap Stock Index Portfolio | Stocks: US Mid-Cap (100%) |
| Small-Cap Stock Index Portfolio | Stocks: US Small-Cap (100%) |
| International Stock Market Index Portfolio | Stocks: International Market (100%) |
| Developed Markets Index Portfolio | Stocks: International Developed (100%) |
| Social Index Portfolio | Stocks: US Total Market / ESG (100%) |
| Growth Portfolio | Stocks: US Total Market (48%), Stocks: International Market (32%), Bonds: US Total Market (14%), Bonds: International (6%) |
| Moderate Growth Portfolio | Stocks: US Total Market (36%), Stocks: International Market (24%), Bonds: US Total Market (28%), Bonds: International (12%) |
| Conservative Growth Portfolio | Stocks: US Total Market (24%), Stocks: International Market (16%), Bonds: US Total Market (42%), Bonds: International (18%) |
| Income Portfolio | Stocks: US Total Market (12%), Stocks: International Market (8%), Bonds: US Total Market (56%), Bonds: International (24%) |
| Bond Market Index Portfolio | Bonds: US Total Market (100%) |
| International Bond Market Index Portfolio | Bonds: International (100%) |
| Short-Term Bond Market Index Portfolio | Bonds: Short-Term (100%) |
| Conservative Income Portfolio | Bonds: US Total Market (34.5%), Bonds: International (22.5%), Bonds: Short-Term Inflation-Protected (18%), Short-Term Reserves (25%) |
| Interest Accumulation Portfolio | Short-Term Reserves (100%) |

Target Enrollment Portfolios (2023-2044) are also seeded as virtual funds; their composition shifts over time and maps to a blend of the above categories per the NYSaves glide path.

### 5.2 Price Scraping

A `nysaves` scraper fetches unit prices from `https://www.nysaves.org/price-and-performance/` (public, no auth required). The page is server-rendered HTML with a clean table structure.

**Scraper behavior:**
- Parses the HTML table on the Price & Performance page
- Extracts portfolio name, unit price, and price date for all listed funds
- Matches each row to a `VirtualFund` by name (normalized string match)
- Updates `unit_price` and `price_as_of` on matching records
- Updates `FundProvider.last_price_refresh`
- Returns a summary: how many prices were updated, any names that failed to match

**Trigger:** Manual on-demand via a "Refresh Prices" button in the UI (on the Virtual Funds admin page and/or the portfolio detail page). No scheduled job in the initial implementation.

**Implementation:** A new `scraper_service.py` module with a `refresh_virtual_fund_prices(provider_slug)` function. The NYSaves scraper is the first implementation; future providers add their own scraper keyed by `provider.price_scraper`.

### 5.3 NYSaves Holdings Input Format

Since NYSaves has no export feature, holdings are entered via a purpose-built CSV format or a manual entry UI form.

**CSV format (`nysaves` upload type):**

```
Account Number,Account Name,Portfolio Name,Units,Unit Price,Current Value
NYS-001,Child 1 529,Growth Stock Index Portfolio,45.231,,
NYS-001,Child 1 529,Bond Market Index Portfolio,12.500,,
NYS-002,Child 2 529,Moderate Growth Portfolio,88.750,,
```

- `Unit Price` and `Current Value` are optional — if omitted, the system uses the most recent scraped unit price for the virtual fund
- `Account Number` is user-defined (not from NYSaves) — used to group positions within a portfolio
- `Portfolio Name` must match a known `VirtualFund.name` for the NYSaves provider (case-insensitive)

**Parser:** A new `parse_nysaves_csv()` function in `account_services.py`, similar in structure to the existing Fidelity/E-Trade parsers. Creates `AccountUpload` (with `upload_type='nysaves'`, `account_type='education'`) and `AccountPosition` records with `virtual_fund` FK populated.

---

## 6. Education Portfolio Modeling

### 6.1 Time Window

The education glide path is anchored to `years_to_enrollment` on the `Portfolio`:

- Positive value (e.g., 12): 12 years until the student starts college
- Zero: The student starts college this year
- Negative (e.g., -2): The student is 2 years into a 4-year program

The rule lookup uses `years_to_enrollment` in place of `years_to_retirement`. A portfolio's applicable rule is the `GlidepathRule` where `gt_retire_age < years_to_enrollment <= lt_retire_age`.

### 6.2 Projection Model

The education projection calculates a forward-looking balance trajectory from today through the end of the college withdrawal period.

**Inputs (from Portfolio):**
- `current_balance` — computed from positions
- `years_to_enrollment` — time until college starts
- `college_duration_years` — default 4
- `annual_contribution` — fixed dollar amount added per year (portfolio level)
- `annual_withdrawal` — fixed dollar amount withdrawn per year during school
- `return_assumption` — annual return rate (e.g., 6.00%)

**Phases:**

**Phase 1 — Accumulation** (years 0 through `years_to_enrollment - 1`):
```
balance[t+1] = balance[t] x (1 + return_assumption) + annual_contribution
```

**Phase 2 — Withdrawal** (years `years_to_enrollment` through `years_to_enrollment + college_duration_years - 1`):
```
balance[t+1] = balance[t] x (1 + return_assumption) - annual_withdrawal
```

**Output:** A year-by-year balance table. If balance hits zero during withdrawal, this is flagged as a shortfall.

**Derived metrics:**
- `projected_balance_at_enrollment` — Phase 1 end balance
- `projected_balance_at_graduation` — Phase 2 end balance (may be negative if underfunded)
- `total_withdrawals` — `annual_withdrawal x college_duration_years`
- `funding_gap` — max(0, total_withdrawals - projected_balance_at_enrollment) adjusted for in-school returns
- `required_annual_contribution` — back-solved: what annual contribution is needed to fully fund total_withdrawals?

**Implementation:** A new `education_projection.py` service (analogous to `monte_carlo.py` for retirement). The Monte Carlo module may be extended separately to run probabilistic scenarios for education projections.

### 6.3 Rebalancing for Education

When the user asks "how should I rebalance my 529?", the system:

1. Looks up the portfolio's `years_to_enrollment`
2. Finds the matching `GlidepathRule` in the assigned education `RuleSet`
3. Computes the current asset allocation by exploding virtual fund positions into their `VirtualFundComposition` categories
4. Compares current vs. target allocation
5. Returns rebalancing recommendations: which virtual funds to buy/sell and by how much (in units and dollars), constrained by the available NYSaves funds

**Constraint:** NYSaves allows only 2 investment exchanges per calendar year. This limit should be surfaced as a warning in the UI when displaying rebalancing recommendations.

---

## 7. Glidepath Rules for Education

### 7.1 Sample Education RuleSet Structure

An education `RuleSet` contains `GlidepathRule` rows where the time-window fields represent years to enrollment (not years to retirement). Negative values represent years already enrolled.

**Example (aggressive-to-conservative education glide path):**

| Years to Enrollment | Stocks % | Bonds % | Notes |
|---------------------|----------|---------|-------|
| > 15 | 90% | 10% | Very long horizon |
| 10-15 | 80% | 20% | Long horizon |
| 5-10 | 70% | 30% | Medium horizon |
| 2-5 | 50% | 50% | Approaching enrollment |
| 0-2 | 30% | 70% | Near enrollment |
| -4-0 (enrolled) | 20% | 80% | In school, drawing down |

Within Stocks/Bonds, the category breakdown (US Total Market, International, etc.) follows the same `CategoryAllocation` structure as retirement rules.

### 7.2 UI Terminology for Education Rules

When a `RuleSet` has `account_type='education'`, the UI relabels fields:
- "Years to Retirement" -> "Years to Enrollment"
- "Retirement Age" -> "Enrollment Year / Age"
- "gt_retire_age / lt_retire_age" column headers -> "From (years)" / "To (years)"

---

## 8. Mixed Portfolios

A portfolio with `account_type='general'` (or any type) can contain `PortfolioItem` entries drawn from accounts of different upload types. The asset allocation analysis works the same way: each position contributes to the overall allocation via its fund's `AssetCategory` (or `VirtualFundComposition` for virtual funds).

When a mixed portfolio is used for glide path analysis, it must have a `ruleset` assigned. The ruleset's `account_type` determines which time-window field is used (`years_to_retirement` for retirement rules, `years_to_enrollment` for education rules). Mixed portfolios without a clear account type can use any ruleset but the user is responsible for consistency.

The UI should surface a warning when a portfolio contains both retirement and education account positions, as the blended analysis may not be meaningful for rebalancing purposes.

---

## 9. Service Layer Changes

### 9.1 `account_services.py`

**Add:**
- `parse_nysaves_csv(file_content, user, filename)` — parses NYSaves holding CSV format, creates `AccountUpload` + `AccountPosition` records with virtual fund linkages
- `get_portfolio_analysis()` — extend to handle virtual fund composition explosion when computing asset allocation
- `resolve_position_asset_categories(position)` — returns a list of `(AssetCategory, effective_percentage, effective_value)` for any position, handling both real-ticker funds (single category) and virtual funds (composition-exploded)

### 9.2 `scraper_service.py` (new)

```python
def refresh_virtual_fund_prices(provider_slug: str) -> dict:
    """Scrape and update unit prices for all virtual funds under a given provider."""

def _scrape_nysaves_prices() -> dict[str, Decimal]:
    """Scrape nysaves.org/price-and-performance/ and return {fund_name: unit_price}."""
```

### 9.3 `education_projection.py` (new)

```python
def calculate_education_projection(portfolio) -> dict:
    """
    Returns year-by-year balance projection for an education portfolio.
    Keys: years (list), balances (list), projected_at_enrollment,
          projected_at_graduation, funding_gap, required_annual_contribution
    """

def calculate_required_contribution(current_balance, years_to_enrollment,
                                     college_duration, annual_withdrawal,
                                     return_assumption) -> Decimal:
    """Back-solve: what annual contribution fully funds the withdrawal plan?"""
```

### 9.4 `services.py`

- Extend `import_glidepath_rules_csv()` to set `account_type` on the created `RuleSet` based on a header field in the CSV
- Add validation that a `RuleSet`'s `account_type` matches the `Portfolio.account_type` it's assigned to (warning, not hard block)

### 9.5 `ticker_service.py`

- Extend `get_fund_price()` to handle virtual funds: return `virtual_fund.unit_price` instead of fetching from a market data API
- Add `get_portfolio_current_value()` to aggregate across both real and virtual fund positions

---

## 10. UI / UX Changes

### 10.1 Portfolio Creation / Edit

- Add account type selector: Retirement / Education / General
- Show education-specific fields when Education is selected:
  - Years to Enrollment (integer, can be negative)
  - College Duration (default: 4 years)
  - Annual Withdrawal (dollar amount)
  - Annual Contribution (dollar amount)
  - Return Assumption (percentage)

### 10.2 Education Portfolio Dashboard

New view/tab for education portfolios showing:
- Current balance breakdown by virtual fund (name, units, unit price, value)
- Asset allocation breakdown (exploded from virtual fund composition)
- Target allocation from the assigned education rule set
- Rebalancing recommendations (with NYSaves 2-exchanges-per-year warning)
- Projection chart: year-by-year balance through enrollment and graduation
- Funding gap / required contribution callout

### 10.3 Virtual Fund Management (Admin)

Admin-accessible pages for:
- Fund Providers: list, add, edit
- Virtual Funds: list by provider, add/edit fund with current price and date, link to compositions
- Virtual Fund Compositions: edit percentage breakdowns per fund (with running total validation)
- "Refresh Prices" button on provider detail page — triggers `refresh_virtual_fund_prices()` and shows a results summary

### 10.4 NYSaves Upload Page

A new upload type option on the existing account positions upload page:
- Dropdown: Fidelity / E-Trade / **NY 529 (NYSaves)**
- When NYSaves is selected: show the expected CSV format, link to a downloadable template
- After upload: show matched vs. unmatched virtual fund names, prompt user to resolve unmatched names

### 10.5 RuleSet UI

- Add account type label to rule set list view
- Filter rule set selector on portfolio edit to show only rule sets matching the portfolio's account type
- Relabel time-window columns based on account type when editing rules

---

## 11. Migrations

Migrations will be created for:

1. `FundProvider` table (new)
2. `VirtualFund` table (new)
3. `VirtualFundComposition` table (new)
4. `Fund.is_virtual`, `Fund.virtual_fund` FK, `Fund.ticker` allow-blank (alter)
5. `AccountUpload.account_type`, `AccountUpload.fund_provider` FK (alter)
6. `AccountPosition.virtual_fund` FK (alter)
7. `RuleSet.account_type`, `RuleSet.description` (alter)
8. `Portfolio.account_type`, `Portfolio.years_to_enrollment`, `Portfolio.college_duration_years`, `Portfolio.annual_withdrawal`, `Portfolio.annual_contribution`, `Portfolio.return_assumption` (alter)

**Backward compatibility:** All new fields default to `null` or `'retirement'` so existing data is unaffected.

**Seed data migration:** A data migration seeds the NYSaves `FundProvider`, all 18+ `VirtualFund` records, and their `VirtualFundComposition` entries using the compositions documented in Section 5.1.

---

## 12. Future Extensibility

### 12.1 Adding Another 529 Provider

1. Add a `FundProvider` record (via admin or migration) with `slug`, `price_source_url`, and `price_scraper` identifier
2. Add `VirtualFund` + `VirtualFundComposition` records for that provider's portfolio lineup
3. Implement `_scrape_<provider>_prices()` in `scraper_service.py`
4. Add a new `upload_type` choice in `AccountUpload` and a corresponding parser in `account_services.py`

No model schema changes are required.

### 12.2 Adding an HSA or Other Account Type

Add a new value to the `ACCOUNT_TYPE_CHOICES` lists and create a corresponding `RuleSet` type. The projection and rule engine work as-is; only UI labels and possibly a new projection model would need to be added.

### 12.3 Scheduled Price Refresh

When automated price scraping is desired (future), add a management command `refresh_fund_prices` that calls `refresh_virtual_fund_prices()` for all active providers. This can be scheduled via cron or a task queue (Celery). No architectural changes needed — the scraper service is already written to be callable from any context.

### 12.4 Monte Carlo for Education

Extend `monte_carlo.py` to run probabilistic projections for education portfolios, varying the return assumption across simulations (e.g., using market assumption distributions from the uploaded BlackRock assumptions). This reuses the existing assumptions infrastructure.

---

## 13. Issue Breakdown (Suggested)

The following GitHub issues should be created to implement this spec:

**Infrastructure / Models**
- [ ] Add `FundProvider`, `VirtualFund`, `VirtualFundComposition` models + migrations
- [ ] Extend `Fund` model with `is_virtual` flag and `virtual_fund` FK
- [ ] Add `account_type` to `AccountUpload`, `RuleSet`, and `Portfolio` models
- [ ] Add education fields to `Portfolio` model (`years_to_enrollment`, `college_duration_years`, `annual_withdrawal`, `annual_contribution`, `return_assumption`)
- [ ] Add `virtual_fund` FK to `AccountPosition`
- [ ] Write seed data migration for NYSaves fund catalog

**NYSaves Integration**
- [ ] Implement NYSaves CSV holdings parser in `account_services.py`
- [ ] Implement NYSaves price scraper in `scraper_service.py` (new file)
- [ ] Add NYSaves upload type to upload UI and form handling
- [ ] Extend position asset-category resolution to handle virtual fund composition explosion

**Education Portfolio**
- [ ] Implement `education_projection.py` — balance projection and funding gap calculation
- [ ] Implement `calculate_required_contribution()` back-solver
- [ ] Add education portfolio dashboard view and template
- [ ] Add education-specific fields to portfolio create/edit UI

**Admin / Virtual Fund Management**
- [ ] Admin pages for FundProvider, VirtualFund, VirtualFundComposition
- [ ] "Refresh Prices" button on provider detail page (manual scrape trigger)
- [ ] Admin validation: VirtualFundComposition percentages must sum to 100%

**Glidepath Rules**
- [ ] Add `account_type` to `RuleSet` model and UI
- [ ] Filter rule set selector by account type on portfolio edit
- [ ] Relabel time-window fields in rules UI based on account type
- [ ] Add example education rule set CSV and seed data

**Rebalancing**
- [ ] Extend rebalancing recommendations to support virtual fund positions
- [ ] Surface NYSaves 2-exchanges-per-year limit warning in rebalancing UI

**Testing**
- [ ] Unit tests for NYSaves CSV parser
- [ ] Unit tests for price scraper (mocked HTML)
- [ ] Unit tests for education projection calculations
- [ ] Unit tests for virtual fund composition explosion in portfolio analysis
- [ ] Integration tests for education portfolio end-to-end flow

---

*End of spec.*
