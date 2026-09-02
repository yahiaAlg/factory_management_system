# stock/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin, ExportActionMixin
from .models import (
    RawMaterialStockBalance,
    FinishedProductStockBalance,
    StockMovement,
    StockAdjustment,
    StockAdjustmentLine,
)
from .resources import (
    RawMaterialStockBalanceResource,
    FinishedProductStockBalanceResource,
    StockMovementResource,
    StockAdjustmentResource,
    StockAdjustmentLineResource,
)


@admin.register(RawMaterialStockBalance)
class RawMaterialStockBalanceAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_class = RawMaterialStockBalanceResource

    list_display = ("raw_material", "site", "quantity", "stock_status_badge", "last_movement_date", "last_updated")
    list_filter = ("site",)
    search_fields = ("raw_material__reference", "raw_material__designation")
    readonly_fields = ("site", "raw_material", "quantity", "last_movement_date", "last_updated")
    ordering = ("raw_material__reference",)

    # BR-RM-05: quantity exclusively managed via stock signals — no write access
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Statut")
    def stock_status_badge(self, obj):
        # Per-site status (functional spec §25.2.3) — obj.get_stock_status()
        # scopes to obj.site rather than aggregating across every site.
        status = obj.get_stock_status()
        config = {
            "available": ("#198754", "Disponible"),
            "running_low": ("#fd7e14", "Alerte"),
            "stockout": ("#dc3545", "Rupture"),
            "on_order": ("#0d6efd", "En commande"),
        }
        color, label = config.get(status, ("#6c757d", status))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color, label,
        )


@admin.register(FinishedProductStockBalance)
class FinishedProductStockBalanceAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_class = FinishedProductStockBalanceResource

    list_display = (
        "finished_product", "site", "quantity", "weighted_average_cost",
        "stock_status_badge", "last_movement_date", "last_updated",
    )
    list_filter = ("site",)
    search_fields = ("finished_product__reference", "finished_product__designation")
    readonly_fields = ("site", "finished_product", "quantity", "weighted_average_cost", "last_movement_date", "last_updated")
    ordering = ("finished_product__reference",)

    # Spec S7: managed exclusively via stock signals — no write access
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Statut")
    def stock_status_badge(self, obj):
        status = obj.get_stock_status()
        config = {
            "available": ("#198754", "Disponible"),
            "running_low": ("#fd7e14", "Alerte"),
            "stockout": ("#dc3545", "Rupture"),
        }
        color, label = config.get(status, ("#6c757d", status))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color, label,
        )


@admin.register(StockMovement)
class StockMovementAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_class = StockMovementResource

    list_display = (
        "movement_date", "site", "movement_type_badge", "raw_material", "finished_product",
        "quantity", "unit_price", "unit_cost",
        "source_document_type", "source_document_id",
    )
    list_filter = ("site", "movement_type", "source_document_type", "movement_date")
    search_fields = (
        "raw_material__reference", "finished_product__reference",
        "source_document_id", "remarks",
    )
    date_hierarchy = "movement_date"
    ordering = ("-movement_date", "-created_at")
    readonly_fields = (
        "site", "raw_material", "finished_product", "movement_type",
        "quantity", "unit_price", "unit_cost",
        "source_document_type", "source_document_id", "source_line_id",
        "movement_date", "remarks", "created_by", "created_at",
    )

    # BR-RM-05: only created by authorised signal handlers
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Type de mouvement")
    def movement_type_badge(self, obj):
        colors = {
            "in": "#198754",
            "out": "#dc3545",
            "adjustment_in": "#0d6efd",
            "adjustment_out": "#fd7e14",
        }
        color = colors.get(obj.movement_type, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color, obj.get_movement_type_display(),
        )


class StockAdjustmentLineInline(admin.TabularInline):
    model = StockAdjustmentLine
    extra = 1
    fields = ("raw_material", "finished_product", "quantity_before", "quantity_after", "remarks")
    autocomplete_fields = ("raw_material", "finished_product")


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(ImportExportModelAdmin):
    resource_class = StockAdjustmentResource

    list_display = (
        "reference", "site", "adjustment_type", "adjustment_date",
        "reason_short", "approved_by", "approved_at", "created_by",
    )
    list_filter = ("site", "adjustment_type", "adjustment_date")
    search_fields = ("reference", "reason")
    date_hierarchy = "adjustment_date"
    ordering = ("-adjustment_date", "-reference")
    readonly_fields = ("reference", "approved_by", "approved_at", "created_by", "created_at")
    inlines = [StockAdjustmentLineInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "site", "adjustment_type", "adjustment_date", "reason"),
        }),
        ("Approbation", {
            "fields": ("approved_by", "approved_at"),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Motif")
    def reason_short(self, obj):
        return obj.reason[:60] + "…" if len(obj.reason) > 60 else obj.reason

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StockAdjustmentLine)
class StockAdjustmentLineAdmin(ImportExportModelAdmin):
    resource_class = StockAdjustmentLineResource

    list_display = (
        "stock_adjustment", "raw_material", "finished_product",
        "quantity_before", "quantity_after", "quantity_adjustment_display",
    )
    search_fields = ("stock_adjustment__reference", "raw_material__reference", "finished_product__reference")
    autocomplete_fields = ("stock_adjustment", "raw_material", "finished_product")

    @admin.display(description="Ajustement")
    def quantity_adjustment_display(self, obj):
        delta = obj.quantity_after - obj.quantity_before
        color = "#198754" if delta >= 0 else "#dc3545"
        sign = "+" if delta >= 0 else ""
        return format_html('<span style="color:{};font-weight:bold">{}{}</span>', color, sign, delta)
