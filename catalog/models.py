# catalog/models.py
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
    # SPEC S22.3: flags units that measure volume (litre, mL, ...). Required
    # for a RawMaterial to use kg_equivalent_mode="density" (§22.5).
    is_volumetric = models.BooleanField(
        default=False,
        verbose_name="Unité volumétrique",
        help_text="Coché pour les unités de volume (litre, mL...) — requis pour la conversion par densité.",
    )

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

    # Row highlight color for the catalog list view — user-chosen via a
    # color picker on the create/edit form. Defaults to the RM list's
    # original blue accent so existing records keep their current look.
    row_color = models.CharField(
        max_length=7,
        default="#2563eb",
        verbose_name="Couleur de ligne (catalogue)",
        help_text="Couleur utilisée pour distinguer cette matière première dans la liste.",
    )

    # ------------------------------------------------------------------
    # BR-DUAL-01: dual-entry article. Links this RawMaterial to its mirror
    # FinishedProduct row when the same physical article is both consumed
    # as a raw material AND sold/stocked as a finished product (e.g. a
    # chemical purchased in bulk that is also resold as-is, unchanged).
    # designation/unit_of_measure/is_active stay synced in real time
    # (catalog/signals.py) and every StockMovement on either side is
    # mirrored onto the other's stock balance (stock/signals.py).
    # ------------------------------------------------------------------
    twin_finished_product = models.OneToOneField(
        "catalog.FinishedProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="twin_raw_material",
        verbose_name="Produit fini jumeau (article à double entrée)",
        help_text="Lier à un produit fini pour synchroniser automatiquement la quantité et la désignation entre les deux catalogues.",
    )

    # ------------------------------------------------------------------
    # SPEC S22 (planned, §22.3): KG-Equivalent Mass Formulation Engine.
    # Purely additive — does not affect unit_of_measure, stock, or
    # delivery-note/invoicing behaviour. Used only inside formulation math
    # (Formulation.non_complement_mass_kg / FormulationLine.kg_equivalent).
    # ------------------------------------------------------------------
    KG_EQUIVALENT_MODE_CHOICES = [
        ("direct", "Direct (kg par unité)"),
        ("density", "Densité (kg par litre)"),
    ]
    kg_equivalent_mode = models.CharField(
        max_length=10,
        choices=KG_EQUIVALENT_MODE_CHOICES,
        blank=True,
        verbose_name="Mode d'équivalence kg",
        help_text="Méthode de conversion en kg pour les formulations à base de masse (§22).",
    )
    kg_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Kg par unité",
        help_text="Requis si mode = Direct. Masse en kg d'une unité de cette matière.",
    )
    density_kg_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Densité (kg/L)",
        help_text="Requis si mode = Densité. Unité de mesure doit être volumétrique.",
    )
    volumetric_factor = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("1.0000"),
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Facteur volumétrique",
        help_text="Multiplicateur appliqué à l'équivalent kg pour obtenir le poids volumétrique (§22.6).",
    )

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

        # SPEC S22.3: kg-equivalent mode validation (planned formulation engine)
        if self.kg_equivalent_mode == "direct":
            if self.kg_per_unit is None:
                raise ValidationError(
                    {"kg_per_unit": "Kg par unité est requis lorsque le mode est Direct."}
                )
        elif self.kg_equivalent_mode == "density":
            if self.density_kg_per_liter is None:
                raise ValidationError(
                    {
                        "density_kg_per_liter": (
                            "La densité (kg/L) est requise lorsque le mode est Densité."
                        )
                    }
                )
            if self.unit_of_measure_id and not self.unit_of_measure.is_volumetric:
                raise ValidationError(
                    {
                        "kg_equivalent_mode": (
                            "Le mode Densité nécessite une unité de mesure volumétrique "
                            "(litre, mL...)."
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
    # SPEC S22.5: kg-equivalent (planned formulation engine, read-only)
    # ------------------------------------------------------------------
    @property
    def effective_kg_per_unit(self):
        """How many kg one unit of this material's unit_of_measure represents.

        Falls back to 1 unit = 1 kg when kg_equivalent_mode has not been
        explicitly configured — the formulation engine (§22) always has a
        usable kg-equivalent for every raw material unless a different
        conversion (direct kg/unit or density) has been set on the record.
        """
        if self.kg_equivalent_mode == "direct":
            return self.kg_per_unit
        if self.kg_equivalent_mode == "density":
            # unit_of_measure for a density-mode material is itself a litre-
            # denominated unit (§22.5), so 1 unit == 1 litre for this purpose.
            return self.density_kg_per_liter
        # Not configured — default to 1 unit = 1 kg unless said otherwise.
        return Decimal("1.0000")

    # ------------------------------------------------------------------
    # Stock helpers (read-only computed values)
    # ------------------------------------------------------------------
    def get_current_stock(self, site=None):
        """Current stock quantity (functional spec §25.2.3).

        With no `site`, aggregates across every ProductionSite — the
        company-wide total, matching pre-multi-site behaviour for any
        caller that doesn't care which site. Pass a specific `site`
        (ProductionSite instance or pk) to read just that site's balance.
        """
        from django.db.models import Sum

        qs = self.stock_balances.all()
        if site is not None:
            qs = qs.filter(site=site)
        total = qs.aggregate(total=Sum("quantity"))["total"]
        return total if total is not None else Decimal("0.000")

    def get_stock_status(self, site=None):
        current_stock = self.get_current_stock(site=site)
        from supplier_ops.models import SupplierDN

        order_filter = {
            "lines__raw_material": self,
            "status__in": ["pending", "validated"],
        }
        if site is not None:
            order_filter["site"] = site
        has_active_order = SupplierDN.objects.filter(**order_filter).exists()
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

    @property
    def is_dual(self):
        """True when this raw material is mirrored to a FinishedProduct (BR-DUAL-01)."""
        return self.twin_finished_product_id is not None


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

    # ------------------------------------------------------------------
    # SPEC S22 — KG-Equivalent Mass Formulation Engine.
    # Mirrors RawMaterial's kg-equivalent fields so a finished product's
    # batch/target quantities can be expressed and compared in kg, the
    # standard production unit. Purely additive — does not affect
    # sales_unit, stock, or delivery-note/invoicing behaviour.
    # ------------------------------------------------------------------
    KG_EQUIVALENT_MODE_CHOICES = [
        ("direct", "Direct (kg par unité)"),
        ("density", "Densité (kg par litre)"),
    ]
    kg_equivalent_mode = models.CharField(
        max_length=10,
        choices=KG_EQUIVALENT_MODE_CHOICES,
        blank=True,
        verbose_name="Mode d'équivalence kg",
        help_text=(
            "Méthode de conversion en kg pour la standardisation de la production (§22). "
            "Non renseigné = 1 unité = 1 kg par défaut."
        ),
    )
    kg_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Kg par unité",
        help_text="Requis si mode = Direct. Masse en kg d'une unité de ce produit.",
    )
    density_kg_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Densité (kg/L)",
        help_text="Requis si mode = Densité. Unité de vente doit être volumétrique.",
    )
    volumetric_factor = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("1.0000"),
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="Facteur volumétrique",
        help_text="Multiplicateur appliqué à l'équivalent kg pour obtenir le poids volumétrique (§22.6).",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")

    # Row highlight color for the catalog list view — user-chosen via a
    # color picker on the create/edit form. Defaults to the FP list's
    # original violet accent so existing records keep their current look.
    row_color = models.CharField(
        max_length=7,
        default="#7c3aed",
        verbose_name="Couleur de ligne (catalogue)",
        help_text="Couleur utilisée pour distinguer ce produit fini dans la liste.",
    )

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
    # Validation — SPEC S22: kg-equivalent mode (mirrors RawMaterial.clean())
    # ------------------------------------------------------------------
    def clean(self):
        if self.kg_equivalent_mode == "direct":
            if self.kg_per_unit is None:
                raise ValidationError(
                    {"kg_per_unit": "Kg par unité est requis lorsque le mode est Direct."}
                )
        elif self.kg_equivalent_mode == "density":
            if self.density_kg_per_liter is None:
                raise ValidationError(
                    {
                        "density_kg_per_liter": (
                            "La densité (kg/L) est requise lorsque le mode est Densité."
                        )
                    }
                )
            if self.sales_unit_id and not self.sales_unit.is_volumetric:
                raise ValidationError(
                    {
                        "kg_equivalent_mode": (
                            "Le mode Densité nécessite une unité de vente volumétrique "
                            "(litre, mL...)."
                        )
                    }
                )

    # ------------------------------------------------------------------
    # SPEC S22: kg-equivalent (read-only) — falls back to 1 unit = 1 kg.
    # ------------------------------------------------------------------
    @property
    def effective_kg_per_unit(self):
        """How many kg one sales_unit of this product represents.

        Falls back to 1 unit = 1 kg when kg_equivalent_mode has not been
        explicitly configured, so every finished product always has a
        usable kg-equivalent for production standardization (§22).
        """
        if self.kg_equivalent_mode == "direct":
            return self.kg_per_unit
        if self.kg_equivalent_mode == "density":
            return self.density_kg_per_liter
        return Decimal("1.0000")

    # ------------------------------------------------------------------
    # Stock helpers
    # ------------------------------------------------------------------
    def get_current_stock(self, site=None):
        """Current stock quantity (functional spec §25.2.3) — see
        RawMaterial.get_current_stock for the aggregation convention."""
        from django.db.models import Sum

        qs = self.stock_balances.all()
        if site is not None:
            qs = qs.filter(site=site)
        total = qs.aggregate(total=Sum("quantity"))["total"]
        return total if total is not None else Decimal("0.000")

    def get_stock_status(self, site=None):
        current_stock = self.get_current_stock(site=site)
        if current_stock <= Decimal("0"):
            return "stockout"
        if current_stock <= self.alert_threshold:
            return "running_low"
        return "available"

    def get_wac(self, site=None):
        """Weighted Average Cost — read from FinishedProductStockBalance.
        SPEC S3: never user-editable; recomputed via signal after PO closure.
        With no `site`, returns the quantity-weighted average across every
        site's own WAC (falls back to 0.00 with no stock anywhere).
        """
        qs = self.stock_balances.all()
        if site is not None:
            balance = qs.filter(site=site).first()
            return balance.weighted_average_cost if balance else Decimal("0.00")
        total_qty = Decimal("0.000")
        total_cost = Decimal("0.00")
        for balance in qs:
            if balance.quantity > 0:
                total_qty += balance.quantity
                total_cost += balance.quantity * balance.weighted_average_cost
        return (total_cost / total_qty) if total_qty > 0 else Decimal("0.00")

    @property
    def wac(self):
        """Company-wide weighted average cost — see get_wac()."""
        return self.get_wac()

    def get_unit_gross_margin(self):
        return self.reference_selling_price - self.wac

    def get_margin_rate(self):
        if self.reference_selling_price <= 0:
            return Decimal("0.00")
        return (self.get_unit_gross_margin() / self.reference_selling_price) * 100

    # ------------------------------------------------------------------
    # BR-DUAL-01: dual-entry article — mirror image of
    # RawMaterial.is_dual / RawMaterial.twin_finished_product.
    # ------------------------------------------------------------------
    @property
    def is_dual(self):
        """True when this finished product is mirrored to a RawMaterial (BR-DUAL-01)."""
        return hasattr(self, "twin_raw_material")
