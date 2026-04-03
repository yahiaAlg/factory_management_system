# reporting/forms.py
from django import forms
from .models import FinancialPeriod, ReportTemplate

class FinancialPeriodForm(forms.ModelForm):
    class Meta:
        model = FinancialPeriod
        fields = ['name', 'period_type', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError(
                "La date de fin doit être postérieure à la date de début"
            )
        
        return cleaned_data

class ReportParametersForm(forms.Form):
    """Generic form for report parameters"""
    
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Date de début"
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Date de fin"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default values to current month
        from django.utils import timezone
        now = timezone.now()
        current_month = now.replace(day=1)
        next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
        
        self.fields['date_from'].initial = current_month.date()
        self.fields['date_to'].initial = (next_month - timezone.timedelta(days=1)).date()

class AgingReportForm(forms.Form):
    """Form for aging reports"""
    
    as_of_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Date de situation",
        initial=timezone.now().date()
    )

class StockReportForm(forms.Form):
    """Form for stock reports"""
    
    STOCK_TYPE_CHOICES = [
        ('all', 'Tous les stocks'),
        ('raw_materials', 'Matières premières'),
        ('finished_products', 'Produits finis'),
    ]
    
    stock_type = forms.ChoiceField(
        choices=STOCK_TYPE_CHOICES,
        initial='all',
        label="Type de stock"
    )
    
    include_zero_stock = forms.BooleanField(
        required=False,
        initial=False,
        label="Inclure les stocks à zéro"
    )