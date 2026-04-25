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
)


@login_required
def supplier_dns_list(request):
    dns = SupplierDN.objects.select_related("supplier", "validated_by").all()

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
            "title": "Bons de livraison fournisseurs",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def supplier_dn_create(request):
    if request.method == "POST":
        form = SupplierDNForm(request.POST)
        formset = SupplierDNLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            formset.instance = dn
            formset.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="supplier_ops",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL Fournisseur {dn.reference} créé avec succès")
            return redirect("supplier_ops:supplier_dn_detail", dn_id=dn.id)
    else:
        form = SupplierDNForm()
        formset = SupplierDNLineFormSet()

    return render(
        request,
        "supplier_ops/supplier_dn_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouveau BL Fournisseur",
            "rm_categories": RawMaterialCategory.objects.filter(is_active=True),
            "uom_choices": UnitOfMeasure.objects.filter(is_active=True),
            "active_suppliers": Supplier.objects.filter(is_active=True),
        },
    )


@login_required
def supplier_dn_detail(request, dn_id):
    dn = get_object_or_404(SupplierDN, id=dn_id)
    return render(
        request,
        "supplier_ops/supplier_dn_detail.html",
        {
            "dn": dn,
            "lines": dn.lines.select_related("raw_material", "unit_of_measure").all(),
            "can_validate": (
                request.user.userprofile.role in ["manager", "stock_prod"]
                and dn.status == "pending"
            ),
            "title": f"BL Fournisseur - {dn.reference}",
        },
    )


# require post import for supplier_dn_validate


@login_required
@require_POST
def supplier_dn_validate(request, dn_id):
    dn = get_object_or_404(SupplierDN, pk=dn_id)

    if request.user.userprofile.role not in ("manager", "accountant"):
        messages.error(request, "Vous n'avez pas la permission de valider un BL.")
        return redirect("supplier_ops:supplier_dn_detail", dn_id=dn_id)

    uploaded_file = request.FILES.get("sd_dnf_file")
    if uploaded_file:
        from expenses.models import SupportingDocument

        SupportingDocument.objects.create(
            doc_type="SD-DNF",
            entity_type="supplierdn",
            entity_id=dn.pk,
            description=f"Justificatif BL {dn.reference} — {uploaded_file.name}",
            file=uploaded_file,
            registered_by=request.user,
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
            else:
                invoice = form.save(commit=False)
                invoice.created_by = request.user
                invoice.save()

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

    return render(
        request,
        "supplier_ops/supplier_invoice_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouvelle facture fournisseur",
        },
    )


@login_required
def supplier_invoice_detail(request, invoice_id):
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    return render(
        request,
        "supplier_ops/supplier_invoice_detail.html",
        {
            "invoice": invoice,
            "lines": invoice.lines.select_related("raw_material").all(),
            "payments": invoice.payments.all(),
            "linked_dns": invoice.linked_dns.all(),
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
        if form.is_valid():
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
                        "invoice": invoice,
                        "title": f"Paiement - {invoice.reference}",
                    },
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

    return render(
        request,
        "supplier_ops/supplier_payment_form.html",
        {
            "form": form,
            "invoice": invoice,
            "title": f"Paiement - {invoice.reference}",
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
            if form.cleaned_data["amount"] > total_outstanding:
                form.add_error(
                    "amount",
                    f"Le montant ({form.cleaned_data['amount']} DA) dépasse le solde total dû ({total_outstanding} DA).",
                )
            else:
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
                    messages.success(
                        request,
                        f"Règlement {settlement.reference} enregistré. "
                        f"Factures soldées : {invoices_str}",
                    )
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
