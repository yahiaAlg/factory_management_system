from django.contrib import admin
from .models import Supplier

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'raison_sociale', 'currency', 'payment_terms', 
        'get_outstanding_balance', 'is_active', 'created_at'
    ]
    list_filter = ['currency', 'is_active', 'wilaya', 'created_at']
    search_fields = ['code', 'raison_sociale', 'nif', 'nis', 'rc']
    list_editable = ['is_active']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('code', 'raison_sociale', 'forme_juridique')
        }),
        ('Identifiants fiscaux', {
            'fields': ('nif', 'nis', 'rc', 'ai'),
            'classes': ('collapse',)
        }),
        ('Coordonnées', {
            'fields': ('address', 'wilaya', 'phone', 'fax', 'email')
        }),
        ('Contact', {
            'fields': ('contact_person', 'contact_phone')
        }),
        ('Conditions commerciales', {
            'fields': ('payment_terms', 'currency')
        }),
        ('Coordonnées bancaires', {
            'fields': ('bank_name', 'bank_account', 'rib'),
            'classes': ('collapse',)
        }),
        ('Statut et notes', {
            'fields': ('is_active', 'notes')
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_outstanding_balance(self, obj):
        balance = obj.get_outstanding_balance()
        return f"{balance:,.2f} {obj.currency}"
    get_outstanding_balance.short_description = 'Solde à payer'