from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class FinancialPeriod(models.Model):
    """Financial reporting periods"""

    PERIOD_TYPE_CHOICES = [
        ("monthly", "Mensuel"),
        ("quarterly", "Trimestriel"),
        ("annual", "Annuel"),
        ("custom", "Personnalisé"),
    ]

    name = models.CharField(max_length=100, verbose_name="Nom de la période")
    period_type = models.CharField(
        max_length=20, choices=PERIOD_TYPE_CHOICES, verbose_name="Type de période"
    )
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(verbose_name="Date de fin")
    is_closed = models.BooleanField(default=False, verbose_name="Période clôturée")

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Période financière"
        verbose_name_plural = "Périodes financières"
        ordering = ["-start_date"]
        unique_together = ["period_type", "start_date", "end_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def get_financial_summary(self):
        """Get financial summary for this period"""
        from sales.models import ClientInvoice, ClientPayment
        from supplier_ops.models import SupplierInvoice, SupplierPayment
        from expenses.models import Expense

        # Revenues
        invoiced_revenue = ClientInvoice.objects.filter(
            invoice_date__gte=self.start_date, invoice_date__lte=self.end_date
        ).aggregate(total=models.Sum("total_ttc"))["total"] or Decimal("0.00")

        collected_revenue = ClientPayment.objects.filter(
            payment_date__gte=self.start_date, payment_date__lte=self.end_date
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        # Supplier charges
        committed_supplier_charges = SupplierInvoice.objects.filter(
            invoice_date__gte=self.start_date, invoice_date__lte=self.end_date
        ).aggregate(total=models.Sum("total_ttc"))["total"] or Decimal("0.00")

        paid_supplier_charges = SupplierPayment.objects.filter(
            payment_date__gte=self.start_date, payment_date__lte=self.end_date
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        # Operational expenses
        committed_operational_expenses = Expense.objects.filter(
            expense_date__gte=self.start_date,
            expense_date__lte=self.end_date,
            status__in=["validated", "paid"],
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        paid_operational_expenses = Expense.objects.filter(
            payment_date__gte=self.start_date,
            payment_date__lte=self.end_date,
            status="paid",
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

        # Calculate results
        total_committed_charges = (
            committed_supplier_charges + committed_operational_expenses
        )
        total_paid_charges = paid_supplier_charges + paid_operational_expenses

        theoretical_result = invoiced_revenue - total_committed_charges
        actual_cash_result = collected_revenue - total_paid_charges

        return {
            "invoiced_revenue": invoiced_revenue,
            "collected_revenue": collected_revenue,
            "committed_supplier_charges": committed_supplier_charges,
            "paid_supplier_charges": paid_supplier_charges,
            "committed_operational_expenses": committed_operational_expenses,
            "paid_operational_expenses": paid_operational_expenses,
            "total_committed_charges": total_committed_charges,
            "total_paid_charges": total_paid_charges,
            "theoretical_result": theoretical_result,
            "actual_cash_result": actual_cash_result,
            "collection_rate": (
                (collected_revenue / invoiced_revenue * 100)
                if invoiced_revenue > 0
                else Decimal("0.00")
            ),
            "settlement_rate": (
                (total_paid_charges / total_committed_charges * 100)
                if total_committed_charges > 0
                else Decimal("0.00")
            ),
        }


class ReportTemplate(models.Model):
    """Predefined report templates"""

    REPORT_TYPE_CHOICES = [
        ("financial_result", "Résultat financier"),
        ("receivables_aging", "Échéancier clients"),
        ("payables_aging", "Échéancier fournisseurs"),
        ("production_yield", "Analyse des rendements"),
        ("expense_breakdown", "Répartition des dépenses"),
        ("stock_valuation", "Valorisation des stocks"),
        ("sales_analysis", "Analyse des ventes"),
        ("supplier_analysis", "Analyse fournisseurs"),
    ]

    name = models.CharField(max_length=100, verbose_name="Nom du rapport")
    report_type = models.CharField(
        max_length=30, choices=REPORT_TYPE_CHOICES, verbose_name="Type de rapport"
    )
    description = models.TextField(blank=True, verbose_name="Description")

    # Report parameters (stored as JSON)
    parameters = models.JSONField(default=dict, verbose_name="Paramètres")

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Modèle de rapport"
        verbose_name_plural = "Modèles de rapports"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class ReportExecution(models.Model):
    """Report execution history"""

    STATUS_CHOICES = [
        ("running", "En cours"),
        ("completed", "Terminé"),
        ("failed", "Échec"),
    ]

    template = models.ForeignKey(
        ReportTemplate, on_delete=models.CASCADE, verbose_name="Modèle"
    )
    execution_date = models.DateTimeField(
        auto_now_add=True, verbose_name="Date d'exécution"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="running", verbose_name="Statut"
    )

    # Execution parameters
    parameters = models.JSONField(default=dict, verbose_name="Paramètres d'exécution")

    # Results
    result_data = models.JSONField(
        null=True, blank=True, verbose_name="Données résultat"
    )
    error_message = models.TextField(blank=True, verbose_name="Message d'erreur")

    executed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Exécuté par"
    )

    class Meta:
        verbose_name = "Exécution de rapport"
        verbose_name_plural = "Exécutions de rapports"
        ordering = ["-execution_date"]

    def __str__(self):
        return (
            f"{self.template.name} - {self.execution_date.strftime('%Y-%m-%d %H:%M')}"
        )
