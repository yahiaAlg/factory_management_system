# clients/forms.py
from django import forms
from .models import Client

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'code', 'raison_sociale', 'forme_juridique',
            'nif', 'nis', 'rc', 'ai',
            'address', 'wilaya', 'phone', 'fax', 'email',
            'contact_person', 'contact_phone',
            'payment_terms', 'credit_status', 'max_discount_pct',
            'notes', 'is_active'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'payment_terms': forms.NumberInput(attrs={'min': '0'}),
            'max_discount_pct': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Auto-generate code for new clients
        if not self.instance.pk:
            next_num = Client.objects.count() + 1
            self.fields['code'].initial = f"C-{next_num:04d}"
    
    def clean_code(self):
        code = self.cleaned_data['code']
        
        # Check for duplicate codes
        existing = Client.objects.filter(code=code)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        
        if existing.exists():
            raise forms.ValidationError("Ce code client existe déjà")
        
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate that at least one fiscal identifier is provided for professional clients
        nif = cleaned_data.get('nif')
        nis = cleaned_data.get('nis')
        rc = cleaned_data.get('rc')
        ai = cleaned_data.get('ai')
        
        if not any([nif, nis, rc, ai]):
            self.add_error(None, 
                "Il est recommandé de fournir au moins un identifiant fiscal"
            )
        
        return cleaned_data