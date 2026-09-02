# suppliers/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import Supplier


class SupplierResource(resources.ModelResource):
    """
    Import/export for Supplier.

    Import notes:
      - 'code' is the natural key for matching existing records.
      - 'currency' must be one of: DZD / EUR / USD.
      - 'payment_terms' is an integer number of days (≥ 0).
      - 'created_by' matched by username.
    """

    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = Supplier
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
            "currency",
            "bank_name",
            "bank_account",
            "rib",
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
