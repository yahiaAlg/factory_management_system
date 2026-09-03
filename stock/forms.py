# stock/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from core.forms import SiteLockedFormMixin
from .models import StockAdjustment, StockAdjustmentLine

class StockAdjustmentForm(SiteLockedFormMixin, forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['site', 'adjustment_type', 'adjustment_date', 'reason']
        widgets = {
            'adjustment_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        # functional spec §25.2.5 + avicole-style role-locking (§3.5.4):
        #   - `initial_site=<ProductionSite>` just pre-fills (editable).
        #   - `site=<ProductionSite>` locks AND hides the field — used for
        #     stock_prod (or a site-bound accountant/viewer).
        initial_site = kwargs.pop('initial_site', None)
        locked_site = kwargs.pop('site', None)
        self._locked_site = locked_site
        super().__init__(*args, **kwargs)
        from core.models import ProductionSite
        self.fields['site'].queryset = ProductionSite.objects.filter(is_active=True)
        if locked_site is not None:
            self.fields['site'].initial = locked_site.pk
            self.fields['site'].widget = forms.HiddenInput()
        elif initial_site is not None and not self.is_bound:
            self.fields['site'].initial = initial_site.pk

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
        # The parent StockAdjustment's site (functional spec §25.2.3) — used
        # to auto-fill quantity_before from the correct site's balance.
        # Passed in via the formset's form_kwargs by the create/edit views.
        self.site = kwargs.pop('site', None)
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

        # Auto-fill current stock as quantity_before — scoped to the parent
        # adjustment's site (§25.2.3); falls back to 0 if the site is not
        # yet known (e.g. formset validated before the main form).
        if raw_material:
            try:
                from .models import RawMaterialStockBalance
                balance = RawMaterialStockBalance.objects.get(
                    site=self.site, raw_material=raw_material
                )
                cleaned_data['quantity_before'] = balance.quantity
            except RawMaterialStockBalance.DoesNotExist:
                cleaned_data['quantity_before'] = Decimal('0.000')

        elif finished_product:
            try:
                from .models import FinishedProductStockBalance
                balance = FinishedProductStockBalance.objects.get(
                    site=self.site, finished_product=finished_product
                )
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


# ---------------------------------------------------------------------------
# StockAdjustmentSupportingDocForm — PieceJointe upload form for
# StockAdjustment (mirrors sales.ClientSupportingDocForm /
# supplier_ops.SupplierSupportingDocForm). Kept as a separate standalone
# form used only by the dedicated "add document" view — it is NOT part of
# StockAdjustmentForm/StockAdjustmentLineFormSet, so attaching a document
# stays optional and never affects create/edit/approve validation.
# ---------------------------------------------------------------------------
class StockAdjustmentSupportingDocForm(forms.Form):
    """Inline form for attaching a PieceJointe to a StockAdjustment."""

    DOC_TYPES = [
        ("SD-CORR", "Document de correction"),
        ("AUTRE", "Autre"),
    ]

    doc_type = forms.ChoiceField(
        label="Type de document",
        choices=DOC_TYPES,
        widget=forms.Select(attrs={"class": "form-control-app"}),
    )
    description = forms.CharField(
        label="Description",
        max_length=300,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control-app",
                "placeholder": "Brève description du document",
            }
        ),
    )
    file = forms.FileField(
        label="Fichier joint",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control-app"}),
        help_text="Formats acceptés : PDF, JPG, PNG",
    )