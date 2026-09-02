"""
core/management/commands/seed_phase1c_supplier_bl_multi_formulations.py

Seed for the multi-formulation demo (scenario §4.4 — formulations 3020,
3010, 4010). Creates the 8 shared raw materials (HD400, SR100, RT, GLOCO,
LS, BIO, ANT, EAU) if missing, then a single BL Fournisseur covering the
combined quantity needed across the three formulations (validated, stock
credited). No QA/QC gate is active on these materials, so the BL follows
the plain "draft -> pending -> validated" path (BR-QA-01: no plan = no
gate).

Pre-requisite: seed_phase0_bidon_vert has run (admin user, supplier
F-0001, UnitOfMeasure KG, RawMaterialCategory master data).

Usage:
    python manage.py seed_phase0_bidon_vert
    python manage.py seed_phase1c_supplier_bl_multi_formulations
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _ok(self, msg):
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _skip(self, msg):
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg} — already exists, skipped"))


class Command(BaseCommand):
    help = (
        "Seed: catalogue MP (HD400, SR100, RT, GLOCO, LS, BIO, ANT, EAU) + "
        "BL Fournisseur unique couvrant les formulations 3020/3010/4010 "
        "(§4.4 du scénario), validé (stock MP crédité)."
    )

    def handle(self, *args, **options):
        from catalog.models import RawMaterial, RawMaterialCategory, UnitOfMeasure
        from suppliers.models import Supplier
        from supplier_ops.models import SupplierDN, SupplierDNLine
        from core.models import PieceJointe
        from core.utils import get_seed_site

        main_site = get_seed_site(self)

        try:
            admin = User.objects.get(username="admin")
        except User.DoesNotExist:
            raise CommandError(
                "User 'admin' introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        try:
            supplier = Supplier.objects.get(code="F-0001")
        except Supplier.DoesNotExist:
            raise CommandError(
                "Fournisseur F-0001 introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        kg = UnitOfMeasure.objects.get(code="KG")
        cat_resines = RawMaterialCategory.objects.get(name="Résines et polymères")
        cat_additifs = RawMaterialCategory.objects.get(name="Additifs et colorants")
        cat_lubs = RawMaterialCategory.objects.get(name="Lubrifiants industriels")
        cat_chimie = RawMaterialCategory.objects.get(name="Produits chimiques")
        cat_conso = RawMaterialCategory.objects.get(name="Consommables")

        # code, category, reference_price (DZD/kg), alert, stockout
        raw_materials = [
            (
                "HD400",
                cat_resines,
                Decimal("165.00"),
                Decimal("50.000"),
                Decimal("10.000"),
            ),
            (
                "SR100",
                cat_resines,
                Decimal("165.00"),
                Decimal("30.000"),
                Decimal("5.000"),
            ),
            ("RT", cat_chimie, Decimal("120.00"), Decimal("5.000"), Decimal("1.000")),
            (
                "GLOCO",
                cat_additifs,
                Decimal("250.00"),
                Decimal("5.000"),
                Decimal("1.000"),
            ),
            ("LS", cat_lubs, Decimal("145.00"), Decimal("2.000"), Decimal("0.500")),
            ("BIO", cat_chimie, Decimal("500.00"), Decimal("0.500"), Decimal("0.100")),
            ("ANT", cat_chimie, Decimal("500.00"), Decimal("0.500"), Decimal("0.100")),
            ("EAU", cat_conso, Decimal("2.00"), Decimal("50.000"), Decimal("10.000")),
        ]

        # Combined purchase quantity = sum of the 3 formulations (§4.4):
        # 3020 + 3010 + 4010, per material (kg).
        qty_by_code = {
            "HD400": Decimal("400.000")
            + Decimal("300.000")
            + Decimal("170.000"),  # 870
            "SR100": Decimal("130.000")
            + Decimal("130.000")
            + Decimal("180.000"),  # 440
            "RT": Decimal("20.000") + Decimal("11.000") + Decimal("20.000"),  # 51
            "GLOCO": Decimal("40.000") + Decimal("10.000") + Decimal("0.000"),  # 50
            "LS": Decimal("0.000") + Decimal("0.000") + Decimal("0.000"),  # 0
            "BIO": Decimal("1.000") + Decimal("1.000") + Decimal("1.000"),  # 3
            "ANT": Decimal("1.000") + Decimal("1.000") + Decimal("1.000"),  # 3
            "EAU": Decimal("440.000") + Decimal("440.000") + Decimal("440.000"),  # 1320
        }

        with transaction.atomic():
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    "\n▶ Catalogue — Matières premières (multi-formulations)"
                )
            )
            rms = {}
            for code, category, ref_price, alert, stockout in raw_materials:
                rm = RawMaterial.objects.filter(designation=code).first()
                if rm:
                    _skip(self, f"{code} ({rm.reference})")
                else:
                    rm = RawMaterial.objects.create(
                        designation=code,
                        category=category,
                        unit_of_measure=kg,
                        default_supplier=supplier,
                        reference_price=ref_price,
                        alert_threshold=alert,
                        stockout_threshold=stockout,
                        is_active=True,
                        created_by=admin,
                    )
                    _ok(self, f"{rm.reference} — {code}")
                rms[code] = rm

            self.stdout.write(
                self.style.MIGRATE_HEADING("\n▶ BL Fournisseur (3020 + 3010 + 4010)")
            )
            dn = SupplierDN.objects.filter(
                external_reference="BL-PLASTOCHIM-2026-3020-3010-4010"
            ).first()
            if dn:
                _skip(self, dn.reference)
            else:
                dn = SupplierDN.objects.create(
                    site=main_site,
                    external_reference="BL-PLASTOCHIM-2026-3020-3010-4010",
                    supplier=supplier,
                    delivery_date=datetime.date(2026, 5, 20),
                    remarks=(
                        "Livraison matières couvrant les formulations 3020, 3010 et "
                        "4010 (§4.4 du scénario) — quantités cumulées, lignes à qty "
                        "nulle omises."
                    ),
                    created_by=admin,
                )
                price_by_code = {code: price for code, _, price, _, _ in raw_materials}
                for code, qty in qty_by_code.items():
                    if qty <= 0:
                        continue  # LS: 0 kg across all 3 formulations — no line
                    SupplierDNLine.objects.create(
                        supplier_dn=dn,
                        raw_material=rms[code],
                        quantity_received=qty,
                        unit_of_measure=kg,
                        agreed_unit_price=price_by_code[code],
                    )
                dn.refresh_from_db()
                _ok(
                    self,
                    f"{dn.reference} créé — {dn.lines.count()} lignes — Total HT {dn.total_amount_ht} DZD",
                )

                dn.transition_to("pending", admin)
                _ok(self, f"{dn.reference} soumis — statut={dn.status}")
                # Pas de plan d'échantillonnage actif sur ces MP -> pas de
                # redirection vers "pending_qc_sampling" (BR-QA-01).

                dn.refresh_from_db()
                if dn.status == "pending":
                    PieceJointe.objects.create(
                        content_type=ContentType.objects.get_for_model(dn),
                        object_id=dn.pk,
                        fichier=ContentFile(
                            b"%PDF-1.4\n%...\n",  # dummy PDF content
                            name="BL-PLASTOCHIM-2026-3020-3010-4010-signe.pdf",
                        ),
                        type_document=PieceJointe.TYPE_SD_DNF,
                        description="Pièce jointe seed (SD-DNF)",
                        uploaded_by=admin,
                    )
                    dn.validate(admin)
                    _ok(
                        self,
                        f"{dn.reference} validé — statut={dn.status} (stock MP mis à jour)",
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "\n✅  seed_phase1c_supplier_bl_multi_formulations completed.\n"
            )
        )
        self.stdout.write(
            "  Stock crédité : HD400 +870, SR100 +440, RT +51, GLOCO +50, "
            "BIO +3, ANT +3, EAU +1320 kg (LS : 0, aucune ligne).\n"
            "  Prochaine étape : créer les Formulations 3020/3010/4010 "
            "(Production → Formulations → Nouvelle) puis leurs Ordres de "
            "Production.\n"
        )
