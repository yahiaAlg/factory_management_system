# catalog/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import RawMaterialCategory, UnitOfMeasure, RawMaterial, FinishedProduct
from .resources import (
    RawMaterialCategoryResource,
    UnitOfMeasureResource,
    RawMaterialResource,
    FinishedProductResource,
)


@admin.register(RawMaterialCategory)
class RawMaterialCategoryAdmin(ImportExportModelAdmin):
    resource_class = RawMaterialCategoryResource

    list_display = ("name", "description_short", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)

    @admin.display(description="Description")
    def description_short(self, obj):
        return obj.description[:60] + "…" if len(obj.description) > 60 else obj.description


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(ImportExportModelAdmin):
    resource_class = UnitOfMeasureResource

    list_display = ("code", "name", "symbol", "is_volumetric", "is_active")
    list_filter = ("is_active", "is_volumetric")
    search_fields = ("code", "name", "symbol")


@admin.register(RawMaterial)
class RawMaterialAdmin(ImportExportModelAdmin):
    resource_class = RawMaterialResource

    list_display = (
        "reference", "designation", "category", "unit_of_measure",
        "default_supplier", "reference_price", "stock_status_badge",
        "alert_threshold", "stockout_threshold", "is_active",
    )
    list_filter = ("category", "is_active", "unit_of_measure")
    search_fields = ("reference", "designation")
    readonly_fields = ("reference", "created_at", "updated_at", "created_by")
    autocomplete_fields = ("category", "unit_of_measure", "default_supplier")
    ordering = ("reference",)

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "designation", "category", "unit_of_measure",
                       "default_supplier", "is_active"),
        }),
        ("Prix & Seuils", {
            "fields": ("reference_price", "alert_threshold", "stockout_threshold"),
        }),
        ("Équivalence kg — production (§22)", {
            "fields": ("kg_equivalent_mode", "kg_per_unit", "density_kg_per_liter",
                       "volumetric_factor"),
            "classes": ("collapse",),
            "description": "Non renseigné = 1 unité = 1 kg par défaut. Utilisé pour standardiser la production en kg (Section 22).",
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut stock")
    def stock_status_badge(self, obj):
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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FinishedProduct)
class FinishedProductAdmin(ImportExportModelAdmin):
    resource_class = FinishedProductResource

    list_display = (
        "reference", "designation", "sales_unit",
        "reference_selling_price", "wac", "alert_threshold",
        "stock_status_badge", "is_active",
    )
    list_filter = ("is_active", "sales_unit")
    search_fields = ("reference", "designation")
    readonly_fields = ("reference", "wac", "created_at", "updated_at", "created_by")
    autocomplete_fields = ("sales_unit",)
    ordering = ("reference",)

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "designation", "sales_unit", "is_active"),
        }),
        ("Tarification & Stock", {
            "fields": ("reference_selling_price", "wac", "alert_threshold"),
        }),
        ("Équivalence kg — production (§22)", {
            "fields": ("kg_equivalent_mode", "kg_per_unit", "density_kg_per_liter",
                       "volumetric_factor"),
            "classes": ("collapse",),
            "description": "Non renseigné = 1 unité = 1 kg par défaut. Utilisé pour standardiser la production en kg (Section 22).",
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut stock")
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

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
