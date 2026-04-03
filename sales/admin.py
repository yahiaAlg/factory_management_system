# sales/admin.py
from django.contrib import admin
from .models import ClientDN, ClientDNLine, ClientInvoice, ClientInvoiceDNLink, ClientPayment

class ClientDNLineInline(admin.TabularInline):
    model = ClientDNLine
    extra = 1
    readonly_fields = ['line_amount']

@admin.register(ClientDN)
class ClientDNAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'client', 'delivery_date', 'status', 
        'total_ht', 'validated_by', 'created_at'
    ]
    list_filter = ['status', 'delivery_date', 'created_at']
    search_fields = ['reference', 'client__raison_sociale']
    readonly_fields = ['reference', 'total_ht', 'validated_by', 'validated_at', 'created_by', 'created_at']
    inlines = [ClientDNLineInline]
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('reference', 'client', 'delivery_date')
        }),
        ('Statut', {
            'fields': ('status', 'validated_by', 'validated_at')
        }),
        ('Montants', {
            'fields': ('total_ht', 'discount_pct')
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

@admin.register(ClientInvoice)
class ClientInvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'client', 'invoice_date', 'due_date', 'status',
        'total_ttc', 'balance_due', 'is_overdue'
    ]
    list_filter = ['status', 'invoice_date', 'due_date']
    search_fields = ['reference', 'client__raison_sociale']
    readonly_fields = [
        'reference', 'total_ht', 'net_ht', 'vat_amount', 'total_ttc',
        'amount_collected', 'balance_due', 'created_by', 'created_at'
    ]
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(ClientPayment)
class ClientPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'client', 'payment_date', 'amount', 
        'payment_method', 'recorded_by', 'created_at'
    ]
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['reference', 'client__raison_sociale', 'bank_reference']
    readonly_fields = ['reference', 'recorded_by', 'created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)