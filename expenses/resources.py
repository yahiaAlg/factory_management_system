# expenses/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import ExpenseCategory, Expense, SupportingDocument


class ExpenseCategoryResource(resources.ModelResource):
    class Meta:
        model = ExpenseCategory
        import_id_fields = ("code",)
        fields = ("id", "code", "label", "is_active", "order")
        export_order = fields
        skip_unchanged = True
        report_skipped = False


class ExpenseResource(resources.ModelResource):
    """
    Import/export for Expense.

    Import notes:
      - 'reference' (DEP-YYYY-NNNN) is auto-generated; leave blank on INSERT,
        include on UPDATE to match existing records.
      - 'status' must be one of: recorded / validated / paid / rejected.
      - Signal-managed/validation-controlled fields (validated_by,
        validated_at, rejection_reason) are included for export/migration but
        should not be manipulated via import in normal operations — use the
        business-action methods (validate, reject, mark_as_paid) instead.
      - 'linked_supplier_invoice' matched by SupplierInvoice reference (nullable).
      - SupportingDocument attachments are not carried in this resource;
        manage them separately via SupportingDocumentResource.
    """

    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(ExpenseCategory, field="code"),
    )
    validated_by = fields.Field(
        column_name="validated_by",
        attribute="validated_by",
        widget=ForeignKeyWidget(User, field="username"),
    )
    linked_supplier_invoice = fields.Field(
        column_name="linked_supplier_invoice",
        attribute="linked_supplier_invoice",
        widget=ForeignKeyWidget("supplier_ops.SupplierInvoice", field="reference"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = Expense
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "expense_date",
            "category",
            "description",
            "amount",
            "beneficiary",
            "payment_method",
            "payment_date",
            "status",
            "validated_by",
            "validated_at",
            "rejection_reason",
            "linked_supplier_invoice",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_category(self, obj):
        return obj.category.code

    def dehydrate_validated_by(self, obj):
        return obj.validated_by.username if obj.validated_by else ""

    def dehydrate_linked_supplier_invoice(self, obj):
        return obj.linked_supplier_invoice.reference if obj.linked_supplier_invoice else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class SupportingDocumentResource(resources.ModelResource):
    """
    Import/export for SupportingDocument.

    The 'file' FileField is excluded — binary content cannot be
    safely round-tripped through CSV/XLSX.  Use 'file_reference' to
    record an external path or identifier instead.
    """

    registered_by = fields.Field(
        column_name="registered_by",
        attribute="registered_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = SupportingDocument
        exclude = ("file",)
        fields = (
            "id",
            "doc_type",
            "entity_type",
            "entity_id",
            "description",
            "file_reference",
            "registered_by",
            "registered_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_registered_by(self, obj):
        return obj.registered_by.username
