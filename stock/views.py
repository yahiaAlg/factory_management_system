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
from core.models import ProductionSite
from core.utils import (
    get_default_site,
    remember_site,
    site_scope_kwargs,
    site_form_kwargs,
    require_site_context,
    site_object_or_404,
)
from .models import (
    RawMaterialStockBalance,
    FinishedProductStockBalance,
    StockMovement,
    StockAdjustment,
    StockAdjustmentLine,
)
from .forms import (
    StockAdjustmentForm,
    StockAdjustmentLineFormSet,
    StockAdjustmentSupportingDocForm,
)


@login_required
def raw_materials_stock_list(request):
    # functional spec §25.2.4: "Site / All Sites" filter — no filter (all
    # sites, each shown as its own row) when the GET param is absent/"all".
    balances = RawMaterialStockBalance.objects.select_related(
        "raw_material", "raw_material__category", "raw_material__unit_of_measure", "site"
    ).filter(**site_scope_kwargs(request))
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
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Stock matières premières",
        },
    )


@login_required
def finished_products_stock_list(request):
    balances = FinishedProductStockBalance.objects.select_related(
        "finished_product", "finished_product__sales_unit", "site"
    ).filter(**site_scope_kwargs(request))
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
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Stock produits finis",
        },
    )


@login_required
def stock_movements_list(request):
    movements = StockMovement.objects.select_related(
        "raw_material", "finished_product", "created_by", "site"
    ).filter(**site_scope_kwargs(request))
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
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Historique des mouvements",
        },
    )


@login_required
def raw_material_stock_detail(request, material_id):
    from catalog.models import RawMaterial

    material = get_object_or_404(RawMaterial, id=material_id)
    # One row per site (§25.2.3) — the detail page shows every site's
    # balance side by side rather than a single company-wide figure.
    balances = RawMaterialStockBalance.objects.select_related("site").filter(
        raw_material=material
    )
    movements = StockMovement.objects.filter(raw_material=material).select_related(
        "site"
    ).order_by("-movement_date", "-created_at")[:50]
    total_qty = material.get_current_stock()
    return render(
        request,
        "stock/raw_material_stock_detail.html",
        {
            "material": material,
            "balances": balances,
            "current_qty": total_qty,
            "movements": movements,
            "stock_status": material.get_stock_status(),
            "stock_value": total_qty * material.reference_price,
            "title": f"Stock - {material.designation}",
        },
    )


@login_required
def finished_product_stock_detail(request, product_id):
    from catalog.models import FinishedProduct

    product = get_object_or_404(FinishedProduct, id=product_id)
    balances = FinishedProductStockBalance.objects.select_related("site").filter(
        finished_product=product
    )
    movements = StockMovement.objects.filter(finished_product=product).select_related(
        "site"
    ).order_by("-movement_date", "-created_at")[:50]
    qty = product.get_current_stock()
    wac = product.get_wac()
    stock_value = sum(b.get_stock_value() for b in balances)
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
            "balances": balances,
            "current_qty": qty,
            "movements": movements,
            "stock_status": product.get_stock_status(),
            "stock_value": stock_value,
            "wac": wac,
            "unit_margin": unit_margin,
            "margin_rate": margin_rate,
            "title": f"Stock - {product.designation}",
        },
    )


@login_required
def stock_adjustments_list(request):
    from core.models import ProductionSite

    adjustments = StockAdjustment.objects.select_related(
        "created_by", "approved_by", "site"
    ).filter(**site_scope_kwargs(request))
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
            "sites": ProductionSite.objects.filter(is_active=True),
            "selected_site": request.GET.get("site", "all"),
            "title": "Ajustements de stock",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
@require_site_context
def stock_adjustment_create(request):
    from core.models import ProductionSite

    if request.method == "POST":
        # The line formset's clean() needs the parent's site (§25.2.3) to
        # look up the right per-site balance for quantity_before, so we
        # resolve it from the raw POST data before building the formset.
        # For a role-locked user (stock_prod), site_form_kwargs already
        # forces this to their own site server-side via SiteLockedFormMixin
        # regardless of the raw POST value, so this is only the *display*
        # site used for the formset's balance lookups.
        posted_site = ProductionSite.objects.filter(pk=request.POST.get("site")).first()
        form_kwargs = site_form_kwargs(request)
        site_for_formset = form_kwargs.get("site") or posted_site
        form = StockAdjustmentForm(request.POST, **form_kwargs)
        formset = StockAdjustmentLineFormSet(
            request.POST, form_kwargs={"site": site_for_formset}
        )
        # Optional inline attachment: only build/validate the doc sub-form
        # when a file was actually provided, keeping the upload optional.
        doc_form = (
            StockAdjustmentSupportingDocForm(request.POST, request.FILES)
            if request.FILES.get("file")
            else None
        )
        if (
            form.is_valid()
            and formset.is_valid()
            and (doc_form is None or doc_form.is_valid())
        ):
            adjustment = form.save(commit=False)
            adjustment.created_by = request.user
            adjustment.save()
            formset.instance = adjustment
            formset.save()
            remember_site(request, adjustment.site)
            if doc_form is not None:
                from core.models import PieceJointe

                PieceJointe.objects.create(
                    content_object=adjustment,
                    type_document=doc_form.cleaned_data["doc_type"],
                    description=doc_form.cleaned_data["description"],
                    fichier=doc_form.cleaned_data.get("file"),
                    uploaded_by=request.user,
                )
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
        default_site = get_default_site(request)
        form = StockAdjustmentForm(**site_form_kwargs(request))
        formset = StockAdjustmentLineFormSet(form_kwargs={"site": default_site})
        doc_form = StockAdjustmentSupportingDocForm()
    return render(
        request,
        "stock/stock_adjustment_form.html",
        {
            "form": form,
            "formset": formset,
            "doc_form": doc_form,
            "title": "Nouvel ajustement de stock",
        },
    )


@login_required
def stock_adjustment_detail(request, adjustment_id):
    adjustment = site_object_or_404(request, StockAdjustment, id=adjustment_id)
    supporting_docs = adjustment.pieces_jointes.select_related("uploaded_by").order_by(
        "-created_at"
    )
    return render(
        request,
        "stock/stock_adjustment_detail.html",
        {
            "adjustment": adjustment,
            "lines": adjustment.lines.all(),
            "supporting_docs": supporting_docs,
            "can_approve": request.user.userprofile.role == "manager"
            and not adjustment.approved_by,
            "title": f"Ajustement - {adjustment.reference}",
        },
    )


@login_required
@role_required(["manager", "stock_prod"])
def stock_adjustment_add_document(request, adjustment_id):
    """Attach a PieceJointe to a StockAdjustment (optional, no gate — mirrors
    client_dn_add_document / supplier_dn_add_document)."""
    adjustment = site_object_or_404(request, StockAdjustment, pk=adjustment_id)
    if request.method == "POST":
        form = StockAdjustmentSupportingDocForm(request.POST, request.FILES)
        if form.is_valid():
            from core.models import PieceJointe

            PieceJointe.objects.create(
                content_object=adjustment,
                type_document=form.cleaned_data["doc_type"],
                description=form.cleaned_data["description"],
                fichier=form.cleaned_data.get("file"),
                uploaded_by=request.user,
            )
            AuditLog.log_action(
                user=request.user,
                action_type="update",
                module="stock",
                instance=adjustment,
                details={"document_added": form.cleaned_data["doc_type"]},
                request=request,
            )
            messages.success(request, "Document justificatif ajouté avec succès.")
            return redirect(
                "stock:stock_adjustment_detail", adjustment_id=adjustment.pk
            )
    else:
        form = StockAdjustmentSupportingDocForm()
    return render(
        request,
        "stock/stock_adjustment_add_document.html",
        {
            "form": form,
            "adjustment": adjustment,
            "title": f"Ajouter un justificatif — {adjustment.reference}",
        },
    )


@login_required
@role_required(["manager"])
def stock_adjustment_approve(request, adjustment_id):
    adjustment = site_object_or_404(request, StockAdjustment, id=adjustment_id)
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
        # functional spec §25.2.3: stock is now per-site. When the caller
        # (a create form) knows which site it's working in, pass site_id
        # to check that site's own balance; otherwise fall back to the
        # company-wide total across every site.
        site_id = request.GET.get("site_id")
        if material_type and material_id and required_qty:
            try:
                required_qty = Decimal(required_qty)
                if material_type == "finished_product":
                    from catalog.models import FinishedProduct

                    material = get_object_or_404(FinishedProduct, id=material_id)
                    current_stock = material.get_current_stock(site=site_id or None)
                elif material_type == "raw_material":
                    from catalog.models import RawMaterial

                    material = get_object_or_404(RawMaterial, id=material_id)
                    current_stock = material.get_current_stock(site=site_id or None)
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

    # Evaluate to lists once so len() is reliable and queries aren't re-run
    rm_stockouts = list(rm_stockouts)
    rm_low_stock = list(rm_low_stock)
    fp_stockouts = list(fp_stockouts)
    fp_low_stock = list(fp_low_stock)

    return render(
        request,
        "stock/stock_alerts_dashboard.html",
        {
            "rm_stockouts": rm_stockouts,
            "rm_low_stock": rm_low_stock,
            "fp_stockouts": fp_stockouts,
            "fp_low_stock": fp_low_stock,
            "total_alerts": len(rm_stockouts)
            + len(rm_low_stock)
            + len(fp_stockouts)
            + len(fp_low_stock),
            "title": "Alertes stock",
        },
    )
