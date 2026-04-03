from django import forms
from .models import CompanyInformation, SystemParameter

class CompanyInformationForm(forms.ModelForm):
    class Meta:
        model = CompanyInformation
        fields = [
            'raison_sociale', 'forme_juridique', 'nif', 'nis', 'rc', 'ai',
            'address', 'wilaya', 'phone', 'email',
            'bank_name', 'bank_account', 'rib', 'logo',
            'vat_rate', 'fiscal_regime'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'vat_rate': forms.NumberInput(attrs={'step': '0.0001', 'min': '0', 'max': '1'}),
            'logo': forms.FileInput(attrs={'accept': 'image/*'}),
        }

class SystemParameterForm(forms.ModelForm):
    class Meta:
        model = SystemParameter
        fields = ['category', 'key', 'value', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'value': forms.Textarea(attrs={'rows': 2}),
        }