# stock/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Q, Sum, F
from django.utils import timezone
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import (
    RawMaterialStockBalance,
    FinishedProductStockBalance,
    StockMovement,
    StockAdjustment,
    StockAdjustmentLine,
)
from .forms import StockAdjustmentForm, StockAdjustmentLineFormSet


@login_required
def raw_materials_stock_list(request):
    balances = RawMaterialStockBalance.objects.select_related(
        "raw_material", "raw_material__category", "raw_material__unit_of_measure"
    ).all()
    search = request.GET.get("search")
    if search:
        balances = balances.filter(
            Q(raw_material__reference__icontains=search)
            | Q(raw_material__designation__icontains=search)
        )
    category_filter = request.GET.get("category")
    if category_filter:
        balances = balances.filter(raw_material__category_id=category_filter)
    status_filter = request.GET.get("status")
    if status_filter:
        balances = [b for b in balances if b.get_stock_status() == status_filter]
    total_value = sum(b.get_stock_value() for b in balances)
    stockout_count = sum(1 for b in balances if b.get_stock_status() == "stockout")
    low_stock_count = sum(1 for b in balances if b.get_stock_status() == "running_low")
    return render(
        request,
        "stock/raw_materials_stock_list.html",
        {
            "balances": balances,
            "total_value": total_value,
            "stockout_count": stockout_count,
            "low_stock_count": low_stock_count,
            "title": "Stock matières premières",
        },
    )


@login_required
def finished_products_stock_list(request):
    balances = FinishedProductStockBalance.objects.select_related(
        "finished_product", "finished_product__sales_unit"
    ).all()
    search = request.GET.get("search")
    if search:
        balances = balances.filter(
            Q(finished_product__reference__icontains=search)
            | Q(finished_product__designation__icontains=search)
        )
    status_filter = request.GET.get("status")
    if status_filter:
        balances = [b for b in balances if b.get_stock_status() == status_filter]
    total_value = sum(b.get_stock_value() for b in balances)
    stockout_count = sum(1 for b in balances if b.get_stock_status() == "stockout")
    low_stock_count = sum(1 for b in balances if b.get_stock_status() == "running_low")
    return render(
        request,
        "stock/finished_products_stock_list.html",
        {
            "balances": balances,
            "total_value": total_value,
            "stockout_count": stockout_count,
            "low_stock_count": low_stock_count,
            "title": "Stock produits finis",
        },
    )


@login_required
def stock_movements_list(request):
    movements = StockMovement.objects.select_related(
        "raw_material", "finished_product", "created_by"
    ).all()
    material_type = request.GET.get("material_type")
    material_id = request.GET.get("material_id")
    if material_type == "raw_material" and material_id:
        movements = movements.filter(raw_material_id=material_id)
    elif material_type == "finished_product" and material_id:
        movements = movements.filter(finished_product_id=material_id)
    movement_type_filter = request.GET.get("movement_type")
    if movement_type_filter:
        movements = movements.filter(movement_type=movement_type_filter)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        movements = movements.filter(movement_date__gte=date_from)
    if date_to:
        movements = movements.filter(movement_date__lte=date_to)
    return render(
        request,
        "stock/stock_movements_list.html",
        {
            "movements": movements.order_by("-movement_date", "-created_at")[:100],
            "movement_types": StockMovement.MOVEMENT_TYPE_CHOICES,
            "title": "Historique des mouvements",
        },
    )


@login_required
def raw_material_stock_detail(request, material_id):
    from catalog.models import RawMaterial

    material = get_object_or_404(RawMaterial, id=material_id)
    try:
        balance = material.stock_balance
    except RawMaterialStockBalance.DoesNotExist:
        balance = None
    movements = StockMovement.objects.filter(raw_material=material).order_by(
        "-movement_date", "-created_at"
    )[:50]
    return render(
        request,
        "stock/raw_material_stock_detail.html",
        {
            "material": material,
            "balance": balance,
            "current_qty": balance.quantity if balance else Decimal("0.000"),
            "movements": movements,
            "stock_status": balance.get_stock_status() if balance else "stockout",
            "stock_value": balance.get_stock_value() if balance else Decimal("0.00"),
            "title": f"Stock - {material.designation}",
        },
    )


@login_required
def finished_product_stock_detail(request, product_id):
    from catalog.models import FinishedProduct

    product = get_object_or_404(FinishedProduct, id=product_id)
    try:
        balance = product.stock_balance
    except FinishedProductStockBalance.DoesNotExist:
        balance = None
    movements = StockMovement.objects.filter(finished_product=product).order_by(
        "-movement_date", "-created_at"
    )[:50]
    wac = balance.weighted_average_cost if balance else Decimal("0.00")
    qty = balance.quantity if balance else Decimal("0.000")
    unit_margin = product.reference_selling_price - wac
    margin_rate = (
        (unit_margin / product.reference_selling_price * 100)
        if product.reference_selling_price > 0
        else Decimal("0.00")
    )
    return render(
        request,
        "stock/finished_product_stock_detail.html",
        {
            "product": product,
            "balance": balance,
            "current_qty": qty,
            "movements": movements,
            "stock_status": balance.get_stock_status() if balance else "stockout",
            "stock_value": balance.get_stock_value() if balance else Decimal("0.00"),
            "unit_margin": unit_margin,
            "margin_rate": margin_rate,
            "title": f"Stock - {product.designation}",
        },
    )


@login_required
def stock_adjustments_list(request):
    adjustments = StockAdjustment.objects.select_related(
        "created_by", "approved_by"
    ).all()
    type_filter = request.GET.get("adjustment_type")
    if type_filter:
        adjustments = adjustments.filter(adjustment_type=type_filter)
    approval_filter = request.GET.get("approval_status")
    if approval_filter == "pending":
        adjustments = adjustments.filter(approved_by__isnull=True)
    elif approval_filter == "approved":
        adjustments = adjustments.filter(approved_by__isnull=False)
    return render(
        request,
        "stock/stock_adjustments_list.html",
        {
            "adjustments": adjustments.order_by("-adjustment_date"),
            "adjustment_types": StockAdjustment.ADJUSTMENT_TYPE_CHOICES,
            "title": "Ajustements de stock",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def stock_adjustment_create(request):
    if request.method == "POST":
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            adjustment = form.save(commit=False)
            adjustment.created_by = request.user
            adjustment.save()
            formset.instance = adjustment
            formset.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="stock",
                instance=adjustment,
                request=request,
            )
            messages.success(
                request, f"Ajustement {adjustment.reference} créé avec succès"
            )
            return redirect(
                "stock:stock_adjustment_detail", adjustment_id=adjustment.id
            )
    else:
        form = StockAdjustmentForm()
        formset = StockAdjustmentLineFormSet()
    return render(
        request,
        "stock/stock_adjustment_form.html",
        {"form": form, "formset": formset, "title": "Nouvel ajustement de stock"},
    )


@login_required
def stock_adjustment_detail(request, adjustment_id):
    adjustment = get_object_or_404(StockAdjustment, id=adjustment_id)
    return render(
        request,
        "stock/stock_adjustment_detail.html",
        {
            "adjustment": adjustment,
            "lines": adjustment.lines.all(),
            "can_approve": request.user.userprofile.role == "manager"
            and not adjustment.approved_by,
            "title": f"Ajustement - {adjustment.reference}",
        },
    )


@login_required
@role_required(["manager"])
def stock_adjustment_approve(request, adjustment_id):
    adjustment = get_object_or_404(StockAdjustment, id=adjustment_id)
    if request.method == "POST":
        if adjustment.approved_by:
            messages.error(request, "Cet ajustement est déjà approuvé")
        else:
            try:
                adjustment.approve(request.user)
                AuditLog.log_action(
                    user=request.user,
                    action_type="validate",
                    module="stock",
                    instance=adjustment,
                    request=request,
                )
                messages.success(request, f"Ajustement {adjustment.reference} approuvé")
            except ValueError as e:
                messages.error(request, str(e))
    return redirect("stock:stock_adjustment_detail", adjustment_id=adjustment.id)


@login_required
def stock_availability_ajax(request):
    if request.method == "GET":
        material_type = request.GET.get("material_type")
        material_id = request.GET.get("material_id")
        required_qty = request.GET.get("required_qty")
        if material_type and material_id and required_qty:
            try:
                required_qty = Decimal(required_qty)
                if material_type == "finished_product":
                    from catalog.models import FinishedProduct

                    material = get_object_or_404(FinishedProduct, id=material_id)
                    try:
                        current_stock = material.stock_balance.quantity
                    except FinishedProductStockBalance.DoesNotExist:
                        current_stock = Decimal("0.000")
                elif material_type == "raw_material":
                    from catalog.models import RawMaterial

                    material = get_object_or_404(RawMaterial, id=material_id)
                    try:
                        current_stock = material.stock_balance.quantity
                    except RawMaterialStockBalance.DoesNotExist:
                        current_stock = Decimal("0.000")
                else:
                    return JsonResponse({"success": False, "error": "Type invalide"})
                return JsonResponse(
                    {
                        "success": True,
                        "current_stock": str(current_stock),
                        "required_qty": str(required_qty),
                        "sufficient": current_stock >= required_qty,
                        "shortage": str(
                            max(required_qty - current_stock, Decimal("0.000"))
                        ),
                        "material_name": material.designation,
                    }
                )
            except Exception as e:
                return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Paramètres invalides"})


@login_required
def stock_alerts_dashboard(request):
    rm_stockouts = RawMaterialStockBalance.objects.select_related(
        "raw_material"
    ).filter(quantity__lte=F("raw_material__stockout_threshold"))
    rm_low_stock = RawMaterialStockBalance.objects.select_related(
        "raw_material"
    ).filter(
        quantity__gt=F("raw_material__stockout_threshold"),
        quantity__lte=F("raw_material__alert_threshold"),
    )
    fp_stockouts = FinishedProductStockBalance.objects.select_related(
        "finished_product"
    ).filter(quantity__lte=0)
    fp_low_stock = FinishedProductStockBalance.objects.select_related(
        "finished_product"
    ).filter(quantity__gt=0, quantity__lte=F("finished_product__alert_threshold"))
    return render(
        request,
        "stock/stock_alerts_dashboard.html",
        {
            "rm_stockouts": rm_stockouts,
            "rm_low_stock": rm_low_stock,
            "fp_stockouts": fp_stockouts,
            "fp_low_stock": fp_low_stock,
            "title": "Alertes stock",
        },
    )
