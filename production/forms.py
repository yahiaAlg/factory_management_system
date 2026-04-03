# production/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import Formulation, FormulationLine, ProductionOrder


class FormulationForm(forms.ModelForm):
    class Meta:
        model = Formulation
        fields = [
            "designation",
            "finished_product",
            "reference_batch_qty",
            "reference_batch_unit",
            "expected_yield_pct",
            "technical_notes",
        ]
        widgets = {
            "designation": forms.TextInput(attrs={"size": 60}),
            "reference_batch_qty": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001"}
            ),
            "expected_yield_pct": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "max": "200"}
            ),
            "technical_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import FinishedProduct, UnitOfMeasure

        self.fields["finished_product"].queryset = FinishedProduct.objects.filter(
            is_active=True
        )
        self.fields["reference_batch_unit"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )

        # BR-PROD-03: block editing if any in_progress PO exists
        if self.instance.pk and self.instance.has_active_production_orders():
            for field in self.fields.values():
                field.disabled = True
            self._br_prod_03_locked = True
        else:
            self._br_prod_03_locked = False

    def clean(self):
        cleaned_data = super().clean()
        # BR-PROD-03: final guard in case disabled fields were bypassed
        if self.instance.pk and self.instance.has_active_production_orders():
            raise forms.ValidationError(
                "Impossible de modifier cette formulation : des ordres de production sont en cours (BR-PROD-03)."
            )
        return cleaned_data


class FormulationLineForm(forms.ModelForm):
    class Meta:
        model = FormulationLine
        fields = ["raw_material", "qty_per_batch", "unit_of_measure", "tolerance_pct"]
        widgets = {
            "qty_per_batch": forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
            "tolerance_pct": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "100"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import RawMaterial, UnitOfMeasure

        self.fields["raw_material"].queryset = RawMaterial.objects.filter(
            is_active=True
        )
        self.fields["unit_of_measure"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )


FormulationLineFormSet = inlineformset_factory(
    Formulation,
    FormulationLine,
    form=FormulationLineForm,
    extra=1,
    can_delete=True,
)


class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = ["formulation", "target_qty", "target_unit", "launch_date", "notes"]
        widgets = {
            "target_qty": forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
            "launch_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import UnitOfMeasure

        # Only active formulations; BR-PROD-03 locks apply to editing the formulation,
        # NOT to creating POs against it — multiple POs per formulation are permitted.
        self.fields["formulation"].queryset = Formulation.objects.filter(is_active=True)
        self.fields["target_unit"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )

    def clean(self):
        cleaned_data = super().clean()
        target_qty = cleaned_data.get("target_qty")

        # target_qty min enforced by model validator; mirror here for UX
        if target_qty is not None and target_qty <= 0:
            self.add_error("target_qty", "La quantité cible doit être positive.")

        return cleaned_data


class ProductionOrderCloseForm(forms.ModelForm):
    """
    Form for closing (completing) a ProductionOrder.

    Dynamic fields for each consumption line are added in __init__.
    The view is responsible for extracting consumption_<id> values and
    passing them to ProductionOrder.close(consumption_data=...).
    """

    actual_qty_produced = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
        label="Quantité réellement produite",
    )

    class Meta:
        model = ProductionOrder
        fields = ["actual_qty_produced", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            for line in self.instance.consumption_lines.all():
                field_name = f"consumption_{line.id}"
                self.fields[field_name] = forms.DecimalField(
                    max_digits=10,
                    decimal_places=3,
                    min_value=Decimal("0.000"),
                    initial=line.qty_theoretical,
                    widget=forms.NumberInput(attrs={"step": "0.001", "min": "0"}),
                    label=f"{line.raw_material.designation} (théo: {line.qty_theoretical})",
                    help_text=f"Unité : {line.raw_material.unit_of_measure.symbol}",
                )

    def clean_actual_qty_produced(self):
        actual_qty = self.cleaned_data["actual_qty_produced"]
        if actual_qty <= 0:
            raise forms.ValidationError("La quantité produite doit être positive.")
        return actual_qty

    def get_consumption_data(self):
        """
        Return {raw_material_id: actual_qty} dict for ProductionOrder.close().
        Call only after is_valid().
        """
        result = {}
        if self.instance and self.instance.pk:
            for line in self.instance.consumption_lines.all():
                field_name = f"consumption_{line.id}"
                qty = self.cleaned_data.get(field_name)
                if qty is not None:
                    result[line.raw_material_id] = qty
        return result
