# sales/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import (
    ClientDN,
    ClientDNLine,
    ClientInvoice,
    ClientInvoiceDNLink,
    ClientPayment,
    ClientAccountPayment,
)


class ClientDNResource(resources.ModelResource):
    """
    Import/export for ClientDN (Bon de Livraison Client).

    Import notes:
      - 'reference' (BL-C-YYYY-NNNN) is auto-generated; blank on INSERT.
      - 'total_ht' is editable=False (recomputed in save() from lines).
        Included in export, stripped on import via before_import_row().
      - 'status' transitions must use validate() in normal operations.
      - 'linked_invoice' matched by ClientInvoice reference (nullable).
    """

    client = fields.Field(
        column_name="client",
        attribute="client",
        widget=ForeignKeyWidget("clients.Client", field="code"),
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
        widget=ForeignKeyWidget(ClientInvoice, field="reference"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = ClientDN
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "site",
            "client",
            "delivery_date",
            "status",
            "total_ht",
            "discount_pct",
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

    def dehydrate_client(self, obj):
        return obj.client.code

    def dehydrate_validated_by(self, obj):
        return obj.validated_by.username if obj.validated_by else ""

    def dehydrate_linked_invoice(self, obj):
        return obj.linked_invoice.reference if obj.linked_invoice else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        row.pop("total_ht", None)
        if not row.get("reference"):
            row["reference"] = ""


class ClientDNLineResource(resources.ModelResource):
    """
    Import/export for ClientDNLine.
    'line_amount' is a @property — exported for reporting, stripped on import.
    """

    client_dn = fields.Field(
        column_name="client_dn",
        attribute="client_dn",
        widget=ForeignKeyWidget(ClientDN, field="reference"),
    )
    finished_product = fields.Field(
        column_name="finished_product",
        attribute="finished_product",
        widget=ForeignKeyWidget("catalog.FinishedProduct", field="reference"),
    )
    unit_of_measure = fields.Field(
        column_name="unit_of_measure",
        attribute="unit_of_measure",
        widget=ForeignKeyWidget("catalog.UnitOfMeasure", field="code"),
    )

    class Meta:
        model = ClientDNLine
        import_id_fields = ("client_dn", "finished_product")
        fields = (
            "id",
            "client_dn",
            "finished_product",
            "quantity_delivered",
            "unit_of_measure",
            "selling_unit_price_ht",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_client_dn(self, obj):
        return obj.client_dn.reference

    def dehydrate_finished_product(self, obj):
        return obj.finished_product.reference

    def dehydrate_unit_of_measure(self, obj):
        return obj.unit_of_measure.code


class ClientInvoiceResource(resources.ModelResource):
    """
    Import/export for ClientInvoice.

    Import notes:
      - 'reference' (FC-YYYY-NNNN) auto-generated; blank on INSERT.
      - 'total_ht', 'vat_amount', 'total_ttc', 'balance_due' are
        editable=False (signal/save-managed); stripped on import.
      - 'net_ht' is a @property; excluded entirely.
      - 'linked_dns' M2M managed via ClientInvoiceDNLinkResource.
    """

    client = fields.Field(
        column_name="client",
        attribute="client",
        widget=ForeignKeyWidget("clients.Client", field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = ClientInvoice
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "client",
            "invoice_date",
            "due_date",
            "status",
            "total_ht",
            "discount_pct",
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

    def dehydrate_client(self, obj):
        return obj.client.code

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        for computed in ("total_ht", "vat_amount", "total_ttc", "balance_due"):
            row.pop(computed, None)
        if not row.get("reference"):
            row["reference"] = ""


class ClientInvoiceDNLinkResource(resources.ModelResource):
    """Through-table linking ClientInvoice ↔ ClientDN."""

    client_invoice = fields.Field(
        column_name="client_invoice",
        attribute="client_invoice",
        widget=ForeignKeyWidget(ClientInvoice, field="reference"),
    )
    client_dn = fields.Field(
        column_name="client_dn",
        attribute="client_dn",
        widget=ForeignKeyWidget(ClientDN, field="reference"),
    )

    class Meta:
        model = ClientInvoiceDNLink
        import_id_fields = ("client_invoice", "client_dn")
        fields = ("id", "client_invoice", "client_dn", "created_at")
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_client_invoice(self, obj):
        return obj.client_invoice.reference

    def dehydrate_client_dn(self, obj):
        return obj.client_dn.reference


class ClientPaymentResource(resources.ModelResource):
    """
    Import/export for ClientPayment.
    'reference' (PAY-C-YYYY-NNNN) auto-generated; blank on INSERT.
    """

    client_invoice = fields.Field(
        column_name="client_invoice",
        attribute="client_invoice",
        widget=ForeignKeyWidget(ClientInvoice, field="reference"),
    )
    client = fields.Field(
        column_name="client",
        attribute="client",
        widget=ForeignKeyWidget("clients.Client", field="code"),
    )
    recorded_by = fields.Field(
        column_name="recorded_by",
        attribute="recorded_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = ClientPayment
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "client_invoice",
            "client",
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

    def dehydrate_client_invoice(self, obj):
        return obj.client_invoice.reference

    def dehydrate_client(self, obj):
        return obj.client.code

    def dehydrate_recorded_by(self, obj):
        return obj.recorded_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class ClientAccountPaymentResource(resources.ModelResource):
    """
    Import/export for ClientAccountPayment (FIFO account-level settlement).
    'reference' (RGL-C-YYYY-NNNN) auto-generated; blank on INSERT.
    """

    client = fields.Field(
        column_name="client",
        attribute="client",
        widget=ForeignKeyWidget("clients.Client", field="code"),
    )
    recorded_by = fields.Field(
        column_name="recorded_by",
        attribute="recorded_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = ClientAccountPayment
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "client",
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

    def dehydrate_client(self, obj):
        return obj.client.code

    def dehydrate_recorded_by(self, obj):
        return obj.recorded_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""
