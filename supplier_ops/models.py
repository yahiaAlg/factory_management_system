# supplier_ops/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class SupplierDN(models.Model):
    """Supplier Delivery Note (Bon de Livraison Fournisseur).

    SPEC S2 / S8:
      - reference: auto-generated BL-F-YYYY-NNNN, immutable after creation.
      - Stock movements created ONLY on validation, not on creation/save.
      - validate() must not call post_save.send() manually — signals handle it.
    """

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("pending", "En attente de validation"),
        ("validated", "Validé"),
        ("in_dispute", "En litige"),
        ("cancelled", "Annulé"),
    ]

    # Valid transitions per spec S6
    VALID_TRANSITIONS = {
        "draft": ["pending", "cancelled"],
        "pending": ["validated", "in_dispute", "cancelled"],
        "validated": ["in_dispute"],
        "in_dispute": ["pending"],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence BL", editable=False
    )
    external_reference = models.CharField(
        max_length=100, verbose_name="Référence fournisseur"
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    delivery_date = models.DateField(verbose_name="Date de livraison")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Statut"
    )

    # SPEC S3: total_amount_ht is a computed property — not stored as a user-editable field.
    # We keep it as a cached DB field updated only in save(), never from POST data.
    total_amount_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant total HT",
        editable=False,
    )

    remarks = models.TextField(blank=True, verbose_name="Observations")

    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_supplier_dns",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")

    linked_invoice = models.ForeignKey(
        "SupplierInvoice",
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
        verbose_name = "BL Fournisseur"
        verbose_name_plural = "BL Fournisseurs"
        ordering = ["-delivery_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "delivery_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code}"

    # ------------------------------------------------------------------
    # Reference generation & save
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.delivery_date.year
                    if self.delivery_date
                    else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("BL-F", year)
        else:
            # Block reference mutation
            orig = SupplierDN.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError("La référence d'un BL fournisseur est immuable.")

        # Recompute total from lines (never from form input)
        if self.pk:
            self.total_amount_ht = sum(line.line_amount for line in self.lines.all())

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Status transition
    # ------------------------------------------------------------------
    def transition_to(self, new_status, user):
        """Enforce valid status transitions (spec S6)."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Transition invalide : {self.status} → {new_status}."
            )
        self.status = new_status
        if new_status == "validated":
            self.validated_by = user
            self.validated_at = timezone.now()
        self.save()

    # ------------------------------------------------------------------
    # Business action: validate
    # ------------------------------------------------------------------
    def validate(self, user):
        """
        Validate the delivery note.

        SPEC BR-RM-05: stock movements are created by the
        supplier_dn_post_save signal in stock/signals.py, NOT here.
        Supporting document (SD-DNF) gate is enforced here.
        """
        if self.status != "pending":
            raise ValidationError(
                "Seuls les BL en attente de validation peuvent être validés."
            )

        # SPEC SupportingDocument gate: SD-DNF must be attached
        from expenses.models import SupportingDocument

        if not SupportingDocument.objects.filter(
            doc_type="SD-DNF",
            entity_type="supplierdn",
            entity_id=self.pk,
        ).exists():
            raise ValidationError(
                "Le BL fournisseur ne peut pas être validé sans justificatif signé (SD-DNF) attaché."
            )

        self.transition_to("validated", user)
        # Signal supplier_ops.signals.supplier_dn_post_save will handle stock movements.

    def can_be_linked_to_invoice(self):
        return self.status == "validated" and not self.linked_invoice


class SupplierDNLine(models.Model):
    """Line item in a Supplier Delivery Note.

    SPEC S3: line_amount is a @property (qty × price), never stored
    as a user-editable field.
    """

    supplier_dn = models.ForeignKey(
        SupplierDN, on_delete=models.CASCADE, related_name="lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    quantity_received = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité reçue",
    )
    unit_of_measure = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, verbose_name="Unité"
    )
    agreed_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix unitaire convenu",
    )

    class Meta:
        verbose_name = "Ligne BL Fournisseur"
        verbose_name_plural = "Lignes BL Fournisseur"
        unique_together = ["supplier_dn", "raw_material"]

    def __str__(self):
        return f"{self.supplier_dn.reference} - {self.raw_material.designation}"

    @property
    def line_amount(self):
        """SPEC S3: computed property — never stored, never from POST data."""
        return self.quantity_received * self.agreed_unit_price

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Refresh DN total cache
        if self.supplier_dn_id:
            SupplierDN.objects.filter(pk=self.supplier_dn_id).update(
                total_amount_ht=sum(l.line_amount for l in self.supplier_dn.lines.all())
            )


class SupplierInvoice(models.Model):
    """Supplier Invoice (Facture Fournisseur).

    SPEC S2:
      - reference: FF-YYYY-NNNN, immutable.
      - balance_due: computed by signal after SupplierPayment save (S7).
      - No payment if status == 'in_dispute' (BR-INV-04 — enforced in
        SupplierPayment.clean() below AND in views).
      - (supplier, external_reference) must be unique (BR-INV-08).
    """

    STATUS_CHOICES = [
        ("entered", "Saisie"),
        ("under_reconciliation", "En rapprochement"),
        ("verified", "Vérifiée"),
        ("in_dispute", "En litige"),
        ("unpaid", "Impayée"),
        ("partially_paid", "Partiellement payée"),
        ("paid", "Payée"),
        ("cancelled", "Annulée"),
    ]

    RECONCILIATION_CHOICES = [
        ("pending", "En attente"),
        ("compliant", "Conforme"),
        ("minor_discrepancy", "Écart mineur"),
        ("dispute", "Litige"),
    ]

    VALID_TRANSITIONS = {
        "entered": ["under_reconciliation", "cancelled"],
        "under_reconciliation": ["verified", "in_dispute"],
        "verified": ["unpaid"],
        "unpaid": ["partially_paid", "paid", "in_dispute"],
        "partially_paid": ["paid", "in_dispute"],
        "in_dispute": ["unpaid"],  # Manager only — enforced in view
        "paid": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence facture", editable=False
    )
    external_reference = models.CharField(
        max_length=100, verbose_name="Référence fournisseur"
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    invoice_date = models.DateField(verbose_name="Date facture")
    due_date = models.DateField(verbose_name="Date d'échéance")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="entered", verbose_name="Statut"
    )

    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
        editable=False,
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

    # SPEC S3: balance_due is signal-updated after SupplierPayment save — never form-editable.
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Solde dû",
        editable=False,
    )

    reconciliation_result = models.CharField(
        max_length=20,
        choices=RECONCILIATION_CHOICES,
        default="pending",
        verbose_name="Résultat rapprochement",
        editable=False,
    )
    # SPEC S3: reconciliation_delta is signal-updated after ReconciliationLine save — never form-editable.
    reconciliation_delta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Écart rapprochement",
        editable=False,
    )

    linked_dns = models.ManyToManyField(
        SupplierDN, through="SupplierInvoiceDNLink", verbose_name="BL liés"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Facture Fournisseur"
        verbose_name_plural = "Factures Fournisseur"
        ordering = ["-invoice_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "invoice_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code}"

    # ------------------------------------------------------------------
    # BR-INV-08: duplicate (supplier, external_reference) check
    # ------------------------------------------------------------------
    def clean(self):
        qs = SupplierInvoice.objects.filter(
            supplier=self.supplier,
            external_reference=self.external_reference,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                "Une facture avec cette référence fournisseur existe déjà pour ce fournisseur."
            )

    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.invoice_date.year if self.invoice_date else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("FF", year)
        else:
            orig = SupplierInvoice.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError(
                    "La référence d'une facture fournisseur est immuable."
                )

        if self.pk:
            self._recompute_totals()

        super().save(*args, **kwargs)

    def _recompute_totals(self):
        """Recompute HT / TVA / TTC from lines. Called only from save()."""
        self.total_ht = sum(line.line_amount for line in self.lines.all())
        from core.models import CompanyInformation

        try:
            company = CompanyInformation.objects.first()
            vat_rate = company.vat_rate if company else Decimal("0.19")
        except Exception:
            vat_rate = Decimal("0.19")
        self.vat_amount = self.total_ht * vat_rate
        self.total_ttc = self.total_ht + self.vat_amount
        # balance_due is recomputed by SupplierPayment post_save signal, not here.

    def recompute_balance_due(self):
        """Called by supplier_ops.signals after SupplierPayment save (spec S7)."""
        total_paid = sum(p.amount for p in self.payments.all())
        self.balance_due = self.total_ttc - total_paid
        # Update payment status
        if self.balance_due <= 0:
            self.status = "paid"
        elif total_paid > 0 and self.status not in ("in_dispute", "cancelled"):
            self.status = "partially_paid"
        SupplierInvoice.objects.filter(pk=self.pk).update(
            balance_due=self.balance_due, status=self.status
        )

    def transition_to(self, new_status, user):
        """Enforce valid status transitions (spec S6)."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Transition invalide : {self.status} → {new_status}."
            )
        self.status = new_status
        self.save()

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    def perform_reconciliation(self):
        """Line-by-line BL ↔ Invoice reconciliation.

        Fixed: original code had a double-addition bug in the
        dn_materials aggregation — corrected below.
        """
        if not self.linked_dns.exists():
            return

        self.reconciliation_lines.all().delete()

        invoice_lines = {line.raw_material_id: line for line in self.lines.all()}

        # Aggregate DN quantities per material (fix: avoid double-count)
        dn_materials: dict = {}
        for dn in self.linked_dns.all():
            for dn_line in dn.lines.all():
                mid = dn_line.raw_material_id
                if mid in dn_materials:
                    existing_qty = dn_materials[mid]["quantity"]
                    existing_price = dn_materials[mid]["price"]
                    new_qty = existing_qty + dn_line.quantity_received
                    # Weighted-average price
                    new_price = (
                        existing_qty * existing_price
                        + dn_line.quantity_received * dn_line.agreed_unit_price
                    ) / new_qty
                    dn_materials[mid] = {
                        "material": dn_line.raw_material,
                        "quantity": new_qty,
                        "price": new_price,
                    }
                else:
                    dn_materials[mid] = {
                        "material": dn_line.raw_material,
                        "quantity": dn_line.quantity_received,
                        "price": dn_line.agreed_unit_price,
                    }

        total_delta = Decimal("0.00")
        for mid in set(invoice_lines) | set(dn_materials):
            inv = invoice_lines.get(mid)
            dn = dn_materials.get(mid)

            qty_delivered = dn["quantity"] if dn else Decimal("0.000")
            price_agreed = dn["price"] if dn else Decimal("0.00")
            qty_invoiced = inv.quantity_invoiced if inv else Decimal("0.000")
            price_invoiced = inv.unit_price_invoiced if inv else Decimal("0.00")

            delta_qty = qty_invoiced - qty_delivered
            delta_price = price_invoiced - price_agreed
            delta_amount = (qty_invoiced * price_invoiced) - (
                qty_delivered * price_agreed
            )
            total_delta += delta_amount

            ReconciliationLine.objects.create(
                supplier_invoice=self,
                raw_material_id=mid,
                qty_delivered=qty_delivered,
                qty_invoiced=qty_invoiced,
                delta_qty=delta_qty,
                price_agreed=price_agreed,
                price_invoiced=price_invoiced,
                delta_price=delta_price,
                delta_amount=delta_amount,
            )

        # Update reconciliation result
        self.reconciliation_delta = total_delta
        from core.models import SystemParameter

        tolerance = SystemParameter.get_decimal_value(
            "reconciliation_tolerance_epsilon", Decimal("500.00")
        )
        dispute_limit = SystemParameter.get_decimal_value(
            "reconciliation_dispute_delta", Decimal("5000.00")
        )

        abs_delta = abs(total_delta)
        if abs_delta <= tolerance:
            self.reconciliation_result = "compliant"
            self.status = "verified"
        elif abs_delta <= dispute_limit:
            self.reconciliation_result = "minor_discrepancy"
            self.status = "under_reconciliation"
        else:
            self.reconciliation_result = "dispute"
            self.status = "in_dispute"

        SupplierInvoice.objects.filter(pk=self.pk).update(
            reconciliation_delta=self.reconciliation_delta,
            reconciliation_result=self.reconciliation_result,
            status=self.status,
        )

    def is_overdue(self):
        return self.due_date < timezone.now().date() and self.balance_due > 0


class SupplierInvoiceLine(models.Model):
    """Line item in a Supplier Invoice."""

    supplier_invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name="lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    quantity_invoiced = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité facturée",
    )
    unit_price_invoiced = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix unitaire facturé",
    )

    class Meta:
        verbose_name = "Ligne Facture Fournisseur"
        verbose_name_plural = "Lignes Facture Fournisseur"
        unique_together = ["supplier_invoice", "raw_material"]

    @property
    def line_amount(self):
        """SPEC S3: computed property."""
        return self.quantity_invoiced * self.unit_price_invoiced

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.supplier_invoice_id:
            self.supplier_invoice._recompute_totals()
            SupplierInvoice.objects.filter(pk=self.supplier_invoice_id).update(
                total_ht=self.supplier_invoice.total_ht,
                vat_amount=self.supplier_invoice.vat_amount,
                total_ttc=self.supplier_invoice.total_ttc,
            )

    def __str__(self):
        return f"{self.supplier_invoice.reference} - {self.designation}"


class SupplierInvoiceDNLink(models.Model):
    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE)
    supplier_dn = models.ForeignKey(SupplierDN, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["supplier_invoice", "supplier_dn"]


class ReconciliationLine(models.Model):
    """Reconciliation comparison line between DN and Invoice.

    SPEC S3: delta_qty, delta_price, delta_amount are computed — stored
    here after perform_reconciliation() runs, never user-editable.
    """

    supplier_invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name="reconciliation_lines"
    )
    raw_material = models.ForeignKey("catalog.RawMaterial", on_delete=models.PROTECT)

    qty_delivered = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"), editable=False
    )
    price_agreed = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    qty_invoiced = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"), editable=False
    )
    price_invoiced = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False
    )

    delta_qty = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000"), editable=False
    )
    delta_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    delta_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), editable=False
    )

    class Meta:
        verbose_name = "Ligne de rapprochement"
        verbose_name_plural = "Lignes de rapprochement"
        unique_together = ["supplier_invoice", "raw_material"]


class SupplierPayment(models.Model):
    """Payment made to a supplier.

    SPEC BR-INV-04: clean() blocks payment if invoice status == 'in_dispute'.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence paiement", editable=False
    )
    supplier_invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Facture",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    payment_date = models.DateField(verbose_name="Date de paiement")
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
        verbose_name = "Paiement Fournisseur"
        verbose_name_plural = "Paiements Fournisseur"
        ordering = ["-payment_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "payment_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code} - {self.amount}"

    # ------------------------------------------------------------------
    # BR-INV-04 (spec S4): hard gate — model layer
    # ------------------------------------------------------------------
    def clean(self):
        if self.supplier_invoice_id:
            inv = SupplierInvoice.objects.get(pk=self.supplier_invoice_id)
            if inv.status == "in_dispute":
                raise ValidationError(
                    "Impossible d'enregistrer un paiement pour une facture en litige (BR-INV-04). "
                    "Le litige doit être résolu par le Manager avant tout paiement."
                )

    def save(self, *args, **kwargs):
        self.full_clean()  # Ensure clean() runs on every save
        if not self.reference:
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("PAY-F", year)
        super().save(*args, **kwargs)
        # Signal supplier_ops.signals.supplier_payment_post_save will call
        # invoice.recompute_balance_due() — spec S7.
