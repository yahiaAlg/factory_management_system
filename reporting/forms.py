# reporting/forms.py
from django import forms
from .models import FinancialPeriod, ReportTemplate


class FinancialPeriodForm(forms.ModelForm):
    class Meta:
        model = FinancialPeriod
        fields = ["name", "period_type", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError(
                "La date de fin doit être postérieure à la date de début."
            )

        return cleaned_data


class ReportParametersForm(forms.Form):
    """Generic form for report parameters."""

    date_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date de début",
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date de fin",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default to current month — evaluated per request, not at import time
        from django.utils import timezone

        now = timezone.now()
        first_of_month = now.replace(day=1).date()
        first_of_next = (
            (now.replace(day=1) + timezone.timedelta(days=32)).replace(day=1).date()
        )
        last_of_month = first_of_next - timezone.timedelta(days=1)

        self.fields["date_from"].initial = first_of_month
        self.fields["date_to"].initial = last_of_month

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError(
                "La date de début doit être antérieure ou égale à la date de fin."
            )

        return cleaned_data


class AgingReportForm(forms.Form):
    """Form for aging reports."""

    as_of_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Date de situation",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIX: set initial in __init__, not at class body level.
        # Class-level initial=timezone.now().date() is evaluated once at import
        # time and stays frozen for the lifetime of the process.
        from django.utils import timezone

        self.fields["as_of_date"].initial = timezone.now().date()


class StockReportForm(forms.Form):
    """Form for stock reports."""

    STOCK_TYPE_CHOICES = [
        ("all", "Tous les stocks"),
        ("raw_materials", "Matières premières"),
        ("finished_products", "Produits finis"),
    ]

    stock_type = forms.ChoiceField(
        choices=STOCK_TYPE_CHOICES,
        initial="all",
        label="Type de stock",
    )
    include_zero_stock = forms.BooleanField(
        required=False,
        initial=False,
        label="Inclure les stocks à zéro",
    )
