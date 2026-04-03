from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class CompanyInformation(models.Model):
    """Company information used in printed documents"""
    
    raison_sociale = models.CharField(max_length=200, verbose_name="Raison sociale")
    forme_juridique = models.CharField(max_length=100, blank=True, verbose_name="Forme juridique")
    nif = models.CharField(max_length=20, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=20, blank=True, verbose_name="NIS")
    rc = models.CharField(max_length=20, blank=True, verbose_name="RC")
    ai = models.CharField(max_length=20, blank=True, verbose_name="AI")
    address = models.TextField(verbose_name="Adresse")
    wilaya = models.CharField(max_length=100, verbose_name="Wilaya")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    bank_name = models.CharField(max_length=200, blank=True, verbose_name="Nom de la banque")
    bank_account = models.CharField(max_length=50, blank=True, verbose_name="Compte bancaire")
    rib = models.CharField(max_length=23, blank=True, verbose_name="RIB")
    logo = models.ImageField(upload_to='company/', blank=True, verbose_name="Logo")
    
    # Fiscal settings
    vat_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=4, 
        default=Decimal('0.19'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        verbose_name="Taux de TVA"
    )
    fiscal_regime = models.CharField(max_length=100, blank=True, verbose_name="Régime fiscal")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Informations société"
        verbose_name_plural = "Informations société"
    
    def __str__(self):
        return self.raison_sociale
    
    def save(self, *args, **kwargs):
        # Ensure only one company record exists
        if not self.pk and CompanyInformation.objects.exists():
            raise ValueError("Il ne peut y avoir qu'un seul enregistrement de société")
        super().save(*args, **kwargs)

class SystemParameter(models.Model):
    """System-wide configuration parameters"""
    
    PARAMETER_TYPES = [
        ('financial', 'Paramètres financiers'),
        ('stock', 'Paramètres stock'),
        ('production', 'Paramètres production'),
        ('alert', 'Paramètres alertes'),
        ('document', 'Paramètres documents'),
    ]
    
    category = models.CharField(max_length=20, choices=PARAMETER_TYPES, verbose_name="Catégorie")
    key = models.CharField(max_length=100, unique=True, verbose_name="Clé")
    value = models.TextField(verbose_name="Valeur")
    description = models.TextField(verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Paramètre système"
        verbose_name_plural = "Paramètres système"
        unique_together = ['category', 'key']
    
    def __str__(self):
        return f"{self.category} - {self.key}"
    
    @classmethod
    def get_value(cls, key, default=None):
        """Get parameter value by key"""
        try:
            param = cls.objects.get(key=key, is_active=True)
            return param.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def get_decimal_value(cls, key, default=Decimal('0')):
        """Get parameter value as Decimal"""
        value = cls.get_value(key)
        if value:
            try:
                return Decimal(str(value))
            except:
                pass
        return default
    
    @classmethod
    def get_int_value(cls, key, default=0):
        """Get parameter value as integer"""
        value = cls.get_value(key)
        if value:
            try:
                return int(value)
            except:
                pass
        return default

class DocumentSequence(models.Model):
    """Document reference number sequences"""
    
    prefix = models.CharField(max_length=10, unique=True, verbose_name="Préfixe")
    current_year = models.IntegerField(verbose_name="Année courante")
    current_number = models.IntegerField(default=0, verbose_name="Numéro courant")
    description = models.CharField(max_length=200, verbose_name="Description")
    
    class Meta:
        verbose_name = "Séquence document"
        verbose_name_plural = "Séquences documents"
        unique_together = ['prefix', 'current_year']
    
    def __str__(self):
        return f"{self.prefix}-{self.current_year}-{self.current_number:04d}"
    
    @classmethod
    def get_next_reference(cls, prefix, year):
        """Get next document reference for given prefix and year"""
        sequence, created = cls.objects.get_or_create(
            prefix=prefix,
            current_year=year,
            defaults={'current_number': 0, 'description': f'Séquence pour {prefix}'}
        )
        
        sequence.current_number += 1
        sequence.save()
        
        return f"{prefix}-{year}-{sequence.current_number:04d}"