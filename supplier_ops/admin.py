# supplier_ops/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import (
    SupplierDN, SupplierDNLine,
    SupplierInvoice, SupplierInvoiceLine, SupplierInvoiceDNLink,
    SupplierPayment, SupplierAccountPayment,
)
from .resources import (
    SupplierDNResource, SupplierDNLineResource,
    SupplierInvoiceResource, SupplierInvoiceLineResource,
    SupplierInvoiceDNLinkResource,
    SupplierPaymentResource, SupplierAccountPaymentResource,
)


class SupplierDNLineInline(admin.TabularInline):
    model = SupplierDNLine
    extra = 1
    fields = ("raw_material", "quantity_received", "unit_of_measure", "agreed_unit_price")
    autocomplete_fields = ("raw_material", "unit_of_measure")


class SupplierInvoiceLineInline(admin.TabularInline):
    model = SupplierInvoiceLine
    extra = 1
    fields = ("raw_material", "designation", "quantity_invoiced", "unit_price_invoiced")
    autocomplete_fields = ("raw_material",)


class SupplierInvoiceDNLinkInline(admin.TabularInline):
    model = SupplierInvoiceDNLink
    extra = 0
    fields = ("supplier_dn", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("supplier_dn",)


class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0
    fields = ("reference", "payment_date", "amount", "payment_method", "bank_reference", "recorded_by")
    readonly_fields = ("reference", "recorded_by")


@admin.register(SupplierDN)
class SupplierDNAdmin(ImportExportModelAdmin):
    resource_class = SupplierDNResource

    list_display = (
        "reference", "site", "supplier", "delivery_date",
        "total_amount_ht", "status_badge",
        "validated_by", "linked_invoice",
    )
    list_filter = ("site", "status", "delivery_date")
    search_fields = ("reference", "external_reference", "supplier__code", "supplier__raison_sociale")
    date_hierarchy = "delivery_date"
    ordering = ("-delivery_date", "-reference")
    readonly_fields = (
        "reference", "total_amount_ht", "validated_by", "validated_at",
        "created_by", "created_at", "updated_at",
    )
    autocomplete_fields = ("supplier", "linked_invoice")
    inlines = [SupplierDNLineInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "site", "external_reference", "supplier", "delivery_date", "status"),
        }),
        ("Montant", {
            "fields": ("total_amount_ht",),
        }),
        ("Validation", {
            "fields": ("validated_by", "validated_at"),
        }),
        ("Liens & Remarques", {
            "fields": ("linked_invoice", "remarks"),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "pending": "#fd7e14",
            "validated": "#198754",
            "cancelled": "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color, obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierDNLine)
class SupplierDNLineAdmin(ImportExportModelAdmin):
    resource_class = SupplierDNLineResource

    list_display = ("supplier_dn", "raw_material", "quantity_received", "unit_of_measure", "agreed_unit_price")
    search_fields = ("supplier_dn__reference", "raw_material__reference", "raw_material__designation")
    autocomplete_fields = ("supplier_dn", "raw_material", "unit_of_measure")


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(ImportExportModelAdmin):
    resource_class = SupplierInvoiceResource

    list_display = (
        "reference", "external_reference", "supplier",
        "invoice_date", "due_date",
        "total_ht", "vat_amount", "total_ttc", "balance_due",
        "status_badge",
    )
    list_filter = ("status", "invoice_date", "due_date")
    search_fields = ("reference", "external_reference", "supplier__code", "supplier__raison_sociale")
    date_hierarchy = "invoice_date"
    ordering = ("-invoice_date", "-reference")
    readonly_fields = (
        "reference", "total_ht", "vat_amount", "total_ttc",
        "balance_due", "created_by", "created_at", "updated_at",
    )
    autocomplete_fields = ("supplier",)
    inlines = [SupplierInvoiceLineInline, SupplierInvoiceDNLinkInline, SupplierPaymentInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "external_reference", "supplier", "invoice_date", "due_date", "status"),
        }),
        ("Montants", {
            "fields": ("total_ht", "vat_amount", "total_ttc", "balance_due"),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "verified": "#0d6efd",
            "unpaid": "#fd7e14",
            "partially_paid": "#ffc107",
            "paid": "#198754",
            "in_dispute": "#dc3545",
            "cancelled": "#adb5bd",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em">{}</span>',
            color, obj.get_status_display(),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierInvoiceLine)
class SupplierInvoiceLineAdmin(ImportExportModelAdmin):
    resource_class = SupplierInvoiceLineResource

    list_display = ("supplier_invoice", "raw_material", "designation", "quantity_invoiced", "unit_price_invoiced")
    search_fields = ("supplier_invoice__reference", "raw_material__reference", "designation")
    autocomplete_fields = ("supplier_invoice", "raw_material")


@admin.register(SupplierInvoiceDNLink)
class SupplierInvoiceDNLinkAdmin(ImportExportModelAdmin):
    resource_class = SupplierInvoiceDNLinkResource

    list_display = ("supplier_invoice", "supplier_dn", "created_at")
    search_fields = ("supplier_invoice__reference", "supplier_dn__reference")
    autocomplete_fields = ("supplier_invoice", "supplier_dn")
    readonly_fields = ("created_at",)


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(ImportExportModelAdmin):
    resource_class = SupplierPaymentResource

    list_display = (
        "reference", "supplier_invoice", "supplier",
        "payment_date", "amount", "payment_method", "bank_reference",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("reference", "supplier__code", "supplier_invoice__reference", "bank_reference")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date", "-reference")
    readonly_fields = ("reference", "recorded_by", "created_at")
    autocomplete_fields = ("supplier_invoice", "supplier")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierAccountPayment)
class SupplierAccountPaymentAdmin(ImportExportModelAdmin):
    resource_class = SupplierAccountPaymentResource

    list_display = (
        "reference", "supplier", "payment_date",
        "amount", "payment_method", "bank_reference",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("reference", "supplier__code", "bank_reference")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date", "-reference")
    readonly_fields = ("reference", "recorded_by", "created_at")
    autocomplete_fields = ("supplier",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# §23 (planned) — Supplier Advance
# ---------------------------------------------------------------------------
from .models import SupplierAdvance, SupplierAdvanceAllocation


class SupplierAdvanceAllocationInline(admin.TabularInline):
    model = SupplierAdvanceAllocation
    extra = 0
    readonly_fields = ("invoice", "amount_allocated", "created_at")
    can_delete = False


@admin.register(SupplierAdvance)
class SupplierAdvanceAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "supplier", "date", "origin",
        "amount", "remaining_amount", "payment_method",
    )
    list_filter = ("origin", "payment_method", "date")
    search_fields = ("reference", "supplier__code", "supplier__raison_sociale")
    date_hierarchy = "date"
    ordering = ("-date", "-reference")
    readonly_fields = ("reference", "settlement", "origin", "recorded_by", "created_at")
    autocomplete_fields = ("supplier",)
    inlines = [SupplierAdvanceAllocationInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupplierAdvanceAllocation)
class SupplierAdvanceAllocationAdmin(admin.ModelAdmin):
    list_display = ("advance", "invoice", "amount_allocated", "created_at")
    search_fields = ("advance__reference", "invoice__reference")
    readonly_fields = ("advance", "invoice", "amount_allocated", "created_at")
