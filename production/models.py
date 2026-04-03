# production/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class Formulation(models.Model):
    """Production formulation/recipe.

    SPEC BR-PROD-03: editing blocked if any PO with status='in_progress'.
    SPEC S8: reference F-NNN, sequential, no year.
    """

    reference = models.CharField(
        max_length=50, verbose_name="Référence formulation", editable=False
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
        if not self.pk and not self.reference:
            from core.models import DocumentSequence

            self.reference = DocumentSequence.get_next_reference("F", 0)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # BR-PROD-03: block modification when in_progress PO exists
    # ------------------------------------------------------------------
    def clean(self):
        if self.pk and self.has_active_production_orders():
            raise ValidationError(
                "Impossible de modifier une formulation avec des ordres de production en cours (BR-PROD-03)."
            )

    def has_active_production_orders(self):
        return self.production_orders.filter(status="in_progress").exists()

    # ------------------------------------------------------------------
    def create_new_version(self, user):
        """Create a new version; blocks if in_progress POs exist."""
        if self.has_active_production_orders():
            raise ValidationError(
                "Impossible de créer une nouvelle version : des ordres de production sont en cours."
            )
        self.is_active = False
        self.save()

        new_f = Formulation.objects.create(
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
        for line in self.lines.all():
            FormulationLine.objects.create(
                formulation=new_f,
                raw_material=line.raw_material,
                qty_per_batch=line.qty_per_batch,
                unit_of_measure=line.unit_of_measure,
                tolerance_pct=line.tolerance_pct,
            )
        return new_f

    def calculate_theoretical_cost(self):
        return sum(
            line.qty_per_batch * line.raw_material.reference_price
            for line in self.lines.all()
        )

    def get_unit_theoretical_cost(self):
        batch_cost = self.calculate_theoretical_cost()
        if self.reference_batch_qty > 0:
            return batch_cost / self.reference_batch_qty
        return Decimal("0.00")


class FormulationLine(models.Model):
    """Raw material line in a formulation."""

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

    @property
    def theoretical_cost(self):
        return self.qty_per_batch * self.raw_material.reference_price


class ProductionOrder(models.Model):
    """Production Order (Ordre de Production).

    SPEC S2 / S6 status transitions:
      pending → validated  (via validate())
      validated → in_progress  (via launch())
      in_progress → completed  (via close())
      in_progress / pending → cancelled

    SPEC S3: yield_rate and yield_status are @property — NOT stored DB fields.
    """

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("validated", "Validé"),
        ("in_progress", "En cours"),
        ("completed", "Terminé"),
        ("cancelled", "Annulé"),
    ]

    VALID_TRANSITIONS = {
        "pending": ["validated", "cancelled"],
        "validated": ["in_progress", "cancelled"],
        "in_progress": ["completed", "cancelled"],
        "completed": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence OP", editable=False
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

    actual_qty_produced = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité réellement produite",
    )

    stock_check_passed = models.BooleanField(
        default=False, verbose_name="Vérification stock OK"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

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
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.launch_date.year if self.launch_date else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("OP", year)
            if self.formulation and not self.formulation_version:
                self.formulation_version = self.formulation.version
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # SPEC S3: yield_rate and yield_status as @property
    # ------------------------------------------------------------------
    @property
    def yield_rate(self):
        """Computed — never stored directly (spec S3)."""
        if self.actual_qty_produced is not None and self.target_qty > 0:
            return (self.actual_qty_produced / self.target_qty) * 100
        return None

    @property
    def yield_status(self):
        """Derived from yield_rate vs configurable thresholds (spec S3)."""
        rate = self.yield_rate
        if rate is None:
            return None
        from core.models import SystemParameter

        warning = SystemParameter.get_decimal_value(
            "yield_warning_threshold", Decimal("90.00")
        )
        critical = SystemParameter.get_decimal_value(
            "yield_critical_threshold", Decimal("80.00")
        )
        if rate >= warning:
            return "normal"
        if rate >= critical:
            return "warning"
        return "critical"

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------
    def _transition(self, new_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Transition invalide : {self.status} → {new_status}."
            )
        self.status = new_status

    def validate(self, user):
        """pending → validated: stock availability check."""
        self._transition("validated")
        insufficient = self._check_stock_availability()
        self.stock_check_passed = len(insufficient) == 0
        self.save()
        return insufficient

    def launch(self, user):
        """validated → in_progress: create consumption lines."""
        self._transition("in_progress")
        self._create_consumption_lines()
        self.save()

    def close(self, user, actual_qty_produced, consumption_data):
        """
        in_progress → completed.

        SPEC BR-PROD-05: uses qty_actual (not qty_theoretical) for RM
        stock deductions — handled by the post_save signal in
        production/signals.py, NOT called directly here.

        consumption_data: {raw_material_id: actual_qty, ...}
        """
        self._transition("completed")
        self.actual_qty_produced = actual_qty_produced
        self.closure_date = timezone.now().date()
        self.closed_by = user
        self.save()

        # Record actual consumption on lines
        for material_id, actual_qty in consumption_data.items():
            try:
                line = self.consumption_lines.get(raw_material_id=material_id)
                line.qty_actual = actual_qty
                line.save()
            except ProductionOrderLine.DoesNotExist:
                pass
        # Signal production.signals.production_order_post_save handles
        # RM deductions + FG credit + WAC recalculation (spec S7).

    def cancel(self, user):
        """pending or in_progress → cancelled."""
        self._transition("cancelled")
        self.save()

    # ------------------------------------------------------------------
    def _check_stock_availability(self):
        insufficient = []
        for line in self.consumption_lines.all():
            from stock.models import RawMaterialStockBalance

            try:
                balance = RawMaterialStockBalance.objects.get(
                    raw_material=line.raw_material
                )
                available = balance.quantity
            except RawMaterialStockBalance.DoesNotExist:
                available = Decimal("0.000")
            if available < line.qty_theoretical:
                insufficient.append(
                    {
                        "material": line.raw_material,
                        "required": line.qty_theoretical,
                        "available": available,
                        "shortage": line.qty_theoretical - available,
                    }
                )
        return insufficient

    def _create_consumption_lines(self):
        """Scale formulation lines to target_qty."""
        self.consumption_lines.all().delete()
        scaling = self.target_qty / self.formulation.reference_batch_qty
        for fl in self.formulation.lines.all():
            ProductionOrderLine.objects.create(
                production_order=self,
                raw_material=fl.raw_material,
                qty_theoretical=fl.qty_per_batch * scaling,
                tolerance_pct=fl.tolerance_pct,
            )

    def calculate_batch_cost(self):
        """Actual cost using qty_actual (spec BR-PROD-05)."""
        return sum(
            (line.qty_actual or Decimal("0.000")) * line.raw_material.reference_price
            for line in self.consumption_lines.all()
        )

    def get_unit_cost(self):
        cost = self.calculate_batch_cost()
        if self.actual_qty_produced and self.actual_qty_produced > 0:
            return cost / self.actual_qty_produced
        return Decimal("0.00")


class ProductionOrderLine(models.Model):
    """Raw material consumption line in a production order.

    SPEC S3: delta_qty and financial_impact are @property — NOT stored.
    qty_theoretical is computed at PO creation from formulation, never
    accepted from form input.
    """

    production_order = models.ForeignKey(
        ProductionOrder, on_delete=models.CASCADE, related_name="consumption_lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    # SPEC S3: computed at PO creation — editable=False prevents form submission
    qty_theoretical = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité théorique",
        editable=False,
    )
    qty_actual = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Quantité réelle",
    )
    tolerance_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        verbose_name="Tolérance (%)",
    )

    class Meta:
        verbose_name = "Ligne consommation OP"
        verbose_name_plural = "Lignes consommation OP"
        unique_together = ["production_order", "raw_material"]

    def __str__(self):
        return f"{self.production_order.reference} - {self.raw_material.designation}"

    # SPEC S3: computed properties — never stored
    @property
    def delta_qty(self):
        if self.qty_actual is not None:
            return self.qty_actual - self.qty_theoretical
        return None

    @property
    def financial_impact(self):
        dq = self.delta_qty
        if dq is not None:
            return dq * self.raw_material.reference_price
        return None

    def is_within_tolerance(self):
        if self.qty_actual is None:
            return True
        tolerance_amount = self.qty_theoretical * (self.tolerance_pct / 100)
        dq = self.delta_qty
        return abs(dq) <= tolerance_amount if dq is not None else True

    def get_variance_percentage(self):
        if self.qty_theoretical == 0 or self.qty_actual is None:
            return Decimal("0.00")
        return (self.delta_qty / self.qty_theoretical) * 100
