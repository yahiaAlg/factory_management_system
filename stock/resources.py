# stock/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import (
    RawMaterialStockBalance,
    FinishedProductStockBalance,
    StockMovement,
    StockAdjustment,
    StockAdjustmentLine,
)


class RawMaterialStockBalanceResource(resources.ModelResource):
    """
    Export-only resource for RawMaterialStockBalance.

    SPEC BR-RM-05: quantity must NEVER be set via a form or direct
    import. Write paths are exclusively stock signals triggered by
    supplier DN validation and production order closure.
    This resource is provided for reporting and migration snapshots only.
    """

    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )

    class Meta:
        model = RawMaterialStockBalance
        fields = (
            "id",
            "site",
            "raw_material",
            "quantity",
            "last_movement_date",
            "last_updated",
        )
        export_order = fields
        skip_unchanged = True

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference

    def import_data(self, *args, **kwargs):
        raise NotImplementedError(
            "RawMaterialStockBalance import is disabled — "
            "quantity is managed exclusively via stock signals (BR-RM-05)."
        )


class FinishedProductStockBalanceResource(resources.ModelResource):
    """
    Export-only resource for FinishedProductStockBalance.

    'weighted_average_cost' is signal-recomputed after every PO closure
    (spec S7) — never user-editable. Export only.
    """

    finished_product = fields.Field(
        column_name="finished_product",
        attribute="finished_product",
        widget=ForeignKeyWidget("catalog.FinishedProduct", field="reference"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )

    class Meta:
        model = FinishedProductStockBalance
        fields = (
            "id",
            "site",
            "finished_product",
            "quantity",
            "weighted_average_cost",
            "last_movement_date",
            "last_updated",
        )
        export_order = fields
        skip_unchanged = True

    def dehydrate_finished_product(self, obj):
        return obj.finished_product.reference

    def import_data(self, *args, **kwargs):
        raise NotImplementedError(
            "FinishedProductStockBalance import is disabled — "
            "managed exclusively via stock signals (spec S7)."
        )


class StockMovementResource(resources.ModelResource):
    """
    Export-only resource for StockMovement.

    StockMovements must only be created by the four authorised signal
    handlers (spec BR-RM-05); direct import is blocked.
    Exported for audit trail, reporting, and migration purposes.
    """

    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )
    finished_product = fields.Field(
        column_name="finished_product",
        attribute="finished_product",
        widget=ForeignKeyWidget("catalog.FinishedProduct", field="reference"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "site",
            "raw_material",
            "finished_product",
            "movement_type",
            "quantity",
            "unit_price",
            "unit_cost",
            "source_document_type",
            "source_document_id",
            "source_line_id",
            "movement_date",
            "remarks",
            "created_by",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference if obj.raw_material else ""

    def dehydrate_finished_product(self, obj):
        return obj.finished_product.reference if obj.finished_product else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def import_data(self, *args, **kwargs):
        raise NotImplementedError(
            "StockMovement import is disabled — "
            "records are created only by authorised signal handlers (BR-RM-05)."
        )


class StockAdjustmentResource(resources.ModelResource):
    """
    Import/export for StockAdjustment.

    Import notes:
      - 'reference' (ADJ-YYYY-NNNN) auto-generated; blank on INSERT.
      - Stock movements are created by approve(), not by import.
        Import 'approved_by' / 'approved_at' only for migration of already-
        approved records; do NOT re-trigger approval via import.
    """

    approved_by = fields.Field(
        column_name="approved_by",
        attribute="approved_by",
        widget=ForeignKeyWidget(User, field="username"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )

    class Meta:
        model = StockAdjustment
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "site",
            "adjustment_type",
            "adjustment_date",
            "reason",
            "approved_by",
            "approved_at",
            "created_by",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_approved_by(self, obj):
        return obj.approved_by.username if obj.approved_by else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class StockAdjustmentLineResource(resources.ModelResource):
    """
    Import/export for StockAdjustmentLine.
    'quantity_adjustment' is a @property (quantity_after - quantity_before) — excluded.
    """

    stock_adjustment = fields.Field(
        column_name="stock_adjustment",
        attribute="stock_adjustment",
        widget=ForeignKeyWidget(StockAdjustment, field="reference"),
    )
    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )
    finished_product = fields.Field(
        column_name="finished_product",
        attribute="finished_product",
        widget=ForeignKeyWidget("catalog.FinishedProduct", field="reference"),
    )

    class Meta:
        model = StockAdjustmentLine
        import_id_fields = ("stock_adjustment", "raw_material")
        fields = (
            "id",
            "stock_adjustment",
            "raw_material",
            "finished_product",
            "quantity_before",
            "quantity_after",
            "remarks",
        )
        # quantity_adjustment is @property — never imported/exported as a column.
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_stock_adjustment(self, obj):
        return obj.stock_adjustment.reference

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference if obj.raw_material else ""

    def dehydrate_finished_product(self, obj):
        return obj.finished_product.reference if obj.finished_product else ""
