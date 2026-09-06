# production/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from core.forms import SiteLockedFormMixin
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
            "target_batch_mass_kg",
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
            "target_batch_mass_kg": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001"}
            ),
            "technical_notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "target_batch_mass_kg": (
                "Planifié (§22) — masse cible en kg, requise seulement si une ligne "
                "de la formulation est marquée comme complément."
            ),
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

        # Production is standardized in kg (§22): default a brand-new
        # formulation's batch unit to KG. Auto-detection based on the
        # chosen finished product then takes over client-side (see
        # applyFpUnit() in formulation_form.html); this is just the
        # sensible starting point before a product is picked.
        if not self.instance.pk and not self.is_bound:
            kg_unit = UnitOfMeasure.objects.filter(code="KG", is_active=True).first()
            if kg_unit:
                self.fields["reference_batch_unit"].initial = kg_unit.pk

        # BUGFIX: none of this form's fields ever carried the app's
        # form-control-app class (only individual line rows and some other
        # forms in this file do it), so every field here — Désignation,
        # Produit fini, Qté, Unité, Rendement, Masse cible, Notes — was
        # rendering as a completely unstyled native browser control: no
        # border-radius, no focus glow, no consistent height, nothing
        # tying it visually to the rest of the app ("looks like a plain
        # piece of paper"). Apply the same class every other styled form
        # in this app already relies on.
        for field in self.fields.values():
            attrs = field.widget.attrs
            if "class" not in attrs:
                attrs["class"] = "form-control-app"

        # BR-PROD-03: block editing if any in_progress PO exists
        if self.instance.pk and self.instance.has_active_production_orders():
            for field in self.fields.values():
                field.disabled = True
            self.br_prod_03_locked = True
        else:
            self.br_prod_03_locked = False

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
        fields = [
            "raw_material",
            "qty_per_batch",
            "unit_of_measure",
            "tolerance_pct",
            "is_complement",
        ]
        widgets = {
            "qty_per_batch": forms.NumberInput(attrs={"step": "0.001", "min": "0.001"}),
            "tolerance_pct": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "100"}
            ),
        }
        help_texts = {
            "is_complement": (
                "Planifié (§22) — quantité calculée automatiquement pour atteindre "
                "la masse cible du lot."
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
        # SPEC S22.4: a complement line's qty_per_batch is computed by
        # Formulation.recompute_complement_quantity(), not entered by hand.
        # Placeholder value accepted here; the view/admin overwrites it.
        # BUGFIX: this must also cover a *new, unsaved* row being submitted
        # with "Complément" freshly checked (self.instance.pk is still None
        # at this point) — previously only an already-saved complement line
        # got the relaxed requirement, so ticking the checkbox on a brand
        # new row and leaving Qté/lot blank (the normal, expected way to
        # use this field) always failed validation with a silent
        # "Ce champ est obligatoire." error that the template never
        # rendered, making Enregistrer appear to do nothing.
        is_complement_now = bool(self.instance.pk and self.instance.is_complement)
        if not is_complement_now and self.is_bound:
            is_complement_now = bool(self.data.get(self.add_prefix("is_complement")))
        if is_complement_now:
            self.fields["qty_per_batch"].required = False
            self.fields["qty_per_batch"].help_text = (
                "Calculé automatiquement (ligne complément, §22.4)."
            )

        # BUGFIX: same missing-class issue as FormulationForm above — raw_material
        # and unit_of_measure rendered as bare <select> with no styling at all.
        # Checkboxes are deliberately skipped: form-control-app is a padded,
        # bordered "text field" style that looks broken wrapped around a
        # native checkbox square.
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                continue
            attrs = field.widget.attrs
            if "class" not in attrs:
                attrs["class"] = "form-control-app"

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_complement") and not cleaned_data.get("qty_per_batch"):
            # Allow blank on a new complement line — a placeholder minimum is
            # used until recompute_complement_quantity() runs after save.
            cleaned_data["qty_per_batch"] = Decimal("0.001")
        return cleaned_data


class BaseFormulationLineFormSet(forms.BaseInlineFormSet):
    """
    SPEC S22.4: at most one line per formulation may be marked "Complément".

    This used to be enforced in FormulationLine.clean() via a query against
    already-saved sibling lines (`formulation.lines.filter(is_complement=True)`).
    That check raced against this exact formset: reassigning the complement
    flag from one row to another in a single submit (uncheck row A, check
    row B) always failed, because row B's clean() ran against the database
    *before* row A's uncheck had been saved, so A still counted as an
    existing complement line and B was rejected as a duplicate.
    Enforcing the rule here instead lets us look at every sibling row's
    about-to-be-saved value in the same pass, so a same-submission
    reassignment is evaluated correctly.
    """

    def clean(self):
        super().clean()
        # Don't pile on if individual rows already failed validation —
        # cleaned_data is unreliable/absent for forms with errors.
        if any(self.errors):
            return
        complement_forms = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            if form.cleaned_data.get("is_complement"):
                complement_forms.append(form)
        if len(complement_forms) > 1:
            error = forms.ValidationError(
                "Une seule ligne de formulation peut être marquée comme "
                "complément (§22.4) : décochez les autres avant d'enregistrer.",
                code="multiple_complements",
            )
            for form in complement_forms:
                form.add_error("is_complement", error)
            raise error


FormulationLineFormSet = inlineformset_factory(
    Formulation,
    FormulationLine,
    form=FormulationLineForm,
    formset=BaseFormulationLineFormSet,
    extra=1,
    can_delete=True,
)


class ProductionOrderForm(SiteLockedFormMixin, forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = [
            "site",
            "formulation",
            "target_qty",
            "target_unit",
            "launch_date",
            "notes",
        ]
        widgets = {
            "target_qty": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001", "class": "form-control-app"}
            ),
            "launch_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control-app"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control-app"}),
        }

    def __init__(self, *args, **kwargs):
        # functional spec §25.2.5 + avicole-style role-locking (§3.5.4):
        #   - `initial_site=<ProductionSite>` just pre-fills the field
        #     (editable) — used for manager/unbound accountant/viewer.
        #   - `site=<ProductionSite>` locks AND hides the field — used for
        #     stock_prod/sales (or a site-bound accountant/viewer), who
        #     must never be able to submit a different site than their own.
        initial_site = kwargs.pop("initial_site", None)
        locked_site = kwargs.pop("site", None)
        self._locked_site = locked_site
        super().__init__(*args, **kwargs)
        from catalog.models import UnitOfMeasure
        from core.models import ProductionSite

        self.fields["site"].queryset = ProductionSite.objects.filter(is_active=True)
        if locked_site is not None:
            self.fields["site"].initial = locked_site.pk
            self.fields["site"].widget = forms.HiddenInput()
        elif initial_site is not None and not self.is_bound:
            self.fields["site"].initial = initial_site.pk

        # Only active formulations; BR-PROD-03 locks apply to editing the formulation,
        # NOT to creating POs against it — multiple POs per formulation are permitted.
        self.fields["formulation"].queryset = Formulation.objects.filter(is_active=True)
        self.fields["target_unit"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )
        for field in self.fields.values():
            widget = field.widget
            attrs = widget.attrs if hasattr(widget, "attrs") else {}
            if "class" not in attrs:
                attrs["class"] = "form-control-app"
            widget.attrs = attrs

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
        widget=forms.NumberInput(
            attrs={"step": "0.001", "min": "0.001", "class": "form-control-app"}
        ),
        label="Quantité réellement produite",
    )

    class Meta:
        model = ProductionOrder
        fields = ["actual_qty_produced", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control-app"}),
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
                    widget=forms.NumberInput(
                        attrs={"step": "0.001", "min": "0", "class": "form-control-app"}
                    ),
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
