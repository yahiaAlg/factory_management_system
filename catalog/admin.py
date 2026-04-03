# catalog/admin.py
from django.contrib import admin
from .models import RawMaterialCategory, UnitOfMeasure, RawMaterial, FinishedProduct


@admin.register(RawMaterialCategory)
class RawMaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    list_editable = ["is_active"]


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "symbol", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    list_editable = ["is_active"]


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "designation",
        "category",
        "unit_of_measure",
        "reference_price",
        "get_current_stock",
        "get_stock_status",
        "is_active",
    ]
    list_filter = ["category", "is_active", "created_at"]
    search_fields = ["reference", "designation"]
    list_editable = ["is_active"]
    readonly_fields = ["reference", "created_by", "created_at", "updated_at"]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": ("reference", "designation", "category", "unit_of_measure"),
            },
        ),
        (
            "Fournisseur",
            {
                "fields": ("default_supplier",),
            },
        ),
        (
            "Prix et seuils",
            {
                "fields": ("reference_price", "alert_threshold", "stockout_threshold"),
            },
        ),
        (
            "Statut",
            {
                "fields": ("is_active",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(FinishedProduct)
class FinishedProductAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "designation",
        "sales_unit",
        "reference_selling_price",
        "get_current_stock",
        "get_stock_status",
        "is_active",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["reference", "designation"]
    list_editable = ["is_active"]
    readonly_fields = ["reference", "created_by", "created_at", "updated_at"]

    fieldsets = (
        (
            "Informations générales",
            {
                # FIX: removed 'source_formulation' — field does not exist on FinishedProduct.
                # The formulation link is on Formulation.finished_product (FK from production side).
                "fields": ("reference", "designation", "sales_unit"),
            },
        ),
        (
            "Prix et seuils",
            {
                "fields": ("reference_selling_price", "alert_threshold"),
            },
        ),
        (
            "Statut",
            {
                "fields": ("is_active",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
