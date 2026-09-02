# suppliers/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import Supplier
from .resources import SupplierResource


@admin.register(Supplier)
class SupplierAdmin(ImportExportModelAdmin):
    resource_class = SupplierResource

    list_display = (
        "code", "raison_sociale", "forme_juridique", "wilaya",
        "phone", "payment_terms", "currency", "is_active",
    )
    list_filter = ("currency", "is_active", "wilaya")
    search_fields = ("code", "raison_sociale", "nif", "nis", "rc", "email")
    readonly_fields = ("created_by", "created_at", "updated_at")
    ordering = ("raison_sociale",)

    fieldsets = (
        ("Identification", {
            "fields": ("code", "raison_sociale", "forme_juridique", "is_active"),
        }),
        ("Identifiants fiscaux", {
            "fields": ("nif", "nis", "rc", "ai"),
        }),
        ("Coordonnées", {
            "fields": ("address", "wilaya", "phone", "fax", "email"),
        }),
        ("Contact", {
            "fields": ("contact_person", "contact_phone"),
        }),
        ("Conditions commerciales", {
            "fields": ("payment_terms", "currency"),
        }),
        ("Banque", {
            "fields": ("bank_name", "bank_account", "rib"),
        }),
        ("Notes", {
            "fields": ("notes",),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
