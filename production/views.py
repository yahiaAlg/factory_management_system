# production/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import json
from accounts.utils import role_required
from accounts.models import AuditLog
from core.models import ProductionSite
from core.utils import get_default_site, remember_site, site_filter_kwargs
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


def _formulation_static_context():
    """Shared JS-support context for the formulation create/edit form."""
    from catalog.models import UnitOfMeasure, RawMaterial, FinishedProduct
    from core.models import SystemParameter
    import json as _json

    rm_unit_map = {
        str(rm.pk): rm.unit_of_measure_id
        for rm in RawMaterial.objects.filter(is_active=True).select_related(
            "unit_of_measure"
        )
    }
    # SPEC S22 — per-material kg-equivalent data for the client-side
    # mass-balance preview (mirrors the existing scaling-preview pattern).
    # effective_kg_per_unit never returns None now — RM without an explicit
    # kg_equivalent_mode default to 1 unit = 1 kg.
    rm_kg_map = {
        str(rm.pk): {
            "kg_per_unit": str(rm.effective_kg_per_unit),
            "volumetric_factor": str(rm.volumetric_factor),
            "unit_symbol": rm.unit_of_measure.symbol,
        }
        for rm in RawMaterial.objects.filter(is_active=True).select_related(
            "unit_of_measure"
        )
    }
    # Finished-product → sales_unit map, used to auto-detect the
    # formulation's reference_batch_unit once a finished product is chosen.
    fp_unit_map = {
        str(fp.pk): fp.sales_unit_id
        for fp in FinishedProduct.objects.filter(is_active=True).select_related(
            "sales_unit"
        )
    }
    # Finished-product → kg-equivalent-per-sales-unit, used to auto-populate
    # "Masse cible du lot (kg)" from "Quantité de référence par lot" without
    # requiring the user to do the unit conversion by hand: target_kg =
    # reference_batch_qty * kg_per_unit. When reference_batch_unit is KG
    # itself this is just 1:1.
    fp_kg_map = {
        str(fp.pk): str(fp.effective_kg_per_unit)
        for fp in FinishedProduct.objects.filter(is_active=True)
    }
    kg_unit = UnitOfMeasure.objects.filter(code="KG", is_active=True).first()

    reconciliation_epsilon = SystemParameter.get_decimal_value(
        "reconciliation_tolerance_epsilon", Decimal("500.00")
    )
    return {
        "units_of_measure": UnitOfMeasure.objects.filter(is_active=True),
        "rm_unit_map_json": _json.dumps(rm_unit_map),
        "rm_kg_map_json": _json.dumps(rm_kg_map),
        "fp_unit_map_json": _json.dumps(fp_unit_map),
        "fp_kg_map_json": _json.dumps(fp_kg_map),
        "kg_unit_id": kg_unit.pk if kg_unit else None,
        "reconciliation_epsilon": str(reconciliation_epsilon),
    }


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
            try:
                # SPEC S22.4: compute the complement line's qty_per_batch now
                # that every sibling line and target_batch_mass_kg are saved.
                formulation.recompute_complement_quantity()
                # SPEC S22.4: re-run the mass-reconciliation check now that
                # lines exist (Formulation.clean() no-ops before the first
                # save, since self.pk was still None at form-validation time).
                formulation.clean()
            except ValidationError as e:
                messages.error(
                    request, e.message if hasattr(e, "message") else str(e)
                )
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
            return redirect(
                "production:formulation_detail", formulation_id=formulation.id
            )
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
            **_formulation_static_context(),
        },
    )


@login_required
def formulation_detail(request, formulation_id):
    formulation = get_object_or_404(Formulation, id=formulation_id)

    # SPEC S22.4 (planned) — mass-balance status shown alongside the
    # composition table when a target batch mass is defined.
    mass_balance_ok, mass_balance_status = None, None
    if formulation.target_batch_mass_kg is not None:
        complement_line = formulation.get_complement_line()
        non_complement_mass = formulation.non_complement_mass_kg
        if complement_line:
            if non_complement_mass < formulation.target_batch_mass_kg:
                mass_balance_ok = True
                mass_balance_status = "OK — complément calculé automatiquement"
            else:
                mass_balance_ok = False
                mass_balance_status = "Pas de place pour le complément"
        else:
            from core.models import SystemParameter

            epsilon = SystemParameter.get_decimal_value(
                "reconciliation_tolerance_epsilon", Decimal("500.00")
            )
            delta = abs(non_complement_mass - formulation.target_batch_mass_kg)
            mass_balance_ok = delta <= epsilon
            mass_balance_status = (
                f"OK — dans la tolérance de réconciliation ({epsilon} kg)"
                if mass_balance_ok
                else f"Écart de {delta:.3f} kg — hors tolérance ({epsilon} kg)"
            )

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
            "mass_balance_ok": mass_balance_ok,
            "mass_balance_status": mass_balance_status,
        },
    )


@login_required
@role_required(["manager"])
def formulation_edit(request, formulation_id):
    """True in-place edit of a formulation's fields and composition lines.

    SPEC BR-PROD-03: blocked (redirect + message) while any in_progress PO
    references this formulation — the form itself also disables every
    field in that state as a second guard (FormulationForm.br_prod_03_locked).
    To change a formulation that is currently locked, use "Nouvelle version"
    instead (formulation_new_version), which is unaffected by in-place edits.
    """
    formulation = get_object_or_404(Formulation, id=formulation_id)

    if formulation.has_active_production_orders():
        messages.error(
            request,
            "Impossible de modifier cette formulation : des ordres de production "
            "sont en cours (BR-PROD-03). Utilisez « Nouvelle version » à la place.",
        )
        return redirect(
            "production:formulation_detail", formulation_id=formulation.id
        )

    if request.method == "POST":
        form = FormulationForm(request.POST, instance=formulation)
        formset = FormulationLineFormSet(request.POST, instance=formulation)
        if form.is_valid() and formset.is_valid():
            formulation = form.save()
            formset.save()
            try:
                formulation.recompute_complement_quantity()
                formulation.clean()
            except ValidationError as e:
                messages.error(
                    request, e.message if hasattr(e, "message") else str(e)
                )
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="production",
                instance=formulation,
                request=request,
            )
            messages.success(
                request, f"Formulation {formulation.reference} mise à jour avec succès"
            )
            return redirect(
                "production:formulation_detail", formulation_id=formulation.id
            )
    else:
        form = FormulationForm(instance=formulation)
        formset = FormulationLineFormSet(instance=formulation)

    return render(
        request,
        "production/formulation_form.html",
        {
            "form": form,
            "formset": formset,
            "formulation": formulation,
            "title": f"Modifier — {formulation.reference}",
            **_formulation_static_context(),
        },
    )


@login_required
@role_required(["manager"])
def formulation_new_version(request, formulation_id):
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
            return redirect(
                "production:formulation_detail", formulation_id=new_formulation.id
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("production:formulation_detail", formulation_id=formulation.id)


@login_required
def production_orders_list(request):
    """
    FIX: removed .filter(yield_status=...) and .filter(yield_rate=...) ORM calls.
    yield_status and yield_rate are @property on ProductionOrder — they cannot
    be used in ORM queryset filters.
    FIX: removed reference to ProductionOrder.YIELD_STATUS_CHOICES — does not exist.
    """
    orders = ProductionOrder.objects.select_related(
        "formulation", "formulation__finished_product", "created_by", "site"
    ).filter(**site_filter_kwargs(request))

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
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
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
            remember_site(request, order.site)
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
            return redirect("production:production_order_detail", order_id=order.id)
    else:
        form = ProductionOrderForm(initial_site=get_default_site(request))

    import json as _json
    from .models import Formulation

    formulation_unit_map = {
        str(f.pk): f.reference_batch_unit_id
        for f in Formulation.objects.filter(is_active=True).select_related(
            "reference_batch_unit"
        )
    }
    return render(
        request,
        "production/production_order_form.html",
        {
            "form": form,
            "title": "Nouvel ordre de production",
            "formulation_unit_map_json": _json.dumps(formulation_unit_map),
        },
    )


@login_required
def production_order_detail(request, order_id):
    order = get_object_or_404(ProductionOrder, id=order_id)
    role = request.user.userprofile.role
    latest_formulation = (
        Formulation.objects.filter(reference=order.formulation.reference)
        .order_by("-version")
        .first()
    )
    has_newer_version = bool(
        latest_formulation and latest_formulation.version > order.formulation_version
    )
    from quality.models import SamplingPlan, QualitySpecification

    gate_b_plan = SamplingPlan.get_active_for(
        "B", finished_product=order.formulation.finished_product
    )
    gate_c_plan = SamplingPlan.get_active_for(
        "C", finished_product=order.formulation.finished_product
    )
    fp_spec = QualitySpecification.get_active_for(order.formulation.finished_product)
    gate_c_sample = order.quality_samples.filter(control_point="C").order_by("-sampled_at").first()
    open_ncrs = order.ncrs.exclude(status="closed")

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
            # BOM correction/reconciliation: only offered when a newer
            # formulation version actually exists and this order isn't
            # itself already a not-yet-actioned correction placeholder.
            "can_reconcile": role in ["manager", "stock_prod"] and has_newer_version,
            "latest_formulation": latest_formulation,
            "title": f"Ordre de Production - {order.reference}",
            # --- QA/QC Gate B/C context ---
            "gate_b_plan": gate_b_plan,
            "gate_b_checkpoints": gate_b_plan.checkpoint_label_list() if gate_b_plan else [],
            "gate_c_plan": gate_c_plan,
            "fp_quality_spec": fp_spec,
            "gate_c_sample": gate_c_sample,
            "open_ncrs": open_ncrs,
            "can_draw_gate_b_sample": request.user.userprofile.can_perform_qc()
            and order.status == "in_progress" and gate_b_plan is not None,
            "can_ack_hold": request.user.userprofile.can_lift_production_hold()
            and order.gate_b_hold and not order.gate_b_hold_acknowledged,
            "can_draw_gate_c_sample": request.user.userprofile.can_perform_qc()
            and order.status == "pending_qc_release",
            "can_release_gate_c": request.user.userprofile.can_release_gate_c()
            and order.status == "pending_qc_release",
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

    return redirect("production:production_order_detail", order_id=order.id)


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

    return redirect("production:production_order_detail", order_id=order.id)


@login_required
def production_order_acknowledge_hold(request, order_id):
    """QA/QC Gate B (§5.3): Production Manager (or QA) acknowledges a hold."""
    order = get_object_or_404(ProductionOrder, id=order_id)
    if not request.user.userprofile.can_lift_production_hold():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("production:production_order_detail", order_id=order.id)

    if request.method == "POST":
        note = request.POST.get("note", "")
        abort = request.POST.get("decision") == "abort"
        try:
            order.acknowledge_hold(request.user, note, abort=abort)
            AuditLog.log_action(
                user=request.user, action_type="update", module="production",
                instance=order, details={"action": "ack_gate_b_hold", "abort": abort},
                request=request,
            )
            messages.success(
                request,
                f"Alerte Gate B acquittée{' — OP avorté' if abort else ''}.",
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("production:production_order_detail", order_id=order.id)


@login_required
def production_order_release_gate_c(request, order_id):
    """QA/QC Gate C (§6.2): release to Completed, or open investigation."""
    order = get_object_or_404(ProductionOrder, id=order_id)
    if not request.user.userprofile.can_release_gate_c():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("production:production_order_detail", order_id=order.id)

    if request.method == "POST":
        try:
            result = order.release_gate_c(request.user)
            AuditLog.log_action(
                user=request.user, action_type="validate", module="production",
                instance=order, details={"action": "gate_c_release", "result": result},
                request=request,
            )
            if result == "completed":
                messages.success(
                    request, f"OP {order.reference} libéré — stock PF crédité."
                )
            else:
                messages.warning(
                    request,
                    f"OP {order.reference} placé sous investigation — NCR ouverte.",
                )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("production:production_order_detail", order_id=order.id)


@login_required
@role_required(["manager", "stock_prod"])
def production_order_close(request, order_id):
    """in_progress → completed"""
    order = get_object_or_404(ProductionOrder, id=order_id)

    if order.status != "in_progress":
        messages.error(request, "Cet ordre ne peut pas être clôturé")
        return redirect("production:production_order_detail", order_id=order.id)

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
                    details={"action": "close", "yield_rate": str(order.yield_rate), "status": order.status},
                    request=request,
                )
                if order.status == "pending_qc_release":
                    messages.success(
                        request,
                        f"Résultats de l'OP {order.reference} déclarés — en attente de libération QC (Gate C).",
                    )
                else:
                    messages.success(
                        request, f"Ordre de production {order.reference} clôturé"
                    )
                return redirect("production:production_order_detail", order_id=order.id)
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


# ─── BOM correction / reconciliation ────────────────────────────────────────


@login_required
@role_required(["manager", "stock_prod"])
def production_order_reconcile(request, order_id):
    """Reconcile an old production order's BOM against a newer formulation
    version. Creates a brand-new correction ProductionOrder linked back to
    the original via corrects_order — the original is never modified.

    The new correction order's consumption lines are pre-filled by scaling
    the new formulation's ratios to the (re-specified) target quantity —
    same scaling convention as ProductionOrder._create_consumption_lines()
    — but every line is editable before submission so operators can adjust
    the suggested values by hand.
    """
    old_order = get_object_or_404(ProductionOrder, id=order_id)
    old_formulation = old_order.formulation

    latest_formulation = (
        Formulation.objects.filter(reference=old_formulation.reference)
        .order_by("-version")
        .first()
    )
    if not latest_formulation or latest_formulation.version <= old_order.formulation_version:
        messages.info(
            request,
            "Aucune version plus récente de cette formulation n'est disponible pour réconciliation.",
        )
        return redirect("production:production_order_detail", order_id=old_order.id)
    new_formulation = latest_formulation

    old_lines = {
        line.raw_material_id: line
        for line in old_order.consumption_lines.select_related(
            "raw_material", "raw_material__unit_of_measure"
        ).all()
    }
    new_lines = list(
        new_formulation.lines.select_related(
            "raw_material", "unit_of_measure"
        ).all()
    )
    new_lines_by_rm = {fl.raw_material_id: fl for fl in new_lines}

    default_target_qty = old_order.actual_qty_produced or old_order.target_qty

    if request.method == "POST":
        try:
            target_qty = Decimal(request.POST.get("target_qty", "0"))
        except InvalidOperation:
            target_qty = Decimal("0")

        if target_qty <= 0:
            messages.error(request, "La quantité cible doit être supérieure à zéro.")
        else:
            scale = target_qty / new_formulation.reference_batch_qty
            new_order = ProductionOrder(
                formulation=new_formulation,
                formulation_version=new_formulation.version,
                target_qty=target_qty,
                target_unit=old_order.target_unit,
                launch_date=timezone.now().date(),
                status="pending",
                corrects_order=old_order,
                created_by=request.user,
                notes=(
                    f"Correction de {old_order.reference} — formulation "
                    f"{old_formulation.reference} v{old_order.formulation_version} "
                    f"\u2192 v{new_formulation.version}."
                ),
            )
            new_order.save()

            for fl in new_lines:
                field_name = f"line_qty_{fl.raw_material_id}"
                raw_val = request.POST.get(field_name, "").strip()
                try:
                    qty = Decimal(raw_val) if raw_val else fl.qty_per_batch * scale
                except InvalidOperation:
                    qty = fl.qty_per_batch * scale
                if qty < 0:
                    qty = Decimal("0.000")
                ProductionOrderLine.objects.create(
                    production_order=new_order,
                    raw_material=fl.raw_material,
                    qty_theoretical=qty,
                    tolerance_pct=fl.tolerance_pct,
                )

            AuditLog.log_action(
                user=request.user,
                action_type="create",
                module="production",
                instance=new_order,
                details={
                    "corrects_order": old_order.reference,
                    "target_qty": str(target_qty),
                    "new_formulation_version": new_formulation.version,
                },
                request=request,
            )
            messages.success(
                request,
                f"Ordre de correction {new_order.reference} créé, lié à {old_order.reference}.",
            )
            return redirect(
                "production:production_order_detail", order_id=new_order.id
            )

    # ------------------------------------------------------------------
    # Server-rendered preview at the default target qty (JS recomputes the
    # "suggested" column live as the user edits the target qty input).
    # ------------------------------------------------------------------
    scale_default = (
        default_target_qty / new_formulation.reference_batch_qty
        if new_formulation.reference_batch_qty
        else Decimal("0")
    )
    rows = []
    for rm_id in set(old_lines.keys()) | set(new_lines_by_rm.keys()):
        old_line = old_lines.get(rm_id)
        new_line = new_lines_by_rm.get(rm_id)
        if new_line:
            status_flag = "kept" if old_line else "added"
            suggested = (new_line.qty_per_batch * scale_default).quantize(Decimal("0.001"))
            raw_material = new_line.raw_material
            unit_symbol = new_line.unit_of_measure.symbol
            tolerance_pct = new_line.tolerance_pct
        else:
            status_flag = "removed"
            suggested = None
            raw_material = old_line.raw_material
            unit_symbol = old_line.raw_material.unit_of_measure.symbol
            tolerance_pct = None
        old_qty = None
        if old_line is not None:
            old_qty = (
                old_line.qty_actual
                if old_line.qty_actual is not None
                else old_line.qty_theoretical
            )
        rows.append(
            {
                "raw_material_id": rm_id,
                "raw_material": raw_material,
                "old_qty": old_qty,
                "suggested_qty": suggested,
                "unit_symbol": unit_symbol,
                "tolerance_pct": tolerance_pct,
                "status": status_flag,
            }
        )
    status_order = {"kept": 0, "added": 1, "removed": 2}
    rows.sort(key=lambda r: (status_order[r["status"]], r["raw_material"].designation))

    new_lines_json = json.dumps(
        [
            {
                "rm_id": fl.raw_material_id,
                "qty_per_batch": str(fl.qty_per_batch),
            }
            for fl in new_lines
        ]
    )

    return render(
        request,
        "production/production_order_reconcile.html",
        {
            "old_order": old_order,
            "old_formulation": old_formulation,
            "new_formulation": new_formulation,
            "rows": rows,
            "default_target_qty": default_target_qty,
            "reference_batch_qty": new_formulation.reference_batch_qty,
            "new_lines_json": new_lines_json,
            "title": f"Correction — {old_order.reference}",
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

                # First pass: compute theoretical qty + kg equivalent per line,
                # so we can derive each material's % share of the total batch
                # mass (kg) once every line's contribution is known.
                raw_lines = []
                total_kg = Decimal("0.000")
                for line in formulation.lines.all():
                    theoretical_qty = line.qty_per_batch * scaling_factor
                    kg_per_unit = line.raw_material.effective_kg_per_unit
                    kg_qty = (
                        theoretical_qty * kg_per_unit
                        if kg_per_unit is not None
                        else None
                    )
                    if kg_qty is not None:
                        total_kg += kg_qty
                    raw_lines.append((line, theoretical_qty, kg_qty))

                lines_data = []
                for line, theoretical_qty, kg_qty in raw_lines:
                    try:
                        balance = RawMaterialStockBalance.objects.get(
                            raw_material=line.raw_material
                        )
                        available_qty = balance.quantity
                    except RawMaterialStockBalance.DoesNotExist:
                        available_qty = Decimal("0.000")

                    if kg_qty is not None and total_kg > 0:
                        percentage = (kg_qty / total_kg) * Decimal("100")
                    else:
                        percentage = None

                    lines_data.append(
                        {
                            "material_id": line.raw_material.id,
                            "material_name": line.raw_material.designation,
                            "theoretical_qty": str(theoretical_qty),
                            "unit": line.unit_of_measure.symbol,
                            "kg_qty": str(kg_qty) if kg_qty is not None else None,
                            "percentage": str(percentage) if percentage is not None else None,
                            "available_qty": str(available_qty),
                            "sufficient": available_qty >= theoretical_qty,
                        }
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "scaling_factor": str(scaling_factor),
                        "total_kg": str(total_kg) if total_kg > 0 else None,
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
