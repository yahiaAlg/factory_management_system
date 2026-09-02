# supplier_ops/utils.py
from django.db import models  # FIX: was missing — models.Sum used below
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
import datetime
import logging
from .models import SupplierInvoice, SupplierDN

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# §23 (planned) — Prepayment consumption engine (mirrors avicole's
# achats.utils.consommer_acomptes_fifo)
# ---------------------------------------------------------------------------


def consume_supplier_advances_fifo(invoice):
    """
    Draw down unused SupplierAdvance records (prepayments / overpayment
    surplus) against a freshly-created invoice, oldest advance first (FIFO)
    — the mirror image of SupplierAccountPayment.settle_fifo(): instead of
    a payment looking for invoices to cover, an invoice checks for money
    that is already waiting (§23.3.3).

    For every DA consumed:
      - A SupplierPayment record is created with payment_method="advance"
        (an audit trail parallel to the ones settle_fifo() creates, and the
        mechanism that updates invoice.balance_due / status immediately —
        a brand-new invoice can already show Paid/Partially Paid the moment
        it is created, before any règlement is ever recorded against it).
      - An immutable SupplierAdvanceAllocation record is created.
      - The advance's remaining_amount is decremented.

    Call this right after an invoice's totals are finalized (after lines /
    linked_dns are set) — from supplier_invoice_create() and from
    create_supplier_opening_balance() below.

    Args:
        invoice (SupplierInvoice): the freshly-created invoice (its
            total_net/balance_due must already reflect its final amount).
    """
    from .models import SupplierAdvance, SupplierAdvanceAllocation, SupplierPayment

    invoice.refresh_from_db()
    if invoice.balance_due <= 0:
        return

    advances = SupplierAdvance.objects.filter(
        supplier=invoice.supplier, remaining_amount__gt=0
    ).order_by("date", "pk")

    remaining_to_cover = invoice.balance_due

    for advance in advances:
        if remaining_to_cover <= 0:
            break

        to_consume = min(advance.remaining_amount, remaining_to_cover)
        if to_consume <= 0:
            continue

        payment = SupplierPayment(
            supplier_invoice=invoice,
            supplier=invoice.supplier,
            payment_date=advance.date if advance.date > invoice.invoice_date else invoice.invoice_date,
            amount=to_consume,
            payment_method="advance",
            bank_reference=advance.reference,
            recorded_by=advance.recorded_by or invoice.created_by,
        )
        payment.save()

        SupplierAdvanceAllocation.objects.create(
            advance=advance, invoice=invoice, amount_allocated=to_consume
        )

        advance.remaining_amount = advance.remaining_amount - to_consume
        advance.save(update_fields=["remaining_amount"])

        remaining_to_cover -= to_consume

        logger.info(
            "§23.3.3: consumed %s DA from SupplierAdvance pk=%s for %s against "
            "invoice %s. Advance remaining: %s DA.",
            to_consume,
            advance.pk,
            invoice.supplier.code,
            invoice.reference,
            advance.remaining_amount,
        )

    invoice.recompute_balance_due()


# ---------------------------------------------------------------------------
# §23.5 (planned) — Opening Balance (mirrors avicole's
# achats.utils.creer_dette_initiale_fournisseur)
# ---------------------------------------------------------------------------


def create_supplier_opening_balance(
    supplier, amount, motif, reference_date=None, due_date=None, created_by=None
):
    """
    ADMIN-ONLY: record a prior debt the factory owes *supplier* (opening
    balance when the supplier is first entered into the system with an
    existing balance) as a normal SupplierInvoice with
    is_opening_balance=True and no lines/DNs attached (§23.5).

    Because it's a real SupplierInvoice, every existing screen (dette
    globale, aging, FIFO settlement, statement of account) picks it up
    automatically — no other function needs to change. The caller (the
    view) MUST verify the requesting user is a manager/admin before calling
    this.

    Args:
        supplier (Supplier): the supplier owed money.
        amount (Decimal): amount owed, > 0.
        motif (str): required explanation, stored in invoice notes for audit.
        reference_date (date | None): defaults to today.
        due_date (date | None): optional due date; defaults to reference_date.
        created_by (User | None): the admin recording this entry.

    Returns:
        SupplierInvoice: the newly created opening-balance invoice.

    Raises:
        ValueError: amount is not strictly positive.
    """
    from core.models import DocumentSequence
    from .models import SupplierInvoice

    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Le montant du solde d'ouverture doit être supérieur à zéro.")

    reference_date = reference_date or datetime.date.today()
    due_date = due_date or reference_date

    invoice = SupplierInvoice.objects.create(
        reference=DocumentSequence.get_next_reference("FF", reference_date.year),
        # Suffixed with a timestamp (not just the date) so several
        # same-day opening-balance entries for the same supplier never
        # collide on the (supplier, external_reference) uniqueness check
        # (BR-INV-08) — the spec explicitly allows several such entries.
        external_reference=f"OUV-{reference_date.isoformat()}-{datetime.datetime.now().strftime('%H%M%S%f')}",
        supplier=supplier,
        invoice_date=reference_date,
        due_date=due_date,
        status="unpaid",
        payment_method="virement",
        total_ht=amount,
        vat_amount=Decimal("0.00"),
        total_ttc=amount,
        timbre_fiscal=Decimal("0.00"),
        total_net=amount,
        balance_due=amount,
        is_opening_balance=True,
        notes=f"Solde d'ouverture / correction — {motif}",
        created_by=created_by,
    )

    # §23.5 "Immediate advance consumption": if the supplier already has an
    # unused advance on file, consume it against this opening balance right
    # away — mirrors the call for BL-derived invoices in
    # supplier_invoice_create().
    consume_supplier_advances_fifo(invoice)

    logger.info(
        "§23.5: opening balance of %s DA recorded for supplier '%s' by '%s'. "
        "Invoice %s.",
        amount,
        supplier.code,
        created_by,
        invoice.reference,
    )
    return invoice


# ---------------------------------------------------------------------------
# §23.6 (planned) — Statement of account (mirrors avicole's
# achats.utils.get_releve_compte_fournisseur)
# ---------------------------------------------------------------------------


def get_supplier_statement(supplier, date_start=None, date_end=None) -> dict:
    """
    Build a chronological, running-balance statement of account for one
    supplier (§23.6) — the printable équivalent of a "relevé de compte".

    Débit lines come from SupplierInvoice (invoicing creates debt in this
    system, not receipt), crédit lines from SupplierPayment — EXCLUDING
    payment_method="advance" rows, since those only represent the still-
    unconsumed portion of a payment/settlement already counted in full as
    that payment's own crédit line elsewhere; listing them again would
    double-count the same cash movement.

    Args:
        supplier (Supplier): the supplier instance.
        date_start (date | None): first day included in the main table;
            everything strictly before this date is folded into
            opening_balance instead of appearing as its own row.
        date_end (date | None): last day included in the main table.

    Returns:
        dict with keys: opening_balance, lines, closing_balance,
        total_debit, total_credit, unbilled_dns.
    """
    from .models import SupplierPayment, SupplierAdvance

    invoices_qs = SupplierInvoice.objects.filter(supplier=supplier).prefetch_related(
        "lines", "linked_dns"
    )
    payments_qs = SupplierPayment.objects.filter(supplier=supplier).exclude(
        payment_method="advance"
    )
    # §23.3.2: every SupplierAdvance.amount is cash that came in with no
    # SupplierPayment row of its own at the time — whether it was the
    # unapplied remainder of a settlement (origin=settlement_surplus) or a
    # standalone deposit (origin=direct_entry). Its *later* consumption
    # against an invoice creates a payment_method="advance" row, already
    # excluded above, so counting the advance itself here (once, at its own
    # date) is the only place that cash movement is ever counted — no
    # double-count, no missing credit line.
    advances_qs = SupplierAdvance.objects.filter(supplier=supplier)

    opening_balance = Decimal("0")
    if date_start is not None:
        opening_balance += invoices_qs.filter(invoice_date__lt=date_start).aggregate(
            total=models.Sum("total_net")
        )["total"] or Decimal("0")
        opening_balance -= payments_qs.filter(payment_date__lt=date_start).aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")
        opening_balance -= advances_qs.filter(date__lt=date_start).aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")
        invoices_qs = invoices_qs.filter(invoice_date__gte=date_start)
        payments_qs = payments_qs.filter(payment_date__gte=date_start)
        advances_qs = advances_qs.filter(date__gte=date_start)

    if date_end is not None:
        invoices_qs = invoices_qs.filter(invoice_date__lte=date_end)
        payments_qs = payments_qs.filter(payment_date__lte=date_end)
        advances_qs = advances_qs.filter(date__lte=date_end)

    lines = []
    for invoice in invoices_qs.order_by("invoice_date", "pk"):
        lines.append(
            {
                "date": invoice.invoice_date,
                "type": "invoice",
                "reference": invoice.reference,
                "dns": list(invoice.linked_dns.all()),
                "is_opening_balance": invoice.is_opening_balance,
                "status_display": invoice.get_status_display(),
                "debit": invoice.total_net,
                "credit": Decimal("0"),
                "object": invoice,
            }
        )
    for payment in payments_qs.order_by("payment_date", "pk"):
        lines.append(
            {
                "date": payment.payment_date,
                "type": "payment",
                "reference": payment.reference,
                "dns": [],
                "is_opening_balance": False,
                "status_display": payment.get_payment_method_display(),
                "debit": Decimal("0"),
                "credit": payment.amount,
                "object": payment,
            }
        )
    for advance in advances_qs.order_by("date", "pk"):
        lines.append(
            {
                "date": advance.date,
                "type": "advance",
                "reference": advance.reference,
                "dns": [],
                "is_opening_balance": False,
                "status_display": (
                    "Surplus de règlement"
                    if advance.origin == SupplierAdvance.ORIGIN_SETTLEMENT_SURPLUS
                    else "Avance directe"
                ),
                "debit": Decimal("0"),
                "credit": advance.amount,
                "object": advance,
            }
        )

    # Chronological; on a same-day tie, the invoice is listed before the
    # payment/advance (the debt is booked before a same-day credit against
    # it).
    lines.sort(key=lambda l: (l["date"], 0 if l["type"] == "invoice" else 1))

    balance = opening_balance
    for line in lines:
        balance += line["debit"] - line["credit"]
        line["balance"] = balance

    total_debit = sum((l["debit"] for l in lines), Decimal("0"))
    total_credit = sum((l["credit"] for l in lines), Decimal("0"))

    unbilled_dns_qs = SupplierDN.objects.filter(
        supplier=supplier, status="validated", linked_invoice__isnull=True
    ).order_by("delivery_date")
    if date_start is not None:
        unbilled_dns_qs = unbilled_dns_qs.filter(delivery_date__gte=date_start)
    if date_end is not None:
        unbilled_dns_qs = unbilled_dns_qs.filter(delivery_date__lte=date_end)

    return {
        "opening_balance": opening_balance,
        "lines": lines,
        "closing_balance": balance,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "unbilled_dns": list(unbilled_dns_qs),
    }
