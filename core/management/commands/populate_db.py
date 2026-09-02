"""
core/management/commands/populate_db.py

Usage:
    python manage.py populate_db            # seed (idempotent)
    python manage.py populate_db --flush    # wipe transactional data first, then seed
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from supplier_ops.models import SupplierDN

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _section(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.MIGRATE_HEADING(f"\n▶ {msg}"))


def _warn(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg}"))


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Seed the database with realistic demo data for all modules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all transactional data before seeding (master data is kept).",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            self._seed_core()
            self._seed_users()
            self._seed_units_and_categories()
            self._seed_suppliers()
            self._seed_clients()
            self._seed_catalog()
            self._seed_expense_categories()
            self._seed_formulations()
            self._seed_supplier_dns()  # → creates RM stock via signal
            self._seed_production_orders()  # → creates FG stock via signal
            self._seed_supplier_invoices()
            self._seed_client_dns()  # → deducts FG stock via signal
            self._seed_client_invoices()
            self._seed_stock_adjustments()  # → corrective stock movements
            self._seed_expenses()

        self.stdout.write(
            self.style.SUCCESS("\n✅  populate_db completed successfully.\n")
        )

    # ===================================================================
    # FLUSH
    # ===================================================================

    def _flush(self):
        _section(self, "Flushing transactional data")
        from sales.models import (
            ClientAccountPayment,
            ClientPayment,
            ClientInvoice,
            ClientDN,
        )
        from supplier_ops.models import (
            SupplierPayment,
            SupplierAccountPayment,
            SupplierInvoice,
            SupplierDN,
            SupplierInvoiceDNLink,
            SupplierInvoiceLine,
            SupplierDNLine,
        )
        from production.models import (
            ProductionOrderLine,
            ProductionOrder,
            FormulationLine,
            Formulation,
        )
        from stock.models import (
            StockMovement,
            StockAdjustment,
            StockAdjustmentLine,
            RawMaterialStockBalance,
            FinishedProductStockBalance,
        )
        from expenses.models import Expense, SupportingDocument

        for model in [
            ClientAccountPayment,
            ClientPayment,
            ClientInvoice,
            ClientDN,
            SupplierPayment,
            SupplierAccountPayment,
            SupplierInvoiceLine,
            SupplierInvoiceDNLink,
            SupplierInvoice,
            SupplierDNLine,
            SupplierDN,
            ProductionOrderLine,
            ProductionOrder,
            FormulationLine,
            Formulation,
            StockAdjustmentLine,
            StockAdjustment,
            StockMovement,
            RawMaterialStockBalance,
            FinishedProductStockBalance,
            Expense,
            SupportingDocument,
        ]:
            count, _ = model.objects.all().delete()
            if count:
                _ok(self, f"Deleted {count} {model.__name__} rows")

    # ===================================================================
    # PHASE 1 — CORE
    # ===================================================================

    def _seed_core(self):
        _section(self, "Core — CompanyInformation & SystemParameters")
        from core.models import CompanyInformation, SystemParameter, DocumentSequence
        from core.utils import get_seed_site

        # Multi-site (§25.2): a fresh DB always has "Site Principal" (MAIN),
        # seeded by the core.0004_seed_main_site data migration. Every
        # later phase attaches its site-scoped documents (BL Fournisseur,
        # OP, Ajustement, BL Client) to it via self._main_site.
        self._main_site = get_seed_site(self)
        _ok(self, f"Using ProductionSite '{self._main_site.name}' ({self._main_site.code})")

        # Singleton company info
        if not CompanyInformation.objects.exists():
            CompanyInformation.objects.create(
                raison_sociale="SARL AlgéroPlast",
                forme_juridique="SARL",
                nif="099312345678901",
                nis="26900123456789",
                rc="09/00-0123456B19",
                ai="09-123456789",
                address="Zone Industrielle, BP 42",
                wilaya="Sétif",
                phone="036 12 34 56",
                email="contact@algeroplast.dz",
                bank_name="BNA — Agence Sétif",
                bank_account="00100123456789012345",
                rib="00100123456789012345678",
                vat_rate=Decimal("0.19"),
                fiscal_regime="Réel",
            )
            _ok(self, "CompanyInformation created")
        else:
            _ok(self, "CompanyInformation already exists — skipped")

        # System parameters (SPEC S2 required keys)
        params = [
            (
                "financial",
                "reconciliation_tolerance_epsilon",
                "500.00",
                "Tolérance de rapprochement BL/Facture (DZD)",
            ),
            (
                "financial",
                "reconciliation_dispute_delta",
                "5000.00",
                "Seuil de litige rapprochement (DZD)",
            ),
            (
                "financial",
                "expense_delegation_threshold",
                "50000.00",
                "Seuil délégation dépenses — validation Manager requise (DZD)",
            ),
            (
                "production",
                "yield_warning_threshold",
                "90.00",
                "Seuil d'alerte rendement (%)",
            ),
            (
                "production",
                "yield_critical_threshold",
                "80.00",
                "Seuil critique rendement (%)",
            ),
            (
                "alert",
                "payment_due_alert_days",
                "7",
                "Nombre de jours avant échéance pour alerte",
            ),
            ("financial", "default_vat_rate", "0.19", "Taux de TVA par défaut"),
            (
                "document",
                "current_year",
                str(datetime.date.today().year),
                "Année fiscale en cours",
            ),
        ]
        for category, key, value, description in params:
            _, created = SystemParameter.objects.get_or_create(
                key=key,
                defaults=dict(
                    category=category,
                    value=value,
                    description=description,
                    is_active=True,
                ),
            )
            if created:
                _ok(self, f"SystemParameter '{key}' = {value}")

        # Pre-seed document sequences so references start clean.
        # Multi-site (§25.2): BL-F, OP, BL-C, ADJ are per-site sequences —
        # pre-seed the "Site Principal" (MAIN) variant so this demo data
        # starts each of those at NNNN=0001 too. Other prefixes stay
        # company-wide and unaffected.
        site_code = self._main_site.code
        sequences = [
            ("RM", 0, "Matières premières"),
            ("PF", 0, "Produits finis"),
            ("F", 0, "Formulations"),
            (f"BL-F-{site_code}", datetime.date.today().year, "BL Fournisseur"),
            ("FF", datetime.date.today().year, "Factures Fournisseur"),
            ("PAY-F", datetime.date.today().year, "Paiements Fournisseur"),
            (f"BL-C-{site_code}", datetime.date.today().year, "BL Client"),
            ("FC", datetime.date.today().year, "Factures Client"),
            ("PAY-C", datetime.date.today().year, "Paiements Client"),
            ("DEP", datetime.date.today().year, "Dépenses"),
            (f"OP-{site_code}", datetime.date.today().year, "Ordres de Production"),
            ("RGL-F", datetime.date.today().year, "Règlements compte fournisseur"),
            ("RGL-C", datetime.date.today().year, "Règlements compte client"),
            (f"ADJ-{site_code}", datetime.date.today().year, "Ajustements stock"),
        ]
        for prefix, year, description in sequences:
            DocumentSequence.objects.get_or_create(
                prefix=prefix,
                current_year=year,
                defaults={"current_number": 0, "description": description},
            )

    # ===================================================================
    # PHASE 2 — USERS
    # ===================================================================

    def _seed_users(self):
        _section(self, "Users & Profiles")
        from accounts.models import UserProfile

        users_data = [
            ("admin", "Admin", "", "admin@algeroplast.dz", True, "manager"),
            (
                "manager1",
                "Karim",
                "Boudiaf",
                "k.boudiaf@algeroplast.dz",
                False,
                "manager",
            ),
            (
                "stock1",
                "Nadia",
                "Hamidi",
                "n.hamidi@algeroplast.dz",
                False,
                "stock_prod",
            ),
            (
                "accountant1",
                "Omar",
                "Ferhat",
                "o.ferhat@algeroplast.dz",
                False,
                "accountant",
            ),
            ("sales1", "Samira", "Rahmani", "s.rahmani@algeroplast.dz", False, "sales"),
            ("viewer1", "Youcef", "Benali", "y.benali@algeroplast.dz", False, "viewer"),
        ]

        self._users = {}
        for username, first, last, email, is_super, role in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults=dict(
                    first_name=first,
                    last_name=last,
                    email=email,
                    is_superuser=is_super,
                    is_staff=is_super,
                ),
            )
            if created:
                user.set_password("admin1234")
                user.save()
                # Signal auto-creates profile with role='viewer'; update it
                profile = user.userprofile
                profile.role = role
                profile.save()
                _ok(self, f"User '{username}' ({role})")
            else:
                # Ensure role is correct even if user pre-existed
                profile, _ = UserProfile.objects.get_or_create(
                    user=user, defaults={"role": role}
                )
                if profile.role != role:
                    profile.role = role
                    profile.save()
            self._users[username] = user

        self._manager = self._users["manager1"]
        self._stock = self._users["stock1"]
        self._accountant = self._users["accountant1"]
        self._sales = self._users["sales1"]

    # ===================================================================
    # PHASE 3 — UNITS & CATEGORIES
    # ===================================================================

    def _seed_units_and_categories(self):
        _section(self, "Units of Measure & Raw Material Categories")
        from catalog.models import UnitOfMeasure, RawMaterialCategory

        units = [
            ("KG", "Kilogramme", "kg"),
            ("G", "Gramme", "g"),
            ("L", "Litre", "L"),
            ("ML", "Millilitre", "mL"),
            ("M", "Mètre", "m"),
            ("M2", "Mètre carré", "m²"),
            ("PCE", "Pièce", "pce"),
            ("SAC", "Sac", "sac"),
            ("BTE", "Boîte", "bte"),
            ("T", "Tonne", "t"),
        ]
        self._units = {}
        for code, name, symbol in units:
            obj, created = UnitOfMeasure.objects.get_or_create(
                code=code, defaults=dict(name=name, symbol=symbol)
            )
            self._units[code] = obj
            if created:
                _ok(self, f"Unit: {code}")

        categories = [
            ("Résines et polymères", "Matières plastiques de base"),
            ("Additifs et colorants", "Additifs chimiques et pigments"),
            ("Emballages", "Matériaux d'emballage"),
            ("Lubrifiants industriels", "Huiles et graisses industrielles"),
            ("Produits chimiques", "Produits chimiques divers"),
        ]
        self._rm_categories = {}
        for name, desc in categories:
            obj, created = RawMaterialCategory.objects.get_or_create(
                name=name, defaults={"description": desc}
            )
            self._rm_categories[name] = obj
            if created:
                _ok(self, f"Category: {name}")

    # ===================================================================
    # PHASE 4 — SUPPLIERS
    # ===================================================================

    def _seed_suppliers(self):
        _section(self, "Suppliers")
        from suppliers.models import Supplier

        suppliers_data = [
            {
                "code": "FRNR-001",
                "raison_sociale": "PetroChim SARL",
                "forme_juridique": "SARL",
                "nif": "09931000001234",
                "address": "Zone Industrielle Rouiba, Alger",
                "wilaya": "Alger",
                "phone": "023 11 22 33",
                "email": "commercial@petrochim.dz",
                "contact_person": "Amine Kaci",
                "payment_terms": 30,
                "currency": "DZD",
            },
            {
                "code": "FRNR-002",
                "raison_sociale": "PolyPlus Algérie SPA",
                "forme_juridique": "SPA",
                "nif": "09931000005678",
                "address": "Route nationale 5, Annaba",
                "wilaya": "Annaba",
                "phone": "038 44 55 66",
                "email": "ventes@polyplus.dz",
                "contact_person": "Fatima Seghir",
                "payment_terms": 45,
                "currency": "DZD",
            },
            {
                "code": "FRNR-003",
                "raison_sociale": "ChimAlg Import",
                "forme_juridique": "SARL",
                "nif": "09931000009012",
                "address": "Port commercial, Oran",
                "wilaya": "Oran",
                "phone": "041 88 99 00",
                "email": "imports@chimalg.dz",
                "contact_person": "Khaled Mansouri",
                "payment_terms": 60,
                "currency": "EUR",
            },
        ]
        self._suppliers = {}
        for data in suppliers_data:
            code = data.pop("code")
            obj, created = Supplier.objects.get_or_create(
                code=code, defaults={**data, "created_by": self._manager}
            )
            self._suppliers[code] = obj
            if created:
                _ok(self, f"Supplier: {code} — {obj.raison_sociale}")

    # ===================================================================
    # PHASE 5 — CLIENTS
    # ===================================================================

    def _seed_clients(self):
        _section(self, "Clients")
        from clients.models import Client

        clients_data = [
            {
                "code": "CLT-001",
                "raison_sociale": "Plastiques du Nord SARL",
                "forme_juridique": "SARL",
                "nif": "09931111001234",
                "address": "Zone industrielle, Constantine",
                "wilaya": "Constantine",
                "phone": "031 22 33 44",
                "email": "achat@plastnord.dz",
                "contact_person": "Djamel Aouad",
                "payment_terms": 30,
                "credit_status": "active",
                "max_discount_pct": Decimal("5.00"),
            },
            {
                "code": "CLT-002",
                "raison_sociale": "Emballages Modernes SPA",
                "forme_juridique": "SPA",
                "nif": "09931111005678",
                "address": "Route de Boufarik, Blida",
                "wilaya": "Blida",
                "phone": "025 44 55 66",
                "email": "commandes@emballmod.dz",
                "contact_person": "Lynda Chaouch",
                "payment_terms": 45,
                "credit_status": "active",
                "max_discount_pct": Decimal("10.00"),
            },
            {
                "code": "CLT-003",
                "raison_sociale": "MétalPack Est EURL",
                "forme_juridique": "EURL",
                "nif": "09931111009012",
                "address": "Zone franche, Sétif",
                "wilaya": "Sétif",
                "phone": "036 77 88 99",
                "email": "direction@metalpack.dz",
                "contact_person": "Rachid Zerrouk",
                "payment_terms": 60,
                "credit_status": "suspended",
                "max_discount_pct": Decimal("3.00"),
            },
            {
                "code": "CLT-004",
                "raison_sociale": "DistribPlas Ouest SARL",
                "forme_juridique": "SARL",
                "nif": "09931111012345",
                "address": "Boulevard des Entrepreneurs, Oran",
                "wilaya": "Oran",
                "phone": "041 33 44 55",
                "email": "achat@distribplas.dz",
                "contact_person": "Sofiane Belarbi",
                "payment_terms": 30,
                "credit_status": "active",
                "max_discount_pct": Decimal("7.00"),
            },
            {
                "code": "CLT-005",
                "raison_sociale": "Agro-Embal Sud SPA",
                "forme_juridique": "SPA",
                "nif": "09931111015678",
                "address": "Zone d'activité, Biskra",
                "wilaya": "Biskra",
                "phone": "033 55 66 77",
                "email": "logistique@agroembal.dz",
                "contact_person": "Amira Touati",
                "payment_terms": 45,
                "credit_status": "active",
                "max_discount_pct": Decimal("8.00"),
            },
        ]
        self._clients = {}
        for data in clients_data:
            code = data.pop("code")
            obj, created = Client.objects.get_or_create(
                code=code, defaults={**data, "created_by": self._manager}
            )
            self._clients[code] = obj
            if created:
                _ok(self, f"Client: {code} — {obj.raison_sociale}")

    # ===================================================================
    # PHASE 6 — CATALOG
    # ===================================================================

    def _seed_catalog(self):
        _section(self, "Catalog — Raw Materials & Finished Products")
        from catalog.models import RawMaterial, FinishedProduct

        raw_materials_data = [
            {
                "designation": "Polypropylène PP Homopolymère",
                "category": "Résines et polymères",
                "unit_code": "KG",
                "default_supplier": "FRNR-001",
                "reference_price": Decimal("185.00"),
                "alert_threshold": Decimal("500.000"),
                "stockout_threshold": Decimal("100.000"),
            },
            {
                "designation": "Polyéthylène haute densité PEHD",
                "category": "Résines et polymères",
                "unit_code": "KG",
                "default_supplier": "FRNR-001",
                "reference_price": Decimal("195.00"),
                "alert_threshold": Decimal("400.000"),
                "stockout_threshold": Decimal("80.000"),
            },
            {
                "designation": "Colorant masterbatch noir",
                "category": "Additifs et colorants",
                "unit_code": "KG",
                "default_supplier": "FRNR-002",
                "reference_price": Decimal("420.00"),
                "alert_threshold": Decimal("50.000"),
                "stockout_threshold": Decimal("10.000"),
            },
            {
                "designation": "Colorant masterbatch blanc",
                "category": "Additifs et colorants",
                "unit_code": "KG",
                "default_supplier": "FRNR-002",
                "reference_price": Decimal("390.00"),
                "alert_threshold": Decimal("50.000"),
                "stockout_threshold": Decimal("10.000"),
            },
            {
                "designation": "Stabilisant thermique UV",
                "category": "Additifs et colorants",
                "unit_code": "KG",
                "default_supplier": "FRNR-003",
                "reference_price": Decimal("1250.00"),
                "alert_threshold": Decimal("20.000"),
                "stockout_threshold": Decimal("5.000"),
            },
            {
                "designation": "Lubrifiant silicone industriel",
                "category": "Lubrifiants industriels",
                "unit_code": "L",
                "default_supplier": "FRNR-003",
                "reference_price": Decimal("850.00"),
                "alert_threshold": Decimal("30.000"),
                "stockout_threshold": Decimal("5.000"),
            },
        ]

        self._raw_materials = {}
        for data in raw_materials_data:
            designation = data["designation"]
            if RawMaterial.objects.filter(designation=designation).exists():
                obj = RawMaterial.objects.get(designation=designation)
                self._raw_materials[designation] = obj
                _warn(self, f"RawMaterial '{designation}' already exists — skipped")
                continue

            obj = RawMaterial(
                designation=designation,
                category=self._rm_categories[data["category"]],
                unit_of_measure=self._units[data["unit_code"]],
                default_supplier=self._suppliers[data["default_supplier"]],
                reference_price=data["reference_price"],
                alert_threshold=data["alert_threshold"],
                stockout_threshold=data["stockout_threshold"],
                created_by=self._manager,
            )
            # reference auto-generated in save()
            obj.save()
            self._raw_materials[designation] = obj
            _ok(self, f"RawMaterial: {obj.reference} — {designation}")

        # Finished Products
        finished_products_data = [
            {
                "designation": "Bidon PP 5L noir",
                "unit_code": "PCE",
                "reference_selling_price": Decimal("380.00"),
                "alert_threshold": Decimal("200.000"),
            },
            {
                "designation": "Bidon PEHD 10L blanc",
                "unit_code": "PCE",
                "reference_selling_price": Decimal("620.00"),
                "alert_threshold": Decimal("150.000"),
            },
            {
                "designation": "Fût industriel 30L",
                "unit_code": "PCE",
                "reference_selling_price": Decimal("1450.00"),
                "alert_threshold": Decimal("50.000"),
            },
        ]
        self._finished_products = {}
        for data in finished_products_data:
            designation = data["designation"]
            if FinishedProduct.objects.filter(designation=designation).exists():
                obj = FinishedProduct.objects.get(designation=designation)
                self._finished_products[designation] = obj
                _warn(self, f"FinishedProduct '{designation}' already exists — skipped")
                continue

            obj = FinishedProduct(
                designation=designation,
                sales_unit=self._units[data["unit_code"]],
                reference_selling_price=data["reference_selling_price"],
                alert_threshold=data["alert_threshold"],
                created_by=self._manager,
            )
            obj.save()
            self._finished_products[designation] = obj
            _ok(self, f"FinishedProduct: {obj.reference} — {designation}")

    # ===================================================================
    # PHASE 7 — EXPENSE CATEGORIES
    # ===================================================================

    def _seed_expense_categories(self):
        _section(self, "Expense Categories")
        from expenses.models import ExpenseCategory

        categories = [
            ("ENERGIE", "Énergie et utilities", 1),
            ("TRANSPORT", "Transport et logistique", 2),
            ("ENTRETIEN", "Entretien et maintenance", 3),
            ("FOURNITURES", "Fournitures de bureau", 4),
            ("LOYER", "Loyer et charges immobilières", 5),
            ("SALAIRES", "Salaires et charges sociales", 6),
            ("COMM", "Frais commerciaux", 7),
            ("DIVERS", "Dépenses diverses", 8),
        ]
        self._expense_categories = {}
        for code, label, order in categories:
            obj, created = ExpenseCategory.objects.get_or_create(
                code=code, defaults=dict(label=label, order=order)
            )
            self._expense_categories[code] = obj
            if created:
                _ok(self, f"ExpenseCategory: {code}")

    # ===================================================================
    # PHASE 8 — FORMULATIONS
    # ===================================================================

    def _seed_formulations(self):
        _section(self, "Formulations")
        from production.models import Formulation, FormulationLine

        pp = self._raw_materials["Polypropylène PP Homopolymère"]
        pehd = self._raw_materials["Polyéthylène haute densité PEHD"]
        mb_noir = self._raw_materials["Colorant masterbatch noir"]
        mb_blanc = self._raw_materials["Colorant masterbatch blanc"]
        stab = self._raw_materials["Stabilisant thermique UV"]

        fp1 = self._finished_products["Bidon PP 5L noir"]
        fp2 = self._finished_products["Bidon PEHD 10L blanc"]
        fp3 = self._finished_products["Fût industriel 30L"]

        formulations_data = [
            {
                "designation": "Formulation Bidon PP 5L Noir",
                "finished_product": fp1,
                "reference_batch_qty": Decimal("100.000"),
                "unit_code": "PCE",
                "expected_yield_pct": Decimal("97.50"),
                "lines": [
                    (pp, Decimal("480.000"), "KG", Decimal("3.00")),
                    (mb_noir, Decimal("9.600"), "KG", Decimal("5.00")),
                    (stab, Decimal("2.400"), "KG", Decimal("5.00")),
                ],
            },
            {
                "designation": "Formulation Bidon PEHD 10L Blanc",
                "finished_product": fp2,
                "reference_batch_qty": Decimal("100.000"),
                "unit_code": "PCE",
                "expected_yield_pct": Decimal("96.00"),
                "lines": [
                    (pehd, Decimal("980.000"), "KG", Decimal("3.00")),
                    (mb_blanc, Decimal("19.600"), "KG", Decimal("5.00")),
                    (stab, Decimal("4.900"), "KG", Decimal("5.00")),
                ],
            },
            {
                "designation": "Formulation Fût industriel 30L",
                "finished_product": fp3,
                "reference_batch_qty": Decimal("50.000"),
                "unit_code": "PCE",
                "expected_yield_pct": Decimal("95.00"),
                "lines": [
                    (pehd, Decimal("1450.000"), "KG", Decimal("3.00")),
                    (mb_noir, Decimal("29.000"), "KG", Decimal("5.00")),
                    (stab, Decimal("7.250"), "KG", Decimal("5.00")),
                ],
            },
        ]

        self._formulations = {}
        for data in formulations_data:
            designation = data["designation"]
            if Formulation.objects.filter(designation=designation).exists():
                obj = Formulation.objects.get(designation=designation)
                self._formulations[designation] = obj
                _warn(self, f"Formulation '{designation}' already exists — skipped")
                continue

            obj = Formulation(
                designation=designation,
                finished_product=data["finished_product"],
                reference_batch_qty=data["reference_batch_qty"],
                reference_batch_unit=self._units[data["unit_code"]],
                expected_yield_pct=data["expected_yield_pct"],
                created_by=self._manager,
            )
            obj.save()

            for rm, qty, unit_code, tolerance in data["lines"]:
                FormulationLine.objects.create(
                    formulation=obj,
                    raw_material=rm,
                    qty_per_batch=qty,
                    unit_of_measure=self._units[unit_code],
                    tolerance_pct=tolerance,
                )

            self._formulations[designation] = obj
            _ok(self, f"Formulation: {obj.reference} v{obj.version} — {designation}")

    # ===================================================================
    # PHASE 9 — SUPPLIER DNs  (creates RM stock via signal)
    # ===================================================================

    def _seed_supplier_dns(self):
        _section(self, "Supplier Delivery Notes (→ RM stock)")
        from supplier_ops.models import SupplierDN, SupplierDNLine
        from core.models import PieceJointe

        pp = self._raw_materials["Polypropylène PP Homopolymère"]
        pehd = self._raw_materials["Polyéthylène haute densité PEHD"]
        mb_n = self._raw_materials["Colorant masterbatch noir"]
        mb_b = self._raw_materials["Colorant masterbatch blanc"]
        stab = self._raw_materials["Stabilisant thermique UV"]
        lub = self._raw_materials["Lubrifiant silicone industriel"]

        dns_data = [
            {
                "ext_ref": "BC-2026-001",
                "supplier": "FRNR-001",
                "delivery_date": datetime.date(2026, 1, 10),
                "lines": [
                    (pp, Decimal("2000.000"), "KG", Decimal("180.00")),
                    (pehd, Decimal("1500.000"), "KG", Decimal("190.00")),
                ],
            },
            {
                "ext_ref": "BC-2026-002",
                "supplier": "FRNR-002",
                "delivery_date": datetime.date(2026, 1, 15),
                "lines": [
                    (mb_n, Decimal("200.000"), "KG", Decimal("410.00")),
                    (mb_b, Decimal("200.000"), "KG", Decimal("385.00")),
                    (stab, Decimal("80.000"), "KG", Decimal("1240.00")),
                ],
            },
            {
                "ext_ref": "BC-2026-003",
                "supplier": "FRNR-003",
                "delivery_date": datetime.date(2026, 2, 5),
                "lines": [
                    (lub, Decimal("100.000"), "L", Decimal("840.00")),
                    (stab, Decimal("40.000"), "KG", Decimal("1245.00")),
                ],
            },
            {
                "ext_ref": "BC-2026-004",
                "supplier": "FRNR-001",
                "delivery_date": datetime.date(2026, 3, 1),
                "lines": [
                    (pp, Decimal("3000.000"), "KG", Decimal("182.00")),
                    (pehd, Decimal("2500.000"), "KG", Decimal("192.00")),
                ],
            },
            {
                "ext_ref": "BC-2026-005",
                "supplier": "FRNR-002",
                "delivery_date": datetime.date(2026, 3, 20),
                "lines": [
                    (mb_n, Decimal("300.000"), "KG", Decimal("412.00")),
                    (mb_b, Decimal("150.000"), "KG", Decimal("388.00")),
                    (stab, Decimal("60.000"), "KG", Decimal("1250.00")),
                ],
            },
            {
                "ext_ref": "BC-2026-006",
                "supplier": "FRNR-001",
                "delivery_date": datetime.date(2026, 4, 8),
                "lines": [
                    (pp, Decimal("2500.000"), "KG", Decimal("183.00")),
                    (pehd, Decimal("2000.000"), "KG", Decimal("193.00")),
                    (lub, Decimal("50.000"), "L", Decimal("845.00")),
                ],
            },
        ]

        self._supplier_dns = []
        for data in dns_data:
            ext_ref = data["ext_ref"]
            if SupplierDN.objects.filter(external_reference=ext_ref).exists():
                dn = SupplierDN.objects.get(external_reference=ext_ref)
                self._supplier_dns.append(dn)
                _warn(self, f"SupplierDN ext_ref='{ext_ref}' already exists — skipped")
                continue

            supplier = self._suppliers[data["supplier"]]

            # 1. Create in draft
            dn = SupplierDN.objects.create(
                site=self._main_site,
                external_reference=ext_ref,
                supplier=supplier,
                delivery_date=data["delivery_date"],
                status="draft",
                created_by=self._manager,
            )
            # 2. Add lines
            for rm, qty, unit_code, price in data["lines"]:
                SupplierDNLine.objects.create(
                    supplier_dn=dn,
                    raw_material=rm,
                    quantity_received=qty,
                    unit_of_measure=self._units[unit_code],
                    agreed_unit_price=price,
                )
            # 3. Move to pending
            dn.transition_to("pending", self._manager)

            # 4. Attach required SD-DNF piece jointe (PieceJointe, core.models)
            PieceJointe.objects.create(
                content_object=dn,
                type_document=PieceJointe.TYPE_SD_DNF,
                description=f"BL fournisseur signé — {ext_ref}",
                uploaded_by=self._stock,
            )
            # 5. Validate (triggers stock signal)
            dn.validate(user=self._stock)
            self._supplier_dns.append(dn)
            _ok(
                self,
                f"SupplierDN: {dn.reference} — {ext_ref} (validated → RM stock updated)",
            )

    # ===================================================================
    # PHASE 10 — PRODUCTION ORDERS  (creates FG stock via signal)
    # ===================================================================

    def _seed_production_orders(self):
        _section(self, "Production Orders (→ FG stock)")
        from production.models import ProductionOrder

        f1 = self._formulations["Formulation Bidon PP 5L Noir"]
        f2 = self._formulations["Formulation Bidon PEHD 10L Blanc"]
        f3 = self._formulations["Formulation Fût industriel 30L"]

        pos_data = [
            {
                "formulation": f1,
                "target_qty": Decimal("200.000"),
                "launch_date": datetime.date(2026, 1, 20),
                "actual_qty": Decimal("196.000"),
                "consumption": {
                    "Polypropylène PP Homopolymère": Decimal("963.000"),
                    "Colorant masterbatch noir": Decimal("19.400"),
                    "Stabilisant thermique UV": Decimal("4.800"),
                },
            },
            {
                "formulation": f2,
                "target_qty": Decimal("150.000"),
                "launch_date": datetime.date(2026, 2, 1),
                "actual_qty": Decimal("143.000"),
                "consumption": {
                    "Polyéthylène haute densité PEHD": Decimal("1470.000"),
                    "Colorant masterbatch blanc": Decimal("29.400"),
                    "Stabilisant thermique UV": Decimal("7.350"),
                },
            },
            {
                "formulation": f3,
                "target_qty": Decimal("80.000"),
                "launch_date": datetime.date(2026, 2, 15),
                "actual_qty": Decimal("75.000"),
                "consumption": {
                    "Polyéthylène haute densité PEHD": Decimal("2330.000"),
                    "Colorant masterbatch noir": Decimal("46.500"),
                    "Stabilisant thermique UV": Decimal("11.600"),
                },
            },
            {
                "formulation": f1,
                "target_qty": Decimal("300.000"),
                "launch_date": datetime.date(2026, 3, 10),
                "actual_qty": Decimal("294.000"),
                "consumption": {
                    "Polypropylène PP Homopolymère": Decimal("1446.000"),
                    "Colorant masterbatch noir": Decimal("28.800"),
                    "Stabilisant thermique UV": Decimal("7.200"),
                },
            },
            # March — PEHD 10L run with near-warning yield (88.7% < 90% threshold)
            {
                "formulation": f2,
                "target_qty": Decimal("200.000"),
                "launch_date": datetime.date(2026, 3, 22),
                "actual_qty": Decimal("177.000"),
                "consumption": {
                    "Polyéthylène haute densité PEHD": Decimal("1980.000"),
                    "Colorant masterbatch blanc": Decimal("39.600"),
                    "Stabilisant thermique UV": Decimal("9.900"),
                },
            },
            # April — Fût 30L large run
            {
                "formulation": f3,
                "target_qty": Decimal("120.000"),
                "launch_date": datetime.date(2026, 4, 5),
                "actual_qty": Decimal("115.000"),
                "consumption": {
                    "Polyéthylène haute densité PEHD": Decimal("3510.000"),
                    "Colorant masterbatch noir": Decimal("70.200"),
                    "Stabilisant thermique UV": Decimal("17.550"),
                },
            },
            # April — PP 5L replenishment for growing demand
            {
                "formulation": f1,
                "target_qty": Decimal("400.000"),
                "launch_date": datetime.date(2026, 4, 18),
                "actual_qty": Decimal("391.000"),
                "consumption": {
                    "Polypropylène PP Homopolymère": Decimal("1924.000"),
                    "Colorant masterbatch noir": Decimal("38.400"),
                    "Stabilisant thermique UV": Decimal("9.600"),
                },
            },
        ]

        self._production_orders = []
        for data in pos_data:
            formulation = data["formulation"]
            launch_date = data["launch_date"]

            if ProductionOrder.objects.filter(
                formulation=formulation,
                launch_date=launch_date,
                actual_qty_produced=data["actual_qty"],
            ).exists():
                po = ProductionOrder.objects.get(
                    formulation=formulation,
                    launch_date=launch_date,
                    actual_qty_produced=data["actual_qty"],
                )
                self._production_orders.append(po)
                _warn(
                    self,
                    f"ProductionOrder for '{formulation.designation}' on {launch_date} already exists — skipped",
                )
                continue

            po = ProductionOrder(
                site=self._main_site,
                formulation=formulation,
                formulation_version=formulation.version,
                target_qty=data["target_qty"],
                target_unit=self._units["PCE"],
                launch_date=launch_date,
                created_by=self._stock,
            )
            po.save()

            # pending → validated
            insufficient = po.validate(user=self._stock)
            if insufficient:
                _warn(
                    self,
                    f"  Stock check: {len(insufficient)} shortages (proceeding anyway for demo)",
                )

            # validated → in_progress (creates consumption lines)
            po.launch(user=self._stock)

            # Build consumption_data dict {raw_material_id: qty}
            consumption_data = {}
            for mat_designation, qty in data["consumption"].items():
                rm = self._raw_materials[mat_designation]
                consumption_data[rm.pk] = qty

            # in_progress → completed (signals handle stock movements)
            po.close(
                user=self._stock,
                actual_qty_produced=data["actual_qty"],
                consumption_data=consumption_data,
            )

            self._production_orders.append(po)
            _ok(
                self,
                f"ProductionOrder: {po.reference} — {formulation.designation} "
                f"× {data['actual_qty']} pce (completed)",
            )

    # ===================================================================
    # PHASE 11 — SUPPLIER INVOICES
    # ===================================================================

    def _seed_supplier_invoices(self):
        _section(self, "Supplier Invoices")
        from supplier_ops.models import (
            SupplierInvoice,
            SupplierInvoiceLine,
            SupplierInvoiceDNLink,
        )

        year = datetime.date.today().year
        invoice_data = [
            {
                "ext_ref": "FF-PETROCHIM-2601",
                "supplier": "FRNR-001",
                "invoice_date": datetime.date(2026, 1, 18),
                "due_date": datetime.date(2026, 2, 17),
                "linked_dns_ext": ["BC-2026-001"],
                "lines": [
                    (
                        "Polypropylène PP Homopolymère",
                        Decimal("2000.000"),
                        Decimal("180.00"),
                    ),
                    (
                        "Polyéthylène haute densité PEHD",
                        Decimal("1500.000"),
                        Decimal("190.00"),
                    ),
                ],
            },
            {
                "ext_ref": "FF-POLYPLUS-2601",
                "supplier": "FRNR-002",
                "invoice_date": datetime.date(2026, 1, 20),
                "due_date": datetime.date(2026, 3, 5),
                "linked_dns_ext": ["BC-2026-002"],
                "lines": [
                    (
                        "Colorant masterbatch noir",
                        Decimal("200.000"),
                        Decimal("415.00"),
                    ),
                    (
                        "Colorant masterbatch blanc",
                        Decimal("200.000"),
                        Decimal("388.00"),
                    ),
                    ("Stabilisant thermique UV", Decimal("80.000"), Decimal("1245.00")),
                ],
            },
            {
                "ext_ref": "FF-PETROCHIM-2603",
                "supplier": "FRNR-001",
                "invoice_date": datetime.date(2026, 3, 8),
                "due_date": datetime.date(2026, 4, 7),
                "linked_dns_ext": ["BC-2026-004"],
                "lines": [
                    (
                        "Polypropylène PP Homopolymère",
                        Decimal("3000.000"),
                        Decimal("182.00"),
                    ),
                    (
                        "Polyéthylène haute densité PEHD",
                        Decimal("2500.000"),
                        Decimal("192.00"),
                    ),
                ],
            },
            {
                "ext_ref": "FF-POLYPLUS-2603",
                "supplier": "FRNR-002",
                "invoice_date": datetime.date(2026, 3, 25),
                "due_date": datetime.date(2026, 5, 9),
                "linked_dns_ext": ["BC-2026-005"],
                "lines": [
                    (
                        "Colorant masterbatch noir",
                        Decimal("300.000"),
                        Decimal("412.00"),
                    ),
                    (
                        "Colorant masterbatch blanc",
                        Decimal("150.000"),
                        Decimal("388.00"),
                    ),
                    ("Stabilisant thermique UV", Decimal("60.000"), Decimal("1250.00")),
                ],
            },
        ]

        self._supplier_invoices = []
        for data in invoice_data:
            ext_ref = data["ext_ref"]
            if SupplierInvoice.objects.filter(external_reference=ext_ref).exists():
                inv = SupplierInvoice.objects.get(external_reference=ext_ref)
                self._supplier_invoices.append(inv)
                _warn(self, f"SupplierInvoice '{ext_ref}' already exists — skipped")
                continue

            supplier = self._suppliers[data["supplier"]]
            inv = SupplierInvoice.objects.create(
                external_reference=ext_ref,
                supplier=supplier,
                invoice_date=data["invoice_date"],
                due_date=data["due_date"],
                status="entered",
                created_by=self._accountant,
            )
            # Lines
            for designation, qty, price in data["lines"]:
                rm = self._raw_materials[designation]
                SupplierInvoiceLine.objects.create(
                    supplier_invoice=inv,
                    raw_material=rm,
                    designation=designation,
                    quantity_invoiced=qty,
                    unit_price_invoiced=price,
                )
            # Link DNs
            for dn_ext_ref in data["linked_dns_ext"]:
                dn = SupplierDN.objects.get(external_reference=dn_ext_ref)
                SupplierInvoiceDNLink.objects.create(
                    supplier_invoice=inv, supplier_dn=dn
                )
                # Mark DN as linked
                dn.linked_invoice = inv
                dn.save()

            # Transition entered → verified (manual, no reconciliation)
            inv.transition_to("verified", self._accountant)
            # Transition verified → unpaid
            inv.refresh_from_db()
            if inv.status == "verified":
                inv.transition_to("unpaid", self._accountant)

            self._supplier_invoices.append(inv)
            _ok(
                self,
                f"SupplierInvoice: {inv.reference} ({ext_ref}) — "
                f"status={inv.status}, total_ttc={inv.total_ttc}",
            )

    # ===================================================================
    # PHASE 12 — CLIENT DNs  (deducts FG stock via signal)
    # ===================================================================

    def _seed_client_dns(self):
        _section(self, "Client Delivery Notes (→ FG stock deduction)")
        from sales.models import ClientDN, ClientDNLine

        fp1 = self._finished_products["Bidon PP 5L noir"]
        fp2 = self._finished_products["Bidon PEHD 10L blanc"]
        fp3 = self._finished_products["Fût industriel 30L"]

        dns_data = [
            # January
            {
                "client": "CLT-001",
                "delivery_date": datetime.date(2026, 1, 28),
                "discount_pct": Decimal("3.00"),
                "lines": [
                    (fp1, Decimal("80.000"), "PCE", Decimal("375.00")),
                    (fp2, Decimal("40.000"), "PCE", Decimal("615.00")),
                ],
            },
            # February
            {
                "client": "CLT-001",
                "delivery_date": datetime.date(2026, 2, 10),
                "discount_pct": Decimal("3.00"),
                "lines": [
                    (fp1, Decimal("100.000"), "PCE", Decimal("375.00")),
                    (fp2, Decimal("50.000"), "PCE", Decimal("615.00")),
                ],
            },
            {
                "client": "CLT-002",
                "delivery_date": datetime.date(2026, 2, 20),
                "discount_pct": Decimal("5.00"),
                "lines": [
                    (fp2, Decimal("80.000"), "PCE", Decimal("610.00")),
                    (fp3, Decimal("20.000"), "PCE", Decimal("1440.00")),
                ],
            },
            {
                "client": "CLT-004",
                "delivery_date": datetime.date(2026, 2, 25),
                "discount_pct": Decimal("4.00"),
                "lines": [
                    (fp1, Decimal("120.000"), "PCE", Decimal("376.00")),
                    (fp3, Decimal("15.000"), "PCE", Decimal("1445.00")),
                ],
            },
            # March
            {
                "client": "CLT-001",
                "delivery_date": datetime.date(2026, 3, 15),
                "discount_pct": Decimal("3.00"),
                "lines": [
                    (fp1, Decimal("150.000"), "PCE", Decimal("378.00")),
                ],
            },
            {
                "client": "CLT-005",
                "delivery_date": datetime.date(2026, 3, 20),
                "discount_pct": Decimal("6.00"),
                "lines": [
                    (fp2, Decimal("60.000"), "PCE", Decimal("612.00")),
                    (fp3, Decimal("30.000"), "PCE", Decimal("1442.00")),
                ],
            },
            # April
            {
                "client": "CLT-002",
                "delivery_date": datetime.date(2026, 4, 10),
                "discount_pct": Decimal("5.00"),
                "lines": [
                    (fp1, Decimal("200.000"), "PCE", Decimal("380.00")),
                    (fp2, Decimal("70.000"), "PCE", Decimal("618.00")),
                ],
            },
            {
                "client": "CLT-004",
                "delivery_date": datetime.date(2026, 4, 22),
                "discount_pct": Decimal("4.00"),
                "lines": [
                    (fp1, Decimal("180.000"), "PCE", Decimal("380.00")),
                    (fp3, Decimal("25.000"), "PCE", Decimal("1450.00")),
                ],
            },
        ]

        self._client_dns = []
        for data in dns_data:
            client = self._clients[data["client"]]
            delivery_date = data["delivery_date"]

            # Simple duplicate guard on (client, delivery_date, discount)
            if ClientDN.objects.filter(
                client=client,
                delivery_date=delivery_date,
                discount_pct=data["discount_pct"],
            ).exists():
                dn = ClientDN.objects.filter(
                    client=client,
                    delivery_date=delivery_date,
                    discount_pct=data["discount_pct"],
                ).first()
                self._client_dns.append(dn)
                _warn(
                    self,
                    f"ClientDN for {client.code} on {delivery_date} already exists — skipped",
                )
                continue

            dn = ClientDN(
                site=self._main_site,
                client=client,
                delivery_date=delivery_date,
                discount_pct=data["discount_pct"],
                status="draft",
                created_by=self._sales,
            )
            dn.save()

            for fp, qty, unit_code, price in data["lines"]:
                ClientDNLine.objects.create(
                    client_dn=dn,
                    finished_product=fp,
                    quantity_delivered=qty,
                    unit_of_measure=self._units[unit_code],
                    selling_unit_price_ht=price,
                )
            dn.refresh_from_db()

            # Validate (checks stock, then signal deducts FG stock)
            try:
                dn.validate(user=self._sales)
                _ok(
                    self,
                    f"ClientDN: {dn.reference} — {client.code} on {delivery_date} (validated)",
                )
            except Exception as exc:
                _warn(self, f"ClientDN {dn.reference} validation failed: {exc}")

            self._client_dns.append(dn)

    # ===================================================================
    # PHASE 13 — CLIENT INVOICES
    # ===================================================================

    def _seed_client_invoices(self):
        _section(self, "Client Invoices")
        from sales.models import ClientInvoice, ClientInvoiceDNLink, ClientPayment

        self._client_invoices = []
        invoice_data = [
            # Invoice 1 — CLT-001 Jan+Feb DNs, partial payment
            {
                "client": "CLT-001",
                "invoice_date": datetime.date(2026, 2, 12),
                "discount_pct": Decimal("0.00"),
                "dn_indices": [0, 1],  # Jan-28 + Feb-10 DNs
                "partial_payment": Decimal("80000.00"),
            },
            # Invoice 2 — CLT-002 Feb DN, discount, no payment yet
            {
                "client": "CLT-002",
                "invoice_date": datetime.date(2026, 2, 22),
                "discount_pct": Decimal("2.00"),
                "dn_indices": [2],
                "partial_payment": None,
            },
            # Invoice 3 — CLT-004 Feb DN, partially paid
            {
                "client": "CLT-004",
                "invoice_date": datetime.date(2026, 3, 1),
                "discount_pct": Decimal("1.00"),
                "dn_indices": [3],
                "partial_payment": Decimal("100000.00"),
            },
            # Invoice 4 — CLT-001 March DN, fully paid
            {
                "client": "CLT-001",
                "invoice_date": datetime.date(2026, 3, 18),
                "discount_pct": Decimal("0.00"),
                "dn_indices": [4],
                "partial_payment": None,
                "full_payment": Decimal("56700.00"),
            },
            # Invoice 5 — CLT-005 March DN, no payment (recent)
            {
                "client": "CLT-005",
                "invoice_date": datetime.date(2026, 3, 22),
                "discount_pct": Decimal("3.00"),
                "dn_indices": [5],
                "partial_payment": None,
            },
        ]

        for data in invoice_data:
            client = self._clients[data["client"]]
            if ClientInvoice.objects.filter(
                client=client, invoice_date=data["invoice_date"]
            ).exists():
                inv = ClientInvoice.objects.filter(
                    client=client, invoice_date=data["invoice_date"]
                ).first()
                self._client_invoices.append(inv)
                _warn(
                    self,
                    f"ClientInvoice for {client.code} on {data['invoice_date']} already exists — skipped",
                )
                continue

            inv = ClientInvoice(
                client=client,
                invoice_date=data["invoice_date"],
                due_date=data["invoice_date"]
                + datetime.timedelta(days=client.payment_terms),
                discount_pct=data["discount_pct"],
                created_by=self._accountant,
            )
            inv.save()

            # Link DNs
            for idx in data["dn_indices"]:
                if idx < len(self._client_dns):
                    dn = self._client_dns[idx]
                    ClientInvoiceDNLink.objects.get_or_create(
                        client_invoice=inv, client_dn=dn
                    )
                    dn.linked_invoice = inv
                    dn.save()

            inv.save()  # recompute totals

            # Partial payment
            if data.get("partial_payment"):
                ClientPayment.objects.create(
                    client_invoice=inv,
                    client=client,
                    payment_date=data["invoice_date"] + datetime.timedelta(days=10),
                    amount=data["partial_payment"],
                    payment_method="transfer",
                    bank_reference=f"VIR-{inv.reference}",
                    recorded_by=self._accountant,
                )
                inv.recompute_balance_due()

            # Full payment
            if data.get("full_payment"):
                inv.refresh_from_db()
                ClientPayment.objects.create(
                    client_invoice=inv,
                    client=client,
                    payment_date=data["invoice_date"] + datetime.timedelta(days=15),
                    amount=data["full_payment"],
                    payment_method="cheque",
                    bank_reference=f"CHQ-{inv.reference}",
                    recorded_by=self._accountant,
                )
                inv.recompute_balance_due()

            inv.refresh_from_db()
            _ok(
                self,
                f"ClientInvoice: {inv.reference} — {client.code}, "
                f"TTC={inv.total_ttc}, solde={inv.balance_due}",
            )
            self._client_invoices.append(inv)

    # ===================================================================
    # PHASE 14 — STOCK ADJUSTMENTS
    # ===================================================================

    def _seed_stock_adjustments(self):
        _section(self, "Stock Adjustments")
        from stock.models import (
            StockAdjustment,
            StockAdjustmentLine,
            RawMaterialStockBalance,
            FinishedProductStockBalance,
        )

        pp = self._raw_materials["Polypropylène PP Homopolymère"]
        mb_n = self._raw_materials["Colorant masterbatch noir"]
        stab = self._raw_materials["Stabilisant thermique UV"]
        lub = self._raw_materials["Lubrifiant silicone industriel"]
        fp1 = self._finished_products["Bidon PP 5L noir"]
        fp2 = self._finished_products["Bidon PEHD 10L blanc"]
        fp3 = self._finished_products["Fût industriel 30L"]

        def rm_qty(rm):
            """Return current stock quantity for a raw material at the seed
            site (0 if no balance yet). Site-scoped since multi-site
            (§25.2) turned RawMaterialStockBalance into one row PER SITE."""
            try:
                return RawMaterialStockBalance.objects.get(
                    site=self._main_site, raw_material=rm
                ).quantity
            except RawMaterialStockBalance.DoesNotExist:
                return Decimal("0.000")

        def fg_qty(fp):
            """Return current stock quantity for a finished product at the
            seed site — see rm_qty()."""
            try:
                return FinishedProductStockBalance.objects.get(
                    site=self._main_site, finished_product=fp
                ).quantity
            except FinishedProductStockBalance.DoesNotExist:
                return Decimal("0.000")

        # Each entry: adjustment_type must be one of:
        #   inventory | correction | loss | damage | return
        #
        # Lines are tuples of:
        #   RM lines  → (raw_material_obj,  delta,  remarks)
        #   FG lines  → (finished_product_obj, delta, remarks)
        #
        # delta is the signed change; quantity_after = quantity_before + delta.
        # quantity_before is read live from the stock balance at seed time so
        # the before/after snapshot is always consistent with production data.
        adjustments_data = [
            # ── End-of-January inventory count ──────────────────────────
            {
                "adjustment_date": datetime.date(2026, 1, 31),
                "reason": "Inventaire physique fin janvier — écart constaté",
                "adjustment_type": "inventory",
                "rm_lines": [
                    (pp, Decimal("-25.000"), "Écart inventaire PP — perte de mesure"),
                    (mb_n, Decimal("-2.500"), "Écart inventaire masterbatch noir"),
                ],
                "fg_lines": [],
            },
            # ── February damage write-off ────────────────────────────────
            {
                "adjustment_date": datetime.date(2026, 2, 28),
                "reason": "Mise au rebut produits endommagés — humidité entrepôt",
                "adjustment_type": "damage",
                "rm_lines": [
                    (
                        stab,
                        Decimal("-3.000"),
                        "Stabilisant dégradé — exposition humidité",
                    ),
                    (lub, Decimal("-5.000"), "Lubrifiant contaminé — fût percé"),
                ],
                "fg_lines": [
                    (
                        fp2,
                        Decimal("-8.000"),
                        "Bidons PEHD 10L déformés — stockage incorrect",
                    ),
                ],
            },
            # ── End-of-Q1 count — mixed surplus/deficit ──────────────────
            {
                "adjustment_date": datetime.date(2026, 3, 31),
                "reason": "Inventaire trimestriel — écarts constatés sur MP et PF",
                "adjustment_type": "inventory",
                "rm_lines": [
                    (
                        pp,
                        Decimal("12.000"),
                        "Surplus PP — retour production non enregistré",
                    ),
                ],
                "fg_lines": [
                    (
                        fp1,
                        Decimal("5.000"),
                        "Bidons PP 5L surplus — lot non comptabilisé",
                    ),
                    (fp3, Decimal("-3.000"), "Fûts 30L — écart comptage négatif"),
                ],
            },
            # ── April quality rejection ───────────────────────────────────
            {
                "adjustment_date": datetime.date(2026, 4, 12),
                "reason": "Rejet qualité — non-conformité contrôle colorimétrique",
                "adjustment_type": "loss",
                "rm_lines": [],
                "fg_lines": [
                    (
                        fp1,
                        Decimal("-12.000"),
                        "Bidons PP 5L — défaut couleur lot OP-2026-007",
                    ),
                    (
                        fp2,
                        Decimal("-5.000"),
                        "Bidons PEHD 10L — inclusion corps étranger",
                    ),
                ],
            },
        ]

        for data in adjustments_data:
            adj_date = data["adjustment_date"]
            reason = data["reason"]

            if StockAdjustment.objects.filter(
                adjustment_date=adj_date, reason=reason
            ).exists():
                _warn(self, f"StockAdjustment on {adj_date} already exists — skipped")
                continue

            adj = StockAdjustment(
                site=self._main_site,
                adjustment_date=adj_date,
                reason=reason,
                adjustment_type=data["adjustment_type"],
                created_by=self._stock,
            )
            adj.save()

            # ── Raw material lines ────────────────────────────────────────
            for rm, delta, remarks in data["rm_lines"]:
                qty_before = rm_qty(rm)
                qty_after = max(Decimal("0.000"), qty_before + delta)
                StockAdjustmentLine.objects.create(
                    stock_adjustment=adj,
                    raw_material=rm,
                    finished_product=None,
                    quantity_before=qty_before,
                    quantity_after=qty_after,
                    remarks=remarks,
                )

            # ── Finished product lines ────────────────────────────────────
            for fp, delta, remarks in data["fg_lines"]:
                qty_before = fg_qty(fp)
                qty_after = max(Decimal("0.000"), qty_before + delta)
                StockAdjustmentLine.objects.create(
                    stock_adjustment=adj,
                    raw_material=None,
                    finished_product=fp,
                    quantity_before=qty_before,
                    quantity_after=qty_after,
                    remarks=remarks,
                )

            # approve() creates StockMovement records and is the only
            # permitted write path per spec BR-RM-05.
            try:
                adj.approve(user=self._manager)
                _ok(
                    self,
                    f"StockAdjustment: {adj.reference} — {reason[:60]} "
                    f"({len(data['rm_lines'])} RM + {len(data['fg_lines'])} FG lines, approved)",
                )
            except Exception as exc:
                _warn(self, f"StockAdjustment {adj.reference} approval failed: {exc}")

    # ===================================================================
    # PHASE 15 — EXPENSES
    # ===================================================================

    def _seed_expenses(self):
        _section(self, "Expenses")
        from expenses.models import Expense

        expenses_data = [
            # ── January ──────────────────────────────────────────────────────
            {
                "expense_date": datetime.date(2026, 1, 5),
                "category": "ENERGIE",
                "description": "Facture électricité — janvier 2026",
                "amount": Decimal("185000.00"),
                "beneficiary": "Sonelgaz",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 1, 20),
            },
            {
                "expense_date": datetime.date(2026, 1, 8),
                "category": "TRANSPORT",
                "description": "Transport matières premières — livraison BC-2026-001",
                "amount": Decimal("42000.00"),
                "beneficiary": "TransLog SARL",
                "status": "paid",
                "payment_method": "cheque",
                "payment_date": datetime.date(2026, 1, 25),
            },
            {
                "expense_date": datetime.date(2026, 1, 10),
                "category": "SALAIRES",
                "description": "Salaires et charges sociales — janvier 2026",
                "amount": Decimal("850000.00"),
                "beneficiary": "Personnel AlgéroPlast",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 1, 28),
            },
            {
                "expense_date": datetime.date(2026, 1, 15),
                "category": "ENTRETIEN",
                "description": "Entretien préventif presse injection n°3",
                "amount": Decimal("28500.00"),
                "beneficiary": "MécaTech SPA",
                "status": "paid",
                "payment_method": "cheque",
                "payment_date": datetime.date(2026, 2, 1),
            },
            {
                "expense_date": datetime.date(2026, 1, 20),
                "category": "LOYER",
                "description": "Loyer entrepôt — janvier 2026",
                "amount": Decimal("120000.00"),
                "beneficiary": "Immobilière Sétif SARL",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 1, 22),
            },
            # ── February ──────────────────────────────────────────────────────
            {
                "expense_date": datetime.date(2026, 2, 3),
                "category": "FOURNITURES",
                "description": "Fournitures de bureau — T1 2026",
                "amount": Decimal("8750.00"),
                "beneficiary": "PaperShop EURL",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 2, 5),
                "category": "SALAIRES",
                "description": "Salaires et charges sociales — février 2026",
                "amount": Decimal("855000.00"),
                "beneficiary": "Personnel AlgéroPlast",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 2, 27),
            },
            {
                "expense_date": datetime.date(2026, 2, 10),
                "category": "ENERGIE",
                "description": "Facture gaz industriel — février 2026",
                "amount": Decimal("67000.00"),
                "beneficiary": "Naftal",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 2, 25),
            },
            {
                "expense_date": datetime.date(2026, 2, 12),
                "category": "TRANSPORT",
                "description": "Transport livraison clients — zone Est",
                "amount": Decimal("38000.00"),
                "beneficiary": "TransLog SARL",
                "status": "paid",
                "payment_method": "cheque",
                "payment_date": datetime.date(2026, 3, 5),
            },
            {
                "expense_date": datetime.date(2026, 2, 18),
                "category": "ENTRETIEN",
                "description": "Remplacement courroies ligne extrusion n°1",
                "amount": Decimal("15200.00"),
                "beneficiary": "MécaTech SPA",
                "status": "paid",
                "payment_method": "cheque",
                "payment_date": datetime.date(2026, 3, 1),
            },
            # ── March ──────────────────────────────────────────────────────
            {
                "expense_date": datetime.date(2026, 3, 1),
                "category": "LOYER",
                "description": "Loyer entrepôt — mars 2026",
                "amount": Decimal("120000.00"),
                "beneficiary": "Immobilière Sétif SARL",
                "status": "recorded",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 3, 5),
                "category": "SALAIRES",
                "description": "Salaires et charges sociales — mars 2026",
                "amount": Decimal("860000.00"),
                "beneficiary": "Personnel AlgéroPlast",
                "status": "paid",
                "payment_method": "transfer",
                "payment_date": datetime.date(2026, 3, 28),
            },
            {
                "expense_date": datetime.date(2026, 3, 5),
                "category": "COMM",
                "description": "Frais déplacement commercial — prospection clients Est",
                "amount": Decimal("35000.00"),
                "beneficiary": "Samira Rahmani",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 3, 8),
                "category": "ENERGIE",
                "description": "Facture électricité — mars 2026",
                "amount": Decimal("192000.00"),
                "beneficiary": "Sonelgaz",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 3, 10),
                "category": "DIVERS",
                "description": "Réparation véhicule commercial",
                "amount": Decimal("18400.00"),
                "beneficiary": "AutoService DZ",
                "status": "recorded",
                "payment_method": "",
                "payment_date": None,
            },
            # ── April ──────────────────────────────────────────────────────
            {
                "expense_date": datetime.date(2026, 4, 2),
                "category": "LOYER",
                "description": "Loyer entrepôt — avril 2026",
                "amount": Decimal("120000.00"),
                "beneficiary": "Immobilière Sétif SARL",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 4, 5),
                "category": "SALAIRES",
                "description": "Salaires et charges sociales — avril 2026",
                "amount": Decimal("860000.00"),
                "beneficiary": "Personnel AlgéroPlast",
                "status": "recorded",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 4, 10),
                "category": "TRANSPORT",
                "description": "Transport matières premières — livraison BC-2026-006",
                "amount": Decimal("55000.00"),
                "beneficiary": "TransLog SARL",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 4, 15),
                "category": "ENTRETIEN",
                "description": "Révision générale presse injection n°2",
                "amount": Decimal("47500.00"),
                "beneficiary": "MécaTech SPA",
                "status": "recorded",
                "payment_method": "",
                "payment_date": None,
            },
            {
                "expense_date": datetime.date(2026, 4, 20),
                "category": "COMM",
                "description": "Salon professionnel emballage — stand + déplacements",
                "amount": Decimal("92000.00"),
                "beneficiary": "SAFEX Alger",
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
            },
        ]

        for data in expenses_data:
            description = data["description"]
            if Expense.objects.filter(description=description).exists():
                _warn(self, f"Expense '{description[:50]}' already exists — skipped")
                continue

            category = self._expense_categories[data["category"]]
            expense = Expense(
                expense_date=data["expense_date"],
                category=category,
                description=description,
                amount=data["amount"],
                beneficiary=data["beneficiary"],
                created_by=self._accountant,
            )
            expense.save()  # reference auto-generated

            # Apply status directly (bypassing delegation gate for seed data)
            if data["status"] in ("validated", "paid"):
                Expense.objects.filter(pk=expense.pk).update(
                    status=data["status"],
                    validated_by=self._manager,
                    validated_at=timezone.now(),
                )
            if data["status"] == "paid" and data["payment_date"]:
                Expense.objects.filter(pk=expense.pk).update(
                    payment_method=data["payment_method"],
                    payment_date=data["payment_date"],
                )

            expense.refresh_from_db()
            _ok(
                self,
                f"Expense: {expense.reference} — {description[:50]} "
                f"({expense.amount} DZD, {expense.status})",
            )
