from django.contrib import admin
from .models import CompanyInformation, SystemParameter, DocumentSequence

@admin.register(CompanyInformation)
class CompanyInformationAdmin(admin.ModelAdmin):
    list_display = ['raison_sociale', 'nif', 'wilaya', 'created_at']
    fields = [
        'raison_sociale', 'forme_juridique', 'nif', 'nis', 'rc', 'ai',
        'address', 'wilaya', 'phone', 'email',
        'bank_name', 'bank_account', 'rib', 'logo',
        'vat_rate', 'fiscal_regime'
    ]
    
    def has_add_permission(self, request):
        # Only allow one company record
        return not CompanyInformation.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(SystemParameter)
class SystemParameterAdmin(admin.ModelAdmin):
    list_display = ['category', 'key', 'value', 'is_active', 'updated_at']
    list_filter = ['category', 'is_active']
    search_fields = ['key', 'description']
    list_editable = ['is_active']

@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ['prefix', 'current_year', 'current_number', 'description']
    list_filter = ['current_year']
    search_fields = ['prefix', 'description']
    readonly_fields = ['current_number']