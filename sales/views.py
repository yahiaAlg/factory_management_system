# sales/views.py
import json

from django.views.decorators.http import require_POST
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from core.models import ProductionSite
from core.utils import get_default_site, remember_site, site_filter_kwargs
from .models import ClientDN, ClientDNLine, ClientInvoice, ClientPayment
from .forms import (
    ClientDNForm,
    ClientDNLineFormSet,
    ClientInvoiceForm,
    ClientPaymentForm,
    ClientAccountPaymentForm,
    ClientSupportingDocForm,
)
from django.db.models.functions import TruncMonth


@login_required
def client_dns_list(request):
    dns = ClientDN.objects.select_related("client", "validated_by", "site").filter(
        **site_filter_kwargs(request)
    )
    search = request.GET.get("search")
    if search:
        dns = dns.filter(
            Q(reference__icontains=search) | Q(client__raison_sociale__icontains=search)
        )
    status_filter = request.GET.get("status")
    if status_filter:
        dns = dns.filter(status=status_filter)
    client_filter = request.GET.get("client")
    if client_filter:
        dns = dns.filter(client_id=client_filter)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        dns = dns.filter(delivery_date__gte=date_from)
    if date_to:
        dns = dns.filter(delivery_date__lte=date_to)
    return render(
        request,
        "sales/client_dns_list.html",
        {
            "dns": dns.order_by("-delivery_date"),
            "status_choices": ClientDN.STATUS_CHOICES,
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Bons de livraison clients",
        },
    )


@login_required
@role_required(["manager", "sales"])
def client_dn_create(request):
    if request.method == "POST":
        form = ClientDNForm(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            ClientSupportingDocForm(request.POST, request.FILES, entity_type="dn")
            if request.FILES.get("file")
            else None
        )
        if form.is_valid() and (doc_form is None or doc_form.is_valid()):
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            formset = ClientDNLineFormSet(request.POST, instance=dn)
            if formset.is_valid():
                formset.save()
                remember_site(request, dn.site)
                if doc_form is not None:
                    from core.models import PieceJointe

                    PieceJointe.objects.create(
                        content_object=dn,
                        type_document=doc_form.cleaned_data["doc_type"],
                        description=doc_form.cleaned_data["description"],
                        fichier=doc_form.cleaned_data.get("file"),
                        uploaded_by=request.user,
                    )
                AuditLog.log_action(
                    user=request.user,
                    action_type="create",
                    module="sales",
                    instance=dn,
                    request=request,
                )
                messages.success(request, f"BL Client {dn.reference} créé avec succès")
                return redirect("sales:client_dn_detail", dn_id=dn.id)
            else:
                dn.delete()
                formset = ClientDNLineFormSet(request.POST)
        else:
            formset = ClientDNLineFormSet(request.POST)
    else:
        form = ClientDNForm(initial_site=get_default_site(request))
        formset = ClientDNLineFormSet()
        doc_form = ClientSupportingDocForm(entity_type="dn")
    return render(
        request,
        "sales/client_dn_form.html",
        {
            "form": form,
            "formset": formset,
            "doc_form": doc_form,
            "title": "Nouveau BL Client",
        },
    )


@login_required
def client_dn_edit(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    if dn.status != "draft":
        messages.error(request, "Seuls les BL en brouillon peuvent être modifiés.")
        return redirect("sales:client_dn_detail", dn_id=dn.id)
    if request.method == "POST":
        form = ClientDNForm(request.POST, instance=dn)
        formset = ClientDNLineFormSet(request.POST, instance=dn)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"BL {dn.reference} mis à jour.")
            return redirect("sales:client_dn_detail", dn_id=dn.id)
    else:
        form = ClientDNForm(instance=dn)
        formset = ClientDNLineFormSet(instance=dn)
    return render(
        request,
        "sales/client_dn_form.html",
        {
            "form": form,
            "formset": formset,
            "title": f"Modifier {dn.reference}",
            "dn": dn,
        },
    )


@login_required
def client_dn_detail(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    role = request.user.userprofile.role
    lines = dn.lines.select_related("finished_product", "unit_of_measure").all()
    gross_ht = sum(line.line_amount for line in lines)
    discount_amount = gross_ht - dn.total_ht
    supporting_docs = dn.pieces_jointes.select_related("uploaded_by").order_by(
        "-created_at"
    )
    return render(
        request,
        "sales/client_dn_detail.html",
        {
            "dn": dn,
            "lines": lines,
            "gross_ht": gross_ht,
            "discount_amount": discount_amount,
            "supporting_docs": supporting_docs,
            "can_validate": role in ["manager", "sales"] and dn.status == "draft",
            "can_invoice": role in ["manager", "sales", "accountant"]
            and dn.can_be_invoiced(),
            "title": f"BL Client - {dn.reference}",
        },
    )


@login_required
@role_required(["manager", "sales", "accountant"])
def client_dn_add_document(request, dn_id):
    """Attach a PieceJointe to a ClientDN (mirrors supplier_dn_add_document)."""
    dn = get_object_or_404(ClientDN, pk=dn_id)
    if request.method == "POST":
        form = ClientSupportingDocForm(request.POST, request.FILES, entity_type="dn")
        if form.is_valid():
            from core.models import PieceJointe

            PieceJointe.objects.create(
                content_object=dn,
                type_document=form.cleaned_data["doc_type"],
                description=form.cleaned_data["description"],
                fichier=form.cleaned_data.get("file"),
                uploaded_by=request.user,
            )
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="sales",
                instance=dn,
                details={"document_added": form.cleaned_data["doc_type"]},
                request=request,
            )
            messages.success(request, "Document justificatif ajouté avec succès.")
            return redirect("sales:client_dn_detail", dn_id=dn.pk)
    else:
        form = ClientSupportingDocForm(entity_type="dn")
    return render(
        request,
        "sales/client_dn_add_document.html",
        {"form": form, "dn": dn, "title": f"Ajouter un justificatif — {dn.reference}"},
    )


@login_required
@role_required(["manager", "sales"])
def client_dn_validate(request, dn_id):
    dn = get_object_or_404(ClientDN, id=dn_id)
    if request.method == "POST":
        try:
            dn.validate(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="validate",
                module="sales",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL {dn.reference} validé avec succès")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
    return redirect("sales:client_dn_detail", dn_id=dn.id)


@login_required
def client_invoices_list(request):
    invoices = ClientInvoice.objects.select_related("client").all()
    search = request.GET.get("search")
    if search:
        invoices = invoices.filter(
            Q(reference__icontains=search) | Q(client__raison_sociale__icontains=search)
        )
    status_filter = request.GET.get("status")
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    if request.GET.get("overdue") == "true":
        invoices = invoices.filter(
            due_date__lt=timezone.now().date(), balance_due__gt=0
        )
    client_filter = request.GET.get("client")
    if client_filter:
        invoices = invoices.filter(client_id=client_filter)
    return render(
        request,
        "sales/client_invoices_list.html",
        {
            "invoices": invoices.order_by("-invoice_date"),
            "status_choices": ClientInvoice.STATUS_CHOICES,
            "title": "Factures clients",
        },
    )


from django.http import JsonResponse


@login_required
def client_dns_for_client(request, client_id):
    """Return validated, uninvoiced DNs for a client as JSON (used by invoice create form)."""
    try:
        dns = ClientDN.objects.filter(
            client_id=client_id,
            status="validated",
            linked_invoice__isnull=True,
        ).prefetch_related("lines__finished_product", "lines__unit_of_measure")

        data = []
        for dn in dns:
            lines = []
            for l in dn.lines.all():
                lines.append(
                    {
                        "fp_id": l.finished_product_id,
                        "fp_ref": (
                            l.finished_product.reference if l.finished_product else ""
                        ),
                        "fp_name": (
                            l.finished_product.designation if l.finished_product else ""
                        ),
                        "uom_symbol": (
                            l.unit_of_measure.symbol if l.unit_of_measure else ""
                        ),
                        "quantity_delivered": str(l.quantity_delivered),
                        "selling_unit_price_ht": str(l.selling_unit_price_ht),
                    }
                )
            data.append(
                {
                    "id": dn.id,
                    "reference": dn.reference,
                    "delivery_date": str(dn.delivery_date),
                    "total_amount_ht": str(dn.total_ht),
                    "lines": lines,
                }
            )
        return JsonResponse({"success": True, "dns": data})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@role_required(["manager", "sales", "accountant"])
def client_invoice_create(request):
    if request.method == "POST":
        form = ClientInvoiceForm(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            ClientSupportingDocForm(
                request.POST, request.FILES, entity_type="invoice"
            )
            if request.FILES.get("file")
            else None
        )
        if form.is_valid() and (doc_form is None or doc_form.is_valid()):
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            if doc_form is not None:
                from core.models import PieceJointe

                PieceJointe.objects.create(
                    content_object=invoice,
                    type_document=doc_form.cleaned_data["doc_type"],
                    description=doc_form.cleaned_data["description"],
                    fichier=doc_form.cleaned_data.get("file"),
                    uploaded_by=request.user,
                )
            linked_dn_ids = request.POST.getlist("linked_dns")
            for dn_id in linked_dn_ids:
                try:
                    dn = ClientDN.objects.get(
                        id=dn_id, status="validated", linked_invoice__isnull=True
                    )
                    invoice.linked_dns.add(dn)
                    dn.linked_invoice = invoice
                    dn.status = "invoiced"
                    dn.save()
                except ClientDN.DoesNotExist:
                    pass
            if linked_dn_ids:
                invoice.save()

            # §23.4 (planned): consume any unused ClientAdvance for this
            # client automatically, oldest first — the invoice can already
            # be born Paid/Partially Paid before any new encaissement is
            # ever recorded against it.
            from .utils import consume_client_advances_fifo

            consume_client_advances_fifo(invoice)

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="sales",
                instance=invoice,
                request=request,
            )
            messages.success(request, f"Facture {invoice.reference} créée avec succès")
            return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    else:
        form = ClientInvoiceForm()
        doc_form = ClientSupportingDocForm(entity_type="invoice")
    return render(
        request,
        "sales/client_invoice_form.html",
        {"form": form, "doc_form": doc_form, "title": "Nouvelle facture client"},
    )


@login_required
def client_invoice_detail(request, invoice_id):
    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    role = request.user.userprofile.role
    payments = invoice.payments.all()

    # "Documents justificatifs" gathers attachments from the invoice itself
    # AND from each of its payments (encaissements) — a doc attached while
    # recording a payment previously vanished from this page since only
    # invoice.pieces_jointes was queried. Each doc is tagged with its
    # source record so the table can show where it came from.
    supporting_docs = list(
        invoice.pieces_jointes.select_related("uploaded_by").order_by("-created_at")
    )
    for doc in supporting_docs:
        doc.source_label = f"Facture {invoice.reference}"
    for p in payments:
        payment_docs = list(
            p.pieces_jointes.select_related("uploaded_by").order_by("-created_at")
        )
        for doc in payment_docs:
            doc.source_label = f"Encaissement {p.reference}"
        supporting_docs.extend(payment_docs)
        p.has_supporting_doc = bool(payment_docs)
    supporting_docs.sort(key=lambda d: d.created_at, reverse=True)

    return render(
        request,
        "sales/client_invoice_detail.html",
        {
            "invoice": invoice,
            "linked_dns": invoice.linked_dns.all(),
            "payments": payments,
            "supporting_docs": supporting_docs,
            "can_collect": (
                role in ["manager", "accountant"]
                and invoice.balance_due > 0
                and invoice.status not in ["cancelled", "in_dispute"]
            ),
            "title": f"Facture Client - {invoice.reference}",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def client_invoice_add_document(request, invoice_id):
    """Attach a PieceJointe to a ClientInvoice (mirrors supplier_invoice_add_document)."""
    invoice = get_object_or_404(ClientInvoice, pk=invoice_id)
    if request.method == "POST":
        form = ClientSupportingDocForm(
            request.POST, request.FILES, entity_type="invoice"
        )
        if form.is_valid():
            from core.models import PieceJointe

            PieceJointe.objects.create(
                content_object=invoice,
                type_document=form.cleaned_data["doc_type"],
                description=form.cleaned_data["description"],
                fichier=form.cleaned_data.get("file"),
                uploaded_by=request.user,
            )
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="sales",
                instance=invoice,
                details={"document_added": form.cleaned_data["doc_type"]},
                request=request,
            )
            messages.success(request, "Document justificatif ajouté avec succès.")
            return redirect("sales:client_invoice_detail", invoice_id=invoice.pk)
    else:
        form = ClientSupportingDocForm(entity_type="invoice")
    return render(
        request,
        "sales/client_invoice_add_document.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Ajouter un justificatif — {invoice.reference}",
        },
    )


@login_required
@require_POST
def client_invoice_change_status(request, invoice_id):
    """
    Manager: force any valid status via select + guided buttons.
    Others: guided transition to allowed next states only.
    """
    from django.core.exceptions import ValidationError

    invoice = get_object_or_404(ClientInvoice, pk=invoice_id)
    role = request.user.userprofile.role
    new_status = request.POST.get("new_status", "").strip()

    if not new_status:
        messages.error(request, "Statut cible manquant.")
        return redirect("sales:client_invoice_detail", invoice_id=invoice_id)

    allowed = ClientInvoice.VALID_TRANSITIONS.get(invoice.status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Transition invalide : {invoice.get_status_display()} → {new_status}.",
        )
        return redirect("sales:client_invoice_detail", invoice_id=invoice_id)

    if role != "manager" and new_status not in allowed[:1]:
        messages.error(
            request, "Vous n'avez pas la permission d'effectuer cette transition."
        )
        return redirect("sales:client_invoice_detail", invoice_id=invoice_id)

    try:
        invoice.transition_to(new_status, request.user)
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="sales",
            instance=invoice,
            details={"status_change": new_status},
            request=request,
        )
        messages.success(
            request,
            f"Statut de la facture {invoice.reference} mis à jour : {invoice.get_status_display()}.",
        )
    except ValidationError as e:
        messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("sales:client_invoice_detail", invoice_id=invoice_id)


@login_required
@role_required(["manager", "accountant"])
def client_payment_create(request, invoice_id):
    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    if invoice.balance_due <= 0:
        messages.error(request, "Cette facture est déjà entièrement payée")
        return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    if request.method == "POST":
        form = ClientPaymentForm(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            ClientSupportingDocForm(
                request.POST, request.FILES, entity_type="payment"
            )
            if request.FILES.get("file")
            else None
        )
        if form.is_valid() and (doc_form is None or doc_form.is_valid()):
            payment = form.save(commit=False)
            payment.client_invoice = invoice
            payment.client = invoice.client
            payment.recorded_by = request.user
            if payment.amount > invoice.balance_due:
                messages.error(request, "Le montant ne peut pas dépasser le solde dû")
                return render(
                    request,
                    "sales/client_payment_form.html",
                    {
                        "form": form,
                        "doc_form": doc_form,
                        "invoice": invoice,
                        "title": f"Encaissement - {invoice.reference}",
                    },
                )
            payment.save()
            if doc_form is not None:
                from core.models import PieceJointe

                PieceJointe.objects.create(
                    content_object=payment,
                    type_document=doc_form.cleaned_data["doc_type"],
                    description=doc_form.cleaned_data["description"],
                    fichier=doc_form.cleaned_data.get("file"),
                    uploaded_by=request.user,
                )
            AuditLog.log_action(
                user=request.user,
                action_type="pay",
                module="sales",
                instance=payment,
                details={"invoice": invoice.reference, "amount": str(payment.amount)},
                request=request,
            )
            messages.success(request, f"Encaissement {payment.reference} enregistré")
            return redirect("sales:client_invoice_detail", invoice_id=invoice.id)
    else:
        form = ClientPaymentForm(initial={"amount": invoice.balance_due})
        doc_form = ClientSupportingDocForm(entity_type="payment")
    return render(
        request,
        "sales/client_payment_form.html",
        {
            "form": form,
            "doc_form": doc_form,
            "invoice": invoice,
            "title": f"Encaissement - {invoice.reference}",
        },
    )


@login_required
def client_dn_print(request, dn_id):
    from core.models import CompanyInformation

    dn = get_object_or_404(ClientDN, id=dn_id)
    company = CompanyInformation.objects.first()
    lines = dn.lines.select_related("finished_product", "unit_of_measure").all()
    gross_ht = sum(line.line_amount for line in lines)
    discount_amount = gross_ht - dn.total_ht
    return render(
        request,
        "sales/client_dn_print.html",
        {
            "dn": dn,
            "lines": lines,
            "company": company,
            "gross_ht": gross_ht,
            "discount_amount": discount_amount,
        },
    )


@login_required
def client_invoice_print(request, invoice_id):
    from core.models import CompanyInformation

    invoice = get_object_or_404(ClientInvoice, id=invoice_id)
    company = CompanyInformation.objects.first()
    return render(
        request,
        "sales/client_invoice_print.html",
        {
            "invoice": invoice,
            "linked_dns": invoice.linked_dns.all(),
            "company": company,
        },
    )


@login_required
def client_payment_receipt_print(request, payment_id):
    payment = get_object_or_404(ClientPayment, id=payment_id)
    return render(
        request, "sales/client_payment_receipt_print.html", {"payment": payment}
    )


"""
Replacement for the sales_dashboard view in sales/views.py.
Paste this function in place of the existing sales_dashboard view.
Also add these imports at the top of views.py if not already present:

    import json
    from datetime import date, timedelta
    from django.db.models import Sum, Count, Q
    from django.db.models.functions import TruncMonth
"""


@login_required
def sales_dashboard(request):
    today = timezone.now().date()

    # ── Date range ──────────────────────────────────────────────────────────
    # Defaults: first day of current month → today
    default_from = today.replace(day=1)
    default_to = today

    try:
        date_from = date.fromisoformat(request.GET.get("date_from", ""))
    except (ValueError, TypeError):
        date_from = default_from

    try:
        date_to = date.fromisoformat(request.GET.get("date_to", ""))
    except (ValueError, TypeError):
        date_to = default_to

    if date_from > date_to:
        date_from, date_to = date_to, date_from

    # ── Quick-range shortcuts ────────────────────────────────────────────────
    quick = request.GET.get("quick")
    if quick == "7d":
        date_from, date_to = today - timedelta(days=6), today
    elif quick == "30d":
        date_from, date_to = today - timedelta(days=29), today
    elif quick == "90d":
        date_from, date_to = today - timedelta(days=89), today
    elif quick == "ytd":
        date_from, date_to = today.replace(month=1, day=1), today
    elif quick == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        date_from = last_prev.replace(day=1)
        date_to = last_prev

    # ── Import models (lazy to avoid circular imports) ───────────────────────
    from .models import ClientDN, ClientInvoice, ClientPayment

    # ── KPIs (within selected range) ────────────────────────────────────────
    invoices_qs = ClientInvoice.objects.filter(
        invoice_date__gte=date_from, invoice_date__lte=date_to
    )
    payments_qs = ClientPayment.objects.filter(
        payment_date__gte=date_from, payment_date__lte=date_to
    )
    dns_qs = ClientDN.objects.filter(
        delivery_date__gte=date_from, delivery_date__lte=date_to
    )

    total_invoiced = invoices_qs.aggregate(t=Sum("total_ttc"))["t"] or Decimal("0")
    total_collected = payments_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    invoice_count = invoices_qs.count()
    dn_count = dns_qs.count()
    payment_count = payments_qs.count()

    # Always global (not range-filtered)
    outstanding_receivables = ClientInvoice.objects.filter(balance_due__gt=0).aggregate(
        t=Sum("balance_due")
    )["t"] or Decimal("0")
    overdue_qs = ClientInvoice.objects.filter(
        due_date__lt=today, balance_due__gt=0
    ).select_related("client")
    overdue_amount = overdue_qs.aggregate(t=Sum("balance_due"))["t"] or Decimal("0")
    overdue_count = overdue_qs.count()

    collection_rate = (
        round(float(total_collected) / float(total_invoiced) * 100, 1)
        if total_invoiced > 0
        else 0.0
    )

    # ── Chart 1: Monthly revenue vs collections (last 12 months) ─────────────
    twelve_months_ago = today.replace(day=1) - timedelta(days=335)
    monthly_invoiced_raw = (
        ClientInvoice.objects.filter(invoice_date__gte=twelve_months_ago)
        .annotate(month=TruncMonth("invoice_date"))
        .values("month")
        .annotate(total=Sum("total_ttc"))
        .order_by("month")
    )
    monthly_collected_raw = (
        ClientPayment.objects.filter(payment_date__gte=twelve_months_ago)
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    # Build a unified month index (last 12 months)
    month_labels = []
    cur = twelve_months_ago.replace(day=1)
    while cur <= today.replace(day=1):
        month_labels.append(cur.strftime("%b %Y"))
        # advance one month safely (always on day=1)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1, day=1)
        else:
            cur = cur.replace(month=cur.month + 1, day=1)

    invoiced_by_month = {
        r["month"].strftime("%b %Y"): float(r["total"]) for r in monthly_invoiced_raw
    }
    collected_by_month = {
        r["month"].strftime("%b %Y"): float(r["total"]) for r in monthly_collected_raw
    }

    revenue_chart = {
        "labels": month_labels,
        "invoiced": [invoiced_by_month.get(m, 0) for m in month_labels],
        "collected": [collected_by_month.get(m, 0) for m in month_labels],
    }

    # ── Chart 2: Invoice status breakdown (within range) ─────────────────────
    status_raw = (
        invoices_qs.values("status")
        .annotate(count=Count("id"), total=Sum("total_ttc"))
        .order_by("-total")
    )
    STATUS_LABELS = {
        "issued": "Émise",
        "partially_paid": "Part. payée",
        "paid": "Payée",
        "in_dispute": "En litige",
        "cancelled": "Annulée",
    }
    invoice_status_chart = {
        "labels": [STATUS_LABELS.get(r["status"], r["status"]) for r in status_raw],
        "counts": [r["count"] for r in status_raw],
        "totals": [float(r["total"] or 0) for r in status_raw],
    }

    # ── Chart 3: Top 10 clients by invoiced TTC (within range) ──────────────
    top_clients_raw = (
        invoices_qs.values("client__raison_sociale", "client__code")
        .annotate(total=Sum("total_ttc"))
        .order_by("-total")[:10]
    )
    top_clients_chart = {
        "labels": [r["client__code"] for r in top_clients_raw],
        "full_names": [r["client__raison_sociale"] for r in top_clients_raw],
        "totals": [float(r["total"] or 0) for r in top_clients_raw],
    }

    # ── Chart 4: Payment methods (within range) ──────────────────────────────
    pay_method_raw = (
        payments_qs.values("payment_method")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("-total")
    )
    METHOD_LABELS = {
        "cash": "Espèces",
        "transfer": "Virement",
        "cheque": "Chèque",
        "bill": "Effet",
        "card": "Carte",
    }
    payment_method_chart = {
        "labels": [
            METHOD_LABELS.get(r["payment_method"], r["payment_method"])
            for r in pay_method_raw
        ],
        "counts": [r["count"] for r in pay_method_raw],
        "totals": [float(r["total"] or 0) for r in pay_method_raw],
    }

    # ── Chart 5: DN status breakdown (within range) ──────────────────────────
    dn_status_raw = (
        dns_qs.values("status").annotate(count=Count("id")).order_by("-count")
    )
    DN_STATUS_LABELS = {
        "draft": "Brouillon",
        "validated": "Validé",
        "delivered": "Livré",
        "invoiced": "Facturé",
        "cancelled": "Annulé",
    }
    dn_status_chart = {
        "labels": [
            DN_STATUS_LABELS.get(r["status"], r["status"]) for r in dn_status_raw
        ],
        "counts": [r["count"] for r in dn_status_raw],
    }

    # ── Recent activity tables ───────────────────────────────────────────────
    recent_dns = dns_qs.select_related("client", "validated_by").order_by(
        "-delivery_date"
    )[:15]
    recent_invoices = invoices_qs.select_related("client").order_by("-invoice_date")[
        :15
    ]
    recent_payments = payments_qs.select_related("client", "client_invoice").order_by(
        "-payment_date"
    )[:15]

    # ── Overdue aging buckets (global) ───────────────────────────────────────
    aging = {
        "0_30": Decimal(0),
        "31_60": Decimal(0),
        "61_90": Decimal(0),
        "90_plus": Decimal(0),
    }
    for inv in overdue_qs:
        days = inv.days_overdue()
        if days <= 30:
            aging["0_30"] += inv.balance_due
        elif days <= 60:
            aging["31_60"] += inv.balance_due
        elif days <= 90:
            aging["61_90"] += inv.balance_due
        else:
            aging["90_plus"] += inv.balance_due

    aging_chart = {
        "labels": ["1-30 j", "31-60 j", "61-90 j", "90+ j"],
        "totals": [
            float(aging["0_30"]),
            float(aging["31_60"]),
            float(aging["61_90"]),
            float(aging["90_plus"]),
        ],
    }

    return render(
        request,
        "sales/sales_dashboard.html",
        {
            "title": "Tableau de bord commercial",
            # Filters
            "date_from": date_from,
            "date_to": date_to,
            "quick": quick or "",
            # KPIs
            "total_invoiced": total_invoiced,
            "total_collected": total_collected,
            "outstanding_receivables": outstanding_receivables,
            "overdue_amount": overdue_amount,
            "overdue_count": overdue_count,
            "invoice_count": invoice_count,
            "dn_count": dn_count,
            "payment_count": payment_count,
            "collection_rate": collection_rate,
            # Charts (as JSON strings)
            "revenue_chart_json": json.dumps(revenue_chart),
            "invoice_status_chart_json": json.dumps(invoice_status_chart),
            "top_clients_chart_json": json.dumps(top_clients_chart),
            "payment_method_chart_json": json.dumps(payment_method_chart),
            "dn_status_chart_json": json.dumps(dn_status_chart),
            "aging_chart_json": json.dumps(aging_chart),
            # Tables
            "overdue_invoices": overdue_qs.order_by("due_date")[:20],
            "recent_dns": recent_dns,
            "recent_invoices": recent_invoices,
            "recent_payments": recent_payments,
        },
    )


@login_required
@role_required(["manager", "accountant"])
def client_account_settlement(request, client_id):
    """
    Record a payment against a client account and apply FIFO invoice clearing.
    POST /sales/clients/<client_id>/settle/
    """
    from clients.models import Client
    from .models import ClientAccountPayment
    from django.db import transaction

    client = get_object_or_404(Client, pk=client_id, is_active=True)

    open_invoices = (
        ClientInvoice.objects.filter(
            client=client,
            balance_due__gt=0,
        )
        .exclude(status__in=["in_dispute", "cancelled", "paid"])
        .order_by("due_date", "invoice_date")
    )
    total_outstanding = sum(inv.balance_due for inv in open_invoices)

    if request.method == "POST":
        form = ClientAccountPaymentForm(request.POST)
        if form.is_valid():
            # §23.4 (planned): an amount above total_outstanding is now
            # accepted — settle_fifo() clears every open invoice and
            # automatically records the surplus as a ClientAdvance.
            try:
                with transaction.atomic():
                    settlement = form.save(commit=False)
                    settlement.client = client
                    settlement.recorded_by = request.user
                    settlement.save()
                    applied = settlement.settle_fifo()

                AuditLog.log_action(
                    user=request.user,
                    action_type="pay",
                    module="sales",
                    instance=settlement,
                    details={
                        "client": client.code,
                        "amount": str(settlement.amount),
                        "invoices_cleared": len(applied),
                    },
                    request=request,
                )
                invoices_str = ", ".join(
                    f"{r['invoice'].reference} ({r['applied']} DA)" for r in applied
                )
                surplus = settlement.amount - sum(r["applied"] for r in applied)
                success_msg = (
                    f"Règlement {settlement.reference} enregistré. "
                    f"Factures soldées : {invoices_str or '—'}"
                )
                if surplus > 0:
                    success_msg += (
                        f" Surplus de {surplus} DA enregistré comme avance "
                        f"client (§23 planifié)."
                    )
                messages.success(request, success_msg)
                return redirect("clients:client_detail", client_id=client.id)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = ClientAccountPaymentForm(initial={"amount": total_outstanding})

    return render(
        request,
        "sales/client_account_settlement.html",
        {
            "client": client,
            "form": form,
            "open_invoices": open_invoices,
            "total_outstanding": total_outstanding,
            "title": f"Régler le compte — {client.raison_sociale}",
        },
    )


@login_required
def finished_product_info(request, product_id):
    """AJAX: return sales_unit and reference_selling_price for a finished product."""
    from django.http import JsonResponse
    from catalog.models import FinishedProduct

    product = get_object_or_404(FinishedProduct, id=product_id, is_active=True)
    return JsonResponse(
        {
            "unit_id": product.sales_unit_id,
            "unit_symbol": product.sales_unit.symbol if product.sales_unit else "",
            "reference_price": str(product.reference_selling_price),
        }
    )


# ---------------------------------------------------------------------------
# §23 (planned) — Client Advance (direct entry), Opening Balance,
# Statement of Account
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant"])
def client_advance_create(request, client_id):
    """§23.4 — direct-entry Client Advance, independent of any settlement."""
    from django.db.models import Sum
    from clients.models import Client
    from .models import ClientAdvance
    from .forms import ClientAdvanceForm

    client = get_object_or_404(Client, pk=client_id, is_active=True)
    available_advance_total = ClientAdvance.objects.filter(
        client=client, remaining_amount__gt=0
    ).aggregate(total=Sum("remaining_amount"))["total"] or 0

    if request.method == "POST":
        form = ClientAdvanceForm(request.POST)
        if form.is_valid():
            advance = form.save(commit=False)
            advance.client = client
            advance.origin = ClientAdvance.ORIGIN_DIRECT_ENTRY
            advance.recorded_by = request.user
            advance.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="sales",
                instance=advance,
                details={"client": client.code, "amount": str(advance.amount)},
                request=request,
            )
            messages.success(
                request,
                f"Avance {advance.reference} de {advance.amount} DA enregistrée "
                f"pour {client.raison_sociale} (§23 planifié).",
            )
            return redirect("clients:client_detail", client_id=client.id)
    else:
        form = ClientAdvanceForm(initial={"date": timezone.now().date()})

    return render(
        request,
        "sales/client_advance_form.html",
        {
            "form": form,
            "client": client,
            "available_advance_total": available_advance_total,
            "title": f"Enregistrer une avance — {client.raison_sociale}",
        },
    )


@login_required
@role_required(["manager"])
def client_opening_balance_create(request, client_id):
    """§23.5 — ADMIN-ONLY opening balance entry."""
    from django.db.models import Sum
    from clients.models import Client
    from .models import ClientAdvance
    from .forms import ClientOpeningBalanceForm
    from .utils import create_client_opening_balance

    client = get_object_or_404(Client, pk=client_id, is_active=True)
    available_advance_total = ClientAdvance.objects.filter(
        client=client, remaining_amount__gt=0
    ).aggregate(total=Sum("remaining_amount"))["total"] or 0

    if request.method == "POST":
        form = ClientOpeningBalanceForm(request.POST)
        if form.is_valid():
            try:
                invoice = create_client_opening_balance(
                    client=client,
                    amount=form.cleaned_data["amount"],
                    motif=form.cleaned_data["motif"],
                    reference_date=form.cleaned_data.get("reference_date"),
                    due_date=form.cleaned_data.get("due_date"),
                    created_by=request.user,
                )
            except ValueError as e:
                messages.error(request, str(e))
            else:
                AuditLog.log_action(
                    user=request.user,
                    action_type="create",
                    module="sales",
                    instance=invoice,
                    details={
                        "client": client.code,
                        "amount": str(invoice.total_net),
                        "opening_balance": True,
                    },
                    request=request,
                )
                messages.success(
                    request,
                    f"Solde d'ouverture {invoice.reference} enregistré pour "
                    f"{client.raison_sociale} (§23 planifié).",
                )
                return redirect("clients:client_detail", client_id=client.id)
    else:
        form = ClientOpeningBalanceForm(
            initial={"reference_date": timezone.now().date()}
        )

    return render(
        request,
        "sales/client_opening_balance_form.html",
        {
            "form": form,
            "client": client,
            "available_advance_total": available_advance_total,
            "title": f"Solde d'ouverture — {client.raison_sociale}",
        },
    )


@login_required
def client_statement(request, client_id):
    """§23.6 — chronological, running-balance statement of account."""
    from clients.models import Client
    from .utils import get_client_statement

    client = get_object_or_404(Client, pk=client_id, is_active=True)

    date_start = request.GET.get("date_start") or None
    date_end = request.GET.get("date_end") or None
    if date_start:
        date_start = timezone.datetime.strptime(date_start, "%Y-%m-%d").date()
    if date_end:
        date_end = timezone.datetime.strptime(date_end, "%Y-%m-%d").date()

    statement = get_client_statement(client, date_start=date_start, date_end=date_end)

    return render(
        request,
        "sales/client_statement.html",
        {
            "client": client,
            "statement": statement,
            "date_start": date_start,
            "date_end": date_end,
            "title": f"Relevé de compte — {client.raison_sociale}",
        },
    )
