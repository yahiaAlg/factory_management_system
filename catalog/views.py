# catalog/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import RawMaterial, FinishedProduct, RawMaterialCategory, UnitOfMeasure
from .forms import RawMaterialForm, FinishedProductForm, RawMaterialCategoryForm

@login_required
def raw_materials_list(request):
    """Raw materials catalog list"""
    materials = RawMaterial.objects.select_related(
        'category', 'unit_of_measure', 'default_supplier'
    ).all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        materials = materials.filter(
            Q(reference__icontains=search) | 
            Q(designation__icontains=search)
        )
    
    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        materials = materials.filter(category_id=category_id)
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        # This would need additional logic to filter by stock status
        pass
    
    # Active filter
    if request.GET.get('active') == 'false':
        materials = materials.filter(is_active=False)
    elif request.GET.get('active') != 'all':
        materials = materials.filter(is_active=True)
    
    categories = RawMaterialCategory.objects.filter(is_active=True)
    
    context = {
        'materials': materials,
        'categories': categories,
        'title': 'Catalogue matières premières'
    }
    
    return render(request, 'catalog/raw_materials_list.html', context)

@login_required
@role_required(['manager'])
def raw_material_create(request):
    """Create new raw material"""
    if request.method == 'POST':
        form = RawMaterialForm(request.POST)
        if form.is_valid():
            material = form.save(commit=False)
            material.created_by = request.user
            material.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='catalog',
                instance=material,
                request=request
            )
            
            messages.success(request, f"Matière première {material.reference} créée avec succès")
            return redirect('raw_materials_list')
    else:
        form = RawMaterialForm()
    
    return render(request, 'catalog/raw_material_form.html', {
        'form': form,
        'title': 'Nouvelle matière première'
    })

@login_required
def raw_material_detail(request, material_id):
    """Raw material detail view"""
    material = get_object_or_404(RawMaterial, id=material_id)
    
    # Get stock movements history
    stock_movements = []
    try:
        from stock.models import StockMovement
        stock_movements = StockMovement.objects.filter(
            raw_material=material
        ).order_by('-created_at')[:20]
    except:
        pass
    
    context = {
        'material': material,
        'stock_movements': stock_movements,
        'current_stock': material.get_current_stock(),
        'stock_status': material.get_stock_status(),
        'title': f'Matière première - {material.reference}'
    }
    
    return render(request, 'catalog/raw_material_detail.html', context)

@login_required
@role_required(['manager'])
def raw_material_edit(request, material_id):
    """Edit raw material"""
    material = get_object_or_404(RawMaterial, id=material_id)
    
    if request.method == 'POST':
        form = RawMaterialForm(request.POST, instance=material)
        if form.is_valid():
            old_values = {
                'designation': material.designation,
                'reference_price': str(material.reference_price),
                'alert_threshold': str(material.alert_threshold),
                'stockout_threshold': str(material.stockout_threshold),
            }
            
            material = form.save()
            
            new_values = {
                'designation': material.designation,
                'reference_price': str(material.reference_price),
                'alert_threshold': str(material.alert_threshold),
                'stockout_threshold': str(material.stockout_threshold),
            }
            
            AuditLog.log_action(
                user=request.user,
                action_type='update',
                module='catalog',
                instance=material,
                details={'before': old_values, 'after': new_values},
                request=request
            )
            
            messages.success(request, f"Matière première {material.reference} modifiée avec succès")
            return redirect('raw_material_detail', material_id=material.id)
    else:
        form = RawMaterialForm(instance=material)
    
    return render(request, 'catalog/raw_material_form.html', {
        'form': form,
        'material': material,
        'title': f'Modifier - {material.reference}'
    })

@login_required
def finished_products_list(request):
    """Finished products catalog list"""
    products = FinishedProduct.objects.select_related('sales_unit').all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        products = products.filter(
            Q(reference__icontains=search) | 
            Q(designation__icontains=search)
        )
    
    # Active filter
    if request.GET.get('active') == 'false':
        products = products.filter(is_active=False)
    elif request.GET.get('active') != 'all':
        products = products.filter(is_active=True)
    
    context = {
        'products': products,
        'title': 'Catalogue produits finis'
    }
    
    return render(request, 'catalog/finished_products_list.html', context)

@login_required
@role_required(['manager'])
def finished_product_create(request):
    """Create new finished product"""
    if request.method == 'POST':
        form = FinishedProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='catalog',
                instance=product,
                request=request
            )
            
            messages.success(request, f"Produit fini {product.reference} créé avec succès")
            return redirect('finished_products_list')
    else:
        form = FinishedProductForm()
    
    return render(request, 'catalog/finished_product_form.html', {
        'form': form,
        'title': 'Nouveau produit fini'
    })

@login_required
def finished_product_detail(request, product_id):
    """Finished product detail view"""
    product = get_object_or_404(FinishedProduct, id=product_id)
    
    # Get production history
    production_orders = []
    try:
        from production.models import ProductionOrder
        production_orders = ProductionOrder.objects.filter(
            formulation__finished_product=product
        ).order_by('-created_at')[:10]
    except:
        pass
    
    context = {
        'product': product,
        'production_orders': production_orders,
        'current_stock': product.get_current_stock(),
        'stock_status': product.get_stock_status(),
        'wac': product.get_weighted_average_cost(),
        'unit_margin': product.get_unit_gross_margin(),
        'margin_rate': product.get_margin_rate(),
        'title': f'Produit fini - {product.reference}'
    }
    
    return render(request, 'catalog/finished_product_detail.html', context)

@login_required
def check_stock_availability(request):
    """AJAX endpoint to check stock availability for production/sales"""
    if request.method == 'GET':
        material_id = request.GET.get('material_id')
        required_qty = request.GET.get('required_qty')
        
        if material_id and required_qty:
            try:
                material = RawMaterial.objects.get(id=material_id)
                required_qty = Decimal(required_qty)
                current_stock = material.get_current_stock()
                
                return JsonResponse({
                    'success': True,
                    'current_stock': str(current_stock),
                    'required_qty': str(required_qty),
                    'sufficient': current_stock >= required_qty,
                    'status': material.get_stock_status(),
                    'material': material.designation
                })
            except (RawMaterial.DoesNotExist, ValueError):
                pass
    
    return JsonResponse({'success': False, 'error': 'Paramètres invalides'})