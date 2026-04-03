from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import json


class SupplierDN(models.Model):
    """Supplier Delivery Note (Bon de Livraison Fournisseur)"""

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("pending", "En attente de validation"),
        ("validated", "Validé"),
        ("in_dispute", "En litige"),
        ("cancelled", "Annulé"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence BL"
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
    total_amount_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant total HT",
    )

    remarks = models.TextField(blank=True, verbose_name="Observations")

    # Validation tracking
    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_supplier_dns",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")

    # Invoice linking
    linked_invoice = models.ForeignKey(
        "SupplierInvoice",
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

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: BL-F-YYYY-NNNN
            from core.models import DocumentSequence

            year = (
                self.delivery_date.year if self.delivery_date else timezone.now().year
            )
            self.reference = DocumentSequence.get_next_reference("BL-F", year)

        # Calculate total amount
        if self.pk:
            self.total_amount_ht = sum(line.line_amount for line in self.lines.all())

        super().save(*args, **kwargs)

    def validate(self, user):
        """Validate the delivery note"""
        if self.status != "pending":
            raise ValueError("Seuls les BL en attente peuvent être validés")

        self.status = "validated"
        self.validated_by = user
        self.validated_at = timezone.now()
        self.save()

        # Update stock balances via signals
        from django.db.models.signals import post_save

        post_save.send(sender=self.__class__, instance=self, created=False)

    def can_be_linked_to_invoice(self):
        """Check if DN can be linked to an invoice"""
        return self.status == "validated" and not self.linked_invoice


class SupplierDNLine(models.Model):
    """Line item in a Supplier Delivery Note"""

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
    line_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant ligne",
    )

    class Meta:
        verbose_name = "Ligne BL Fournisseur"
        verbose_name_plural = "Lignes BL Fournisseur"
        unique_together = ["supplier_dn", "raw_material"]

    def save(self, *args, **kwargs):
        # Calculate line amount
        self.line_amount = self.quantity_received * self.agreed_unit_price
        super().save(*args, **kwargs)

        # Update DN total
        if self.supplier_dn_id:
            self.supplier_dn.save()

    def __str__(self):
        return f"{self.supplier_dn.reference} - {self.raw_material.designation}"


class SupplierInvoice(models.Model):
    """Supplier Invoice (Facture Fournisseur)"""

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

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence facture"
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

    # Financial amounts
    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
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
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Solde dû",
    )

    # Reconciliation
    reconciliation_result = models.CharField(
        max_length=20,
        choices=RECONCILIATION_CHOICES,
        default="pending",
        verbose_name="Résultat rapprochement",
    )
    reconciliation_delta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Écart rapprochement",
    )

    # Linked delivery notes
    linked_dns = models.ManyToManyField(
        SupplierDN, through="SupplierInvoiceDNLink", verbose_name="BL liés"
    )

    # Metadata
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

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: FF-YYYY-NNNN
            from core.models import DocumentSequence

            year = self.invoice_date.year if self.invoice_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("FF", year)

        # Calculate totals
        if self.pk:
            self.total_ht = sum(line.line_amount for line in self.lines.all())
            # Calculate VAT based on company settings
            from core.models import CompanyInformation

            try:
                company = CompanyInformation.objects.first()
                if company:
                    self.vat_amount = self.total_ht * company.vat_rate
            except:
                self.vat_amount = Decimal("0.00")

            self.total_ttc = self.total_ht + self.vat_amount

            # Calculate balance due
            total_payments = sum(payment.amount for payment in self.payments.all())
            self.balance_due = self.total_ttc - total_payments

        super().save(*args, **kwargs)

    def perform_reconciliation(self):
        """Perform automatic reconciliation with linked DNs"""
        if not self.linked_dns.exists():
            return

        # Clear existing reconciliation lines
        self.reconciliation_lines.all().delete()

        total_delta = Decimal("0.00")

        # Get all materials from both invoice and DNs
        invoice_materials = {line.raw_material_id: line for line in self.lines.all()}
        dn_materials = {}

        for dn in self.linked_dns.all():
            for dn_line in dn.lines.all():
                material_id = dn_line.raw_material_id
                if material_id in dn_materials:
                    # Aggregate quantities if same material in multiple DNs
                    dn_materials[material_id]["quantity"] += dn_line.quantity_received
                    # Use weighted average price
                    total_amount = (
                        dn_materials[material_id]["quantity"]
                        * dn_materials[material_id]["price"]
                        + dn_line.quantity_received * dn_line.agreed_unit_price
                    )
                    dn_materials[material_id]["quantity"] += dn_line.quantity_received
                    dn_materials[material_id]["price"] = (
                        total_amount / dn_materials[material_id]["quantity"]
                    )
                else:
                    dn_materials[material_id] = {
                        "material": dn_line.raw_material,
                        "quantity": dn_line.quantity_received,
                        "price": dn_line.agreed_unit_price,
                    }

        # Create reconciliation lines
        all_materials = set(invoice_materials.keys()) | set(dn_materials.keys())

        for material_id in all_materials:
            invoice_line = invoice_materials.get(material_id)
            dn_data = dn_materials.get(material_id)

            qty_delivered = dn_data["quantity"] if dn_data else Decimal("0.000")
            price_agreed = dn_data["price"] if dn_data else Decimal("0.00")
            qty_invoiced = (
                invoice_line.quantity_invoiced if invoice_line else Decimal("0.000")
            )
            price_invoiced = (
                invoice_line.unit_price_invoiced if invoice_line else Decimal("0.00")
            )

            delta_qty = qty_invoiced - qty_delivered
            delta_price = price_invoiced - price_agreed
            delta_amount = (qty_invoiced * price_invoiced) - (
                qty_delivered * price_agreed
            )

            total_delta += delta_amount

            ReconciliationLine.objects.create(
                supplier_invoice=self,
                raw_material_id=material_id,
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

        # Get thresholds from system parameters
        from core.models import SystemParameter

        tolerance_threshold = SystemParameter.get_decimal_value(
            "reconciliation_tolerance_threshold", Decimal("500.00")
        )
        dispute_threshold = SystemParameter.get_decimal_value(
            "reconciliation_dispute_threshold", Decimal("5000.00")
        )

        abs_delta = abs(total_delta)
        if abs_delta <= tolerance_threshold:
            self.reconciliation_result = "compliant"
            self.status = "verified"
        elif abs_delta <= dispute_threshold:
            self.reconciliation_result = "minor_discrepancy"
            self.status = "under_reconciliation"
        else:
            self.reconciliation_result = "dispute"
            self.status = "in_dispute"

        self.save()

    def is_overdue(self):
        """Check if invoice is overdue"""
        return self.due_date < timezone.now().date() and self.balance_due > 0


class SupplierInvoiceLine(models.Model):
    """Line item in a Supplier Invoice"""

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
    line_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant ligne",
    )

    class Meta:
        verbose_name = "Ligne Facture Fournisseur"
        verbose_name_plural = "Lignes Facture Fournisseur"
        unique_together = ["supplier_invoice", "raw_material"]

    def save(self, *args, **kwargs):
        # Calculate line amount
        self.line_amount = self.quantity_invoiced * self.unit_price_invoiced
        super().save(*args, **kwargs)

        # Update invoice total
        if self.supplier_invoice_id:
            self.supplier_invoice.save()

    def __str__(self):
        return f"{self.supplier_invoice.reference} - {self.designation}"


class SupplierInvoiceDNLink(models.Model):
    """Many-to-many relationship between Supplier Invoices and Delivery Notes"""

    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE)
    supplier_dn = models.ForeignKey(SupplierDN, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["supplier_invoice", "supplier_dn"]


class ReconciliationLine(models.Model):
    """Reconciliation comparison line between DN and Invoice"""

    supplier_invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name="reconciliation_lines"
    )
    raw_material = models.ForeignKey("catalog.RawMaterial", on_delete=models.PROTECT)

    # Delivered quantities (from DN)
    qty_delivered = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000")
    )
    price_agreed = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Invoiced quantities
    qty_invoiced = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000")
    )
    price_invoiced = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Calculated deltas
    delta_qty = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000")
    )
    delta_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    delta_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = "Ligne de rapprochement"
        verbose_name_plural = "Lignes de rapprochement"
        unique_together = ["supplier_invoice", "raw_material"]


class SupplierPayment(models.Model):
    """Payment made to a supplier"""

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence paiement"
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

    # Metadata
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

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: PAY-F-YYYY-NNNN
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("PAY-F", year)

        super().save(*args, **kwargs)

        # Update invoice balance
        if self.supplier_invoice_id:
            self.supplier_invoice.save()
