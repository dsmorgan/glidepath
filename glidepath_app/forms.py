from django import forms
from .models import APISettings, Fund, AssetCategory, User, IdentityProvider, AccountUpload
from django.contrib.auth.hashers import make_password


class GlidepathRuleUploadForm(forms.Form):
    file = forms.FileField(label="Glidepath CSV")


class AccountUploadForm(forms.Form):
    """Form for uploading account position CSV files."""
    file = forms.FileField(
        label="CSV File",
        widget=forms.FileInput(attrs={
            'class': 'block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none',
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
        fields = ['ticker', 'name', 'category']
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
        }
        labels = {
            'ticker': 'Ticker Symbol',
            'name': 'Fund Name',
            'category': 'Asset Category',
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
            'name', 'type', 'redirect_url', 'auto_provision_users',
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
