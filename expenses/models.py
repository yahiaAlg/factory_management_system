from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

class Expense(models.Model):
    """Operational expenses management"""
    
    CATEGORY_CHOICES = [
        ('salaries', 'Salaires et charges sociales'),
        ('maintenance', 'Maintenance et réparations'),
        ('energy', 'Énergie et utilités'),
        ('transport', 'Transport et logistique'),
        ('rent', 'Loyers et charges locatives'),
        ('supplies', 'Fournitures et consommables'),
        ('taxes', 'Taxes et impôts'),
        ('insurance', 'Assurances'),
        ('professional', 'Services professionnels'),
        ('marketing', 'Marketing et communication'),
        ('training', 'Formation'),
        ('other', 'Autres charges'),
    ]
    
    STATUS_CHOICES = [
        ('recorded', 'Enregistrée'),
        ('validated', 'Validée'),
        ('paid', 'Payée'),
        ('rejected', 'Rejetée'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Espèces'),
        ('transfer', 'Virement'),
        ('cheque', 'Chèque'),
        ('card', 'Carte bancaire'),
        ('direct_debit', 'Prélèvement'),
    ]
    
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence dépense")
    expense_date = models.DateField(verbose_name="Date de la dépense")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="Catégorie")
    description = models.TextField(verbose_name="Description")
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant"
    )
    
    # Payment information
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        verbose_name="Mode de paiement"
    )
    payment_date = models.DateField(null=True, blank=True, verbose_name="Date de paiement")
    beneficiary = models.CharField(max_length=200, verbose_name="Bénéficiaire")
    
    # Status and approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='recorded', verbose_name="Statut")
    validated_by = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='validated_expenses',
        verbose_name="Validé par"
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validé le")
    rejection_reason = models.TextField(blank=True, verbose_name="Motif de rejet")
    
    # Link to supplier invoice if applicable
    linked_supplier_invoice = models.ForeignKey(
        'supplier_ops.SupplierInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Facture fournisseur liée"
    )
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ['-expense_date', '-reference']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['category', 'expense_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.reference} - {self.description[:50]}"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate reference: DEP-YYYY-NNNN
            from core.models import DocumentSequence
            year = self.expense_date.year if self.expense_date else timezone.now().year
            self.reference = DocumentSequence.get_next_reference('DEP', year)
        
        super().save(*args, **kwargs)
    
    def validate(self, user):
        """Validate the expense"""
        if self.status != 'recorded':
            raise ValueError("Seules les dépenses enregistrées peuvent être validées")
        
        # Check delegation threshold
        from core.models import SystemParameter
        delegation_threshold = SystemParameter.get_decimal_value(
            'expense_delegation_threshold', 
            Decimal('50000.00')
        )
        
        if self.amount > delegation_threshold and user.userprofile.role != 'manager':
            raise ValueError("Montant supérieur au seuil de délégation - validation Manager requise")
        
        self.status = 'validated'
        self.validated_by = user
        self.validated_at = timezone.now()
        self.save()
    
    def reject(self, user, reason):
        """Reject the expense"""
        if self.status != 'recorded':
            raise ValueError("Seules les dépenses enregistrées peuvent être rejetées")
        
        self.status = 'rejected'
        self.validated_by = user
        self.validated_at = timezone.now()
        self.rejection_reason = reason
        self.save()
    
    def mark_as_paid(self, user, payment_date, payment_method):
        """Mark expense as paid"""
        if self.status != 'validated':
            raise ValueError("Seules les dépenses validées peuvent être marquées comme payées")
        
        self.status = 'paid'
        self.payment_date = payment_date
        self.payment_method = payment_method
        self.save()
    
    def requires_manager_approval(self):
        """Check if expense requires manager approval"""
        from core.models import SystemParameter
        delegation_threshold = SystemParameter.get_decimal_value(
            'expense_delegation_threshold', 
            Decimal('50000.00')
        )
        return self.amount > delegation_threshold
    
    def is_overdue_for_validation(self, days=7):
        """Check if expense is overdue for validation"""
        if self.status == 'recorded':
            cutoff_date = timezone.now().date() - timezone.timedelta(days=days)
            return self.expense_date <= cutoff_date
        return False

class SupportingDocument(models.Model):
    """Supporting documents for various business events"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('SD-DNF', 'BL Fournisseur signé'),
        ('SD-INV-F', 'Facture fournisseur originale'),
        ('SD-PAY-F', 'Justificatif paiement fournisseur'),
        ('SD-DNC', 'BL Client signé'),
        ('SD-INV-C', 'Facture client émise'),
        ('SD-PAY-C', 'Justificatif encaissement client'),
        ('SD-EXP', 'Justificatif dépense'),
        ('SD-CORR', 'Document de correction'),
    ]
    
    doc_type = models.CharField(max_length=10, choices=DOCUMENT_TYPE_CHOICES, verbose_name="Type de document")
    
    # Generic foreign key fields
    entity_type = models.CharField(max_length=50, verbose_name="Type d'entité")
    entity_id = models.PositiveIntegerField(verbose_name="ID entité")
    
    description = models.TextField(verbose_name="Description")
    file_reference = models.CharField(max_length=200, blank=True, verbose_name="Référence fichier")
    
    # Metadata
    registered_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Enregistré par")
    registered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Document justificatif"
        verbose_name_plural = "Documents justificatifs"
        ordering = ['-registered_at']
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['doc_type']),
        ]
    
    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.description[:50]}"
    
    @classmethod
    def create_for_entity(cls, doc_type, entity, description, user, file_reference=''):
        """Create supporting document for any entity"""
        return cls.objects.create(
            doc_type=doc_type,
            entity_type=entity.__class__.__name__.lower(),
            entity_id=entity.id,
            description=description,
            file_reference=file_reference,
            registered_by=user
        )
    
    def get_entity(self):
        """Get the linked entity object"""
        # This would need to be implemented with proper model mapping
        # For now, return a simple representation
        return f"{self.entity_type}#{self.entity_id}"

class ExpenseCategory(models.Model):
    """Expense categories for better organization and reporting"""
    
    name = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    # Budget tracking
    monthly_budget = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Budget mensuel"
    )
    annual_budget = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Budget annuel"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépenses"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def get_monthly_spent(self, year, month):
        """Get total spent for a specific month"""
        return Expense.objects.filter(
            category=self.code,
            expense_date__year=year,
            expense_date__month=month,
            status__in=['validated', 'paid']
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def get_annual_spent(self, year):
        """Get total spent for a specific year"""
        return Expense.objects.filter(
            category=self.code,
            expense_date__year=year,
            status__in=['validated', 'paid']
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def get_budget_utilization_rate(self, year, month=None):
        """Get budget utilization rate"""
        if month:
            spent = self.get_monthly_spent(year, month)
            budget = self.monthly_budget
        else:
            spent = self.get_annual_spent(year)
            budget = self.annual_budget
        
        if budget and budget > 0:
            return (spent / budget) * 100
        return Decimal('0.00')