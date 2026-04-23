# supplier_ops/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import (
    SupplierDN,
    SupplierInvoice,
)
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


@login_required
@role_required(["manager", "stock_prod"])
def supplier_dn_validate(request, dn_id):
    """
    FIX: original code only caught ValueError; SupplierDN.validate() raises
    ValidationError (wrong status, missing SD-DNF supporting document).
    """
    dn = get_object_or_404(SupplierDN, id=dn_id)

    if request.method == "POST":
        try:
            dn.validate(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="validate",
                module="supplier_ops",
                instance=dn,
                request=request,
            )
            messages.success(request, f"BL {dn.reference} validé avec succès")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("supplier_ops:supplier_dn_detail", dn_id=dn.id)


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

    reconciliation_filter = request.GET.get("reconciliation")
    if reconciliation_filter:
        invoices = invoices.filter(reconciliation_result=reconciliation_filter)

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
            "reconciliation_choices": SupplierInvoice.RECONCILIATION_CHOICES,
            "title": "Factures fournisseurs",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_invoice_create(request):
    if request.method == "POST":
        form = SupplierInvoiceForm(request.POST)
        formset = SupplierInvoiceLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            formset.instance = invoice
            formset.save()

            linked_dn_ids = request.POST.getlist("linked_dns")
            if linked_dn_ids:
                for dn_id in linked_dn_ids:
                    try:
                        dn = SupplierDN.objects.get(id=dn_id, status="validated")
                        invoice.linked_dns.add(dn)
                    except SupplierDN.DoesNotExist:
                        pass
                invoice.perform_reconciliation()

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="supplier_ops",
                instance=invoice,
                request=request,
            )
            messages.success(request, f"Facture {invoice.reference} créée avec succès")
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
            "reconciliation_lines": invoice.reconciliation_lines.select_related(
                "raw_material"
            ).all(),
            "payments": invoice.payments.all(),
            "linked_dns": invoice.linked_dns.all(),
            "can_pay": (
                request.user.userprofile.role in ["manager", "accountant"]
                and invoice.status in ["verified", "unpaid", "partially_paid"]
                and invoice.balance_due > 0
            ),
            "title": f"Facture Fournisseur - {invoice.reference}",
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
def reconciliation_ajax(request, invoice_id):
    """
    AJAX endpoint — permitted by S5 (real-time reconciliation delta calculation
    as Accountant enters invoice lines).

    FIX: wrong SystemParameter keys used in original code:
      'reconciliation_tolerance_threshold' → 'reconciliation_tolerance_epsilon'
      'reconciliation_dispute_threshold'   → 'reconciliation_dispute_delta'
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    try:
        invoice = get_object_or_404(SupplierInvoice, id=invoice_id)

        lines_data = []
        for key, value in request.POST.items():
            if key.startswith("lines-") and key.endswith("-quantity_invoiced"):
                line_index = key.split("-")[1]
                material_id = request.POST.get(f"lines-{line_index}-raw_material")
                try:
                    quantity = float(value) if value else 0
                    price = float(
                        request.POST.get(f"lines-{line_index}-unit_price_invoiced", 0)
                    )
                except ValueError:
                    continue
                if material_id and quantity > 0:
                    lines_data.append(
                        {
                            "material_id": int(material_id),
                            "quantity": quantity,
                            "price": price,
                        }
                    )

        # Aggregate DN quantities per material
        dn_data = {}
        for dn in invoice.linked_dns.all():
            for dn_line in dn.lines.all():
                mid = dn_line.raw_material_id
                if mid in dn_data:
                    dn_data[mid]["quantity"] += float(dn_line.quantity_received)
                else:
                    dn_data[mid] = {
                        "quantity": float(dn_line.quantity_received),
                        "price": float(dn_line.agreed_unit_price),
                    }

        total_delta = 0.0
        reconciliation_data = []
        for line_data in lines_data:
            mid = line_data["material_id"]
            qty_inv = line_data["quantity"]
            price_inv = line_data["price"]
            dn_info = dn_data.get(mid, {"quantity": 0.0, "price": 0.0})
            qty_del = dn_info["quantity"]
            price_agr = dn_info["price"]

            delta_qty = qty_inv - qty_del
            delta_price = price_inv - price_agr
            delta_amount = (qty_inv * price_inv) - (qty_del * price_agr)
            total_delta += delta_amount

            reconciliation_data.append(
                {
                    "material_id": mid,
                    "qty_delivered": qty_del,
                    "qty_invoiced": qty_inv,
                    "delta_qty": delta_qty,
                    "price_agreed": price_agr,
                    "price_invoiced": price_inv,
                    "delta_price": delta_price,
                    "delta_amount": delta_amount,
                }
            )

        from core.models import SystemParameter
        from decimal import Decimal

        # FIX: correct parameter key names (S2 / SystemParameter spec)
        tolerance = float(
            SystemParameter.get_decimal_value(
                "reconciliation_tolerance_epsilon", Decimal("500.00")
            )
        )
        dispute_limit = float(
            SystemParameter.get_decimal_value(
                "reconciliation_dispute_delta", Decimal("5000.00")
            )
        )

        abs_delta = abs(total_delta)
        if abs_delta <= tolerance:
            status, label, css = "compliant", "Conforme", "success"
        elif abs_delta <= dispute_limit:
            status, label, css = "minor_discrepancy", "Écart mineur", "warning"
        else:
            status, label, css = "dispute", "Litige", "danger"

        return JsonResponse(
            {
                "success": True,
                "total_delta": total_delta,
                "reconciliation_status": status,
                "status_label": label,
                "status_class": css,
                "reconciliation_lines": reconciliation_data,
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


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
            "reconciliation_lines": invoice.reconciliation_lines.select_related(
                "raw_material"
            ).all(),
        },
    )
