# accounts/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin, ExportActionMixin
from .models import UserProfile, AuditLog
from .resources import UserProfileResource, AuditLogResource


@admin.register(UserProfile)
class UserProfileAdmin(ImportExportModelAdmin):
    resource_class = UserProfileResource

    list_display = ("user", "role_badge", "is_active", "created_at", "updated_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("user__username",)

    fieldsets = (
        ("Utilisateur", {
            "fields": ("user", "role", "is_active"),
        }),
        ("Horodatage", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Rôle")
    def role_badge(self, obj):
        colors = {
            "manager": "#dc3545",
            "stock_prod": "#fd7e14",
            "accountant": "#0d6efd",
            "sales": "#198754",
            "viewer": "#6c757d",
        }
        color = colors.get(obj.role, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color,
            obj.get_role_display(),
        )


@admin.register(AuditLog)
class AuditLogAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_class = AuditLogResource

    list_display = (
        "timestamp", "user", "action_type_badge", "module",
        "entity_type", "entity_reference", "ip_address",
    )
    list_filter = ("action_type", "module", "timestamp")
    search_fields = ("user__username", "entity_type", "entity_reference", "ip_address")
    readonly_fields = (
        "timestamp", "user", "action_type", "module",
        "entity_type", "entity_id", "entity_reference",
        "detail_json", "ip_address",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    # Audit records are immutable — disable all write operations
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Action")
    def action_type_badge(self, obj):
        colors = {
            "create": "#198754",
            "update": "#0d6efd",
            "validate": "#fd7e14",
            "pay": "#6f42c1",
            "cancel": "#dc3545",
            "login": "#20c997",
            "failed_login": "#dc3545",
        }
        color = colors.get(obj.action_type, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color,
            obj.get_action_type_display(),
        )
