from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Supplier
from .forms import SupplierForm

@login_required
def suppliers_list(request):
    """Suppliers directory list"""
    suppliers = Supplier.objects.all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        suppliers = suppliers.filter(
            Q(code__icontains=search) | 
            Q(raison_sociale__icontains=search) |
            Q(nif__icontains=search) |
            Q(nis__icontains=search)
        )
    
    # Currency filter
    currency_filter = request.GET.get('currency')
    if currency_filter:
        suppliers = suppliers.filter(currency=currency_filter)
    
    # Wilaya filter
    wilaya_filter = request.GET.get('wilaya')
    if wilaya_filter:
        suppliers = suppliers.filter(wilaya=wilaya_filter)
    
    # Active filter
    if request.GET.get('active') == 'false':
        suppliers = suppliers.filter(is_active=False)
    elif request.GET.get('active') != 'all':
        suppliers = suppliers.filter(is_active=True)
    
    # Get unique wilayas and currencies for filters
    wilayas = Supplier.objects.values_list('wilaya', flat=True).distinct().exclude(wilaya='')
    currencies = Supplier.CURRENCY_CHOICES
    
    context = {
        'suppliers': suppliers.order_by('raison_sociale'),
        'wilayas': sorted(wilayas),
        'currencies': currencies,
        'title': 'Répertoire fournisseurs'
    }
    
    return render(request, 'suppliers/suppliers_list.html', context)

@login_required
@role_required(['manager', 'accountant'])
def supplier_create(request):
    """Create new supplier"""
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='suppliers',
                instance=supplier,
                request=request
            )
            
            messages.success(request, f"Fournisseur {supplier.code} créé avec succès")
            return redirect('suppliers_list')
    else:
        form = SupplierForm()
    
    return render(request, 'suppliers/supplier_form.html', {
        'form': form,
        'title': 'Nouveau fournisseur'
    })

@login_required
def supplier_detail(request, supplier_id):
    """Supplier detail view"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # Get recent deliveries and invoices
    recent_deliveries = supplier.get_recent_deliveries(10)
    recent_invoices = supplier.get_recent_invoices(10)
    
    # Calculate statistics
    current_year = timezone.now().year
    total_purchases_current_year = supplier.get_total_purchases_amount(current_year)
    total_purchases_previous_year = supplier.get_total_purchases_amount(current_year - 1)
    outstanding_balance = supplier.get_outstanding_balance()
    
    context = {
        'supplier': supplier,
        'recent_deliveries': recent_deliveries,
        'recent_invoices': recent_invoices,
        'total_purchases_current_year': total_purchases_current_year,
        'total_purchases_previous_year': total_purchases_previous_year,
        'outstanding_balance': outstanding_balance,
        'title': f'Fournisseur - {supplier.code}'
    }
    
    return render(request, 'suppliers/supplier_detail.html', context)

@login_required
@role_required(['manager', 'accountant'])
def supplier_edit(request, supplier_id):
    """Edit supplier"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            old_values = {
                'raison_sociale': supplier.raison_sociale,
                'address': supplier.address,
                'payment_terms': supplier.payment_terms,
                'currency': supplier.currency,
            }
            
            supplier = form.save()
            
            new_values = {
                'raison_sociale': supplier.raison_sociale,
                'address': supplier.address,
                'payment_terms': supplier.payment_terms,
                'currency': supplier.currency,
            }
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='suppliers',
                instance=supplier,
                details={'before': old_values, 'after': new_values},
                request=request
            )
            
            messages.success(request, f"Fournisseur {supplier.code} modifié avec succès")
            return redirect('supplier_detail', supplier_id=supplier.id)
    else:
        form = SupplierForm(instance=supplier)
    
    return render(request, 'suppliers/supplier_form.html', {
        'form': form,
        'supplier': supplier,
        'title': f'Modifier - {supplier.code}'
    })

@login_required
@role_required(['manager', 'accountant'])
def supplier_toggle_active(request, supplier_id):
    """Toggle supplier active status via AJAX"""
    if request.method == 'POST':
        try:
            supplier = Supplier.objects.get(id=supplier_id)
            old_status = supplier.is_active
            supplier.is_active = not supplier.is_active
            supplier.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='suppliers',
                instance=supplier,
                details={
                    'field_changed': 'is_active',
                    'before': old_status,
                    'after': supplier.is_active
                },
                request=request
            )
            
            return JsonResponse({
                'success': True,
                'is_active': supplier.is_active,
                'message': f"Fournisseur {'activé' if supplier.is_active else 'désactivé'}"
            })
        except Supplier.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Fournisseur non trouvé'})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

@login_required
def supplier_search_ajax(request):
    """AJAX endpoint for supplier search in dropdowns"""
    search = request.GET.get('q', '')
    suppliers = Supplier.objects.filter(
        Q(code__icontains=search) | Q(raison_sociale__icontains=search),
        is_active=True
    )[:20]
    
    results = [
        {
            'id': supplier.id,
            'code': supplier.code,
            'raison_sociale': supplier.raison_sociale,
            'display': f"{supplier.code} - {supplier.raison_sociale}"
        }
        for supplier in suppliers
    ]
    
    return JsonResponse({'results': results})