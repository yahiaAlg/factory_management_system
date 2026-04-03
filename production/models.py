from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal


class Formulation(models.Model):
    """Production formulation/recipe"""

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence formulation"
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct", on_delete=models.PROTECT, verbose_name="Produit fini"
    )
    reference_batch_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité de référence du lot",
    )
    reference_batch_unit = models.ForeignKey(
        "catalog.UnitOfMeasure",
        on_delete=models.PROTECT,
        verbose_name="Unité du lot de référence",
    )
    expected_yield_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("200.00")),
        ],
        verbose_name="Rendement attendu (%)",
    )
    version = models.IntegerField(default=1, verbose_name="Version")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    technical_notes = models.TextField(blank=True, verbose_name="Notes techniques")

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Formulation"
        verbose_name_plural = "Formulations"
        ordering = ["reference"]
        unique_together = ["reference", "version"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["finished_product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.reference} v{self.version} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: F-NNN
            next_num = Formulation.objects.count() + 1
            self.reference = f"F-{next_num:03d}"

        super().save(*args, **kwargs)

    def create_new_version(self, user):
        """Create a new version of this formulation"""
        if self.has_active_production_orders():
            raise ValueError(
                "Impossible de modifier une formulation avec des ordres de production actifs"
            )

        # Deactivate current version
        self.is_active = False
        self.save()

        # Create new version
        new_formulation = Formulation.objects.create(
            reference=self.reference,
            designation=self.designation,
            finished_product=self.finished_product,
            reference_batch_qty=self.reference_batch_qty,
            reference_batch_unit=self.reference_batch_unit,
            expected_yield_pct=self.expected_yield_pct,
            version=self.version + 1,
            technical_notes=self.technical_notes,
            created_by=user,
        )

        # Copy formulation lines
        for line in self.lines.all():
            FormulationLine.objects.create(
                formulation=new_formulation,
                raw_material=line.raw_material,
                qty_per_batch=line.qty_per_batch,
                unit_of_measure=line.unit_of_measure,
                tolerance_pct=line.tolerance_pct,
            )

        return new_formulation

    def has_active_production_orders(self):
        """Check if formulation has active production orders"""
        return self.production_orders.filter(status="in_progress").exists()

    def calculate_theoretical_cost(self):
        """Calculate theoretical cost per batch"""
        total_cost = Decimal("0.00")
        for line in self.lines.all():
            material_cost = line.qty_per_batch * line.raw_material.reference_price
            total_cost += material_cost
        return total_cost

    def get_unit_theoretical_cost(self):
        """Get theoretical cost per unit of finished product"""
        batch_cost = self.calculate_theoretical_cost()
        if self.reference_batch_qty > 0:
            return batch_cost / self.reference_batch_qty
        return Decimal("0.00")


class FormulationLine(models.Model):
    """Raw material line in a formulation"""

    formulation = models.ForeignKey(
        Formulation, on_delete=models.CASCADE, related_name="lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    qty_per_batch = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité par lot",
    )
    unit_of_measure = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, verbose_name="Unité"
    )
    tolerance_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Tolérance (%)",
    )

    class Meta:
        verbose_name = "Ligne de formulation"
        verbose_name_plural = "Lignes de formulation"
        unique_together = ["formulation", "raw_material"]

    def __str__(self):
        return f"{self.formulation.reference} - {self.raw_material.designation}"

    def get_theoretical_cost(self):
        """Get theoretical cost for this line"""
        return self.qty_per_batch * self.raw_material.reference_price


class ProductionOrder(models.Model):
    """Production Order (Ordre de Production)"""

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("validated", "Validé"),
        ("in_progress", "En cours"),
        ("completed", "Terminé"),
        ("cancelled", "Annulé"),
    ]

    YIELD_STATUS_CHOICES = [
        ("normal", "Normal"),
        ("warning", "Attention"),
        ("critical", "Critique"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence OP"
    )
    formulation = models.ForeignKey(
        Formulation,
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Formulation",
    )
    formulation_version = models.IntegerField(verbose_name="Version formulation")
    target_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité cible",
    )
    target_unit = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, verbose_name="Unité cible"
    )

    launch_date = models.DateField(verbose_name="Date de lancement")
    closure_date = models.DateField(
        null=True, blank=True, verbose_name="Date de clôture"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Statut"
    )

    # Production results
    actual_qty_produced = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité réellement produite",
    )
    yield_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Taux de rendement (%)",
    )
    yield_status = models.CharField(
        max_length=20,
        choices=YIELD_STATUS_CHOICES,
        default="normal",
        verbose_name="Statut rendement",
    )

    # Stock validation
    stock_check_passed = models.BooleanField(
        default=False, verbose_name="Vérification stock OK"
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_production_orders",
        verbose_name="Clôturé par",
    )

    class Meta:
        verbose_name = "Ordre de Production"
        verbose_name_plural = "Ordres de Production"
        ordering = ["-launch_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["formulation", "status"]),
            models.Index(fields=["launch_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.formulation.designation}"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: OP-YYYY-NNNN
            from core.models import DocumentSequence

            year = self.launch_date.year if self.launch_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("OP", year)

        # Store formulation version
        if self.formulation and not self.formulation_version:
            self.formulation_version = self.formulation.version

        super().save(*args, **kwargs)

    def validate_stock_availability(self):
        """Check if all required materials are available in stock"""
        insufficient_materials = []

        for line in self.consumption_lines.all():
            from stock.models import RawMaterialStockBalance

            try:
                balance = RawMaterialStockBalance.objects.get(
                    raw_material=line.raw_material
                )
                if balance.quantity < line.qty_theoretical:
                    insufficient_materials.append(
                        {
                            "material": line.raw_material,
                            "required": line.qty_theoretical,
                            "available": balance.quantity,
                            "shortage": line.qty_theoretical - balance.quantity,
                        }
                    )
            except RawMaterialStockBalance.DoesNotExist:
                insufficient_materials.append(
                    {
                        "material": line.raw_material,
                        "required": line.qty_theoretical,
                        "available": Decimal("0.000"),
                        "shortage": line.qty_theoretical,
                    }
                )

        self.stock_check_passed = len(insufficient_materials) == 0
        self.save()

        return insufficient_materials

    def launch(self, user):
        """Launch the production order"""
        if self.status != "pending":
            raise ValueError("Seuls les ordres en attente peuvent être lancés")

        # Create consumption lines based on formulation
        self.create_consumption_lines()

        # Validate stock availability
        insufficient_materials = self.validate_stock_availability()

        if insufficient_materials and not user.userprofile.role == "manager":
            raise ValueError("Stock insuffisant pour certaines matières premières")

        self.status = "in_progress"
        self.save()

    def create_consumption_lines(self):
        """Create consumption lines based on formulation"""
        # Clear existing lines
        self.consumption_lines.all().delete()

        # Calculate scaling factor
        scaling_factor = self.target_qty / self.formulation.reference_batch_qty

        # Create lines
        for formulation_line in self.formulation.lines.all():
            ProductionOrderLine.objects.create(
                production_order=self,
                raw_material=formulation_line.raw_material,
                qty_theoretical=formulation_line.qty_per_batch * scaling_factor,
                tolerance_pct=formulation_line.tolerance_pct,
            )

    def close(self, user, actual_qty_produced, consumption_data):
        """Close the production order with actual results"""
        if self.status != "in_progress":
            raise ValueError("Seul un ordre en cours peut être clôturé")

        self.actual_qty_produced = actual_qty_produced
        self.closure_date = timezone.now().date()
        self.closed_by = user

        # Calculate yield rate
        if self.target_qty > 0:
            self.yield_rate = (actual_qty_produced / self.target_qty) * 100

        # Determine yield status
        from core.models import SystemParameter

        warning_threshold = SystemParameter.get_decimal_value(
            "yield_warning_threshold", Decimal("90.00")
        )
        critical_threshold = SystemParameter.get_decimal_value(
            "yield_critical_threshold", Decimal("80.00")
        )

        if self.yield_rate >= warning_threshold:
            self.yield_status = "normal"
        elif self.yield_rate >= critical_threshold:
            self.yield_status = "warning"
        else:
            self.yield_status = "critical"

        # Update consumption lines with actual quantities
        for material_id, actual_qty in consumption_data.items():
            try:
                line = self.consumption_lines.get(raw_material_id=material_id)
                line.qty_actual = actual_qty
                line.save()
            except ProductionOrderLine.DoesNotExist:
                pass

        self.status = "completed"
        self.save()

        # Trigger stock movements via signals
        from django.db.models.signals import post_save

        post_save.send(sender=self.__class__, instance=self, created=False)

    def calculate_batch_cost(self):
        """Calculate actual cost of this production batch"""
        total_cost = Decimal("0.00")
        for line in self.consumption_lines.all():
            if line.qty_actual is not None:
                material_cost = line.qty_actual * line.raw_material.reference_price
                total_cost += material_cost
        return total_cost

    def get_unit_cost(self):
        """Get actual unit cost of produced goods"""
        batch_cost = self.calculate_batch_cost()
        if self.actual_qty_produced and self.actual_qty_produced > 0:
            return batch_cost / self.actual_qty_produced
        return Decimal("0.00")


class ProductionOrderLine(models.Model):
    """Raw material consumption line in a production order"""

    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name="consumption_lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    qty_theoretical = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité théorique",
    )
    qty_actual = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité réelle",
    )
    delta_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.000"),
        verbose_name="Écart quantité",
    )
    tolerance_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        verbose_name="Tolérance (%)",
    )
    financial_impact = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Impact financier",
    )

    class Meta:
        verbose_name = "Ligne consommation OP"
        verbose_name_plural = "Lignes consommation OP"
        unique_together = ["production_order", "raw_material"]

    def save(self, *args, **kwargs):
        # Calculate delta and financial impact
        if self.qty_actual is not None:
            self.delta_qty = self.qty_actual - self.qty_theoretical
            self.financial_impact = self.delta_qty * self.raw_material.reference_price

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.production_order.reference} - {self.raw_material.designation}"

    def is_within_tolerance(self):
        """Check if actual consumption is within tolerance"""
        if self.qty_actual is None:
            return True

        tolerance_amount = self.qty_theoretical * (self.tolerance_pct / 100)
        return abs(self.delta_qty) <= tolerance_amount

    def get_variance_percentage(self):
        """Get variance percentage from theoretical"""
        if self.qty_theoretical == 0 or self.qty_actual is None:
            return Decimal("0.00")

        return (self.delta_qty / self.qty_theoretical) * 100
