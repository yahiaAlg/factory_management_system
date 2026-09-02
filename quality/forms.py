# quality/forms.py
from django import forms
from django.forms import inlineformset_factory

from .models import (
    NonConformityReport,
    Property,
    QualitySpecification,
    QualitySpecLine,
    Sample,
    SamplingPlan,
)  # noqa: F401


def _app_style(form):
    """Apply the app's standard form-control-app class to every field that
    doesn't already carry one, skipping checkboxes (native, unstyled by
    design) — matches the pattern used across production/forms.py so a
    new form in this app never ships as bare, unstyled HTML controls."""
    for field in form.fields.values():
        if isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
            continue
        attrs = field.widget.attrs
        if "class" not in attrs:
            attrs["class"] = "form-control-app"


class SampleDrawForm(forms.ModelForm):
    class Meta:
        model = Sample
        fields = ["quality_specification", "quantity_sampled", "unit", "checkpoint_label"]
        widgets = {
            "quantity_sampled": forms.NumberInput(attrs={"step": "0.001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _app_style(self)


class TestResultForm(forms.Form):
    """One dynamic row per QualitySpecLine applicable to the sample's gate."""

    def __init__(self, *args, spec_lines=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.spec_lines = list(spec_lines or [])
        for line in self.spec_lines:
            self.fields[f"value_{line.id}"] = forms.CharField(
                label=str(line.property.name),
                required=False,
                widget=forms.TextInput(attrs={"class": "form-control-app"}),
            )
            self.fields[f"instrument_{line.id}"] = forms.CharField(
                label="Instrument/méthode", required=False,
                widget=forms.TextInput(attrs={"class": "form-control-app"}),
            )


class NCRDispositionForm(forms.Form):
    ROOT_CAUSE_CHOICES = [("", "—")] + list(NonConformityReport.ROOT_CAUSE_CHOICES)
    DISPOSITION_CHOICES = [("", "—")] + list(NonConformityReport.DISPOSITION_CHOICES)

    root_cause_category = forms.ChoiceField(
        choices=ROOT_CAUSE_CHOICES, required=False,
        widget=forms.Select(attrs={"class": "form-control-app"}),
    )
    root_cause_detail = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": "form-control-app", "rows": 2}),
    )
    corrective_action = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control-app", "rows": 3}),
    )
    disposition = forms.ChoiceField(
        choices=DISPOSITION_CHOICES,
        widget=forms.Select(attrs={"class": "form-control-app"}),
    )
    proof_document = forms.FileField(required=False)


# ---------------------------------------------------------------------------
# Configuration CRUD — Property / Test Catalogue, Quality Specifications,
# Sampling Plans. These models existed and are exactly what powers every
# gate (BR-QA-01: no active plan for a target+control point => that gate
# never appears anywhere in the app) but previously had no in-app form to
# create or edit them — only Django admin could touch them, which is why
# the whole QA/QC module could look unreachable/empty until an admin had
# separately configured it outside the app.
# ---------------------------------------------------------------------------
class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            "name", "applies_to", "unit_label", "test_method_reference",
            "result_data_type", "default_precision", "is_active",
        ]
        widgets = {
            "test_method_reference": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _app_style(self)


class QualitySpecificationForm(forms.ModelForm):
    class Meta:
        model = QualitySpecification
        fields = ["raw_material", "finished_product", "version", "effective_date", "is_active"]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "raw_material": "Renseignez soit une matière première, soit un produit fini — jamais les deux.",
            "version": "Incrémentez pour créer une nouvelle version (l'ancienne reste consultable).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import FinishedProduct, RawMaterial

        self.fields["raw_material"].queryset = RawMaterial.objects.filter(is_active=True)
        self.fields["raw_material"].required = False
        self.fields["finished_product"].queryset = FinishedProduct.objects.filter(is_active=True)
        self.fields["finished_product"].required = False
        _app_style(self)

    def clean(self):
        cleaned_data = super().clean()
        rm = cleaned_data.get("raw_material")
        fp = cleaned_data.get("finished_product")
        if bool(rm) == bool(fp):
            raise forms.ValidationError(
                "Choisissez soit une matière première, soit un produit fini (pas les deux, pas aucun)."
            )
        return cleaned_data


class QualitySpecLineForm(forms.ModelForm):
    class Meta:
        model = QualitySpecLine
        fields = [
            "property", "gate_a", "gate_b", "gate_c", "nominal_value",
            "tolerance_pct", "hard_min", "hard_max", "is_critical",
            "expected_boolean", "accepted_categories",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = Property.objects.filter(is_active=True)
        self.fields["property"].required = False
        _app_style(self)


QualitySpecLineFormSet = inlineformset_factory(
    QualitySpecification,
    QualitySpecLine,
    form=QualitySpecLineForm,
    extra=1,
    can_delete=True,
)


class SamplingPlanForm(forms.ModelForm):
    class Meta:
        model = SamplingPlan
        fields = [
            "raw_material", "finished_product", "control_point",
            "trigger_description", "checkpoint_labels", "sample_size_rule",
            "frequency", "frequency_n", "is_active", "deactivated_reason",
        ]
        help_texts = {
            "raw_material": (
                "Laissez matière première ET produit fini vides pour un plan "
                "s'appliquant à toutes les cibles de ce point de contrôle."
            ),
            "control_point": "BR-QA-01 : sans plan actif pour une cible + un point de contrôle, ce contrôle n'est pas exigé.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalog.models import FinishedProduct, RawMaterial

        self.fields["raw_material"].queryset = RawMaterial.objects.filter(is_active=True)
        self.fields["raw_material"].required = False
        self.fields["finished_product"].queryset = FinishedProduct.objects.filter(is_active=True)
        self.fields["finished_product"].required = False
        self.fields["frequency_n"].required = False
        _app_style(self)

    def clean(self):
        cleaned_data = super().clean()
        rm = cleaned_data.get("raw_material")
        fp = cleaned_data.get("finished_product")
        control_point = cleaned_data.get("control_point")
        if rm and fp:
            raise forms.ValidationError(
                "Un plan cible une matière première OU un produit fini, pas les deux."
            )
        if control_point == "A" and fp:
            raise forms.ValidationError("Gate A ne s'applique qu'aux matières premières.")
        if control_point in ("B", "C") and rm:
            raise forms.ValidationError("Gate B / Gate C ne s'appliquent qu'aux produits finis.")
        return cleaned_data
