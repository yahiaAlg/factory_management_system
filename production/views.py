# production/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, Avg
from django.utils import timezone
from decimal import Decimal
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import Formulation, FormulationLine, ProductionOrder, ProductionOrderLine
from .forms import (
    FormulationForm, FormulationLineFormSet, ProductionOrderForm,
    ProductionOrderCloseForm
)

@login_required
def formulations_list(request):
    """Formulations list"""
    formulations = Formulation.objects.select_related('finished_product', 'created_by').all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        formulations = formulations.filter(
            Q(reference__icontains=search) | 
            Q(designation__icontains=search) |
            Q(finished_product__designation__icontains=search)
        )
    
    # Active filter
    if request.GET.get('active') == 'false':
        formulations = formulations.filter(is_active=False)
    elif request.GET.get('active') != 'all':
        formulations = formulations.filter(is_active=True)
    
    # Product filter
    product_filter = request.GET.get('product')
    if product_filter:
        formulations = formulations.filter(finished_product_id=product_filter)
    
    context = {
        'formulations': formulations.order_by('reference', '-version'),
        'title': 'Formulations'
    }
    
    return render(request, 'production/formulations_list.html', context)

@login_required
@role_required(['manager'])
def formulation_create(request):
    """Create new formulation"""
    if request.method == 'POST':
        form = FormulationForm(request.POST)
        formset = FormulationLineFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            formulation = form.save(commit=False)
            formulation.created_by = request.user
            formulation.save()
            
            formset.instance = formulation
            formset.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='production',
                instance=formulation,
                request=request
            )
            
            messages.success(request, f"Formulation {formulation.reference} créée avec succès")
            return redirect('formulation_detail', formulation_id=formulation.id)
    else:
        form = FormulationForm()
        formset = FormulationLineFormSet()
    
    return render(request, 'production/formulation_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nouvelle formulation'
    })

@login_required
def formulation_detail(request, formulation_id):
    """Formulation detail view"""
    formulation = get_object_or_404(Formulation, id=formulation_id)
    
    # Get production orders using this formulation
    production_orders = formulation.production_orders.all().order_by('-launch_date')[:10]
    
    # Calculate statistics
    theoretical_cost = formulation.calculate_theoretical_cost()
    unit_cost = formulation.get_unit_theoretical_cost()
    
    context = {
        'formulation': formulation,
        'lines': formulation.lines.select_related('raw_material', 'unit_of_measure').all(),
        'production_orders': production_orders,
        'theoretical_cost': theoretical_cost,
        'unit_cost': unit_cost,
        'can_edit': request.user.userprofile.role == 'manager',
        'title': f'Formulation - {formulation.reference}'
    }
    
    return render(request, 'production/formulation_detail.html', context)

@login_required
@role_required(['manager'])
def formulation_edit(request, formulation_id):
    """Edit formulation (creates new version)"""
    formulation = get_object_or_404(Formulation, id=formulation_id)
    
    if request.method == 'POST':
        try:
            new_formulation = formulation.create_new_version(request.user)
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='production',
                instance=new_formulation,
                details={'previous_version': formulation.version},
                request=request
            )
            
            messages.success(request, f"Nouvelle version {new_formulation.version} créée")
            return redirect('formulation_detail', formulation_id=new_formulation.id)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('formulation_detail', formulation_id=formulation.id)
    
    return redirect('formulation_detail', formulation_id=formulation.id)

@login_required
def production_orders_list(request):
    """Production orders list"""
    orders = ProductionOrder.objects.select_related(
        'formulation', 'formulation__finished_product', 'created_by'
    ).all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        orders = orders.filter(
            Q(reference__icontains=search) | 
            Q(formulation__designation__icontains=search)
        )
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    # Yield status filter
    yield_filter = request.GET.get('yield_status')
    if yield_filter:
        orders = orders.filter(yield_status=yield_filter)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        orders = orders.filter(launch_date__gte=date_from)
    if date_to:
        orders = orders.filter(launch_date__lte=date_to)
    
    context = {
        'orders': orders.order_by('-launch_date'),
        'status_choices': ProductionOrder.STATUS_CHOICES,
        'yield_choices': ProductionOrder.YIELD_STATUS_CHOICES,
        'title': 'Ordres de production'
    }
    
    return render(request, 'production/production_orders_list.html', context)

@login_required
@role_required(['manager', 'stock_prod'])
def production_order_create(request):
    """Create new production order"""
    if request.method == 'POST':
        form = ProductionOrderForm(request.POST)
        
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='production',
                instance=order,
                request=request
            )
            
            messages.success(request, f"Ordre de production {order.reference} créé avec succès")
            return redirect('production_order_detail', order_id=order.id)
    else:
        form = ProductionOrderForm()
    
    return render(request, 'production/production_order_form.html', {
        'form': form,
        'title': 'Nouvel ordre de production'
    })

@login_required
def production_order_detail(request, order_id):
    """Production order detail view"""
    order = get_object_or_404(ProductionOrder, id=order_id)
    
    context = {
        'order': order,
        'consumption_lines': order.consumption_lines.select_related('raw_material').all(),
        'can_launch': (
            request.user.userprofile.role in ['manager', 'stock_prod'] and 
            order.status == 'pending'
        ),
        'can_close': (
            request.user.userprofile.role in ['manager', 'stock_prod'] and 
            order.status == 'in_progress'
        ),
        'title': f'Ordre de Production - {order.reference}'
    }
    
    return render(request, 'production/production_order_detail.html', context)

@login_required
@role_required(['manager', 'stock_prod'])
def production_order_launch(request, order_id):
    """Launch production order"""
    order = get_object_or_404(ProductionOrder, id=order_id)
    
    if request.method == 'POST':
        try:
            order.launch(request.user)
            
            AuditLog.log_action(
                user=request.user,
                action_type='validate',
                module='production',
                instance=order,
                details={'action': 'launch'},
                request=request
            )
            
            messages.success(request, f"Ordre de production {order.reference} lancé")
        except ValueError as e:
            messages.error(request, str(e))
        
        return redirect('production_order_detail', order_id=order.id)
    
    return redirect('production_order_detail', order_id=order.id)

@login_required
@role_required(['manager', 'stock_prod'])
def production_order_close(request, order_id):
    """Close production order with actual results"""
    order = get_object_or_404(ProductionOrder, id=order_id)
    
    if order.status != 'in_progress':
        messages.error(request, "Cet ordre ne peut pas être clôturé")
        return redirect('production_order_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = ProductionOrderCloseForm(request.POST, instance=order)
        
        if form.is_valid():
            actual_qty_produced = form.cleaned_data['actual_qty_produced']
            
            # Get consumption data from form
            consumption_data = {}
            for line in order.consumption_lines.all():
                field_name = f'consumption_{line.id}'
                if field_name in form.cleaned_data:
                    consumption_data[line.raw_material_id] = form.cleaned_data[field_name]
            
            try:
                order.close(request.user, actual_qty_produced, consumption_data)
                
                AuditLog.log_action(
                    user=request.user,
                    action_type='validate',
                    module='production',
                    instance=order,
                    details={'action': 'close', 'yield_rate': str(order.yield_rate)},
                    request=request
                )
                
                messages.success(request, f"Ordre de production {order.reference} clôturé")
                return redirect('production_order_detail', order_id=order.id)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = ProductionOrderCloseForm(instance=order)
    
    return render(request, 'production/production_order_close.html', {
        'form': form,
        'order': order,
        'title': f'Clôture OP - {order.reference}'
    })

@login_required
def formulation_scaling_ajax(request):
    """AJAX endpoint for formulation scaling preview"""
    if request.method == 'GET':
        formulation_id = request.GET.get('formulation_id')
        target_qty = request.GET.get('target_qty')
        
        if formulation_id and target_qty:
            try:
                formulation = Formulation.objects.get(id=formulation_id)
                target_qty = Decimal(target_qty)
                
                scaling_factor = target_qty / formulation.reference_batch_qty
                
                lines_data = []
                for line in formulation.lines.all():
                    theoretical_qty = line.qty_per_batch * scaling_factor
                    
                    # Check stock availability
                    from stock.models import RawMaterialStockBalance
                    try:
                        balance = RawMaterialStockBalance.objects.get(raw_material=line.raw_material)
                        available_qty = balance.quantity
                        sufficient = available_qty >= theoretical_qty
                    except RawMaterialStockBalance.DoesNotExist:
                        available_qty = Decimal('0.000')
                        sufficient = False
                    
                    lines_data.append({
                        'material_id': line.raw_material.id,
                        'material_name': line.raw_material.designation,
                        'theoretical_qty': str(theoretical_qty),
                        'unit': line.unit_of_measure.symbol,
                        'available_qty': str(available_qty),
                        'sufficient': sufficient
                    })
                
                return JsonResponse({
                    'success': True,
                    'scaling_factor': str(scaling_factor),
                    'lines': lines_data
                })
            except (Formulation.DoesNotExist, ValueError):
                pass
    
    return JsonResponse({'success': False, 'error': 'Paramètres invalides'})

@login_required
def production_yield_report(request):
    """Production yield analysis report"""
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    orders = ProductionOrder.objects.filter(status='completed')
    
    if date_from:
        orders = orders.filter(closure_date__gte=date_from)
    if date_to:
        orders = orders.filter(closure_date__lte=date_to)
    
    # Calculate statistics
    stats = orders.aggregate(
        total_orders=models.Count('id'),
        avg_yield=Avg('yield_rate'),
        total_over_consumption_cost=Sum('consumption_lines__financial_impact')
    )
    
    # Get orders with yield issues
    warning_orders = orders.filter(yield_status='warning')
    critical_orders = orders.filter(yield_status='critical')
    
    context = {
        'orders': orders.order_by('-closure_date')[:50],
        'stats': stats,
        'warning_orders': warning_orders,
        'critical_orders': critical_orders,
        'title': 'Analyse des rendements de production'
    }
    
    return render(request, 'production/yield_report.html', context)