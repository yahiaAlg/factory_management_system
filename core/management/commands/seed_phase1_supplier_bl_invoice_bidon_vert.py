"""
core/management/commands/seed_phase1_supplier_bl_invoice_bidon_vert.py

Phase 1 seed for scenario "Bidon PEHD 15L Vert" — Achat & Réception.
Creates and VALIDATES a full supplier cycle: BL Fournisseur -> QA/QC Gate A
(RM-001 PEHD only — sample drawn, tested, released) -> validated (with
SD-DNF attached, stock RM credited) -> Facture Fournisseur (linked, verified,
unpaid) -> Paiement Fournisseur (with SD-PAY-F attached -> invoice reaches
'paid').

Because a Gate A Sampling Plan is active only for RM-001 (see
seed_phase0_bidon_vert), the delivery note is automatically redirected to
"Pending QC Sampling" on submit (BR-QA-01) — RM-002/003/004 are unaffected
and would proceed exactly as before if they were the only lines present.

Pre-requisite: seed_phase0_bidon_vert has run (F-0001, RM-001..004, admin,
qualite, laboratoire, QA/QC master data).

Usage:
    python manage.py seed_phase0_bidon_vert
    python manage.py seed_phase1_supplier_bl_invoice_bidon_vert
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
    """Attach a placeholder PieceJointe of the given type, unless already present."""
    from core.models import PieceJointe

    ct = ContentType.objects.get_for_model(obj)
    exists = PieceJointe.objects.filter(
        content_type=ct, object_id=obj.pk, type_document=doc_type
    ).exists()
    if exists:
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
        "Phase 1 seed: BL Fournisseur (+ QA/QC Gate A sur RM-001) + Facture "
        "Fournisseur + Paiement (Bidon PEHD 15L Vert)."
    )

    def handle(self, *args, **options):
        from catalog.models import RawMaterial
        from suppliers.models import Supplier
        from supplier_ops.models import (
            SupplierDN,
            SupplierDNLine,
            SupplierInvoice,
            SupplierInvoiceLine,
            SupplierInvoiceDNLink,
            SupplierPayment,
        )
        from core.models import PieceJointe
        from core.utils import get_seed_site
        from quality.models import Sample, TestResult, QualitySpecification

        main_site = get_seed_site(self)

        try:
            admin = User.objects.get(username="admin")
        except User.DoesNotExist:
            raise CommandError(
                "User 'admin' introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        try:
            qa_manager = User.objects.get(username="qualite")
            qc_tech = User.objects.get(username="laboratoire")
        except User.DoesNotExist:
            raise CommandError(
                "Comptes 'qualite'/'laboratoire' introuvables — lancez d'abord "
                "'python manage.py minimal_populate_db --flush' puis "
                "seed_phase0_bidon_vert."
            )

        try:
            supplier = Supplier.objects.get(code="F-0001")
        except Supplier.DoesNotExist:
            raise CommandError(
                "Fournisseur F-0001 introuvable — lancez d'abord seed_phase0_bidon_vert."
            )

        rm_lines_spec = [
            # (designation, qty_received, agreed_price, qty_invoiced, unit_price_invoiced)
            ("Polyéthylène haute densité PEHD", Decimal("55.000"), Decimal("380.00")),
            ("Masterbatch Vert PEHD", Decimal("1.000"), Decimal("1100.00")),
            ("Stabilisant thermique UV", Decimal("0.500"), Decimal("1200.00")),
            ("Lubrifiant silicone industriel", Decimal("0.500"), Decimal("780.00")),
        ]
        try:
            rms = {
                d: RawMaterial.objects.get(designation=d) for d, _, _ in rm_lines_spec
            }
        except RawMaterial.DoesNotExist as exc:
            raise CommandError(
                f"Matière première manquante — lancez d'abord seed_phase0_bidon_vert. ({exc})"
            )

        kg = rms[rm_lines_spec[0][0]].unit_of_measure  # all 4 RM use KG

        with transaction.atomic():
            # ================================================================
            # BL Fournisseur
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ BL Fournisseur"))
            dn = SupplierDN.objects.filter(
                external_reference="BL-PLASTOCHIM-2026-047"
            ).first()
            if dn:
                _skip(self, dn.reference)
            else:
                dn = SupplierDN.objects.create(
                    site=main_site,
                    external_reference="BL-PLASTOCHIM-2026-047",
                    supplier=supplier,
                    delivery_date=datetime.date(2026, 5, 10),
                    remarks="Livraison matières lot Bidon Vert PF-001 — DB vierge init.",
                    created_by=admin,
                )
                for designation, qty, price in rm_lines_spec:
                    SupplierDNLine.objects.create(
                        supplier_dn=dn,
                        raw_material=rms[designation],
                        quantity_received=qty,
                        unit_of_measure=kg,
                        agreed_unit_price=price,
                    )
                dn.refresh_from_db()
                _ok(
                    self,
                    f"{dn.reference} créé — {dn.lines.count()} lignes — Total HT {dn.total_amount_ht} DZD",
                )

                dn.transition_to("pending", admin)
                _ok(
                    self,
                    f"{dn.reference} soumis — statut={dn.status}"
                    + (
                        " (redirigé vers contrôle QC Gate A — BR-QA-01, plan actif sur RM-001)"
                        if dn.status == "pending_qc_sampling"
                        else ""
                    ),
                )

                # ========================================================
                # QA/QC Gate A — un plan d'échantillonnage actif existe
                # uniquement pour RM-001 (PEHD) : la ligne correspondante
                # doit être échantillonnée et libérée avant validation.
                # Les 3 autres lignes n'ont pas de plan -> aucune action QC
                # requise pour elles (BR-QA-01).
                # ========================================================
                if dn.status == "pending_qc_sampling":
                    self.stdout.write(
                        self.style.MIGRATE_HEADING("\n▶ QA/QC — Gate A (RM-001 PEHD)")
                    )
                    pehd_line = dn.lines.get(raw_material=rms["Polyéthylène haute densité PEHD"])
                    spec = QualitySpecification.get_active_for(pehd_line.raw_material)
                    spec_line = spec.lines.filter(gate_a=True).first()

                    sample = Sample.objects.filter(supplier_dn_line=pehd_line).first()
                    if sample:
                        _skip(self, sample.reference)
                    else:
                        sample = Sample.objects.create(
                            control_point="A",
                            supplier_dn_line=pehd_line,
                            quality_specification=spec,
                            quantity_sampled=Decimal("0.100"),
                            unit=pehd_line.unit_of_measure,
                            sampled_by=qc_tech,
                            status="results_pending",
                        )
                        # Within tolerance: nominal 8.00 g/10min ± 15% -> [6.80, 9.20]
                        TestResult.objects.create(
                            sample=sample,
                            spec_line=spec_line,
                            recorded_value="7.60",
                            recorded_numeric=Decimal("7.60"),
                            instrument_method="Plastomètre à extrusion — ASTM D1238",
                            recorded_by=qc_tech,
                            outcome=spec_line.evaluate(Decimal("7.60")),
                        )
                        outcome = sample.compute_outcome()
                        _ok(
                            self,
                            f"{sample.reference} — MFI relevé 7,60 g/10min — {outcome}",
                        )

                    dn.refresh_from_db()
                    dn.qc_release(qa_manager)
                    dn.refresh_from_db()
                    _ok(self, f"{dn.reference} — QC libéré — statut={dn.status}")

                _attach(
                    dn,
                    PieceJointe.TYPE_SD_DNF,
                    "BL-PLASTOCHIM-2026-047-signe.pdf",
                    admin,
                )
                dn.validate(admin)
                _ok(
                    self,
                    f"{dn.reference} validé — statut={dn.status} (stock RM mis à jour)",
                )

            # ================================================================
            # Facture Fournisseur
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Facture Fournisseur"))
            invoice = SupplierInvoice.objects.filter(
                supplier=supplier, external_reference="FACT-PLASTOCHIM-2026-047"
            ).first()
            if invoice:
                _skip(self, invoice.reference)
            else:
                invoice = SupplierInvoice.objects.create(
                    external_reference="FACT-PLASTOCHIM-2026-047",
                    supplier=supplier,
                    invoice_date=datetime.date(2026, 5, 10),
                    due_date=datetime.date(2026, 6, 9),
                    payment_method="virement",
                    created_by=admin,
                )
                for designation, qty, price in rm_lines_spec:
                    rm = rms[designation]
                    SupplierInvoiceLine.objects.create(
                        supplier_invoice=invoice,
                        raw_material=rm,
                        designation=rm.designation,
                        quantity_invoiced=qty,
                        unit_price_invoiced=price,
                    )
                invoice.refresh_from_db()
                invoice.save()  # forces full _recompute_totals() (total_net / balance_due)
                _ok(
                    self,
                    f"{invoice.reference} — HT {invoice.total_ht} / TVA {invoice.vat_amount} "
                    f"/ TTC {invoice.total_ttc} / Net à payer {invoice.total_net} DZD",
                )

                SupplierInvoiceDNLink.objects.get_or_create(
                    supplier_invoice=invoice, supplier_dn=dn
                )
                dn.linked_invoice = invoice
                dn.save()

                invoice.transition_to("verified", admin)
                invoice.transition_to("unpaid", admin)
                _ok(self, f"{invoice.reference} — statut={invoice.status}")

            # ================================================================
            # Paiement Fournisseur
            # ================================================================
            self.stdout.write(self.style.MIGRATE_HEADING("\n▶ Paiement Fournisseur"))
            payment = SupplierPayment.objects.filter(
                supplier_invoice=invoice, bank_reference="VIR-BDL-2026-0515-001"
            ).first()
            if payment:
                _skip(self, payment.reference)
            else:
                _attach(
                    invoice,
                    PieceJointe.TYPE_SD_PAY_F,
                    "VIR-BDL-2026-0515-001.pdf",
                    admin,
                )
                payment = SupplierPayment.objects.create(
                    supplier_invoice=invoice,
                    supplier=supplier,
                    payment_date=datetime.date(2026, 5, 15),
                    amount=invoice.total_net.quantize(Decimal("0.01")),
                    payment_method="transfer",
                    bank_reference="VIR-BDL-2026-0515-001",
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
                "\n✅  seed_phase1_supplier_bl_invoice_bidon_vert completed.\n"
            )
        )
        self.stdout.write(
            "  QA/QC Gate A : RM-001 (PEHD) échantillonné, conforme, QC libéré — "
            "RM-002/003/004 sans contrôle (aucun plan actif, BR-QA-01).\n"
            "  Prochaine étape : Phase 2 — Formulation (Production → Formulations → Nouvelle).\n"
        )
