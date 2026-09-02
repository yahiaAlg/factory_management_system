"""
core/management/commands/seed_scenario_adjuvant_gate_a.py

Standalone scenario seed: "Adjuvant pour béton — Contrôle Gate A" (see
scenario_adjuvant_beton_gate_a.md). Demonstrates the QA/QC module on a
liquid concrete admixture raw material, whose acceptance criteria mix
numeric tests (densité, pH, matière sèche, chlorures) with a non-numeric
one (Aspect/couleur/homogénéité — boolean Conforme/Non conforme).

This exercises the QualitySpecLine.evaluate() boolean/categorical path
(previously always resolved to "fail" for non-numeric properties, since
evaluate() only ever looked at recorded_numeric).

Pre-requisite: minimal_populate_db has run (units KG/L, an 'admin' user,
QA/QC users 'qualite'/'laboratoire').

Usage:
    python manage.py minimal_populate_db --flush
    python manage.py seed_scenario_adjuvant_gate_a
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _ok(self, msg):
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _skip(self, msg):
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg} — already exists, skipped"))


def _attach(obj, doc_type, filename, user):
    """Attach a placeholder PieceJointe of the given type, unless already present
    (mirrors seed_phase1_supplier_bl_invoice_bidon_vert._attach)."""
    from core.models import PieceJointe

    ct = ContentType.objects.get_for_model(obj)
    if PieceJointe.objects.filter(
        content_type=ct, object_id=obj.pk, type_document=doc_type
    ).exists():
        return
    PieceJointe.objects.create(
        content_type=ct,
        object_id=obj.pk,
        fichier=ContentFile(
            f"Document justificatif seed — {filename}".encode(), name=filename
        ),
        type_document=doc_type,
        description=f"Pièce jointe seed ({doc_type})",
        uploaded_by=user,
    )


class Command(BaseCommand):
    help = (
        "Scenario seed: Gate A sur un adjuvant liquide pour béton (RM-ADJ-01) — "
        "démontre l'évaluation booléenne/catégorielle de QualitySpecLine.evaluate()."
    )

    def handle(self, *args, **options):
        from catalog.models import RawMaterial, RawMaterialCategory, UnitOfMeasure
        from suppliers.models import Supplier
        from supplier_ops.models import SupplierDN, SupplierDNLine
        from core.utils import get_seed_site
        from quality.models import (
            Property,
            QualitySpecification,
            QualitySpecLine,
            SamplingPlan,
            Sample,
            TestResult,
        )

        main_site = get_seed_site(self)

        try:
            admin = User.objects.get(username="admin")
            qa_manager = User.objects.get(username="qualite")
            qc_tech = User.objects.get(username="laboratoire")
        except User.DoesNotExist as exc:
            raise CommandError(
                "Comptes requis introuvables — lancez d'abord "
                "'python manage.py minimal_populate_db --flush'. "
                f"({exc})"
            )

        try:
            litre = UnitOfMeasure.objects.get(code="L")
        except UnitOfMeasure.DoesNotExist:
            raise CommandError(
                "Unité 'L' introuvable — lancez d'abord minimal_populate_db."
            )

        with transaction.atomic():
            # ================================================================
            # Catalogue — fournisseur + matière première (adjuvant liquide)
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Fournisseur & Catalogue"))
            supplier, created = Supplier.objects.get_or_create(
                code="F-0002",
                defaults=dict(
                    raison_sociale="CHIMADJUV SPA",
                    forme_juridique="SPA",
                    nif="000219876543210",
                    nis="099919876543",
                    rc="19/00-7654321B26",
                    ai="19876543210",
                    address="Zone Industrielle Est, Sétif",
                    wilaya="Sétif",
                    phone="036709988",
                    email="contact@chimadjuv.dz",
                    contact_person="Nadia Cherifi",
                    created_by=admin,
                ),
            )
            (
                _ok(self, f"{supplier.code} — {supplier.raison_sociale}")
                if created
                else _skip(self, supplier.code)
            )

            category, _created = RawMaterialCategory.objects.get_or_create(
                name="Adjuvants béton",
                defaults=dict(
                    description="Adjuvants chimiques pour béton et béton projeté"
                ),
            )

            rm, created = RawMaterial.objects.get_or_create(
                designation="Accélérateur de prise (base sulfate d'aluminium)",
                defaults=dict(
                    category=category,
                    unit_of_measure=litre,
                    default_supplier=supplier,
                    reference_price=Decimal("420.00"),
                    alert_threshold=Decimal("50.000"),
                    stockout_threshold=Decimal("10.000"),
                    created_by=admin,
                ),
            )
            (
                _ok(self, f"{rm.reference} — {rm.designation}")
                if created
                else _skip(self, rm.reference)
            )

            # ================================================================
            # Module QA/QC — Propriétés, Spécification, Plan d'échantillonnage
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Module QA/QC — Adjuvant"))

            props_spec = [
                # (name, applies_to, unit, data_type, test_method)
                (
                    "Aspect / couleur / homogénéité",
                    "raw_material",
                    "",
                    "boolean",
                    "Contrôle visuel — absence de séparation/précipitation",
                ),
                ("pH adjuvant", "raw_material", "pH", "numeric", "pH-mètre"),
                (
                    "Masse volumique adjuvant",
                    "raw_material",
                    "g/cm³",
                    "numeric",
                    "Densimètre / balance hydrostatique",
                ),
                (
                    "Teneur en matières sèches",
                    "raw_material",
                    "%",
                    "numeric",
                    "Dessiccation 105°C — EN 480-8",
                ),
                (
                    "Teneur en chlorures (Cl-)",
                    "raw_material",
                    "%",
                    "numeric",
                    "Titrage potentiométrique — EN 480-10",
                ),
            ]
            properties = {}
            for name, applies_to, unit, dtype, method in props_spec:
                prop, created = Property.objects.get_or_create(
                    name=name,
                    defaults=dict(
                        applies_to=applies_to,
                        unit_label=unit,
                        result_data_type=dtype,
                        test_method_reference=method,
                        created_by=admin,
                    ),
                )
                properties[name] = prop
                (
                    _ok(self, f"Propriété '{name}' ({dtype})")
                    if created
                    else _skip(self, f"Propriété '{name}'")
                )

            spec = QualitySpecification.get_active_for(rm)
            if spec:
                _skip(self, f"Spécification {rm.designation} déjà active")
            else:
                spec = QualitySpecification.objects.create(
                    raw_material=rm,
                    version=1,
                    effective_date=datetime.date(2026, 6, 1),
                    is_active=True,
                    created_by=admin,
                )
                lines_spec = [
                    # (property, gate_a, nominal, tol_pct, hard_min, hard_max, critical, exp_bool, categories)
                    (
                        properties["Aspect / couleur / homogénéité"],
                        True,
                        None,
                        None,
                        None,
                        None,
                        True,
                        True,
                        "",
                    ),
                    (
                        properties["pH adjuvant"],
                        True,
                        Decimal("3.0"),
                        Decimal("20"),
                        None,
                        None,
                        False,
                        None,
                        "",
                    ),
                    (
                        properties["Masse volumique adjuvant"],
                        True,
                        Decimal("1.28"),
                        Decimal("3"),
                        None,
                        None,
                        True,
                        None,
                        "",
                    ),
                    (
                        properties["Teneur en matières sèches"],
                        True,
                        Decimal("40.0"),
                        Decimal("5"),
                        None,
                        None,
                        False,
                        None,
                        "",
                    ),
                    (
                        properties["Teneur en chlorures (Cl-)"],
                        True,
                        None,
                        None,
                        None,
                        Decimal("0.10"),
                        True,
                        None,
                        "",
                    ),
                ]
                for prop, ga, nom, tol, hmin, hmax, crit, exp_bool, cats in lines_spec:
                    QualitySpecLine.objects.create(
                        specification=spec,
                        property=prop,
                        gate_a=ga,
                        nominal_value=nom,
                        tolerance_pct=tol,
                        hard_min=hmin,
                        hard_max=hmax,
                        is_critical=crit,
                        expected_boolean=exp_bool,
                        accepted_categories=cats,
                    )
                _ok(
                    self,
                    f"Spécification qualité v1 — {rm.reference} (5 lignes, Gate A)",
                )

            plan, created = SamplingPlan.objects.get_or_create(
                raw_material=rm,
                control_point="A",
                is_active=True,
                defaults=dict(
                    trigger_description="Par lot / livraison",
                    sample_size_rule="1 échantillon de 1 L par lot",
                    frequency="every",
                    created_by=admin,
                ),
            )
            (
                _ok(self, f"Plan d'échantillonnage actif — Gate A ({rm.reference})")
                if created
                else _skip(self, "Plan Gate A")
            )

            # ================================================================
            # BL Fournisseur — déclenche Gate A
            # ================================================================
            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ BL Fournisseur — Lot conforme")
            )
            dn = SupplierDN.objects.filter(
                external_reference="BL-CHIMADJUV-2026-011"
            ).first()
            if dn:
                _skip(self, dn.reference)
            else:
                dn = SupplierDN.objects.create(
                    site=main_site,
                    external_reference="BL-CHIMADJUV-2026-011",
                    supplier=supplier,
                    delivery_date=datetime.date(2026, 6, 5),
                    remarks="Livraison adjuvant — lot L2026-0611.",
                    created_by=admin,
                )
                SupplierDNLine.objects.create(
                    supplier_dn=dn,
                    raw_material=rm,
                    quantity_received=Decimal("200.000"),
                    unit_of_measure=litre,
                    agreed_unit_price=Decimal("420.00"),
                )
                dn.refresh_from_db()
                dn.transition_to("pending", admin)
                _ok(self, f"{dn.reference} soumis — statut={dn.status}")

                if dn.status == "pending_qc_sampling":
                    self.stdout.write(
                        self.style.MIGRATE_HEADING(
                            "\n▶ QA/QC — Gate A (adjuvant, lot conforme)"
                        )
                    )
                    line = dn.lines.get(raw_material=rm)
                    spec_lines = {
                        sl.property.name: sl for sl in spec.lines.filter(gate_a=True)
                    }

                    sample = Sample.objects.create(
                        control_point="A",
                        supplier_dn_line=line,
                        quality_specification=spec,
                        quantity_sampled=Decimal("1.000"),
                        unit=litre,
                        sampled_by=qc_tech,
                        status="results_pending",
                    )

                    results = [
                        # (property, raw_value, numeric_value, instrument)
                        (
                            "Aspect / couleur / homogénéité",
                            "Conforme",
                            None,
                            "Contrôle visuel",
                        ),
                        ("pH adjuvant", "3.20", Decimal("3.20"), "pH-mètre HI98107"),
                        (
                            "Masse volumique adjuvant",
                            "1.285",
                            Decimal("1.285"),
                            "Densimètre à immersion",
                        ),
                        (
                            "Teneur en matières sèches",
                            "41.20",
                            Decimal("41.20"),
                            "Étuve 105°C, 24h",
                        ),
                        (
                            "Teneur en chlorures (Cl-)",
                            "0.045",
                            Decimal("0.045"),
                            "Titrateur potentiométrique",
                        ),
                    ]
                    for name, raw, num, instrument in results:
                        sl = spec_lines[name]
                        TestResult.objects.create(
                            sample=sample,
                            spec_line=sl,
                            recorded_value=raw,
                            recorded_numeric=num,
                            instrument_method=instrument,
                            recorded_by=qc_tech,
                            outcome=sl.evaluate(num, raw),
                        )
                    outcome = sample.compute_outcome()
                    _ok(self, f"{sample.reference} — 5/5 tests renseignés — {outcome}")
                    for r in sample.results.select_related("spec_line__property"):
                        _ok(
                            self,
                            f"  {r.spec_line.property.name}: {r.recorded_value} → {r.outcome}",
                        )

                    dn.refresh_from_db()
                    dn.qc_release(qa_manager)
                    dn.refresh_from_db()
                    _ok(self, f"{dn.reference} — QC libéré — statut={dn.status}")

                from core.models import PieceJointe

                _attach(dn, PieceJointe.TYPE_SD_DNF, f"{dn.reference}_signe.pdf", admin)
                dn.validate(admin)
                _ok(
                    self,
                    f"{dn.reference} validé — statut={dn.status} (stock adjuvant mis à jour)",
                )

            # ================================================================
            # Second BL — lot non conforme sur l'aspect visuel (booléen)
            # ================================================================
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    "\n▶ BL Fournisseur — Lot non conforme (aspect)"
                )
            )
            dn2 = SupplierDN.objects.filter(
                external_reference="BL-CHIMADJUV-2026-014"
            ).first()
            if dn2:
                _skip(self, dn2.reference)
            else:
                dn2 = SupplierDN.objects.create(
                    site=main_site,
                    external_reference="BL-CHIMADJUV-2026-014",
                    supplier=supplier,
                    delivery_date=datetime.date(2026, 6, 18),
                    remarks="Livraison adjuvant — lot L2026-0618 (retour transporteur, chaleur).",
                    created_by=admin,
                )
                SupplierDNLine.objects.create(
                    supplier_dn=dn2,
                    raw_material=rm,
                    quantity_received=Decimal("100.000"),
                    unit_of_measure=litre,
                    agreed_unit_price=Decimal("420.00"),
                )
                dn2.refresh_from_db()
                dn2.transition_to("pending", admin)
                _ok(self, f"{dn2.reference} soumis — statut={dn2.status}")

                if dn2.status == "pending_qc_sampling":
                    self.stdout.write(
                        self.style.MIGRATE_HEADING(
                            "\n▶ QA/QC — Gate A (adjuvant, lot non conforme)"
                        )
                    )
                    line2 = dn2.lines.get(raw_material=rm)
                    spec_lines = {
                        sl.property.name: sl for sl in spec.lines.filter(gate_a=True)
                    }

                    sample2 = Sample.objects.create(
                        control_point="A",
                        supplier_dn_line=line2,
                        quality_specification=spec,
                        quantity_sampled=Decimal("1.000"),
                        unit=litre,
                        sampled_by=qc_tech,
                        status="results_pending",
                    )
                    results2 = [
                        (
                            "Aspect / couleur / homogénéité",
                            "Non conforme",
                            None,
                            "Contrôle visuel — dépôt/cristallisation visible",
                        ),
                        ("pH adjuvant", "3.15", Decimal("3.15"), "pH-mètre HI98107"),
                        (
                            "Masse volumique adjuvant",
                            "1.279",
                            Decimal("1.279"),
                            "Densimètre à immersion",
                        ),
                        (
                            "Teneur en matières sèches",
                            "40.80",
                            Decimal("40.80"),
                            "Étuve 105°C, 24h",
                        ),
                        (
                            "Teneur en chlorures (Cl-)",
                            "0.052",
                            Decimal("0.052"),
                            "Titrateur potentiométrique",
                        ),
                    ]
                    for name, raw, num, instrument in results2:
                        sl = spec_lines[name]
                        TestResult.objects.create(
                            sample=sample2,
                            spec_line=sl,
                            recorded_value=raw,
                            recorded_numeric=num,
                            instrument_method=instrument,
                            recorded_by=qc_tech,
                            outcome=sl.evaluate(num, raw),
                        )
                    outcome2 = sample2.compute_outcome()
                    _ok(
                        self,
                        f"{sample2.reference} — {outcome2} (Aspect non conforme, is_critical=True → échantillon entier échoue)",
                    )
                    for r in sample2.results.select_related("spec_line__property"):
                        _ok(
                            self,
                            f"  {r.spec_line.property.name}: {r.recorded_value} → {r.outcome}",
                        )

                    dn2.refresh_from_db()
                    _ok(
                        self,
                        f"{dn2.reference} reste en statut={dn2.status} — validation bloquée tant que l'échantillon n'est pas conforme/dérogé (BR-QA-02)",
                    )

                    # ========================================================
                    # NCR — auto-ouverte par le signal post_save sur Sample
                    # (quality/signals.py), puis dispositionnée/clôturée
                    # exactement comme quality.views.ncr_detail le fait via
                    # NCRDispositionForm + NonConformityReport.disposition_action/close.
                    # ========================================================
                    self.stdout.write(
                        self.style.MIGRATE_HEADING(
                            "\n▶ NCR — Disposition du lot non conforme"
                        )
                    )
                    ncr = sample2.ncrs.first()
                    if ncr is None:
                        self.stdout.write(
                            self.style.WARNING(
                                "  ⚠ Aucune NCR auto-ouverte trouvée sur l'échantillon "
                                f"{sample2.reference} — signal non déclenché, étape ignorée."
                            )
                        )
                    else:
                        _ok(self, f"{ncr.reference} auto-ouverte (statut={ncr.status})")

                        from core.models import PieceJointe

                        _attach(
                            ncr,
                            PieceJointe.TYPE_SD_CORR,
                            f"retour_{ncr.reference}.pdf",
                            qa_manager,
                        )
                        _ok(self, f"Justificatif joint (BR-QA-11) pour {ncr.reference}")

                        ncr.disposition_action(
                            qa_manager,
                            disposition="return_to_supplier",
                            corrective_action=(
                                "Lot L2026-0618 refusé et retourné à CHIMADJUV SPA. "
                                "Exigence ajoutée au cahier des charges transporteur : "
                                "protection thermique en été pour éviter la cristallisation."
                            ),
                            root_cause_category="supplier_quality",
                            root_cause_detail=(
                                "Dépôt/cristallisation visible à réception, probablement lié "
                                "à une exposition à la chaleur pendant le transport (BL du "
                                "18/06, période estivale)."
                            ),
                        )
                        ncr.refresh_from_db()
                        _ok(self, f"{ncr.reference} dispositionnée — statut={ncr.status}")
                        ncr.close(qa_manager)
                        ncr.refresh_from_db()
                        _ok(self, f"{ncr.reference} clôturée par {qa_manager.username} — statut={ncr.status}")

        self.stdout.write(
            self.style.SUCCESS("\n✅  seed_scenario_adjuvant_gate_a completed.")
        )
