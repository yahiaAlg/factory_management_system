"""
core/management/commands/minimal_populate_db.py

Seeds only the essential master data required for a fully functional
fresh installation.  No suppliers, clients, catalog items, formulations,
or any transactional records are created — those are entered by users
through the UI.

Usage:
    python manage.py minimal_populate_db            # idempotent seed
    python manage.py minimal_populate_db --flush    # wipe everything first, then seed
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _section(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.MIGRATE_HEADING(f"\n▶ {msg}"))


def _warn(self: "Command", msg: str) -> None:
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg}"))


def _skip(self: "Command", label: str) -> None:
    _warn(self, f"{label} already exists — skipped")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Seed the essential master data for a fresh installation. "
        "Idempotent — safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help=(
                "Wipe ALL data (including transactional records) before seeding. "
                "WARNING: irreversible in production."
            ),
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            self._seed_core()
            self._seed_users()
            self._seed_units_and_categories()
            self._seed_expense_categories()

        self.stdout.write(
            self.style.SUCCESS("\n✅  minimal_populate_db completed successfully.\n")
        )
        self.stdout.write(
            "  Next steps:\n"
            "    • Log in as admin (password: admin1234!) and update company info\n"
            "    • Create suppliers via the Fournisseurs module\n"
            "    • Create clients via the Clients module\n"
            "    • Add raw materials & finished products via the Catalogue module\n"
            "    • Define formulations via the Production module\n"
        )

    # ===================================================================
    # FLUSH
    # ===================================================================

    def _flush(self):
        _section(self, "Flushing ALL data")
        from django.apps import apps

        # Order matters — FK constraints; delete transactional first,
        # then reference/master data, then core.
        FLUSH_ORDER = [
            # Transactional
            ("sales", "ClientAccountPayment"),
            ("sales", "ClientPayment"),
            ("sales", "ClientInvoiceDNLink"),
            ("sales", "ClientInvoice"),
            ("sales", "ClientDNLine"),
            ("sales", "ClientDN"),
            ("supplier_ops", "SupplierAccountPayment"),
            ("supplier_ops", "SupplierPayment"),
            ("supplier_ops", "SupplierInvoiceDNLink"),
            ("supplier_ops", "SupplierInvoiceLine"),
            ("supplier_ops", "SupplierInvoice"),
            ("supplier_ops", "SupplierDNLine"),
            ("supplier_ops", "SupplierDN"),
            ("production", "ProductionOrderLine"),
            ("production", "ProductionOrder"),
            ("production", "FormulationLine"),
            ("production", "Formulation"),
            ("stock", "StockAdjustmentLine"),
            ("stock", "StockAdjustment"),
            ("stock", "StockMovement"),
            ("stock", "RawMaterialStockBalance"),
            ("stock", "FinishedProductStockBalance"),
            ("expenses", "SupportingDocument"),
            ("expenses", "Expense"),
            # Reference / master
            ("catalog", "RawMaterial"),
            ("catalog", "FinishedProduct"),
            ("catalog", "UnitOfMeasure"),
            ("catalog", "RawMaterialCategory"),
            ("expenses", "ExpenseCategory"),
            ("clients", "Client"),
            ("suppliers", "Supplier"),
            # Core
            ("core", "DocumentSequence"),
            ("core", "SystemParameter"),
            ("core", "CompanyInformation"),
            # Accounts (users last — keep Django's own auth tables safe)
            ("accounts", "AuditLog"),
            ("accounts", "UserProfile"),
        ]

        for app_label, model_name in FLUSH_ORDER:
            try:
                model = apps.get_model(app_label, model_name)
                count, _ = model.objects.all().delete()
                if count:
                    _ok(self, f"Deleted {count} {model_name} rows")
            except LookupError:
                _warn(self, f"{app_label}.{model_name} not found — skipped")

        # Delete non-superuser accounts created by previous seeds
        deleted, _ = User.objects.filter(is_superuser=False).delete()
        if deleted:
            _ok(self, f"Deleted {deleted} non-superuser User rows")

    # ===================================================================
    # PHASE 1 — CORE
    # ===================================================================

    def _seed_core(self):
        _section(
            self, "Core — CompanyInformation, SystemParameters & DocumentSequences"
        )
        from core.models import CompanyInformation, SystemParameter, DocumentSequence
        from core.utils import get_seed_site

        # ── Production Site (multi-site, §25.2) ──────────────────────────
        # `manage.py flush` (used by every seed script here) truncates
        # ProductionSite but does NOT re-run the core.0004_seed_main_site
        # data migration, so it must be (re-)seeded here explicitly — the
        # earliest step in the pipeline — rather than assumed to already
        # exist. get_seed_site() is idempotent: no-ops if it's already there.
        get_seed_site(self)

        # ── Company Information ──────────────────────────────────────────
        # Pre-filled with placeholder values; update via Settings → Entreprise.
        if not CompanyInformation.objects.exists():
            CompanyInformation.objects.create(
                raison_sociale="Votre Entreprise SARL",
                forme_juridique="SARL",
                nif="",
                nis="",
                rc="",
                ai="",
                address="Adresse à compléter",
                wilaya="",
                phone="",
                email="",
                bank_name="",
                bank_account="",
                rib="",
                vat_rate=Decimal("0.19"),
                fiscal_regime="Réel",
            )
            _ok(self, "CompanyInformation created (placeholder — update via Settings)")
        else:
            _skip(self, "CompanyInformation")

        # ── System Parameters ────────────────────────────────────────────
        # These are the keys the application logic reads at runtime.
        # All values are sensible defaults; adjust in Settings → Paramètres.
        params = [
            # Financial reconciliation
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
            # Expense delegation
            (
                "financial",
                "expense_delegation_threshold",
                "50000.00",
                "Seuil délégation dépenses — validation Manager requise (DZD)",
            ),
            # Production yield alerts
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
            # Payment due alerts
            (
                "alert",
                "payment_due_alert_days",
                "7",
                "Nombre de jours avant échéance pour alerte de paiement",
            ),
            # Tax
            (
                "financial",
                "default_vat_rate",
                "0.19",
                "Taux de TVA par défaut",
            ),
            # Fiscal year
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
            else:
                _skip(self, f"SystemParameter '{key}'")

        # ── Document Sequences ───────────────────────────────────────────
        # One sequence per document prefix; counters start at 0 (next
        # document generated will be 001).  Year-scoped sequences use the
        # current calendar year.
        year = datetime.date.today().year
        # Multi-site (§25.2): BL-F, BL-C, OP, ADJ are per-site sequences —
        # pre-seed the "Site Principal" (MAIN) variant (matching the site
        # get_seed_site() resolved above) so this demo data starts each of
        # those at NNNN=0001 too. Other prefixes stay company-wide.
        site_code = get_seed_site(self).code
        sequences = [
            # Master-data counters (year = 0 → not year-scoped)
            ("RM", 0, "Matières premières"),
            ("PF", 0, "Produits finis"),
            ("F", 0, "Formulations"),
            # Transactional document sequences (year-scoped)
            (f"BL-F-{site_code}", year, "Bons de livraison fournisseur"),
            ("FF", year, "Factures fournisseur"),
            ("PAY-F", year, "Paiements fournisseur"),
            ("RGL-F", year, "Règlements compte fournisseur"),
            (f"BL-C-{site_code}", year, "Bons de livraison client"),
            ("FC", year, "Factures client"),
            ("PAY-C", year, "Paiements client"),
            ("RGL-C", year, "Règlements compte client"),
            ("DEP", year, "Dépenses"),
            (f"OP-{site_code}", year, "Ordres de production"),
            (f"ADJ-{site_code}", year, "Ajustements de stock"),
        ]

        for prefix, seq_year, description in sequences:
            _, created = DocumentSequence.objects.get_or_create(
                prefix=prefix,
                current_year=seq_year,
                defaults={"current_number": 0, "description": description},
            )
            if created:
                _ok(self, f"DocumentSequence '{prefix}' (year={seq_year or '—'})")
            else:
                _skip(self, f"DocumentSequence '{prefix}'")

    # ===================================================================
    # PHASE 2 — USERS
    # ===================================================================

    def _seed_users(self):
        _section(self, "Users & Roles")
        from accounts.models import UserProfile

        # One representative account per role.
        # All passwords default to admin1234! — enforce a change on
        # first login in production.
        users_data = [
            # (username, first_name, last_name, email, is_superuser, role)
            (
                "admin",
                "Administrateur",
                "",
                "admin@entreprise.local",
                True,
                "manager",
            ),
            (
                "manager",
                "Responsable",
                "Général",
                "manager@entreprise.local",
                False,
                "manager",
            ),
            (
                "stock",
                "Responsable",
                "Stock",
                "stock@entreprise.local",
                False,
                "stock_prod",
            ),
            (
                "comptable",
                "Comptable",
                "",
                "comptable@entreprise.local",
                False,
                "accountant",
            ),
            (
                "commercial",
                "Commercial",
                "",
                "commercial@entreprise.local",
                False,
                "sales",
            ),
            (
                "lecteur",
                "Consultation",
                "",
                "lecteur@entreprise.local",
                False,
                "viewer",
            ),
            (
                "qualite",
                "Responsable",
                "Qualité",
                "qualite@entreprise.local",
                False,
                "qa_manager",
            ),
            (
                "laboratoire",
                "Technicien",
                "Laboratoire",
                "laboratoire@entreprise.local",
                False,
                "qc_technician",
            ),
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
                # Signal auto-creates the profile with role='viewer'; correct it.
                profile = user.userprofile
                profile.role = role
                profile.save()
                _ok(self, f"User '{username}' — role: {role}")
            else:
                # Ensure profile role is correct even if user pre-existed.
                profile, _ = UserProfile.objects.get_or_create(
                    user=user, defaults={"role": role}
                )
                if profile.role != role:
                    profile.role = role
                    profile.save()
                    _ok(self, f"User '{username}' — role corrected to: {role}")
                else:
                    _skip(self, f"User '{username}'")

            self._users[username] = user

    # ===================================================================
    # PHASE 3 — UNITS OF MEASURE & RAW MATERIAL CATEGORIES
    # ===================================================================

    def _seed_units_and_categories(self):
        _section(self, "Units of Measure & Raw Material Categories")
        from catalog.models import UnitOfMeasure, RawMaterialCategory

        # ── Units of Measure ─────────────────────────────────────────────
        units = [
            # (code, name, symbol)
            # — Mass
            ("KG", "Kilogramme", "kg"),
            ("G", "Gramme", "g"),
            ("T", "Tonne", "t"),
            # — Volume
            ("L", "Litre", "L"),
            ("ML", "Millilitre", "mL"),
            # — Length / area
            ("M", "Mètre", "m"),
            ("M2", "Mètre carré", "m²"),
            # — Count / packaging
            ("PCE", "Pièce", "pce"),
            ("SAC", "Sac", "sac"),
            ("BTE", "Boîte", "bte"),
            ("ROL", "Rouleau", "rol"),
            ("PAL", "Palette", "pal"),
        ]

        for code, name, symbol in units:
            _, created = UnitOfMeasure.objects.get_or_create(
                code=code, defaults=dict(name=name, symbol=symbol)
            )
            if created:
                _ok(self, f"UnitOfMeasure: {code} ({symbol})")
            else:
                _skip(self, f"UnitOfMeasure '{code}'")

        # ── Raw Material Categories ──────────────────────────────────────
        rm_categories = [
            # (name, description)
            ("Résines et polymères", "Matières plastiques de base : PP, PEHD, PVC…"),
            (
                "Additifs et colorants",
                "Masterbatches, stabilisants, plastifiants, pigments",
            ),
            ("Lubrifiants industriels", "Huiles et graisses pour machines"),
            ("Emballages", "Matériaux d'emballage et de conditionnement"),
            ("Produits chimiques", "Produits chimiques industriels divers"),
            ("Consommables", "Consommables atelier et production"),
        ]

        for name, description in rm_categories:
            _, created = RawMaterialCategory.objects.get_or_create(
                name=name, defaults={"description": description}
            )
            if created:
                _ok(self, f"RawMaterialCategory: {name}")
            else:
                _skip(self, f"RawMaterialCategory '{name}'")

    # ===================================================================
    # PHASE 4 — EXPENSE CATEGORIES
    # ===================================================================

    def _seed_expense_categories(self):
        _section(self, "Expense Categories")
        from expenses.models import ExpenseCategory

        # Code, label, display order
        # These map to every standard operating expense bucket.
        categories = [
            ("SALAIRES", "Salaires et charges sociales", 1),
            ("LOYER", "Loyer et charges immobilières", 2),
            ("ENERGIE", "Énergie et utilities", 3),
            ("TRANSPORT", "Transport et logistique", 4),
            ("ENTRETIEN", "Entretien et maintenance", 5),
            ("FOURNITURES", "Fournitures de bureau", 6),
            ("COMM", "Frais commerciaux et marketing", 7),
            ("INFORMATIQUE", "Informatique et télécommunications", 8),
            ("ASSURANCES", "Assurances", 9),
            ("HONORAIRES", "Honoraires et prestations externes", 10),
            ("IMPOTS", "Impôts, taxes et contributions", 11),
            ("DIVERS", "Dépenses diverses", 12),
        ]

        for code, label, order in categories:
            _, created = ExpenseCategory.objects.get_or_create(
                code=code, defaults=dict(label=label, order=order)
            )
            if created:
                _ok(self, f"ExpenseCategory: {code} — {label}")
            else:
                _skip(self, f"ExpenseCategory '{code}'")
