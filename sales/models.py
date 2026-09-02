# sales/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from core.models import PieceJointe


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
    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="client_dns",
        verbose_name="Site expéditeur",
        help_text="Site dont le stock de produits finis est débité à la validation (fonc. spec §25.2.3).",
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

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="client_dn")

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
                site_code = self.site.code if self.site_id else None
                self.reference = DocumentSequence.get_next_reference(
                    "BL-C", year, site_code=site_code
                )
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
        BR-CDN-02: atomic — all lines must have sufficient FG stock AT
        THIS DN's SITE (functional spec §25.2.3). A bare
        FinishedProductStockBalance.objects.get(finished_product=...) with
        no site filter would silently let confirming an order at Site B
        consume Site A's stock — exactly the failure mode the spec warns
        against — so the lookup below is always scoped to self.site.
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
                    site=self.site, finished_product=line.finished_product
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

    PAYMENT_METHOD_CHOICES = [
        ("espece", "Espèces"),
        ("virement", "Virement bancaire"),
        ("cheque", "Chèque"),
        ("ccp", "CCP"),
    ]

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="virement",
        verbose_name="Mode de règlement",
    )

    # Timbre fiscal — only non-zero when payment_method == 'espece'
    # Rates: 300 < (HT+TVA) ≤ 30 000 → 1% | ≤ 100 000 → 1.5% | > 100 000 → 2%
    timbre_fiscal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Timbre fiscal",
        editable=False,
    )

    # total_net = total_ttc + timbre_fiscal (grand total payable)
    total_net = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Net à payer",
        editable=False,
    )

    linked_dns = models.ManyToManyField(
        ClientDN, through="ClientInvoiceDNLink", verbose_name="BL liés"
    )

    # §23.5 — Opening Balance (mirrors SupplierInvoice.is_opening_balance):
    # flags an invoice created via create_client_opening_balance() instead
    # of from DNs. _recompute_totals() is guarded below so its manually
    # entered amount survives later saves (e.g. a status transition).
    is_opening_balance = models.BooleanField(
        default=False, verbose_name="Solde d'ouverture (§23 planifié)"
    )
    # §23.5 — required explanation for an opening-balance invoice, stored
    # here for audit; also usable as free-text notes on any other invoice.
    notes = models.TextField(blank=True, verbose_name="Notes")

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="client_invoice")

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

        # §23.5: an opening-balance invoice has no linked DNs — never
        # recompute its manually-entered totals from an empty DN set.
        if self.pk and not self.is_opening_balance:
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

        # Timbre fiscal — only applies for espèces payment
        self.timbre_fiscal = Decimal("0.00")
        if self.payment_method == "espece":
            base = self.total_ttc  # HT net + TVA = TTC
            if base > Decimal("100000"):
                self.timbre_fiscal = (base * Decimal("0.02")).quantize(Decimal("0.01"))
            elif base > Decimal("30000"):
                self.timbre_fiscal = (base * Decimal("0.015")).quantize(Decimal("0.01"))
            elif base > Decimal("300"):
                self.timbre_fiscal = (base * Decimal("0.01")).quantize(Decimal("0.01"))

        self.total_net = self.total_ttc + self.timbre_fiscal

        # FIX: initialize balance_due — same bug as SupplierInvoice
        total_collected = (
            sum(p.amount for p in self.payments.all()) if self.pk else Decimal("0.00")
        )
        self.balance_due = self.total_net - total_collected

    @property
    def discount_amount(self):
        return self.total_ht * (self.discount_pct / 100)

    @property
    def net_ht(self):
        """SPEC S3: computed property."""
        return self.total_ht * (1 - self.discount_pct / 100)

    def recompute_balance_due(self):
        """Called by sales.signals after ClientPayment save (spec S7)."""
        total_collected = sum(p.amount for p in self.payments.all())
        self.balance_due = self.total_net - total_collected
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
        # §23.4 — synthetic method used exclusively by
        # utils.consume_client_advances_fifo() when an advance is drawn down
        # against a new invoice. Excluded from the statement of account's
        # crédit lines (§23.6) — mirrors SupplierPayment's "advance" method.
        ("advance", "Avance consommée (§23 planifié)"),
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

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="client_payment")

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


class ClientAccountPayment(models.Model):
    """Client-level account settlement payment (FIFO invoice clearing).

    Instead of paying a specific invoice, the accountant records a payment
    against the client account. The settle_fifo() method then clears invoices
    oldest-first (by due_date, then invoice_date) until the amount is exhausted,
    creating one ClientPayment record per invoice touched.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
        ("card", "Carte bancaire"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence règlement", editable=False
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="account_payments",
        verbose_name="Client",
    )
    payment_date = models.DateField(verbose_name="Date d'encaissement")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant encaissé",
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="Mode de paiement"
    )
    bank_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence bancaire"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Enregistré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    pieces_jointes = GenericRelation(
        PieceJointe, related_query_name="client_account_payment"
    )

    class Meta:
        verbose_name = "Règlement compte client"
        verbose_name_plural = "Règlements compte client"
        ordering = ["-payment_date", "-reference"]
        indexes = [
            models.Index(fields=["client", "payment_date"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.client.code} - {self.amount} DA"

    def save(self, *args, **kwargs):
        if not self.reference:
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("RGL-C", year)
        super().save(*args, **kwargs)

    def settle_fifo(self):
        """Apply self.amount to the client's open invoices oldest-first.

        Fetches all invoices with balance_due > 0 and status not in_dispute/cancelled,
        ordered by due_date ASC then invoice_date ASC (FIFO).
        Creates one ClientPayment record per invoice touched, reducing
        balance_due proportionally. Updates each invoice's status via
        recompute_balance_due().

        Returns a list of dicts: [{"invoice": <ClientInvoice>, "applied": <Decimal>}, ...]
        """
        open_invoices = (
            ClientInvoice.objects.filter(
                client=self.client,
                balance_due__gt=0,
            )
            .exclude(status__in=["in_dispute", "cancelled", "paid"])
            .order_by("due_date", "invoice_date")
            .select_for_update()
        )

        remaining = self.amount
        applied = []

        for invoice in open_invoices:
            if remaining <= 0:
                break

            to_apply = min(remaining, invoice.balance_due)

            payment = ClientPayment(
                client_invoice=invoice,
                client=self.client,
                payment_date=self.payment_date,
                amount=to_apply,
                payment_method=self.payment_method,
                bank_reference=self.bank_reference,
                recorded_by=self.recorded_by,
            )
            payment.save()

            invoice.refresh_from_db()
            invoice.recompute_balance_due()

            applied.append({"invoice": invoice, "applied": to_apply})
            remaining -= to_apply

        # §23.4 — mirrors SupplierAccountPayment.settle_fifo(): any leftover
        # amount once every open invoice in scope is cleared (including the
        # full settlement when the client had no open invoices at all — a
        # deposit paid before their next delivery is even invoiced) becomes
        # a standing ClientAdvance rather than being rejected. Unlike the
        # supplier side there was no existing numbered rule to supersede
        # here — this simply adds the missing overpayment handling.
        if remaining > 0:
            ClientAdvance.objects.create(
                client=self.client,
                settlement=self,
                origin=ClientAdvance.ORIGIN_SETTLEMENT_SURPLUS,
                amount=remaining,
                remaining_amount=remaining,
                date=self.payment_date,
                recorded_by=self.recorded_by,
                notes=(
                    f"Surplus automatique du règlement {self.reference} du "
                    f"{self.payment_date} — {self.amount} DA au total."
                ),
            )

        return applied


class ClientAdvance(models.Model):
    """Client Advance (§23.4) — mirrors SupplierAdvance exactly, on the
    receivables side: a credit balance held for a specific client — a
    deposit or overpayment not yet matched to an invoice."""

    ORIGIN_SETTLEMENT_SURPLUS = "settlement_surplus"
    ORIGIN_DIRECT_ENTRY = "direct_entry"
    ORIGIN_CHOICES = [
        (ORIGIN_SETTLEMENT_SURPLUS, "Surplus de règlement"),
        (ORIGIN_DIRECT_ENTRY, "Saisie directe"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
        ("card", "Carte bancaire"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence avance", editable=False
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="advances",
        verbose_name="Client",
    )
    settlement = models.OneToOneField(
        ClientAccountPayment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advance",
        verbose_name="Règlement source",
        help_text="Renseigné uniquement quand origin = Surplus de règlement (§23.4).",
    )
    origin = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_DIRECT_ENTRY,
        verbose_name="Origine",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant (DA)",
    )
    remaining_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Montant restant (DA)",
    )
    date = models.DateField(verbose_name="Date")
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="cash",
        verbose_name="Mode de paiement",
        help_text="Utilisé seulement pour une saisie directe (origin = Saisie directe).",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Enregistré par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="client_advance")

    class Meta:
        verbose_name = "Avance Client (§23 planifié)"
        verbose_name_plural = "Avances Client (§23 planifié)"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["client", "date"]),
            models.Index(fields=["remaining_amount"]),
        ]

    def __str__(self):
        status = "utilisée" if self.remaining_amount <= 0 else "disponible"
        return f"Avance {self.client.code} — {self.amount} DA [{status}]"

    def save(self, *args, **kwargs):
        if self.pk is None and not self.reference:
            from core.models import DocumentSequence

            year = self.date.year if self.date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("AV-C", year)
        if self.pk is None and (self.remaining_amount is None or self.remaining_amount == 0):
            self.remaining_amount = self.amount
        super().save(*args, **kwargs)

    @property
    def is_fully_used(self):
        return self.remaining_amount <= 0


class ClientAdvanceAllocation(models.Model):
    """Immutable line: portion of a ClientAdvance consumed by one
    ClientInvoice (§23.4), mirroring SupplierAdvanceAllocation. Created
    exclusively by utils.consume_client_advances_fifo()."""

    advance = models.ForeignKey(
        ClientAdvance, on_delete=models.PROTECT, related_name="allocations"
    )
    invoice = models.ForeignKey(
        ClientInvoice, on_delete=models.PROTECT, related_name="advance_allocations"
    )
    amount_allocated = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Montant alloué (DA)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Allocation d'avance (§23 planifié)"
        verbose_name_plural = "Allocations d'avance (§23 planifié)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.advance.reference} → {self.invoice.reference} : {self.amount_allocated} DA"
