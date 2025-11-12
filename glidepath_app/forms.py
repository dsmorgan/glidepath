from django import forms
from .models import APISettings, Fund, AssetCategory, User, IdentityProvider, AccountUpload, Portfolio, RuleSet
from django.contrib.auth.hashers import make_password


class GlidepathRuleUploadForm(forms.Form):
    file = forms.FileField(label="Glidepath CSV")


class AccountUploadForm(forms.Form):
    """Form for uploading account position CSV files."""
    file = forms.FileField(
        label="CSV File",
        widget=forms.FileInput(attrs={
            'class': 'border border-gray-300 rounded-md p-2 text-sm',
            'accept': '.csv'
        })
    )
    upload_type = forms.ChoiceField(
        label="Type",
        choices=AccountUpload.UPLOAD_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full border border-gray-300 rounded-md p-2'
        })
    )


class APISettingsForm(forms.ModelForm):
    """Form for managing API keys and settings."""

    class Meta:
        model = APISettings
        fields = [
            'alpha_vantage_api_key',
            'finnhub_api_key',
            'polygon_api_key',
            'eodhd_api_key',
        ]
        widgets = {
            'alpha_vantage_api_key': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter Alpha Vantage API Key'
            }),
            'finnhub_api_key': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter Finnhub API Key'
            }),
            'polygon_api_key': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter Polygon.io API Key'
            }),
            'eodhd_api_key': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter EODHD API Key (or use DEMO)'
            }),
        }
        labels = {
            'alpha_vantage_api_key': 'API Key',
            'finnhub_api_key': 'API Key',
            'polygon_api_key': 'API Key',
            'eodhd_api_key': 'API Key',
        }


class FundForm(forms.ModelForm):
    """Form for adding a new fund with ticker, name, and category."""

    class Meta:
        model = Fund
        fields = ['ticker', 'name', 'category', 'preference']
        widgets = {
            'ticker': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2 bg-gray-100',
                'readonly': 'readonly',
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter fund name'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2'
            }),
            'preference': forms.NumberInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'min': '1',
                'max': '256',
            }),
        }
        labels = {
            'ticker': 'Ticker Symbol',
            'name': 'Fund Name',
            'category': 'Asset Category',
            'preference': 'Preference',
        }
        help_texts = {
            'preference': 'Display order and recommendation priority. Lower values appear first (1 is highest priority). Values 1-10 mark this as a recommended fund for the category.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add "Other" as the first option in the category choices
        self.fields['category'].empty_label = "Other (no category)"
        self.fields['category'].required = False


class UserForm(forms.ModelForm):
    """Form for managing user accounts."""
    password = forms.CharField(
        label="Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full border border-gray-300 rounded-md p-2',
            'placeholder': 'Enter password (leave blank to keep current)'
        }),
        help_text="Only used for internal users. Leave blank to keep current password."
    )
    password_visible = forms.BooleanField(
        required=False,
        label="Show password",
        widget=forms.CheckboxInput(attrs={
            'class': 'ml-2'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'name', 'identity_provider', 'role', 'disabled', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter email address'
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter full name (optional)'
            }),
            'identity_provider': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2'
            }),
            'role': forms.RadioSelect(choices=User.ROLE_CHOICES, attrs={
                'class': 'ml-2'
            }),
            'disabled': forms.CheckboxInput(attrs={
                'class': 'ml-2'
            }),
        }
        labels = {
            'username': 'Username',
            'email': 'Email',
            'name': 'Full Name',
            'identity_provider': 'Identity Provider (leave blank for internal user)',
            'role': 'Role',
            'disabled': 'Disable this account',
            'password': 'Password',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['identity_provider'].empty_label = "Internal User"
        self.fields['identity_provider'].required = False
        self.fields['name'].required = False
        # Remove the password field from the form's field list since we handle it separately
        if 'password' in self.fields:
            del self.fields['password']

    def clean(self):
        cleaned_data = super().clean()
        identity_provider = cleaned_data.get('identity_provider')
        password = self.cleaned_data.get('password')

        # For internal users, password is required on creation
        if not identity_provider and not self.instance.pk and not password:
            raise forms.ValidationError("Password is required for internal users.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.data.get('password')

        # Only update password if a new one is provided
        if password:
            user.password = make_password(password)

        if commit:
            user.save()
        return user


class IdentityProviderForm(forms.ModelForm):
    """Form for managing identity provider configurations."""

    class Meta:
        model = IdentityProvider
        fields = [
            'name', 'type', 'redirect_url', 'auto_provision_users', 'disabled',
            'client_id', 'client_secret', 'authorization_url', 'token_url',
            'identity_path', 'email_path', 'name_path', 'scopes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter provider name (e.g., Google, GitHub)'
            }),
            'type': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2'
            }, choices=IdentityProvider.PROVIDER_TYPE_CHOICES),
            'redirect_url': forms.URLInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'https://yourdomain.com/callback'
            }),
            'auto_provision_users': forms.CheckboxInput(attrs={
                'class': 'ml-2'
            }),
            'disabled': forms.CheckboxInput(attrs={
                'class': 'ml-2'
            }),
            'client_id': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter client ID'
            }),
            'client_secret': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter client secret',
                'type': 'password'
            }),
            'authorization_url': forms.URLInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'https://provider.com/oauth/authorize'
            }),
            'token_url': forms.URLInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'https://provider.com/oauth/token'
            }),
            'identity_path': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'e.g., sub or id'
            }),
            'email_path': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'e.g., email'
            }),
            'name_path': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'e.g., name (optional)'
            }),
            'scopes': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'e.g., openid profile email'
            }),
        }
        labels = {
            'name': 'Provider Name',
            'type': 'Provider Type',
            'redirect_url': 'Redirect URL',
            'auto_provision_users': 'Auto Provision Users',
            'client_id': 'Client ID',
            'client_secret': 'Client Secret',
            'authorization_url': 'Authorization URL',
            'token_url': 'Token URL',
            'identity_path': 'Identity Path (JSON path)',
            'email_path': 'Email Path (JSON path)',
            'name_path': 'Name Path (JSON path)',
            'scopes': 'Scopes',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name_path'].required = False
        self.fields['redirect_url'].required = False


class PortfolioForm(forms.ModelForm):
    """Form for creating and editing portfolios."""

    # Generate year and retirement age choices
    YEAR_BORN_CHOICES = [('', 'Select year')] + [(year, str(year)) for year in range(1940, 2021)]
    RETIREMENT_AGE_CHOICES = [('', 'Select age')] + [(age, str(age)) for age in range(40, 81)]

    year_born = forms.IntegerField(
        required=False,
        widget=forms.Select(choices=YEAR_BORN_CHOICES, attrs={
            'class': 'w-full border border-gray-300 rounded-md p-2'
        })
    )
    retirement_age = forms.IntegerField(
        required=False,
        widget=forms.Select(choices=RETIREMENT_AGE_CHOICES, attrs={
            'class': 'w-full border border-gray-300 rounded-md p-2'
        })
    )

    class Meta:
        model = Portfolio
        fields = ['name', 'ruleset', 'year_born', 'retirement_age']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2',
                'placeholder': 'Enter portfolio name'
            }),
            'ruleset': forms.Select(attrs={
                'class': 'w-full border border-gray-300 rounded-md p-2'
            }),
        }
        labels = {
            'name': 'Portfolio Name',
            'ruleset': 'Glidepath Rule',
            'year_born': 'Year Born',
            'retirement_age': 'Retirement Age',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['ruleset'].empty_label = "None (No glidepath rule)"
        self.fields['ruleset'].required = False

    def clean_name(self):
        """Ensure portfolio name is unique for the user."""
        name = self.cleaned_data.get('name')
        if not name:
            raise forms.ValidationError("Portfolio name is required.")

        # Check for duplicate names (excluding current instance if editing)
        query = Portfolio.objects.filter(user=self.user, name=name)
        if self.instance.pk:
            query = query.exclude(pk=self.instance.pk)

        if query.exists():
            raise forms.ValidationError(f"Portfolio '{name}' already exists for this user.")

        return name
