# supplier_ops/utils.py
from django.db import models  # FIX: was missing — models.Sum used below
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from .models import SupplierInvoice, SupplierDN


def get_overdue_supplier_invoices():
    """Get all overdue supplier invoices."""
    return SupplierInvoice.objects.filter(
        due_date__lt=timezone.now().date(),
        balance_due__gt=0,
        status__in=["verified", "unpaid", "partially_paid"],
    )


def get_disputed_supplier_invoices():
    """Get all disputed supplier invoices."""
    return SupplierInvoice.objects.filter(status="in_dispute")


def get_unlinked_supplier_dns():
    """Get validated supplier DNs not yet linked to invoices."""
    return SupplierDN.objects.filter(
        status="validated",
        linked_invoice__isnull=True,
    )


def calculate_supplier_outstanding_balance(supplier):
    """Calculate total outstanding balance for a supplier."""
    # FIX: was using models.Sum without importing models; now uses Sum directly.
    return SupplierInvoice.objects.filter(
        supplier=supplier,
        status__in=["verified", "unpaid", "partially_paid"],
    ).aggregate(total=Sum("balance_due"))["total"] or Decimal("0.00")


def get_reconciliation_summary(period_start=None, period_end=None):
    """Get reconciliation summary for a period."""
    invoices = SupplierInvoice.objects.all()

    if period_start:
        invoices = invoices.filter(invoice_date__gte=period_start)
    if period_end:
        invoices = invoices.filter(invoice_date__lte=period_end)

    return {
        "total_invoices": invoices.count(),
        "compliant": invoices.filter(reconciliation_result="compliant").count(),
        "minor_discrepancy": invoices.filter(
            reconciliation_result="minor_discrepancy"
        ).count(),
        "dispute": invoices.filter(reconciliation_result="dispute").count(),
        "pending": invoices.filter(reconciliation_result="pending").count(),
        # reconciliation_delta is a stored DB field (updated by perform_reconciliation),
        # so summing abs values in Python is acceptable for a summary figure.
        "total_delta_amount": sum(abs(inv.reconciliation_delta) for inv in invoices),
    }
