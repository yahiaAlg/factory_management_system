# production/admin.py
from django.contrib import admin
from .models import Formulation, FormulationLine, ProductionOrder, ProductionOrderLine


class FormulationLineInline(admin.TabularInline):
    model = FormulationLine
    extra = 1


@admin.register(Formulation)
class FormulationAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "version",
        "designation",
        "finished_product",
        "reference_batch_qty",
        "expected_yield_pct",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "finished_product", "created_at"]
    search_fields = ["reference", "designation"]
    readonly_fields = ["reference", "version", "created_by", "created_at", "updated_at"]
    inlines = [FormulationLineInline]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": ("reference", "version", "designation", "finished_product"),
            },
        ),
        (
            "Paramètres de production",
            {
                "fields": (
                    "reference_batch_qty",
                    "reference_batch_unit",
                    "expected_yield_pct",
                ),
            },
        ),
        (
            "Statut et notes",
            {
                "fields": ("is_active", "technical_notes"),
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


class ProductionOrderLineInline(admin.TabularInline):
    model = ProductionOrderLine
    extra = 0
    # delta_qty and financial_impact are @property — valid in readonly_fields
    readonly_fields = ["qty_theoretical", "delta_qty", "financial_impact"]


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "formulation",
        "target_qty",
        "actual_qty_produced",
        "get_yield_rate",
        "get_yield_status",
        "status",
        "launch_date",
    ]
    # FIX: removed 'yield_status' from list_filter — it is a @property, not a DB
    # field, and Django ORM cannot filter on it.
    list_filter = ["status", "launch_date"]
    search_fields = ["reference", "formulation__designation"]
    # yield_rate and yield_status are @property — Django admin renders them fine
    # in readonly_fields (it calls them as callables).
    readonly_fields = [
        "reference",
        "formulation_version",
        "yield_rate",
        "yield_status",
        "stock_check_passed",
        "created_by",
        "created_at",
        "closed_by",
    ]
    inlines = [ProductionOrderLineInline]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": ("reference", "formulation", "formulation_version"),
            },
        ),
        (
            "Paramètres de production",
            {
                "fields": ("target_qty", "target_unit", "launch_date"),
            },
        ),
        (
            "Résultats",
            {
                "fields": (
                    "actual_qty_produced",
                    "yield_rate",
                    "yield_status",
                    "closure_date",
                ),
            },
        ),
        (
            "Statut",
            {
                "fields": ("status", "stock_check_passed"),
            },
        ),
        (
            "Notes",
            {
                "fields": ("notes",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_by", "created_at", "closed_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # Proxy methods so list_display can show @property values
    def get_yield_rate(self, obj):
        r = obj.yield_rate
        return f"{r:.2f} %" if r is not None else "—"

    get_yield_rate.short_description = "Rendement"

    def get_yield_status(self, obj):
        return obj.yield_status or "—"

    get_yield_status.short_description = "Statut rendement"
