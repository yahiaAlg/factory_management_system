# expenses/forms.py
from django import forms
from .models import Expense, SupportingDocument

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'expense_date', 'category', 'description', 'amount', 
            'beneficiary', 'linked_supplier_invoice'
        ]
        widgets = {
            'expense_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'beneficiary': forms.TextInput(attrs={'size': 50}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter supplier invoices that are verified but not yet linked to expenses
        from supplier_ops.models import SupplierInvoice
        self.fields['linked_supplier_invoice'].queryset = SupplierInvoice.objects.filter(
            status__in=['verified', 'unpaid', 'partially_paid'],
            expense__isnull=True  # Not already linked to an expense
        )
        self.fields['linked_supplier_invoice'].required = False
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount

class SupportingDocumentForm(forms.ModelForm):
    class Meta:
        model = SupportingDocument
        fields = ['doc_type', 'description', 'file_reference']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'file_reference': forms.TextInput(attrs={'placeholder': 'Référence du fichier ou emplacement'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter document types relevant to expenses
        expense_doc_types = [
            ('SD-EXP', 'Justificatif dépense'),
            ('SD-INV-F', 'Facture fournisseur originale'),
            ('SD-PAY-F', 'Justificatif paiement fournisseur'),
        ]
        self.fields['doc_type'].choices = expense_doc_types

class ExpenseValidationForm(forms.Form):
    action = forms.ChoiceField(
        choices=[('validate', 'Valider'), ('reject', 'Rejeter')],
        widget=forms.RadioSelect,
        label="Action"
    )
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Motif de rejet"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        rejection_reason = cleaned_data.get('rejection_reason')
        
        if action == 'reject' and not rejection_reason:
            raise forms.ValidationError("Le motif de rejet est obligatoire")
        
        return cleaned_data

class ExpensePaymentForm(forms.Form):
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Date de paiement"
    )
    payment_method = forms.ChoiceField(
        choices=Expense.PAYMENT_METHOD_CHOICES,
        label="Mode de paiement"
    )
    bank_reference = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Référence bancaire ou numéro de chèque'}),
        label="Référence bancaire"
    )