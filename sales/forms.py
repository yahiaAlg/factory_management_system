from django import forms
from django.forms import inlineformset_factory
from .models import ClientDN, ClientDNLine, ClientInvoice, ClientPayment

class ClientDNForm(forms.ModelForm):
    class Meta:
        model = ClientDN
        fields = ['client', 'delivery_date', 'discount_pct', 'remarks']
        widgets = {
            'delivery_date': forms.DateInput(attrs={'type': 'date'}),
            'discount_pct': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active clients with good credit status
        from clients.models import Client
        self.fields['client'].queryset = Client.objects.filter(
            is_active=True,
            credit_status__in=['active', 'suspended']
        )
    
    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        discount_pct = cleaned_data.get('discount_pct', 0)
        
        if client and discount_pct > client.max_discount_pct:
            raise forms.ValidationError(
                f"La remise ne peut pas dépasser {client.max_discount_pct}% pour ce client"
            )
        
        return cleaned_data

class ClientDNLineForm(forms.ModelForm):
    class Meta:
        model = ClientDNLine
        fields = ['finished_product', 'quantity_delivered', 'unit_of_measure', 'selling_unit_price_ht']
        widgets = {
            'quantity_delivered': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'selling_unit_price_ht': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active finished products and units
        from catalog.models import FinishedProduct, UnitOfMeasure
        self.fields['finished_product'].queryset = FinishedProduct.objects.filter(is_active=True)
        self.fields['unit_of_measure'].queryset = UnitOfMeasure.objects.filter(is_active=True)
        
        # Set default price from product reference price
        if self.instance and self.instance.finished_product:
            self.fields['selling_unit_price_ht'].initial = self.instance.finished_product.reference_selling_price

ClientDNLineFormSet = inlineformset_factory(
    ClientDN,
    ClientDNLine,
    form=ClientDNLineForm,
    extra=1,
    can_delete=True
)

class ClientInvoiceForm(forms.ModelForm):
    class Meta:
        model = ClientInvoice
        fields = ['client', 'invoice_date', 'discount_pct']
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'discount_pct': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter active clients
        from clients.models import Client
        self.fields['client'].queryset = Client.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        discount_pct = cleaned_data.get('discount_pct', 0)
        
        if client and discount_pct > client.max_discount_pct:
            raise forms.ValidationError(
                f"La remise ne peut pas dépasser {client.max_discount_pct}% pour ce client"
            )
        
        return cleaned_data

class ClientPaymentForm(forms.ModelForm):
    class Meta:
        model = ClientPayment
        fields = ['payment_date', 'amount', 'payment_method', 'bank_reference']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'bank_reference': forms.TextInput(attrs={'placeholder': 'Référence bancaire ou numéro de chèque'}),
        }
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Le montant doit être positif")
        return amount