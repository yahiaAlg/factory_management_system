from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class RawMaterialStockBalance(models.Model):
    """Current stock balance for raw materials"""

    raw_material = models.OneToOneField(
        "catalog.RawMaterial", on_delete=models.CASCADE, related_name="stock_balance"
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        verbose_name="Quantité en stock",
    )
    last_movement_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernière mouvement"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Solde stock matière première"
        verbose_name_plural = "Soldes stock matières premières"

    def __str__(self):
        return f"{self.raw_material.designation} - {self.quantity} {self.raw_material.unit_of_measure.symbol}"

    def get_stock_status(self):
        """Get current stock status"""
        return self.raw_material.get_stock_status()

    def get_stock_value(self):
        """Calculate stock value using reference price"""
        return self.quantity * self.raw_material.reference_price


class FinishedProductStockBalance(models.Model):
    """Current stock balance for finished products"""

    finished_product = models.OneToOneField(
        "catalog.FinishedProduct",
        on_delete=models.CASCADE,
        related_name="stock_balance",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        verbose_name="Quantité en stock",
    )
    weighted_average_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût moyen pondéré",
    )
    last_movement_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernière mouvement"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Solde stock produit fini"
        verbose_name_plural = "Soldes stock produits finis"

    def __str__(self):
        return f"{self.finished_product.designation} - {self.quantity} {self.finished_product.sales_unit.symbol}"

    def get_stock_status(self):
        """Get current stock status"""
        return self.finished_product.get_stock_status()

    def get_stock_value(self):
        """Calculate stock value using WAC"""
        return self.quantity * self.weighted_average_cost

    def update_weighted_average_cost(self):
        """Recalculate weighted average cost from production movements"""
        production_movements = StockMovement.objects.filter(
            finished_product=self.finished_product,
            movement_type="production",
            quantity__gt=0,
        ).order_by("movement_date")

        if not production_movements.exists():
            self.weighted_average_cost = Decimal("0.00")
            self.save()
            return

        total_cost = Decimal("0.00")
        total_quantity = Decimal("0.000")

        for movement in production_movements:
            if movement.unit_cost and movement.unit_cost > 0:
                batch_cost = movement.quantity * movement.unit_cost
                total_cost += batch_cost
                total_quantity += movement.quantity

        if total_quantity > 0:
            self.weighted_average_cost = total_cost / total_quantity
        else:
            self.weighted_average_cost = Decimal("0.00")

        self.save()


class StockMovement(models.Model):
    """Stock movement history for traceability"""

    MOVEMENT_TYPE_CHOICES = [
        ("receipt", "Réception"),
        ("consumption", "Consommation"),
        ("production", "Production"),
        ("delivery", "Livraison"),
        ("adjustment", "Ajustement"),
        ("opening", "Stock d'ouverture"),
        ("return", "Retour"),
        ("loss", "Perte"),
    ]

    SOURCE_DOCUMENT_CHOICES = [
        ("supplier_dn", "BL Fournisseur"),
        ("production_order", "Ordre de Production"),
        ("client_dn", "BL Client"),
        ("adjustment", "Ajustement"),
        ("opening", "Stock d'ouverture"),
    ]

    # Material references (one of these will be filled)
    raw_material = models.ForeignKey(
        "catalog.RawMaterial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Matière première",
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Produit fini",
    )

    movement_type = models.CharField(
        max_length=20, choices=MOVEMENT_TYPE_CHOICES, verbose_name="Type de mouvement"
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Quantité"
    )

    # Pricing information
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix unitaire",
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût unitaire",
    )

    # Source document traceability
    source_document_type = models.CharField(
        max_length=20,
        choices=SOURCE_DOCUMENT_CHOICES,
        verbose_name="Type document source",
    )
    source_document_id = models.PositiveIntegerField(verbose_name="ID document source")
    source_line_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="ID ligne source"
    )

    movement_date = models.DateField(verbose_name="Date mouvement")
    remarks = models.TextField(blank=True, verbose_name="Observations")

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-movement_date", "-created_at"]
        indexes = [
            models.Index(fields=["raw_material", "movement_date"]),
            models.Index(fields=["finished_product", "movement_date"]),
            models.Index(fields=["source_document_type", "source_document_id"]),
        ]

    def __str__(self):
        material = self.raw_material or self.finished_product
        return f"{self.get_movement_type_display()} - {material} - {self.quantity}"

    def save(self, *args, **kwargs):
        # Validate that exactly one material is specified
        if not (
            (self.raw_material and not self.finished_product)
            or (self.finished_product and not self.raw_material)
        ):
            raise ValueError(
                "Exactly one of raw_material or finished_product must be specified"
            )

        super().save(*args, **kwargs)

        # Update stock balances
        self.update_stock_balance()

    def update_stock_balance(self):
        """Update the corresponding stock balance"""
        if self.raw_material:
            balance, created = RawMaterialStockBalance.objects.get_or_create(
                raw_material=self.raw_material, defaults={"quantity": Decimal("0.000")}
            )

            # Recalculate balance from all movements
            total_quantity = StockMovement.objects.filter(
                raw_material=self.raw_material
            ).aggregate(total=models.Sum("quantity"))["total"] or Decimal("0.000")

            balance.quantity = total_quantity
            balance.last_movement_date = timezone.now()
            balance.save()

        elif self.finished_product:
            balance, created = FinishedProductStockBalance.objects.get_or_create(
                finished_product=self.finished_product,
                defaults={
                    "quantity": Decimal("0.000"),
                    "weighted_average_cost": Decimal("0.00"),
                },
            )

            # Recalculate balance from all movements
            total_quantity = StockMovement.objects.filter(
                finished_product=self.finished_product
            ).aggregate(total=models.Sum("quantity"))["total"] or Decimal("0.000")

            balance.quantity = total_quantity
            balance.last_movement_date = timezone.now()
            balance.save()

            # Update weighted average cost
            balance.update_weighted_average_cost()


class StockAdjustment(models.Model):
    """Stock adjustment for corrections and inventory updates"""

    ADJUSTMENT_TYPE_CHOICES = [
        ("inventory", "Inventaire"),
        ("correction", "Correction"),
        ("loss", "Perte"),
        ("damage", "Avarie"),
        ("return", "Retour"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence ajustement"
    )
    adjustment_type = models.CharField(
        max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, verbose_name="Type d'ajustement"
    )
    adjustment_date = models.DateField(verbose_name="Date ajustement")
    reason = models.TextField(verbose_name="Motif")

    # Approval
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_adjustments",
        verbose_name="Approuvé par",
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Approuvé le"
    )

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ajustement de stock"
        verbose_name_plural = "Ajustements de stock"
        ordering = ["-adjustment_date"]

    def __str__(self):
        return f"{self.reference} - {self.get_adjustment_type_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: ADJ-YYYY-NNNN
            from core.models import DocumentSequence

            year = (
                self.adjustment_date.year
                if self.adjustment_date
                else timezone.now().year
            )
            self.reference = DocumentSequence.get_next_reference("ADJ", year)

        super().save(*args, **kwargs)

    def approve(self, user):
        """Approve the adjustment and create stock movements"""
        if self.approved_by:
            raise ValueError("Cet ajustement est déjà approuvé")

        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

        # Create stock movements for each line
        for line in self.lines.all():
            StockMovement.objects.create(
                raw_material=line.raw_material,
                finished_product=line.finished_product,
                movement_type="adjustment",
                quantity=line.quantity_adjustment,
                source_document_type="adjustment",
                source_document_id=self.id,
                source_line_id=line.id,
                movement_date=self.adjustment_date,
                created_by=user,
                remarks=f"Ajustement {self.reference}: {self.reason}",
            )


class StockAdjustmentLine(models.Model):
    """Line item in a stock adjustment"""

    stock_adjustment = models.ForeignKey(
        StockAdjustment, on_delete=models.CASCADE, related_name="lines"
    )

    # Material references (one of these will be filled)
    raw_material = models.ForeignKey(
        "catalog.RawMaterial",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Matière première",
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Produit fini",
    )

    quantity_before = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Quantité avant"
    )
    quantity_after = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Quantité après"
    )
    quantity_adjustment = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Ajustement"
    )

    remarks = models.TextField(blank=True, verbose_name="Observations")

    class Meta:
        verbose_name = "Ligne ajustement stock"
        verbose_name_plural = "Lignes ajustement stock"

    def save(self, *args, **kwargs):
        # Calculate adjustment quantity
        self.quantity_adjustment = self.quantity_after - self.quantity_before
        super().save(*args, **kwargs)

    def __str__(self):
        material = self.raw_material or self.finished_product
        return f"{self.stock_adjustment.reference} - {material}"
