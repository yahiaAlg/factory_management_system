# reporting/utils.py
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta


def generate_financial_result_report(date_from, date_to):
    """Generate financial result report data."""
    from sales.models import ClientInvoice, ClientPayment
    from supplier_ops.models import SupplierInvoice, SupplierPayment
    from expenses.models import Expense

    invoiced_revenue = ClientInvoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
    ).exclude(status="cancelled").aggregate(total=Sum("total_ttc"))["total"] or Decimal(
        "0.00"
    )

    collected_revenue = ClientPayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    committed_supplier_charges = SupplierInvoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
    ).exclude(status="cancelled").aggregate(total=Sum("total_ttc"))["total"] or Decimal(
        "0.00"
    )

    paid_supplier_charges = SupplierPayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    committed_operational_expenses = Expense.objects.filter(
        expense_date__gte=date_from,
        expense_date__lte=date_to,
        status__in=["validated", "paid"],
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    paid_operational_expenses = Expense.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
        status="paid",
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    total_committed_charges = (
        committed_supplier_charges + committed_operational_expenses
    )
    total_paid_charges = paid_supplier_charges + paid_operational_expenses

    theoretical_result = invoiced_revenue - total_committed_charges
    actual_cash_result = collected_revenue - total_paid_charges

    collection_rate = (
        (collected_revenue / invoiced_revenue * 100)
        if invoiced_revenue > 0
        else Decimal("0.00")
    )
    settlement_rate = (
        (total_paid_charges / total_committed_charges * 100)
        if total_committed_charges > 0
        else Decimal("0.00")
    )

    return {
        "period": {"from": date_from, "to": date_to},
        "invoiced_revenue": invoiced_revenue,
        "collected_revenue": collected_revenue,
        "committed_supplier_charges": committed_supplier_charges,
        "paid_supplier_charges": paid_supplier_charges,
        "committed_operational_expenses": committed_operational_expenses,
        "paid_operational_expenses": paid_operational_expenses,
        "total_committed_charges": total_committed_charges,
        "total_paid_charges": total_paid_charges,
        "theoretical_result": theoretical_result,
        "actual_cash_result": actual_cash_result,
        "collection_rate": collection_rate,
        "settlement_rate": settlement_rate,
        "cash_gap": actual_cash_result - theoretical_result,
    }


def generate_receivables_aging_report(as_of_date):
    """Generate client receivables aging report."""
    from sales.models import ClientInvoice
    from clients.models import Client

    clients_with_balance = Client.objects.filter(
        clientinvoice__balance_due__gt=0
    ).distinct()

    bucket_keys = [
        "current",
        "days_1_30",
        "days_31_60",
        "days_61_90",
        "days_over_90",
        "total",
    ]
    totals = {k: Decimal("0.00") for k in bucket_keys}
    aging_data = []

    for client in clients_with_balance:
        client_data = {"client": client, **{k: Decimal("0.00") for k in bucket_keys}}

        for invoice in ClientInvoice.objects.filter(client=client, balance_due__gt=0):
            days_overdue = (as_of_date - invoice.due_date).days
            balance = invoice.balance_due

            if days_overdue <= 0:
                client_data["current"] += balance
            elif days_overdue <= 30:
                client_data["days_1_30"] += balance
            elif days_overdue <= 60:
                client_data["days_31_60"] += balance
            elif days_overdue <= 90:
                client_data["days_61_90"] += balance
            else:
                client_data["days_over_90"] += balance

            client_data["total"] += balance

        for k in bucket_keys:
            totals[k] += client_data[k]

        aging_data.append(client_data)

    return {"as_of_date": as_of_date, "clients": aging_data, "totals": totals}


def generate_payables_aging_report(as_of_date):
    """Generate supplier payables aging report."""
    from supplier_ops.models import SupplierInvoice
    from suppliers.models import Supplier

    suppliers_with_balance = Supplier.objects.filter(
        supplierinvoice__balance_due__gt=0
    ).distinct()

    bucket_keys = [
        "current",
        "days_1_30",
        "days_31_60",
        "days_61_90",
        "days_over_90",
        "total",
    ]
    totals = {k: Decimal("0.00") for k in bucket_keys}
    aging_data = []

    for supplier in suppliers_with_balance:
        supplier_data = {
            "supplier": supplier,
            **{k: Decimal("0.00") for k in bucket_keys},
        }

        for invoice in SupplierInvoice.objects.filter(
            supplier=supplier, balance_due__gt=0
        ):
            days_overdue = (as_of_date - invoice.due_date).days
            balance = invoice.balance_due

            if days_overdue <= 0:
                supplier_data["current"] += balance
            elif days_overdue <= 30:
                supplier_data["days_1_30"] += balance
            elif days_overdue <= 60:
                supplier_data["days_31_60"] += balance
            elif days_overdue <= 90:
                supplier_data["days_61_90"] += balance
            else:
                supplier_data["days_over_90"] += balance

            supplier_data["total"] += balance

        for k in bucket_keys:
            totals[k] += supplier_data[k]

        aging_data.append(supplier_data)

    return {"as_of_date": as_of_date, "suppliers": aging_data, "totals": totals}


def generate_production_yield_report(date_from, date_to):
    """
    Generate production yield analysis report.

    FIXES:
    - yield_status and delta_qty are @property on their models — they cannot
      be used in ORM .filter() calls.  Replaced all such filters with Python-level
      comprehensions/checks over the already-fetched queryset.
    - yield_rate is also a @property; avg_yield is now computed in Python.
    """
    from production.models import ProductionOrder

    orders = list(
        ProductionOrder.objects.filter(
            closure_date__gte=date_from,
            closure_date__lte=date_to,
            status="completed",
        )
        .select_related(
            "formulation",
            "formulation__finished_product",
        )
        .prefetch_related("consumption_lines__raw_material")
    )

    total_orders = len(orders)

    # yield_rate is a @property — compute average in Python
    rates = [o.yield_rate for o in orders if o.yield_rate is not None]
    avg_yield = (sum(rates) / len(rates)) if rates else Decimal("0.00")

    # yield_status is a @property — categorise in Python
    normal_orders = sum(1 for o in orders if o.yield_status == "normal")
    warning_orders = sum(1 for o in orders if o.yield_status == "warning")
    critical_orders = sum(1 for o in orders if o.yield_status == "critical")

    # delta_qty and financial_impact are @property on ProductionOrderLine —
    # cannot ORM-filter; iterate in Python
    total_over_consumption = Decimal("0.00")
    over_consumption_by_material: dict = {}

    for order in orders:
        for line in order.consumption_lines.all():
            delta = line.delta_qty
            if delta is None or delta <= 0:
                continue
            impact = line.financial_impact or Decimal("0.00")
            total_over_consumption += impact

            material = line.raw_material
            if material.pk not in over_consumption_by_material:
                over_consumption_by_material[material.pk] = {
                    "material": material,
                    "total_over_consumption": Decimal("0.000"),
                    "total_cost": Decimal("0.00"),
                    "order_count": 0,
                }
            entry = over_consumption_by_material[material.pk]
            entry["total_over_consumption"] += delta
            entry["total_cost"] += impact
            entry["order_count"] += 1

    top_over_consuming = sorted(
        over_consumption_by_material.values(),
        key=lambda x: x["total_cost"],
        reverse=True,
    )[:10]

    return {
        "period": {"from": date_from, "to": date_to},
        "total_orders": total_orders,
        "avg_yield": avg_yield,
        "normal_orders": normal_orders,
        "warning_orders": warning_orders,
        "critical_orders": critical_orders,
        "total_over_consumption_cost": total_over_consumption,
        "orders": orders,
        "top_over_consuming_materials": top_over_consuming,
    }


def generate_expense_breakdown_report(date_from, date_to):
    """
    Generate expense breakdown analysis report.

    FIXES:
    - Removed reference to non-existent Expense.CATEGORY_CHOICES.
      ExpenseCategory is now a FK model, not a char-choice field.
      Category breakdown now queries ExpenseCategory objects directly.
    - expenses.filter(category=category_code) replaced with
      expenses.filter(category=category_obj) (FK lookup).
    """
    from expenses.models import Expense, ExpenseCategory

    expenses = Expense.objects.filter(
        expense_date__gte=date_from,
        expense_date__lte=date_to,
        status__in=["validated", "paid"],
    ).select_related("category")

    total_amount = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    category_breakdown = {}
    for category in ExpenseCategory.objects.filter(is_active=True).order_by(
        "order", "label"
    ):
        category_total = expenses.filter(category=category).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        if category_total > 0:
            category_breakdown[category.label] = {
                "amount": category_total,
                "percentage": (
                    (category_total / total_amount * 100)
                    if total_amount > 0
                    else Decimal("0.00")
                ),
                "count": expenses.filter(category=category).count(),
            }

    top_beneficiaries = (
        expenses.values("beneficiary")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")[:10]
    )

    monthly_trend = []
    current_date = date_from.replace(day=1)
    while current_date <= date_to:
        next_month = (current_date + timedelta(days=32)).replace(day=1)
        month_total = expenses.filter(
            expense_date__gte=current_date, expense_date__lt=next_month
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        monthly_trend.append(
            {"month": current_date.strftime("%Y-%m"), "total": month_total}
        )
        current_date = next_month

    return {
        "period": {"from": date_from, "to": date_to},
        "total_amount": total_amount,
        "total_count": expenses.count(),
        "category_breakdown": category_breakdown,
        "top_beneficiaries": top_beneficiaries,
        "monthly_trend": monthly_trend,
        "expenses": expenses.order_by("-expense_date"),
    }


def calculate_working_capital_requirement():
    """Calculate current working capital requirement."""
    from sales.models import ClientInvoice
    from supplier_ops.models import SupplierInvoice

    client_receivables = ClientInvoice.objects.filter(balance_due__gt=0).aggregate(
        total=Sum("balance_due")
    )["total"] or Decimal("0.00")
    supplier_payables = SupplierInvoice.objects.filter(balance_due__gt=0).aggregate(
        total=Sum("balance_due")
    )["total"] or Decimal("0.00")

    return {
        "client_receivables": client_receivables,
        "supplier_payables": supplier_payables,
        "wcr": client_receivables - supplier_payables,
    }
