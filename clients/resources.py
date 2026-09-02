# clients/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import Client


class ClientResource(resources.ModelResource):
    """
    Import/export for Client.

    Import notes:
      - 'code' is the natural key used to match existing records.
      - 'credit_status' must be one of: active / suspended / blocked.
      - 'max_discount_pct' must be 0.00–100.00.
      - 'payment_terms' is an integer number of days (≥ 0).
      - 'created_by' matched by username.
    """

    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = Client
        import_id_fields = ("code",)
        fields = (
            "id",
            "code",
            "raison_sociale",
            "forme_juridique",
            "nif",
            "nis",
            "rc",
            "ai",
            "address",
            "wilaya",
            "phone",
            "fax",
            "email",
            "contact_person",
            "contact_phone",
            "payment_terms",
            "credit_status",
            "max_discount_pct",
            "is_active",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_created_by(self, obj):
        return obj.created_by.username
