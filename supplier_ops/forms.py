# supplier_ops/forms.py
from django import forms
from django.forms import inlineformset_factory
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
        fields = ["external_reference", "supplier", "delivery_date", "remarks"]
        widgets = {
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active suppliers
        from suppliers.models import Supplier

        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)


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
        fields = ["external_reference", "supplier", "invoice_date", "due_date"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
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


class SupplierAccountPaymentForm(forms.ModelForm):
    class Meta:
        from .models import SupplierAccountPayment

        model = SupplierAccountPayment
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
