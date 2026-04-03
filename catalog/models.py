from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal


class RawMaterialCategory(models.Model):
    """Categories for raw materials"""

    name = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie matière première"
        verbose_name_plural = "Catégories matières premières"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    """Units of measure for materials and products"""

    code = models.CharField(max_length=10, unique=True, verbose_name="Code")
    name = models.CharField(max_length=50, verbose_name="Nom")
    symbol = models.CharField(max_length=10, verbose_name="Symbole")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class RawMaterial(models.Model):
    """Raw materials catalog.

    SPEC S2 / S8:
      - reference: auto-generated RM-NNN, unique, immutable after creation.
      - unit_of_measure: immutable once any SupplierDNLine or FormulationLine
        references this material.
      - alert_threshold > stockout_threshold enforced in clean().
      - Deactivation only — never deleted.
    """

    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Référence",
        editable=False,  # Never accepted from form input
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    category = models.ForeignKey(
        RawMaterialCategory, on_delete=models.PROTECT, verbose_name="Catégorie"
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, verbose_name="Unité de mesure"
    )

    default_supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Fournisseur par défaut",
    )

    reference_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix de référence",
    )

    # Spec: "integer ≥ 0" but DecimalField used for sub-unit precision
    alert_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Seuil d'alerte",
    )
    stockout_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Seuil de rupture",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Matière première"
        verbose_name_plural = "Matières premières"
        ordering = ["reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.designation}"

    # ------------------------------------------------------------------
    # Reference auto-generation  (SPEC S8: RM-NNN, sequential, no year)
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            # New instance — generate reference before first save
            if not self.reference:
                self.reference = self._generate_reference()
        else:
            # Existing instance — block reference mutation
            original = RawMaterial.objects.get(pk=self.pk)
            if original.reference != self.reference:
                raise ValidationError(
                    "La référence d'une matière première est immuable après création."
                )
        super().save(*args, **kwargs)

    @classmethod
    def _generate_reference(cls):
        from core.models import DocumentSequence

        # Use DocumentSequence with a pseudo-year=0 for year-less sequences
        return DocumentSequence.get_next_reference("RM", 0)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def clean(self):
        # SPEC S2: alert_threshold must be strictly > stockout_threshold
        if self.alert_threshold <= self.stockout_threshold:
            raise ValidationError(
                {
                    "alert_threshold": (
                        "Le seuil d'alerte doit être strictement supérieur au seuil de rupture."
                    )
                }
            )

        # SPEC S2: unit_of_measure immutable once referenced by any DN or formulation line
        if self.pk:
            original = RawMaterial.objects.get(pk=self.pk)
            if original.unit_of_measure_id != self.unit_of_measure_id:
                if self._is_referenced():
                    raise ValidationError(
                        {
                            "unit_of_measure": (
                                "L'unité de mesure ne peut pas être modifiée une fois que la matière "
                                "est référencée dans un BL fournisseur ou une formulation."
                            )
                        }
                    )

    def _is_referenced(self):
        """Return True if any SupplierDNLine or FormulationLine references this material."""
        from supplier_ops.models import SupplierDNLine
        from production.models import FormulationLine

        return (
            SupplierDNLine.objects.filter(raw_material=self).exists()
            or FormulationLine.objects.filter(raw_material=self).exists()
        )

    # ------------------------------------------------------------------
    # Stock helpers (read-only computed values)
    # ------------------------------------------------------------------
    def get_current_stock(self):
        try:
            return self.stock_balance.quantity
        except Exception:
            return Decimal("0.000")

    def get_stock_status(self):
        current_stock = self.get_current_stock()
        from supplier_ops.models import SupplierDN

        has_active_order = SupplierDN.objects.filter(
            lines__raw_material=self,
            status__in=["pending", "validated"],
        ).exists()
        if has_active_order:
            return "on_order"
        if current_stock <= self.stockout_threshold:
            return "stockout"
        if current_stock <= self.alert_threshold:
            return "running_low"
        return "available"

    def get_stock_status_display_class(self):
        return {
            "available": "success",
            "running_low": "warning",
            "stockout": "danger",
            "on_order": "info",
        }.get(self.get_stock_status(), "secondary")


class FinishedProduct(models.Model):
    """Finished products catalog.

    SPEC S2 / S8:
      - reference: auto-generated PF-NNN, unique, immutable after creation.
      - wac (Weighted Average Cost) is NOT a user-editable field;
        it lives on FinishedProductStockBalance and is recomputed via
        signal after every PO closure.
      - source_formulation FK removed — not in spec (link is via
        Formulation.finished_product FK on the production side).
      - Deactivation only — never deleted.
    """

    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Référence",
        editable=False,
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    sales_unit = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, verbose_name="Unité de vente"
    )

    reference_selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix de vente de référence",
    )

    alert_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0.000"))],
        verbose_name="Seuil d'alerte stock",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produit fini"
        verbose_name_plural = "Produits finis"
        ordering = ["reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.designation}"

    # ------------------------------------------------------------------
    # Reference auto-generation  (SPEC S8: PF-NNN, sequential, no year)
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                self.reference = self._generate_reference()
        else:
            original = FinishedProduct.objects.get(pk=self.pk)
            if original.reference != self.reference:
                raise ValidationError(
                    "La référence d'un produit fini est immuable après création."
                )
        super().save(*args, **kwargs)

    @classmethod
    def _generate_reference(cls):
        from core.models import DocumentSequence

        return DocumentSequence.get_next_reference("PF", 0)

    # ------------------------------------------------------------------
    # Stock helpers
    # ------------------------------------------------------------------
    def get_current_stock(self):
        try:
            return self.stock_balance.quantity
        except Exception:
            return Decimal("0.000")

    def get_stock_status(self):
        current_stock = self.get_current_stock()
        if current_stock <= Decimal("0"):
            return "stockout"
        if current_stock <= self.alert_threshold:
            return "running_low"
        return "available"

    @property
    def wac(self):
        """Weighted Average Cost — read from FinishedProductStockBalance.
        SPEC S3: never user-editable; recomputed via signal after PO closure.
        """
        try:
            return self.stock_balance.weighted_average_cost
        except Exception:
            return Decimal("0.00")

    def get_unit_gross_margin(self):
        return self.reference_selling_price - self.wac

    def get_margin_rate(self):
        if self.reference_selling_price <= 0:
            return Decimal("0.00")
        return (self.get_unit_gross_margin() / self.reference_selling_price) * 100
