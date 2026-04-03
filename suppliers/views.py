# suppliers/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone  # FIX: was missing; used in supplier_detail
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Supplier
from .forms import SupplierForm


@login_required
def suppliers_list(request):
    suppliers = Supplier.objects.all()

    search = request.GET.get("search")
    if search:
        suppliers = suppliers.filter(
            Q(code__icontains=search)
            | Q(raison_sociale__icontains=search)
            | Q(nif__icontains=search)
            | Q(nis__icontains=search)
        )

    currency_filter = request.GET.get("currency")
    if currency_filter:
        suppliers = suppliers.filter(currency=currency_filter)

    wilaya_filter = request.GET.get("wilaya")
    if wilaya_filter:
        suppliers = suppliers.filter(wilaya=wilaya_filter)

    if request.GET.get("active") == "false":
        suppliers = suppliers.filter(is_active=False)
    elif request.GET.get("active") != "all":
        suppliers = suppliers.filter(is_active=True)

    wilayas = (
        Supplier.objects.values_list("wilaya", flat=True).distinct().exclude(wilaya="")
    )

    return render(
        request,
        "suppliers/suppliers_list.html",
        {
            "suppliers": suppliers.order_by("raison_sociale"),
            "wilayas": sorted(wilayas),
            "currencies": Supplier.CURRENCY_CHOICES,
            "title": "Répertoire fournisseurs",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="suppliers",
                instance=supplier,
                request=request,
            )
            messages.success(request, f"Fournisseur {supplier.code} créé avec succès")
            return redirect("suppliers_list")
    else:
        form = SupplierForm()

    return render(
        request,
        "suppliers/supplier_form.html",
        {
            "form": form,
            "title": "Nouveau fournisseur",
        },
    )


@login_required
def supplier_detail(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    current_year = timezone.now().year
    return render(
        request,
        "suppliers/supplier_detail.html",
        {
            "supplier": supplier,
            "recent_deliveries": supplier.get_recent_deliveries(10),
            "recent_invoices": supplier.get_recent_invoices(10),
            "total_purchases_current_year": supplier.get_total_purchases_amount(
                current_year
            ),
            "total_purchases_previous_year": supplier.get_total_purchases_amount(
                current_year - 1
            ),
            "outstanding_balance": supplier.get_outstanding_balance(),
            "title": f"Fournisseur - {supplier.code}",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_edit(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            old_values = {
                "raison_sociale": supplier.raison_sociale,
                "address": supplier.address,
                "payment_terms": supplier.payment_terms,
                "currency": supplier.currency,
            }
            supplier = form.save()
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="suppliers",
                instance=supplier,
                details={
                    "before": old_values,
                    "after": {
                        "raison_sociale": supplier.raison_sociale,
                        "address": supplier.address,
                        "payment_terms": supplier.payment_terms,
                        "currency": supplier.currency,
                    },
                },
                request=request,
            )
            messages.success(
                request, f"Fournisseur {supplier.code} modifié avec succès"
            )
            return redirect("supplier_detail", supplier_id=supplier.id)
    else:
        form = SupplierForm(instance=supplier)

    return render(
        request,
        "suppliers/supplier_form.html",
        {
            "form": form,
            "supplier": supplier,
            "title": f"Modifier - {supplier.code}",
        },
    )


@login_required
@role_required(["manager", "accountant"])
def supplier_toggle_active(request, supplier_id):
    """
    FIX: was a JsonResponse/AJAX endpoint — outside the 4 permitted AJAX cases (S5).
    Converted to a standard POST-Redirect-GET view.
    """
    if request.method == "POST":
        supplier = get_object_or_404(Supplier, id=supplier_id)
        old_status = supplier.is_active
        supplier.is_active = not supplier.is_active
        supplier.save()
        AuditLog.log_action(
            user=request.user,
            action_type="update",
            module="suppliers",
            instance=supplier,
            details={
                "field_changed": "is_active",
                "before": old_status,
                "after": supplier.is_active,
            },
            request=request,
        )
        status_label = "activé" if supplier.is_active else "désactivé"
        messages.success(request, f"Fournisseur {supplier.code} {status_label}")

    return redirect("supplier_detail", supplier_id=supplier_id)


# FIX: supplier_search_ajax REMOVED.
# A generic JSON autocomplete endpoint is not among the 4 permitted AJAX cases (S5).
# Supplier dropdowns in forms are populated server-side via queryset in SupplierDNForm
# and SupplierInvoiceForm __init__().
