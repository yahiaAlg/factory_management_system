from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal


class Supplier(models.Model):
    """Supplier directory"""

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

    # Algerian fiscal identifiers
    nif = models.CharField(max_length=20, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=20, blank=True, verbose_name="NIS")
    rc = models.CharField(max_length=20, blank=True, verbose_name="RC")
    ai = models.CharField(max_length=20, blank=True, verbose_name="AI")

    # Contact information
    address = models.TextField(verbose_name="Adresse")
    wilaya = models.CharField(max_length=100, blank=True, verbose_name="Wilaya")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    fax = models.CharField(max_length=20, blank=True, verbose_name="Fax")
    email = models.EmailField(blank=True, verbose_name="Email")

    # Contact person
    contact_person = models.CharField(
        max_length=200, blank=True, verbose_name="Personne de contact"
    )
    contact_phone = models.CharField(
        max_length=20, blank=True, verbose_name="Téléphone contact"
    )

    # Commercial terms
    payment_terms = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0)],
        verbose_name="Délai de paiement (jours)",
        help_text="Délai de paiement standard en jours",
    )
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="DZD", verbose_name="Devise"
    )

    # Bank details (for payments)
    bank_name = models.CharField(
        max_length=200, blank=True, verbose_name="Nom de la banque"
    )
    bank_account = models.CharField(
        max_length=50, blank=True, verbose_name="Compte bancaire"
    )
    rib = models.CharField(max_length=23, blank=True, verbose_name="RIB")

    # Status and metadata
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Notes
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
        """Get total outstanding balance for this supplier"""
        from supplier_ops.models import SupplierInvoice

        outstanding = SupplierInvoice.objects.filter(
            supplier=self, status__in=["verified", "unpaid", "partially_paid"]
        ).aggregate(total=models.Sum("balance_due"))["total"]

        return outstanding or Decimal("0.00")

    def get_total_purchases_amount(self, year=None):
        """Get total purchases amount for a given year"""
        from supplier_ops.models import SupplierInvoice

        invoices = SupplierInvoice.objects.filter(supplier=self)

        if year:
            invoices = invoices.filter(invoice_date__year=year)

        total = invoices.aggregate(total=models.Sum("total_ttc"))["total"]
        return total or Decimal("0.00")

    def get_payment_terms_display_verbose(self):
        """Get verbose payment terms display"""
        if self.payment_terms == 0:
            return "Comptant"
        elif self.payment_terms == 30:
            return "30 jours"
        elif self.payment_terms == 60:
            return "60 jours"
        elif self.payment_terms == 90:
            return "90 jours"
        else:
            return f"{self.payment_terms} jours"

    def has_fiscal_identifier(self):
        """Check if supplier has at least one fiscal identifier"""
        return bool(self.nif or self.nis or self.rc or self.ai)

    def get_recent_deliveries(self, limit=10):
        """Get recent delivery notes for this supplier"""
        from supplier_ops.models import SupplierDN

        return SupplierDN.objects.filter(supplier=self).order_by("-delivery_date")[
            :limit
        ]

    def get_recent_invoices(self, limit=10):
        """Get recent invoices for this supplier"""
        from supplier_ops.models import SupplierInvoice

        return SupplierInvoice.objects.filter(supplier=self).order_by("-invoice_date")[
            :limit
        ]
