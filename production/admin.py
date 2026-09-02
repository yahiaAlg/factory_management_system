# production/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import Formulation, FormulationLine, ProductionOrder, ProductionOrderLine
from .resources import (
    FormulationResource,
    FormulationLineResource,
    ProductionOrderResource,
    ProductionOrderLineResource,
)


class FormulationLineInline(admin.TabularInline):
    model = FormulationLine
    extra = 1
    fields = ("raw_material", "qty_per_batch", "unit_of_measure", "tolerance_pct",
              "is_complement")
    autocomplete_fields = ("raw_material", "unit_of_measure")


class ProductionOrderLineInline(admin.TabularInline):
    model = ProductionOrderLine
    extra = 0
    fields = ("raw_material", "qty_theoretical", "qty_actual", "tolerance_pct")
    readonly_fields = ("qty_theoretical",)
    autocomplete_fields = ("raw_material",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Formulation)
class FormulationAdmin(ImportExportModelAdmin):
    resource_class = FormulationResource

    list_display = (
        "reference", "designation", "finished_product",
        "version", "reference_batch_qty", "reference_batch_unit",
        "expected_yield_pct", "is_active",
    )
    list_filter = ("is_active", "finished_product")
    search_fields = ("reference", "designation")
    readonly_fields = ("reference", "created_by", "created_at", "updated_at")
    autocomplete_fields = ("finished_product", "reference_batch_unit")
    ordering = ("reference", "-version")
    inlines = [FormulationLineInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "designation", "finished_product", "version", "is_active"),
        }),
        ("Paramètres de lot", {
            "fields": ("reference_batch_qty", "reference_batch_unit", "expected_yield_pct"),
        }),
        ("Masse cible — moteur de formulation (planifié, §22)", {
            "fields": ("target_batch_mass_kg",),
            "classes": ("collapse",),
            "description": "Requis uniquement si une ligne complément est utilisée (Section 22, non déployé).",
        }),
        ("Notes techniques", {
            "fields": ("technical_notes",),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # SPEC S22.4: recompute the complement line's quantity after every
        # sibling line save (add/edit/delete via the inline formset).
        form.instance.recompute_complement_quantity()


@admin.register(FormulationLine)
class FormulationLineAdmin(ImportExportModelAdmin):
    resource_class = FormulationLineResource

    list_display = ("formulation", "raw_material", "qty_per_batch", "unit_of_measure",
                     "tolerance_pct", "is_complement")
    list_filter = ("formulation", "is_complement")
    search_fields = ("formulation__reference", "raw_material__reference", "raw_material__designation")
    autocomplete_fields = ("formulation", "raw_material", "unit_of_measure")


@admin.register(ProductionOrder)
class ProductionOrderAdmin(ImportExportModelAdmin):
    resource_class = ProductionOrderResource

    list_display = (
        "reference", "site", "formulation", "formulation_version",
        "target_qty", "target_unit", "status_badge",
        "launch_date", "closure_date", "actual_qty_produced",
    )
    list_filter = ("site", "status", "launch_date")
    search_fields = ("reference", "formulation__reference")
    date_hierarchy = "launch_date"
    ordering = ("-launch_date", "-reference")
    readonly_fields = (
        "reference", "stock_check_passed",
        "created_by", "created_at", "closed_by",
    )
    autocomplete_fields = ("formulation", "target_unit")
    inlines = [ProductionOrderLineInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "site", "formulation", "formulation_version", "status"),
        }),
        ("Quantités & Unités", {
            "fields": ("target_qty", "target_unit", "actual_qty_produced"),
        }),
        ("Dates", {
            "fields": ("launch_date", "closure_date"),
        }),
        ("Contrôle", {
            "fields": ("stock_check_passed", "notes"),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "closed_by"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "validated": "#0d6efd",
            "in_progress": "#fd7e14",
            "closed": "#198754",
            "cancelled": "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color,
            obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProductionOrderLine)
class ProductionOrderLineAdmin(ImportExportModelAdmin):
    resource_class = ProductionOrderLineResource

    list_display = (
        "production_order", "raw_material",
        "qty_theoretical", "qty_actual", "tolerance_pct",
    )
    list_filter = ("production_order__status",)
    search_fields = ("production_order__reference", "raw_material__reference")
    readonly_fields = ("qty_theoretical",)
    autocomplete_fields = ("production_order", "raw_material")
