# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, AuditLog


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profil utilisateur"


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "get_role",
        "is_active",
    )

    def get_role(self, obj):
        return (
            obj.userprofile.get_role_display() if hasattr(obj, "userprofile") else "-"
        )

    get_role.short_description = "Rôle"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    list_editable = ["role", "is_active"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action_type", "module", "entity_reference"]
    list_filter = ["action_type", "module", "timestamp"]
    search_fields = ["user__username", "entity_reference"]
    # FIX: removed 'content_type' and 'object_id' — AuditLog uses plain char fields
    # (entity_type, entity_id, entity_reference), not GenericForeignKey.
    readonly_fields = [
        "timestamp",
        "user",
        "action_type",
        "module",
        "entity_type",
        "entity_id",
        "entity_reference",
        "detail_json",
        "ip_address",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
