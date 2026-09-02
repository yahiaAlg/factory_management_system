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
        default=Decimal("1000.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité de référence du lot",
        help_text="Production standardisée en kg — 1000 kg par défaut.",
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

    # SPEC S22.3 (planned): target total mass in kg for one reference batch.
    # Required for a formulation that uses a complement line (§22.4);
    # otherwise optional/informational only.
    target_batch_mass_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Masse cible du lot (kg)",
        help_text="Masse totale, en kg, du lot de référence — requis si une ligne complément est utilisée (§22).",
    )

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

        # SPEC S22.4 (planned): mass reconciliation for formulations that
        # declare a target_batch_mass_kg. Only runs once lines exist (i.e.
        # on an already-saved formulation — new formulations get their
        # lines added afterwards via the inline formset).
        if self.pk and self.target_batch_mass_kg is not None:
            complement_lines = [l for l in self.lines.all() if l.is_complement]
            if len(complement_lines) > 1:
                raise ValidationError(
                    "Au plus une ligne de formulation peut être marquée comme complément (§22.4)."
                )
            non_complement_mass = self.non_complement_mass_kg
            if complement_lines:
                if non_complement_mass >= self.target_batch_mass_kg:
                    raise ValidationError(
                        {
                            "target_batch_mass_kg": (
                                "Les autres ingrédients atteignent ou dépassent déjà la masse cible "
                                "du lot ; il n'y a pas de place pour un complément (§22.4)."
                            )
                        }
                    )
            else:
                from core.models import SystemParameter

                epsilon = SystemParameter.get_decimal_value(
                    "reconciliation_tolerance_epsilon", Decimal("500.00")
                )
                total_mass = sum(
                    (line.kg_equivalent or Decimal("0.000")) for line in self.lines.all()
                )
                if abs(total_mass - self.target_batch_mass_kg) > epsilon:
                    raise ValidationError(
                        {
                            "target_batch_mass_kg": (
                                "Sans ligne complément, la somme des équivalents kg des lignes doit "
                                "correspondre à la masse cible du lot (tolérance de réconciliation "
                                f"système : {epsilon} kg) (§22.4)."
                            )
                        }
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
                is_complement=line.is_complement,
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

    # ------------------------------------------------------------------
    # SPEC S22.3/22.4 (planned): KG-Equivalent Mass Formulation Engine
    # ------------------------------------------------------------------
    @property
    def non_complement_mass_kg(self):
        """Sum of kg_equivalent across every non-complement line (§22.3)."""
        return sum(
            (line.kg_equivalent or Decimal("0.000"))
            for line in self.lines.filter(is_complement=False)
        )

    def get_complement_line(self):
        return self.lines.filter(is_complement=True).first()

    def recompute_complement_quantity(self):
        """Recompute and persist the complement line's qty_per_batch (§22.4).

        qty_per_batch = (target_batch_mass_kg - non_complement_mass_kg) / complement.raw_material.effective_kg_per_unit

        No-op if there is no complement line or no target_batch_mass_kg set.
        Called whenever a sibling line or target_batch_mass_kg changes.
        """
        complement = self.get_complement_line()
        if complement is None or self.target_batch_mass_kg is None:
            return
        kg_per_unit = complement.raw_material.effective_kg_per_unit
        if not kg_per_unit:
            return
        remaining_mass = self.target_batch_mass_kg - self.non_complement_mass_kg
        if remaining_mass <= 0:
            raise ValidationError(
                "Les autres ingrédients atteignent ou dépassent déjà la masse cible "
                "du lot ; il n'y a pas de place pour un complément (§22.4)."
            )
        complement.qty_per_batch = remaining_mass / kg_per_unit
        FormulationLine.objects.filter(pk=complement.pk).update(
            qty_per_batch=complement.qty_per_batch
        )


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

    # SPEC S22.4 (planned): marks this line as the formula's auto-balancing
    # ingredient. At most one per formulation (enforced in Formulation.clean()
    # and here). qty_per_batch on a complement line is computed, not entered
    # by hand — see Formulation.recompute_complement_quantity().
    is_complement = models.BooleanField(
        default=False,
        verbose_name="Complément",
        help_text="Quantité calculée automatiquement pour atteindre la masse cible du lot (§22.4).",
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

    # ------------------------------------------------------------------
    # SPEC S22.3/22.6 (planned): KG-Equivalent Mass Formulation Engine
    # ------------------------------------------------------------------
    @property
    def kg_equivalent(self):
        """qty_per_batch expressed in kg via the raw material's kg pivot (§22.3).

        Returns None if the raw material has no kg_equivalent_mode configured.
        """
        kg_per_unit = self.raw_material.effective_kg_per_unit
        if kg_per_unit is None:
            return None
        return self.qty_per_batch * kg_per_unit

    @property
    def volumetric_weight(self):
        """Informational bulk/logistics weight (§22.6) — not used in mass
        reconciliation or stock accounting."""
        kg_eq = self.kg_equivalent
        if kg_eq is None:
            return None
        return kg_eq * self.raw_material.volumetric_factor

    def clean(self):
        # SPEC S22.4: at most one complement line per formulation.
        if self.is_complement and self.formulation_id:
            other_complement = (
                self.formulation.lines.filter(is_complement=True)
                .exclude(pk=self.pk)
                .exists()
            )
            if other_complement:
                raise ValidationError(
                    {
                        "is_complement": (
                            "Cette formulation a déjà une ligne complément (§22.4) : "
                            "une seule est autorisée."
                        )
                    }
                )
            if self.raw_material_id and self.raw_material.effective_kg_per_unit is None:
                raise ValidationError(
                    {
                        "is_complement": (
                            "La matière première choisie comme complément doit avoir un "
                            "équivalent kg configuré (§22.5)."
                        )
                    }
                )


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
        # --- QA/QC Gate C (functional spec §6.2) ---
        ("pending_qc_release", "En attente de libération QC"),
        ("completed_investigation", "Terminé — Sous investigation"),
        # ---
        ("completed", "Terminé"),
        ("cancelled", "Annulé"),
    ]

    # Amended by QA/QC Gate C (functional spec §6.2, §10.3)
    VALID_TRANSITIONS = {
        "pending": ["validated", "cancelled"],
        "validated": ["in_progress", "cancelled"],
        "in_progress": ["pending_qc_release", "completed", "cancelled"],
        "pending_qc_release": ["completed", "completed_investigation"],
        "completed_investigation": ["completed", "cancelled"],
        "completed": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence OP", editable=False
    )
    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Site",
        help_text=(
            "Site où l'ordre est exécuté (fonc. spec §25.2.3) : la matière "
            "première est consommée depuis le stock de CE site, et le "
            "produit fini y est ajouté."
        ),
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
        max_length=25, choices=STATUS_CHOICES, default="pending", verbose_name="Statut"
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

    # --- QA/QC Gate B (functional spec §5) — soft/advisory hold ---
    gate_b_hold = models.BooleanField(
        default=False, verbose_name="Alerte QC en cours (Gate B)",
    )
    gate_b_hold_note = models.TextField(blank=True, verbose_name="Note d'alerte Gate B")
    gate_b_hold_acknowledged = models.BooleanField(
        default=False, verbose_name="Alerte Gate B acquittée (BR-QA-07)",
    )
    gate_b_ack_note = models.TextField(blank=True, verbose_name="Note d'acquittement")
    gate_b_ack_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name="gate_b_acks", verbose_name="Alerte acquittée par",
    )

    # --- QA/QC Gate C (functional spec §6) ---
    scrapped = models.BooleanField(
        default=False, verbose_name="Rebuté (disposition NCR = Scrap)",
        help_text="Si vrai, aucun stock PF n'est crédité à la clôture (§6.5).",
    )

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

    # ------------------------------------------------------------------
    # BOM reconciliation / correction mechanism: when a formulation gets a
    # new version that adds/removes raw materials, an old production order
    # can be "corrected" — a brand-new order is created against the new
    # formulation version for a (possibly re-specified) target quantity,
    # with consumption lines pre-filled from the new formula's ratios.
    # The original order is left untouched; this FK links the correction
    # forward to it. Self-referential, so a correction can itself later be
    # corrected again if the formula evolves further.
    # ------------------------------------------------------------------
    corrects_order = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name="Corrige l'OP",
        help_text="Renseigné uniquement pour un ordre de correction — pointe vers l'OP d'origine.",
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
                site_code = self.site.code if self.site_id else None
                self.reference = DocumentSequence.get_next_reference(
                    "OP", year, site_code=site_code
                )
            if self.formulation and not self.formulation_version:
                self.formulation_version = self.formulation.version
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # SPEC S22 (planned): target quantity expressed in kg — mirrors
    # FormulationLine.kg_equivalent, using the finished product's
    # kg-equivalent pivot (always resolves thanks to the 1kg=1unit
    # fallback). Purely informational; does not affect target_qty/target_unit.
    # ------------------------------------------------------------------
    @property
    def target_qty_kg(self):
        kg_per_unit = self.formulation.finished_product.effective_kg_per_unit
        if kg_per_unit is None:
            return None
        return self.target_qty * kg_per_unit

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
        in_progress → completed | pending_qc_release (functional spec §6.2).

        SPEC BR-PROD-05 / BR-QA-06: uses qty_actual (not qty_theoretical) for
        RM stock deductions — handled by the post_save signal in
        production/signals.py, NOT called directly here. RM deduction happens
        regardless of the QC/yield gate outcome (BR-QA-06); only the
        finished-goods credit is held pending QC release.

        BR-QA-07: cannot close cleanly while an unacknowledged Gate B hold
        is outstanding.

        consumption_data: {raw_material_id: actual_qty, ...}
        """
        if self.gate_b_hold and not self.gate_b_hold_acknowledged:
            raise ValidationError(
                "BR-QA-07 : une alerte qualité Gate B n'a pas été acquittée par "
                "le Responsable Production — impossible de clôturer l'OP."
            )

        gate_c_required = self._gate_c_required()
        self._transition("pending_qc_release" if gate_c_required else "completed")
        self.actual_qty_produced = actual_qty_produced
        self.closure_date = timezone.now().date()
        self.closed_by = user
        self.save()

        # Record actual consumption on lines — fires regardless of gate C
        # outcome (BR-QA-06); the consumption signal checks for a status in
        # {completed, pending_qc_release, completed_investigation}.
        for material_id, actual_qty in consumption_data.items():
            try:
                line = self.consumption_lines.get(raw_material_id=material_id)
                line.qty_actual = actual_qty
                line.save()
            except ProductionOrderLine.DoesNotExist:
                pass
        # Signal production.signals.* handles RM deductions + FG credit
        # (only when status == completed) + WAC recalculation (spec S7).

    def cancel(self, user):
        """pending or in_progress → cancelled."""
        self._transition("cancelled")
        self.save()

    # ------------------------------------------------------------------
    # QA/QC Gate B helpers (functional spec §5)
    # ------------------------------------------------------------------
    def record_checkpoint_hold(self, note):
        """A Gate B sample came back Non-Conforming: raise the advisory hold
        flag. Does NOT change self.status (§5.3/§5.4 — the state machine is
        never blocked by Gate B)."""
        self.gate_b_hold = True
        self.gate_b_hold_note = note
        self.gate_b_hold_acknowledged = False
        self.save(update_fields=["gate_b_hold", "gate_b_hold_note", "gate_b_hold_acknowledged"])

    def acknowledge_hold(self, user, note, abort=False):
        """Production Manager acknowledges a Gate B hold (§5.3). Acknowledging
        is not resolving — it records that the hold was seen and a decision
        made. If abort=True, the order is cancelled and an NCR auto-opened."""
        self.gate_b_hold_acknowledged = True
        self.gate_b_ack_note = note
        self.gate_b_ack_by = user
        self.save(update_fields=["gate_b_hold_acknowledged", "gate_b_ack_note", "gate_b_ack_by"])
        if abort:
            self.cancel(user)
            from quality.models import NonConformityReport

            NonConformityReport.objects.create(
                gate="B",
                trigger_type="inprocess_hold",
                production_order=self,
                description=(
                    f"OP {self.reference} avorté suite à une alerte Gate B non "
                    f"résolue : {self.gate_b_hold_note}"
                ),
                opened_by=user,
            )

    # ------------------------------------------------------------------
    # QA/QC Gate C helpers (functional spec §6)
    # ------------------------------------------------------------------
    def _gate_c_required(self):
        """BR-QA-01: Gate C only applies if an active Gate-C Sampling Plan
        exists for this finished product, OR the yield/consumption outcome
        itself mandates a review (BR-QA-10)."""
        from quality.models import SamplingPlan

        if SamplingPlan.get_active_for(
            "C", finished_product=self.formulation.finished_product
        ):
            return True
        return self._quantitative_deviation_requires_review()

    def _quantitative_deviation_requires_review(self):
        """BR-QA-10: a 'critical' yield_status always triggers review; a
        'warning' yield_status triggers one too (v1: no per-formulation
        standing-deviation exemption configured yet)."""
        if self.yield_status in ("critical", "warning"):
            return True
        return any(
            not line.is_within_tolerance()
            for line in self.consumption_lines.all()
            if line.qty_actual is not None
        )

    def gate_c_sample_conforming(self):
        """Latest Gate C sample outcome for this order, or None if none drawn."""
        sample = self.quality_samples.filter(control_point="C").order_by("-sampled_at").first()
        if not sample:
            return None
        return sample.is_conforming()

    def release_gate_c(self, user):
        """pending_qc_release -> completed | completed_investigation (§6.2).

        Physical/quality check (sample) AND quantitative check (yield/tolerance)
        must both be clean for a direct release to 'completed'; otherwise the
        order moves to 'completed_investigation' and a mandatory NCR is opened
        (§6.4), pre-populated with the specific out-of-tolerance lines."""
        if self.status != "pending_qc_release":
            raise ValidationError("Cet OP n'est pas en attente de libération QC.")

        sample_ok = self.gate_c_sample_conforming()
        quantitative_ok = not self._quantitative_deviation_requires_review()

        if sample_ok in (True, None) and quantitative_ok:
            self._transition("completed")
            self.save()
            return "completed"

        self._transition("completed_investigation")
        self.save()

        from quality.models import NonConformityReport

        if not self.ncrs.filter(trigger_type="yield_deviation", status__in=["open", "under_review", "dispositioned"]).exists():
            deviating = [
                f"{l.raw_material.designation}: écart {l.get_variance_percentage():.1f}%"
                for l in self.consumption_lines.all()
                if l.qty_actual is not None and not l.is_within_tolerance()
            ]
            NonConformityReport.objects.create(
                gate="C",
                trigger_type="yield_deviation" if quantitative_ok is False else "failed_sample",
                production_order=self,
                sample=self.quality_samples.filter(control_point="C").order_by("-sampled_at").first(),
                description=(
                    f"OP {self.reference} : rendement={self.yield_rate}, "
                    f"statut={self.yield_status}. Écarts: {', '.join(deviating) or 'n/a'}."
                ),
                opened_by=user,
            )
        return "completed_investigation"

    def resolve_investigation(self, user, disposition):
        """completed_investigation -> completed | stays scrapped (§6.4-6.5).

        Called once the linked NCR has been dispositioned by QA. 'scrap' does
        not credit finished stock (write-off instead, per §6.5); any other
        disposition credits stock as a normal completion."""
        if self.status != "completed_investigation":
            raise ValidationError("Cet OP n'est pas sous investigation.")
        if disposition == "scrap":
            self.scrapped = True
        self._transition("completed")
        self.save()

    # ------------------------------------------------------------------
    def _check_stock_availability(self):
        # SPEC §25.2.3 — must be scoped to THIS order's site: a bare
        # RawMaterialStockBalance.objects.get(raw_material=...) with no
        # site filter would silently read/consume another site's stock
        # once more than one ProductionSite exists (the exact bug the
        # spec calls out — confirming an order at Site B could silently
        # consume Site A's stock).
        insufficient = []
        for line in self.consumption_lines.all():
            from stock.models import RawMaterialStockBalance

            try:
                balance = RawMaterialStockBalance.objects.get(
                    site=self.site, raw_material=line.raw_material
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
        """Scale formulation lines to target_qty.

        Correction orders (self.corrects_order_id is set) already have their
        consumption lines populated from the reconciliation tool at creation
        time — the reconciled quantities may deliberately differ from a
        straight proportional scaling, so they must never be regenerated
        here. Only ever a no-op for correction orders; unaffected for
        ordinary orders.
        """
        if self.corrects_order_id:
            return
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

    # ------------------------------------------------------------------
    # SPEC S22 (planned): kg-equivalent view of the consumption line —
    # mirrors FormulationLine.kg_equivalent, using the raw material's
    # effective_kg_per_unit (always resolves thanks to the 1kg=1unit
    # fallback). Purely informational; qty_theoretical/qty_actual remain
    # the stored/authoritative values in the raw material's native unit.
    # ------------------------------------------------------------------
    @property
    def qty_theoretical_kg(self):
        kg_per_unit = self.raw_material.effective_kg_per_unit
        if kg_per_unit is None:
            return None
        return self.qty_theoretical * kg_per_unit

    @property
    def qty_actual_kg(self):
        if self.qty_actual is None:
            return None
        kg_per_unit = self.raw_material.effective_kg_per_unit
        if kg_per_unit is None:
            return None
        return self.qty_actual * kg_per_unit

    @property
    def delta_qty_kg(self):
        if self.qty_actual_kg is not None and self.qty_theoretical_kg is not None:
            return self.qty_actual_kg - self.qty_theoretical_kg
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
