from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

def generate_financial_result_report(date_from, date_to):
    """Generate financial result report data"""
    from sales.models import ClientInvoice, ClientPayment
    from supplier_ops.models import SupplierInvoice, SupplierPayment
    from expenses.models import Expense
    
    # Revenues
    invoiced_revenue = ClientInvoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to
    ).aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
    
    collected_revenue = ClientPayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Supplier charges
    committed_supplier_charges = SupplierInvoice.objects.filter(
        invoice_date__gte=date_from,
        invoice_date__lte=date_to
    ).aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
    
    paid_supplier_charges = SupplierPayment.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Operational expenses
    committed_operational_expenses = Expense.objects.filter(
        expense_date__gte=date_from,
        expense_date__lte=date_to,
        status__in=['validated', 'paid']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    paid_operational_expenses = Expense.objects.filter(
        payment_date__gte=date_from,
        payment_date__lte=date_to,
        status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate totals and results
    total_committed_charges = committed_supplier_charges + committed_operational_expenses
    total_paid_charges = paid_supplier_charges + paid_operational_expenses
    
    theoretical_result = invoiced_revenue - total_committed_charges
    actual_cash_result = collected_revenue - total_paid_charges
    
    # Calculate rates
    collection_rate = (collected_revenue / invoiced_revenue * 100) if invoiced_revenue > 0 else Decimal('0.00')
    settlement_rate = (total_paid_charges / total_committed_charges * 100) if total_committed_charges > 0 else Decimal('0.00')
    
    return {
        'period': {'from': date_from, 'to': date_to},
        'invoiced_revenue': invoiced_revenue,
        'collected_revenue': collected_revenue,
        'committed_supplier_charges': committed_supplier_charges,
        'paid_supplier_charges': paid_supplier_charges,
        'committed_operational_expenses': committed_operational_expenses,
        'paid_operational_expenses': paid_operational_expenses,
        'total_committed_charges': total_committed_charges,
        'total_paid_charges': total_paid_charges,
        'theoretical_result': theoretical_result,
        'actual_cash_result': actual_cash_result,
        'collection_rate': collection_rate,
        'settlement_rate': settlement_rate,
        'cash_gap': actual_cash_result - theoretical_result,
    }

def generate_receivables_aging_report(as_of_date):
    """Generate client receivables aging report"""
    from sales.models import ClientInvoice
    from clients.models import Client
    
    # Get all clients with outstanding invoices
    clients_with_balance = Client.objects.filter(
        clientinvoice__balance_due__gt=0
    ).distinct()
    
    aging_data = []
    totals = {
        'current': Decimal('0.00'),
        'days_1_30': Decimal('0.00'),
        'days_31_60': Decimal('0.00'),
        'days_61_90': Decimal('0.00'),
        'days_over_90': Decimal('0.00'),
        'total': Decimal('0.00')
    }
    
    for client in clients_with_balance:
        client_data = {
            'client': client,
            'current': Decimal('0.00'),
            'days_1_30': Decimal('0.00'),
            'days_31_60': Decimal('0.00'),
            'days_61_90': Decimal('0.00'),
            'days_over_90': Decimal('0.00'),
            'total': Decimal('0.00')
        }
        
        # Get outstanding invoices for this client
        outstanding_invoices = ClientInvoice.objects.filter(
            client=client,
            balance_due__gt=0
        )
        
        for invoice in outstanding_invoices:
            days_overdue = (as_of_date - invoice.due_date).days
            balance = invoice.balance_due
            
            if days_overdue <= 0:
                client_data['current'] += balance
            elif days_overdue <= 30:
                client_data['days_1_30'] += balance
            elif days_overdue <= 60:
                client_data['days_31_60'] += balance
            elif days_overdue <= 90:
                client_data['days_61_90'] += balance
            else:
                client_data['days_over_90'] += balance
            
            client_data['total'] += balance
        
        # Add to totals
        for key in totals:
            totals[key] += client_data[key]
        
        aging_data.append(client_data)
    
    return {
        'as_of_date': as_of_date,
        'clients': aging_data,
        'totals': totals
    }

def generate_payables_aging_report(as_of_date):
    """Generate supplier payables aging report"""
    from supplier_ops.models import SupplierInvoice
    from suppliers.models import Supplier
    
    # Get all suppliers with outstanding invoices
    suppliers_with_balance = Supplier.objects.filter(
        supplierinvoice__balance_due__gt=0
    ).distinct()
    
    aging_data = []
    totals = {
        'current': Decimal('0.00'),
        'days_1_30': Decimal('0.00'),
        'days_31_60': Decimal('0.00'),
        'days_61_90': Decimal('0.00'),
        'days_over_90': Decimal('0.00'),
        'total': Decimal('0.00')
    }
    
    for supplier in suppliers_with_balance:
        supplier_data = {
            'supplier': supplier,
            'current': Decimal('0.00'),
            'days_1_30': Decimal('0.00'),
            'days_31_60': Decimal('0.00'),
            'days_61_90': Decimal('0.00'),
            'days_over_90': Decimal('0.00'),
            'total': Decimal('0.00')
        }
        
        # Get outstanding invoices for this supplier
        outstanding_invoices = SupplierInvoice.objects.filter(
            supplier=supplier,
            balance_due__gt=0
        )
        
        for invoice in outstanding_invoices:
            days_overdue = (as_of_date - invoice.due_date).days
            balance = invoice.balance_due
            
            if days_overdue <= 0:
                supplier_data['current'] += balance
            elif days_overdue <= 30:
                supplier_data['days_1_30'] += balance
            elif days_overdue <= 60:
                supplier_data['days_31_60'] += balance
            elif days_overdue <= 90:
                supplier_data['days_61_90'] += balance
            else:
                supplier_data['days_over_90'] += balance
            
            supplier_data['total'] += balance
        
        # Add to totals
        for key in totals:
            totals[key] += supplier_data[key]
        
        aging_data.append(supplier_data)
    
    return {
        'as_of_date': as_of_date,
        'suppliers': aging_data,
        'totals': totals
    }

def generate_production_yield_report(date_from, date_to):
    """Generate production yield analysis report"""
    from production.models import ProductionOrder
    
    # Get completed production orders in the period
    orders = ProductionOrder.objects.filter(
        closure_date__gte=date_from,
        closure_date__lte=date_to,
        status='completed'
    ).select_related('formulation', 'formulation__finished_product')
    
    # Calculate statistics
    total_orders = orders.count()
    avg_yield = orders.aggregate(avg=Avg('yield_rate'))['avg'] or Decimal('0.00')
    
    # Orders by yield status
    normal_orders = orders.filter(yield_status='normal').count()
    warning_orders = orders.filter(yield_status='warning').count()
    critical_orders = orders.filter(yield_status='critical').count()
    
    # Calculate total over-consumption cost
    total_over_consumption = Decimal('0.00')
    for order in orders:
        for line in order.consumption_lines.filter(delta_qty__gt=0):
            total_over_consumption += line.financial_impact
    
    # Top over-consuming materials
    from production.models import ProductionOrderLine
    over_consumption_by_material = {}
    
    for order in orders:
        for line in order.consumption_lines.filter(delta_qty__gt=0):
            material = line.raw_material
            if material not in over_consumption_by_material:
                over_consumption_by_material[material] = {
                    'total_over_consumption': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                    'order_count': 0
                }
            
            over_consumption_by_material[material]['total_over_consumption'] += line.delta_qty
            over_consumption_by_material[material]['total_cost'] += line.financial_impact
            over_consumption_by_material[material]['order_count'] += 1
    
    # Sort by cost impact
    top_over_consuming = sorted(
        over_consumption_by_material.items(),
        key=lambda x: x[1]['total_cost'],
        reverse=True
    )[:10]
    
    return {
        'period': {'from': date_from, 'to': date_to},
        'total_orders': total_orders,
        'avg_yield': avg_yield,
        'normal_orders': normal_orders,
        'warning_orders': warning_orders,
        'critical_orders': critical_orders,
        'total_over_consumption_cost': total_over_consumption,
        'orders': orders,
        'top_over_consuming_materials': top_over_consuming
    }

def generate_expense_breakdown_report(date_from, date_to):
    """Generate expense breakdown analysis report"""
    from expenses.models import Expense
    
    # Get expenses in the period
    expenses = Expense.objects.filter(
        expense_date__gte=date_from,
        expense_date__lte=date_to,
        status__in=['validated', 'paid']
    )
    
    # Total amount
    total_amount = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Breakdown by category
    category_breakdown = {}
    for category_code, category_name in Expense.CATEGORY_CHOICES:
        category_total = expenses.filter(category=category_code).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        if category_total > 0:
            category_breakdown[category_name] = {
                'amount': category_total,
                'percentage': (category_total / total_amount * 100) if total_amount > 0 else Decimal('0.00'),
                'count': expenses.filter(category=category_code).count()
            }
    
    # Top beneficiaries
    top_beneficiaries = expenses.values('beneficiary').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')[:10]
    
    # Monthly trend (if period spans multiple months)
    monthly_trend = []
    current_date = date_from.replace(day=1)
    
    while current_date <= date_to:
        next_month = (current_date + timedelta(days=32)).replace(day=1)
        month_total = expenses.filter(
            expense_date__gte=current_date,
            expense_date__lt=next_month
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        monthly_trend.append({
            'month': current_date.strftime('%Y-%m'),
            'total': month_total
        })
        
        current_date = next_month
    
    return {
        'period': {'from': date_from, 'to': date_to},
        'total_amount': total_amount,
        'total_count': expenses.count(),
        'category_breakdown': category_breakdown,
        'top_beneficiaries': top_beneficiaries,
        'monthly_trend': monthly_trend,
        'expenses': expenses.order_by('-expense_date')
    }

def calculate_working_capital_requirement():
    """Calculate current working capital requirement"""
    from sales.models import ClientInvoice
    from supplier_ops.models import SupplierInvoice
    
    # Outstanding client receivables
    client_receivables = ClientInvoice.objects.filter(
        balance_due__gt=0
    ).aggregate(total=Sum('balance_due'))['total'] or Decimal('0.00')
    
    # Outstanding supplier payables
    supplier_payables = SupplierInvoice.objects.filter(
        balance_due__gt=0
    ).aggregate(total=Sum('balance_due'))['total'] or Decimal('0.00')
    
    # WCR = Receivables - Payables
    wcr = client_receivables - supplier_payables
    
    return {
        'client_receivables': client_receivables,
        'supplier_payables': supplier_payables,
        'wcr': wcr
    }