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
            self._seed_expenses()

        self.stdout.write(
            self.style.SUCCESS("\n✅  populate_db completed successfully.\n")
        )

    # ===================================================================
    # FLUSH
    # ===================================================================

    def _flush(self):
        _section(self, "Flushing transactional data")
        from sales.models import ClientPayment, ClientInvoice, ClientDN
        from supplier_ops.models import (
            SupplierPayment,
            SupplierInvoice,
            SupplierDN,
            ReconciliationLine,
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
            ClientPayment,
            ClientInvoice,
            ClientDN,
            SupplierPayment,
            ReconciliationLine,
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

        # Pre-seed document sequences so references start clean
        sequences = [
            ("RM", 0, "Matières premières"),
            ("PF", 0, "Produits finis"),
            ("F", 0, "Formulations"),
            ("BL-F", datetime.date.today().year, "BL Fournisseur"),
            ("FF", datetime.date.today().year, "Factures Fournisseur"),
            ("PAY-F", datetime.date.today().year, "Paiements Fournisseur"),
            ("BL-C", datetime.date.today().year, "BL Client"),
            ("FC", datetime.date.today().year, "Factures Client"),
            ("PAY-C", datetime.date.today().year, "Paiements Client"),
            ("DEP", datetime.date.today().year, "Dépenses"),
            ("OP", datetime.date.today().year, "Ordres de Production"),
            ("ADJ", datetime.date.today().year, "Ajustements stock"),
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
                user.set_password("Demo1234!")
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
        from expenses.models import SupportingDocument

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

            # 4. Attach required SD-DNF supporting document
            SupportingDocument.objects.create(
                doc_type="SD-DNF",
                entity_type="supplierdn",
                entity_id=dn.pk,
                description=f"BL fournisseur signé — {ext_ref}",
                file_reference=f"scans/dn/{ext_ref}.pdf",
                registered_by=self._stock,
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

            # Reconcile → sets status to verified/dispute automatically
            inv.perform_reconciliation()

            # Transition verified → unpaid
            inv.refresh_from_db()
            if inv.status == "verified":
                inv.transition_to("unpaid", self._accountant)

            self._supplier_invoices.append(inv)
            _ok(
                self,
                f"SupplierInvoice: {inv.reference} ({ext_ref}) — "
                f"status={inv.status}, delta={inv.reconciliation_delta}",
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
                "client": "CLT-001",
                "delivery_date": datetime.date(2026, 3, 15),
                "discount_pct": Decimal("3.00"),
                "lines": [
                    (fp1, Decimal("150.000"), "PCE", Decimal("378.00")),
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
            {
                "client": "CLT-001",
                "invoice_date": datetime.date(2026, 2, 12),
                "discount_pct": Decimal("0.00"),
                "dn_indices": [0],  # indices into self._client_dns
                "partial_payment": Decimal("50000.00"),
            },
            {
                "client": "CLT-002",
                "invoice_date": datetime.date(2026, 2, 22),
                "discount_pct": Decimal("2.00"),
                "dn_indices": [1],
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
            if data["partial_payment"]:
                ClientPayment.objects.create(
                    client_invoice=inv,
                    client=client,
                    payment_date=data["invoice_date"] + datetime.timedelta(days=10),
                    amount=data["partial_payment"],
                    payment_method="transfer",
                    bank_reference=f"VIR-{inv.reference}",
                    recorded_by=self._accountant,
                )
                # Signal recomputes balance_due; call manually in seed context
                inv.recompute_balance_due()

            inv.refresh_from_db()
            _ok(
                self,
                f"ClientInvoice: {inv.reference} — {client.code}, "
                f"TTC={inv.total_ttc}, solde={inv.balance_due}",
            )
            self._client_invoices.append(inv)

    # ===================================================================
    # PHASE 14 — EXPENSES
    # ===================================================================

    def _seed_expenses(self):
        _section(self, "Expenses")
        from expenses.models import Expense

        expenses_data = [
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
                "status": "validated",
                "payment_method": "",
                "payment_date": None,
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
                "category": "COMM",
                "description": "Frais déplacement commercial — prospection clients Est",
                "amount": Decimal("35000.00"),
                "beneficiary": "Samira Rahmani",
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
