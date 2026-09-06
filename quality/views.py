# quality/views.py
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import AuditLog
from accounts.utils import role_required
from production.models import ProductionOrder
from supplier_ops.models import SupplierDNLine

from .forms import (
    NCRDispositionForm,
    PropertyForm,
    QualitySpecificationForm,
    QualitySpecLineFormSet,
    SampleDrawForm,
    SamplingPlanForm,
)
from .models import (
    NonConformityReport,
    Property,
    QualitySpecification,
    Sample,
    SamplingPlan,
    TestResult,
)

QC_ROLES = ["qa_manager", "qc_technician", "manager"]
QA_ROLES = ["qa_manager", "manager"]


def _qc_gate_access(user):
    return hasattr(user, "userprofile") and user.userprofile.can_perform_qc()


# ---------------------------------------------------------------------------
# Sample Register
# ---------------------------------------------------------------------------
@login_required
def sample_register(request):
    if not request.user.userprofile.can_view_quality_dashboard():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("core:dashboard")

    samples = Sample.objects.select_related(
        "quality_specification", "sampled_by"
    ).order_by("-sampled_at")

    gate = request.GET.get("gate")
    if gate in ("A", "B", "C"):
        samples = samples.filter(control_point=gate)
    status = request.GET.get("status")
    if status:
        samples = samples.filter(status=status)
    if request.user.userprofile.role == "qc_technician":
        samples = samples.filter(sampled_by=request.user)

    return render(
        request,
        "quality/sample_register.html",
        {
            "samples": samples[:300],
            "title": "Registre des échantillons",
            "status_choices": Sample.STATUS_CHOICES,
        },
    )


@login_required
def sample_detail(request, sample_id):
    sample = get_object_or_404(
        Sample.objects.select_related("quality_specification", "sampled_by"), pk=sample_id
    )
    results = sample.results.select_related("spec_line__property", "recorded_by")
    return render(
        request,
        "quality/sample_detail.html",
        {
            "sample": sample,
            "results": results,
            "title": f"Échantillon {sample.reference}",
            "can_override": request.user.userprofile.can_override_qc_result(),
            "can_enter_results": _qc_gate_access(request.user)
            and sample.status in ("draft", "results_pending"),
        },
    )


# ---------------------------------------------------------------------------
# Gate A — draw a sample from a Supplier DN line
# ---------------------------------------------------------------------------
@login_required
def gate_a_sample_draw(request, dn_line_id):
    line = get_object_or_404(
        SupplierDNLine.objects.select_related("supplier_dn", "raw_material", "unit_of_measure"),
        pk=dn_line_id,
    )
    if not _qc_gate_access(request.user):
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("supplier_ops:supplier_dn_detail", dn_id=line.supplier_dn_id)

    spec = QualitySpecification.get_active_for(line.raw_material)
    if spec is None:
        messages.error(
            request,
            f"Aucune spécification qualité active pour {line.raw_material.designation} — "
            "impossible de prélever un échantillon Gate A.",
        )
        return redirect("supplier_ops:supplier_dn_detail", dn_id=line.supplier_dn_id)

    if request.method == "POST":
        form = SampleDrawForm(request.POST)
        form.fields["quality_specification"].queryset = QualitySpecification.objects.filter(pk=spec.pk)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.control_point = "A"
            sample.supplier_dn_line = line
            sample.sampled_by = request.user
            sample.status = "results_pending"
            sample.save()
            AuditLog.log_action(
                user=request.user, action_type="create", module="quality",
                instance=sample, details={"gate": "A", "dn_line": line.id}, request=request,
            )
            messages.success(request, f"Échantillon {sample.reference} créé (Gate A).")
            return redirect("quality:sample_result_entry", sample_id=sample.id)
    else:
        form = SampleDrawForm(initial={"quality_specification": spec, "unit": line.unit_of_measure})
        form.fields["quality_specification"].queryset = QualitySpecification.objects.filter(pk=spec.pk)

    return render(
        request,
        "quality/sample_draw.html",
        {"form": form, "line": line, "gate": "A", "title": "Prélever un échantillon — Gate A"},
    )


# ---------------------------------------------------------------------------
# Gate B / C — draw a sample from a Production Order
# ---------------------------------------------------------------------------
@login_required
def gate_bc_sample_draw(request, order_id, gate):
    order = get_object_or_404(ProductionOrder, pk=order_id)
    if gate not in ("B", "C") or not _qc_gate_access(request.user):
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("production:production_order_detail", order_id=order.id)

    fp = order.formulation.finished_product
    spec = QualitySpecification.get_active_for(fp)
    if spec is None:
        messages.error(
            request,
            f"Aucune spécification qualité active pour {fp.designation} — "
            f"impossible de prélever un échantillon Gate {gate}.",
        )
        return redirect("production:production_order_detail", order_id=order.id)

    if request.method == "POST":
        form = SampleDrawForm(request.POST)
        form.fields["quality_specification"].queryset = QualitySpecification.objects.filter(pk=spec.pk)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.control_point = gate
            sample.production_order = order
            sample.sampled_by = request.user
            sample.status = "results_pending"
            sample.save()
            AuditLog.log_action(
                user=request.user, action_type="create", module="quality",
                instance=sample, details={"gate": gate, "production_order": order.id}, request=request,
            )
            messages.success(request, f"Échantillon {sample.reference} créé (Gate {gate}).")
            return redirect("quality:sample_result_entry", sample_id=sample.id)
    else:
        form = SampleDrawForm(initial={"quality_specification": spec})
        form.fields["quality_specification"].queryset = QualitySpecification.objects.filter(pk=spec.pk)

    plan = SamplingPlan.get_active_for(gate, finished_product=fp)
    checkpoints = plan.checkpoint_label_list() if (plan and gate == "B") else []

    return render(
        request,
        "quality/sample_draw.html",
        {
            "form": form, "order": order, "gate": gate,
            "checkpoints": checkpoints,
            "title": f"Prélever un échantillon — Gate {gate}",
        },
    )


# ---------------------------------------------------------------------------
# Result entry — generic for any gate
# ---------------------------------------------------------------------------
@login_required
def sample_result_entry(request, sample_id):
    sample = get_object_or_404(Sample, pk=sample_id)
    if not _qc_gate_access(request.user):
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:sample_detail", sample_id=sample.id)

    spec_lines = list(sample.spec_lines_for_gate().select_related("property"))
    existing = {r.spec_line_id: r for r in sample.results.all()}

    if request.method == "POST":
        if not spec_lines:
            # Nothing to record: the active specification for this target has
            # no line for this gate (e.g. an empty/duplicate specification —
            # see QualitySpecification's version-uniqueness constraint). Do
            # NOT call compute_outcome() or log an audit entry for a save that
            # stored nothing, and do not show a success message.
            messages.error(
                request,
                "Aucun résultat enregistré : la spécification active pour "
                "cette cible ne contient aucune ligne pour ce point de "
                "contrôle. Vérifiez la spécification qualité (Configuration "
                "› Spécifications qualité) avant de ressaisir les résultats.",
            )
            return redirect("quality:sample_result_entry", sample_id=sample.id)

        for line in spec_lines:
            raw_value = request.POST.get(f"value_{line.id}", "").strip()
            instrument = request.POST.get(f"instrument_{line.id}", "").strip()
            if not raw_value:
                continue
            numeric_value = None
            try:
                numeric_value = Decimal(raw_value)
            except (InvalidOperation, ValueError):
                numeric_value = None

            result, _created = TestResult.objects.update_or_create(
                sample=sample, spec_line=line,
                defaults={
                    "recorded_value": raw_value,
                    "recorded_numeric": numeric_value,
                    "instrument_method": instrument,
                    "recorded_by": request.user,
                    "outcome": line.evaluate(numeric_value, raw_value),
                },
            )
        outcome = sample.compute_outcome()
        AuditLog.log_action(
            user=request.user, action_type="update", module="quality",
            instance=sample, details={"action": "results_recorded", "outcome": outcome},
            request=request,
        )

        # Gate B: a non-conforming in-process sample raises the advisory hold.
        if sample.control_point == "B" and outcome == "non_conforming" and sample.production_order:
            failing = ", ".join(
                r.spec_line.property.name for r in sample.results.filter(outcome="fail", qa_override=False)
            )
            sample.production_order.record_checkpoint_hold(
                f"Échantillon {sample.reference} ({sample.checkpoint_label or 'point de contrôle'}) "
                f"non conforme : {failing}."
            )

        messages.success(request, f"Résultats enregistrés — échantillon {outcome.replace('_', ' ')}.")
        return redirect("quality:sample_detail", sample_id=sample.id)

    return render(
        request,
        "quality/sample_result_entry.html",
        {
            "sample": sample,
            "spec_lines": spec_lines,
            "existing": existing,
            "title": f"Saisie des résultats — {sample.reference}",
        },
    )


@login_required
def result_qa_override(request, result_id):
    result = get_object_or_404(TestResult, pk=result_id)
    if not request.user.userprofile.can_override_qc_result():
        messages.error(request, "Seul un Responsable QA peut accorder une dérogation (BR-QA-08).")
        return redirect("quality:sample_detail", sample_id=result.sample_id)

    if request.method == "POST":
        justification = request.POST.get("justification", "")
        try:
            result.apply_qa_override(request.user, justification)
            AuditLog.log_action(
                user=request.user, action_type="update", module="quality",
                instance=result, details={"action": "qa_override"}, request=request,
            )
            messages.success(request, "Dérogation QA appliquée.")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect("quality:sample_detail", sample_id=result.sample_id)


# ---------------------------------------------------------------------------
# Non-Conformity Reports
# ---------------------------------------------------------------------------
@login_required
def ncr_list(request):
    if not request.user.userprofile.can_view_quality_dashboard():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("core:dashboard")

    ncrs = NonConformityReport.objects.select_related("sample", "production_order", "opened_by")
    status = request.GET.get("status")
    if status:
        ncrs = ncrs.filter(status=status)
    gate = request.GET.get("gate")
    if gate in ("A", "B", "C"):
        ncrs = ncrs.filter(gate=gate)

    return render(
        request,
        "quality/ncr_list.html",
        {"ncrs": ncrs[:300], "title": "Non-Conformités (NCR)", "status_choices": NonConformityReport.STATUS_CHOICES},
    )


@login_required
def ncr_detail(request, ncr_id):
    ncr = get_object_or_404(NonConformityReport, pk=ncr_id)
    can_disposition = request.user.userprofile.can_close_ncr() and ncr.status in ("open", "under_review")
    can_close = request.user.userprofile.can_close_ncr() and ncr.status == "dispositioned"

    if request.method == "POST" and "disposition_submit" in request.POST:
        if not can_disposition:
            messages.error(request, "Accès non autorisé.")
            return redirect("quality:ncr_detail", ncr_id=ncr.id)
        form = NCRDispositionForm(request.POST, request.FILES)
        if form.is_valid():
            proof = form.cleaned_data.get("proof_document")
            if proof:
                from core.models import PieceJointe

                PieceJointe.objects.create(
                    content_object=ncr, type_document=PieceJointe.TYPE_SD_CORR,
                    description=f"Justificatif NCR {ncr.reference}", fichier=proof,
                    uploaded_by=request.user,
                )
            try:
                ncr.disposition_action(
                    request.user,
                    disposition=form.cleaned_data["disposition"],
                    corrective_action=form.cleaned_data["corrective_action"],
                    root_cause_category=form.cleaned_data["root_cause_category"],
                    root_cause_detail=form.cleaned_data["root_cause_detail"],
                )
                AuditLog.log_action(
                    user=request.user, action_type="update", module="quality",
                    instance=ncr, details={"action": "disposition", "disposition": ncr.disposition},
                    request=request,
                )
                messages.success(request, f"NCR {ncr.reference} dispositionnée.")
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("quality:ncr_detail", ncr_id=ncr.id)

    if request.method == "POST" and "close_submit" in request.POST:
        try:
            ncr.close(request.user)
            AuditLog.log_action(
                user=request.user, action_type="validate", module="quality",
                instance=ncr, details={"action": "close"}, request=request,
            )
            messages.success(request, f"NCR {ncr.reference} clôturée.")

            # If this NCR closes out a Gate C investigation, resolve the order.
            if ncr.production_order and ncr.production_order.status == "completed_investigation":
                ncr.production_order.resolve_investigation(request.user, ncr.disposition)
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("quality:ncr_detail", ncr_id=ncr.id)

    form = NCRDispositionForm(initial={
        "corrective_action": ncr.corrective_action,
        "disposition": ncr.disposition,
        "root_cause_category": ncr.root_cause_category,
        "root_cause_detail": ncr.root_cause_detail,
    })

    return render(
        request,
        "quality/ncr_detail.html",
        {
            "ncr": ncr, "form": form, "can_disposition": can_disposition, "can_close": can_close,
            "title": f"NCR {ncr.reference}",
        },
    )


# ---------------------------------------------------------------------------
# Section 11 — QA Dashboard
# ---------------------------------------------------------------------------
@login_required
def quality_dashboard(request):
    if not request.user.userprofile.can_view_quality_dashboard():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("core:dashboard")

    is_qc_only = request.user.userprofile.role == "qc_technician"
    period_start = timezone.now() - timedelta(days=30)

    samples_qs = Sample.objects.filter(sampled_at__gte=period_start)
    ncrs_qs = NonConformityReport.objects.all()
    if is_qc_only:
        samples_qs = samples_qs.filter(sampled_by=request.user)
        ncrs_qs = ncrs_qs.filter(opened_by=request.user)

    total_samples = samples_qs.count()
    first_pass_conforming = samples_qs.filter(
        status="conforming"
    ).exclude(results__qa_override=True).count()
    first_pass_yield = round(100 * first_pass_conforming / total_samples, 1) if total_samples else None

    by_gate = (
        samples_qs.values("control_point")
        .annotate(total=Count("id"), conforming=Count("id", filter=Q(status="conforming")))
        .order_by("control_point")
    )

    open_ncrs = ncrs_qs.exclude(status="closed")
    ncr_aging = []
    for ncr in open_ncrs.select_related("opened_by").order_by("created_at")[:20]:
        age_days = (timezone.now() - ncr.created_at).days
        ncr_aging.append({"ncr": ncr, "age_days": age_days, "over_sla": age_days > 7})

    ncr_by_root_cause = (
        ncrs_qs.exclude(root_cause_category="")
        .values("root_cause_category")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    failing_properties = (
        TestResult.objects.filter(sample__sampled_at__gte=period_start, outcome="fail")
        .values("spec_line__property__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    supplier_ncrs = (
        ncrs_qs.filter(gate="A", supplier_dn_line__isnull=False)
        .values("supplier_dn_line__supplier_dn__supplier__raison_sociale")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    # Everything in this module (which gates are enforced, which forms even
    # appear elsewhere in the app) is driven entirely by whether Property /
    # QualitySpecification / SamplingPlan records exist (BR-QA-01). Surface
    # that configuration state directly so an empty module is explained,
    # not just silent.
    active_plans_count = SamplingPlan.objects.filter(is_active=True).count()
    active_specs_count = QualitySpecification.objects.filter(is_active=True).count()
    properties_count = Property.objects.filter(is_active=True).count()
    can_configure = request.user.userprofile.can_manage_quality_standards()

    return render(
        request,
        "quality/dashboard.html",
        {
            "title": "Tableau de bord Qualité",
            "period_days": 30,
            "total_samples": total_samples,
            "first_pass_yield": first_pass_yield,
            "by_gate": by_gate,
            "open_ncrs_count": open_ncrs.count(),
            "ncr_aging": ncr_aging,
            "ncr_by_root_cause": ncr_by_root_cause,
            "failing_properties": failing_properties,
            "supplier_ncrs": supplier_ncrs,
            "is_qc_only": is_qc_only,
            "active_plans_count": active_plans_count,
            "active_specs_count": active_specs_count,
            "properties_count": properties_count,
            "can_configure": can_configure,
            "nothing_configured": active_plans_count == 0 and active_specs_count == 0,
        },
    )


# ---------------------------------------------------------------------------
# Configuration CRUD — Property / Test Catalogue
# ---------------------------------------------------------------------------
@login_required
def property_list(request):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    properties = Property.objects.all().order_by("name")
    return render(
        request,
        "quality/property_list.html",
        {"title": "Catalogue Propriétés / Tests", "properties": properties},
    )


@login_required
def property_form(request, property_id=None):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")

    instance = get_object_or_404(Property, pk=property_id) if property_id else None
    if request.method == "POST":
        form = PropertyForm(request.POST, instance=instance)
        if form.is_valid():
            prop = form.save(commit=False)
            if not instance:
                prop.created_by = request.user
            prop.save()
            AuditLog.log_action(
                user=request.user, action_type="update" if instance else "create",
                module="quality", instance=prop,
                details={"action": "property_saved"}, request=request,
            )
            messages.success(request, f"Propriété « {prop.name} » enregistrée.")
            return redirect("quality:property_list")
    else:
        form = PropertyForm(instance=instance)

    return render(
        request,
        "quality/property_form.html",
        {
            "title": "Modifier la propriété" if instance else "Nouvelle propriété",
            "form": form,
            "instance": instance,
        },
    )


@login_required
def property_toggle_active(request, property_id):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    prop = get_object_or_404(Property, pk=property_id)
    if request.method == "POST":
        prop.is_active = not prop.is_active
        prop.save(update_fields=["is_active"])
        AuditLog.log_action(
            user=request.user, action_type="update", module="quality", instance=prop,
            details={"action": "toggle_active", "is_active": prop.is_active}, request=request,
        )
        messages.success(
            request,
            f"Propriété « {prop.name} » {'réactivée' if prop.is_active else 'désactivée'}.",
        )
    return redirect("quality:property_list")


# ---------------------------------------------------------------------------
# Configuration CRUD — Quality Specifications (+ lines)
# ---------------------------------------------------------------------------
@login_required
def specification_list(request):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    specs = (
        QualitySpecification.objects.select_related("raw_material", "finished_product")
        .prefetch_related("lines")
        .order_by("-is_active", "-effective_date", "-version")
    )
    return render(
        request,
        "quality/specification_list.html",
        {"title": "Spécifications qualité", "specs": specs},
    )


@login_required
def specification_form(request, spec_id=None):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")

    instance = get_object_or_404(QualitySpecification, pk=spec_id) if spec_id else None
    if request.method == "POST":
        form = QualitySpecificationForm(request.POST, instance=instance)
        # The formset needs a saved parent instance to bind to; for a brand
        # new specification we validate the parent form first, save it
        # (without committing lines yet), then bind the formset to it —
        # mirrors the same two-step pattern production.formulation_create
        # already uses for Formulation + FormulationLine.
        if form.is_valid():
            spec = form.save(commit=False)
            if not instance:
                spec.created_by = request.user
            spec.save()
            formset = QualitySpecLineFormSet(request.POST, instance=spec)
            if formset.is_valid():
                formset.save()
                AuditLog.log_action(
                    user=request.user, action_type="update" if instance else "create",
                    module="quality", instance=spec,
                    details={"action": "specification_saved"}, request=request,
                )
                messages.success(request, f"Spécification « {spec} » enregistrée.")
                return redirect("quality:specification_list")
        else:
            formset = QualitySpecLineFormSet(
                request.POST, instance=instance or QualitySpecification()
            )
    else:
        form = QualitySpecificationForm(instance=instance)
        formset = QualitySpecLineFormSet(instance=instance)

    return render(
        request,
        "quality/specification_form.html",
        {
            "title": "Modifier la spécification" if instance else "Nouvelle spécification qualité",
            "form": form,
            "formset": formset,
            "instance": instance,
            "properties_exist": Property.objects.filter(is_active=True).exists(),
        },
    )


@login_required
def specification_toggle_active(request, spec_id):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    spec = get_object_or_404(QualitySpecification, pk=spec_id)
    if request.method == "POST":
        spec.is_active = not spec.is_active
        spec.save(update_fields=["is_active"])
        AuditLog.log_action(
            user=request.user, action_type="update", module="quality", instance=spec,
            details={"action": "toggle_active", "is_active": spec.is_active}, request=request,
        )
        messages.success(
            request, f"Spécification « {spec} » {'réactivée' if spec.is_active else 'désactivée'}."
        )
    return redirect("quality:specification_list")


# ---------------------------------------------------------------------------
# Configuration CRUD — Sampling Plans
# ---------------------------------------------------------------------------
@login_required
def sampling_plan_list(request):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    plans = (
        SamplingPlan.objects.select_related("raw_material", "finished_product")
        .order_by("control_point", "-is_active", "-created_at")
    )
    return render(
        request,
        "quality/sampling_plan_list.html",
        {"title": "Plans d'échantillonnage", "plans": plans},
    )


@login_required
def sampling_plan_form(request, plan_id=None):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")

    instance = get_object_or_404(SamplingPlan, pk=plan_id) if plan_id else None
    if request.method == "POST":
        form = SamplingPlanForm(request.POST, instance=instance)
        if form.is_valid():
            plan = form.save(commit=False)
            if not instance:
                plan.created_by = request.user
            plan.save()
            AuditLog.log_action(
                user=request.user, action_type="update" if instance else "create",
                module="quality", instance=plan,
                details={"action": "sampling_plan_saved"}, request=request,
            )
            messages.success(request, f"Plan d'échantillonnage « {plan} » enregistré.")
            return redirect("quality:sampling_plan_list")
    else:
        form = SamplingPlanForm(instance=instance)

    return render(
        request,
        "quality/sampling_plan_form.html",
        {
            "title": "Modifier le plan" if instance else "Nouveau plan d'échantillonnage",
            "form": form,
            "instance": instance,
        },
    )


@login_required
def sampling_plan_toggle_active(request, plan_id):
    if not request.user.userprofile.can_manage_quality_standards():
        messages.error(request, "Accès non autorisé pour votre rôle")
        return redirect("quality:quality_dashboard")
    plan = get_object_or_404(SamplingPlan, pk=plan_id)
    if request.method == "POST":
        reason = request.POST.get("deactivated_reason", "").strip()
        plan.is_active = not plan.is_active
        if not plan.is_active and reason:
            # BR-QA-12: deactivating a plan should record why.
            plan.deactivated_reason = reason
        plan.save(update_fields=["is_active", "deactivated_reason"])
        AuditLog.log_action(
            user=request.user, action_type="update", module="quality", instance=plan,
            details={"action": "toggle_active", "is_active": plan.is_active}, request=request,
        )
        messages.success(
            request, f"Plan « {plan} » {'réactivé' if plan.is_active else 'désactivé'}."
        )
    return redirect("quality:sampling_plan_list")
