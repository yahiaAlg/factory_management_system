# sales/utils.py
"""
Business-logic helpers for the client invoicing cycle — §23 (planned)
Prepayment / Opening Balance / Statement of Account mechanism.

Mirrors supplier_ops/utils.py exactly, on the receivables side:
    consume_client_advances_fifo   — §23.4 prepayment consumption engine
    create_client_opening_balance  — §23.5 admin-only opening balance
    get_client_statement           — §23.6 chronological statement of account
"""
from django.db import models
from decimal import Decimal
import datetime
import logging

from .models import ClientInvoice, ClientDN

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# §23.4 (planned) — Prepayment consumption engine
# ---------------------------------------------------------------------------


def consume_client_advances_fifo(invoice):
    """
    Draw down unused ClientAdvance records (deposits / overpayment surplus)
    against a freshly-created invoice, oldest advance first (FIFO) — mirrors
    supplier_ops.utils.consume_supplier_advances_fifo (§23.3.3 / §23.4).

    For every DA consumed:
      - A ClientPayment record is created with payment_method="advance".
      - An immutable ClientAdvanceAllocation record is created.
      - The advance's remaining_amount is decremented.

    Call this right after an invoice's totals are finalized — from
    client_invoice_create() and from create_client_opening_balance() below.

    Args:
        invoice (ClientInvoice): the freshly-created invoice.
    """
    from .models import ClientAdvance, ClientAdvanceAllocation, ClientPayment

    invoice.refresh_from_db()
    if invoice.balance_due <= 0:
        return

    advances = ClientAdvance.objects.filter(
        client=invoice.client, remaining_amount__gt=0
    ).order_by("date", "pk")

    remaining_to_cover = invoice.balance_due

    for advance in advances:
        if remaining_to_cover <= 0:
            break

        to_consume = min(advance.remaining_amount, remaining_to_cover)
        if to_consume <= 0:
            continue

        payment = ClientPayment(
            client_invoice=invoice,
            client=invoice.client,
            payment_date=advance.date if advance.date > invoice.invoice_date else invoice.invoice_date,
            amount=to_consume,
            payment_method="advance",
            bank_reference=advance.reference,
            recorded_by=advance.recorded_by or invoice.created_by,
        )
        payment.save()

        ClientAdvanceAllocation.objects.create(
            advance=advance, invoice=invoice, amount_allocated=to_consume
        )

        advance.remaining_amount = advance.remaining_amount - to_consume
        advance.save(update_fields=["remaining_amount"])

        remaining_to_cover -= to_consume

        logger.info(
            "§23.4: consumed %s DA from ClientAdvance pk=%s for %s against "
            "invoice %s. Advance remaining: %s DA.",
            to_consume,
            advance.pk,
            invoice.client.code,
            invoice.reference,
            advance.remaining_amount,
        )

    invoice.recompute_balance_due()


# ---------------------------------------------------------------------------
# §23.5 (planned) — Opening Balance
# ---------------------------------------------------------------------------


def create_client_opening_balance(
    client, amount, motif, reference_date=None, due_date=None, created_by=None
):
    """
    ADMIN-ONLY: record a prior receivable owed by *client* (opening balance
    when the client is first entered into the system with an existing
    balance) as a normal ClientInvoice with is_opening_balance=True and no
    DNs attached (§23.5). Mirrors
    supplier_ops.utils.create_supplier_opening_balance.

    Args:
        client (Client): the client who owes money.
        amount (Decimal): amount owed, > 0.
        motif (str): required explanation, stored in invoice notes for audit.
        reference_date (date | None): defaults to today.
        due_date (date | None): optional due date; defaults to reference_date.
        created_by (User | None): the admin recording this entry.

    Returns:
        ClientInvoice: the newly created opening-balance invoice.

    Raises:
        ValueError: amount is not strictly positive.
    """
    from core.models import DocumentSequence
    from .models import ClientInvoice

    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Le montant du solde d'ouverture doit être supérieur à zéro.")

    reference_date = reference_date or datetime.date.today()
    due_date = due_date or reference_date

    invoice = ClientInvoice.objects.create(
        reference=DocumentSequence.get_next_reference("FC", reference_date.year),
        client=client,
        invoice_date=reference_date,
        due_date=due_date,
        status="issued",
        payment_method="virement",
        total_ht=amount,
        discount_pct=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total_ttc=amount,
        timbre_fiscal=Decimal("0.00"),
        total_net=amount,
        balance_due=amount,
        is_opening_balance=True,
        notes=f"Solde d'ouverture / correction — {motif}",
        created_by=created_by,
    )

    # §23.5 "Immediate advance consumption": if the client already has an
    # unused advance on file, consume it against this opening balance right
    # away — mirrors the call for DN-derived invoices in
    # client_invoice_create().
    consume_client_advances_fifo(invoice)

    logger.info(
        "§23.5: opening balance of %s DA recorded for client '%s' by '%s'. "
        "Invoice %s.",
        amount,
        client.code,
        created_by,
        invoice.reference,
    )
    return invoice


# ---------------------------------------------------------------------------
# §23.6 (planned) — Statement of account
# ---------------------------------------------------------------------------


def get_client_statement(client, date_start=None, date_end=None) -> dict:
    """
    Build a chronological, running-balance statement of account for one
    client (§23.6). Mirrors supplier_ops.utils.get_supplier_statement.

    Débit lines come from ClientInvoice, crédit lines from ClientPayment —
    EXCLUDING payment_method="advance" rows (already counted once as the
    original payment's own crédit line — see consume_client_advances_fifo).

    Args:
        client (Client): the client instance.
        date_start (date | None): first day included in the main table.
        date_end (date | None): last day included in the main table.

    Returns:
        dict with keys: opening_balance, lines, closing_balance,
        total_debit, total_credit, unbilled_dns.
    """
    from .models import ClientPayment, ClientAdvance

    invoices_qs = ClientInvoice.objects.filter(client=client).prefetch_related(
        "linked_dns"
    )
    payments_qs = ClientPayment.objects.filter(client=client).exclude(
        payment_method="advance"
    )
    # §23.4: mirrors supplier_ops.utils.get_supplier_statement — every
    # ClientAdvance.amount is cash received with no ClientPayment row of
    # its own yet (settlement surplus or a standalone deposit); its later
    # consumption creates an excluded "advance"-method row, so counting the
    # advance itself here is the only place that cash is ever counted.
    advances_qs = ClientAdvance.objects.filter(client=client)

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
                    if advance.origin == ClientAdvance.ORIGIN_SETTLEMENT_SURPLUS
                    else "Avance directe"
                ),
                "debit": Decimal("0"),
                "credit": advance.amount,
                "object": advance,
            }
        )

    lines.sort(key=lambda l: (l["date"], 0 if l["type"] == "invoice" else 1))

    balance = opening_balance
    for line in lines:
        balance += line["debit"] - line["credit"]
        line["balance"] = balance

    total_debit = sum((l["debit"] for l in lines), Decimal("0"))
    total_credit = sum((l["credit"] for l in lines), Decimal("0"))

    unbilled_dns_qs = ClientDN.objects.filter(
        client=client, status="validated", linked_invoice__isnull=True
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
