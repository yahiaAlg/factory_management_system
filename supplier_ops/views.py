# supplier_ops/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.utils import timezone
from accounts.utils import role_required
from accounts.models import AuditLog
from .models import (
    SupplierDN, SupplierDNLine, SupplierInvoice, SupplierInvoiceLine,
    SupplierPayment, ReconciliationLine
)
from .forms import (
    SupplierDNForm, SupplierDNLineFormSet, SupplierInvoiceForm,
    SupplierInvoiceLineFormSet, SupplierPaymentForm
)

@login_required
def supplier_dns_list(request):
    """Supplier delivery notes list"""
    dns = SupplierDN.objects.select_related('supplier', 'validated_by').all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        dns = dns.filter(
            Q(reference__icontains=search) | 
            Q(external_reference__icontains=search) |
            Q(supplier__raison_sociale__icontains=search)
        )
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        dns = dns.filter(status=status_filter)
    
    # Supplier filter
    supplier_filter = request.GET.get('supplier')
    if supplier_filter:
        dns = dns.filter(supplier_id=supplier_filter)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        dns = dns.filter(delivery_date__gte=date_from)
    if date_to:
        dns = dns.filter(delivery_date__lte=date_to)
    
    context = {
        'dns': dns.order_by('-delivery_date'),
        'status_choices': SupplierDN.STATUS_CHOICES,
        'title': 'Bons de livraison fournisseurs'
    }
    
    return render(request, 'supplier_ops/supplier_dns_list.html', context)

@login_required
@role_required(['manager', 'stock_prod'])
def supplier_dn_create(request):
    """Create new supplier delivery note"""
    if request.method == 'POST':
        form = SupplierDNForm(request.POST)
        formset = SupplierDNLineFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            
            formset.instance = dn
            formset.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='supplier_ops',
                instance=dn,
                request=request
            )
            
            messages.success(request, f"BL Fournisseur {dn.reference} créé avec succès")
            return redirect('supplier_dn_detail', dn_id=dn.id)
    else:
        form = SupplierDNForm()
        formset = SupplierDNLineFormSet()
    
    return render(request, 'supplier_ops/supplier_dn_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nouveau BL Fournisseur'
    })

@login_required
def supplier_dn_detail(request, dn_id):
    """Supplier delivery note detail view"""
    dn = get_object_or_404(SupplierDN, id=dn_id)
    
    context = {
        'dn': dn,
        'lines': dn.lines.select_related('raw_material', 'unit_of_measure').all(),
        'can_validate': (
            request.user.userprofile.role in ['manager', 'stock_prod'] and 
            dn.status == 'pending'
        ),
        'title': f'BL Fournisseur - {dn.reference}'
    }
    
    return render(request, 'supplier_ops/supplier_dn_detail.html', context)

@login_required
@role_required(['manager', 'stock_prod'])
def supplier_dn_validate(request, dn_id):
    """Validate supplier delivery note"""
    dn = get_object_or_404(SupplierDN, id=dn_id)
    
    if request.method == 'POST':
        if dn.status != 'pending':
            messages.error(request, "Ce BL ne peut pas être validé")
            return redirect('supplier_dn_detail', dn_id=dn.id)
        
        try:
            dn.validate(request.user)
            
            AuditLog.log_action(
                user=request.user,
                action_type='validate',
                module='supplier_ops',
                instance=dn,
                request=request
            )
            
            messages.success(request, f"BL {dn.reference} validé avec succès")
        except ValueError as e:
            messages.error(request, str(e))
        
        return redirect('supplier_dn_detail', dn_id=dn.id)
    
    return redirect('supplier_dn_detail', dn_id=dn.id)

@login_required
def supplier_invoices_list(request):
    """Supplier invoices list"""
    invoices = SupplierInvoice.objects.select_related('supplier').all()
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        invoices = invoices.filter(
            Q(reference__icontains=search) | 
            Q(external_reference__icontains=search) |
            Q(supplier__raison_sociale__icontains=search)
        )
    
    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    
    # Reconciliation filter
    reconciliation_filter = request.GET.get('reconciliation')
    if reconciliation_filter:
        invoices = invoices.filter(reconciliation_result=reconciliation_filter)
    
    # Overdue filter
    if request.GET.get('overdue') == 'true':
        invoices = invoices.filter(
            due_date__lt=timezone.now().date(),
            balance_due__gt=0
        )
    
    context = {
        'invoices': invoices.order_by('-invoice_date'),
        'status_choices': SupplierInvoice.STATUS_CHOICES,
        'reconciliation_choices': SupplierInvoice.RECONCILIATION_CHOICES,
        'title': 'Factures fournisseurs'
    }
    
    return render(request, 'supplier_ops/supplier_invoices_list.html', context)

@login_required
@role_required(['manager', 'accountant'])
def supplier_invoice_create(request):
    """Create new supplier invoice"""
    if request.method == 'POST':
        form = SupplierInvoiceForm(request.POST)
        formset = SupplierInvoiceLineFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.created_by = request.user
            invoice.save()
            
            formset.instance = invoice
            formset.save()
            
            # Link to delivery notes if specified
            linked_dn_ids = request.POST.getlist('linked_dns')
            if linked_dn_ids:
                for dn_id in linked_dn_ids:
                    try:
                        dn = SupplierDN.objects.get(id=dn_id, status='validated')
                        invoice.linked_dns.add(dn)
                    except SupplierDN.DoesNotExist:
                        pass
                
                # Perform reconciliation
                invoice.perform_reconciliation()
            
            AuditLog.log_action(
                user=request.user,
                action_type='create',
                module='supplier_ops',
                instance=invoice,
                request=request
            )
            
            messages.success(request, f"Facture {invoice.reference} créée avec succès")
            return redirect('supplier_invoice_detail', invoice_id=invoice.id)
    else:
        form = SupplierInvoiceForm()
        formset = SupplierInvoiceLineFormSet()
    
    return render(request, 'supplier_ops/supplier_invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nouvelle facture fournisseur'
    })

@login_required
def supplier_invoice_detail(request, invoice_id):
    """Supplier invoice detail view"""
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    
    context = {
        'invoice': invoice,
        'lines': invoice.lines.select_related('raw_material').all(),
        'reconciliation_lines': invoice.reconciliation_lines.select_related('raw_material').all(),
        'payments': invoice.payments.all(),
        'linked_dns': invoice.linked_dns.all(),
        'can_pay': (
            request.user.userprofile.role in ['manager', 'accountant'] and 
            invoice.status in ['verified', 'unpaid', 'partially_paid'] and
            invoice.balance_due > 0
        ),
        'title': f'Facture Fournisseur - {invoice.reference}'
    }
    
    return render(request, 'supplier_ops/supplier_invoice_detail.html', context)

@login_required
@role_required(['manager', 'accountant'])
def supplier_payment_create(request, invoice_id):
    """Create payment for supplier invoice"""
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    
    if invoice.balance_due <= 0:
        messages.error(request, "Cette facture est déjà entièrement payée")
        return redirect('supplier_invoice_detail', invoice_id=invoice.id)
    
    if request.method == 'POST':
        form = SupplierPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.supplier_invoice = invoice
            payment.supplier = invoice.supplier
            payment.recorded_by = request.user
            
            # Validate payment amount
            if payment.amount > invoice.balance_due:
                messages.error(request, "Le montant du paiement ne peut pas dépasser le solde dû")
                return render(request, 'supplier_ops/supplier_payment_form.html', {
                    'form': form,
                    'invoice': invoice,
                    'title': f'Paiement - {invoice.reference}'
                })
            
            payment.save()
            
            AuditLog.log_action(
                user=request.user,
                action_type='pay',
                module='supplier_ops',
                instance=payment,
                details={'invoice': invoice.reference, 'amount': str(payment.amount)},
                request=request
            )
            
            messages.success(request, f"Paiement {payment.reference} enregistré avec succès")
            return redirect('supplier_invoice_detail', invoice_id=invoice.id)
    else:
        form = SupplierPaymentForm(initial={'amount': invoice.balance_due})
    
    return render(request, 'supplier_ops/supplier_payment_form.html', {
        'form': form,
        'invoice': invoice,
        'title': f'Paiement - {invoice.reference}'
    })

@login_required
def reconciliation_ajax(request, invoice_id):
    """AJAX endpoint for real-time reconciliation calculation"""
    if request.method == 'POST':
        try:
            invoice = SupplierInvoice.objects.get(id=invoice_id)
            
            # Get form data
            lines_data = []
            for key, value in request.POST.items():
                if key.startswith('lines-') and key.endswith('-quantity_invoiced'):
                    line_index = key.split('-')[1]
                    material_id = request.POST.get(f'lines-{line_index}-raw_material')
                    quantity = float(value) if value else 0
                    price = float(request.POST.get(f'lines-{line_index}-unit_price_invoiced', 0))
                    
                    if material_id and quantity > 0:
                        lines_data.append({
                            'material_id': int(material_id),
                            'quantity': quantity,
                            'price': price
                        })
            
            # Calculate reconciliation
            total_delta = 0
            reconciliation_data = []
            
            # Get DN data for comparison
            dn_data = {}
            for dn in invoice.linked_dns.all():
                for dn_line in dn.lines.all():
                    material_id = dn_line.raw_material_id
                    if material_id in dn_data:
                        dn_data[material_id]['quantity'] += float(dn_line.quantity_received)
                    else:
                        dn_data[material_id] = {
                            'quantity': float(dn_line.quantity_received),
                            'price': float(dn_line.agreed_unit_price)
                        }
            
            # Compare invoice lines with DN data
            for line_data in lines_data:
                material_id = line_data['material_id']
                qty_invoiced = line_data['quantity']
                price_invoiced = line_data['price']
                
                dn_info = dn_data.get(material_id, {'quantity': 0, 'price': 0})
                qty_delivered = dn_info['quantity']
                price_agreed = dn_info['price']
                
                delta_qty = qty_invoiced - qty_delivered
                delta_price = price_invoiced - price_agreed
                delta_amount = (qty_invoiced * price_invoiced) - (qty_delivered * price_agreed)
                
                total_delta += delta_amount
                
                reconciliation_data.append({
                    'material_id': material_id,
                    'qty_delivered': qty_delivered,
                    'qty_invoiced': qty_invoiced,
                    'delta_qty': delta_qty,
                    'price_agreed': price_agreed,
                    'price_invoiced': price_invoiced,
                    'delta_price': delta_price,
                    'delta_amount': delta_amount
                })
            
            # Determine reconciliation status
            from core.models import SystemParameter
            tolerance_threshold = float(SystemParameter.get_decimal_value('reconciliation_tolerance_threshold', 500))
            dispute_threshold = float(SystemParameter.get_decimal_value('reconciliation_dispute_threshold', 5000))
            
            abs_delta = abs(total_delta)
            if abs_delta <= tolerance_threshold:
                status = 'compliant'
                status_label = 'Conforme'
                status_class = 'success'
            elif abs_delta <= dispute_threshold:
                status = 'minor_discrepancy'
                status_label = 'Écart mineur'
                status_class = 'warning'
            else:
                status = 'dispute'
                status_label = 'Litige'
                status_class = 'danger'
            
            return JsonResponse({
                'success': True,
                'total_delta': total_delta,
                'reconciliation_status': status,
                'status_label': status_label,
                'status_class': status_class,
                'reconciliation_lines': reconciliation_data
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

@login_required
def supplier_dn_print(request, dn_id):
    """Print view for supplier delivery note"""
    dn = get_object_or_404(SupplierDN, id=dn_id)
    
    context = {
        'dn': dn,
        'lines': dn.lines.select_related('raw_material', 'unit_of_measure').all(),
    }
    
    return render(request, 'supplier_ops/supplier_dn_print.html', context)

@login_required
def supplier_invoice_print(request, invoice_id):
    """Print view for supplier invoice"""
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id)
    
    context = {
        'invoice': invoice,
        'lines': invoice.lines.select_related('raw_material').all(),
        'reconciliation_lines': invoice.reconciliation_lines.select_related('raw_material').all(),
    }
    
    return render(request, 'supplier_ops/supplier_invoice_print.html', context)