from django import forms
from .models import RawMaterial, FinishedProduct, RawMaterialCategory, UnitOfMeasure

class RawMaterialForm(forms.ModelForm):
    class Meta:
        model = RawMaterial
        fields = [
            'reference', 'designation', 'category', 'unit_of_measure',
            'default_supplier', 'reference_price', 'alert_threshold', 
            'stockout_threshold', 'is_active'
        ]
        widgets = {
            'reference': forms.TextInput(attrs={'readonly': True}),
            'designation': forms.TextInput(attrs={'size': 60}),
            'reference_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'alert_threshold': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'stockout_threshold': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Auto-generate reference for new materials
        if not self.instance.pk:
            # This should be generated based on business rules
            next_num = RawMaterial.objects.count() + 1
            self.fields['reference'].initial = f"RM-{next_num:04d}"
            self.fields['reference'].widget.attrs.pop('readonly', None)
        
        # Filter active categories and units
        self.fields['category'].queryset = RawMaterialCategory.objects.filter(is_active=True)
        self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        alert_threshold = cleaned_data.get('alert_threshold')
        stockout_threshold = cleaned_data.get('stockout_threshold')
        
        if alert_threshold and stockout_threshold:
            if alert_threshold <= stockout_threshold:
                raise forms.ValidationError(
                    "Le seuil d'alerte doit être supérieur au seuil de rupture"
                )
        
        return cleaned_data

class FinishedProductForm(forms.ModelForm):
    class Meta:
        model = FinishedProduct
        fields = [
            'reference', 'designation', 'sales_unit', 'reference_selling_price',
            'alert_threshold', 'source_formulation', 'is_active'
        ]
        widgets = {
            'reference': forms.TextInput(attrs={'readonly': True}),
            'designation': forms.TextInput(attrs={'size': 60}),
            'reference_selling_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'alert_threshold': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Auto-generate reference for new products
        if not self.instance.pk:
            next_num = FinishedProduct.objects.count() + 1
            self.fields['reference'].initial = f"PF-{next_num:03d}"
            self.fields['reference'].widget.attrs.pop('readonly', None)
        
        # Filter active units
        self.fields['sales_unit'].queryset = UnitOfMeasure.objects.filter(is_active=True)

class RawMaterialCategoryForm(forms.ModelForm):
    class Meta:
        model = RawMaterialCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }