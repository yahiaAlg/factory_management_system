from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal


class Supplier(models.Model):
    """Supplier directory.

    SPEC S2: all required fields present — code, raison_sociale,
    forme_juridique, nif, nis, rc, ai, address, wilaya, phone, email,
    contact_person, payment_terms, currency (DZD/EUR/USD), is_active.
    """

    CURRENCY_CHOICES = [
        ("DZD", "Dinar algérien"),
        ("EUR", "Euro"),
        ("USD", "Dollar américain"),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="Code fournisseur")
    raison_sociale = models.CharField(max_length=200, verbose_name="Raison sociale")
    forme_juridique = models.CharField(
        max_length=100, blank=True, verbose_name="Forme juridique"
    )

    nif = models.CharField(max_length=20, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=20, blank=True, verbose_name="NIS")
    rc = models.CharField(max_length=20, blank=True, verbose_name="RC")
    ai = models.CharField(max_length=20, blank=True, verbose_name="AI")

    address = models.TextField(verbose_name="Adresse")
    wilaya = models.CharField(max_length=100, blank=True, verbose_name="Wilaya")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    fax = models.CharField(max_length=20, blank=True, verbose_name="Fax")
    email = models.EmailField(blank=True, verbose_name="Email")

    contact_person = models.CharField(
        max_length=200, blank=True, verbose_name="Personne de contact"
    )
    contact_phone = models.CharField(
        max_length=20, blank=True, verbose_name="Téléphone contact"
    )

    payment_terms = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0)],
        verbose_name="Délai de paiement (jours)",
    )
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="DZD", verbose_name="Devise"
    )

    bank_name = models.CharField(
        max_length=200, blank=True, verbose_name="Nom de la banque"
    )
    bank_account = models.CharField(
        max_length=50, blank=True, verbose_name="Compte bancaire"
    )
    rib = models.CharField(max_length=23, blank=True, verbose_name="RIB")

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ["raison_sociale"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["raison_sociale"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.raison_sociale}"

    def get_outstanding_balance(self):
        from supplier_ops.models import SupplierInvoice

        result = SupplierInvoice.objects.filter(
            supplier=self,
            status__in=["verified", "unpaid", "partially_paid"],
        ).aggregate(total=models.Sum("balance_due"))["total"]
        return result or Decimal("0.00")

    def get_total_purchases_amount(self, year=None):
        from supplier_ops.models import SupplierInvoice

        qs = SupplierInvoice.objects.filter(supplier=self)
        if year:
            qs = qs.filter(invoice_date__year=year)
        return qs.aggregate(total=models.Sum("total_ttc"))["total"] or Decimal("0.00")

    def has_fiscal_identifier(self):
        return bool(self.nif or self.nis or self.rc or self.ai)

    def get_payment_terms_display_verbose(self):
        if self.payment_terms == 0:
            return "Comptant"
        return f"{self.payment_terms} jours"

    def get_recent_deliveries(self, limit=10):
        from supplier_ops.models import SupplierDN

        return SupplierDN.objects.filter(supplier=self).order_by("-delivery_date")[
            :limit
        ]

    def get_recent_invoices(self, limit=10):
        from supplier_ops.models import SupplierInvoice

        return SupplierInvoice.objects.filter(supplier=self).order_by("-invoice_date")[
            :limit
        ]
