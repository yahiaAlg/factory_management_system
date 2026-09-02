# reporting/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta  # FIX: timezone.timedelta does not exist
from decimal import Decimal
import csv

from accounts.utils import role_required
from .forms import ReportParametersForm, AgingReportForm, StockReportForm
from .models import FinancialPeriod, ReportTemplate, ReportExecution
from .utils import (
    generate_financial_result_report,
    generate_receivables_aging_report,
    generate_payables_aging_report,
    generate_production_yield_report,
    generate_expense_breakdown_report,
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant", "viewer"])  # FIX: was missing entirely
def reporting_dashboard(request):
    """Main reporting dashboard."""
    recent_executions = ReportExecution.objects.select_related("template").order_by(
        "-execution_date"
    )[:10]
    templates = ReportTemplate.objects.filter(is_active=True).order_by(
        "report_type", "name"
    )

    # FIX: timezone.now() returns a datetime; replace(day=1) still a datetime.
    # DateField filters require date objects, not datetimes.
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    # Advance to next month's first day safely via timedelta
    first_of_next_month = (first_of_month + timedelta(days=32)).replace(day=1)

    from sales.models import ClientInvoice
    from expenses.models import Expense

    monthly_revenue = ClientInvoice.objects.filter(
        invoice_date__gte=first_of_month,
        invoice_date__lt=first_of_next_month,
    ).aggregate(total=Sum("total_ttc"))["total"] or Decimal("0.00")

    monthly_expenses = Expense.objects.filter(
        expense_date__gte=first_of_month,
        expense_date__lt=first_of_next_month,
        status__in=["validated", "paid"],
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    context = {
        "recent_executions": recent_executions,
        "templates": templates,
        "monthly_revenue": monthly_revenue,
        "monthly_expenses": monthly_expenses,
        "title": "Tableau de bord reporting",
    }
    return render(request, "reporting/reporting_dashboard.html", context)


# ---------------------------------------------------------------------------
# Financial reports
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant", "viewer"])
def financial_result_report(request):
    """Financial result report."""
    # FIX: use ReportParametersForm for validation instead of raw strptime.
    # GET params pre-populate the form so date pickers work on re-load.
    form = ReportParametersForm(request.GET or None)

    report_data = None
    date_from = date_to = None

    if request.GET and form.is_valid():
        date_from = form.cleaned_data["date_from"]
        date_to = form.cleaned_data["date_to"]
        report_data = generate_financial_result_report(date_from, date_to)
    elif not request.GET:
        # First load — show default range from unbound form (current month)
        today = timezone.now().date()
        date_from = today.replace(day=1)
        date_to = (date_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        report_data = generate_financial_result_report(date_from, date_to)
        form = ReportParametersForm(
            initial={"date_from": date_from, "date_to": date_to}
        )

    context = {
        "form": form,
        "report_data": report_data,
        "date_from": date_from,
        "date_to": date_to,
        "title": "Rapport de résultat financier",
    }
    return render(request, "reporting/financial_result_report.html", context)


@login_required
@role_required(["manager", "accountant", "sales", "viewer"])
def receivables_aging_report(request):
    """Client receivables aging report."""
    # FIX: use AgingReportForm instead of raw strptime.
    form = AgingReportForm(request.GET or None)

    report_data = None
    as_of_date = None

    if request.GET and form.is_valid():
        as_of_date = form.cleaned_data["as_of_date"]
        report_data = generate_receivables_aging_report(as_of_date)
    elif not request.GET:
        as_of_date = timezone.now().date()
        report_data = generate_receivables_aging_report(as_of_date)
        form = AgingReportForm(initial={"as_of_date": as_of_date})

    context = {
        "form": form,
        "report_data": report_data,
        "as_of_date": as_of_date,
        "title": "Échéancier clients",
    }
    return render(request, "reporting/receivables_aging_report.html", context)


@login_required
@role_required(["manager", "accountant", "viewer"])
def payables_aging_report(request):
    """Supplier payables aging report."""
    # FIX: use AgingReportForm instead of raw strptime.
    form = AgingReportForm(request.GET or None)

    report_data = None
    as_of_date = None

    if request.GET and form.is_valid():
        as_of_date = form.cleaned_data["as_of_date"]
        report_data = generate_payables_aging_report(as_of_date)
    elif not request.GET:
        as_of_date = timezone.now().date()
        report_data = generate_payables_aging_report(as_of_date)
        form = AgingReportForm(initial={"as_of_date": as_of_date})

    context = {
        "form": form,
        "report_data": report_data,
        "as_of_date": as_of_date,
        "title": "Échéancier fournisseurs",
    }
    return render(request, "reporting/payables_aging_report.html", context)


# ---------------------------------------------------------------------------
# Operational reports
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "stock_prod", "viewer"])
def production_yield_report(request):
    """Production yield analysis report."""
    # FIX: use ReportParametersForm; fix timezone.timedelta → timedelta.
    form = ReportParametersForm(request.GET or None)

    report_data = None
    date_from = date_to = None

    if request.GET and form.is_valid():
        date_from = form.cleaned_data["date_from"]
        date_to = form.cleaned_data["date_to"]
        report_data = generate_production_yield_report(date_from, date_to)
    elif not request.GET:
        today = timezone.now().date()
        date_from = today.replace(day=1)
        date_to = (date_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        report_data = generate_production_yield_report(date_from, date_to)
        form = ReportParametersForm(
            initial={"date_from": date_from, "date_to": date_to}
        )

    context = {
        "form": form,
        "report_data": report_data,
        "date_from": date_from,
        "date_to": date_to,
        "title": "Analyse des rendements de production",
    }
    return render(request, "reporting/production_yield_report.html", context)


@login_required
@role_required(["manager", "accountant", "viewer"])
def expense_breakdown_report(request):
    """Expense breakdown analysis report."""
    # FIX: use ReportParametersForm; fix timezone.timedelta → timedelta.
    form = ReportParametersForm(request.GET or None)

    report_data = None
    date_from = date_to = None

    if request.GET and form.is_valid():
        date_from = form.cleaned_data["date_from"]
        date_to = form.cleaned_data["date_to"]
        report_data = generate_expense_breakdown_report(date_from, date_to)
    elif not request.GET:
        today = timezone.now().date()
        date_from = today.replace(day=1)
        date_to = (date_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        report_data = generate_expense_breakdown_report(date_from, date_to)
        form = ReportParametersForm(
            initial={"date_from": date_from, "date_to": date_to}
        )

    context = {
        "form": form,
        "report_data": report_data,
        "date_from": date_from,
        "date_to": date_to,
        "title": "Répartition des dépenses",
    }
    return render(request, "reporting/expense_breakdown_report.html", context)


@login_required
@role_required(["manager", "accountant", "viewer"])
def stock_valuation_report(request):
    """Stock valuation report.

    FIX: StockReportForm is now actually used — stock_type filters which
    balances are queried, and include_zero_stock controls the quantity__gt=0
    guard that was hard-coded in the original.
    """
    from stock.models import RawMaterialStockBalance, FinishedProductStockBalance

    form = StockReportForm(request.GET or None)
    # Fall back to defaults when form is unbound or invalid
    if form.is_valid():
        stock_type = form.cleaned_data["stock_type"]
        include_zero_stock = form.cleaned_data["include_zero_stock"]
    else:
        stock_type = "all"
        include_zero_stock = False

    qty_filter = {}  # empty → include zero; populated → exclude zero
    if not include_zero_stock:
        qty_filter["quantity__gt"] = 0

    rm_data = []
    rm_total_value = Decimal("0.00")

    if stock_type in ("all", "raw_materials"):
        rm_balances = RawMaterialStockBalance.objects.select_related(
            "raw_material",
            "raw_material__unit_of_measure",
            "raw_material__category",
        ).filter(**qty_filter)

        for balance in rm_balances:
            value = balance.get_stock_value()
            rm_total_value += value
            rm_data.append(
                {
                    "material": balance.raw_material,
                    "quantity": balance.quantity,
                    "unit_price": balance.raw_material.reference_price,
                    "value": value,
                    "status": balance.get_stock_status(),
                }
            )

    fp_data = []
    fp_total_value = Decimal("0.00")

    if stock_type in ("all", "finished_products"):
        fp_balances = FinishedProductStockBalance.objects.select_related(
            "finished_product",
            "finished_product__sales_unit",
        ).filter(**qty_filter)

        for balance in fp_balances:
            value = balance.get_stock_value()
            fp_total_value += value
            fp_data.append(
                {
                    "product": balance.finished_product,
                    "quantity": balance.quantity,
                    "unit_cost": balance.weighted_average_cost,
                    "value": value,
                    "status": balance.get_stock_status(),
                }
            )

    context = {
        "form": form,
        "rm_data": rm_data,
        "fp_data": fp_data,
        "rm_total_value": rm_total_value,
        "fp_total_value": fp_total_value,
        "total_stock_value": rm_total_value + fp_total_value,
        "stock_type": stock_type,
        "title": "Valorisation des stocks",
    }
    return render(request, "reporting/stock_valuation_report.html", context)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant"])
def export_report_csv(request, report_type):
    """Export report data to CSV.

    FIX 1: financial_result branch now guards against missing date params
            instead of crashing with AttributeError on None.strptime().
    FIX 2: Added export branches for payables_aging, production_yield,
            expense_breakdown and stock_valuation that were completely absent.
    FIX 3: as_of_date default handling made explicit — request.GET.get()
            returns a str or None; both cases are now handled cleanly.
    """
    from datetime import datetime

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = (
        f'attachment; filename="{report_type}_{timezone.now().strftime("%Y%m%d")}.csv"'
    )
    writer = csv.writer(response)

    # ------------------------------------------------------------------ helpers
    def _parse_date(raw):
        """Return a date object or None."""
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _default_month():
        today = timezone.now().date()
        d_from = today.replace(day=1)
        d_to = (d_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return d_from, d_to

    # ------------------------------------------------------------------ routes
    if report_type == "financial_result":
        date_from = _parse_date(request.GET.get("date_from"))
        date_to = _parse_date(request.GET.get("date_to"))

        # FIX: original silently produced an empty response when params missing
        if not date_from or not date_to:
            date_from, date_to = _default_month()

        data = generate_financial_result_report(date_from, date_to)
        writer.writerow(["Rapport de Résultat Financier"])
        writer.writerow(["Période", f"{date_from} - {date_to}"])
        writer.writerow([])
        writer.writerow(["Indicateur", "Montant (DZD)"])
        writer.writerow(["Revenus facturés", data["invoiced_revenue"]])
        writer.writerow(["Revenus encaissés", data["collected_revenue"]])
        writer.writerow(
            ["Charges fournisseurs engagées", data["committed_supplier_charges"]]
        )
        writer.writerow(["Charges fournisseurs payées", data["paid_supplier_charges"]])
        writer.writerow(
            [
                "Dépenses opérationnelles engagées",
                data["committed_operational_expenses"],
            ]
        )
        writer.writerow(
            ["Dépenses opérationnelles payées", data["paid_operational_expenses"]]
        )
        writer.writerow(["Total charges engagées", data["total_committed_charges"]])
        writer.writerow(["Total charges payées", data["total_paid_charges"]])
        writer.writerow(["Résultat théorique", data["theoretical_result"]])
        writer.writerow(["Résultat réel (trésorerie)", data["actual_cash_result"]])
        writer.writerow(["Taux de recouvrement (%)", data["collection_rate"]])
        writer.writerow(["Taux de règlement (%)", data["settlement_rate"]])

    elif report_type == "receivables_aging":
        as_of_date = _parse_date(request.GET.get("as_of_date")) or timezone.now().date()
        data = generate_receivables_aging_report(as_of_date)
        writer.writerow(["Échéancier Clients"])
        writer.writerow(["Date de situation", as_of_date])
        writer.writerow([])
        writer.writerow(
            ["Client", "Courant", "1-30 j", "31-60 j", "61-90 j", "> 90 j", "Total"]
        )
        for row in data["clients"]:
            writer.writerow(
                [
                    row["client"].raison_sociale,
                    row["current"],
                    row["days_1_30"],
                    row["days_31_60"],
                    row["days_61_90"],
                    row["days_over_90"],
                    row["total"],
                ]
            )
        totals = data["totals"]
        writer.writerow(
            [
                "TOTAL",
                totals["current"],
                totals["days_1_30"],
                totals["days_31_60"],
                totals["days_61_90"],
                totals["days_over_90"],
                totals["total"],
            ]
        )

    elif report_type == "payables_aging":
        # FIX: was completely absent in original
        as_of_date = _parse_date(request.GET.get("as_of_date")) or timezone.now().date()
        data = generate_payables_aging_report(as_of_date)
        writer.writerow(["Échéancier Fournisseurs"])
        writer.writerow(["Date de situation", as_of_date])
        writer.writerow([])
        writer.writerow(
            [
                "Fournisseur",
                "Courant",
                "1-30 j",
                "31-60 j",
                "61-90 j",
                "> 90 j",
                "Total",
            ]
        )
        for row in data["suppliers"]:
            writer.writerow(
                [
                    row["supplier"].raison_sociale,
                    row["current"],
                    row["days_1_30"],
                    row["days_31_60"],
                    row["days_61_90"],
                    row["days_over_90"],
                    row["total"],
                ]
            )
        totals = data["totals"]
        writer.writerow(
            [
                "TOTAL",
                totals["current"],
                totals["days_1_30"],
                totals["days_31_60"],
                totals["days_61_90"],
                totals["days_over_90"],
                totals["total"],
            ]
        )

    elif report_type == "production_yield":
        # FIX: was completely absent in original
        date_from = _parse_date(request.GET.get("date_from"))
        date_to = _parse_date(request.GET.get("date_to"))
        if not date_from or not date_to:
            date_from, date_to = _default_month()

        data = generate_production_yield_report(date_from, date_to)
        writer.writerow(["Analyse des Rendements de Production"])
        writer.writerow(["Période", f"{date_from} - {date_to}"])
        writer.writerow([])
        writer.writerow(["Total ordres", data["total_orders"]])
        writer.writerow(["Rendement moyen (%)", data["avg_yield"]])
        writer.writerow(["Ordres normaux", data["normal_orders"]])
        writer.writerow(["Ordres en alerte", data["warning_orders"]])
        writer.writerow(["Ordres critiques", data["critical_orders"]])
        writer.writerow(
            ["Coût total sur-consommation (DZD)", data["total_over_consumption_cost"]]
        )
        writer.writerow([])
        writer.writerow(
            [
                "Référence OP",
                "Formulation",
                "Qté cible",
                "Qté produite",
                "Rendement (%)",
                "Statut",
            ]
        )
        for order in data["orders"]:
            writer.writerow(
                [
                    order.reference,
                    order.formulation.designation,
                    order.target_qty,
                    order.actual_qty_produced,
                    order.yield_rate,
                    order.yield_status,
                ]
            )

    elif report_type == "expense_breakdown":
        # FIX: was completely absent in original
        date_from = _parse_date(request.GET.get("date_from"))
        date_to = _parse_date(request.GET.get("date_to"))
        if not date_from or not date_to:
            date_from, date_to = _default_month()

        data = generate_expense_breakdown_report(date_from, date_to)
        writer.writerow(["Répartition des Dépenses"])
        writer.writerow(["Période", f"{date_from} - {date_to}"])
        writer.writerow([])
        writer.writerow(["Montant total (DZD)", data["total_amount"]])
        writer.writerow(["Nombre de dépenses", data["total_count"]])
        writer.writerow([])
        writer.writerow(["Catégorie", "Montant (DZD)", "% du total", "Nb dépenses"])
        for label, info in data["category_breakdown"].items():
            writer.writerow([label, info["amount"], info["percentage"], info["count"]])
        writer.writerow([])
        writer.writerow(["Top bénéficiaires"])
        writer.writerow(["Bénéficiaire", "Montant (DZD)", "Nb dépenses"])
        for b in data["top_beneficiaries"]:
            writer.writerow([b["beneficiary"], b["total"], b["count"]])

    elif report_type == "stock_valuation":
        # FIX: was completely absent in original
        from stock.models import RawMaterialStockBalance, FinishedProductStockBalance

        writer.writerow(["Valorisation des Stocks"])
        writer.writerow(["Date", timezone.now().date()])
        writer.writerow([])
        writer.writerow(["MATIÈRES PREMIÈRES"])
        writer.writerow(
            [
                "Référence",
                "Désignation",
                "Quantité",
                "Unité",
                "Prix unitaire (DZD)",
                "Valeur (DZD)",
            ]
        )
        rm_total = Decimal("0.00")
        for b in RawMaterialStockBalance.objects.select_related(
            "raw_material", "raw_material__unit_of_measure"
        ).filter(quantity__gt=0):
            value = b.get_stock_value()
            rm_total += value
            writer.writerow(
                [
                    b.raw_material.reference,
                    b.raw_material.designation,
                    b.quantity,
                    b.raw_material.unit_of_measure.symbol,
                    b.raw_material.reference_price,
                    value,
                ]
            )
        writer.writerow(["", "", "", "", "Total MP", rm_total])
        writer.writerow([])
        writer.writerow(["PRODUITS FINIS"])
        writer.writerow(
            [
                "Référence",
                "Désignation",
                "Quantité",
                "Unité",
                "CMP (DZD)",
                "Valeur (DZD)",
            ]
        )
        fp_total = Decimal("0.00")
        for b in FinishedProductStockBalance.objects.select_related(
            "finished_product", "finished_product__sales_unit"
        ).filter(quantity__gt=0):
            value = b.get_stock_value()
            fp_total += value
            writer.writerow(
                [
                    b.finished_product.reference,
                    b.finished_product.designation,
                    b.quantity,
                    b.finished_product.sales_unit.symbol,
                    b.weighted_average_cost,
                    value,
                ]
            )
        writer.writerow(["", "", "", "", "Total PF", fp_total])
        writer.writerow(["", "", "", "", "TOTAL GÉNÉRAL", rm_total + fp_total])

    else:
        writer.writerow(["Type de rapport inconnu :", report_type])

    return response


# ---------------------------------------------------------------------------
# AJAX endpoints
# ---------------------------------------------------------------------------


@login_required
@role_required(["manager", "accountant", "viewer"])  # FIX: was missing entirely
def kpi_dashboard_ajax(request):
    """AJAX endpoint for KPI dashboard data.

    FIX 1: timezone.timedelta → timedelta (timezone has no timedelta attr).
    FIX 2: start_date / end_date were datetime objects used in DateField ORM
            filters.  All computations now work with date objects via
            timezone.now().date().
    FIX 3: quarter end date was computed with timedelta(days=93) which is
            imprecise.  Now computed by adding 3 months correctly.
    """
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Méthode non autorisée"})

    period = request.GET.get("period", "month")  # month | quarter | year
    today = timezone.now().date()  # FIX: work with date, not datetime

    if period == "month":
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)

    elif period == "quarter":
        # FIX: proper quarter boundaries, no off-by-one from timedelta(days=93)
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1)
        # End = first day of the month 3 months later
        end_month = quarter_start_month + 3
        end_year = today.year + (end_month - 1) // 12
        end_month = ((end_month - 1) % 12) + 1
        end_date = today.replace(year=end_year, month=end_month, day=1)

    else:  # year
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(year=today.year + 1, month=1, day=1)

    from sales.models import ClientInvoice
    from supplier_ops.models import SupplierInvoice
    from expenses.models import Expense

    revenue = ClientInvoice.objects.filter(
        invoice_date__gte=start_date,
        invoice_date__lt=end_date,
    ).exclude(status="cancelled").aggregate(total=Sum("total_ttc"))["total"] or Decimal(
        "0.00"
    )

    op_expenses = Expense.objects.filter(
        expense_date__gte=start_date,
        expense_date__lt=end_date,
        status__in=["validated", "paid"],
    ).exclude(status="cancelled").aggregate(total=Sum("amount"))["total"] or Decimal(
        "0.00"
    )

    supplier_charges = SupplierInvoice.objects.filter(
        invoice_date__gte=start_date,
        invoice_date__lt=end_date,
    ).exclude(status="cancelled").aggregate(total=Sum("total_ttc"))["total"] or Decimal(
        "0.00"
    )

    total_charges = op_expenses + supplier_charges

    return JsonResponse(
        {
            "success": True,
            "period": period,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "revenue": str(revenue),
            "op_expenses": str(op_expenses),
            "supplier_charges": str(supplier_charges),
            "total_charges": str(total_charges),
            "result": str(revenue - total_charges),
        }
    )
