# core/admin.py
from django.contrib import admin
from django.contrib import messages
from django.contrib.contenttypes.admin import GenericTabularInline
from import_export.admin import ImportExportModelAdmin
from .models import (
    CompanyInformation,
    SystemParameter,
    DocumentSequence,
    PieceJointe,
    ProductionSite,
)
from .resources import (
    CompanyInformationResource,
    SystemParameterResource,
    DocumentSequenceResource,
)


# ---------------------------------------------------------------------------
# PieceJointeInline — shared generic inline, reused by every admin that
# carries proof documents (SupplierDN, SupplierInvoice, Expense, ClientDN,
# ClientInvoice, ...). Import and drop into `inlines` on the target
# ModelAdmin. Mirrors the avicole project's core.admin.PieceJointeInline.
# ---------------------------------------------------------------------------


class PieceJointeInline(GenericTabularInline):
    model = PieceJointe
    ct_field = "content_type"
    ct_fk_field = "object_id"
    extra = 1
    fields = ("fichier", "type_document", "description", "uploaded_by")
    readonly_fields = ("uploaded_by",)
    verbose_name = "Pièce jointe"
    verbose_name_plural = "Pièces jointes"

    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit=False)
        if not obj.uploaded_by_id and self.request.user.is_authenticated:
            obj.uploaded_by = self.request.user
        if commit:
            obj.save()
        return obj

    def get_formset(self, request, obj=None, **kwargs):
        self.request = request
        return super().get_formset(request, obj, **kwargs)


@admin.register(PieceJointe)
class PieceJointeAdmin(admin.ModelAdmin):
    list_display = ("type_document", "content_object", "description", "uploaded_by", "created_at")
    list_filter = ("type_document", "content_type")
    search_fields = ("description",)
    readonly_fields = ("uploaded_by", "created_at")


@admin.register(CompanyInformation)
class CompanyInformationAdmin(ImportExportModelAdmin):
    resource_class = CompanyInformationResource

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "raison_sociale",
                    "forme_juridique",
                    "nif",
                    "nis",
                    "rc",
                    "ai",
                ),
            },
        ),
        (
            "Coordonnées",
            {
                "fields": ("address", "wilaya", "phone", "email"),
            },
        ),
        (
            "Banque",
            {
                "fields": ("bank_name", "bank_account", "rib"),
            },
        ),
        (
            "Fiscal",
            {
                "fields": ("vat_rate", "fiscal_regime"),
            },
        ),
        (
            "Identité visuelle",
            {
                "fields": ("logo",),
            },
        ),
        (
            "Horodatage",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request):
        # Singleton: only one record allowed
        return not CompanyInformation.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Immediately reflect the new name in the running admin site
        # so the header updates without a server restart.
        from .app import _apply_admin_branding

        _apply_admin_branding(obj)


@admin.register(SystemParameter)
class SystemParameterAdmin(ImportExportModelAdmin):
    resource_class = SystemParameterResource

    list_display = (
        "category",
        "key",
        "value",
        "description_short",
        "is_active",
        "updated_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("key", "description", "value")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("category", "key")

    fieldsets = (
        (
            None,
            {
                "fields": ("category", "key", "value", "description", "is_active"),
            },
        ),
        (
            "Horodatage",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Description")
    def description_short(self, obj):
        return (
            obj.description[:60] + "…" if len(obj.description) > 60 else obj.description
        )


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(ImportExportModelAdmin):
    resource_class = DocumentSequenceResource

    list_display = (
        "prefix",
        "current_year_display",
        "current_number",
        "next_reference_preview",
        "description",
    )
    search_fields = ("prefix", "description")
    ordering = ("prefix", "current_year")

    # current_number is read-only to prevent accidental duplicate references
    readonly_fields = ("next_reference_preview",)

    fieldsets = (
        (
            None,
            {
                "fields": ("prefix", "current_year", "current_number", "description"),
            },
        ),
        (
            "Aperçu",
            {
                "fields": ("next_reference_preview",),
            },
        ),
    )

    @admin.display(description="Année")
    def current_year_display(self, obj):
        return "—" if obj.current_year == 0 else str(obj.current_year)

    @admin.display(description="Prochaine référence")
    def next_reference_preview(self, obj):
        next_num = obj.current_number + 1
        if obj.current_year == 0:
            return f"{obj.prefix}-{next_num:03d}"
        return f"{obj.prefix}-{obj.current_year}-{next_num:04d}"

    def save_model(self, request, obj, form, change):
        if change:
            messages.warning(
                request,
                "⚠️ Modifier current_number peut générer des références en doublon si des "
                "documents ont déjà été émis jusqu'à ce numéro dans l'environnement cible.",
            )
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# ProductionSite (functional spec §25.2) — admin-only CRUD, mirrors the
# avicole project's Branche admin.
# ---------------------------------------------------------------------------


@admin.register(ProductionSite)
class ProductionSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "contact", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "address")
    autocomplete_fields = ("contact",)
