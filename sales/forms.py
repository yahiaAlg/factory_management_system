# sales/forms.py
from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from core.forms import SiteLockedFormMixin
from .models import ClientDN, ClientDNLine, ClientInvoice, ClientPayment


class ClientDNForm(SiteLockedFormMixin, forms.ModelForm):
    class Meta:
        model = ClientDN
        fields = ["site", "client", "delivery_date", "discount_pct", "remarks"]
        widgets = {
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "discount_pct": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "100"}
            ),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        # functional spec §25.2.5 + avicole-style role-locking (§3.5.4):
        #   - `initial_site=<ProductionSite>` just pre-fills (editable).
        #   - `site=<ProductionSite>` locks AND hides the field — used for
        #     sales (or a site-bound accountant/viewer).
        initial_site = kwargs.pop("initial_site", None)
        locked_site = kwargs.pop("site", None)
        self._locked_site = locked_site
        super().__init__(*args, **kwargs)
        # Filter active clients with good credit status
        from clients.models import Client
        from core.models import ProductionSite

        self.fields["client"].queryset = Client.objects.filter(
            is_active=True, credit_status__in=["active", "suspended"]
        )
        self.fields["site"].queryset = ProductionSite.objects.filter(is_active=True)
        if locked_site is not None:
            self.fields["site"].initial = locked_site.pk
            self.fields["site"].widget = forms.HiddenInput()
        elif initial_site is not None and not self.is_bound:
            self.fields["site"].initial = initial_site.pk

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        discount_pct = cleaned_data.get("discount_pct", 0)

        if client and discount_pct > client.max_discount_pct:
            raise forms.ValidationError(
                f"La remise ne peut pas dépasser {client.max_discount_pct}% pour ce client"
            )

        return cleaned_data


class ClientDNLineForm(forms.ModelForm):
    class Meta:
        model = ClientDNLine
        fields = [
            "finished_product",
            "quantity_delivered",
            "unit_of_measure",
            "selling_unit_price_ht",
        ]
        widgets = {
            "quantity_delivered": forms.NumberInput(
                attrs={"step": "0.001", "min": "0.001"}
            ),
            "selling_unit_price_ht": forms.NumberInput(
                attrs={"step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active finished products and units
        from catalog.models import FinishedProduct, UnitOfMeasure

        self.fields["finished_product"].queryset = FinishedProduct.objects.filter(
            is_active=True
        )
        self.fields["unit_of_measure"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )

        # Set default price from product reference price
        if self.instance and self.instance.finished_product_id:
            self.fields["selling_unit_price_ht"].initial = (
                self.instance.finished_product.reference_selling_price
            )


ClientDNLineFormSet = inlineformset_factory(
    ClientDN, ClientDNLine, form=ClientDNLineForm, extra=1, can_delete=True
)


class ClientInvoiceForm(forms.ModelForm):
    class Meta:
        model = ClientInvoice
        fields = ["client", "invoice_date", "discount_pct", "payment_method"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "discount_pct": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "100"}
            ),
            "payment_method": forms.Select(attrs={"class": "form-control-app"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active clients
        from clients.models import Client

        self.fields["client"].queryset = Client.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        discount_pct = cleaned_data.get("discount_pct", 0)

        if client and discount_pct > client.max_discount_pct:
            raise forms.ValidationError(
                f"La remise ne peut pas dépasser {client.max_discount_pct}% pour ce client"
            )

        return cleaned_data


class ClientPaymentForm(forms.ModelForm):
    class Meta:
        model = ClientPayment
        fields = ["payment_date", "amount", "payment_method", "bank_reference"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "bank_reference": forms.TextInput(
                attrs={"placeholder": "Référence bancaire ou numéro de chèque"}
            ),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount


class ClientAccountPaymentForm(forms.ModelForm):
    class Meta:
        from .models import ClientAccountPayment

        model = ClientAccountPayment
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
                    "placeholder": "Référence bancaire ou numéro de chèque",
                    "class": "form-control-app",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control-app"}),
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount


# ---------------------------------------------------------------------------
# §23 (planned) — Client Advance (direct entry) & Opening Balance forms
# mirroring supplier_ops/forms.py's SupplierAdvanceForm / SupplierOpeningBalanceForm
# ---------------------------------------------------------------------------

from .models import ClientAdvance as _ClientAdvance


class ClientAdvanceForm(forms.ModelForm):
    """§23.4 — direct-entry Client Advance (a deposit or advance payment
    recorded up front), independent of any settlement."""

    class Meta:
        model = _ClientAdvance
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


class ClientOpeningBalanceForm(forms.Form):
    """§23.5 — admin-only opening balance entry for a client."""

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


# ---------------------------------------------------------------------------
# ClientSupportingDocForm — PieceJointe upload form for ClientDN /
# ClientInvoice, mirrors supplier_ops.forms.SupplierSupportingDocForm
# (receivables-side equivalent, using the SD-DNC / SD-INV-C / SD-PAY-C /
# SD-CORR codes already defined on core.models.PieceJointe.TYPE_CHOICES).
# ---------------------------------------------------------------------------


class ClientSupportingDocForm(forms.Form):
    """Inline form for attaching a PieceJointe to a ClientDN or ClientInvoice."""

    DN_DOC_TYPES = [
        ("SD-DNC", "BL Client signé"),
        ("SD-CORR", "Document de correction"),
    ]

    INVOICE_DOC_TYPES = [
        ("SD-INV-C", "Facture client émise"),
        ("SD-PAY-C", "Justificatif encaissement client"),
        ("SD-CORR", "Document de correction"),
    ]

    PAYMENT_DOC_TYPES = [
        ("SD-PAY-C", "Justificatif encaissement client"),
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
