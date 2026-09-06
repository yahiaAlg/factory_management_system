# quality/models.py
"""
QA/QC Laboratory module.

Implements the Functional Specification "QA/QC Laboratory Module" v1.0:
  - Property/Test Catalogue, Quality Specifications, Sampling Plans
  - Sample + Test Result recording (Gates A / B / C)
  - Non-Conformity Reports (NCRs)

BR-QA-01: a gate is enforced for a target only if an active SamplingPlan
exists for that target + control point. No plan => no gate => unmodified
behavior of the base ERP. This module never hard-fails when unconfigured.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import PieceJointe


CONTROL_POINT_CHOICES = [
    ("A", "Gate A — Pré-production (MP entrante)"),
    ("B", "Gate B — Mi-production (en cours)"),
    ("C", "Gate C — Post-production (PF / rendement)"),
]


# ---------------------------------------------------------------------------
# 3.1 Property / Test Catalogue
# ---------------------------------------------------------------------------
class Property(models.Model):
    """A single testable characteristic, reusable across many materials/products."""

    APPLIES_TO_CHOICES = [
        ("raw_material", "Matière première"),
        ("finished_product", "Produit fini"),
        ("both", "Les deux"),
    ]
    DATA_TYPE_CHOICES = [
        ("numeric", "Numérique (valeur unique)"),
        ("range", "Numérique (plage min/max)"),
        ("boolean", "Booléen (Conforme / Non conforme)"),
        ("categorical", "Catégoriel (grade)"),
    ]

    name = models.CharField(max_length=150, unique=True, verbose_name="Propriété")
    applies_to = models.CharField(
        max_length=20, choices=APPLIES_TO_CHOICES, default="both",
        verbose_name="S'applique à",
    )
    unit_label = models.CharField(
        max_length=30, blank=True, verbose_name="Unité",
        help_text="Ex: %, pH, cP, g/cm³, µm, ΔE, °Brix, MPa, CFU/g",
    )
    test_method_reference = models.CharField(
        max_length=200, blank=True, verbose_name="Méthode / référence d'essai",
    )
    result_data_type = models.CharField(
        max_length=20, choices=DATA_TYPE_CHOICES, default="numeric",
        verbose_name="Type de résultat",
    )
    default_precision = models.PositiveSmallIntegerField(
        default=2, verbose_name="Précision (décimales)",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="properties_created", verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Propriété / Test"
        verbose_name_plural = "Catalogue Propriétés / Tests"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.unit_label})" if self.unit_label else self.name


# ---------------------------------------------------------------------------
# 3.2 Quality Specification
# ---------------------------------------------------------------------------
class QualitySpecification(models.Model):
    """Versioned set of acceptance criteria for one Raw Material or one
    Finished Product. Mirrors production.Formulation's versioning pattern."""

    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, null=True, blank=True,
        related_name="quality_specifications", verbose_name="Matière première",
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct", on_delete=models.PROTECT, null=True, blank=True,
        related_name="quality_specifications", verbose_name="Produit fini",
    )
    version = models.PositiveIntegerField(default=1, verbose_name="Version")
    effective_date = models.DateField(default=timezone.now, verbose_name="Date d'effet")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="quality_specs_created", verbose_name="Créée par",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="quality_specs_approved", verbose_name="Approuvée par (QA)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Spécification qualité"
        verbose_name_plural = "Spécifications qualité"
        ordering = ["-effective_date", "-version"]
        # NOTE: a plain unique_together on (raw_material, finished_product, version)
        # does NOT work here: exactly one of raw_material/finished_product is always
        # NULL (see clean() below), and both Django's validate_unique() and the
        # underlying SQL UNIQUE constraint skip the check entirely whenever any
        # field in the tuple is NULL. Two conditional constraints (one per target
        # type) are required instead — these are enforced at the DB level too,
        # not just in full_clean().
        constraints = [
            models.UniqueConstraint(
                fields=["raw_material", "version"],
                condition=models.Q(finished_product__isnull=True),
                name="uniq_quality_spec_version_per_raw_material",
            ),
            models.UniqueConstraint(
                fields=["finished_product", "version"],
                condition=models.Q(raw_material__isnull=True),
                name="uniq_quality_spec_version_per_finished_product",
            ),
        ]

    def __str__(self):
        return f"{self.target} — v{self.version}"

    @property
    def target(self):
        return self.raw_material or self.finished_product

    def clean(self):
        if bool(self.raw_material_id) == bool(self.finished_product_id):
            raise ValidationError(
                "Une spécification qualité doit cibler soit une matière première, "
                "soit un produit fini (pas les deux, pas aucun)."
            )
        # Explicit duplicate-version check. This mirrors the Meta.constraints
        # above at the Python/form level so the error surfaces as a normal
        # ValidationError (caught by ModelForm/full_clean) instead of only as
        # an IntegrityError from the DB — see the Meta.constraints note for why
        # a bare unique_together can't be relied on for this nullable-target
        # design.
        qs = QualitySpecification.objects.exclude(pk=self.pk)
        if self.raw_material_id:
            qs = qs.filter(raw_material_id=self.raw_material_id, version=self.version)
        else:
            qs = qs.filter(finished_product_id=self.finished_product_id, version=self.version)
        if qs.exists():
            raise ValidationError(
                {
                    "version": (
                        f"Une spécification v{self.version} existe déjà pour "
                        f"{self.target}. Incrémentez la version, ou modifiez "
                        f"la spécification existante plutôt que d'en créer une "
                        f"nouvelle."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean(exclude=[f.name for f in self._meta.fields if f.name not in
                                  ("raw_material", "finished_product", "version")])
        if self.is_active:
            # Only one active version per target (mirrors Formulation behavior).
            qs = QualitySpecification.objects.filter(is_active=True)
            if self.raw_material_id:
                qs = qs.filter(raw_material_id=self.raw_material_id)
            else:
                qs = qs.filter(finished_product_id=self.finished_product_id)
            qs.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active_for(cls, target):
        """target: a RawMaterial or FinishedProduct instance."""
        from catalog.models import RawMaterial

        if isinstance(target, RawMaterial):
            return cls.objects.filter(raw_material=target, is_active=True).first()
        return cls.objects.filter(finished_product=target, is_active=True).first()


class QualitySpecLine(models.Model):
    """One tested Property within a QualitySpecification, with its acceptance
    criteria and which gate(s) it is checked at."""

    specification = models.ForeignKey(
        QualitySpecification, on_delete=models.CASCADE, related_name="lines",
        verbose_name="Spécification",
    )
    property = models.ForeignKey(
        Property, on_delete=models.PROTECT, related_name="spec_lines",
        verbose_name="Propriété",
    )
    gate_a = models.BooleanField(default=False, verbose_name="Contrôlé à Gate A")
    gate_b = models.BooleanField(default=False, verbose_name="Contrôlé à Gate B")
    gate_c = models.BooleanField(default=False, verbose_name="Contrôlé à Gate C")

    nominal_value = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        verbose_name="Valeur nominale",
    )
    tolerance_pct = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name="Tolérance (%)",
        help_text="± pourcentage autour de la valeur nominale.",
    )
    hard_min = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="Min absolu",
    )
    hard_max = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="Max absolu",
    )
    is_critical = models.BooleanField(
        default=False, verbose_name="Critique (BR-QA-05)",
        help_text="Un échec sur cette ligne fait échouer tout l'échantillon.",
    )
    expected_boolean = models.BooleanField(
        null=True, blank=True, verbose_name="Résultat attendu (Conforme = coché)",
        help_text="Utilisé si la propriété est de type Booléen.",
    )
    accepted_categories = models.CharField(
        max_length=300, blank=True, verbose_name="Catégories/grades acceptés",
        help_text="Utilisé si la propriété est de type Catégoriel. Valeurs séparées par des virgules.",
    )

    class Meta:
        verbose_name = "Ligne de spécification"
        verbose_name_plural = "Lignes de spécification"
        unique_together = [("specification", "property")]

    def __str__(self):
        return f"{self.specification} — {self.property.name}"

    def applies_to_gate(self, gate):
        return {"A": self.gate_a, "B": self.gate_b, "C": self.gate_c}.get(gate, False)

    def evaluate(self, numeric_value, raw_value=None):
        """Return 'pass' / 'fail' against this line.

        Numeric/range properties are evaluated on `numeric_value` as before.
        Boolean/categorical properties are evaluated on `raw_value` (text)
        against `expected_boolean` / `accepted_categories` — they must not
        fall through the numeric path, where a non-numeric result always
        parses to None and previously came back 'fail' unconditionally.
        BR-QA: hard min/max always win over nominal/tolerance math.
        """
        data_type = self.property.result_data_type

        if data_type == "boolean":
            if raw_value is None or not str(raw_value).strip():
                return "fail"
            normalized = str(raw_value).strip().lower()
            is_true = normalized in ("true", "1", "conforme", "oui", "yes", "pass", "ok")
            is_false = normalized in ("false", "0", "non conforme", "non", "no", "fail", "nok")
            if not (is_true or is_false):
                return "fail"
            result_bool = is_true
            if self.expected_boolean is None:
                # No explicit expectation configured: any recognized value passes.
                return "pass"
            return "pass" if result_bool == self.expected_boolean else "fail"

        if data_type == "categorical":
            if raw_value is None or not str(raw_value).strip():
                return "fail"
            normalized = str(raw_value).strip().lower()
            if not self.accepted_categories.strip():
                # No explicit list configured: any non-empty category passes.
                return "pass"
            accepted = {v.strip().lower() for v in self.accepted_categories.split(",") if v.strip()}
            return "pass" if normalized in accepted else "fail"

        # numeric / range
        if numeric_value is None:
            return "fail"
        if self.hard_min is not None and numeric_value < self.hard_min:
            return "fail"
        if self.hard_max is not None and numeric_value > self.hard_max:
            return "fail"
        if self.nominal_value is not None and self.tolerance_pct is not None:
            tol = self.nominal_value * (self.tolerance_pct / Decimal("100"))
            low, high = self.nominal_value - abs(tol), self.nominal_value + abs(tol)
            return "pass" if low <= numeric_value <= high else "fail"
        # Only hard limits configured (or nothing at all beyond min/max checks above)
        return "pass"


# ---------------------------------------------------------------------------
# 3.3 Sampling Plan
# ---------------------------------------------------------------------------
class SamplingPlan(models.Model):
    """Defines when/how much to sample. BR-QA-01: no active plan for a
    target+gate combination means that gate is simply not enforced."""

    FREQUENCY_CHOICES = [
        ("every", "À chaque occurrence"),
        ("every_nth", "Toutes les N occurrences"),
        ("statistical", "Statistique (AQL) — futur"),
    ]

    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.CASCADE, null=True, blank=True,
        related_name="sampling_plans", verbose_name="Matière première",
    )
    finished_product = models.ForeignKey(
        "catalog.FinishedProduct", on_delete=models.CASCADE, null=True, blank=True,
        related_name="sampling_plans", verbose_name="Produit fini",
    )
    control_point = models.CharField(
        max_length=1, choices=CONTROL_POINT_CHOICES, verbose_name="Point de contrôle",
    )
    trigger_description = models.CharField(
        max_length=200, blank=True, verbose_name="Déclencheur",
        help_text='Ex: "par ligne de BL", "après mélange", "par OP terminé"',
    )
    checkpoint_labels = models.CharField(
        max_length=300, blank=True, verbose_name="Points de contrôle (Gate B)",
        help_text="Libellés séparés par des virgules, ex: Après mélange, Avant conditionnement",
    )
    sample_size_rule = models.CharField(
        max_length=200, blank=True, verbose_name="Règle de taille d'échantillon",
    )
    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default="every", verbose_name="Fréquence",
    )
    frequency_n = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="N (si 'toutes les N occurrences')",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sampling_plans_created", verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_reason = models.CharField(
        max_length=300, blank=True, verbose_name="Motif de désactivation (BR-QA-12)",
    )

    class Meta:
        verbose_name = "Plan d'échantillonnage"
        verbose_name_plural = "Plans d'échantillonnage"
        ordering = ["control_point", "-created_at"]

    def __str__(self):
        target = self.raw_material or self.finished_product or "Toute cible"
        return f"{target} — {self.get_control_point_display()}"

    def clean(self):
        if self.raw_material_id and self.finished_product_id:
            raise ValidationError(
                "Un plan d'échantillonnage cible une matière première OU un "
                "produit fini, pas les deux (laisser les deux vides = tout)."
            )
        if self.control_point == "A" and self.finished_product_id:
            raise ValidationError("Gate A ne s'applique qu'aux matières premières.")
        if self.control_point in ("B", "C") and self.raw_material_id:
            raise ValidationError("Gate B/C ne s'appliquent qu'aux produits finis.")

    def checkpoint_label_list(self):
        return [c.strip() for c in self.checkpoint_labels.split(",") if c.strip()]

    @classmethod
    def get_active_for(cls, control_point, raw_material=None, finished_product=None):
        """BR-QA-01: returns the active plan for this exact target, falling back
        to a factory-wide "any" plan (both target FKs null) if none is target-specific."""
        qs = cls.objects.filter(control_point=control_point, is_active=True)
        if raw_material is not None:
            specific = qs.filter(raw_material=raw_material).first()
        elif finished_product is not None:
            specific = qs.filter(finished_product=finished_product).first()
        else:
            specific = None
        if specific:
            return specific
        return qs.filter(raw_material__isnull=True, finished_product__isnull=True).first()


# ---------------------------------------------------------------------------
# 3.4 / 3.5 Sample + Test Result
# ---------------------------------------------------------------------------
class Sample(models.Model):
    """Physical record of material drawn for testing (Sections 3.4)."""

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("results_pending", "Résultats en attente"),
        ("results_recorded", "Résultats enregistrés"),
        ("conforming", "Conforme"),
        ("non_conforming", "Non conforme"),
        ("conditionally_accepted", "Accepté avec dérogation"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, editable=False, verbose_name="Référence échantillon",
    )
    control_point = models.CharField(
        max_length=1, choices=CONTROL_POINT_CHOICES, verbose_name="Point de contrôle",
    )

    # Source document — exactly one of these is set depending on control_point.
    supplier_dn_line = models.ForeignKey(
        "supplier_ops.SupplierDNLine", on_delete=models.PROTECT, null=True, blank=True,
        related_name="quality_samples", verbose_name="Ligne BL fournisseur (Gate A)",
    )
    production_order = models.ForeignKey(
        "production.ProductionOrder", on_delete=models.PROTECT, null=True, blank=True,
        related_name="quality_samples", verbose_name="Ordre de production (Gate B/C)",
    )
    checkpoint_label = models.CharField(
        max_length=100, blank=True, verbose_name="Point de contrôle (Gate B)",
    )

    quality_specification = models.ForeignKey(
        QualitySpecification, on_delete=models.PROTECT, related_name="samples",
        verbose_name="Version de spécification (verrouillée — BR-QA-04)",
    )

    quantity_sampled = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        verbose_name="Quantité échantillonnée",
    )
    unit = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, null=True, blank=True,
        verbose_name="Unité",
    )

    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default="draft", verbose_name="Statut",
    )

    sampled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="samples_drawn", verbose_name="Prélevé par",
    )
    sampled_at = models.DateTimeField(default=timezone.now, verbose_name="Prélevé le")

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="quality_sample")

    class Meta:
        verbose_name = "Échantillon"
        verbose_name_plural = "Échantillons"
        ordering = ["-sampled_at"]
        indexes = [
            models.Index(fields=["control_point", "status"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.pk and not self.reference:
            from core.models import DocumentSequence

            year = self.sampled_at.year if self.sampled_at else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("ECH", year)
        super().save(*args, **kwargs)

    @property
    def target(self):
        return self.quality_specification.target

    def spec_lines_for_gate(self):
        return self.quality_specification.lines.filter(**{
            {"A": "gate_a", "B": "gate_b", "C": "gate_c"}[self.control_point]: True
        })

    # ------------------------------------------------------------------
    # BR-QA-05 / 3.5: overall outcome computation
    # ------------------------------------------------------------------
    def compute_outcome(self):
        """Recompute and persist the Sample's overall status from its TestResults.
        BR-QA-05: any un-overridden failing Critical property fails the whole
        sample. Otherwise, any un-overridden failing property fails the sample
        (default "any single non-critical failure" threshold per spec 3.5)."""
        results = list(self.results.select_related("spec_line"))
        if not results:
            self.status = "results_pending"
            self.save(update_fields=["status"])
            return self.status

        any_override = False
        any_fail = False
        for r in results:
            if r.qa_override:
                any_override = True
                continue
            if r.outcome == "fail":
                any_fail = True

        if any_fail:
            self.status = "non_conforming"
        elif any_override:
            self.status = "conditionally_accepted"
        else:
            self.status = "conforming"
        self.save(update_fields=["status"])
        return self.status

    def is_conforming(self):
        return self.status in ("conforming", "conditionally_accepted")


class TestResult(models.Model):
    """One recorded result row per QualitySpecLine tested on a Sample."""

    OUTCOME_CHOICES = [
        ("pass", "Conforme"),
        ("fail", "Non conforme"),
    ]

    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="results")
    spec_line = models.ForeignKey(
        QualitySpecLine, on_delete=models.PROTECT, related_name="test_results",
        verbose_name="Ligne de spécification",
    )

    recorded_value = models.CharField(max_length=200, verbose_name="Valeur relevée")
    recorded_numeric = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        verbose_name="Valeur numérique (calcul pass/fail)",
    )
    outcome = models.CharField(
        max_length=10, choices=OUTCOME_CHOICES, verbose_name="Résultat calculé",
    )
    instrument_method = models.CharField(
        max_length=200, blank=True, verbose_name="Instrument / méthode utilisée",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="test_results_recorded", verbose_name="Enregistré par",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    # BR-QA-08: QA-only override of an automatic Fail.
    qa_override = models.BooleanField(default=False, verbose_name="Dérogation QA")
    override_justification = models.TextField(
        blank=True, verbose_name="Justification de la dérogation",
    )
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="test_results_overridden", verbose_name="Dérogation accordée par",
    )
    overridden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Résultat de test"
        verbose_name_plural = "Résultats de test"
        unique_together = [("sample", "spec_line")]

    def __str__(self):
        return f"{self.sample.reference} — {self.spec_line.property.name}: {self.recorded_value}"

    def save(self, *args, **kwargs):
        # Compute outcome automatically unless already fixed by evaluate().
        if not self.pk or self.outcome not in ("pass", "fail"):
            self.outcome = self.spec_line.evaluate(self.recorded_numeric, self.recorded_value)
        super().save(*args, **kwargs)

    def apply_qa_override(self, user, justification):
        """BR-QA-08: only ever Fail -> Accepted with Deviation, never the reverse,
        and always requires a justification note."""
        if self.outcome != "fail":
            raise ValidationError("La dérogation QA ne s'applique qu'à un résultat en échec.")
        if not justification or not justification.strip():
            raise ValidationError("Une justification est obligatoire pour toute dérogation QA.")
        self.qa_override = True
        self.override_justification = justification
        self.overridden_by = user
        self.overridden_at = timezone.now()
        self.save()
        self.sample.compute_outcome()


# ---------------------------------------------------------------------------
# Section 7 — Non-Conformity Reports
# ---------------------------------------------------------------------------
class NonConformityReport(models.Model):
    """Single structured record used across all three gates whenever something
    fails (Section 7)."""

    TRIGGER_CHOICES = [
        ("failed_sample", "Échantillon en échec"),
        ("inprocess_hold", "Alerte en cours de production (Gate B)"),
        ("yield_deviation", "Écart de rendement / consommation"),
        ("manual", "Ouverture manuelle"),
    ]
    ROOT_CAUSE_CHOICES = [
        ("supplier_quality", "Qualité fournisseur"),
        ("equipment", "Équipement"),
        ("process_operator", "Process / Opérateur"),
        ("formula_design", "Conception formule"),
        ("measurement_error", "Erreur de mesure / échantillonnage"),
        ("environmental", "Environnemental"),
        ("other", "Autre"),
    ]
    DISPOSITION_CHOICES = [
        ("return_to_supplier", "Retour fournisseur"),
        ("scrap", "Mise au rebut"),
        ("rework", "Retraitement"),
        ("accept_deviation", "Acceptation avec dérogation"),
        ("accept_no_action", "Acceptation — aucune action requise"),
    ]
    STATUS_CHOICES = [
        ("open", "Ouverte"),
        ("under_review", "En cours d'analyse"),
        ("dispositioned", "Dispositionnée"),
        ("closed", "Clôturée"),
    ]
    GATE_CHOICES = CONTROL_POINT_CHOICES

    VALID_TRANSITIONS = {
        "open": ["under_review", "dispositioned"],
        "under_review": ["dispositioned"],
        "dispositioned": ["closed"],
        "closed": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, editable=False, verbose_name="Référence NCR",
    )
    gate = models.CharField(max_length=1, choices=GATE_CHOICES, verbose_name="Gate")
    trigger_type = models.CharField(
        max_length=20, choices=TRIGGER_CHOICES, verbose_name="Type de déclencheur",
    )

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, null=True, blank=True,
        related_name="ncrs", verbose_name="Échantillon lié",
    )
    supplier_dn_line = models.ForeignKey(
        "supplier_ops.SupplierDNLine", on_delete=models.PROTECT, null=True, blank=True,
        related_name="ncrs", verbose_name="Ligne BL fournisseur liée",
    )
    production_order = models.ForeignKey(
        "production.ProductionOrder", on_delete=models.PROTECT, null=True, blank=True,
        related_name="ncrs", verbose_name="Ordre de production lié",
    )

    description = models.TextField(verbose_name="Description")
    root_cause_category = models.CharField(
        max_length=30, choices=ROOT_CAUSE_CHOICES, blank=True, verbose_name="Cause racine",
    )
    root_cause_detail = models.TextField(blank=True, verbose_name="Détail cause racine")
    corrective_action = models.TextField(blank=True, verbose_name="Action corrective")
    disposition = models.CharField(
        max_length=25, choices=DISPOSITION_CHOICES, blank=True, verbose_name="Disposition",
    )

    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default="open", verbose_name="Statut",
    )

    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
        related_name="ncrs_opened", verbose_name="Ouverte par",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="ncrs_closed", verbose_name="Clôturée par (QA uniquement — BR-QA-09)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="ncr")

    class Meta:
        verbose_name = "Non-Conformité (NCR)"
        verbose_name_plural = "Non-Conformités (NCR)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "gate"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.pk and not self.reference:
            from core.models import DocumentSequence

            self.reference = DocumentSequence.get_next_reference(
                "NCR", timezone.now().year
            )
        super().save(*args, **kwargs)

    def _transition(self, new_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(f"Transition NCR invalide : {self.status} → {new_status}.")
        self.status = new_status

    def disposition_action(self, user, disposition, corrective_action, root_cause_category="",
                            root_cause_detail=""):
        """QA Manager records the analysis and disposition (7.4). BR-QA-11:
        Return to Supplier / Scrap / Accept with Deviation require a proof
        document — enforced here by checking pieces_jointes already attached."""
        if disposition in ("return_to_supplier", "scrap", "accept_deviation"):
            if not self.pieces_jointes.exists():
                raise ValidationError(
                    "BR-QA-11 : un document justificatif est obligatoire pour "
                    "cette disposition (retour fournisseur / rebut / dérogation)."
                )
        if self.status == "open":
            self._transition("under_review")
        self.disposition = disposition
        self.corrective_action = corrective_action
        self.root_cause_category = root_cause_category
        self.root_cause_detail = root_cause_detail
        self._transition("dispositioned")
        self.save()

    def close(self, user):
        """BR-QA-09: only a QA Manager (or Manager/Admin override) may close an NCR."""
        profile = getattr(user, "userprofile", None)
        if not profile or not profile.can_close_ncr():
            raise ValidationError("Seul un Responsable QA peut clôturer une NCR (BR-QA-09).")
        if not self.disposition:
            raise ValidationError("Une disposition doit être enregistrée avant clôture.")
        self._transition("closed")
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save()
