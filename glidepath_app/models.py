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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self) -> str:
        return f"{self.ticker} - {self.name}"


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
