"""
core/management/commands/seed_phase5_client_bl_invoice_bidon_vert.py

Phase 5 seed for scenario "Bidon PEHD 15L Vert" — Vente & Livraison Client.
Creates and VALIDATES a full client cycle: BL Client (validated, 3% remise)
-> Facture Client (linked) -> Encaissement Client (virement, solde = 0).

Pre-requisite: seed_phase0_bidon_vert has run (C-0001, PF-001, admin).

Stock note: BR-CDN-02 requires PF-001 stock >= 50 pce to validate the BL.
In the full scenario this stock comes from Phase 3 (Ordre de Production).
If this command is run WITHOUT Phases 2-4 having produced that stock, it
tops up PF-001 to 97 pce via a StockAdjustment ("correction") so the
client flow can be exercised standalone — clearly logged below, and
skipped entirely if real production stock already covers the sale.

Usage:
    python manage.py seed_phase0_bidon_vert
    [python manage.py seed_phase1_supplier_bl_invoice_bidon_vert]
    python manage.py seed_phase5_client_bl_invoice_bidon_vert
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def _ok(self, msg):
    self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))


def _skip(self, msg):
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg} — already exists, skipped"))


def _warn(self, msg):
    self.stdout.write(self.style.WARNING(f"  ⚠ {msg}"))


class Command(BaseCommand):
    help = (
        "Phase 5 seed: BL Client + Facture Client + Encaissement (Bidon PEHD 15L Vert)."
    )

    SALE_QTY = Decimal("50.000")
    STOCK_TOPUP_TARGET = Decimal(
        "97.000"
    )  # matches post-production/adjustment state in doc

    def handle(self, *args, **options):
        from catalog.models import FinishedProduct
        from clients.models import Client
        from stock.models import (
            FinishedProductStockBalance,
            StockAdjustment,
            StockAdjustmentLine,
        )
        from sales.models import (
            ClientDN,
            ClientDNLine,
            ClientInvoice,
            ClientInvoiceDNLink,
            ClientPayment,
        )
        from core.utils import get_seed_site

        main_site = get_seed_site(self)

        try:
            admin = User.objects.get(username="admin")
        except User.DoesNotExist:
            raise CommandError(
                "User 'admin' introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        try:
            client = Client.objects.get(code="C-0001")
        except Client.DoesNotExist:
            raise CommandError(
                "Client C-0001 introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        try:
            pf = FinishedProduct.objects.get(designation="Bidon PEHD 15L Vert")
        except FinishedProduct.DoesNotExist:
            raise CommandError(
                "Produit fini PF-001 introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        with transaction.atomic():
            # ================================================================
            # Stock top-up guard (only if Phases 2-4 haven't run)
            # ================================================================
            balance = FinishedProductStockBalance.objects.filter(
                site=main_site, finished_product=pf
            ).first()
            current_qty = balance.quantity if balance else Decimal("0.000")
            if current_qty < self.SALE_QTY:
                _warn(
                    self,
                    f"Stock PF-001 insuffisant ({current_qty} pce) — injection via "
                    f"StockAdjustment pour atteindre {self.STOCK_TOPUP_TARGET} pce "
                    "(substitut du cycle Production, Phases 2-4, non exécuté).",
                )
                adj = StockAdjustment.objects.create(
                    site=main_site,
                    adjustment_type="correction",
                    adjustment_date=datetime.date(2026, 5, 13),
                    reason=(
                        "Injection de stock seed (remplace Phases 2-4 Production) — "
                        "amène PF-001 à l'état post-production/ajustement du scénario."
                    ),
                    created_by=admin,
                )
                StockAdjustmentLine.objects.create(
                    stock_adjustment=adj,
                    finished_product=pf,
                    quantity_before=current_qty,
                    quantity_after=self.STOCK_TOPUP_TARGET,
                    remarks="Seed — stock de départ pour scénario Vente Phase 5.",
                )
                adj.approve(admin)
                _ok(
                    self,
                    f"{adj.reference} approuvé — PF-001 stock = {self.STOCK_TOPUP_TARGET} pce",
                )
            else:
                _ok(
                    self,
                    f"Stock PF-001 déjà suffisant ({current_qty} pce) — pas d'injection nécessaire",
                )

            # ================================================================
            # BL Client
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ BL Client"))
            dn = ClientDN.objects.filter(
                client=client, delivery_date=datetime.date(2026, 5, 14)
            ).first()
            if dn:
                _skip(self, dn.reference)
            else:
                dn = ClientDN.objects.create(
                    site=main_site,
                    client=client,
                    delivery_date=datetime.date(2026, 5, 14),
                    discount_pct=Decimal("3.00"),
                    remarks="Livraison 50 bidons verts — commande ref CMD-C0001-0514",
                    created_by=admin,
                )
                ClientDNLine.objects.create(
                    client_dn=dn,
                    finished_product=pf,
                    quantity_delivered=self.SALE_QTY,
                    unit_of_measure=pf.sales_unit,
                    selling_unit_price_ht=Decimal("1795.00"),
                )
                dn.refresh_from_db()
                _ok(
                    self,
                    f"{dn.reference} créé — Total HT (après remise) {dn.total_ht} DZD",
                )

                dn.validate(admin)
                _ok(
                    self,
                    f"{dn.reference} validé — statut={dn.status} (stock PF-001 -{self.SALE_QTY} pce)",
                )

            # ================================================================
            # Facture Client
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Facture Client"))
            invoice = ClientInvoice.objects.filter(
                client=client, invoice_date=datetime.date(2026, 5, 14)
            ).first()
            if invoice:
                _skip(self, invoice.reference)
            else:
                invoice = ClientInvoice.objects.create(
                    client=client,
                    invoice_date=datetime.date(2026, 5, 14),
                    discount_pct=Decimal(
                        "0.00"
                    ),  # remise déjà appliquée au niveau du BL
                    payment_method="virement",
                    created_by=admin,
                )
                ClientInvoiceDNLink.objects.get_or_create(
                    client_invoice=invoice, client_dn=dn
                )
                dn.linked_invoice = invoice
                dn.save()

                invoice.refresh_from_db()
                invoice.save()  # forces _recompute_totals() from linked DN(s)
                _ok(
                    self,
                    f"{invoice.reference} — HT {invoice.total_ht} / TVA {invoice.vat_amount} "
                    f"/ TTC {invoice.total_ttc} / Net à payer {invoice.total_net} DZD",
                )

            # ================================================================
            # Encaissement Client
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Encaissement Client"))
            payment = ClientPayment.objects.filter(
                client_invoice=invoice, bank_reference="VIR-BDL-C0001-20052026"
            ).first()
            if payment:
                _skip(self, payment.reference)
            else:
                payment = ClientPayment.objects.create(
                    client_invoice=invoice,
                    client=client,
                    payment_date=datetime.date(2026, 5, 20),
                    amount=invoice.total_net.quantize(Decimal("0.01")),
                    payment_method="transfer",
                    bank_reference="VIR-BDL-C0001-20052026",
                    recorded_by=admin,
                )
                invoice.refresh_from_db()
                invoice.recompute_balance_due()
                invoice.refresh_from_db()
                _ok(
                    self,
                    f"{payment.reference} — {payment.amount} DZD — Facture statut={invoice.status} "
                    f"(solde dû {invoice.balance_due} DZD)",
                )

        self.stdout.write(
            self.style.SUCCESS(
                "\n✅  seed_phase5_client_bl_invoice_bidon_vert completed.\n"
            )
        )
