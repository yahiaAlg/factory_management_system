# core/resources.py
from import_export import resources
from .models import CompanyInformation, SystemParameter, DocumentSequence


class CompanyInformationResource(resources.ModelResource):
    """
    Import/export for CompanyInformation (singleton).

    Import warning: the model enforces a singleton constraint — only one
    record is permitted.  Importing more than one row will raise ValueError.
    The logo ImageField is excluded; manage it via the admin interface.
    """

    class Meta:
        model = CompanyInformation
        fields = (
            "id",
            "raison_sociale",
            "forme_juridique",
            "nif",
            "nis",
            "rc",
            "ai",
            "address",
            "wilaya",
            "phone",
            "email",
            "bank_name",
            "bank_account",
            "rib",
            "vat_rate",
            "fiscal_regime",
            "created_at",
            "updated_at",
        )
        # logo excluded — binary/file field not safe to round-trip via CSV/XLSX.
        exclude = ("logo",)
        export_order = (
            "id",
            "raison_sociale",
            "forme_juridique",
            "nif",
            "nis",
            "rc",
            "ai",
            "address",
            "wilaya",
            "phone",
            "email",
            "bank_name",
            "bank_account",
            "rib",
            "vat_rate",
            "fiscal_regime",
            "created_at",
            "updated_at",
        )
        skip_unchanged = True
        report_skipped = False


class SystemParameterResource(resources.ModelResource):
    """
    Import/export for SystemParameter.

    'key' is the natural identifier — use it to update existing parameters.
    'value' is always a text field; cast appropriately in application code.
    """

    class Meta:
        model = SystemParameter
        import_id_fields = ("key",)
        fields = (
            "id",
            "category",
            "key",
            "value",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False


class DocumentSequenceResource(resources.ModelResource):
    """
    Import/export for DocumentSequence.

    Import warning: modifying current_number can cause duplicate document
    references if the target environment has already issued references up to
    that number.  Use with care — typically export-only for backup/migration.
    """

    class Meta:
        model = DocumentSequence
        import_id_fields = ("prefix", "current_year")
        fields = (
            "id",
            "prefix",
            "current_year",
            "current_number",
            "description",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = False
