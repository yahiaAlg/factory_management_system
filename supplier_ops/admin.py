from django.contrib import admin
from .models import (
    SupplierDN, SupplierDNLine, SupplierInvoice, SupplierInvoiceLine,
    SupplierInvoiceDNLink, ReconciliationLine, SupplierPayment
)

class SupplierDNLineInline(admin.TabularInline):
    model = SupplierDNLine
    extra = 1
    readonly_fields = ['line_amount']

@admin.register(SupplierDN)
class SupplierDNAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'supplier', 'delivery_date', 'status', 
        'total_amount_ht', 'validated_by', 'created_at'
    ]
    list_filter = ['status', 'delivery_date', 'created_at']
    search_fields = ['reference', 'external_reference', 'supplier__raison_sociale']
    readonly_fields = ['reference', 'total_amount_ht', 'validated_by', 'validated_at', 'created_by', 'created_at']
    inlines = [SupplierDNLineInline]
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('reference', 'external_reference', 'supplier', 'delivery_date')
        }),
        ('Statut', {
            'fields': ('status', 'validated_by', 'validated_at')
        }),
        ('Montants', {
            'fields': ('total_amount_ht',)
        }),
        ('Observations', {
            'fields': ('remarks',)
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

class SupplierInvoiceLineInline(admin.TabularInline):
    model = SupplierInvoiceLine
    extra = 1
    readonly_fields = ['line_amount']

class ReconciliationLineInline(admin.TabularInline):
    model = ReconciliationLine
    extra = 0
    readonly_fields = ['delta_qty', 'delta_price', 'delta_amount']

@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'supplier', 'invoice_date', 'due_date', 'status',
        'total_ttc', 'balance_due', 'reconciliation_result'
    ]
    list_filter = ['status', 'reconciliation_result', 'invoice_date', 'due_date']
    search_fields = ['reference', 'external_reference', 'supplier__raison_sociale']
    readonly_fields = [
        'reference', 'total_ht', 'vat_amount', 'total_ttc', 'balance_due',
        'reconciliation_delta', 'created_by', 'created_at'
    ]
    inlines = [SupplierInvoiceLineInline, ReconciliationLineInline]
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'supplier', 'payment_date', 'amount', 
        'payment_method', 'recorded_by', 'created_at'
    ]
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['reference', 'supplier__raison_sociale', 'bank_reference']
    readonly_fields = ['reference', 'recorded_by', 'created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)