# sales/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import (
    ClientDN, ClientDNLine,
    ClientInvoice, ClientInvoiceDNLink,
    ClientPayment, ClientAccountPayment,
)
from .resources import (
    ClientDNResource, ClientDNLineResource,
    ClientInvoiceResource, ClientInvoiceDNLinkResource,
    ClientPaymentResource, ClientAccountPaymentResource,
)


class ClientDNLineInline(admin.TabularInline):
    model = ClientDNLine
    extra = 1
    fields = ("finished_product", "quantity_delivered", "unit_of_measure", "selling_unit_price_ht")
    autocomplete_fields = ("finished_product", "unit_of_measure")


class ClientInvoiceDNLinkInline(admin.TabularInline):
    model = ClientInvoiceDNLink
    extra = 0
    fields = ("client_dn", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("client_dn",)


class ClientPaymentInline(admin.TabularInline):
    model = ClientPayment
    extra = 0
    fields = ("reference", "payment_date", "amount", "payment_method", "bank_reference", "recorded_by")
    readonly_fields = ("reference", "recorded_by")


@admin.register(ClientDN)
class ClientDNAdmin(ImportExportModelAdmin):
    resource_class = ClientDNResource

    list_display = (
        "reference", "site", "client", "delivery_date",
        "total_ht", "discount_pct", "status_badge",
        "linked_invoice", "created_by",
    )
    list_filter = ("site", "status", "delivery_date")
    search_fields = ("reference", "client__code", "client__raison_sociale")
    date_hierarchy = "delivery_date"
    ordering = ("-delivery_date", "-reference")
    readonly_fields = (
        "reference", "total_ht", "validated_by", "validated_at",
        "created_by", "created_at", "updated_at",
    )
    autocomplete_fields = ("client", "linked_invoice")
    inlines = [ClientDNLineInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "site", "client", "delivery_date", "status"),
        }),
        ("Montant", {
            "fields": ("total_ht", "discount_pct"),
        }),
        ("Validation", {
            "fields": ("validated_by", "validated_at"),
        }),
        ("Liens", {
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
            "validated": "#198754",
            "invoiced": "#0d6efd",
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


@admin.register(ClientDNLine)
class ClientDNLineAdmin(ImportExportModelAdmin):
    resource_class = ClientDNLineResource

    list_display = ("client_dn", "finished_product", "quantity_delivered", "unit_of_measure", "selling_unit_price_ht")
    search_fields = ("client_dn__reference", "finished_product__reference")
    autocomplete_fields = ("client_dn", "finished_product", "unit_of_measure")


@admin.register(ClientInvoice)
class ClientInvoiceAdmin(ImportExportModelAdmin):
    resource_class = ClientInvoiceResource

    list_display = (
        "reference", "client", "invoice_date", "due_date",
        "total_ht", "discount_pct", "vat_amount", "total_ttc",
        "balance_due", "status_badge",
    )
    list_filter = ("status", "invoice_date", "due_date")
    search_fields = ("reference", "client__code", "client__raison_sociale")
    date_hierarchy = "invoice_date"
    ordering = ("-invoice_date", "-reference")
    readonly_fields = (
        "reference", "total_ht", "vat_amount", "total_ttc",
        "balance_due", "created_by", "created_at", "updated_at",
    )
    autocomplete_fields = ("client",)
    inlines = [ClientInvoiceDNLinkInline, ClientPaymentInline]

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "client", "invoice_date", "due_date", "status"),
        }),
        ("Montants", {
            "fields": ("total_ht", "discount_pct", "vat_amount", "total_ttc", "balance_due"),
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
            "issued": "#0d6efd",
            "partially_paid": "#fd7e14",
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


@admin.register(ClientInvoiceDNLink)
class ClientInvoiceDNLinkAdmin(ImportExportModelAdmin):
    resource_class = ClientInvoiceDNLinkResource

    list_display = ("client_invoice", "client_dn", "created_at")
    search_fields = ("client_invoice__reference", "client_dn__reference")
    autocomplete_fields = ("client_invoice", "client_dn")
    readonly_fields = ("created_at",)


@admin.register(ClientPayment)
class ClientPaymentAdmin(ImportExportModelAdmin):
    resource_class = ClientPaymentResource

    list_display = (
        "reference", "client_invoice", "client",
        "payment_date", "amount", "payment_method", "bank_reference",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("reference", "client__code", "client_invoice__reference", "bank_reference")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date", "-reference")
    readonly_fields = ("reference", "recorded_by", "created_at")
    autocomplete_fields = ("client_invoice", "client")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ClientAccountPayment)
class ClientAccountPaymentAdmin(ImportExportModelAdmin):
    resource_class = ClientAccountPaymentResource

    list_display = (
        "reference", "client", "payment_date",
        "amount", "payment_method", "bank_reference",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("reference", "client__code", "bank_reference")
    date_hierarchy = "payment_date"
    ordering = ("-payment_date", "-reference")
    readonly_fields = ("reference", "recorded_by", "created_at")
    autocomplete_fields = ("client",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# §23 (planned) — Client Advance
# ---------------------------------------------------------------------------
from .models import ClientAdvance, ClientAdvanceAllocation


class ClientAdvanceAllocationInline(admin.TabularInline):
    model = ClientAdvanceAllocation
    extra = 0
    readonly_fields = ("invoice", "amount_allocated", "created_at")
    can_delete = False


@admin.register(ClientAdvance)
class ClientAdvanceAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "client", "date", "origin",
        "amount", "remaining_amount", "payment_method",
    )
    list_filter = ("origin", "payment_method", "date")
    search_fields = ("reference", "client__code", "client__raison_sociale")
    date_hierarchy = "date"
    ordering = ("-date", "-reference")
    readonly_fields = ("reference", "settlement", "origin", "recorded_by", "created_at")
    autocomplete_fields = ("client",)
    inlines = [ClientAdvanceAllocationInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ClientAdvanceAllocation)
class ClientAdvanceAllocationAdmin(admin.ModelAdmin):
    list_display = ("advance", "invoice", "amount_allocated", "created_at")
    search_fields = ("advance__reference", "invoice__reference")
    readonly_fields = ("advance", "invoice", "amount_allocated", "created_at")
