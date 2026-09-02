# core/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from accounts.utils import role_required
from .models import CompanyInformation, SystemParameter
from .forms import CompanyInformationForm, SystemParameterForm


@login_required
def dashboard(request):
    import json
    from django.utils import timezone
    from decimal import Decimal

    today = timezone.localdate()
    year_start = today.replace(month=1, day=1)

    # ── Global date range filter (from GET params) ─────────────────────────────
    from datetime import date as date_type

    try:
        filter_date_from = date_type.fromisoformat(request.GET.get("date_from", ""))
    except (ValueError, TypeError):
        filter_date_from = year_start
    try:
        filter_date_to = date_type.fromisoformat(request.GET.get("date_to", ""))
    except (ValueError, TypeError):
        filter_date_to = today
    filter_is_custom = filter_date_from != year_start or filter_date_to != today

    context = {
        "title": "Tableau de bord",
        "today": today,
        "filter_date_from": str(filter_date_from),
        "filter_date_to": str(filter_date_to),
        "filter_is_custom": filter_is_custom,
    }

    role = getattr(getattr(request.user, "userprofile", None), "role", "")
    context["role"] = role

    # ── Finance KPIs (manager / accountant / viewer) ───────────────────────────
    if role in ("manager", "accountant", "viewer"):
        try:
            from django.db.models import Sum, Count
            from sales.models import ClientInvoice
            from supplier_ops.models import SupplierInvoice

            context["total_revenue"] = ClientInvoice.objects.filter(
                invoice_date__gte=filter_date_from,
                invoice_date__lte=filter_date_to,
            ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))["t"] or Decimal(
                "0.00"
            )

            context["total_supplier_charges"] = SupplierInvoice.objects.filter(
                invoice_date__gte=filter_date_from,
                invoice_date__lte=filter_date_to,
            ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))["t"] or Decimal(
                "0.00"
            )

            context["gross_margin"] = (
                context["total_revenue"] - context["total_supplier_charges"]
            )

            context["outstanding_clients"] = ClientInvoice.objects.filter(
                balance_due__gt=0
            ).aggregate(t=Sum("balance_due"))["t"] or Decimal("0.00")

            context["overdue_count"] = ClientInvoice.objects.filter(
                balance_due__gt=0, due_date__lt=today
            ).count()

            # Overdue invoices list (latest 5) for table
            context["overdue_invoices"] = (
                ClientInvoice.objects.filter(balance_due__gt=0, due_date__lt=today)
                .select_related("client")
                .order_by("due_date")[:5]
            )

            # ── Monthly revenue & charges (last 6 months) for line chart ──────
            try:
                from dateutil.relativedelta import relativedelta
            except ImportError:
                from django.utils.dateparse import parse_date
                import calendar

                class relativedelta:
                    def __init__(self, months=0, days=0):
                        self.months = months
                        self.days = days

                    def __rsub__(self, other):
                        import datetime

                        m = other.month - self.months
                        y = other.year + (m - 1) // 12
                        m = (m - 1) % 12 + 1
                        return other.replace(year=y, month=m)

                    def __radd__(self, other):
                        import datetime

                        m = other.month + self.months
                        y = other.year + (m - 1) // 12
                        m = (m - 1) % 12 + 1
                        d = min(other.day + self.days, calendar.monthrange(y, m)[1])
                        return other.replace(year=y, month=m, day=d)

            months_labels = []
            revenue_data = []
            charges_data = []

            for i in range(5, -1, -1):
                m_start = today.replace(day=1) - relativedelta(months=i)
                m_end = m_start + relativedelta(months=1, days=-1)
                months_labels.append(m_start.strftime("%b %Y"))
                rev = ClientInvoice.objects.filter(
                    invoice_date__gte=m_start,
                    invoice_date__lte=m_end,
                ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))[
                    "t"
                ] or Decimal(
                    "0"
                )
                chg = SupplierInvoice.objects.filter(
                    invoice_date__gte=m_start,
                    invoice_date__lte=m_end,
                ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))[
                    "t"
                ] or Decimal(
                    "0"
                )
                revenue_data.append(float(rev))
                charges_data.append(float(chg))

            context["chart_months"] = json.dumps(months_labels)
            context["chart_revenue"] = json.dumps(revenue_data)
            context["chart_charges"] = json.dumps(charges_data)

            # ── Invoice status breakdown for doughnut ─────────────────────────
            inv_stats = ClientInvoice.objects.values("status").annotate(cnt=Count("id"))
            status_map = {s["status"]: s["cnt"] for s in inv_stats}
            context["inv_legend_labels"] = [
                "Brouillon",
                "Validé",
                "Part. payé",
                "Payé",
                "En retard",
                "Annulé",
            ]
            context["inv_status_data"] = json.dumps(
                [
                    status_map.get("draft", 0),
                    status_map.get("validated", 0),
                    status_map.get("partially_paid", 0),
                    status_map.get("paid", 0),
                    status_map.get("overdue", 0),
                    status_map.get("cancelled", 0),
                ]
            )

        except Exception:
            context.setdefault("total_revenue", Decimal("0.00"))
            context.setdefault("total_supplier_charges", Decimal("0.00"))
            context.setdefault("gross_margin", Decimal("0.00"))
            context.setdefault("outstanding_clients", Decimal("0.00"))
            context.setdefault("overdue_count", 0)
            context.setdefault("overdue_invoices", [])
            context.setdefault("chart_months", json.dumps([]))
            context.setdefault("chart_revenue", json.dumps([]))
            context.setdefault("chart_charges", json.dumps([]))
            context.setdefault(
                "inv_legend_labels",
                ["Brouillon", "Validé", "Part. payé", "Payé", "En retard", "Annulé"],
            )
            context.setdefault("inv_status_data", json.dumps([0, 0, 0, 0, 0, 0]))

    # ── Operations KPIs ────────────────────────────────────────────────────────
    try:
        from stock.models import RawMaterial

        rm_list = list(RawMaterial.objects.all())
        context["rm_stockout_count"] = sum(
            1
            for m in rm_list
            if getattr(m, "get_stock_status", lambda: None)() == "stockout"
        )
        context["rm_alert_count"] = sum(
            1
            for m in rm_list
            if getattr(m, "get_stock_status", lambda: None)() == "running_low"
        )
        context["low_stock_materials"] = [
            m
            for m in rm_list
            if getattr(m, "get_stock_status", lambda: None)()
            in ("stockout", "running_low")
        ]
    except Exception:
        context.setdefault("rm_stockout_count", 0)
        context.setdefault("rm_alert_count", 0)
        context.setdefault("low_stock_materials", [])

    try:
        from production.models import ProductionOrder
        from django.db.models import Count

        context["active_production_orders"] = ProductionOrder.objects.filter(
            status__in=("in_progress", "validated", "pending")
        ).count()

        po_stats = ProductionOrder.objects.values("status").annotate(cnt=Count("id"))
        po_map = {s["status"]: s["cnt"] for s in po_stats}
        context["po_status_labels"] = json.dumps(
            ["En attente", "Validé", "En cours", "Terminé", "Annulé"]
        )
        context["po_status_data"] = json.dumps(
            [
                po_map.get("pending", 0),
                po_map.get("validated", 0),
                po_map.get("in_progress", 0),
                po_map.get("completed", 0),
                po_map.get("cancelled", 0),
            ]
        )

        context["recent_production_orders"] = ProductionOrder.objects.select_related(
            "formulation"
        ).order_by("-created_at")[:5]

    except Exception:
        context.setdefault("active_production_orders", 0)
        context.setdefault("po_status_labels", json.dumps([]))
        context.setdefault("po_status_data", json.dumps([0, 0, 0, 0, 0]))
        context.setdefault("recent_production_orders", [])

    try:
        from supplier_ops.models import SupplierDeliveryNote

        context["pending_supplier_dns"] = SupplierDeliveryNote.objects.filter(
            status="pending"
        ).count()
    except Exception:
        context.setdefault("pending_supplier_dns", 0)

    # ── Expenses breakdown (current year) for doughnut ────────────────────────
    try:
        from django.db.models import Sum
        from expenses.models import Expense

        exp_by_cat = (
            Expense.objects.filter(
                expense_date__gte=filter_date_from, expense_date__lte=filter_date_to
            )
            .exclude(status="cancelled")
            .values("category__label")
            .annotate(total=Sum("amount"))
            .order_by("-total")[:6]
        )
        context["exp_labels"] = json.dumps([e["category__label"] for e in exp_by_cat])
        context["exp_data"] = json.dumps([float(e["total"]) for e in exp_by_cat])
        context["total_expenses_ytd"] = sum(float(e["total"]) for e in exp_by_cat)
        context["exp_date_from"] = str(filter_date_from)
        context["exp_date_to"] = str(filter_date_to)
    except Exception:
        context.setdefault("exp_labels", json.dumps([]))
        context.setdefault("exp_data", json.dumps([]))
        context.setdefault("total_expenses_ytd", 0)

    # ── Recent activity (audit log) ────────────────────────────────────────────
    try:
        from accounts.models import AuditLog

        context["recent_activity"] = AuditLog.objects.select_related("user").order_by(
            "-timestamp"
        )[:12]
    except Exception:
        context.setdefault("recent_activity", [])

    return render(request, "core/dashboard.html", context)


@login_required
@role_required(["manager"])
def company_settings(request):
    company, _ = CompanyInformation.objects.get_or_create(
        defaults={"raison_sociale": "Ma Société", "address": "", "wilaya": ""}
    )

    if request.method == "POST":
        form = CompanyInformationForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Informations société mises à jour avec succès")
            return redirect("core:company_settings")
    else:
        form = CompanyInformationForm(instance=company)

    return render(
        request,
        "core/company_settings.html",
        {
            "form": form,
            "title": "Paramètres société",
        },
    )


@login_required
@role_required(["manager"])
def system_parameters(request):
    if request.method == "POST":
        param_id = request.POST.get("param_id")
        if param_id:
            parameter = get_object_or_404(SystemParameter, id=param_id)
            new_value = request.POST.get("value", "")
            parameter.value = new_value
            parameter.save()
            messages.success(request, f"Paramètre « {parameter.key} » mis à jour")
            return redirect("core:system_parameters")
        else:
            form = SystemParameterForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Paramètre ajouté avec succès")
                return redirect("core:system_parameters")
    else:
        form = SystemParameterForm()

    parameters = SystemParameter.objects.all().order_by("category", "key")
    return render(
        request,
        "core/system_parameters.html",
        {
            "form": form,
            "parameters": parameters,
            "title": "Paramètres système",
        },
    )


@login_required
def chart_data_ajax(request):
    """Return revenue & charges chart data for a given period (AJAX)."""
    import json
    from django.http import JsonResponse
    from django.utils import timezone
    from decimal import Decimal

    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        from django.http import HttpResponseBadRequest

        return HttpResponseBadRequest()

    role = getattr(getattr(request.user, "userprofile", None), "role", "")
    if role not in ("manager", "accountant", "viewer"):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden()

    period = request.GET.get("period", "6")
    today = timezone.localdate()

    try:
        from dateutil.relativedelta import relativedelta
    except ImportError:
        import calendar

        class relativedelta:
            def __init__(self, months=0, days=0):
                self.months = months
                self.days = days

            def __rsub__(self, other):
                m = other.month - self.months
                y = other.year + (m - 1) // 12
                m = (m - 1) % 12 + 1
                return other.replace(year=y, month=m)

            def __radd__(self, other):
                m = other.month + self.months
                y = other.year + (m - 1) // 12
                m = (m - 1) % 12 + 1
                d = min(other.day + self.days, calendar.monthrange(y, m)[1])
                return other.replace(year=y, month=m, day=d)

    if period == "ytd":
        first_month = today.replace(month=1, day=1)
        num_months = today.month
    else:
        try:
            num_months = int(period)
        except ValueError:
            num_months = 6
        num_months = min(max(num_months, 1), 24)
        first_month = today.replace(day=1) - relativedelta(months=num_months - 1)

    from django.db.models import Sum
    from sales.models import ClientInvoice
    from supplier_ops.models import SupplierInvoice

    months_labels, revenue_data, charges_data = [], [], []
    for i in range(num_months):
        m_start = first_month + relativedelta(months=i)
        m_end = m_start + relativedelta(months=1, days=-1)
        months_labels.append(m_start.strftime("%b %Y"))
        rev = ClientInvoice.objects.filter(
            invoice_date__gte=m_start,
            invoice_date__lte=m_end,
        ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))["t"] or Decimal("0")
        chg = SupplierInvoice.objects.filter(
            invoice_date__gte=m_start,
            invoice_date__lte=m_end,
        ).exclude(status="cancelled").aggregate(t=Sum("total_ttc"))["t"] or Decimal("0")
        revenue_data.append(float(rev))
        charges_data.append(float(chg))

    return JsonResponse(
        {"months": months_labels, "revenue": revenue_data, "charges": charges_data}
    )


@login_required
def expense_chart_ajax(request):
    """Return expense-by-category data for a given date range (AJAX)."""
    from django.http import JsonResponse, HttpResponseBadRequest
    from django.utils import timezone
    from decimal import Decimal
    from django.db.models import Sum
    import json

    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return HttpResponseBadRequest()

    today = timezone.localdate()
    year_start = today.replace(month=1, day=1)

    date_from = request.GET.get("from") or year_start
    date_to = request.GET.get("to") or today

    try:
        from expenses.models import Expense

        exp_by_cat = (
            Expense.objects.filter(
                expense_date__gte=date_from, expense_date__lte=date_to
            )
            .exclude(status="cancelled")
            .values("category__label")
            .annotate(total=Sum("amount"))
            .order_by("-total")[:6]
        )
        labels = [e["category__label"] for e in exp_by_cat]
        data = [float(e["total"]) for e in exp_by_cat]
        total = sum(data)
    except Exception:
        labels, data, total = [], [], 0

    return JsonResponse({"labels": labels, "data": data, "total": total})


# ---------------------------------------------------------------------------
# PieceJointe — generic attachment handling shared by every app (mirrors
# the avicole project's mechanism).
#
# Every create/edit view that carries proof documents (SupplierDN,
# SupplierInvoice, Expense, ClientDN, ClientInvoice, ...) builds its
# formset through `build_piece_jointe_formset` below instead of each app
# re-implementing the request.method / request.FILES branching.
# Deletion of a single attachment goes through the one generic
# `piece_jointe_delete` view — wired once in core/urls.py and reused by
# every app's templates.
# ---------------------------------------------------------------------------


def build_piece_jointe_formset(formset_class, request, instance=None, prefix="pj"):
    """
    Build a generic PieceJointeFormSet bound to *instance* (an existing
    header row) — or unbound-to-instance when called before the parent is
    saved (the caller must then set `formset.instance = obj` and re-save).

    On GET (or when the request isn't a POST), returns an unbound formset
    for display. On POST, returns it bound to request.POST/request.FILES so
    the calling view can run its own `form.is_valid() and formset.is_valid()`
    check inside its existing transaction.
    """
    kwargs = {"prefix": prefix}
    if instance is not None:
        kwargs["instance"] = instance
    if request.method == "POST":
        return formset_class(request.POST, request.FILES, **kwargs)
    return formset_class(**kwargs)


@login_required
@require_POST
def piece_jointe_delete(request, pk):
    """
    Delete a single PieceJointe row, regardless of which app/model owns it.

    Generic on purpose: the underlying file is removed by the post_delete
    signal in core/signals.py, so this view only needs to fetch-and-delete
    the row and bounce back to wherever the user came from (?next=<url> or
    the HTTP referer).
    """
    from .models import PieceJointe

    pj = get_object_or_404(PieceJointe, pk=pk)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    pj.delete()
    messages.success(request, "Pièce jointe supprimée.")
    return redirect(next_url)
