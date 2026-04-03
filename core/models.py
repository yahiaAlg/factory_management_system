# core/models.py
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
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

    prefix = models.CharField(max_length=10, verbose_name="Préfixe")
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
    def get_next_reference(cls, prefix, year):
        """
        Atomically increment and return the next reference string.

        For year-less sequences (RM, PF, F) pass year=0.
        For yearly sequences pass the 4-digit year.
        """
        with transaction.atomic():
            sequence, _ = cls.objects.select_for_update().get_or_create(
                prefix=prefix,
                current_year=year,
                defaults={
                    "current_number": 0,
                    "description": f"Séquence pour {prefix}",
                },
            )
            sequence.current_number += 1
            sequence.save(update_fields=["current_number"])

        if year == 0:
            return f"{prefix}-{sequence.current_number:03d}"
        return f"{prefix}-{year}-{sequence.current_number:04d}"
