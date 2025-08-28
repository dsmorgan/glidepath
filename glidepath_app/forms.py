from django import forms


class GlidepathRuleUploadForm(forms.Form):
    file = forms.FileField(label="Glidepath CSV")
