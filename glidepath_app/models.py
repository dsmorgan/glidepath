from decimal import Decimal
import uuid
from django.db import models
from django.contrib.auth.hashers import make_password


class RuleSet(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class AssetClass(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self) -> str:
        return self.name


class AssetCategory(models.Model):
    name = models.CharField(max_length=100)
    asset_class = models.ForeignKey(
        AssetClass, on_delete=models.CASCADE, related_name="categories"
    )

    class Meta:
        unique_together = ("name", "asset_class")

    def __str__(self) -> str:
        return f"{self.asset_class.name}: {self.name}"


class GlidepathRule(models.Model):
    ruleset = models.ForeignKey(
        RuleSet, related_name="rules", on_delete=models.CASCADE, null=True
    )
    gt_retire_age = models.IntegerField()
    lt_retire_age = models.IntegerField()

    class Meta:
        unique_together = ("ruleset", "gt_retire_age", "lt_retire_age")
        ordering = ["ruleset", "gt_retire_age", "lt_retire_age"]

    def save(self, *args, **kwargs):
        self.gt_retire_age = max(-100, self.gt_retire_age)
        self.lt_retire_age = min(100, self.lt_retire_age)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.gt_retire_age} to {self.lt_retire_age}"


class ClassAllocation(models.Model):
    rule = models.ForeignKey(
        GlidepathRule, related_name="class_allocations", on_delete=models.CASCADE
    )
    asset_class = models.ForeignKey(AssetClass, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ("rule", "asset_class")

    def __str__(self) -> str:
        return f"{self.asset_class.name}: {self.percentage}%"


class CategoryAllocation(models.Model):
    rule = models.ForeignKey(
        GlidepathRule, related_name="category_allocations", on_delete=models.CASCADE
    )
    asset_category = models.ForeignKey(AssetCategory, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        unique_together = ("rule", "asset_category")

    def __str__(self) -> str:
        return f"{self.asset_category}: {self.percentage}%"


class APISettings(models.Model):
    """Stores API keys and settings for financial data sources."""
    # Only one row should exist in this table
    id = models.AutoField(primary_key=True)

    # Alpha Vantage
    alpha_vantage_api_key = models.CharField(max_length=100, blank=True, default='')

    # Finnhub
    finnhub_api_key = models.CharField(max_length=100, blank=True, default='')

    # Polygon.io
    polygon_api_key = models.CharField(max_length=100, blank=True, default='')

    # EODHD
    eodhd_api_key = models.CharField(max_length=100, blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "API Settings"
        verbose_name_plural = "API Settings"

    def __str__(self) -> str:
        return "API Settings"

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance."""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings


class Fund(models.Model):
    """Stores investment fund information including ticker, name, and category."""
    ticker = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        AssetCategory, on_delete=models.CASCADE, related_name="funds",
        null=True, blank=True
    )
    preference = models.IntegerField(
        default=99,
        help_text="Display order and recommendation priority (1-10 = recommended, lower = higher priority)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self) -> str:
        return f"{self.ticker} - {self.name}"

    def is_recommended(self):
        """Returns True if this fund is recommended (preference 1-10)."""
        return self.preference is not None and 1 <= self.preference <= 10

    def get_sort_preference(self):
        """Returns the preference value for sorting, treating NULL as 256."""
        return self.preference if self.preference is not None else 256


class IdentityProvider(models.Model):
    """Stores OAuth2/OIDC identity provider configurations."""

    PROVIDER_TYPE_CHOICES = [
        (0, "OAuth2/OIDC"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    type = models.IntegerField(choices=PROVIDER_TYPE_CHOICES, default=0)
    redirect_url = models.URLField(blank=True)
    auto_provision_users = models.BooleanField(default=False)
    disabled = models.BooleanField(default=False, help_text="Prevents new logins from this provider")
    client_id = models.CharField(max_length=500)
    client_secret = models.CharField(max_length=500)
    authorization_url = models.URLField()
    token_url = models.URLField()
    identity_path = models.CharField(max_length=200, help_text="JSON path to user identity in provider response")
    email_path = models.CharField(max_length=200, help_text="JSON path to email in provider response")
    name_path = models.CharField(max_length=200, blank=True, help_text="JSON path to name in provider response")
    scopes = models.CharField(max_length=500, help_text="Space-separated OAuth scopes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(models.Model):
    """Stores user account information and authentication details."""

    ROLE_CHOICES = [
        (0, "Administrator"),
        (1, "User"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200, blank=True)
    identity_provider = models.ForeignKey(
        IdentityProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name="users"
    )
    role = models.IntegerField(choices=ROLE_CHOICES, default=1)
    disabled = models.BooleanField(default=False)
    password = models.CharField(max_length=255, blank=True, help_text="Only used for internal users")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    def is_admin(self) -> bool:
        """Check if user is an administrator."""
        return self.role == 0

    def is_internal_user(self) -> bool:
        """Check if user is an internal (non-identity provider) user."""
        return self.identity_provider is None


class AccountUpload(models.Model):
    """Stores metadata about uploaded account position CSV files."""

    UPLOAD_TYPE_CHOICES = [
        ('fidelity', 'Fidelity'),
        ('etrade', 'E-Trade'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_uploads")
    upload_datetime = models.DateTimeField(auto_now_add=True)
    file_datetime = models.CharField(max_length=200, help_text="Raw date/time string from CSV file")
    upload_type = models.CharField(max_length=50, choices=UPLOAD_TYPE_CHOICES)
    filename = models.CharField(max_length=255)
    entry_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-upload_datetime"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.filename} ({self.upload_datetime})"


class AccountPosition(models.Model):
    """Stores individual position records from account CSV uploads."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(AccountUpload, on_delete=models.CASCADE, related_name="positions")
    account_number = models.CharField(max_length=50)
    account_name = models.CharField(max_length=200)
    symbol = models.CharField(max_length=50)  # Normalized symbol
    description = models.CharField(max_length=500)
    quantity = models.CharField(max_length=50, blank=True)
    last_price = models.CharField(max_length=50, blank=True)
    last_price_change = models.CharField(max_length=50, blank=True)
    current_value = models.CharField(max_length=50, blank=True)
    todays_gain_loss_dollar = models.CharField(max_length=50, blank=True)
    todays_gain_loss_percent = models.CharField(max_length=50, blank=True)
    total_gain_loss_dollar = models.CharField(max_length=50, blank=True)
    total_gain_loss_percent = models.CharField(max_length=50, blank=True)
    percent_of_account = models.CharField(max_length=50, blank=True)
    cost_basis_total = models.CharField(max_length=50, blank=True)
    average_cost_basis = models.CharField(max_length=50, blank=True)
    type = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["upload", "account_number", "symbol"]

    def __str__(self) -> str:
        return f"{self.symbol} - {self.account_number}"


class Portfolio(models.Model):
    """Stores portfolio configurations for grouping account positions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=200)
    ruleset = models.ForeignKey(
        RuleSet, on_delete=models.SET_NULL, null=True, blank=True, related_name="portfolios"
    )
    year_born = models.IntegerField(null=True, blank=True, help_text="Birth year for target allocation calculation")
    retirement_age = models.IntegerField(null=True, blank=True, help_text="Target retirement age for allocation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.name}"

    def get_balance_info(self):
        """
        Returns portfolio balance and metadata.
        Reuses existing get_portfolio_analysis() logic.

        Returns:
            dict with keys: total_balance, allocation, upload_date, days_since_upload, unmapped_positions
        """
        from .account_services import get_portfolio_analysis
        from django.utils import timezone

        analysis = get_portfolio_analysis(self)

        # Find most recent upload date across all accounts in this portfolio
        latest_upload = AccountUpload.objects.filter(
            user=self.user,
            positions__portfolioitem__portfolio=self
        ).order_by('-upload_datetime').first()

        upload_date = latest_upload.upload_datetime if latest_upload else None
        days_since_upload = (timezone.now() - upload_date).days if upload_date else None

        return {
            'total_balance': analysis.get('total_value', 0),
            'allocation': analysis.get('allocation', {}),
            'upload_date': upload_date,
            'days_since_upload': days_since_upload,
            'unmapped_positions': analysis.get('unmapped_positions', [])
        }

    def get_current_age(self):
        """
        Calculate current age from year_born.

        Returns:
            int: current age, or None if year_born not set
        """
        if not self.year_born:
            return None
        from datetime import datetime
        return datetime.now().year - self.year_born

    def get_years_to_retirement(self):
        """
        Calculate years until retirement.

        Returns:
            int: years to retirement, or None if age data not available
        """
        current_age = self.get_current_age()
        if current_age is None or self.retirement_age is None:
            return None
        return self.retirement_age - current_age


class PortfolioItem(models.Model):
    """Stores which account+symbol combinations are included in a portfolio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="items")
    account_number = models.CharField(max_length=50)
    symbol = models.CharField(max_length=50)

    class Meta:
        unique_together = ("portfolio", "account_number", "symbol")
        ordering = ["account_number", "symbol"]

    def __str__(self) -> str:
        return f"{self.portfolio.name} - {self.account_number} - {self.symbol}"


class AssumptionUpload(models.Model):
    """Stores metadata about uploaded market assumption XLSX files."""

    UPLOAD_TYPE_CHOICES = [
        ('blackrock', 'BlackRock Market Assumptions XLSX'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assumption_uploads")
    upload_datetime = models.DateTimeField(auto_now_add=True)
    file_datetime = models.CharField(max_length=200, unique=True, help_text="Date/time string from file (e.g., 'November 2025, data as of 30 September 2025')")
    upload_type = models.CharField(max_length=50, choices=UPLOAD_TYPE_CHOICES)
    filename = models.CharField(max_length=255)
    entry_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-upload_datetime"]

    def __str__(self) -> str:
        username = self.user.username if self.user else "Unknown"
        return f"{username} - {self.filename} ({self.upload_datetime})"


class AssumptionData(models.Model):
    """Stores individual market assumption data records from uploaded XLSX files."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(AssumptionUpload, on_delete=models.CASCADE, related_name="data_rows")

    # Basic identification fields
    currency = models.CharField(max_length=10)
    asset_class = models.CharField(max_length=100)
    asset = models.CharField(max_length=200)
    index = models.CharField(max_length=200)

    # Expected returns (7 time horizons)
    expected_return_5yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_7yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_10yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_15yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_20yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_25yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    expected_return_30yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Lower interquartile range (25th percentile)
    lower_iqr_5yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_7yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_10yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_15yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_20yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_25yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_iqr_30yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Upper interquartile range (75th percentile)
    upper_iqr_5yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_7yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_10yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_15yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_20yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_25yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_iqr_30yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Lower mean uncertainty
    lower_uncertainty_5yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_7yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_10yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_15yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_20yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_25yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    lower_uncertainty_30yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Upper mean uncertainty
    upper_uncertainty_5yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_7yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_10yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_15yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_20yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_25yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    upper_uncertainty_30yr = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Volatility and correlations
    volatility = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    correlation_govt_bonds = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    correlation_equities = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["upload", "asset_class", "asset"]

    def __str__(self) -> str:
        return f"{self.asset} ({self.currency})"
