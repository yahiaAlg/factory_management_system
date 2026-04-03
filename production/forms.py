# production/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import Formulation, FormulationLine, ProductionOrder

class FormulationForm(forms.ModelForm):
    class Meta:
        model = Formulation
        fields = [
            'designation', 'finished_product', 'reference_batch_qty', 
            'reference_batch_unit', 'expected_yield_pct', 'technical_notes'
        ]
        widgets = {
            'designation': forms.TextInput(attrs={'size': 60}),
            'reference_batch_qty': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'expected_yield_pct': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'max': '200'}),
            'technical_notes': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active finished products and units
        from catalog.models import FinishedProduct, UnitOfMeasure
        self.fields['finished_product'].queryset = FinishedProduct.objects.filter(is_active=True)
        self.fields['reference_batch_unit'].queryset = UnitOfMeasure.objects.filter(is_active=True)

class FormulationLineForm(forms.ModelForm):
    class Meta:
        model = FormulationLine
        fields = ['raw_material', 'qty_per_batch', 'unit_of_measure', 'tolerance_pct']
        widgets = {
            'qty_per_batch': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'tolerance_pct': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active raw materials and units
        from catalog.models import RawMaterial, UnitOfMeasure
        self.fields['raw_material'].queryset = RawMaterial.objects.filter(is_active=True)
        self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(is_active=True)

FormulationLineFormSet = inlineformset_factory(
    Formulation,
    FormulationLine,
    form=FormulationLineForm,
    extra=1,
    can_delete=True
)

class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = ['formulation', 'target_qty', 'target_unit', 'launch_date', 'notes']
        widgets = {
            'target_qty': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'launch_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active formulations and units
        from catalog.models import UnitOfMeasure
        self.fields['formulation'].queryset = Formulation.objects.filter(is_active=True)
        self.fields['target_unit'].queryset = UnitOfMeasure.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        formulation = cleaned_data.get('formulation')
        target_qty = cleaned_data.get('target_qty')
        
        if formulation and target_qty:
            # Validate that target quantity is reasonable
            if target_qty <= 0:
                raise forms.ValidationError("La quantité cible doit être positive")
            
            # Check if formulation has active production orders
            if formulation.has_active_production_orders():
                self.add_error('formulation', 
                    "Cette formulation a des ordres de production actifs"
                )
        
        return cleaned_data

class ProductionOrderCloseForm(forms.ModelForm):
    actual_qty_produced = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal('0.001'),
        widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
        label="Quantité réellement produite"
    )
    
    class Meta:
        model = ProductionOrder
        fields = ['actual_qty_produced', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add dynamic fields for each consumption line
        if self.instance and self.instance.pk:
            for line in self.instance.consumption_lines.all():
                field_name = f'consumption_{line.id}'
                self.fields[field_name] = forms.DecimalField(
                    max_digits=10,
                    decimal_places=3,
                    min_value=Decimal('0.000'),
                    initial=line.qty_theoretical,
                    widget=forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
                    label=f"{line.raw_material.designation} (théo: {line.qty_theoretical})",
                    help_text=f"Unité: {line.raw_material.unit_of_measure.symbol}"
                )
    
    def clean_actual_qty_produced(self):
        actual_qty = self.cleaned_data['actual_qty_produced']
        if actual_qty <= 0:
            raise forms.ValidationError("La quantité produite doit être positive")
        return actual_qty