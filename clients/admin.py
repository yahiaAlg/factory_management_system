# clients/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import Client
from .resources import ClientResource


@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin):
    resource_class = ClientResource

    list_display = (
        "code", "raison_sociale", "forme_juridique", "wilaya",
        "phone", "payment_terms", "credit_status_badge", "is_active",
    )
    list_filter = ("credit_status", "is_active", "wilaya")
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
            "fields": ("payment_terms", "credit_status", "max_discount_pct"),
        }),
        ("Notes", {
            "fields": ("notes",),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut crédit")
    def credit_status_badge(self, obj):
        colors = {
            "active": "#198754",
            "suspended": "#fd7e14",
            "blocked": "#dc3545",
        }
        color = colors.get(obj.credit_status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color,
            obj.get_credit_status_display(),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
