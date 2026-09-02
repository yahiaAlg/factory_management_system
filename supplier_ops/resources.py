# supplier_ops/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import (
    SupplierDN,
    SupplierDNLine,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierInvoiceDNLink,
    SupplierPayment,
    SupplierAccountPayment,
)


class SupplierDNResource(resources.ModelResource):
    """
    Import/export for SupplierDN (Bon de Livraison Fournisseur).

    Import notes:
      - 'reference' (BL-F-YYYY-NNNN) auto-generated; blank on INSERT.
      - 'total_amount_ht' is editable=False (recomputed from lines in save());
        stripped on import via before_import_row().
      - Stock movements are created by signals on validation, not by import.
      - 'linked_invoice' matched by SupplierInvoice reference (nullable).
    """

    supplier = fields.Field(
        column_name="supplier",
        attribute="supplier",
        widget=ForeignKeyWidget("suppliers.Supplier", field="code"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )
    validated_by = fields.Field(
        column_name="validated_by",
        attribute="validated_by",
        widget=ForeignKeyWidget(User, field="username"),
    )
    linked_invoice = fields.Field(
        column_name="linked_invoice",
        attribute="linked_invoice",
        widget=ForeignKeyWidget(SupplierInvoice, field="reference"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = SupplierDN
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "site",
            "external_reference",
            "supplier",
            "delivery_date",
            "status",
            "total_amount_ht",
            "remarks",
            "validated_by",
            "validated_at",
            "linked_invoice",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier(self, obj):
        return obj.supplier.code

    def dehydrate_validated_by(self, obj):
        return obj.validated_by.username if obj.validated_by else ""

    def dehydrate_linked_invoice(self, obj):
        return obj.linked_invoice.reference if obj.linked_invoice else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        row.pop("total_amount_ht", None)
        if not row.get("reference"):
            row["reference"] = ""


class SupplierDNLineResource(resources.ModelResource):
    """
    Import/export for SupplierDNLine.
    'line_amount' is a @property — excluded from import/export columns.
    """

    supplier_dn = fields.Field(
        column_name="supplier_dn",
        attribute="supplier_dn",
        widget=ForeignKeyWidget(SupplierDN, field="reference"),
    )
    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )
    unit_of_measure = fields.Field(
        column_name="unit_of_measure",
        attribute="unit_of_measure",
        widget=ForeignKeyWidget("catalog.UnitOfMeasure", field="code"),
    )

    class Meta:
        model = SupplierDNLine
        import_id_fields = ("supplier_dn", "raw_material")
        fields = (
            "id",
            "supplier_dn",
            "raw_material",
            "quantity_received",
            "unit_of_measure",
            "agreed_unit_price",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier_dn(self, obj):
        return obj.supplier_dn.reference

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference

    def dehydrate_unit_of_measure(self, obj):
        return obj.unit_of_measure.code


class SupplierInvoiceResource(resources.ModelResource):
    """
    Import/export for SupplierInvoice.

    Import notes:
      - 'reference' (FF-YYYY-NNNN) auto-generated; blank on INSERT.
      - 'total_ht', 'vat_amount', 'total_ttc', 'balance_due' are editable=False
        (computed by save()/_recompute_totals() and signal); stripped on import.
      - BR-INV-08 unique constraint (supplier, external_reference) is enforced
        by the model's clean() during import validation.
      - 'linked_dns' M2M managed via SupplierInvoiceDNLinkResource.
    """

    supplier = fields.Field(
        column_name="supplier",
        attribute="supplier",
        widget=ForeignKeyWidget("suppliers.Supplier", field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = SupplierInvoice
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "external_reference",
            "supplier",
            "invoice_date",
            "due_date",
            "status",
            "total_ht",
            "vat_amount",
            "total_ttc",
            "balance_due",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier(self, obj):
        return obj.supplier.code

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        for computed in ("total_ht", "vat_amount", "total_ttc", "balance_due"):
            row.pop(computed, None)
        if not row.get("reference"):
            row["reference"] = ""


class SupplierInvoiceLineResource(resources.ModelResource):
    """
    Import/export for SupplierInvoiceLine.
    'line_amount' is a @property — excluded from columns.
    """

    supplier_invoice = fields.Field(
        column_name="supplier_invoice",
        attribute="supplier_invoice",
        widget=ForeignKeyWidget(SupplierInvoice, field="reference"),
    )
    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )

    class Meta:
        model = SupplierInvoiceLine
        import_id_fields = ("supplier_invoice", "raw_material")
        fields = (
            "id",
            "supplier_invoice",
            "raw_material",
            "designation",
            "quantity_invoiced",
            "unit_price_invoiced",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier_invoice(self, obj):
        return obj.supplier_invoice.reference

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference


class SupplierInvoiceDNLinkResource(resources.ModelResource):
    """Through-table linking SupplierInvoice ↔ SupplierDN."""

    supplier_invoice = fields.Field(
        column_name="supplier_invoice",
        attribute="supplier_invoice",
        widget=ForeignKeyWidget(SupplierInvoice, field="reference"),
    )
    supplier_dn = fields.Field(
        column_name="supplier_dn",
        attribute="supplier_dn",
        widget=ForeignKeyWidget(SupplierDN, field="reference"),
    )

    class Meta:
        model = SupplierInvoiceDNLink
        import_id_fields = ("supplier_invoice", "supplier_dn")
        fields = ("id", "supplier_invoice", "supplier_dn", "created_at")
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier_invoice(self, obj):
        return obj.supplier_invoice.reference

    def dehydrate_supplier_dn(self, obj):
        return obj.supplier_dn.reference


class SupplierPaymentResource(resources.ModelResource):
    """
    Import/export for SupplierPayment.

    Import notes:
      - 'reference' (PAY-F-YYYY-NNNN) auto-generated; blank on INSERT.
      - BR-INV-04 (blocked if invoice in_dispute) is enforced by clean()
        which runs via full_clean() in save() — will surface as a
        validation error during import if violated.
    """

    supplier_invoice = fields.Field(
        column_name="supplier_invoice",
        attribute="supplier_invoice",
        widget=ForeignKeyWidget(SupplierInvoice, field="reference"),
    )
    supplier = fields.Field(
        column_name="supplier",
        attribute="supplier",
        widget=ForeignKeyWidget("suppliers.Supplier", field="code"),
    )
    recorded_by = fields.Field(
        column_name="recorded_by",
        attribute="recorded_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = SupplierPayment
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "supplier_invoice",
            "supplier",
            "payment_date",
            "amount",
            "payment_method",
            "bank_reference",
            "recorded_by",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier_invoice(self, obj):
        return obj.supplier_invoice.reference

    def dehydrate_supplier(self, obj):
        return obj.supplier.code

    def dehydrate_recorded_by(self, obj):
        return obj.recorded_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class SupplierAccountPaymentResource(resources.ModelResource):
    """
    Import/export for SupplierAccountPayment (FIFO account-level settlement).
    'reference' (RGL-F-YYYY-NNNN) auto-generated; blank on INSERT.
    """

    supplier = fields.Field(
        column_name="supplier",
        attribute="supplier",
        widget=ForeignKeyWidget("suppliers.Supplier", field="code"),
    )
    recorded_by = fields.Field(
        column_name="recorded_by",
        attribute="recorded_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = SupplierAccountPayment
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "supplier",
            "payment_date",
            "amount",
            "payment_method",
            "bank_reference",
            "notes",
            "recorded_by",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_supplier(self, obj):
        return obj.supplier.code

    def dehydrate_recorded_by(self, obj):
        return obj.recorded_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""
