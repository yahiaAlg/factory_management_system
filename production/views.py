# production/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Formulation, FormulationLine, ProductionOrder, ProductionOrderLine
from .forms import (
    FormulationForm,
    FormulationLineFormSet,
    ProductionOrderForm,
    ProductionOrderCloseForm,
)


@login_required
def formulations_list(request):
    formulations = Formulation.objects.select_related(
        "finished_product", "created_by"
    ).all()

    search = request.GET.get("search")
    if search:
        formulations = formulations.filter(
            Q(reference__icontains=search)
            | Q(designation__icontains=search)
            | Q(finished_product__designation__icontains=search)
        )

    if request.GET.get("active") == "false":
        formulations = formulations.filter(is_active=False)
    elif request.GET.get("active") != "all":
        formulations = formulations.filter(is_active=True)

    product_filter = request.GET.get("product")
    if product_filter:
        formulations = formulations.filter(finished_product_id=product_filter)

    return render(
        request,
        "production/formulations_list.html",
        {
            "formulations": formulations.order_by("reference", "-version"),
            "title": "Formulations",
        },
    )


@login_required
@role_required(["manager"])
def formulation_create(request):
    if request.method == "POST":
        form = FormulationForm(request.POST)
        formset = FormulationLineFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            formulation = form.save(commit=False)
            formulation.created_by = request.user
            formulation.save()
            formset.instance = formulation
            formset.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="production",
                instance=formulation,
                request=request,
            )
            messages.success(
                request, f"Formulation {formulation.reference} créée avec succès"
            )
            return redirect("formulation_detail", formulation_id=formulation.id)
    else:
        form = FormulationForm()
        formset = FormulationLineFormSet()

    return render(
        request,
        "production/formulation_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Nouvelle formulation",
        },
    )


@login_required
def formulation_detail(request, formulation_id):
    formulation = get_object_or_404(Formulation, id=formulation_id)
    return render(
        request,
        "production/formulation_detail.html",
        {
            "formulation": formulation,
            "lines": formulation.lines.select_related(
                "raw_material", "unit_of_measure"
            ).all(),
            "production_orders": formulation.production_orders.all().order_by(
                "-launch_date"
            )[:10],
            "theoretical_cost": formulation.calculate_theoretical_cost(),
            "unit_cost": formulation.get_unit_theoretical_cost(),
            "can_edit": request.user.userprofile.role == "manager",
            "title": f"Formulation - {formulation.reference}",
        },
    )


@login_required
@role_required(["manager"])
def formulation_edit(request, formulation_id):
    """Create a new version of the formulation (BR-PROD-03)."""
    formulation = get_object_or_404(Formulation, id=formulation_id)

    if request.method == "POST":
        try:
            new_formulation = formulation.create_new_version(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="production",
                instance=new_formulation,
                details={"previous_version": formulation.version},
                request=request,
            )
            messages.success(
                request, f"Nouvelle version {new_formulation.version} créée"
            )
            return redirect("formulation_detail", formulation_id=new_formulation.id)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("formulation_detail", formulation_id=formulation.id)


@login_required
def production_orders_list(request):
    """
    FIX: removed .filter(yield_status=...) and .filter(yield_rate=...) ORM calls.
    yield_status and yield_rate are @property on ProductionOrder — they cannot
    be used in ORM queryset filters.
    FIX: removed reference to ProductionOrder.YIELD_STATUS_CHOICES — does not exist.
    """
    orders = ProductionOrder.objects.select_related(
        "formulation", "formulation__finished_product", "created_by"
    ).all()

    search = request.GET.get("search")
    if search:
        orders = orders.filter(
            Q(reference__icontains=search)
            | Q(formulation__designation__icontains=search)
        )

    status_filter = request.GET.get("status")
    if status_filter:
        orders = orders.filter(status=status_filter)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        orders = orders.filter(launch_date__gte=date_from)
    if date_to:
        orders = orders.filter(launch_date__lte=date_to)

    # yield_status filter: must be done in Python after queryset evaluation
    yield_filter = request.GET.get("yield_status")
    orders_qs = orders.order_by("-launch_date")
    if yield_filter:
        orders_qs = [o for o in orders_qs if o.yield_status == yield_filter]

    return render(
        request,
        "production/production_orders_list.html",
        {
            "orders": orders_qs,
            "status_choices": ProductionOrder.STATUS_CHOICES,
            # Inline yield status choices (not on model)
            "yield_choices": [
                ("normal", "Normal"),
                ("warning", "Avertissement"),
                ("critical", "Critique"),
            ],
            "title": "Ordres de production",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def production_order_create(request):
    if request.method == "POST":
        form = ProductionOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="production",
                instance=order,
                request=request,
            )
            messages.success(
                request, f"Ordre de production {order.reference} créé avec succès"
            )
            return redirect("production_order_detail", order_id=order.id)
    else:
        form = ProductionOrderForm()

    return render(
        request,
        "production/production_order_form.html",
        {
            "form": form,
            "title": "Nouvel ordre de production",
        },
    )


@login_required
def production_order_detail(request, order_id):
    order = get_object_or_404(ProductionOrder, id=order_id)
    role = request.user.userprofile.role
    return render(
        request,
        "production/production_order_detail.html",
        {
            "order": order,
            "consumption_lines": order.consumption_lines.select_related(
                "raw_material"
            ).all(),
            # FIX: can_validate: pending → validated (stock check step)
            "can_validate": role in ["manager", "stock_prod"]
            and order.status == "pending",
            # FIX: can_launch: validated → in_progress (not pending → in_progress)
            "can_launch": role in ["manager", "stock_prod"]
            and order.status == "validated",
            "can_close": role in ["manager", "stock_prod"]
            and order.status == "in_progress",
            "title": f"Ordre de Production - {order.reference}",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def production_order_validate(request, order_id):
    """
    NEW VIEW: pending → validated.

    FIX: the original code had no validate step — the launch view tried to call
    launch() on a 'pending' PO, but ProductionOrder.VALID_TRANSITIONS requires
    validated → in_progress.  validate() runs the stock availability check and
    sets stock_check_passed.
    """
    order = get_object_or_404(ProductionOrder, id=order_id)

    if request.method == "POST":
        try:
            insufficient = order.validate(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="validate",
                module="production",
                instance=order,
                details={"stock_check_passed": order.stock_check_passed},
                request=request,
            )
            if insufficient:
                shortage_info = ", ".join(
                    f"{i['material'].designation} (manque {i['shortage']})"
                    for i in insufficient
                )
                messages.warning(
                    request,
                    f"OP {order.reference} validé avec avertissement stock : {shortage_info}",
                )
            else:
                messages.success(
                    request, f"Ordre de production {order.reference} validé"
                )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("production_order_detail", order_id=order.id)


@login_required
@role_required(["manager", "stock_prod"])
def production_order_launch(request, order_id):
    """validated → in_progress"""
    order = get_object_or_404(ProductionOrder, id=order_id)

    if request.method == "POST":
        try:
            order.launch(request.user)
            AuditLog.log_action(
                user=request.user,
                action_type="validate",
                module="production",
                instance=order,
                details={"action": "launch"},
                request=request,
            )
            messages.success(request, f"Ordre de production {order.reference} lancé")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("production_order_detail", order_id=order.id)


@login_required
@role_required(["manager", "stock_prod"])
def production_order_close(request, order_id):
    """in_progress → completed"""
    order = get_object_or_404(ProductionOrder, id=order_id)

    if order.status != "in_progress":
        messages.error(request, "Cet ordre ne peut pas être clôturé")
        return redirect("production_order_detail", order_id=order.id)

    if request.method == "POST":
        form = ProductionOrderCloseForm(request.POST, instance=order)
        if form.is_valid():
            actual_qty_produced = form.cleaned_data["actual_qty_produced"]
            consumption_data = form.get_consumption_data()
            try:
                order.close(request.user, actual_qty_produced, consumption_data)
                AuditLog.log_action(
                    user=request.user,
                    action_type="validate",
                    module="production",
                    instance=order,
                    details={"action": "close", "yield_rate": str(order.yield_rate)},
                    request=request,
                )
                messages.success(
                    request, f"Ordre de production {order.reference} clôturé"
                )
                return redirect("production_order_detail", order_id=order.id)
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
    else:
        form = ProductionOrderCloseForm(instance=order)

    return render(
        request,
        "production/production_order_close.html",
        {
            "form": form,
            "order": order,
            "title": f"Clôture OP - {order.reference}",
        },
    )


@login_required
def formulation_scaling_ajax(request):
    """
    AJAX endpoint — permitted by S5 (formulation scaling preview on PO create form).
    """
    if request.method == "GET":
        formulation_id = request.GET.get("formulation_id")
        target_qty = request.GET.get("target_qty")

        if formulation_id and target_qty:
            try:
                formulation = Formulation.objects.get(id=formulation_id)
                target_qty = Decimal(target_qty)
                scaling_factor = target_qty / formulation.reference_batch_qty

                from stock.models import RawMaterialStockBalance

                lines_data = []
                for line in formulation.lines.all():
                    theoretical_qty = line.qty_per_batch * scaling_factor
                    try:
                        balance = RawMaterialStockBalance.objects.get(
                            raw_material=line.raw_material
                        )
                        available_qty = balance.quantity
                    except RawMaterialStockBalance.DoesNotExist:
                        available_qty = Decimal("0.000")

                    lines_data.append(
                        {
                            "material_id": line.raw_material.id,
                            "material_name": line.raw_material.designation,
                            "theoretical_qty": str(theoretical_qty),
                            "unit": line.unit_of_measure.symbol,
                            "available_qty": str(available_qty),
                            "sufficient": available_qty >= theoretical_qty,
                        }
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "scaling_factor": str(scaling_factor),
                        "lines": lines_data,
                    }
                )
            except (Formulation.DoesNotExist, ValueError, ZeroDivisionError):
                pass

    return JsonResponse({"success": False, "error": "Paramètres invalides"})


@login_required
def production_yield_report(request):
    """
    FIX: removed ORM aggregation on yield_rate, yield_status, and
    financial_impact — these are all @property on their respective models and
    cannot be used in ORM .filter() / .aggregate() calls.  Statistics are now
    computed in Python from the fetched queryset.
    FIX: removed `models.Count` reference — models was not imported.
    """
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    orders = (
        ProductionOrder.objects.filter(status="completed")
        .select_related("formulation", "formulation__finished_product")
        .prefetch_related("consumption_lines__raw_material")
    )

    if date_from:
        orders = orders.filter(closure_date__gte=date_from)
    if date_to:
        orders = orders.filter(closure_date__lte=date_to)

    orders = list(orders.order_by("-closure_date"))

    # Compute stats in Python
    total_orders = len(orders)
    rates = [o.yield_rate for o in orders if o.yield_rate is not None]
    avg_yield = (sum(rates) / len(rates)) if rates else Decimal("0.00")
    normal_orders = [o for o in orders if o.yield_status == "normal"]
    warning_orders = [o for o in orders if o.yield_status == "warning"]
    critical_orders = [o for o in orders if o.yield_status == "critical"]

    total_over_consumption_cost = sum(
        (line.financial_impact or Decimal("0.00"))
        for o in orders
        for line in o.consumption_lines.all()
        if (line.delta_qty or Decimal("0")) > 0
    )

    return render(
        request,
        "production/yield_report.html",
        {
            "orders": orders[:50],
            "total_orders": total_orders,
            "avg_yield": avg_yield,
            "normal_count": len(normal_orders),
            "warning_orders": warning_orders,
            "critical_orders": critical_orders,
            "total_over_consumption_cost": total_over_consumption_cost,
            "title": "Analyse des rendements de production",
        },
    )
