from django import forms
from .models import APISettings, Fund, AssetCategory


class GlidepathRuleUploadForm(forms.Form):
    file = forms.FileField(label="Glidepath CSV")


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
