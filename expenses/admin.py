# expenses/admin.py
from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from .models import ExpenseCategory, Expense, SupportingDocument
from .resources import ExpenseCategoryResource, ExpenseResource, SupportingDocumentResource


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ImportExportModelAdmin):
    resource_class = ExpenseCategoryResource

    list_display = ("code", "label", "order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    ordering = ("order", "label")


class SupportingDocumentInline(admin.TabularInline):
    model = SupportingDocument
    extra = 0
    fields = ("doc_type", "description", "file", "file_reference", "registered_by", "registered_at")
    readonly_fields = ("registered_by", "registered_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Filter to only documents linked to Expense entity type
        return qs.filter(entity_type="expense")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(ImportExportModelAdmin):
    resource_class = ExpenseResource

    list_display = (
        "reference", "expense_date", "category", "description_short",
        "amount", "beneficiary", "status_badge", "created_by",
    )
    list_filter = ("status", "category", "payment_method", "expense_date")
    search_fields = ("reference", "description", "beneficiary")
    date_hierarchy = "expense_date"
    ordering = ("-expense_date", "-reference")
    readonly_fields = (
        "reference", "validated_by", "validated_at",
        "created_by", "created_at", "updated_at",
    )

    fieldsets = (
        ("Identification", {
            "fields": ("reference", "expense_date", "category", "description", "status"),
        }),
        ("Montant & Paiement", {
            "fields": ("amount", "beneficiary", "payment_method", "payment_date"),
        }),
        ("Validation", {
            "fields": ("validated_by", "validated_at", "rejection_reason"),
        }),
        ("Liens", {
            "fields": ("linked_supplier_invoice",),
        }),
        ("Métadonnées", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Description")
    def description_short(self, obj):
        return obj.description[:50] + "…" if len(obj.description) > 50 else obj.description

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "recorded": "#6c757d",
            "validated": "#0d6efd",
            "paid": "#198754",
            "rejected": "#dc3545",
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


@admin.register(SupportingDocument)
class SupportingDocumentAdmin(ImportExportModelAdmin):
    resource_class = SupportingDocumentResource

    list_display = (
        "doc_type", "entity_type", "entity_id",
        "description_short", "file_reference", "registered_by", "registered_at",
    )
    list_filter = ("doc_type", "entity_type")
    search_fields = ("description", "file_reference", "entity_id")
    readonly_fields = ("registered_by", "registered_at")
    date_hierarchy = "registered_at"
    ordering = ("-registered_at",)

    @admin.display(description="Description")
    def description_short(self, obj):
        return obj.description[:60] + "…" if len(obj.description) > 60 else obj.description

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registered_by = request.user
        super().save_model(request, obj, form, change)
