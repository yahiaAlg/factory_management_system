from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from decimal import Decimal
import csv
from accounts.utils import role_required
from .models import FinancialPeriod, ReportTemplate, ReportExecution
from .utils import (
    generate_financial_result_report, generate_receivables_aging_report,
    generate_payables_aging_report, generate_production_yield_report,
    generate_expense_breakdown_report
)

@login_required
def reporting_dashboard(request):
    """Main reporting dashboard"""
    # Recent report executions
    recent_executions = ReportExecution.objects.select_related('template').order_by('-execution_date')[:10]
    
    # Available report templates
    templates = ReportTemplate.objects.filter(is_active=True).order_by('report_type', 'name')
    
    # Quick stats
    current_month = timezone.now().replace(day=1)
    next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
    
    # Get current month financial summary
    from sales.models import ClientInvoice, ClientPayment
    from supplier_ops.models import SupplierInvoice, SupplierPayment
    from expenses.models import Expense
    
    monthly_revenue = ClientInvoice.objects.filter(
        invoice_date__gte=current_month,
        invoice_date__lt=next_month
    ).aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
    
    monthly_expenses = Expense.objects.filter(
        expense_date__gte=current_month,
        expense_date__lt=next_month,
        status__in=['validated', 'paid']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context = {
        'recent_executions': recent_executions,
        'templates': templates,
        'monthly_revenue': monthly_revenue,
        'monthly_expenses': monthly_expenses,
        'title': 'Tableau de bord reporting'
    }
    
    return render(request, 'reporting/reporting_dashboard.html', context)

@login_required
@role_required(['manager', 'accountant', 'viewer'])
def financial_result_report(request):
    """Financial result report"""
    # Date range parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from or not date_to:
        # Default to current month
        current_month = timezone.now().replace(day=1)
        next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
        date_from = current_month.date()
        date_to = (next_month - timezone.timedelta(days=1)).date()
    else:
        from datetime import datetime
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Generate report data
    report_data = generate_financial_result_report(date_from, date_to)
    
    context = {
        'report_data': report_data,
        'date_from': date_from,
        'date_to': date_to,
        'title': 'Rapport de résultat financier'
    }
    
    return render(request, 'reporting/financial_result_report.html', context)

@login_required
@role_required(['manager', 'accountant', 'sales', 'viewer'])
def receivables_aging_report(request):
    """Client receivables aging report"""
    as_of_date = request.GET.get('as_of_date')
    
    if not as_of_date:
        as_of_date = timezone.now().date()
    else:
        from datetime import datetime
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    
    # Generate report data
    report_data = generate_receivables_aging_report(as_of_date)
    
    context = {
        'report_data': report_data,
        'as_of_date': as_of_date,
        'title': 'Échéancier clients'
    }
    
    return render(request, 'reporting/receivables_aging_report.html', context)

@login_required
@role_required(['manager', 'accountant', 'viewer'])
def payables_aging_report(request):
    """Supplier payables aging report"""
    as_of_date = request.GET.get('as_of_date')
    
    if not as_of_date:
        as_of_date = timezone.now().date()
    else:
        from datetime import datetime
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    
    # Generate report data
    report_data = generate_payables_aging_report(as_of_date)
    
    context = {
        'report_data': report_data,
        'as_of_date': as_of_date,
        'title': 'Échéancier fournisseurs'
    }
    
    return render(request, 'reporting/payables_aging_report.html', context)

@login_required
@role_required(['manager', 'stock_prod', 'viewer'])
def production_yield_report(request):
    """Production yield analysis report"""
    # Date range parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from or not date_to:
        # Default to current month
        current_month = timezone.now().replace(day=1)
        next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
        date_from = current_month.date()
        date_to = (next_month - timezone.timedelta(days=1)).date()
    else:
        from datetime import datetime
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Generate report data
    report_data = generate_production_yield_report(date_from, date_to)
    
    context = {
        'report_data': report_data,
        'date_from': date_from,
        'date_to': date_to,
        'title': 'Analyse des rendements de production'
    }
    
    return render(request, 'reporting/production_yield_report.html', context)

@login_required
@role_required(['manager', 'accountant', 'viewer'])
def expense_breakdown_report(request):
    """Expense breakdown analysis report"""
    # Date range parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from or not date_to:
        # Default to current month
        current_month = timezone.now().replace(day=1)
        next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
        date_from = current_month.date()
        date_to = (next_month - timezone.timedelta(days=1)).date()
    else:
        from datetime import datetime
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Generate report data
    report_data = generate_expense_breakdown_report(date_from, date_to)
    
    context = {
        'report_data': report_data,
        'date_from': date_from,
        'date_to': date_to,
        'title': 'Répartition des dépenses'
    }
    
    return render(request, 'reporting/expense_breakdown_report.html', context)

@login_required
@role_required(['manager', 'accountant', 'viewer'])
def stock_valuation_report(request):
    """Stock valuation report"""
    from stock.models import RawMaterialStockBalance, FinishedProductStockBalance
    
    # Raw materials stock valuation
    rm_balances = RawMaterialStockBalance.objects.select_related('raw_material').filter(
        quantity__gt=0
    )
    
    rm_total_value = Decimal('0.00')
    rm_data = []
    
    for balance in rm_balances:
        value = balance.get_stock_value()
        rm_total_value += value
        rm_data.append({
            'material': balance.raw_material,
            'quantity': balance.quantity,
            'unit_price': balance.raw_material.reference_price,
            'value': value,
            'status': balance.get_stock_status()
        })
    
    # Finished products stock valuation
    fp_balances = FinishedProductStockBalance.objects.select_related('finished_product').filter(
        quantity__gt=0
    )
    
    fp_total_value = Decimal('0.00')
    fp_data = []
    
    for balance in fp_balances:
        value = balance.get_stock_value()
        fp_total_value += value
        fp_data.append({
            'product': balance.finished_product,
            'quantity': balance.quantity,
            'unit_cost': balance.weighted_average_cost,
            'value': value,
            'status': balance.get_stock_status()
        })
    
    total_stock_value = rm_total_value + fp_total_value
    
    context = {
        'rm_data': rm_data,
        'fp_data': fp_data,
        'rm_total_value': rm_total_value,
        'fp_total_value': fp_total_value,
        'total_stock_value': total_stock_value,
        'title': 'Valorisation des stocks'
    }
    
    return render(request, 'reporting/stock_valuation_report.html', context)

@login_required
@role_required(['manager', 'accountant'])
def export_report_csv(request, report_type):
    """Export report data to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    
    # Get parameters from request
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if report_type == 'financial_result':
        if date_from and date_to:
            from datetime import datetime
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            
            report_data = generate_financial_result_report(date_from, date_to)
            
            writer.writerow(['Rapport de Résultat Financier'])
            writer.writerow(['Période', f'{date_from} - {date_to}'])
            writer.writerow([])
            writer.writerow(['Indicateur', 'Montant (DZD)'])
            writer.writerow(['Revenus facturés', report_data['invoiced_revenue']])
            writer.writerow(['Revenus encaissés', report_data['collected_revenue']])
            writer.writerow(['Charges engagées', report_data['total_committed_charges']])
            writer.writerow(['Charges payées', report_data['total_paid_charges']])
            writer.writerow(['Résultat théorique', report_data['theoretical_result']])
            writer.writerow(['Résultat réel', report_data['actual_cash_result']])
    
    elif report_type == 'receivables_aging':
        as_of_date = request.GET.get('as_of_date', timezone.now().date())
        if isinstance(as_of_date, str):
            from datetime import datetime
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        report_data = generate_receivables_aging_report(as_of_date)
        
        writer.writerow(['Échéancier Clients'])
        writer.writerow(['Date', as_of_date])
        writer.writerow([])
        writer.writerow(['Client', 'Courant', '1-30 jours', '31-60 jours', '61-90 jours', '> 90 jours', 'Total'])
        
        for client_data in report_data['clients']:
            writer.writerow([
                client_data['client'].raison_sociale,
                client_data['current'],
                client_data['days_1_30'],
                client_data['days_31_60'],
                client_data['days_61_90'],
                client_data['days_over_90'],
                client_data['total']
            ])
    
    return response

@login_required
def kpi_dashboard_ajax(request):
    """AJAX endpoint for KPI dashboard data"""
    if request.method == 'GET':
        period = request.GET.get('period', 'month')  # month, quarter, year
        
        # Calculate date range based on period
        now = timezone.now()
        if period == 'month':
            start_date = now.replace(day=1)
            end_date = (start_date + timezone.timedelta(days=32)).replace(day=1)
        elif period == 'quarter':
            quarter = (now.month - 1) // 3 + 1
            start_date = now.replace(month=(quarter-1)*3+1, day=1)
            end_date = (start_date + timezone.timedelta(days=93)).replace(day=1)
        else:  # year
            start_date = now.replace(month=1, day=1)
            end_date = now.replace(year=now.year+1, month=1, day=1)
        
        # Generate KPI data
        from sales.models import ClientInvoice, ClientPayment
        from supplier_ops.models import SupplierInvoice, SupplierPayment
        from expenses.models import Expense
        
        revenue = ClientInvoice.objects.filter(
            invoice_date__gte=start_date,
            invoice_date__lt=end_date
        ).aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
        
        expenses = Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lt=end_date,
            status__in=['validated', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        supplier_charges = SupplierInvoice.objects.filter(
            invoice_date__gte=start_date,
            invoice_date__lt=end_date
        ).aggregate(total=Sum('total_ttc'))['total'] or Decimal('0.00')
        
        total_charges = expenses + supplier_charges
        result = revenue - total_charges
        
        return JsonResponse({
            'success': True,
            'period': period,
            'revenue': str(revenue),
            'expenses': str(expenses),
            'supplier_charges': str(supplier_charges),
            'total_charges': str(total_charges),
            'result': str(result)
        })
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})