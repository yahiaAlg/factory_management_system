from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.utils import timezone
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Client
from .forms import ClientForm

@login_required
def clients_list(request):
    """Clients directory list"""
    clients = Client.objects.all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        clients = clients.filter(
            Q(code__icontains=search) | 
            Q(raison_sociale__icontains=search) |
            Q(nif__icontains=search) |
            Q(nis__icontains=search)
        )
    
    # Credit status filter
    credit_status_filter = request.GET.get('credit_status')
    if credit_status_filter:
        clients = clients.filter(credit_status=credit_status_filter)
    
    # Wilaya filter
    wilaya_filter = request.GET.get('wilaya')
    if wilaya_filter:
        clients = clients.filter(wilaya=wilaya_filter)
    
    # Active filter
    if request.GET.get('active') == 'false':
        clients = clients.filter(is_active=False)
    elif request.GET.get('active') != 'all':
        clients = clients.filter(is_active=True)
    
    # Get unique wilayas and credit statuses for filters
    wilayas = Client.objects.values_list('wilaya', flat=True).distinct().exclude(wilaya='')
    credit_statuses = Client.CREDIT_STATUS_CHOICES
    
    context = {
        'clients': clients.order_by('raison_sociale'),
        'wilayas': sorted(wilayas),
        'credit_statuses': credit_statuses,
        'title': 'Répertoire clients'
    }
    
    return render(request, 'clients/clients_list.html', context)

@login_required
@role_required(['manager', 'sales'])
def client_create(request):
    """Create new client"""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='clients',
                instance=client,
                request=request
            )
            
            messages.success(request, f"Client {client.code} créé avec succès")
            return redirect('clients_list')
    else:
        form = ClientForm()
    
    return render(request, 'clients/client_form.html', {
        'form': form,
        'title': 'Nouveau client'
    })

@login_required
def client_detail(request, client_id):
    """Client detail view"""
    client = get_object_or_404(Client, id=client_id)
    
    # Get recent deliveries and invoices
    recent_deliveries = client.get_recent_deliveries(10)
    recent_invoices = client.get_recent_invoices(10)
    
    # Calculate statistics
    current_year = timezone.now().year
    total_sales_current_year = client.get_total_sales_amount(current_year)
    total_sales_previous_year = client.get_total_sales_amount(current_year - 1)
    outstanding_balance = client.get_outstanding_balance()
    
    context = {
        'client': client,
        'recent_deliveries': recent_deliveries,
        'recent_invoices': recent_invoices,
        'total_sales_current_year': total_sales_current_year,
        'total_sales_previous_year': total_sales_previous_year,
        'outstanding_balance': outstanding_balance,
        'title': f'Client - {client.code}'
    }
    
    return render(request, 'clients/client_detail.html', context)

@login_required
@role_required(['manager', 'sales'])
def client_edit(request, client_id):
    """Edit client"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            old_values = {
                'raison_sociale': client.raison_sociale,
                'address': client.address,
                'payment_terms': client.payment_terms,
                'credit_status': client.credit_status,
            }
            
            client = form.save()
            
            new_values = {
                'raison_sociale': client.raison_sociale,
                'address': client.address,
                'payment_terms': client.payment_terms,
                'credit_status': client.credit_status,
            }
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='clients',
                instance=client,
                details={'before': old_values, 'after': new_values},
                request=request
            )
            
            messages.success(request, f"Client {client.code} modifié avec succès")
            return redirect('client_detail', client_id=client.id)
    else:
        form = ClientForm(instance=client)
    
    return render(request, 'clients/client_form.html', {
        'form': form,
        'client': client,
        'title': f'Modifier - {client.code}'
    })

@login_required
@role_required(['manager', 'sales'])
def client_toggle_active(request, client_id):
    """Toggle client active status via AJAX"""
    if request.method == 'POST':
        try:
            client = Client.objects.get(id=client_id)
            old_status = client.is_active
            client.is_active = not client.is_active
            client.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='clients',
                instance=client,
                details={
                    'field_changed': 'is_active',
                    'before': old_status,
                    'after': client.is_active
                },
                request=request
            )
            
            return JsonResponse({
                'success': True,
                'is_active': client.is_active,
                'message': f"Client {'activé' if client.is_active else 'désactivé'}"
            })
        except Client.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Client non trouvé'})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

@login_required
@role_required(['manager'])
def client_update_credit_status(request, client_id):
    """Update client credit status via AJAX"""
    if request.method == 'POST':
        try:
            client = Client.objects.get(id=client_id)
            new_status = request.POST.get('credit_status')
            
            if new_status not in dict(Client.CREDIT_STATUS_CHOICES):
                return JsonResponse({'success': False, 'error': 'Statut invalide'})
            
            old_status = client.credit_status
            client.credit_status = new_status
            client.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='clients',
                instance=client,
                details={
                    'field_changed': 'credit_status',
                    'before': old_status,
                    'after': new_status
                },
                request=request
            )
            
            return JsonResponse({
                'success': True,
                'credit_status': new_status,
                'message': f"Statut crédit mis à jour"
            })
        except Client.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Client non trouvé'})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

@login_required
def client_search_ajax(request):
    """AJAX endpoint for client search in dropdowns"""
    search = request.GET.get('q', '')
    clients = Client.objects.filter(
        Q(code__icontains=search) | Q(raison_sociale__icontains=search),
        is_active=True,
        credit_status__in=['active', 'suspended']
    )[:20]
    
    results = [
        {
            'id': client.id,
            'code': client.code,
            'raison_sociale': client.raison_sociale,
            'display': f"{client.code} - {client.raison_sociale}",
            'credit_status': client.credit_status,
            'can_order': client.can_place_order()
        }
        for client in clients
    ]
    
    return JsonResponse({'results': results})