# supplier_ops/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from accounts.utils import role_required
from accounts.models import AuditLog
from core.models import ProductionSite
from core.utils import get_default_site, remember_site, site_filter_kwargs
from expenses.models import Expense
from .models import (
    SupplierDN,
    SupplierInvoice,
)
from catalog.models import RawMaterialCategory, UnitOfMeasure
from suppliers.models import Supplier
from .forms import (
    SupplierDNForm,
    SupplierDNLineFormSet,
    SupplierInvoiceForm,
    SupplierInvoiceLineFormSet,
    SupplierPaymentForm,
    SupplierSupportingDocForm,
)


@login_required
def supplier_dns_list(request):
    dns = SupplierDN.objects.select_related("supplier", "validated_by", "site").filter(
        **site_filter_kwargs(request)
    )

    search = request.GET.get("search")
    if search:
        dns = dns.filter(
            Q(reference__icontains=search)
            | Q(external_reference__icontains=search)
            | Q(supplier__raison_sociale__icontains=search)
        )

    status_filter = request.GET.get("status")
    if status_filter:
        dns = dns.filter(status=status_filter)

    supplier_filter = request.GET.get("supplier")
    if supplier_filter:
        dns = dns.filter(supplier_id=supplier_filter)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        dns = dns.filter(delivery_date__gte=date_from)
    if date_to:
        dns = dns.filter(delivery_date__lte=date_to)

    return render(
        request,
        "supplier_ops/supplier_dns_list.html",
        {
            "dns": dns.order_by("-delivery_date"),
            "status_choices": SupplierDN.STATUS_CHOICES,
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Bons de livraison fournisseurs",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def supplier_dn_create(request):
    if request.method == "POST":
        form = SupplierDNForm(request.POST)
        formset = SupplierDNLineFormSet(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            SupplierSupportingDocForm(request.POST, request.FILES, entity_type="dn")
            if request.FILES.get("file")
            else None
        )
        if (
            form.is_valid()
            and formset.is_valid()
            and (doc_form is None or doc_form.is_valid())
        ):
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            formset.instance = dn
            formset.save()
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
                module="supplier_ops",
                instance=dn,
                request=request,
            )
            remember_site(request, dn.site)
            messages.success(request, f"BL Fournisseur {dn.reference} créé avec succès")
            return redirect("supplier_ops:supplier_dn_detail", dn_id=dn.id)
    else:
        form = SupplierDNForm(initial_site=get_default_site(request))
        formset = SupplierDNLineFormSet()
        doc_form = SupplierSupportingDocForm(entity_type="dn")

    return render(
        request,
        "supplier_ops/supplier_dn_form.html",
        {
            "form": form,
            "formset": formset,
            "doc_form": doc_form,
            "title": "Nouveau BL Fournisseur",
            "rm_categories": RawMaterialCategory.objects.filter(is_active=True),
            "uom_choices": UnitOfMeasure.objects.filter(is_active=True),
            "active_suppliers": Supplier.objects.filter(is_active=True),
        },
    )


@login_required
def supplier_dn_detail(request, dn_id):
    dn = get_object_or_404(SupplierDN, id=dn_id)

    supporting_docs = dn.pieces_jointes.select_related("uploaded_by").order_by(
        "-created_at"
    )
    gate_a_line_ids = {line.id for line in dn.gate_a_lines()}
    return render(
        request,
        "supplier_ops/supplier_dn_detail.html",
        {
            "dn": dn,
            "lines": dn.lines.select_related("raw_material", "unit_of_measure").all(),
            "supporting_docs": supporting_docs,
            "can_validate": (
                request.user.userprofile.role in ["manager", "stock_prod"]
                and dn.status in ("pending", "qc_passed")
            ),
            "title": f"BL Fournisseur - {dn.reference}",
            # --- QA/QC Gate A context ---
            "gate_a_line_ids": gate_a_line_ids,
            "can_draw_gate_a_sample": (
                request.user.userprofile.can_perform_qc()
                and dn.status == "pending_qc_sampling"
            ),
            "can_release_gate_a": (
                request.user.userprofile.can_release_gate_a()
                and dn.status == "pending_qc_sampling"
                and dn.gate_a_clear()
            ),
        },
    )


# require post import for supplier_dn_validate


@login_required
@require_POST
def supplier_dn_qc_release(request, dn_id):
    """QA/QC Gate A (§4.2 Step 5c): move a DN from Pending QC Sampling to
    QC Passed (or Rejected — Returned) once all flagged lines have results."""
    dn = get_object_or_404(SupplierDN, pk=dn_id)
    if not request.user.userprofile.can_release_gate_a():
        messages.error(request, "Vous n'avez pas la permission de libérer le contrôle QC.")
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    try:
        dn.qc_release(request.user)
        if dn.status == "rejected_returned":
            messages.warning(
                request, f"BL {dn.reference} rejeté — retour fournisseur (toutes les lignes ont échoué)."
            )
        else:
            messages.success(request, f"BL {dn.reference} : QC validé, prêt pour validation stock.")
    except ValidationError as e:
        messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)



@login_required
@require_POST
def supplier_dn_validate(request, dn_id):
    dn = get_object_or_404(SupplierDN, pk=dn_id)

    if request.user.userprofile.role not in ("manager", "accountant"):
        messages.error(request, "Vous n'avez pas la permission de valider un BL.")
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    uploaded_file = request.FILES.get("sd_dnf_file")
    if uploaded_file:
        from core.models import PieceJointe

        PieceJointe.objects.create(
            content_object=dn,
            type_document=PieceJointe.TYPE_SD_DNF,
            description=f"Justificatif BL {dn.reference} — {uploaded_file.name}",
            fichier=uploaded_file,
            uploaded_by=request.user,
        )

    try:
        dn.validate(request.user)
        messages.success(request, f"Le BL {dn.reference} a été validé avec succès.")
    except ValidationError as e:
        messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)


@login_required
def supplier_invoices_list(request):
    invoices = SupplierInvoice.objects.select_related("supplier").all()

    search = request.GET.get("search")
    if search:
        invoices = invoices.filter(
            Q(reference__icontains=search)
            | Q(external_reference__icontains=search)
            | Q(supplier__raison_sociale__icontains=search)
        )

    status_filter = request.GET.get("status")
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    if request.GET.get("overdue") == "true":
        invoices = invoices.filter(
            due_date__lt=timezone.now().date(), balance_due__gt=0
        )

    return render(
        request,
        "supplier_ops/supplier_invoices_list.html",
        {
            "invoices": invoices.order_by("-invoice_date"),
            "status_choices": SupplierInvoice.STATUS_CHOICES,
            "title": "Factures fournisseurs",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_invoice_create(request):
    if request.method == "POST":
        form = SupplierInvoiceForm(request.POST)
        linked_dn_ids = request.POST.getlist("linked_dns")

        # Build formset only if explicit line data was posted (new template
        # pre-fills via JS; fallback allows server-side line creation from DNs)
        formset = SupplierInvoiceLineFormSet(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            SupplierSupportingDocForm(
                request.POST, request.FILES, entity_type="invoice"
            )
            if request.FILES.get("file")
            else None
        )

        if form.is_valid():
            has_formset_lines = any(
                request.POST.get(f"lines-{i}-raw_material")
                for i in range(int(request.POST.get("lines-TOTAL_FORMS", 0)))
            )

            if not has_formset_lines and not linked_dn_ids:
                messages.error(
                    request,
                    "Veuillez sélectionner au moins un BL ou saisir une ligne de facture.",
                )
            elif has_formset_lines and not formset.is_valid():
                pass  # fall through to re-render with errors
            elif doc_form is not None and not doc_form.is_valid():
                pass  # fall through to re-render with errors
            else:
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

                if has_formset_lines:
                    formset.instance = invoice
                    formset.save()
                else:
                    # Server-side aggregation from selected DNs
                    from collections import defaultdict
                    from .models import SupplierInvoiceLine

                    agg = defaultdict(
                        lambda: {"qty": 0, "price": None, "designation": ""}
                    )
                    for dn_id in linked_dn_ids:
                        try:
                            dn = SupplierDN.objects.get(pk=dn_id, status="validated")
                            for line in dn.lines.select_related("raw_material").all():
                                rm_id = line.raw_material_id
                                agg[rm_id]["qty"] += line.quantity_received
                                # last DN price wins (template JS does same)
                                agg[rm_id]["price"] = line.agreed_unit_price
                                agg[rm_id][
                                    "designation"
                                ] = line.raw_material.designation
                        except SupplierDN.DoesNotExist:
                            pass

                    for rm_id, vals in agg.items():
                        SupplierInvoiceLine.objects.create(
                            supplier_invoice=invoice,
                            raw_material_id=rm_id,
                            designation=vals["designation"],
                            quantity_invoiced=vals["qty"],
                            unit_price_invoiced=vals["price"],
                        )

                # Link DNs to invoice
                for dn_id in linked_dn_ids:
                    try:
                        dn = SupplierDN.objects.get(pk=dn_id, status="validated")
                        invoice.linked_dns.add(dn)
                    except SupplierDN.DoesNotExist:
                        pass

                # §23.3.3 (planned): consume any unused SupplierAdvance for
                # this supplier automatically, oldest first — the invoice
                # can already be born Paid/Partially Paid before any new
                # règlement is ever recorded against it.
                from .utils import consume_supplier_advances_fifo

                consume_supplier_advances_fifo(invoice)

                AuditLog.log_action(
                    user=request.user,
                    action_type="create",
                    module="supplier_ops",
                    instance=invoice,
                    request=request,
                )
                messages.success(
                    request, f"Facture {invoice.reference} créée avec succès"
                )
                return redirect(
                    "supplier_ops:supplier_invoice_detail", invoice_id=invoice.id
                )
    else:
        form = SupplierInvoiceForm()
        formset = SupplierInvoiceLineFormSet()
        doc_form = SupplierSupportingDocForm(entity_type="invoice")

    return render(
        request,
        "supplier_ops/supplier_invoice_form.html",
        {
            "form": form,
            "formset": formset,
            "doc_form": doc_form,
            "title": "Nouvelle facture fournisseur",
        },
    )


@login_required
def supplier_invoice_detail(request, invoice_id):
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    payments = invoice.payments.all()

    # "Documents justificatifs" gathers attachments from the invoice itself
    # AND from each of its payments (règlements) — a doc attached while
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
            doc.source_label = f"Paiement {p.reference}"
        supporting_docs.extend(payment_docs)
        p.has_supporting_doc = bool(payment_docs)
    supporting_docs.sort(key=lambda d: d.created_at, reverse=True)

    return render(
        request,
        "supplier_ops/supplier_invoice_detail.html",
        {
            "invoice": invoice,
            "lines": invoice.lines.select_related("raw_material").all(),
            "payments": payments,
            "linked_dns": invoice.linked_dns.all(),
            "supporting_docs": supporting_docs,
            "can_pay": (
                request.user.userprofile.role in ["manager", "accountant"]
                and invoice.status in ["verified", "unpaid", "partially_paid"]
                and invoice.balance_due > 0
            ),
            "title": f"Facture Fournisseur - {invoice.reference}",
            "can_settle": (
                invoice.balance_due > 0
                and invoice.status not in ("cancelled", "in_dispute")
                and request.user.userprofile.role in ["manager", "accountant"]
            ),
            "can_link_expense": (
                invoice.status in ["verified", "unpaid", "partially_paid"]
                and request.user.userprofile.role in ["manager", "accountant"]
            ),
            "linked_expense": Expense.objects.filter(
                linked_supplier_invoice=invoice
            ).first(),
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_payment_create(request, invoice_id):
    """
    FIX: added explicit in_dispute check at the view layer (BR-INV-04).
    The model's clean() also enforces this, but the spec requires it in
    both layers.  Checking here lets us show a clear user-facing message
    before the form is even rendered.
    """
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)

    # BR-INV-04: hard gate — view layer
    if invoice.status == "in_dispute":
        messages.error(
            request,
            "Impossible d'enregistrer un paiement : la facture est en litige (BR-INV-04). "
            "Le litige doit être résolu par le Manager avant tout paiement.",
        )
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice.id)

    if invoice.balance_due <= 0:
        messages.error(request, "Cette facture est déjà entièrement payée")
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice.id)

    if request.method == "POST":
        form = SupplierPaymentForm(request.POST)
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            SupplierSupportingDocForm(
                request.POST, request.FILES, entity_type="payment"
            )
            if request.FILES.get("file")
            else None
        )
        if form.is_valid() and (doc_form is None or doc_form.is_valid()):
            payment = form.save(commit=False)
            payment.supplier_invoice = invoice
            payment.supplier = invoice.supplier
            payment.recorded_by = request.user

            if payment.amount > invoice.balance_due:
                messages.error(
                    request, "Le montant du paiement ne peut pas dépasser le solde dû"
                )
                return render(
                    request,
                    "supplier_ops/supplier_payment_form.html",
                    {
                        "form": form,
                        "doc_form": doc_form,
                        "invoice": invoice,
                        "title": f"Paiement - {invoice.reference}",
                    },
                )

            try:
                payment.save()  # model clean() re-checks in_dispute
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
                return render(
                    request,
                    "supplier_ops/supplier_payment_form.html",
                    {
                        "form": form,
                        "doc_form": doc_form,
                        "invoice": invoice,
                        "title": f"Paiement - {invoice.reference}",
                    },
                )

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
                module="supplier_ops",
                instance=payment,
                details={"invoice": invoice.reference, "amount": str(payment.amount)},
                request=request,
            )
            messages.success(
                request, f"Paiement {payment.reference} enregistré avec succès"
            )
            return redirect(
                "supplier_ops:supplier_invoice_detail", invoice_id=invoice.id
            )
    else:
        form = SupplierPaymentForm(initial={"amount": invoice.balance_due})
        doc_form = SupplierSupportingDocForm(entity_type="payment")

    return render(
        request,
        "supplier_ops/supplier_payment_form.html",
        {
            "form": form,
            "doc_form": doc_form,
            "invoice": invoice,
            "title": f"Paiement - {invoice.reference}",
        },
    )


@login_required
@role_required(["manager", "accountant", "stock_prod"])
def supplier_dn_add_document(request, dn_id):
    """Attach a SupportingDocument to a SupplierDN."""
    dn = get_object_or_404(SupplierDN, pk=dn_id)
    if request.method == "POST":
        form = SupplierSupportingDocForm(request.POST, request.FILES, entity_type="dn")
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
                module="supplier_ops",
                instance=dn,
                details={"document_added": form.cleaned_data["doc_type"]},
                request=request,
            )
            messages.success(request, "Document justificatif ajouté avec succès.")
            return redirect("supplier_ops:supplier_dn_detail", dn_id=dn.pk)
    else:
        form = SupplierSupportingDocForm(entity_type="dn")
    return render(
        request,
        "supplier_ops/supplier_dn_add_document.html",
        {"form": form, "dn": dn, "title": f"Ajouter un justificatif — {dn.reference}"},
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_invoice_add_document(request, invoice_id):
    """Attach a SupportingDocument to a SupplierInvoice."""
    invoice = get_object_or_404(SupplierInvoice, pk=invoice_id)
    if request.method == "POST":
        form = SupplierSupportingDocForm(
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
            if form.cleaned_data["doc_type"] == PieceJointe.TYPE_SD_PAY_F:
                # SPEC BR-AUD-04: proof attached after the balance already
                # reached zero — re-run the gate so status can now flip to
                # "paid" without requiring a second manual action.
                invoice.recompute_balance_due()
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="supplier_ops",
                instance=invoice,
                details={"document_added": form.cleaned_data["doc_type"]},
                request=request,
            )
            messages.success(request, "Document justificatif ajouté avec succès.")
            return redirect(
                "supplier_ops:supplier_invoice_detail", invoice_id=invoice.pk
            )
    else:
        form = SupplierSupportingDocForm(entity_type="invoice")
    return render(
        request,
        "supplier_ops/supplier_invoice_add_document.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Ajouter un justificatif — {invoice.reference}",
        },
    )


@login_required
def supplier_dns_for_supplier(request, supplier_id):
    """
    AJAX — returns validated, unlinked SupplierDNs for a given supplier.
    Used by the invoice creation form to auto-populate invoice lines.
    GET /supplier-ops/ajax/supplier-dns/<supplier_id>/
    """
    supplier = get_object_or_404(Supplier, pk=supplier_id, is_active=True)

    dns = (
        SupplierDN.objects.filter(
            supplier=supplier,
            status="validated",
            linked_invoice__isnull=True,
        )
        .prefetch_related("lines__raw_material__unit_of_measure")
        .order_by("-delivery_date")
    )

    data = []
    for dn in dns:
        lines = []
        for line in dn.lines.all():
            rm = line.raw_material
            lines.append(
                {
                    "raw_material_id": rm.pk,
                    "raw_material_ref": rm.reference,
                    "raw_material_name": str(rm),
                    "quantity_received": str(line.quantity_received),
                    "agreed_unit_price": str(line.agreed_unit_price),
                    "uom_symbol": rm.unit_of_measure.symbol,
                    "amount_ht": str(line.quantity_received * line.agreed_unit_price),
                }
            )
        data.append(
            {
                "id": dn.pk,
                "reference": dn.reference,
                "external_reference": dn.external_reference or "",
                "delivery_date": dn.delivery_date.strftime("%d/%m/%Y"),
                "total_amount_ht": str(dn.total_amount_ht),
                "lines": lines,
            }
        )

    return JsonResponse(
        {"success": True, "dns": data, "supplier_name": supplier.raison_sociale}
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_account_settlement(request, supplier_id):
    """
    Record a payment against a supplier account and apply FIFO invoice clearing.
    POST /supplier-ops/suppliers/<supplier_id>/settle/
    """
    from .models import SupplierAccountPayment, SupplierInvoice
    from .forms import SupplierAccountPaymentForm
    from django.db import transaction

    supplier = get_object_or_404(Supplier, pk=supplier_id, is_active=True)

    open_invoices = (
        SupplierInvoice.objects.filter(
            supplier=supplier,
            balance_due__gt=0,
        )
        .exclude(status__in=["in_dispute", "cancelled", "paid"])
        .order_by("due_date", "invoice_date")
    )
    total_outstanding = sum(inv.balance_due for inv in open_invoices)

    if request.method == "POST":
        form = SupplierAccountPaymentForm(request.POST)
        if form.is_valid():
            # §23.3.4 (planned): Rule 28 previously blocked an amount above
            # total_outstanding here. That hard block is superseded — an
            # amount greater than the outstanding debt is now accepted:
            # settle_fifo() clears every open invoice and automatically
            # records the surplus as a SupplierAdvance (§23.3.2a).
            try:
                with transaction.atomic():
                    settlement = form.save(commit=False)
                    settlement.supplier = supplier
                    settlement.recorded_by = request.user
                    settlement.save()
                    applied = settlement.settle_fifo()

                AuditLog.log_action(
                    user=request.user,
                    action_type="pay",
                    module="supplier_ops",
                    instance=settlement,
                    details={
                        "supplier": supplier.code,
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
                        f"fournisseur (§23 planifié)."
                    )
                messages.success(request, success_msg)
                return redirect(
                    "suppliers:supplier_detail", supplier_id=supplier.id
                )
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = SupplierAccountPaymentForm(initial={"amount": total_outstanding})

    return render(
        request,
        "supplier_ops/supplier_account_settlement.html",
        {
            "supplier": supplier,
            "form": form,
            "open_invoices": open_invoices,
            "total_outstanding": total_outstanding,
            "title": f"Régler le compte — {supplier.raison_sociale}",
        },
    )


@login_required
def supplier_dn_print(request, dn_id):
    dn = get_object_or_404(SupplierDN, id=dn_id)
    return render(
        request,
        "supplier_ops/supplier_dn_print.html",
        {
            "dn": dn,
            "lines": dn.lines.select_related("raw_material", "unit_of_measure").all(),
        },
    )


@login_required
def supplier_invoice_print(request, invoice_id):
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    return render(
        request,
        "supplier_ops/supplier_invoice_print.html",
        {
            "invoice": invoice,
            "lines": invoice.lines.select_related("raw_material").all(),
        },
    )


@login_required
@require_POST
def supplier_dn_change_status(request, dn_id):
    """
    Admin (manager): force any valid status via select.
    Others: guided transition to a single next state.
    """
    dn = get_object_or_404(SupplierDN, pk=dn_id)
    role = request.user.userprofile.role
    new_status = request.POST.get("new_status", "").strip()

    if not new_status:
        messages.error(request, "Statut cible manquant.")
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    allowed = SupplierDN.VALID_TRANSITIONS.get(dn.status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Transition invalide : {dn.get_status_display()} → {new_status}.",
        )
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    # Non-managers can't force arbitrary statuses; they can only go to the
    # first allowed next state (= what the guided button posts).
    if role != "manager" and new_status not in allowed[:1]:
        messages.error(
            request, "Vous n'avez pas la permission d'effectuer cette transition."
        )
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    # Reuse the existing validate() path when transitioning to validated
    if new_status == "validated":
        if role not in ("manager", "accountant"):
            messages.error(request, "Seul un Manager ou Comptable peut valider un BL.")
            return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)
        try:
            dn.validate(request.user)
            messages.success(request, f"BL {dn.reference} validé avec succès.")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    try:
        dn.transition_to(new_status, request.user)
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="supplier_ops",
            instance=dn,
            details={"status_change": new_status},
            request=request,
        )
        messages.success(
            request,
            f"Statut du BL {dn.reference} mis à jour : {dn.get_status_display()}.",
        )
    except ValidationError as e:
        messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)


@login_required
@require_POST
def supplier_invoice_change_status(request, invoice_id):
    """
    Admin (manager): force any valid status via select.
    Others: guided transition to a single next state.
    """
    invoice = get_object_or_404(SupplierInvoice, pk=invoice_id)
    role = request.user.userprofile.role
    new_status = request.POST.get("new_status", "").strip()

    if not new_status:
        messages.error(request, "Statut cible manquant.")
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice_id)

    allowed = SupplierInvoice.VALID_TRANSITIONS.get(invoice.status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Transition invalide : {invoice.get_status_display()} → {new_status}.",
        )
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice_id)

    if role != "manager" and new_status not in allowed[:1]:
        messages.error(
            request, "Vous n'avez pas la permission d'effectuer cette transition."
        )
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice_id)

    # in_dispute resolution restricted to manager
    if new_status == "in_dispute" and role not in ("manager", "accountant"):
        messages.error(
            request, "Seul un Manager ou Comptable peut mettre une facture en litige."
        )
        return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice_id)

    # Optional inline SD-PAY-F upload (mirrors supplier_dn_validate's
    # sd_dnf_file) — lets the user satisfy the BR-AUD-04 gate in the same
    # click instead of a separate "add document" trip. Purely optional:
    # if omitted and no SD-PAY-F is already attached, transition_to() below
    # raises a ValidationError that this view already catches gracefully.
    if new_status == "paid":
        uploaded_file = request.FILES.get("sd_pay_f_file")
        if uploaded_file:
            from core.models import PieceJointe

            PieceJointe.objects.create(
                content_object=invoice,
                type_document=PieceJointe.TYPE_SD_PAY_F,
                description=f"Justificatif paiement facture {invoice.reference} — {uploaded_file.name}",
                fichier=uploaded_file,
                uploaded_by=request.user,
            )

    try:
        invoice.transition_to(new_status, request.user)
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="supplier_ops",
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

    return redirect("supplier_ops:supplier_invoice_detail", invoice_id=invoice_id)


@login_required
@role_required(["manager", "stock_prod"])
def supplier_dn_submit(request, dn_id):
    """Transition draft → pending (submit for validation)."""
    dn = get_object_or_404(SupplierDN, id=dn_id)
    if request.method == "POST":
        try:
            dn.transition_to("pending", request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="supplier_ops",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL {dn.reference} soumis pour validation.")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
    return redirect("supplier_ops:supplier_dn_detail", dn_id=dn.id)


# ---------------------------------------------------------------------------
# §23 (planned) — Supplier Advance (direct entry), Opening Balance,
# Statement of Account
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant"])
def supplier_advance_create(request, supplier_id):
    """§23.3.2b — direct-entry Supplier Advance, independent of any settlement."""
    from django.db.models import Sum
    from .models import SupplierAdvance
    from .forms import SupplierAdvanceForm

    supplier = get_object_or_404(Supplier, pk=supplier_id, is_active=True)
    available_advance_total = SupplierAdvance.objects.filter(
        supplier=supplier, remaining_amount__gt=0
    ).aggregate(total=Sum("remaining_amount"))["total"] or 0

    if request.method == "POST":
        form = SupplierAdvanceForm(request.POST)
        if form.is_valid():
            advance = form.save(commit=False)
            advance.supplier = supplier
            advance.origin = SupplierAdvance.ORIGIN_DIRECT_ENTRY
            advance.recorded_by = request.user
            advance.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="supplier_ops",
                instance=advance,
                details={"supplier": supplier.code, "amount": str(advance.amount)},
                request=request,
            )
            messages.success(
                request,
                f"Avance {advance.reference} de {advance.amount} DA enregistrée "
                f"pour {supplier.raison_sociale} (§23 planifié).",
            )
            return redirect("suppliers:supplier_detail", supplier_id=supplier.id)
    else:
        form = SupplierAdvanceForm(initial={"date": timezone.now().date()})

    return render(
        request,
        "supplier_ops/supplier_advance_form.html",
        {
            "form": form,
            "supplier": supplier,
            "available_advance_total": available_advance_total,
            "title": f"Enregistrer une avance — {supplier.raison_sociale}",
        },
    )


@login_required
@role_required(["manager"])
def supplier_opening_balance_create(request, supplier_id):
    """§23.5 — ADMIN-ONLY opening balance entry."""
    from django.db.models import Sum
    from .models import SupplierAdvance
    from .forms import SupplierOpeningBalanceForm
    from .utils import create_supplier_opening_balance

    supplier = get_object_or_404(Supplier, pk=supplier_id, is_active=True)
    available_advance_total = SupplierAdvance.objects.filter(
        supplier=supplier, remaining_amount__gt=0
    ).aggregate(total=Sum("remaining_amount"))["total"] or 0

    if request.method == "POST":
        form = SupplierOpeningBalanceForm(request.POST)
        if form.is_valid():
            try:
                invoice = create_supplier_opening_balance(
                    supplier=supplier,
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
                    module="supplier_ops",
                    instance=invoice,
                    details={
                        "supplier": supplier.code,
                        "amount": str(invoice.total_net),
                        "opening_balance": True,
                    },
                    request=request,
                )
                messages.success(
                    request,
                    f"Solde d'ouverture {invoice.reference} enregistré pour "
                    f"{supplier.raison_sociale} (§23 planifié).",
                )
                return redirect("suppliers:supplier_detail", supplier_id=supplier.id)
    else:
        form = SupplierOpeningBalanceForm(
            initial={"reference_date": timezone.now().date()}
        )

    return render(
        request,
        "supplier_ops/supplier_opening_balance_form.html",
        {
            "form": form,
            "supplier": supplier,
            "available_advance_total": available_advance_total,
            "title": f"Solde d'ouverture — {supplier.raison_sociale}",
        },
    )


@login_required
def supplier_statement(request, supplier_id):
    """§23.6 — chronological, running-balance statement of account."""
    from .utils import get_supplier_statement

    supplier = get_object_or_404(Supplier, pk=supplier_id, is_active=True)

    date_start = request.GET.get("date_start") or None
    date_end = request.GET.get("date_end") or None
    if date_start:
        date_start = timezone.datetime.strptime(date_start, "%Y-%m-%d").date()
    if date_end:
        date_end = timezone.datetime.strptime(date_end, "%Y-%m-%d").date()

    statement = get_supplier_statement(supplier, date_start=date_start, date_end=date_end)

    return render(
        request,
        "supplier_ops/supplier_statement.html",
        {
            "supplier": supplier,
            "statement": statement,
            "date_start": date_start,
            "date_end": date_end,
            "title": f"Relevé de compte — {supplier.raison_sociale}",
        },
    )
