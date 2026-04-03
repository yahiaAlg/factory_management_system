# expenses/admin.py
from django.contrib import admin
from .models import Expense, SupportingDocument, ExpenseCategory

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'expense_date', 'category', 'description', 'amount',
        'status', 'beneficiary', 'validated_by', 'created_at'
    ]
    list_filter = ['category', 'status', 'expense_date', 'payment_method']
    search_fields = ['reference', 'description', 'beneficiary']
    readonly_fields = ['reference', 'validated_by', 'validated_at', 'created_by', 'created_at']
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('reference', 'expense_date', 'category', 'description', 'amount', 'beneficiary')
        }),
        ('Paiement', {
            'fields': ('payment_method', 'payment_date')
        }),
        ('Validation', {
            'fields': ('status', 'validated_by', 'validated_at', 'rejection_reason')
        }),
        ('Liens', {
            'fields': ('linked_supplier_invoice',)
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

@admin.register(SupportingDocument)
class SupportingDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'doc_type', 'entity_type', 'entity_id', 'description',
        'registered_by', 'registered_at'
    ]
    list_filter = ['doc_type', 'entity_type', 'registered_at']
    search_fields = ['description', 'file_reference']
    readonly_fields = ['registered_by', 'registered_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.registered_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'name', 'monthly_budget', 'annual_budget', 'is_active', 'created_at'
    ]
    list_filter = ['is_active']
    search_fields = ['code', 'name']
    list_editable = ['is_active']