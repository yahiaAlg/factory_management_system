# expenses/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class ExpenseCategory(models.Model):
    """Dynamic expense categories — managed via admin or seed command."""

    code = models.CharField(max_length=50, unique=True, verbose_name="Code")
    label = models.CharField(max_length=100, verbose_name="Libellé")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")

    class Meta:
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépenses"
        ordering = ["order", "label"]

    def __str__(self):
        return self.label


class Expense(models.Model):
    """Operational expenses management.

    SPEC BR-EXP-01: if amount > delegation_threshold AND user is not Manager,
    validate() must NOT raise an error — it leaves status as 'recorded'
    (pending Manager approval). It raises PermissionError only so the
    view can show a message; it does NOT change status to 'validated'.

    SPEC SupportingDocument gate: SD-EXP must be attached before validation
    when amount > threshold (spec S2 hard gate).

    Never deleted — deactivate/reject only.
    """

    STATUS_CHOICES = [
        ("recorded", "Enregistrée"),
        ("validated", "Validée"),
        ("paid", "Payée"),
        ("rejected", "Rejetée"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Espèces"),
        ("transfer", "Virement"),
        ("cheque", "Chèque"),
        ("card", "Carte bancaire"),
        ("direct_debit", "Prélèvement"),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence dépense", editable=False
    )
    expense_date = models.DateField(verbose_name="Date de la dépense")
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        verbose_name="Catégorie",
        limit_choices_to={"is_active": True},
    )
    description = models.TextField(verbose_name="Description")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Montant",
    )
    beneficiary = models.CharField(max_length=200, verbose_name="Bénéficiaire")

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        verbose_name="Mode de paiement",
    )
    payment_date = models.DateField(
        null=True, blank=True, verbose_name="Date de paiement"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="recorded", verbose_name="Statut"
    )

    validated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_expenses",
        verbose_name="Validé/Rejeté par",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    rejection_reason = models.TextField(blank=True, verbose_name="Motif de rejet")

    linked_supplier_invoice = models.ForeignKey(
        "supplier_ops.SupplierInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Facture fournisseur liée",
    )

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Créé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ["-expense_date", "-reference"]
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["category", "expense_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.reference} — {self.description[:50]}"

    def save(self, *args, **kwargs):
        if not self.reference:
            from core.models import DocumentSequence

            year = self.expense_date.year if self.expense_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference("DEP", year)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Business actions
    # ------------------------------------------------------------------
    def validate(self, user):
        """
        SPEC BR-EXP-01: if amount > threshold AND user is not Manager,
        status stays 'recorded' — raise PermissionError so the view
        can display a message WITHOUT changing status.

        SPEC SD gate: SD-EXP must be attached when above threshold.
        """
        if self.status != "recorded":
            raise ValidationError(
                "Seules les dépenses enregistrées peuvent être validées."
            )

        from core.models import SystemParameter

        threshold = SystemParameter.get_decimal_value(
            "expense_delegation_threshold", Decimal("50000.00")
        )

        if self.amount > threshold:
            if not hasattr(user, "userprofile") or user.userprofile.role != "manager":
                # SPEC BR-EXP-01: do NOT change status — leave as 'recorded' pending Manager approval
                raise PermissionError(
                    f"Montant ({self.amount} DZD) supérieur au seuil de délégation "
                    f"({threshold} DZD). Validation Manager requise. "
                    "La dépense reste en statut « Enregistrée »."
                )

            # Manager validating above-threshold: SD-EXP required
            if not SupportingDocument.objects.filter(
                doc_type="SD-EXP",
                entity_type="expense",
                entity_id=self.pk,
            ).exists():
                raise ValidationError(
                    "Un justificatif (SD-EXP) doit être attaché avant de valider "
                    "une dépense supérieure au seuil de délégation."
                )

        self.status = "validated"
        self.validated_by = user
        self.validated_at = timezone.now()
        self.save()

    def reject(self, user, reason):
        if self.status not in ("recorded", "validated"):
            raise ValidationError(
                "Seules les dépenses enregistrées ou validées peuvent être rejetées."
            )
        self.status = "rejected"
        self.validated_by = user
        self.validated_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def mark_as_paid(self, user, payment_date, payment_method):
        if self.status != "validated":
            raise ValidationError(
                "Seules les dépenses validées peuvent être marquées comme payées."
            )
        self.status = "paid"
        self.payment_date = payment_date
        self.payment_method = payment_method
        self.save()

    def requires_manager_approval(self):
        from core.models import SystemParameter

        threshold = SystemParameter.get_decimal_value(
            "expense_delegation_threshold", Decimal("50000.00")
        )
        return self.amount > threshold

    def is_overdue_for_validation(self, days=7):
        if self.status == "recorded":
            cutoff = timezone.now().date() - timezone.timedelta(days=days)
            return self.expense_date <= cutoff
        return False


class SupportingDocument(models.Model):
    """Supporting documents for various business events.

    SPEC S2 hard gates (enforced in respective model validate() methods):
      - SD-DNF must be attached before SupplierDN.validate()
      - SD-PAY-F must be attached before SupplierInvoice can be marked Paid
      - SD-EXP must be attached before Expense.validate() when above threshold
    """

    DOCUMENT_TYPE_CHOICES = [
        ("SD-DNF", "BL Fournisseur signé"),
        ("SD-INV-F", "Facture fournisseur originale"),
        ("SD-PAY-F", "Justificatif paiement fournisseur"),
        ("SD-DNC", "BL Client signé"),
        ("SD-INV-C", "Facture client émise"),
        ("SD-PAY-C", "Justificatif encaissement client"),
        ("SD-EXP", "Justificatif dépense"),
        ("SD-CORR", "Document de correction"),
    ]

    doc_type = models.CharField(
        max_length=10, choices=DOCUMENT_TYPE_CHOICES, verbose_name="Type de document"
    )
    entity_type = models.CharField(max_length=50, verbose_name="Type d'entité")
    entity_id = models.PositiveIntegerField(verbose_name="ID entité")
    description = models.TextField(verbose_name="Description")
    file_reference = models.CharField(
        max_length=200, blank=True, verbose_name="Référence fichier"
    )

    registered_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name="Enregistré par"
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Document justificatif"
        verbose_name_plural = "Documents justificatifs"
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["doc_type"]),
        ]

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.description[:50]}"

    @classmethod
    def create_for_entity(cls, doc_type, entity, description, user, file_reference=""):
        return cls.objects.create(
            doc_type=doc_type,
            entity_type=entity.__class__.__name__.lower(),
            entity_id=entity.pk,
            description=description,
            file_reference=file_reference,
            registered_by=user,
        )
