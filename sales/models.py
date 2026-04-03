from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal


class ClientDN(models.Model):
    """Client Delivery Note (Bon de Livraison Client)"""

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("validated", "Validé"),
        ("delivered", "Livré"),
        ("invoiced", "Facturé"),
        ("cancelled", "Annulé"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence BL"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, verbose_name="Client"
    )
    delivery_date = models.DateField(verbose_name="Date de livraison")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Statut"
    )

    # Financial amounts
    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
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

    # Validation tracking
    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_client_dns",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")

    # Invoice linking
    linked_invoice = models.ForeignKey(
        "ClientInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Facture liée",
    )

    # Metadata
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
        if not self.reference:
            # Generate reference: BL-C-YYYY-NNNN
            from core.models import DocumentSequence

            year = (
                self.delivery_date.year if self.delivery_date else timezone.now().year
            )
            self.reference = DocumentSequence.get_next_reference("BL-C", year)

        # Calculate total amount
        if self.pk:
            subtotal = sum(line.line_amount for line in self.lines.all())
            discount_amount = subtotal * (self.discount_pct / 100)
            self.total_ht = subtotal - discount_amount

        super().save(*args, **kwargs)

    def validate(self, user):
        """Validate the client delivery note"""
        if self.status != "draft":
            raise ValueError("Seuls les BL en brouillon peuvent être validés")

        # Check client credit status
        if self.client.credit_status == "blocked":
            raise ValueError("Client bloqué - impossible de valider le BL")

        # Check stock availability for all lines
        insufficient_stock = []
        for line in self.lines.all():
            from stock.models import FinishedProductStockBalance

            try:
                balance = FinishedProductStockBalance.objects.get(
                    finished_product=line.finished_product
                )
                if balance.quantity < line.quantity_delivered:
                    insufficient_stock.append(
                        {
                            "product": line.finished_product,
                            "required": line.quantity_delivered,
                            "available": balance.quantity,
                        }
                    )
            except FinishedProductStockBalance.DoesNotExist:
                insufficient_stock.append(
                    {
                        "product": line.finished_product,
                        "required": line.quantity_delivered,
                        "available": Decimal("0.000"),
                    }
                )

        if insufficient_stock:
            raise ValueError("Stock insuffisant pour certains produits")

        self.status = "validated"
        self.validated_by = user
        self.validated_at = timezone.now()
        self.save()

        # Update stock balances via signals
        from django.db.models.signals import post_save

        post_save.send(sender=self.__class__, instance=self, created=False)

    def can_be_invoiced(self):
        """Check if DN can be invoiced"""
        return self.status == "validated" and not self.linked_invoice

    def get_net_amount(self):
        """Get net amount after discount"""
        discount_amount = self.total_ht * (self.discount_pct / 100)
        return self.total_ht - discount_amount


class ClientDNLine(models.Model):
    """Line item in a Client Delivery Note"""

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
    line_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant ligne",
    )

    class Meta:
        verbose_name = "Ligne BL Client"
        verbose_name_plural = "Lignes BL Client"
        unique_together = ["client_dn", "finished_product"]

    def save(self, *args, **kwargs):
        # Calculate line amount
        self.line_amount = self.quantity_delivered * self.selling_unit_price_ht
        super().save(*args, **kwargs)

        # Update DN total
        if self.client_dn_id:
            self.client_dn.save()

    def __str__(self):
        return f"{self.client_dn.reference} - {self.finished_product.designation}"


class ClientInvoice(models.Model):
    """Client Invoice (Facture Client)"""

    STATUS_CHOICES = [
        ("issued", "Émise"),
        ("partially_paid", "Partiellement payée"),
        ("paid", "Payée"),
        ("in_dispute", "En litige"),
        ("cancelled", "Annulée"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence facture"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, verbose_name="Client"
    )
    invoice_date = models.DateField(verbose_name="Date facture")
    due_date = models.DateField(verbose_name="Date d'échéance")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="issued", verbose_name="Statut"
    )

    # Financial amounts
    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
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
    net_ht = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Net HT"
    )
    vat_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant TVA",
    )
    total_ttc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total TTC",
    )
    amount_collected = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant encaissé",
    )
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Solde dû",
    )

    # Linked delivery notes
    linked_dns = models.ManyToManyField(
        ClientDN, through="ClientInvoiceDNLink", verbose_name="BL liés"
    )

    # Metadata
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
        if not self.reference:
            # Generate reference: FC-YYYY-NNNN
            from core.models import DocumentSequence

            year = self.invoice_date.year if self.invoice_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("FC", year)

        # Calculate amounts
        if self.pk:
            # Calculate from linked DNs
            self.total_ht = sum(dn.total_ht for dn in self.linked_dns.all())

            # Apply discount
            discount_amount = self.total_ht * (self.discount_pct / 100)
            self.net_ht = self.total_ht - discount_amount

            # Calculate VAT
            from core.models import CompanyInformation

            try:
                company = CompanyInformation.objects.first()
                if company:
                    self.vat_amount = self.net_ht * company.vat_rate
            except:
                self.vat_amount = Decimal("0.00")

            self.total_ttc = self.net_ht + self.vat_amount

            # Calculate collected amount and balance
            self.amount_collected = sum(
                payment.amount for payment in self.payments.all()
            )
            self.balance_due = self.total_ttc - self.amount_collected

            # Update status based on payments
            if self.amount_collected >= self.total_ttc:
                self.status = "paid"
            elif self.amount_collected > 0:
                self.status = "partially_paid"
            elif self.status not in ["in_dispute", "cancelled"]:
                self.status = "issued"

        super().save(*args, **kwargs)

    def is_overdue(self):
        """Check if invoice is overdue"""
        return self.due_date < timezone.now().date() and self.balance_due > 0

    def days_overdue(self):
        """Get number of days overdue"""
        if self.is_overdue():
            return (timezone.now().date() - self.due_date).days
        return 0


class ClientInvoiceDNLink(models.Model):
    """Many-to-many relationship between Client Invoices and Delivery Notes"""

    client_invoice = models.ForeignKey(ClientInvoice, on_delete=models.CASCADE)
    client_dn = models.ForeignKey(ClientDN, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["client_invoice", "client_dn"]


class ClientPayment(models.Model):
    """Payment received from a client"""

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
        ("card", "Carte bancaire"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence encaissement"
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

    # Metadata
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
            # Generate reference: PAY-C-YYYY-NNNN
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("PAY-C", year)

        super().save(*args, **kwargs)

        # Update invoice amounts
        if self.client_invoice_id:
            self.client_invoice.save()
