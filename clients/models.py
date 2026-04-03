from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class Client(models.Model):
    """Client directory"""
    
    CREDIT_STATUS_CHOICES = [
        ('active', 'Actif'),
        ('suspended', 'Suspendu'),
        ('blocked', 'Bloqué'),
    ]
    
    code = models.CharField(max_length=20, unique=True, verbose_name="Code client")
    raison_sociale = models.CharField(max_length=200, verbose_name="Raison sociale")
    forme_juridique = models.CharField(max_length=100, blank=True, verbose_name="Forme juridique")
    
    # Algerian fiscal identifiers
    nif = models.CharField(max_length=20, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=20, blank=True, verbose_name="NIS")
    rc = models.CharField(max_length=20, blank=True, verbose_name="RC")
    ai = models.CharField(max_length=20, blank=True, verbose_name="AI")
    
    # Contact information
    address = models.TextField(verbose_name="Adresse")
    wilaya = models.CharField(max_length=100, blank=True, verbose_name="Wilaya")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    fax = models.CharField(max_length=20, blank=True, verbose_name="Fax")
    email = models.EmailField(blank=True, verbose_name="Email")
    
    # Contact person
    contact_person = models.CharField(max_length=200, blank=True, verbose_name="Personne de contact")
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone contact")
    
    # Commercial terms
    payment_terms = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0)],
        verbose_name="Délai de paiement (jours)"
    )
    credit_status = models.CharField(
        max_length=20, 
        choices=CREDIT_STATUS_CHOICES, 
        default='active',
        verbose_name="Statut crédit"
    )
    max_discount_pct = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name="Remise maximale autorisée (%)"
    )
    
    # Status and metadata
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Notes
    notes = models.TextField(blank=True, verbose_name="Notes")
    
    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ['raison_sociale']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['raison_sociale']),
            models.Index(fields=['credit_status']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.raison_sociale}"
    
    def get_outstanding_balance(self):
        """Get total outstanding balance for this client"""
        from sales.models import ClientInvoice
        
        outstanding = ClientInvoice.objects.filter(
            client=self,
            status__in=['issued', 'partially_paid']
        ).aggregate(
            total=models.Sum('balance_due')
        )['total']
        
        return outstanding or Decimal('0.00')
    
    def get_total_sales_amount(self, year=None):
        """Get total sales amount for a given year"""
        from sales.models import ClientInvoice
        
        invoices = ClientInvoice.objects.filter(client=self)
        
        if year:
            invoices = invoices.filter(invoice_date__year=year)
        
        total = invoices.aggregate(total=models.Sum('total_ttc'))['total']
        return total or Decimal('0.00')
    
    def get_payment_terms_display_verbose(self):
        """Get verbose payment terms display"""
        if self.payment_terms == 0:
            return "Comptant"
        elif self.payment_terms == 30:
            return "30 jours"
        elif self.payment_terms == 60:
            return "60 jours"
        elif self.payment_terms == 90:
            return "90 jours"
        else:
            return f"{self.payment_terms} jours"
    
    def has_fiscal_identifier(self):
        """Check if client has at least one fiscal identifier"""
        return bool(self.nif or self.nis or self.rc or self.ai)
    
    def can_place_order(self):
        """Check if client can place new orders"""
        return self.credit_status in ['active', 'suspended'] and self.is_active
    
    def get_recent_deliveries(self, limit=10):
        """Get recent delivery notes for this client"""
        from sales.models import ClientDN
        return ClientDN.objects.filter(client=self).order_by('-delivery_date')[:limit]
    
    def get_recent_invoices(self, limit=10):
        """Get recent invoices for this client"""
        from sales.models import ClientInvoice
        return ClientInvoice.objects.filter(client=self).order_by('-invoice_date')[:limit]