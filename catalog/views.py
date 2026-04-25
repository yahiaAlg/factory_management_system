# catalog/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import RawMaterial, FinishedProduct, RawMaterialCategory
from .forms import RawMaterialForm, FinishedProductForm


@login_required
def raw_materials_list(request):
    """Raw materials catalog list"""
    materials = RawMaterial.objects.select_related(
        "category", "unit_of_measure", "default_supplier"
    ).all()

    search = request.GET.get("search")
    if search:
        materials = materials.filter(
            Q(reference__icontains=search) | Q(designation__icontains=search)
        )

    category_id = request.GET.get("category")
    if category_id:
        materials = materials.filter(category_id=category_id)

    if request.GET.get("active") == "false":
        materials = materials.filter(is_active=False)
    elif request.GET.get("active") != "all":
        materials = materials.filter(is_active=True)

    categories = RawMaterialCategory.objects.filter(is_active=True)

    return render(
        request,
        "catalog/raw_materials_list.html",
        {
            "materials": materials,
            "categories": categories,
            "title": "Catalogue matières premières",
        },
    )


@login_required
@role_required(["manager"])
def raw_material_create(request):
    """Create new raw material — manager only (S9)"""
    if request.method == "POST":
        form = RawMaterialForm(request.POST)
        if form.is_valid():
            material = form.save(commit=False)
            material.created_by = request.user
            material.save()

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="catalog",
                instance=material,
                request=request,
            )

            messages.success(
                request, f"Matière première {material.reference} créée avec succès"
            )
            return redirect("catalog:raw_materials_list")
    else:
        form = RawMaterialForm()

    return render(
        request,
        "catalog/raw_material_form.html",
        {
            "form": form,
            "title": "Nouvelle matière première",
        },
    )


@login_required
def raw_material_detail(request, material_id):
    """Raw material detail view"""
    material = get_object_or_404(RawMaterial, id=material_id)

    from stock.models import StockMovement

    stock_movements = StockMovement.objects.filter(raw_material=material).order_by(
        "-created_at"
    )[:20]

    return render(
        request,
        "catalog/raw_material_detail.html",
        {
            "material": material,
            "stock_movements": stock_movements,
            "current_stock": material.get_current_stock(),
            "stock_status": material.get_stock_status(),
            "title": f"Matière première - {material.reference}",
        },
    )


@login_required
@role_required(["manager"])
def raw_material_edit(request, material_id):
    """Edit raw material — manager only (S9)"""
    material = get_object_or_404(RawMaterial, id=material_id)

    if request.method == "POST":
        form = RawMaterialForm(request.POST, instance=material)
        if form.is_valid():
            old_values = {
                "designation": material.designation,
                "reference_price": str(material.reference_price),
                "alert_threshold": str(material.alert_threshold),
                "stockout_threshold": str(material.stockout_threshold),
            }
            material = form.save()
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="catalog",
                instance=material,
                details={
                    "before": old_values,
                    "after": {
                        "designation": material.designation,
                        "reference_price": str(material.reference_price),
                        "alert_threshold": str(material.alert_threshold),
                        "stockout_threshold": str(material.stockout_threshold),
                    },
                },
                request=request,
            )
            messages.success(
                request, f"Matière première {material.reference} modifiée avec succès"
            )
            return redirect("catalog:raw_material_detail", material_id=material.id)
    else:
        form = RawMaterialForm(instance=material)

    return render(
        request,
        "catalog/raw_material_form.html",
        {
            "form": form,
            "material": material,
            "title": f"Modifier - {material.reference}",
        },
    )


@login_required
def finished_products_list(request):
    """Finished products catalog list"""
    products = FinishedProduct.objects.select_related("sales_unit").all()

    search = request.GET.get("search")
    if search:
        products = products.filter(
            Q(reference__icontains=search) | Q(designation__icontains=search)
        )

    if request.GET.get("active") == "false":
        products = products.filter(is_active=False)
    elif request.GET.get("active") != "all":
        products = products.filter(is_active=True)

    return render(
        request,
        "catalog/finished_products_list.html",
        {
            "products": products,
            "title": "Catalogue produits finis",
        },
    )


@login_required
@role_required(["manager"])
def finished_product_create(request):
    """Create new finished product — manager only (S9)"""
    if request.method == "POST":
        form = FinishedProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="catalog",
                instance=product,
                request=request,
            )

            messages.success(
                request, f"Produit fini {product.reference} créé avec succès"
            )
            return redirect("catalog:finished_products_list")
    else:
        form = FinishedProductForm()

    return render(
        request,
        "catalog/finished_product_form.html",
        {
            "form": form,
            "title": "Nouveau produit fini",
        },
    )


@login_required
def finished_product_detail(request, product_id):
    """Finished product detail view"""
    product = get_object_or_404(FinishedProduct, id=product_id)

    from production.models import ProductionOrder

    production_orders = ProductionOrder.objects.filter(
        formulation__finished_product=product
    ).order_by("-created_at")[:10]

    return render(
        request,
        "catalog/finished_product_detail.html",
        {
            "product": product,
            "production_orders": production_orders,
            "current_stock": product.get_current_stock(),
            "stock_status": product.get_stock_status(),
            "wac": product.wac,
            "unit_margin": product.get_unit_gross_margin(),
            "margin_rate": product.get_margin_rate(),
            "title": f"Produit fini - {product.reference}",
        },
    )


# catalog/views.py  — add this view

# catalog/views.py — FinishedProduct CRUD views
# Add these to your existing catalog/views.py

import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from decimal import Decimal, InvalidOperation
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import FinishedProduct, UnitOfMeasure


# ─── Form ────────────────────────────────────────────────────────────────────


class FinishedProductForm(ModelForm):
    class Meta:
        model = FinishedProduct
        fields = [
            "designation",
            "sales_unit",
            "reference_selling_price",
            "alert_threshold",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sales_unit"].queryset = UnitOfMeasure.objects.filter(
            is_active=True
        )


# ─── List ─────────────────────────────────────────────────────────────────────


@login_required
def finished_products_list(request):
    products = FinishedProduct.objects.select_related("sales_unit").all()

    search = request.GET.get("search", "").strip()
    if search:
        from django.db.models import Q

        products = products.filter(
            Q(reference__icontains=search) | Q(designation__icontains=search)
        )

    active = request.GET.get("active", "true")
    if active == "false":
        products = products.filter(is_active=False)
    elif active != "all":
        products = products.filter(is_active=True)

    products = products.order_by("reference")
    return render(
        request,
        "catalog/finished_product_list.html",
        {
            "products": products,
            "total_count": products.count(),
            "title": "Produits finis",
        },
    )


# ─── Create ───────────────────────────────────────────────────────────────────


@login_required
@role_required(["manager"])
def finished_product_create(request):
    if request.method == "POST":
        form = FinishedProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="catalog",
                instance=product,
                request=request,
            )
            messages.success(request, f"Produit {product.reference} créé avec succès.")
            return redirect("catalog:finished_products_list")
    else:
        form = FinishedProductForm()

    return render(
        request,
        "catalog/finished_product_form.html",
        {
            "form": form,
            "title": "Nouveau produit fini",
        },
    )


# ─── Edit ─────────────────────────────────────────────────────────────────────


@login_required
@role_required(["manager"])
def finished_product_edit(request, product_id):
    product = get_object_or_404(FinishedProduct, pk=product_id)

    if request.method == "POST":
        form = FinishedProductForm(request.POST, instance=product)
        if form.is_valid():
            before = {f: str(getattr(product, f)) for f in form.changed_data}
            product = form.save()
            after = {f: str(getattr(product, f)) for f in form.changed_data}
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="catalog",
                instance=product,
                details={"before": before, "after": after},
                request=request,
            )
            messages.success(request, f"{product.reference} mis à jour.")
            return redirect("catalog:finished_products_list")
    else:
        form = FinishedProductForm(instance=product)

    return render(
        request,
        "catalog/finished_product_form.html",
        {
            "form": form,
            "product": product,
            "title": f"Modifier {product.reference}",
        },
    )


# ─── Toggle active/inactive (replaces hard delete) ───────────────────────────


@login_required
@role_required(["manager"])
@require_POST
def finished_product_deactivate(request, product_id):
    product = get_object_or_404(FinishedProduct, pk=product_id)
    product.is_active = False
    product.save()
    AuditLog.log_action(
        user=request.user,
        action_type="cancel",
        module="catalog",
        instance=product,
        details={"is_active": False},
        request=request,
    )
    messages.success(request, f"{product.reference} désactivé.")
    return redirect("catalog:finished_products_list")


@login_required
@role_required(["manager"])
@require_POST
def finished_product_activate(request, product_id):
    product = get_object_or_404(FinishedProduct, pk=product_id)
    product.is_active = True
    product.save()
    AuditLog.log_action(
        user=request.user,
        action_type="update",
        module="catalog",
        instance=product,
        details={"is_active": True},
        request=request,
    )
    messages.success(request, f"{product.reference} réactivé.")
    return redirect("catalog:finished_products_list")


# ─── Quick-create AJAX (used from formulation form) ───────────────────────────


@login_required
@require_POST
def finished_product_quick_create(request):
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Requête invalide."}, status=400
        )

    designation = payload.get("designation", "").strip()
    sales_unit_id = payload.get("sales_unit", "")

    if not designation:
        return JsonResponse(
            {"success": False, "error": "La désignation est obligatoire."}
        )
    if not sales_unit_id:
        return JsonResponse(
            {"success": False, "error": "L'unité de vente est obligatoire."}
        )

    try:
        sales_unit = UnitOfMeasure.objects.get(pk=sales_unit_id, is_active=True)
    except UnitOfMeasure.DoesNotExist:
        return JsonResponse({"success": False, "error": "Unité de vente introuvable."})

    try:
        price = Decimal(str(payload.get("reference_selling_price", "0")))
    except InvalidOperation:
        price = Decimal("0.00")

    try:
        threshold = Decimal(str(payload.get("alert_threshold", "0")))
    except InvalidOperation:
        threshold = Decimal("0.000")

    product = FinishedProduct.objects.create(
        designation=designation,
        sales_unit=sales_unit,
        reference_selling_price=price,
        alert_threshold=threshold,
        created_by=request.user,
    )

    return JsonResponse({"success": True, "id": product.pk, "label": str(product)})


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import json


@login_required
def raw_material_get_unit(request, material_id):
    """AJAX: return the unit_of_measure for a raw material (for auto-fill in DN lines)."""
    from catalog.models import RawMaterial

    try:

        material = get_object_or_404(RawMaterial, id=material_id)
        return JsonResponse(
            {
                "unit_id": material.unit_of_measure_id,
                "unit_symbol": material.unit_of_measure.symbol,
                "reference_price": str(material.reference_price),  # ← add this
            }
        )
    except RawMaterial.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)


@login_required
@require_POST
def raw_material_quick_create(request):
    """AJAX quick-create a raw material from the supplier DN form modal."""
    from catalog.models import RawMaterial, RawMaterialCategory, UnitOfMeasure
    from decimal import Decimal, InvalidOperation

    try:
        data = json.loads(request.body)
        designation = (data.get("designation") or "").strip()
        category_id = data.get("category")
        uom_id = data.get("unit_of_measure")
        if not designation:
            return JsonResponse({"success": False, "error": "Désignation obligatoire."})
        if not category_id:
            return JsonResponse({"success": False, "error": "Catégorie obligatoire."})
        if not uom_id:
            return JsonResponse(
                {"success": False, "error": "Unité de mesure obligatoire."}
            )

        def to_dec(val, default="0.000"):
            try:
                return Decimal(str(val))
            except (InvalidOperation, TypeError):
                return Decimal(default)

        alert_t = to_dec(data.get("alert_threshold"), "10.000")
        stockout_t = to_dec(data.get("stockout_threshold"), "5.000")

        rm = RawMaterial(
            designation=designation,
            category_id=category_id,
            unit_of_measure_id=uom_id,
            reference_price=to_dec(data.get("reference_price"), "0.00"),
            alert_threshold=alert_t,
            stockout_threshold=stockout_t,
            created_by=request.user,
            is_active=True,
        )
        supplier_id = data.get("default_supplier")
        if supplier_id:
            rm.default_supplier_id = supplier_id

        rm.full_clean()  # triggers clean() — validates alert > stockout, etc.
        rm.save()

        return JsonResponse(
            {
                "success": True,
                "id": rm.pk,
                "label": str(rm),  # "RM-001 - Designation"
                "unit_id": rm.unit_of_measure_id,
            }
        )
    except Exception as e:
        msg = e.message_dict if hasattr(e, "message_dict") else str(e)
        return JsonResponse({"success": False, "error": str(msg)})
