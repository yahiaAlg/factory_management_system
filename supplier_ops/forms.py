# supplier_ops/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import (
    SupplierDN,
    SupplierDNLine,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierPayment,
)


class SupplierDNForm(forms.ModelForm):
    class Meta:
        model = SupplierDN
        fields = ["site", "external_reference", "supplier", "delivery_date", "remarks"]
        widgets = {
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        # functional spec §25.2.5: defaults to whichever site the user
        # most recently worked in — resolved by the view via
        # core.utils.get_default_site and passed in here as `initial_site`.
        initial_site = kwargs.pop("initial_site", None)
        super().__init__(*args, **kwargs)
        from suppliers.models import Supplier
        from core.models import ProductionSite

        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["site"].queryset = ProductionSite.objects.filter(is_active=True)
        if initial_site is not None and not self.is_bound:
            self.fields["site"].initial = initial_site.pk


class SupplierDNLineForm(forms.ModelForm):
    class Meta:
        model = SupplierDNLine
        fields = [
            "raw_material",
            "quantity_received",
            "unit_of_measure",
            "agreed_unit_price",
        ]
        widgets = {
            "quantity_received": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001"}
            ),
            "agreed_unit_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active raw materials
        from catalog.models import RawMaterial, UnitOfMeasure

        self.fields["raw_material"].queryset = RawMaterial.objects.filter(
            is_active=True
        )
        self.fields["unit_of_measure"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )


SupplierDNLineFormSet = inlineformset_factory(
    SupplierDN, SupplierDNLine, form=SupplierDNLineForm, extra=1, can_delete=True
)


class SupplierInvoiceForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoice
        fields = [
            "external_reference",
            "supplier",
            "invoice_date",
            "due_date",
            "payment_method",
        ]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "payment_method": forms.Select(attrs={"class": "form-control-app"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active suppliers
        from suppliers.models import Supplier

        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        invoice_date = cleaned_data.get("invoice_date")
        due_date = cleaned_data.get("due_date")

        if invoice_date and due_date and due_date < invoice_date:
            raise forms.ValidationError(
                "La date d'échéance ne peut pas être antérieure à la date de facture"
            )

        return cleaned_data


class SupplierInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoiceLine
        fields = [
            "raw_material",
            "designation",
            "quantity_invoiced",
            "unit_price_invoiced",
        ]
        widgets = {
            "designation": forms.TextInput(attrs={"size": 40}),
            "quantity_invoiced": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001"}
            ),
            "unit_price_invoiced": forms.NumberInput(
                attrs={"step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active raw materials
        from catalog.models import RawMaterial

        self.fields["raw_material"].queryset = RawMaterial.objects.filter(
            is_active=True
        )


SupplierInvoiceLineFormSet = inlineformset_factory(
    SupplierInvoice,
    SupplierInvoiceLine,
    form=SupplierInvoiceLineForm,
    extra=1,
    can_delete=True,
)


class SupplierPaymentForm(forms.ModelForm):
    class Meta:
        model = SupplierPayment
        fields = ["payment_date", "amount", "payment_method", "bank_reference"]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control-app",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0.01",
                    "class": "form-control-app",
                }
            ),
            "payment_method": forms.Select(
                attrs={
                    "class": "form-control-app",
                }
            ),
            "bank_reference": forms.TextInput(
                attrs={
                    "placeholder": "Référence bancaire ou numéro de chèque",
                    "class": "form-control-app",
                }
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount


class SupplierSupportingDocForm(forms.Form):
    """Inline form for attaching a SupportingDocument to a SupplierDN or SupplierInvoice."""

    DN_DOC_TYPES = [
        ("SD-DNF", "BL Fournisseur signé"),
        ("SD-CORR", "Document de correction"),
    ]

    INVOICE_DOC_TYPES = [
        ("SD-INV-F", "Facture fournisseur originale"),
        ("SD-PAY-F", "Justificatif paiement fournisseur"),
        ("SD-CORR", "Document de correction"),
    ]

    PAYMENT_DOC_TYPES = [
        ("SD-PAY-F", "Justificatif paiement fournisseur"),
        ("SD-CORR", "Document de correction"),
    ]

    doc_type = forms.ChoiceField(
        label="Type de document",
        widget=forms.Select(attrs={"class": "form-control-app"}),
    )
    description = forms.CharField(
        label="Description",
        max_length=300,
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

    def __init__(self, *args, entity_type="dn", **kwargs):
        super().__init__(*args, **kwargs)
        if entity_type == "invoice":
            self.fields["doc_type"].choices = self.INVOICE_DOC_TYPES
        elif entity_type == "payment":
            self.fields["doc_type"].choices = self.PAYMENT_DOC_TYPES
        else:
            self.fields["doc_type"].choices = self.DN_DOC_TYPES


from .models import SupplierAccountPayment as _SupplierAccountPayment


class SupplierAccountPaymentForm(forms.ModelForm):
    class Meta:
        model = _SupplierAccountPayment
        fields = ["payment_date", "amount", "payment_method", "bank_reference", "notes"]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control-app"}
            ),
            "amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "class": "form-control-app"}
            ),
            "payment_method": forms.Select(attrs={"class": "form-control-app"}),
            "bank_reference": forms.TextInput(
                attrs={
                    "placeholder": "Référence bancaire, numéro de chèque, etc.",
                    "class": "form-control-app",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control-app"}),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return amount


# ---------------------------------------------------------------------------
# §23 (planned) — Supplier Advance (direct entry) & Opening Balance forms
# ---------------------------------------------------------------------------

from .models import SupplierAdvance as _SupplierAdvance


class SupplierAdvanceForm(forms.ModelForm):
    """§23.3.2b — direct-entry Supplier Advance (e.g. a cheque handed over
    as a deposit against an upcoming order), independent of any settlement."""

    class Meta:
        model = _SupplierAdvance
        fields = ["date", "amount", "payment_method", "notes"]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "form-control-app"}
            ),
            "amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "class": "form-control-app"}
            ),
            "payment_method": forms.Select(attrs={"class": "form-control-app"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control-app"}),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif.")
        return amount


class SupplierOpeningBalanceForm(forms.Form):
    """§23.5 — admin-only opening balance entry: amount + required
    explanation (motif), plus optional reference/due dates."""

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Montant (DA)",
        widget=forms.NumberInput(
            attrs={"step": "0.01", "min": "0.01", "class": "form-control-app"}
        ),
    )
    motif = forms.CharField(
        label="Motif (explication requise)",
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control-app"}),
    )
    reference_date = forms.DateField(
        label="Date de référence",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control-app"}),
    )
    due_date = forms.DateField(
        label="Date d'échéance",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control-app"}),
    )
