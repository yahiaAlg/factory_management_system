# sales/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


class ClientDN(models.Model):
    """Client Delivery Note (Bon de Livraison Client).

    SPEC BR-CDN-01: validation blocked if client.credit_status == 'blocked'.
    SPEC BR-CDN-02: validation blocked (atomic) if any line qty > FG stock.
    FG stock deductions happen ONLY on validation via post_save signal.
    """

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("validated", "Validé"),
        ("delivered", "Livré"),
        ("invoiced", "Facturé"),
        ("cancelled", "Annulé"),
    ]

    VALID_TRANSITIONS = {
        "draft": ["validated", "cancelled"],
        "validated": ["delivered", "cancelled"],
        "delivered": ["invoiced", "cancelled"],
        "invoiced": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence BL", editable=False
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, verbose_name="Client"
    )
    delivery_date = models.DateField(verbose_name="Date de livraison")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Statut"
    )

    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
        editable=False,
    )
    discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Remise (%)",
    )
    remarks = models.TextField(blank=True, verbose_name="Observations")

    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_client_dns",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")

    linked_invoice = models.ForeignKey(
        "ClientInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Facture liée",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "BL Client"
        verbose_name_plural = "BL Clients"
        ordering = ["-delivery_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["client", "delivery_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.code}"

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.delivery_date.year
                    if self.delivery_date
                    else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("BL-C", year)
        else:
            orig = ClientDN.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError("La référence d'un BL client est immuable.")

        if self.pk:
            subtotal = sum(line.line_amount for line in self.lines.all())
            self.total_ht = subtotal * (1 - self.discount_pct / 100)

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    def validate(self, user):
        """
        draft → validated.

        BR-CDN-01: hard error if client blocked.
        BR-CDN-02: atomic — all lines must have sufficient FG stock.
        Signal client_dn_post_save handles FG stock deductions (spec S7).
        """
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if "validated" not in allowed:
            raise ValidationError(
                f"Transition invalide depuis le statut « {self.status} »."
            )

        # BR-CDN-01
        if self.client.credit_status == "blocked":
            raise ValidationError(
                "Client bloqué — impossible de valider le BL (BR-CDN-01)."
            )

        # BR-CDN-02
        from stock.models import FinishedProductStockBalance

        insufficient = []
        for line in self.lines.all():
            try:
                balance = FinishedProductStockBalance.objects.get(
                    finished_product=line.finished_product
                )
                available = balance.quantity
            except FinishedProductStockBalance.DoesNotExist:
                available = Decimal("0.000")
            if available < line.quantity_delivered:
                insufficient.append(
                    {
                        "product": line.finished_product,
                        "required": line.quantity_delivered,
                        "available": available,
                    }
                )

        if insufficient:
            raise ValidationError(
                "Stock insuffisant pour certains produits — validation impossible (BR-CDN-02)."
            )

        self.status = "validated"
        self.validated_by = user
        self.validated_at = timezone.now()
        self.save()
        # Signal sales.signals.client_dn_post_save will deduct FG stock (spec S7).

    def can_be_invoiced(self):
        return self.status == "validated" and not self.linked_invoice

    @property
    def net_amount(self):
        return self.total_ht  # discount already applied in save()


class ClientDNLine(models.Model):
    """Line item in a Client Delivery Note.

    SPEC S3: line_amount is a @property — never stored or form-editable.
    """

    client_dn = models.ForeignKey(
        ClientDN, on_delete=models.CASCADE, related_name="lines"
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct", on_delete=models.PROTECT, verbose_name="Produit fini"
    )
    quantity_delivered = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité livrée",
    )
    unit_of_measure = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, verbose_name="Unité"
    )
    selling_unit_price_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix unitaire HT",
    )

    class Meta:
        verbose_name = "Ligne BL Client"
        verbose_name_plural = "Lignes BL Client"
        unique_together = ["client_dn", "finished_product"]

    def __str__(self):
        return f"{self.client_dn.reference} - {self.finished_product.designation}"

    @property
    def line_amount(self):
        """SPEC S3: computed property — never stored."""
        return self.quantity_delivered * self.selling_unit_price_ht

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.client_dn_id:
            self.client_dn.save()  # Refresh total_ht cache


class ClientInvoice(models.Model):
    """Client Invoice (Facture Client).

    SPEC S2:
      - due_date auto-calculated as invoice_date + client.payment_terms days;
        manually overridable.
      - Cannot be cancelled if any payment exists.
      - balance_due computed by signal after ClientPayment save (spec S7).
    """

    STATUS_CHOICES = [
        ("issued", "Émise"),
        ("partially_paid", "Partiellement payée"),
        ("paid", "Payée"),
        ("in_dispute", "En litige"),
        ("cancelled", "Annulée"),
    ]

    VALID_TRANSITIONS = {
        "issued": ["partially_paid", "paid", "in_dispute", "cancelled"],
        "partially_paid": ["paid", "in_dispute"],
        "in_dispute": ["issued"],  # Manager only — enforced in view
        "paid": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence facture", editable=False
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, verbose_name="Client"
    )
    invoice_date = models.DateField(verbose_name="Date facture")
    # SPEC: auto-calculated; manually overridable
    due_date = models.DateField(verbose_name="Date d'échéance")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="issued", verbose_name="Statut"
    )

    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
        editable=False,
    )
    discount_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Remise (%)",
    )
    vat_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant TVA",
        editable=False,
    )
    total_ttc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total TTC",
        editable=False,
    )

    # SPEC S3: signal-updated, never form-editable
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Solde dû",
        editable=False,
    )

    linked_dns = models.ManyToManyField(
        ClientDN, through="ClientInvoiceDNLink", verbose_name="BL liés"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Facture Client"
        verbose_name_plural = "Factures Client"
        ordering = ["-invoice_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["client", "invoice_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.code}"

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.invoice_date.year if self.invoice_date else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("FC", year)
            # SPEC: auto-calculate due_date if not supplied
            if not self.due_date and self.invoice_date:
                self.due_date = self.invoice_date + timedelta(
                    days=self.client.payment_terms
                )
        else:
            orig = ClientInvoice.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError("La référence d'une facture client est immuable.")

        if self.pk:
            self._recompute_totals()

        super().save(*args, **kwargs)

    # SPEC S2: cannot cancel if payments exist
    def clean(self):
        if self.pk:
            orig = ClientInvoice.objects.get(pk=self.pk)
            if orig.status != "cancelled" and self.status == "cancelled":
                if self.payments.exists():
                    raise ValidationError(
                        "Impossible d'annuler une facture qui a des paiements enregistrés."
                    )

    def _recompute_totals(self):
        self.total_ht = sum(dn.total_ht for dn in self.linked_dns.all())
        discount_amount = self.total_ht * (self.discount_pct / 100)
        net_ht = self.total_ht - discount_amount
        from core.models import CompanyInformation

        try:
            company = CompanyInformation.objects.first()
            vat_rate = company.vat_rate if company else Decimal("0.19")
        except Exception:
            vat_rate = Decimal("0.19")
        self.vat_amount = net_ht * vat_rate
        self.total_ttc = net_ht + self.vat_amount
        # balance_due updated by ClientPayment post_save signal (spec S7)

    @property
    def net_ht(self):
        """SPEC S3: computed property."""
        return self.total_ht * (1 - self.discount_pct / 100)

    def recompute_balance_due(self):
        """Called by sales.signals after ClientPayment save (spec S7)."""
        total_collected = sum(p.amount for p in self.payments.all())
        self.balance_due = self.total_ttc - total_collected
        if self.balance_due <= 0:
            self.status = "paid"
        elif total_collected > 0 and self.status not in ("in_dispute", "cancelled"):
            self.status = "partially_paid"
        ClientInvoice.objects.filter(pk=self.pk).update(
            balance_due=self.balance_due, status=self.status
        )

    def is_overdue(self):
        return self.due_date < timezone.now().date() and self.balance_due > 0

    def days_overdue(self):
        if self.is_overdue():
            return (timezone.now().date() - self.due_date).days
        return 0


class ClientInvoiceDNLink(models.Model):
    client_invoice = models.ForeignKey(ClientInvoice, on_delete=models.CASCADE)
    client_dn = models.ForeignKey(ClientDN, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["client_invoice", "client_dn"]


class ClientPayment(models.Model):
    """Payment received from a client."""

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
        ("card", "Carte bancaire"),
    ]

    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Référence encaissement",
        editable=False,
    )
    client_invoice = models.ForeignKey(
        ClientInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Facture",
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, verbose_name="Client"
    )
    payment_date = models.DateField(verbose_name="Date d'encaissement")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant",
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="Mode de paiement"
    )
    bank_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence bancaire"
    )

    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Enregistré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Encaissement Client"
        verbose_name_plural = "Encaissements Client"
        ordering = ["-payment_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["client", "payment_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.code} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.reference:
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("PAY-C", year)
        super().save(*args, **kwargs)
        # Signal sales.signals.client_payment_post_save calls
        # invoice.recompute_balance_due() (spec S7).
