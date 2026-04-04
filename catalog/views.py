# catalog/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import RawMaterial, FinishedProduct, RawMaterialCategory, UnitOfMeasure
from .forms import RawMaterialForm, FinishedProductForm, RawMaterialCategoryForm


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
