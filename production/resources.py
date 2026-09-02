# production/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import Formulation, FormulationLine, ProductionOrder, ProductionOrderLine


class FormulationResource(resources.ModelResource):
    """
    Import/export for Formulation.

    Import notes:
      - 'reference' (F-NNN) is auto-generated; blank on INSERT, present on UPDATE.
      - Editing a formulation with in_progress production orders is blocked
        by the model's clean() — BR-PROD-03.
      - 'finished_product' matched by FinishedProduct reference.
      - 'reference_batch_unit' matched by UnitOfMeasure code.
      - 'is_active' / 'version' should be consistent with server state;
        use create_new_version() rather than directly bumping version.
    """

    finished_product = fields.Field(
        column_name="finished_product",
        attribute="finished_product",
        widget=ForeignKeyWidget("catalog.FinishedProduct", field="reference"),
    )
    reference_batch_unit = fields.Field(
        column_name="reference_batch_unit",
        attribute="reference_batch_unit",
        widget=ForeignKeyWidget("catalog.UnitOfMeasure", field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = Formulation
        import_id_fields = ("reference", "version")
        fields = (
            "id",
            "reference",
            "designation",
            "finished_product",
            "reference_batch_qty",
            "reference_batch_unit",
            "expected_yield_pct",
            "version",
            "is_active",
            "technical_notes",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_finished_product(self, obj):
        return obj.finished_product.reference

    def dehydrate_reference_batch_unit(self, obj):
        return obj.reference_batch_unit.code

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class FormulationLineResource(resources.ModelResource):
    """
    Import/export for FormulationLine.

    'formulation' matched by (reference, version) compound key expressed
    as 'formulation_reference' and 'formulation_version' columns.
    """

    formulation = fields.Field(
        column_name="formulation",
        attribute="formulation",
        widget=ForeignKeyWidget(Formulation, field="id"),
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
        model = FormulationLine
        import_id_fields = ("formulation", "raw_material")
        fields = (
            "id",
            "formulation",
            "raw_material",
            "qty_per_batch",
            "unit_of_measure",
            "tolerance_pct",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_formulation(self, obj):
        return obj.formulation.id

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference

    def dehydrate_unit_of_measure(self, obj):
        return obj.unit_of_measure.code


class ProductionOrderResource(resources.ModelResource):
    """
    Import/export for ProductionOrder.

    Import notes:
      - 'reference' (OP-YYYY-NNNN) is auto-generated; blank on INSERT.
      - 'qty_theoretical' on lines is editable=False (computed at PO
        creation from formulation scaling) — handled in ProductionOrderLineResource.
      - 'yield_rate' and 'yield_status' are @properties; excluded.
      - Status transitions should use the business-action methods
        (validate, launch, close, cancel) rather than raw import.
    """

    formulation = fields.Field(
        column_name="formulation",
        attribute="formulation",
        widget=ForeignKeyWidget(Formulation, field="id"),
    )
    site = fields.Field(
        column_name="site",
        attribute="site",
        widget=ForeignKeyWidget("core.ProductionSite", field="code"),
    )
    target_unit = fields.Field(
        column_name="target_unit",
        attribute="target_unit",
        widget=ForeignKeyWidget("catalog.UnitOfMeasure", field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )
    closed_by = fields.Field(
        column_name="closed_by",
        attribute="closed_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = ProductionOrder
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "site",
            "formulation",
            "formulation_version",
            "target_qty",
            "target_unit",
            "launch_date",
            "closure_date",
            "status",
            "actual_qty_produced",
            "stock_check_passed",
            "notes",
            "created_by",
            "created_at",
            "closed_by",
        )
        # yield_rate and yield_status are @property — excluded.
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_formulation(self, obj):
        return obj.formulation.id

    def dehydrate_target_unit(self, obj):
        return obj.target_unit.code

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def dehydrate_closed_by(self, obj):
        return obj.closed_by.username if obj.closed_by else ""

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""


class ProductionOrderLineResource(resources.ModelResource):
    """
    Import/export for ProductionOrderLine.

    Import notes:
      - 'qty_theoretical' is editable=False (computed from formulation at
        PO creation).  It is included in EXPORT for traceability/reporting
        but is excluded from import to prevent overwriting computed values.
      - 'delta_qty' and 'financial_impact' are @properties; excluded.
      - Only 'qty_actual' and 'tolerance_pct' should be updated via import.
    """

    production_order = fields.Field(
        column_name="production_order",
        attribute="production_order",
        widget=ForeignKeyWidget(ProductionOrder, field="reference"),
    )
    raw_material = fields.Field(
        column_name="raw_material",
        attribute="raw_material",
        widget=ForeignKeyWidget("catalog.RawMaterial", field="reference"),
    )

    class Meta:
        model = ProductionOrderLine
        import_id_fields = ("production_order", "raw_material")
        fields = (
            "id",
            "production_order",
            "raw_material",
            "qty_theoretical",  # export only — excluded on import below
            "qty_actual",
            "tolerance_pct",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    # qty_theoretical must never be overwritten via import.
    IMPORT_READONLY_FIELDS = ("qty_theoretical",)

    def dehydrate_production_order(self, obj):
        return obj.production_order.reference

    def dehydrate_raw_material(self, obj):
        return obj.raw_material.reference

    def before_import_row(self, row, row_number=None, **kwargs):
        """Drop qty_theoretical so the model's editable=False is respected."""
        row.pop("qty_theoretical", None)
