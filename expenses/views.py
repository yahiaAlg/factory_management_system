# expenses/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.utils import timezone
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Expense, SupportingDocument, ExpenseCategory
from .forms import ExpenseForm, SupportingDocumentForm

@login_required
def expenses_list(request):
    """Expenses list"""
    expenses = Expense.objects.select_related('created_by', 'validated_by').all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        expenses = expenses.filter(
            Q(reference__icontains=search) | 
            Q(description__icontains=search) |
            Q(beneficiary__icontains=search)
        )
    
    # Category filter
    category_filter = request.GET.get('category')
    if category_filter:
        expenses = expenses.filter(category=category_filter)
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        expenses = expenses.filter(status=status_filter)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)
    
    # Pending validation filter
    if request.GET.get('pending_validation') == 'true':
        expenses = expenses.filter(status='recorded')
    
    # Calculate totals
    total_amount = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    validated_amount = expenses.filter(status__in=['validated', 'paid']).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    paid_amount = expenses.filter(status='paid').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    context = {
        'expenses': expenses.order_by('-expense_date'),
        'category_choices': Expense.CATEGORY_CHOICES,
        'status_choices': Expense.STATUS_CHOICES,
        'total_amount': total_amount,
        'validated_amount': validated_amount,
        'paid_amount': paid_amount,
        'title': 'Gestion des dépenses'
    }
    
    return render(request, 'expenses/expenses_list.html', context)

@login_required
@role_required(['manager', 'accountant'])
def expense_create(request):
    """Create new expense"""
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        
        if form.is_valid():
            expense = form.save(commit=False)
            expense.created_by = request.user
            expense.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='expenses',
                instance=expense,
                request=request
            )
            
            messages.success(request, f"Dépense {expense.reference} créée avec succès")
            return redirect('expense_detail', expense_id=expense.id)
    else:
        form = ExpenseForm()
    
    return render(request, 'expenses/expense_form.html', {
        'form': form,
        'title': 'Nouvelle dépense'
    })

@login_required
def expense_detail(request, expense_id):
    """Expense detail view"""
    expense = get_object_or_404(Expense, id=expense_id)
    
    # Get supporting documents
    supporting_docs = SupportingDocument.objects.filter(
        entity_type='expense',
        entity_id=expense.id
    )
    
    context = {
        'expense': expense,
        'supporting_docs': supporting_docs,
        'can_validate': (
            request.user.userprofile.role in ['manager', 'accountant'] and 
            expense.status == 'recorded'
        ),
        'can_mark_paid': (
            request.user.userprofile.role in ['manager', 'accountant'] and 
            expense.status == 'validated'
        ),
        'requires_manager': expense.requires_manager_approval(),
        'title': f'Dépense - {expense.reference}'
    }
    
    return render(request, 'expenses/expense_detail.html', context)

@login_required
@role_required(['manager', 'accountant'])
def expense_validate(request, expense_id):
    """Validate expense"""
    expense = get_object_or_404(Expense, id=expense_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        try:
            if action == 'validate':
                expense.validate(request.user)
                
                AuditLog.log_action(
                    user=request.user,
                    action_type='validate',
                    module='expenses',
                    instance=expense,
                    request=request
                )
                
                messages.success(request, f"Dépense {expense.reference} validée")
                
            elif action == 'reject':
                reason = request.POST.get('rejection_reason', '')
                if not reason:
                    messages.error(request, "Le motif de rejet est obligatoire")
                    return redirect('expense_detail', expense_id=expense.id)
                
                expense.reject(request.user, reason)
                
                AuditLog.log_action(
                    user=request.user,
                    action_type='update',
                    module='expenses',
                    instance=expense,
                    details={'action': 'reject', 'reason': reason},
                    request=request
                )
                
                messages.success(request, f"Dépense {expense.reference} rejetée")
                
        except ValueError as e:
            messages.error(request, str(e))
        
        return redirect('expense_detail', expense_id=expense.id)
    
    return redirect('expense_detail', expense_id=expense.id)

@login_required
@role_required(['manager', 'accountant'])
def expense_mark_paid(request, expense_id):
    """Mark expense as paid"""
    expense = get_object_or_404(Expense, id=expense_id)
    
    if request.method == 'POST':
        payment_date = request.POST.get('payment_date')
        payment_method = request.POST.get('payment_method')
        
        if not payment_date or not payment_method:
            messages.error(request, "Date et mode de paiement sont obligatoires")
            return redirect('expense_detail', expense_id=expense.id)
        
        try:
            from datetime import datetime
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
            
            expense.mark_as_paid(request.user, payment_date, payment_method)
            
            AuditLog.log_action(
                user=request.user,
                action_type='pay',
                module='expenses',
                instance=expense,
                details={'payment_date': str(payment_date), 'payment_method': payment_method},
                request=request
            )
            
            messages.success(request, f"Dépense {expense.reference} marquée comme payée")
            
        except (ValueError, Exception) as e:
            messages.error(request, f"Erreur: {str(e)}")
        
        return redirect('expense_detail', expense_id=expense.id)
    
    return redirect('expense_detail', expense_id=expense.id)

@login_required
@role_required(['manager', 'accountant'])
def supporting_document_create(request, expense_id):
    """Create supporting document for expense"""
    expense = get_object_or_404(Expense, id=expense_id)
    
    if request.method == 'POST':
        form = SupportingDocumentForm(request.POST)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.entity_type = 'expense'
            doc.entity_id = expense.id
            doc.registered_by = request.user
            doc.save()
            
            messages.success(request, "Document justificatif ajouté avec succès")
            return redirect('expense_detail', expense_id=expense.id)
    else:
        form = SupportingDocumentForm(initial={'doc_type': 'SD-EXP'})
    
    return render(request, 'expenses/supporting_document_form.html', {
        'form': form,
        'expense': expense,
        'title': f'Ajouter justificatif - {expense.reference}'
    })

@login_required
def expenses_dashboard(request):
    """Expenses dashboard with analytics"""
    # Current month stats
    current_month = timezone.now().replace(day=1)
    next_month = (current_month + timezone.timedelta(days=32)).replace(day=1)
    
    # Monthly expenses
    monthly_recorded = Expense.objects.filter(
        expense_date__gte=current_month,
        expense_date__lt=next_month,
        status__in=['recorded', 'validated', 'paid']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    monthly_paid = Expense.objects.filter(
        expense_date__gte=current_month,
        expense_date__lt=next_month,
        status='paid'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Pending validation
    pending_validation = Expense.objects.filter(status='recorded')
    pending_amount = pending_validation.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Expenses by category (current month)
    category_breakdown = {}
    for category_code, category_name in Expense.CATEGORY_CHOICES:
        amount = Expense.objects.filter(
            category=category_code,
            expense_date__gte=current_month,
            expense_date__lt=next_month,
            status__in=['validated', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        if amount > 0:
            category_breakdown[category_name] = amount
    
    # Recent expenses
    recent_expenses = Expense.objects.select_related('created_by').order_by('-created_at')[:10]
    
    # Overdue validations
    overdue_validations = Expense.objects.filter(
        status='recorded',
        expense_date__lt=timezone.now().date() - timezone.timedelta(days=7)
    )
    
    context = {
        'monthly_recorded': monthly_recorded,
        'monthly_paid': monthly_paid,
        'pending_amount': pending_amount,
        'pending_count': pending_validation.count(),
        'category_breakdown': category_breakdown,
        'recent_expenses': recent_expenses,
        'overdue_validations': overdue_validations,
        'title': 'Tableau de bord dépenses'
    }
    
    return render(request, 'expenses/expenses_dashboard.html', context)

@login_required
def expenses_report(request):
    """Expenses analysis report"""
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    expenses = Expense.objects.filter(status__in=['validated', 'paid'])
    
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)
    
    # Category breakdown
    category_totals = {}
    for category_code, category_name in Expense.CATEGORY_CHOICES:
        total = expenses.filter(category=category_code).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        if total > 0:
            category_totals[category_name] = total
    
    # Monthly trend (last 12 months)
    monthly_trend = []
    for i in range(12):
        month_date = timezone.now().replace(day=1) - timezone.timedelta(days=30*i)
        next_month = (month_date + timezone.timedelta(days=32)).replace(day=1)
        
        monthly_total = Expense.objects.filter(
            expense_date__gte=month_date,
            expense_date__lt=next_month,
            status__in=['validated', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        monthly_trend.append({
            'month': month_date.strftime('%Y-%m'),
            'total': monthly_total
        })
    
    monthly_trend.reverse()
    
    # Top beneficiaries
    top_beneficiaries = expenses.values('beneficiary').annotate(
        total=Sum('amount')
    ).order_by('-total')[:10]
    
    context = {
        'expenses': expenses.order_by('-expense_date')[:100],
        'category_totals': category_totals,
        'monthly_trend': monthly_trend,
        'top_beneficiaries': top_beneficiaries,
        'total_amount': sum(category_totals.values()),
        'title': 'Rapport d\'analyse des dépenses'
    }
    
    return render(request, 'expenses/expenses_report.html', context)