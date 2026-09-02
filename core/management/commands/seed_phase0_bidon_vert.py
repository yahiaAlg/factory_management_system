"""
core/management/commands/seed_phase0_bidon_vert.py

Phase 0 seed for scenario "Bidon PEHD 15L Vert" (scenario_bidon_vert_full_cycle_fresh_db.md).
Run AFTER minimal_populate_db (needs UnitOfMeasure KG/PCE, RawMaterialCategory,
an 'admin' user, and the QA/QC users 'qualite'/'laboratoire' already present).
Creates master data — no BL, no formulation, no OP — so the catalogue/
supplier/client are "intact" and ready for Phase 1 (Achat).

Also seeds the QA/QC Laboratory module master data (functional spec
qa_qc_laboratory_functional_spec.md): a Property Catalogue, one Quality
Specification per target, and active Sampling Plans for Gate A (RM-001 only),
Gate B and Gate C (PF-001) — so the fresh-DB scenario exercises all three
gates end-to-end in the phases that follow.

Usage:
    python manage.py minimal_populate_db --flush
    python manage.py seed_phase0_bidon_vert
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


def _ok(self, msg):
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _skip(self, msg):
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg} — already exists, skipped"))


class Command(BaseCommand):
    help = (
        "Phase 0 seed: Fournisseur F-0001, Client C-0001, 4 MP (RM-001..004), "
        "1 PF (PF-001), + module QA/QC (Propriétés, Spécifications, Plans "
        "d'échantillonnage Gates A/B/C)."
    )

    def handle(self, *args, **options):
        from catalog.models import (
            RawMaterial,
            RawMaterialCategory,
            UnitOfMeasure,
            FinishedProduct,
        )
        from suppliers.models import Supplier
        from clients.models import Client
        from accounts.models import UserProfile
        from quality.models import Property, QualitySpecification, QualitySpecLine, SamplingPlan

        try:
            admin = User.objects.get(username="admin")
        except User.DoesNotExist:
            raise CommandError(
                "User 'admin' introuvable — lancez d'abord "
                "'python manage.py minimal_populate_db --flush'."
            )

        try:
            qa_manager = User.objects.get(username="qualite")
        except User.DoesNotExist:
            raise CommandError(
                "User 'qualite' (rôle qa_manager) introuvable — lancez d'abord "
                "'python manage.py minimal_populate_db --flush' (version incluant "
                "les comptes QA/QC)."
            )

        with transaction.atomic():
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Fournisseur"))
            supplier, created = Supplier.objects.get_or_create(
                code="F-0001",
                defaults=dict(
                    raison_sociale="PLASTOCHIM SARL",
                    forme_juridique="SARL",
                    nif="000116123456789",
                    nis="099916123456",
                    rc="16/00-1234567B26",
                    ai="16123456789",
                    address="Zone Industrielle, Lot 12, Sétif",
                    wilaya="Sétif",
                    phone="036701234",
                    email="contact@plastochim.dz",
                    contact_person="Karim Benali",
                    contact_phone="0555112233",
                    payment_terms=30,
                    currency="DZD",
                    is_active=True,
                    created_by=admin,
                ),
            )
            (
                _ok(self, f"{supplier.code} — {supplier.raison_sociale}")
                if created
                else _skip(self, supplier.code)
            )

            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Client"))
            client, created = Client.objects.get_or_create(
                code="C-0001",
                defaults=dict(
                    raison_sociale="DISTRIB NORD SPA",
                    forme_juridique="SPA",
                    nif="000216987654321",
                    nis="099916987654",
                    rc="16/00-7654321A26",
                    ai="16987654321",
                    address="Route Nationale 5, Alger",
                    wilaya="Alger",
                    phone="021456789",
                    email="commandes@distribnord.dz",
                    contact_person="Amina Cherif",
                    contact_phone="0661223344",
                    payment_terms=30,
                    credit_status="active",
                    max_discount_pct=Decimal("5.00"),
                    is_active=True,
                    created_by=admin,
                ),
            )
            (
                _ok(self, f"{client.code} — {client.raison_sociale}")
                if created
                else _skip(self, client.code)
            )

            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ Catalogue — Matières premières")
            )
            kg = UnitOfMeasure.objects.get(code="KG")
            cat_resines = RawMaterialCategory.objects.get(name="Résines et polymères")
            cat_additifs = RawMaterialCategory.objects.get(name="Additifs et colorants")
            cat_lubs = RawMaterialCategory.objects.get(name="Lubrifiants industriels")

            raw_materials = [
                # designation, category, ref_price, alert_threshold, stockout_threshold
                (
                    "Polyéthylène haute densité PEHD",
                    cat_resines,
                    Decimal("380.00"),
                    Decimal("20.000"),
                    Decimal("5.000"),
                ),
                (
                    "Masterbatch Vert PEHD",
                    cat_additifs,
                    Decimal("1100.00"),
                    Decimal("0.500"),
                    Decimal("0.100"),
                ),
                (
                    "Stabilisant thermique UV",
                    cat_additifs,
                    Decimal("1200.00"),
                    Decimal("0.500"),
                    Decimal("0.100"),
                ),
                (
                    "Lubrifiant silicone industriel",
                    cat_lubs,
                    Decimal("780.00"),
                    Decimal("0.500"),
                    Decimal("0.100"),
                ),
            ]

            self._rm = {}
            for designation, category, ref_price, alert, stockout in raw_materials:
                rm = RawMaterial.objects.filter(designation=designation).first()
                if rm:
                    _skip(self, f"{designation} ({rm.reference})")
                else:
                    rm = RawMaterial.objects.create(
                        designation=designation,
                        category=category,
                        unit_of_measure=kg,
                        default_supplier=supplier,
                        reference_price=ref_price,
                        alert_threshold=alert,
                        stockout_threshold=stockout,
                        is_active=True,
                        created_by=admin,
                    )
                    _ok(self, f"{rm.reference} — {designation}")
                self._rm[designation] = rm

            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ Catalogue — Produit fini")
            )
            pce = UnitOfMeasure.objects.get(code="PCE")
            fp = FinishedProduct.objects.filter(
                designation="Bidon PEHD 15L Vert"
            ).first()
            if fp:
                _skip(self, f"Bidon PEHD 15L Vert ({fp.reference})")
            else:
                fp = FinishedProduct.objects.create(
                    designation="Bidon PEHD 15L Vert",
                    sales_unit=pce,
                    reference_selling_price=Decimal("1850.00"),
                    alert_threshold=Decimal("50.000"),
                    is_active=True,
                    created_by=admin,
                )
                _ok(self, f"{fp.reference} — Bidon PEHD 15L Vert")

            # ================================================================
            # QA/QC — Catalogue Propriétés + Spécifications + Plans
            # d'échantillonnage (module Qualité / Laboratoire).
            #
            # Gate A n'est activé que sur RM-001 (PEHD) — RM-002/003/004
            # restent sans plan actif, donc leur réception continue de suivre
            # le flux inchangé (BR-QA-01 : pas de plan = pas de gate).
            # Gates B et C sont activés sur PF-001, la propriété "Épaisseur
            # de paroi" étant contrôlée aux deux points.
            # ================================================================
            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ QA/QC — Catalogue Propriétés")
            )
            prop_mfi, created = Property.objects.get_or_create(
                name="Indice de fluidité (MFI)",
                defaults=dict(
                    applies_to="raw_material",
                    unit_label="g/10min",
                    test_method_reference="ASTM D1238",
                    result_data_type="numeric",
                    default_precision=2,
                    is_active=True,
                    created_by=qa_manager,
                ),
            )
            (
                _ok(self, f"Propriété '{prop_mfi.name}' ({prop_mfi.unit_label})")
                if created
                else _skip(self, prop_mfi.name)
            )
            prop_epaisseur, created = Property.objects.get_or_create(
                name="Épaisseur de paroi",
                defaults=dict(
                    applies_to="finished_product",
                    unit_label="mm",
                    test_method_reference="Micromètre digital — contrôle 4 points",
                    result_data_type="numeric",
                    default_precision=2,
                    is_active=True,
                    created_by=qa_manager,
                ),
            )
            (
                _ok(self, f"Propriété '{prop_epaisseur.name}' ({prop_epaisseur.unit_label})")
                if created
                else _skip(self, prop_epaisseur.name)
            )

            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ QA/QC — Spécifications qualité")
            )
            rm_pehd = self._rm["Polyéthylène haute densité PEHD"]
            spec_rm, created = QualitySpecification.objects.get_or_create(
                raw_material=rm_pehd,
                version=1,
                defaults=dict(
                    effective_date=timezone.now().date(),
                    is_active=True,
                    created_by=qa_manager,
                    approved_by=qa_manager,
                ),
            )
            if created:
                QualitySpecLine.objects.create(
                    specification=spec_rm,
                    property=prop_mfi,
                    gate_a=True,
                    nominal_value=Decimal("8.00"),
                    tolerance_pct=Decimal("15.00"),
                    is_critical=True,
                )
                _ok(self, f"Spécification {spec_rm} — MFI 8,00 ± 15 % (critique, Gate A)")
            else:
                _skip(self, str(spec_rm))

            spec_fp, created = QualitySpecification.objects.get_or_create(
                finished_product=fp,
                version=1,
                defaults=dict(
                    effective_date=timezone.now().date(),
                    is_active=True,
                    created_by=qa_manager,
                    approved_by=qa_manager,
                ),
            )
            if created:
                QualitySpecLine.objects.create(
                    specification=spec_fp,
                    property=prop_epaisseur,
                    gate_b=True,
                    gate_c=True,
                    nominal_value=Decimal("2.50"),
                    tolerance_pct=Decimal("10.00"),
                    is_critical=True,
                )
                _ok(self, f"Spécification {spec_fp} — Épaisseur 2,50 mm ± 10 % (critique, Gates B+C)")
            else:
                _skip(self, str(spec_fp))

            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ QA/QC — Plans d'échantillonnage")
            )
            plan_a, created = SamplingPlan.objects.get_or_create(
                raw_material=rm_pehd,
                control_point="A",
                defaults=dict(
                    trigger_description="À chaque BL fournisseur",
                    sample_size_rule="1 échantillon par livraison",
                    frequency="every",
                    is_active=True,
                    created_by=qa_manager,
                ),
            )
            (
                _ok(self, f"Plan Gate A — {rm_pehd.designation}")
                if created
                else _skip(self, f"Plan Gate A — {rm_pehd.designation}")
            )
            plan_b, created = SamplingPlan.objects.get_or_create(
                finished_product=fp,
                control_point="B",
                defaults=dict(
                    trigger_description="En cours de moulage",
                    checkpoint_labels="Après moulage",
                    sample_size_rule="1 échantillon par point de contrôle",
                    frequency="every",
                    is_active=True,
                    created_by=qa_manager,
                ),
            )
            (
                _ok(self, f"Plan Gate B — {fp.designation} (Après moulage)")
                if created
                else _skip(self, f"Plan Gate B — {fp.designation}")
            )
            plan_c, created = SamplingPlan.objects.get_or_create(
                finished_product=fp,
                control_point="C",
                defaults=dict(
                    trigger_description="Par ordre de production terminé",
                    sample_size_rule="1 échantillon par OP",
                    frequency="every",
                    is_active=True,
                    created_by=qa_manager,
                ),
            )
            (
                _ok(self, f"Plan Gate C — {fp.designation}")
                if created
                else _skip(self, f"Plan Gate C — {fp.designation}")
            )

        self.stdout.write(
            self.style.SUCCESS("\n✅  seed_phase0_bidon_vert completed.\n")
        )
        self.stdout.write(
            "  Catalogue prêt :\n"
            f"    • {supplier.code} — {supplier.raison_sociale}\n"
            f"    • {client.code} — {client.raison_sociale}\n"
            + "".join(f"    • {rm.reference} — {d}\n" for d, rm in self._rm.items())
            + f"    • {fp.reference} — Bidon PEHD 15L Vert\n"
            "  Module QA/QC prêt :\n"
            f"    • Propriété '{prop_mfi.name}' (MP) / '{prop_epaisseur.name}' (PF)\n"
            f"    • Spécification qualité v1 — RM-001 (Gate A) / PF-001 (Gates B+C)\n"
            "    • Plans d'échantillonnage actifs : Gate A (RM-001), Gate B & C (PF-001)\n"
            "    • RM-002/003/004 restent SANS plan actif — leur réception continue "
            "sans contrôle QC (BR-QA-01)\n"
            "  Prochaine étape : Phase 1 — Achat & Réception (BL Fournisseur F-0001).\n"
        )
