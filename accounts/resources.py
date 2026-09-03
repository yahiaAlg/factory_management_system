# accounts/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, BooleanWidget
from django.contrib.auth.models import User
from .models import UserProfile, AuditLog


class UserProfileResource(resources.ModelResource):
    """
    Import/export for UserProfile.

    Import notes:
      - 'user' is matched by username via ForeignKeyWidget.
      - 'role' must be one of the defined ROLES choices.
      - 'site' is matched by ProductionSite.code — required for
        stock_prod/sales, optional for accountant/viewer, must stay blank
        for manager/qa_manager/qc_technician (functional spec §25.2).
      - Importing triggers User.post_save signal which auto-creates a profile,
        so prefer updating existing profiles rather than bulk-creating.
    """

    user = fields.Field(
        column_name="user",
        attribute="user",
        widget=ForeignKeyWidget(User, field="username"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )

    class Meta:
        model = UserProfile
        import_id_fields = ("user",)
        fields = (
            "id",
            "user",
            "role",
            "site",
            "is_active",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_user(self, obj):
        return obj.user.username

    def dehydrate_role(self, obj):
        return obj.get_role_display()

    def dehydrate_site(self, obj):
        return obj.site.code if obj.site else ""


class AuditLogResource(resources.ModelResource):
    """
    Export-only resource for AuditLog.

    AuditLog records are written exclusively by the system (AuditLog.log_action).
    Import is intentionally disabled — use this resource for reporting/archiving only.
    """

    user = fields.Field(
        column_name="user",
        attribute="user",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "timestamp",
            "user",
            "action_type",
            "module",
            "entity_type",
            "entity_id",
            "entity_reference",
            "detail_json",
            "ip_address",
        )
        export_order = fields
        # No import — audit records must never be injected externally.
        skip_unchanged = True

    def dehydrate_user(self, obj):
        return obj.user.username

    def import_data(self, *args, **kwargs):
        raise NotImplementedError(
            "AuditLog import is disabled — records are system-generated only."
        )
