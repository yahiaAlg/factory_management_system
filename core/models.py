# core/models.py
from django.conf import settings
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal


class CompanyInformation(models.Model):
    """Company information used in printed documents (singleton)."""

    raison_sociale = models.CharField(max_length=200, verbose_name="Raison sociale")
    forme_juridique = models.CharField(
        max_length=100, blank=True, verbose_name="Forme juridique"
    )
    nif = models.CharField(max_length=20, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=20, blank=True, verbose_name="NIS")
    rc = models.CharField(max_length=20, blank=True, verbose_name="RC")
    ai = models.CharField(max_length=20, blank=True, verbose_name="AI")
    address = models.TextField(verbose_name="Adresse")
    wilaya = models.CharField(max_length=100, verbose_name="Wilaya")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    bank_name = models.CharField(
        max_length=200, blank=True, verbose_name="Nom de la banque"
    )
    bank_account = models.CharField(
        max_length=50, blank=True, verbose_name="Compte bancaire"
    )
    rib = models.CharField(max_length=23, blank=True, verbose_name="RIB")
    logo = models.ImageField(upload_to="company/", blank=True, verbose_name="Logo")

    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.19"),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Taux de TVA",
    )
    fiscal_regime = models.CharField(
        max_length=100, blank=True, verbose_name="Régime fiscal"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Informations société"
        verbose_name_plural = "Informations société"

    def __str__(self):
        return self.raison_sociale

    def save(self, *args, **kwargs):
        if not self.pk and CompanyInformation.objects.exists():
            raise ValueError("Il ne peut y avoir qu'un seul enregistrement de société.")
        super().save(*args, **kwargs)


class SystemParameter(models.Model):
    """System-wide configuration parameters.

    SPEC S2 required keys (seed via data migration):
      reconciliation_tolerance_epsilon  Decimal  default 500.00
      reconciliation_dispute_delta      Decimal  default 5000.00
      expense_delegation_threshold      Decimal  default 50000.00
      yield_warning_threshold           Decimal  default 90.00
      yield_critical_threshold          Decimal  default 80.00
      payment_due_alert_days            int      default 7
      default_vat_rate                  Decimal  default 0.19
      current_year                      int      current year
    """

    PARAMETER_TYPES = [
        ("financial", "Paramètres financiers"),
        ("stock", "Paramètres stock"),
        ("production", "Paramètres production"),
        ("alert", "Paramètres alertes"),
        ("document", "Paramètres documents"),
    ]

    category = models.CharField(
        max_length=20, choices=PARAMETER_TYPES, verbose_name="Catégorie"
    )
    key = models.CharField(max_length=100, unique=True, verbose_name="Clé")
    value = models.TextField(verbose_name="Valeur")
    description = models.TextField(verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramètre système"
        verbose_name_plural = "Paramètres système"

    def __str__(self):
        return f"{self.category} — {self.key}"

    @classmethod
    def get_value(cls, key, default=None):
        try:
            return cls.objects.get(key=key, is_active=True).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_decimal_value(cls, key, default=Decimal("0")):
        val = cls.get_value(key)
        if val is not None:
            try:
                return Decimal(str(val))
            except Exception:
                pass
        return default

    @classmethod
    def get_int_value(cls, key, default=0):
        val = cls.get_value(key)
        if val is not None:
            try:
                return int(val)
            except Exception:
                pass
        return default


class DocumentSequence(models.Model):
    """Document reference number sequences.

    SPEC S8: every document type has a dedicated prefix + year counter.
    Year-less sequences (RM, PF, F) use current_year=0 as a sentinel.

    get_next_reference() is wrapped in select_for_update() to prevent
    duplicate reference numbers under concurrent requests.
    """

    prefix = models.CharField(max_length=20, verbose_name="Préfixe")
    current_year = models.IntegerField(verbose_name="Année courante")
    current_number = models.IntegerField(default=0, verbose_name="Numéro courant")
    description = models.CharField(max_length=200, verbose_name="Description")

    class Meta:
        verbose_name = "Séquence document"
        verbose_name_plural = "Séquences documents"
        unique_together = ["prefix", "current_year"]

    def __str__(self):
        if self.current_year == 0:
            return f"{self.prefix}-{self.current_number:03d}"
        return f"{self.prefix}-{self.current_year}-{self.current_number:04d}"

    @classmethod
    def get_next_reference(cls, prefix, year, site_code=None):
        """
        Atomically increment and return the next reference string.

        For year-less sequences (RM, PF, F) pass year=0.
        For yearly sequences pass the 4-digit year.

        site_code (functional spec §25.2.4): when given, it is embedded
        in both the sequence key and the returned reference —
        `<prefix>-<site_code>-<year>-<nnnn>` — so each site's numbering
        stays independent (BL-F, BL-C, OP, ADJ only; every other document
        type stays company-wide and omits this). Kept as a separate
        DocumentSequence row per (prefix, site_code, year) so two sites can
        issue documents the same day with no coordination or collision.
        """
        effective_prefix = f"{prefix}-{site_code}" if site_code else prefix
        with transaction.atomic():
            sequence, _ = cls.objects.select_for_update().get_or_create(
                prefix=effective_prefix,
                current_year=year,
                defaults={
                    "current_number": 0,
                    "description": f"Séquence pour {effective_prefix}",
                },
            )
            sequence.current_number += 1
            sequence.save(update_fields=["current_number"])

        if year == 0:
            return f"{effective_prefix}-{sequence.current_number:03d}"
        return f"{effective_prefix}-{year}-{sequence.current_number:04d}"


# ---------------------------------------------------------------------------
# PieceJointe — generic document-proof model (mirrors the mechanism used in
# the avicole project). Replaces the ad-hoc `SupportingDocument`
# (entity_type CharField + entity_id) used by expenses/supplier_ops with a
# real ContentType + GenericForeignKey link. Attaches to ANY model
# (SupplierDN, SupplierInvoice, SupplierPayment, ClientDN, ClientInvoice,
# ClientPayment, Expense, ...) and supports MULTIPLE files per record.
#
# Use the reverse `GenericRelation` declared on the target model (e.g.
# `dn.pieces_jointes.all()`) to query/attach — same pattern as core.forms.
# ---------------------------------------------------------------------------


class PieceJointe(models.Model):
    """
    A single proof/attachment file linked to any other model instance via
    GenericForeignKey. The `type_document` choices reuse the SD-* codes
    already used by the SPEC S2 hard gates (SD-DNF, SD-EXP, ...).
    """

    TYPE_SD_DNF = "SD-DNF"
    TYPE_SD_INV_F = "SD-INV-F"
    TYPE_SD_PAY_F = "SD-PAY-F"
    TYPE_SD_DNC = "SD-DNC"
    TYPE_SD_INV_C = "SD-INV-C"
    TYPE_SD_PAY_C = "SD-PAY-C"
    TYPE_SD_EXP = "SD-EXP"
    TYPE_SD_CORR = "SD-CORR"
    TYPE_AUTRE = "AUTRE"

    TYPE_CHOICES = [
        (TYPE_SD_DNF, "BL Fournisseur signé"),
        (TYPE_SD_INV_F, "Facture fournisseur originale"),
        (TYPE_SD_PAY_F, "Justificatif paiement fournisseur"),
        (TYPE_SD_DNC, "BL Client signé"),
        (TYPE_SD_INV_C, "Facture client émise"),
        (TYPE_SD_PAY_C, "Justificatif encaissement client"),
        (TYPE_SD_EXP, "Justificatif dépense"),
        (TYPE_SD_CORR, "Document de correction"),
        (TYPE_AUTRE, "Autre"),
    ]

    # --- Generic link to the owning record (DN, facture, paiement, ...) ---
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="pieces_jointes",
        verbose_name="Type d'entité",
    )
    object_id = models.PositiveIntegerField(verbose_name="ID entité")
    content_object = GenericForeignKey("content_type", "object_id")

    fichier = models.FileField(
        upload_to="pieces_jointes/%Y/%m/",
        verbose_name="Fichier (PDF/JPG/PNG)",
    )
    type_document = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_AUTRE,
        verbose_name="Type de document",
    )
    description = models.CharField(max_length=200, blank=True, verbose_name="Description")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pieces_jointes_ajoutees",
        verbose_name="Ajouté par",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date d'ajout")

    class Meta:
        verbose_name = "Pièce jointe"
        verbose_name_plural = "Pièces jointes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.get_type_document_display()} — {self.content_object} ({self.created_at:%Y-%m-%d})"


# ---------------------------------------------------------------------------
# ProductionSite (functional spec §25.2 — Production Sites / Branches)
# ---------------------------------------------------------------------------
#
# Deliberately narrower than a full multi-branch redesign: only production
# and the stock/documents that feed it become site-aware (RawMaterialStock-
# Balance, FinishedProductStockBalance, StockMovement, StockAdjustment,
# ProductionOrder, SupplierDN, ClientDN). Suppliers, clients, invoicing,
# expenses in general, and payroll stay company-wide.
#
# Extended to mirror the avicole project's role-locked Branche switcher
# (§3.5): stock_prod/sales are locked to exactly one site
# (UserProfile.site, SITE_REQUIRED_ROLES) with no switcher; manager (and an
# unbound accountant/viewer) get a session-based active-site switcher
# (core.utils.get_active_site / core:site_switch) defaulting to "toutes les
# sites" (global view, read-only for creates — core.utils.
# require_site_context). See accounts.models.UserProfile and core.utils for
# the full resolution logic.



class ProductionSite(models.Model):
    """A physical production facility/branch (functional spec §25.2.1).

    `code` is embedded in the reference numbers of the four site-scoped
    document types (BL-F, BL-C, OP, ADJ — §25.2.4), e.g. `OP-EST-2026-0142`,
    so numbering never collides between sites. A single-facility factory
    only ever needs one seeded site ("Site Principal" / MAIN) and never
    sees the added complexity in practice.
    """

    name = models.CharField(max_length=150, verbose_name="Nom du site")
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Code",
        help_text=(
            "Code court et unique, intégré aux références de documents "
            "(ex : MAIN, EST, OUEST)."
        ),
    )
    address = models.TextField(blank=True, verbose_name="Adresse")
    contact = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_sites_en_charge",
        verbose_name="Contact du site",
        help_text="Magasinier, Responsable Production ou Administrateur référent pour ce site.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Site de production"
        verbose_name_plural = "Sites de production"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)
