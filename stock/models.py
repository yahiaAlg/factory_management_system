# stock/models.py
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

from core.models import PieceJointe


class RawMaterialStockBalance(models.Model):
    """Current stock balance for raw materials, per (site, raw_material)
    (functional spec §25.2.3): a production site physically consumes
    from and receives into its own stockroom, so — once more than one
    ProductionSite exists — a raw material's balance is one row PER SITE,
    not one company-wide row. A single-site factory only ever has one row
    per raw material and sees no behavioural change.

    SPEC BR-RM-05: quantity MUST NOT be set via a form or direct view
    assignment.  The only permitted write paths are:
      - stock.signals.supplier_dn_validated()
      - stock.signals.production_order_closed()
    Both signal handlers call StockMovement.objects.create(), which
    triggers update_stock_balance() below.
    """

    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="raw_material_stock_balances",
        verbose_name="Site",
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.CASCADE, related_name="stock_balances"
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        verbose_name="Quantité en stock",
        editable=False,
    )
    last_movement_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernier mouvement"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Solde stock matière première"
        verbose_name_plural = "Soldes stock matières premières"
        constraints = [
            models.UniqueConstraint(
                fields=["site", "raw_material"], name="uniq_rm_balance_per_site"
            )
        ]

    def __str__(self):
        return (
            f"[{self.site.code}] {self.raw_material.designation} — "
            f"{self.quantity} {self.raw_material.unit_of_measure.symbol}"
        )

    def get_stock_status(self):
        return self.raw_material.get_stock_status(site=self.site)

    def get_stock_value(self):
        return self.quantity * self.raw_material.reference_price


class FinishedProductStockBalance(models.Model):
    """Current stock balance for finished products, per (site,
    finished_product) — mirrors RawMaterialStockBalance (§25.2.3).

    weighted_average_cost is recomputed via signal after every PO closure
    (spec S7) — never user-editable. It is tracked per site, since the two
    sites' production runs (and therefore their actual costs) can differ.
    """

    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="finished_product_stock_balances",
        verbose_name="Site",
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct",
        on_delete=models.CASCADE,
        related_name="stock_balances",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        verbose_name="Quantité en stock",
        editable=False,
    )
    weighted_average_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Coût moyen pondéré",
        editable=False,
    )
    last_movement_date = models.DateTimeField(
        null=True, blank=True, verbose_name="Dernier mouvement"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Solde stock produit fini"
        verbose_name_plural = "Soldes stock produits finis"
        constraints = [
            models.UniqueConstraint(
                fields=["site", "finished_product"], name="uniq_fp_balance_per_site"
            )
        ]

    def __str__(self):
        return (
            f"[{self.site.code}] {self.finished_product.designation} — "
            f"{self.quantity} {self.finished_product.sales_unit.symbol}"
        )

    def get_stock_status(self):
        return self.finished_product.get_stock_status(site=self.site)

    def get_stock_value(self):
        return self.quantity * self.weighted_average_cost

    def update_weighted_average_cost(self):
        """Recompute WAC from this site's production movements (called by signal)."""
        movements = StockMovement.objects.filter(
            site=self.site,
            finished_product=self.finished_product,
            movement_type="production",
            quantity__gt=0,
        ).order_by("movement_date")

        if not movements.exists():
            self.weighted_average_cost = Decimal("0.00")
            self.save(update_fields=["weighted_average_cost"])
            return

        total_cost = Decimal("0.00")
        total_qty = Decimal("0.000")
        for m in movements:
            if m.unit_cost and m.unit_cost > 0:
                total_cost += m.quantity * m.unit_cost
                total_qty += m.quantity

        self.weighted_average_cost = (
            total_cost / total_qty if total_qty > 0 else Decimal("0.00")
        )
        self.save(update_fields=["weighted_average_cost"])


class StockMovement(models.Model):
    """Stock movement history for full traceability.

    Positive quantity = inflow; negative = outflow.
    update_stock_balance() is called from save() to keep balance current,
    but the ONLY callers that may create StockMovements are:
      - stock.signals.supplier_dn_validated()
      - stock.signals.production_order_closed()
      - stock.signals.client_dn_validated()
      - StockAdjustment.approve()
    Never from a form view directly (spec BR-RM-05).
    """

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

    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name="Site",
    )
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

    # BR-DUAL-01: True on the auto-generated mirror movement created for a
    # dual-entry article's other side (RawMaterial ⟷ FinishedProduct, via
    # RawMaterial.twin_finished_product). Prevents the dual-sync signal
    # (stock/signals.py) from mirroring a mirror back onto its source and
    # looping forever.
    is_dual_mirror = models.BooleanField(
        default=False,
        verbose_name="Mouvement miroir (article à double entrée)",
        editable=False,
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-movement_date", "-created_at"]
        indexes = [
            models.Index(fields=["site", "raw_material", "movement_date"]),
            models.Index(fields=["site", "finished_product", "movement_date"]),
            models.Index(fields=["raw_material", "movement_date"]),
            models.Index(fields=["finished_product", "movement_date"]),
            models.Index(fields=["source_document_type", "source_document_id"]),
        ]

    def __str__(self):
        material = self.raw_material or self.finished_product
        site_code = self.site.code if self.site_id else "?"
        return f"[{site_code}] {self.get_movement_type_display()} — {material} — {self.quantity}"

    def save(self, *args, **kwargs):
        if not (
            (self.raw_material and not self.finished_product)
            or (self.finished_product and not self.raw_material)
        ):
            raise ValueError(
                "Exactly one of raw_material or finished_product must be specified."
            )
        if not self.site_id:
            raise ValueError(
                "A StockMovement must specify a site (functional spec §25.2.3)."
            )
        super().save(*args, **kwargs)
        self.update_stock_balance()

    def update_stock_balance(self):
        if self.raw_material:
            balance, _ = RawMaterialStockBalance.objects.get_or_create(
                site=self.site,
                raw_material=self.raw_material,
                defaults={"quantity": Decimal("0.000")},
            )
            total = StockMovement.objects.filter(
                site=self.site, raw_material=self.raw_material
            ).aggregate(total=models.Sum("quantity"))["total"] or Decimal("0.000")
            balance.quantity = total
            balance.last_movement_date = timezone.now()
            balance.save(
                update_fields=["quantity", "last_movement_date", "last_updated"]
            )

        elif self.finished_product:
            balance, _ = FinishedProductStockBalance.objects.get_or_create(
                site=self.site,
                finished_product=self.finished_product,
                defaults={
                    "quantity": Decimal("0.000"),
                    "weighted_average_cost": Decimal("0.00"),
                },
            )
            total = StockMovement.objects.filter(
                site=self.site, finished_product=self.finished_product
            ).aggregate(total=models.Sum("quantity"))["total"] or Decimal("0.000")
            balance.quantity = total
            balance.last_movement_date = timezone.now()
            balance.save(
                update_fields=["quantity", "last_movement_date", "last_updated"]
            )
            balance.update_weighted_average_cost()


class StockAdjustment(models.Model):
    """Stock adjustment for inventory corrections."""

    ADJUSTMENT_TYPE_CHOICES = [
        ("inventory", "Inventaire"),
        ("correction", "Correction"),
        ("loss", "Perte"),
        ("damage", "Avarie"),
        ("return", "Retour"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence ajustement", editable=False
    )
    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="stock_adjustments",
        verbose_name="Site",
    )
    adjustment_type = models.CharField(
        max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, verbose_name="Type d'ajustement"
    )
    adjustment_date = models.DateField(verbose_name="Date ajustement")
    reason = models.TextField(verbose_name="Motif")

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

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Generic attachments (PieceJointe, core.models) — optional supporting
    # documents (e.g. signed inventory count sheet, SD-CORR). Not a hard
    # gate: approve() does NOT require an attachment, so this never blocks
    # the adjustment create/approve forms.
    pieces_jointes = GenericRelation(PieceJointe, related_query_name="stock_adjustment")

    class Meta:
        verbose_name = "Ajustement de stock"
        verbose_name_plural = "Ajustements de stock"
        ordering = ["-adjustment_date"]

    def __str__(self):
        return f"{self.reference} — {self.get_adjustment_type_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            from core.models import DocumentSequence

            year = (
                self.adjustment_date.year
                if self.adjustment_date
                else timezone.now().year
            )
            site_code = self.site.code if self.site_id else None
            self.reference = DocumentSequence.get_next_reference(
                "ADJ", year, site_code=site_code
            )
        super().save(*args, **kwargs)

    def approve(self, user):
        if self.approved_by:
            raise ValueError("Cet ajustement est déjà approuvé.")
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()
        for line in self.lines.all():
            StockMovement.objects.create(
                site=self.site,
                raw_material=line.raw_material,
                finished_product=line.finished_product,
                movement_type="adjustment",
                quantity=line.quantity_adjustment,
                source_document_type="adjustment",
                source_document_id=self.id,
                source_line_id=line.id,
                movement_date=self.adjustment_date,
                created_by=user,
                remarks=f"Ajustement {self.reference} : {self.reason}",
            )


class StockAdjustmentLine(models.Model):
    stock_adjustment = models.ForeignKey(
        StockAdjustment, on_delete=models.CASCADE, related_name="lines"
    )

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

    @property
    def quantity_adjustment(self):
        """Computed — never stored."""
        return self.quantity_after - self.quantity_before

    remarks = models.TextField(blank=True, verbose_name="Observations")

    class Meta:
        verbose_name = "Ligne ajustement stock"
        verbose_name_plural = "Lignes ajustement stock"

    def __str__(self):
        return f"{self.stock_adjustment.reference} — {self.raw_material or self.finished_product}"
