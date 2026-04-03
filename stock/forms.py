from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import StockAdjustment, StockAdjustmentLine

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['adjustment_type', 'adjustment_date', 'reason']
        widgets = {
            'adjustment_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

class StockAdjustmentLineForm(forms.ModelForm):
    class Meta:
        model = StockAdjustmentLine
        fields = [
            'raw_material', 'finished_product', 'quantity_before', 
            'quantity_after', 'remarks'
        ]
        widgets = {
            'quantity_before': forms.NumberInput(attrs={'step': '0.001', 'readonly': True}),
            'quantity_after': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'remarks': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active materials
        from catalog.models import RawMaterial, FinishedProduct
        self.fields['raw_material'].queryset = RawMaterial.objects.filter(is_active=True)
        self.fields['finished_product'].queryset = FinishedProduct.objects.filter(is_active=True)
        
        # Make material fields mutually exclusive
        self.fields['raw_material'].required = False
        self.fields['finished_product'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        raw_material = cleaned_data.get('raw_material')
        finished_product = cleaned_data.get('finished_product')
        
        # Validate that exactly one material is selected
        if not ((raw_material and not finished_product) or (finished_product and not raw_material)):
            raise forms.ValidationError(
                "Veuillez sélectionner soit une matière première, soit un produit fini"
            )
        
        # Auto-fill current stock as quantity_before
        if raw_material:
            try:
                from .models import RawMaterialStockBalance
                balance = RawMaterialStockBalance.objects.get(raw_material=raw_material)
                cleaned_data['quantity_before'] = balance.quantity
            except RawMaterialStockBalance.DoesNotExist:
                cleaned_data['quantity_before'] = Decimal('0.000')
        
        elif finished_product:
            try:
                from .models import FinishedProductStockBalance
                balance = FinishedProductStockBalance.objects.get(finished_product=finished_product)
                cleaned_data['quantity_before'] = balance.quantity
            except FinishedProductStockBalance.DoesNotExist:
                cleaned_data['quantity_before'] = Decimal('0.000')
        
        return cleaned_data

StockAdjustmentLineFormSet = inlineformset_factory(
    StockAdjustment,
    StockAdjustmentLine,
    form=StockAdjustmentLineForm,
    extra=1,
    can_delete=True
)