# expenses/forms.py
from django import forms
from .models import Expense, SupportingDocument


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "expense_date",
            "category",
            "description",
            "amount",
            "beneficiary",
            "linked_supplier_invoice",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "beneficiary": forms.TextInput(attrs={"size": 50}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter supplier invoices that are verified but not yet linked to expenses
        from supplier_ops.models import SupplierInvoice

        self.fields["linked_supplier_invoice"].queryset = (
            SupplierInvoice.objects.filter(
                status__in=["verified", "unpaid", "partially_paid"],
                expense__isnull=True,  # Not already linked to an expense
            )
        )
        self.fields["linked_supplier_invoice"].required = False

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount


from core.forms import PieceJointeForm


class ExpensePieceJointeForm(PieceJointeForm):
    """
    Attach a PieceJointe (core.models) to an Expense — mirrors the avicole
    project's mechanism. Replaces the old SupportingDocument-backed
    SupportingDocumentForm (ad-hoc entity_type/entity_id).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the document types relevant to expenses.
        self.fields["type_document"].choices = [
            ("SD-EXP", "Justificatif dépense"),
            ("SD-INV-F", "Facture fournisseur originale"),
            ("SD-PAY-F", "Justificatif paiement fournisseur"),
        ]
        self.fields["type_document"].required = True
        self.fields["description"].required = True
        self.fields["fichier"].required = True


#: Kept as an alias for any code/import that still refers to the old name.
SupportingDocumentForm = ExpensePieceJointeForm


class ExpenseValidationForm(forms.Form):
    action = forms.ChoiceField(
        choices=[("validate", "Valider"), ("reject", "Rejeter")],
        widget=forms.RadioSelect,
        label="Action",
    )
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Motif de rejet"
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get("action")
        rejection_reason = cleaned_data.get("rejection_reason")

        if action == "reject" and not rejection_reason:
            raise forms.ValidationError("Le motif de rejet est obligatoire")

        return cleaned_data


class ExpensePaymentForm(forms.Form):
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), label="Date de paiement"
    )
    payment_method = forms.ChoiceField(
        choices=Expense.PAYMENT_METHOD_CHOICES, label="Mode de paiement"
    )
    bank_reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Référence bancaire ou numéro de chèque"}
        ),
        label="Référence bancaire",
    )

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get("payment_method")
        bank_reference = cleaned_data.get("bank_reference", "").strip()

        if payment_method and payment_method != "cash" and not bank_reference:
            raise forms.ValidationError(
                "La référence bancaire est obligatoire pour les paiements hors espèces."
            )

        return cleaned_data
