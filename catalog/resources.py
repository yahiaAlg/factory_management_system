# catalog/resources.py
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from django.contrib.auth.models import User
from .models import RawMaterialCategory, UnitOfMeasure, RawMaterial, FinishedProduct


class RawMaterialCategoryResource(resources.ModelResource):
    class Meta:
        model = RawMaterialCategory
        import_id_fields = ("name",)
        fields = ("id", "name", "description", "is_active", "created_at")
        export_order = fields
        skip_unchanged = True
        report_skipped = False


class UnitOfMeasureResource(resources.ModelResource):
    class Meta:
        model = UnitOfMeasure
        import_id_fields = ("code",)
        fields = ("id", "code", "name", "symbol", "is_active")
        export_order = fields
        skip_unchanged = True
        report_skipped = False


class RawMaterialResource(resources.ModelResource):
    """
    Import/export for RawMaterial.

    Import notes:
      - 'reference' (RM-NNN) is auto-generated on creation and immutable
        afterwards.  On import it is treated as the natural key for
        UPDATE operations; leave it blank on INSERT rows and the model
        will generate it.  The column is included in the export so that
        re-imports can match existing rows.
      - 'category' matched by category name.
      - 'unit_of_measure' matched by UnitOfMeasure code.
      - 'default_supplier' matched by Supplier code (nullable).
      - 'created_by' matched by username.
      - alert_threshold must be strictly > stockout_threshold (enforced by
        RawMaterial.clean()).
      - unit_of_measure is immutable once any DN/formulation line references
        this material; the model's clean() will raise ValidationError if
        violated during import.
    """

    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(RawMaterialCategory, field="name"),
    )
    unit_of_measure = fields.Field(
        column_name="unit_of_measure",
        attribute="unit_of_measure",
        widget=ForeignKeyWidget(UnitOfMeasure, field="code"),
    )
    default_supplier = fields.Field(
        column_name="default_supplier",
        attribute="default_supplier",
        # Avoid circular import — supplier resolved by code at runtime
        widget=ForeignKeyWidget("suppliers.Supplier", field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = RawMaterial
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "designation",
            "category",
            "unit_of_measure",
            "default_supplier",
            "reference_price",
            "alert_threshold",
            "stockout_threshold",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_default_supplier(self, obj):
        return obj.default_supplier.code if obj.default_supplier else ""

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        """Strip reference on new rows so the model generates it correctly."""
        if not row.get("reference"):
            row["reference"] = ""


class FinishedProductResource(resources.ModelResource):
    """
    Import/export for FinishedProduct.

    Import notes:
      - 'reference' (PF-NNN) is auto-generated on creation and immutable.
        Same convention as RawMaterialResource: include on UPDATE rows,
        leave blank on INSERT.
      - 'sales_unit' matched by UnitOfMeasure code.
      - 'wac' is a @property backed by FinishedProductStockBalance and is
        never stored on this model; it is excluded from import.
    """

    sales_unit = fields.Field(
        column_name="sales_unit",
        attribute="sales_unit",
        widget=ForeignKeyWidget(UnitOfMeasure, field="code"),
    )
    created_by = fields.Field(
        column_name="created_by",
        attribute="created_by",
        widget=ForeignKeyWidget(User, field="username"),
    )

    class Meta:
        model = FinishedProduct
        import_id_fields = ("reference",)
        fields = (
            "id",
            "reference",
            "designation",
            "sales_unit",
            "reference_selling_price",
            "alert_threshold",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        )
        # 'wac' is a @property — never import/export directly.
        export_order = fields
        skip_unchanged = True
        report_skipped = False

    def dehydrate_sales_unit(self, obj):
        return obj.sales_unit.code

    def dehydrate_created_by(self, obj):
        return obj.created_by.username

    def before_import_row(self, row, row_number=None, **kwargs):
        if not row.get("reference"):
            row["reference"] = ""
