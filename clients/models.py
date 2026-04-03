# clients/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class Client(models.Model):
    """Client directory.

    SPEC S2: required fields — code, raison_sociale, forme_juridique,
    nif, nis, rc, ai, address, wilaya, phone, email, payment_terms,
    credit_status (active/suspended/blocked), max_discount_pct.
    """

    CREDIT_STATUS_CHOICES = [
        ("active", "Actif"),
        ("suspended", "Suspendu"),
        ("blocked", "Bloqué"),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="Code client")
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
    credit_status = models.CharField(
        max_length=20,
        choices=CREDIT_STATUS_CHOICES,
        default="active",
        verbose_name="Statut crédit",
    )
    max_discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Remise maximale autorisée (%)",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ["raison_sociale"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["raison_sociale"]),
            models.Index(fields=["credit_status"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.raison_sociale}"

    def get_outstanding_balance(self):
        from sales.models import ClientInvoice

        result = ClientInvoice.objects.filter(
            client=self, status__in=["issued", "partially_paid"]
        ).aggregate(total=models.Sum("balance_due"))["total"]
        return result or Decimal("0.00")

    def get_total_sales_amount(self, year=None):
        from sales.models import ClientInvoice

        qs = ClientInvoice.objects.filter(client=self)
        if year:
            qs = qs.filter(invoice_date__year=year)
        return qs.aggregate(total=models.Sum("total_ttc"))["total"] or Decimal("0.00")

    def has_fiscal_identifier(self):
        return bool(self.nif or self.nis or self.rc or self.ai)

    def can_place_order(self):
        return self.credit_status in ["active", "suspended"] and self.is_active

    def get_recent_deliveries(self, limit=10):
        from sales.models import ClientDN

        return ClientDN.objects.filter(client=self).order_by("-delivery_date")[:limit]

    def get_recent_invoices(self, limit=10):
        from sales.models import ClientInvoice

        return ClientInvoice.objects.filter(client=self).order_by("-invoice_date")[
            :limit
        ]
