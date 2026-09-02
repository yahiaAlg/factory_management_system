# supplier_ops/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation
from django.utils import timezone
from decimal import Decimal

from core.models import PieceJointe


class SupplierDN(models.Model):
    """Supplier Delivery Note (Bon de Livraison Fournisseur).

    SPEC S2 / S8:
      - reference: auto-generated BL-F-YYYY-NNNN, immutable after creation.
      - Stock movements created ONLY on validation, not on creation/save.
      - validate() must not call post_save.send() manually — signals handle it.
    """

    STATUS_CHOICES = [
        ("draft", "Brouillon"),
        ("pending", "En attente de validation"),
        # --- QA/QC Gate A (functional spec §4.2) ---
        ("pending_qc_sampling", "En attente d'échantillonnage QC"),
        ("qc_passed", "QC validé"),
        ("rejected_returned", "Rejeté — Retourné au fournisseur"),
        # ---
        ("validated", "Validé"),
        ("in_dispute", "En litige"),
        ("cancelled", "Annulé"),
    ]

    # Valid transitions per spec S6, amended by QA/QC Gate A (§4.2, §10.1)
    VALID_TRANSITIONS = {
        "draft": ["pending", "cancelled"],
        "pending": ["validated", "pending_qc_sampling", "in_dispute", "cancelled"],
        "pending_qc_sampling": ["qc_passed", "rejected_returned", "in_dispute"],
        "qc_passed": ["validated", "in_dispute"],
        "rejected_returned": ["in_dispute"],
        "validated": ["in_dispute"],
        "in_dispute": ["pending"],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence BL", editable=False
    )
    site = models.ForeignKey(
        "core.ProductionSite",
        on_delete=models.PROTECT,
        related_name="supplier_dns",
        verbose_name="Site de réception",
        help_text="Site dont le stock de matières premières est crédité à la validation (fonc. spec §25.2.3).",
    )
    external_reference = models.CharField(
        max_length=100, verbose_name="Référence fournisseur"
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    delivery_date = models.DateField(verbose_name="Date de livraison")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Statut"
    )

    # SPEC S3: total_amount_ht is a computed property — not stored as a user-editable field.
    # We keep it as a cached DB field updated only in save(), never from POST data.
    total_amount_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant total HT",
        editable=False,
    )

    remarks = models.TextField(blank=True, verbose_name="Observations")

    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_supplier_dns",
        verbose_name="Validé par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")

    linked_invoice = models.ForeignKey(
        "SupplierInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Facture liée",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic attachments (PieceJointe, core.models) — mirrors the avicole
    # project so a DN can carry several proofs (SD-DNF signed copy, etc.).
    pieces_jointes = GenericRelation(PieceJointe, related_query_name="supplier_dn")

    class Meta:
        verbose_name = "BL Fournisseur"
        verbose_name_plural = "BL Fournisseurs"
        ordering = ["-delivery_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "delivery_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code}"

    # ------------------------------------------------------------------
    # Reference generation & save
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.delivery_date.year
                    if self.delivery_date
                    else timezone.now().year
                )
                site_code = self.site.code if self.site_id else None
                self.reference = DocumentSequence.get_next_reference(
                    "BL-F", year, site_code=site_code
                )
        else:
            # Block reference mutation
            orig = SupplierDN.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError("La référence d'un BL fournisseur est immuable.")

        # Recompute total from lines (never from form input)
        if self.pk:
            self.total_amount_ht = sum(line.line_amount for line in self.lines.all())

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Status transition
    # ------------------------------------------------------------------
    def transition_to(self, new_status, user):
        """Enforce valid status transitions (spec S6).

        QA/QC Gate A (functional spec §4.2, BR-QA-01): when a DN is submitted
        ("pending"), if any line's raw material has an active Gate A Sampling
        Plan, the DN is redirected to "pending_qc_sampling" instead — a no-op
        when no plan applies, per BR-QA-01.
        """
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Transition invalide : {self.status} → {new_status}."
            )
        self.status = new_status
        if new_status == "pending" and self.requires_gate_a_qc():
            self.status = "pending_qc_sampling"
        if new_status == "validated":
            self.validated_by = user
            self.validated_at = timezone.now()
        self.save()

    # ------------------------------------------------------------------
    # QA/QC Gate A helpers (functional spec §4)
    # ------------------------------------------------------------------
    def gate_a_lines(self):
        """Lines whose raw material has an active Gate A Sampling Plan."""
        from quality.models import SamplingPlan

        return [
            line for line in self.lines.select_related("raw_material")
            if SamplingPlan.get_active_for("A", raw_material=line.raw_material)
        ]

    def requires_gate_a_qc(self):
        return len(self.gate_a_lines()) > 0

    def gate_a_clear(self):
        """BR-QA-02: True once every Gate-A-flagged line has a conforming or
        conditionally-accepted sample outcome (rejected lines are simply
        excluded from stock crediting, not a blocker for the rest of the DN)."""
        for line in self.gate_a_lines():
            samples = line.quality_samples.all()
            if not samples.exists():
                return False
            latest = samples.order_by("-sampled_at").first()
            if latest.status not in ("conforming", "conditionally_accepted", "non_conforming"):
                return False  # still pending results
        return True

    def qc_release(self, user):
        """pending_qc_sampling -> qc_passed once all flagged lines have a result
        (conforming lines proceed; non-conforming lines are marked rejected and
        excluded from stock crediting by the signal — §4.2 Step 5c)."""
        if self.status != "pending_qc_sampling":
            raise ValidationError("Ce BL n'est pas en attente d'échantillonnage QC.")
        if not self.gate_a_clear():
            raise ValidationError(
                "Tous les résultats de laboratoire ne sont pas encore enregistrés."
            )
        if all(
            line.quality_samples.order_by("-sampled_at").first().status == "non_conforming"
            for line in self.gate_a_lines()
        ) and len(self.gate_a_lines()) == len(list(self.lines.all())):
            # every single line failed -> whole DN rejected (§4.2 Step 5c)
            self.transition_to("rejected_returned", user)
            return
        self.transition_to("qc_passed", user)

    # ------------------------------------------------------------------
    # Business action: validate
    # ------------------------------------------------------------------
    def validate(self, user):
        """
        Validate the delivery note.

        SPEC BR-RM-05: stock movements are created by the
        supplier_dn_post_save signal in stock/signals.py, NOT here.
        Supporting document (SD-DNF) gate is enforced here.
        """
        if self.status not in ("pending", "qc_passed"):
            raise ValidationError(
                "Seuls les BL en attente de validation (ou validés QC) peuvent être validés."
            )
        # QA/QC Gate A hard block (BR-QA-01/02, functional spec §4.3): a DN with
        # unresolved Gate-A sampling cannot be validated — no-op if no plan applies.
        if self.status == "pending" and self.requires_gate_a_qc():
            raise ValidationError(
                "Ce BL contient des lignes en attente de contrôle qualité (Gate A) "
                "et ne peut pas être validé avant réception des résultats."
            )

        # SPEC PieceJointe gate: SD-DNF must be attached
        if not self.pieces_jointes.filter(type_document=PieceJointe.TYPE_SD_DNF).exists():
            raise ValidationError(
                "Le BL fournisseur ne peut pas être validé sans justificatif signé (SD-DNF) attaché."
            )

        self.transition_to("validated", user)
        # Signal supplier_ops.signals.supplier_dn_post_save will handle stock movements.

    def can_be_linked_to_invoice(self):
        return self.status == "validated" and not self.linked_invoice

    def get_next_transitions(self):
        """
        Returns a list of (value, label, bx_icon, btn_css_class) tuples
        representing the valid next states from the current status.
        Used by the non-admin guided flow in the detail template.
        """
        _meta = {
            "pending": ("En attente de validation", "bx-time", "btn-secondary-app"),
            "pending_qc_sampling": ("En attente QC", "bx-test-tube", "btn-secondary-app"),
            "qc_passed": ("QC validé", "bx-check-shield", "btn-primary-app"),
            "rejected_returned": ("Rejeté — retour fournisseur", "bx-block", "btn-danger-app"),
            "validated": ("Valider", "bx-check-circle", "btn-primary-app"),
            "in_dispute": ("Mettre en litige", "bx-error-circle", "btn-secondary-app"),
            "cancelled": ("Annuler", "bx-x-circle", "btn-secondary-app"),
        }
        result = []
        for val in self.VALID_TRANSITIONS.get(self.status, []):
            label, icon, cls = _meta.get(
                val, (val, "bx-right-arrow-alt", "btn-secondary-app")
            )
            result.append((val, label, icon, cls))
        return result


class SupplierDNLine(models.Model):
    """Line item in a Supplier Delivery Note.

    SPEC S3: line_amount is a @property (qty × price), never stored
    as a user-editable field.
    """

    supplier_dn = models.ForeignKey(
        SupplierDN, on_delete=models.CASCADE, related_name="lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    quantity_received = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité reçue",
    )
    unit_of_measure = models.ForeignKey(
        "catalog.UnitOfMeasure", on_delete=models.PROTECT, verbose_name="Unité"
    )
    agreed_unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix unitaire convenu",
    )

    class Meta:
        verbose_name = "Ligne BL Fournisseur"
        verbose_name_plural = "Lignes BL Fournisseur"
        unique_together = ["supplier_dn", "raw_material"]

    def __str__(self):
        return f"{self.supplier_dn.reference} - {self.raw_material.designation}"

    @property
    def line_amount(self):
        """SPEC S3: computed property — never stored, never from POST data."""
        return self.quantity_received * self.agreed_unit_price

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Refresh DN total cache
        if self.supplier_dn_id:
            SupplierDN.objects.filter(pk=self.supplier_dn_id).update(
                total_amount_ht=sum(l.line_amount for l in self.supplier_dn.lines.all())
            )


class SupplierInvoice(models.Model):
    """Supplier Invoice (Facture Fournisseur).

    SPEC S2:
      - reference: FF-YYYY-NNNN, immutable.
      - balance_due: computed by signal after SupplierPayment save (S7).
      - No payment if status == 'in_dispute' (BR-INV-04 — enforced in
        SupplierPayment.clean() below AND in views).
      - (supplier, external_reference) must be unique (BR-INV-08).
    """

    STATUS_CHOICES = [
        ("entered", "Saisie"),
        ("verified", "Vérifiée"),
        ("in_dispute", "En litige"),
        ("unpaid", "Impayée"),
        ("partially_paid", "Partiellement payée"),
        ("paid", "Payée"),
        ("cancelled", "Annulée"),
    ]

    VALID_TRANSITIONS = {
        "entered": ["verified", "in_dispute", "cancelled"],
        "verified": ["unpaid", "in_dispute"],
        "unpaid": ["partially_paid", "paid", "in_dispute"],
        "partially_paid": ["paid", "in_dispute"],
        "in_dispute": ["unpaid"],  # Manager only — enforced in view
        "paid": [],
        "cancelled": [],
    }

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence facture", editable=False
    )
    external_reference = models.CharField(
        max_length=100, verbose_name="Référence fournisseur"
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    invoice_date = models.DateField(verbose_name="Date facture")
    due_date = models.DateField(verbose_name="Date d'échéance")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="entered", verbose_name="Statut"
    )

    PAYMENT_METHOD_CHOICES = [
        ("virement", "Virement bancaire"),
        ("cheque", "Chèque"),
        ("espece", "Espèces"),
        ("ccp", "CCP"),
    ]

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="virement",
        verbose_name="Mode de règlement",
    )

    total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total HT",
        editable=False,
    )
    vat_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant TVA",
        editable=False,
    )
    total_ttc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total TTC",
        editable=False,
    )
    # Timbre fiscal (droit de timbre) — applicable uniquement en espèces.
    # Tiers : ≤300 DA → 0 ; ]300, 30k] → 1% ; ]30k, 100k] → 1.5% ; >100k → 2%
    timbre_fiscal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Timbre fiscal",
        editable=False,
    )
    # total_net = total_ttc + timbre_fiscal — base for balance_due.
    total_net = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Net à payer",
        editable=False,
    )

    # SPEC S3: balance_due is signal-updated after SupplierPayment save — never form-editable.
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Solde dû",
        editable=False,
    )

    linked_dns = models.ManyToManyField(
        SupplierDN, through="SupplierInvoiceDNLink", verbose_name="BL liés"
    )

    # §23.5 — Opening Balance: flags an invoice created via
    # create_supplier_opening_balance() (utils.py) instead of from DNs.
    # No other function needs to change: it still participates in
    # dette_globale, aging, FIFO settlement, and the statement of account
    # exactly like a normal invoice — only _recompute_totals() is guarded
    # below so its manually-entered amount is never overwritten from lines.
    is_opening_balance = models.BooleanField(
        default=False, verbose_name="Solde d'ouverture (§23 planifié)"
    )
    # §23.5 — required explanation for an opening-balance invoice, stored
    # here for audit; also usable as free-text notes on any other invoice.
    notes = models.TextField(blank=True, verbose_name="Notes")

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="supplier_invoice")

    class Meta:
        verbose_name = "Facture Fournisseur"
        verbose_name_plural = "Factures Fournisseur"
        ordering = ["-invoice_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "invoice_date"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code}"

    # ------------------------------------------------------------------
    # BR-INV-08: duplicate (supplier, external_reference) check
    # ------------------------------------------------------------------
    def clean(self):
        qs = SupplierInvoice.objects.filter(
            supplier=self.supplier,
            external_reference=self.external_reference,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                "Une facture avec cette référence fournisseur existe déjà pour ce fournisseur."
            )

    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.reference:
                from core.models import DocumentSequence

                year = (
                    self.invoice_date.year if self.invoice_date else timezone.now().year
                )
                self.reference = DocumentSequence.get_next_reference("FF", year)
        else:
            orig = SupplierInvoice.objects.get(pk=self.pk)
            if orig.reference != self.reference:
                raise ValidationError(
                    "La référence d'une facture fournisseur est immuable."
                )

        # §23.5: an opening-balance invoice has no lines/DNs behind it — its
        # amounts are set once by create_supplier_opening_balance() and must
        # never be recomputed from an (empty) lines queryset on a later save
        # (e.g. transition_to() calling self.save()).
        if self.pk and not self.is_opening_balance:
            self._recompute_totals()

        super().save(*args, **kwargs)

    def _recompute_totals(self):
        """Recompute HT / TVA / TTC / timbre_fiscal / total_net from lines."""
        self.total_ht = sum(line.line_amount for line in self.lines.all())
        from core.models import CompanyInformation

        try:
            company = CompanyInformation.objects.first()
            vat_rate = company.vat_rate if company else Decimal("0.19")
        except Exception:
            vat_rate = Decimal("0.19")
        self.vat_amount = self.total_ht * vat_rate
        self.total_ttc = self.total_ht + self.vat_amount
        # Timbre fiscal (droit de timbre) — espèces only, tiered rate on TTC.
        if self.payment_method == "espece":
            ttc = self.total_ttc
            if ttc > Decimal("100000"):
                self.timbre_fiscal = (ttc * Decimal("0.02")).quantize(Decimal("0.01"))
            elif ttc > Decimal("30000"):
                self.timbre_fiscal = (ttc * Decimal("0.015")).quantize(Decimal("0.01"))
            elif ttc > Decimal("300"):
                self.timbre_fiscal = (ttc * Decimal("0.01")).quantize(Decimal("0.01"))
            else:
                self.timbre_fiscal = Decimal("0.00")
        else:
            self.timbre_fiscal = Decimal("0.00")
        self.total_net = self.total_ttc + self.timbre_fiscal
        total_paid = (
            sum(p.amount for p in self.payments.all()) if self.pk else Decimal("0.00")
        )
        self.balance_due = self.total_net - total_paid

    def has_sd_pay_f(self):
        """SPEC BR-AUD-04 hard gate: a paid Supplier Invoice must carry a
        SD-PAY-F supporting document."""
        return self.pieces_jointes.filter(type_document=PieceJointe.TYPE_SD_PAY_F).exists()

    def recompute_balance_due(self):
        """
        Called by supplier_ops.signals after SupplierPayment save (spec S7),
        and again whenever a SD-PAY-F is attached after the fact.

        SPEC BR-AUD-04 hard gate: an invoice may only reach "paid" once a
        SD-PAY-F proof is attached. This is enforced here *without* raising
        — if the balance reaches zero but no proof exists yet, the invoice
        is simply held at "partially_paid" instead of erroring out, so that
        recording a payment (SupplierPaymentForm has no file field) never
        fails. Attaching the SD-PAY-F afterwards (see
        supplier_invoice_add_document) re-runs this method and lets the
        status flip to "paid" at that point.
        """
        total_paid = sum(p.amount for p in self.payments.all())
        self.balance_due = self.total_net - total_paid
        if self.balance_due <= 0 and self.has_sd_pay_f():
            self.status = "paid"
        elif total_paid > 0 and self.status not in ("in_dispute", "cancelled"):
            self.status = "partially_paid"
        SupplierInvoice.objects.filter(pk=self.pk).update(
            balance_due=self.balance_due, status=self.status
        )

    def transition_to(self, new_status, user):
        """Enforce valid status transitions (spec S6)."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Transition invalide : {self.status} → {new_status}."
            )
        # SPEC BR-AUD-04 hard gate: manual "Marquer comme payée" also
        # requires SD-PAY-F. Raised here (not in a shared form) so it never
        # blocks SupplierPaymentForm — only this explicit status-change
        # action, which the view already wraps in try/except ValidationError.
        if new_status == "paid" and not self.has_sd_pay_f():
            raise ValidationError(
                "La facture ne peut pas être marquée payée sans justificatif "
                "de paiement (SD-PAY-F) attaché."
            )
        self.status = new_status
        self.save()

    def is_overdue(self):
        return self.due_date < timezone.now().date() and self.balance_due > 0

    def get_next_transitions(self):
        """
        Returns a list of (value, label, bx_icon, btn_css_class) tuples
        for the valid next states from the current status.
        Used by the non-admin guided flow in the detail template.
        """
        _meta = {
            "verified": (
                "Marquer comme vérifiée",
                "bx-check-double",
                "btn-primary-app",
            ),
            "in_dispute": ("Mettre en litige", "bx-error-circle", "btn-secondary-app"),
            "unpaid": ("Marquer comme impayée", "bx-time", "btn-secondary-app"),
            "partially_paid": (
                "Marquer partiellement payée",
                "bx-wallet-alt",
                "btn-secondary-app",
            ),
            "paid": ("Marquer comme payée", "bx-check-circle", "btn-primary-app"),
            "cancelled": ("Annuler la facture", "bx-x-circle", "btn-secondary-app"),
        }
        result = []
        for val in self.VALID_TRANSITIONS.get(self.status, []):
            label, icon, cls = _meta.get(
                val, (val, "bx-right-arrow-alt", "btn-secondary-app")
            )
            result.append((val, label, icon, cls))
        return result


class SupplierInvoiceLine(models.Model):
    """Line item in a Supplier Invoice."""

    supplier_invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name="lines"
    )
    raw_material = models.ForeignKey(
        "catalog.RawMaterial", on_delete=models.PROTECT, verbose_name="Matière première"
    )
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    quantity_invoiced = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name="Quantité facturée",
    )
    unit_price_invoiced = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Prix unitaire facturé",
    )

    class Meta:
        verbose_name = "Ligne Facture Fournisseur"
        verbose_name_plural = "Lignes Facture Fournisseur"
        unique_together = ["supplier_invoice", "raw_material"]

    @property
    def line_amount(self):
        """SPEC S3: computed property."""
        return self.quantity_invoiced * self.unit_price_invoiced

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.supplier_invoice_id:
            self.supplier_invoice._recompute_totals()
            SupplierInvoice.objects.filter(pk=self.supplier_invoice_id).update(
                total_ht=self.supplier_invoice.total_ht,
                vat_amount=self.supplier_invoice.vat_amount,
                total_ttc=self.supplier_invoice.total_ttc,
            )

    def __str__(self):
        return f"{self.supplier_invoice.reference} - {self.designation}"


class SupplierInvoiceDNLink(models.Model):
    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE)
    supplier_dn = models.ForeignKey(SupplierDN, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["supplier_invoice", "supplier_dn"]


class SupplierPayment(models.Model):
    """Payment made to a supplier.

    SPEC BR-INV-04: clean() blocks payment if invoice status == 'in_dispute'.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
        # §23.3.3 — synthetic method used exclusively by
        # utils.consume_supplier_advances_fifo() when an advance is drawn
        # down against a new invoice. Excluded from the statement of
        # account's crédit lines (§23.6) since the cash was already counted
        # in full on the day the underlying SupplierAdvance was recorded.
        ("advance", "Avance consommée (§23 planifié)"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence paiement", editable=False
    )
    supplier_invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Facture",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.PROTECT, verbose_name="Fournisseur"
    )
    payment_date = models.DateField(verbose_name="Date de paiement")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant",
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="Mode de paiement"
    )
    bank_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence bancaire"
    )

    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Enregistré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    pieces_jointes = GenericRelation(PieceJointe, related_query_name="supplier_payment")

    class Meta:
        verbose_name = "Paiement Fournisseur"
        verbose_name_plural = "Paiements Fournisseur"
        ordering = ["-payment_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["supplier", "payment_date"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code} - {self.amount}"

    # ------------------------------------------------------------------
    # BR-INV-04 (spec S4): hard gate — model layer
    # ------------------------------------------------------------------
    def clean(self):
        if self.supplier_invoice_id:
            inv = SupplierInvoice.objects.get(pk=self.supplier_invoice_id)
            if inv.status == "in_dispute":
                raise ValidationError(
                    "Impossible d'enregistrer un paiement pour une facture en litige (BR-INV-04). "
                    "Le litige doit être résolu par le Manager avant tout paiement."
                )

    def save(self, *args, **kwargs):
        self.full_clean()  # Ensure clean() runs on every save
        if not self.reference:
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("PAY-F", year)
        super().save(*args, **kwargs)
        # Signal supplier_ops.signals.supplier_payment_post_save will call
        # invoice.recompute_balance_due() — spec S7.


class SupplierAccountPayment(models.Model):
    """Supplier-level account settlement payment (FIFO invoice clearing).

    Instead of paying a specific invoice, the accountant records a payment
    against the supplier. The settle_fifo() method then clears invoices
    oldest-first (by due_date, then invoice_date) until the amount is exhausted,
    creating one SupplierPayment record per invoice touched.
    """

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence règlement", editable=False
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="account_payments",
        verbose_name="Fournisseur",
    )
    payment_date = models.DateField(verbose_name="Date de règlement")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant réglé",
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name="Mode de paiement"
    )
    bank_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence bancaire"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Enregistré par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    pieces_jointes = GenericRelation(
        PieceJointe, related_query_name="supplier_account_payment"
    )

    class Meta:
        verbose_name = "Règlement compte fournisseur"
        verbose_name_plural = "Règlements compte fournisseur"
        ordering = ["-payment_date", "-reference"]
        indexes = [
            models.Index(fields=["supplier", "payment_date"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.supplier.code} - {self.amount} DA"

    def save(self, *args, **kwargs):
        if not self.reference:
            from core.models import DocumentSequence

            year = self.payment_date.year if self.payment_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("RGL-F", year)
        super().save(*args, **kwargs)

    def settle_fifo(self):
        """Apply self.amount to the supplier's open invoices oldest-first.

        Fetches all invoices with balance_due > 0 and status not in_dispute/cancelled,
        ordered by due_date ASC then invoice_date ASC (FIFO).
        Creates one SupplierPayment record per invoice touched, reducing
        balance_due proportionally. Updates each invoice's status via
        recompute_balance_due().

        Returns a list of dicts describing what was applied:
          [{"invoice": <SupplierInvoice>, "applied": <Decimal>}, ...]
        """
        open_invoices = (
            SupplierInvoice.objects.filter(
                supplier=self.supplier,
                balance_due__gt=0,
            )
            .exclude(status__in=["in_dispute", "cancelled", "paid"])
            .order_by("due_date", "invoice_date")
            .select_for_update()
        )

        remaining = self.amount
        applied = []

        for invoice in open_invoices:
            if remaining <= 0:
                break

            to_apply = min(remaining, invoice.balance_due)

            payment = SupplierPayment(
                supplier_invoice=invoice,
                supplier=self.supplier,
                payment_date=self.payment_date,
                amount=to_apply,
                payment_method=self.payment_method,
                bank_reference=self.bank_reference,
                recorded_by=self.recorded_by,
            )
            # skip full_clean here — in_dispute guard already excluded above
            payment.save()

            invoice.refresh_from_db()
            invoice.recompute_balance_due()

            applied.append({"invoice": invoice, "applied": to_apply})
            remaining -= to_apply

        # §23.3.2a — Settlement surplus: once every open invoice in scope is
        # cleared, any leftover amount (including the entire settlement when
        # the supplier had no open invoices at all — e.g. a brand-new
        # supplier's first payment, made before any delivery has happened)
        # becomes a standing SupplierAdvance rather than being rejected.
        # Supersedes Rule 28 (§14.8): the caller no longer needs to block an
        # over-amount settlement before calling this method.
        if remaining > 0:
            SupplierAdvance.objects.create(
                supplier=self.supplier,
                settlement=self,
                origin=SupplierAdvance.ORIGIN_SETTLEMENT_SURPLUS,
                amount=remaining,
                remaining_amount=remaining,
                date=self.payment_date,
                recorded_by=self.recorded_by,
                notes=(
                    f"Surplus automatique du règlement {self.reference} du "
                    f"{self.payment_date} — {self.amount} DA au total."
                ),
            )

        return applied


class SupplierAdvance(models.Model):
    """Supplier Advance (§23.3) — a credit balance the factory holds against
    a specific supplier: money already paid out that has not yet been
    matched to any invoice.

    Created two ways (§23.3.2):
      (a) Settlement surplus — automatically, by SupplierAccountPayment.settle_fifo()
          above, when the settled amount exceeds the supplier's outstanding debt.
      (b) Direct entry — by the Accountant/Administrator, independent of any
          settlement (e.g. a cheque handed over as a deposit).

    Consumed automatically, oldest-first, by utils.consume_supplier_advances_fifo()
    the moment a new SupplierInvoice is created for the same supplier (§23.3.3).
    """

    ORIGIN_SETTLEMENT_SURPLUS = "settlement_surplus"
    ORIGIN_DIRECT_ENTRY = "direct_entry"
    ORIGIN_CHOICES = [
        (ORIGIN_SETTLEMENT_SURPLUS, "Surplus de règlement"),
        (ORIGIN_DIRECT_ENTRY, "Saisie directe"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("bill", "Effet de commerce"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence avance", editable=False
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="advances",
        verbose_name="Fournisseur",
    )
    settlement = models.OneToOneField(
        SupplierAccountPayment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="advance",
        verbose_name="Règlement source",
        help_text="Renseigné uniquement quand origin = Surplus de règlement (§23.3.2a).",
    )
    origin = models.CharField(
        max_length=20,
        choices=ORIGIN_CHOICES,
        default=ORIGIN_DIRECT_ENTRY,
        verbose_name="Origine",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant (DA)",
    )
    remaining_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Montant restant (DA)",
    )
    date = models.DateField(verbose_name="Date")
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="cash",
        verbose_name="Mode de paiement",
        help_text="Utilisé seulement pour une saisie directe (origin = Saisie directe).",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Enregistré par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    pieces_jointes = GenericRelation(
        PieceJointe, related_query_name="supplier_advance"
    )

    class Meta:
        verbose_name = "Avance Fournisseur (§23 planifié)"
        verbose_name_plural = "Avances Fournisseur (§23 planifié)"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["supplier", "date"]),
            models.Index(fields=["remaining_amount"]),
        ]

    def __str__(self):
        status = "utilisée" if self.remaining_amount <= 0 else "disponible"
        return f"Avance {self.supplier.code} — {self.amount} DA [{status}]"

    def save(self, *args, **kwargs):
        if self.pk is None and not self.reference:
            from core.models import DocumentSequence

            year = self.date.year if self.date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("AV-F", year)
        if self.pk is None and (self.remaining_amount is None or self.remaining_amount == 0):
            self.remaining_amount = self.amount
        super().save(*args, **kwargs)

    @property
    def is_fully_used(self):
        return self.remaining_amount <= 0


class SupplierAdvanceAllocation(models.Model):
    """Immutable line: portion of a SupplierAdvance consumed by one
    SupplierInvoice (§23.3.3). Created exclusively by
    utils.consume_supplier_advances_fifo(); never edited by users — mirrors
    the SupplierPayment audit trail created by settle_fifo()."""

    advance = models.ForeignKey(
        SupplierAdvance, on_delete=models.PROTECT, related_name="allocations"
    )
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.PROTECT, related_name="advance_allocations"
    )
    amount_allocated = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Montant alloué (DA)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Allocation d'avance (§23 planifié)"
        verbose_name_plural = "Allocations d'avance (§23 planifié)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.advance.reference} → {self.invoice.reference} : {self.amount_allocated} DA"
