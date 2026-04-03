from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import json

class UserProfile(models.Model):
    """User profile with role-based permissions"""
    
    ROLES = [
        ('manager', 'Manager / Administrateur'),
        ('stock_prod', 'Responsable Stock/Production'),
        ('accountant', 'Comptable'),
        ('sales', 'Commercial'),
        ('viewer', 'Consultation seule'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES, verbose_name="Rôle")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"
    
    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"
    
    def can_validate_supplier_dn(self):
        """Check if user can validate supplier delivery notes"""
        return self.role in ['manager', 'stock_prod']
    
    def can_create_supplier_invoice(self):
        """Check if user can create supplier invoices"""
        return self.role in ['manager', 'accountant']
    
    def can_validate_production_order(self):
        """Check if user can validate production orders"""
        return self.role in ['manager', 'stock_prod']
    
    def can_create_client_dn(self):
        """Check if user can create client delivery notes"""
        return self.role in ['manager', 'sales']
    
    def can_validate_expense_above_threshold(self):
        """Check if user can validate expenses above threshold"""
        return self.role in ['manager']
    
    def can_access_financial_reports(self):
        """Check if user can access financial reports"""
        return self.role in ['manager', 'accountant', 'viewer']
    
    def can_manage_settings(self):
        """Check if user can manage system settings"""
        return self.role in ['manager']

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created"""
    if created:
        UserProfile.objects.create(user=instance, role='viewer')

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()

class AuditLog(models.Model):
    """Immutable audit trail for all system actions"""
    
    ACTION_TYPES = [
        ('create', 'Création'),
        ('update', 'Modification'),
        ('validate', 'Validation'),
        ('pay', 'Paiement'),
        ('cancel', 'Annulation'),
        ('login', 'Connexion'),
        ('failed_login', 'Échec connexion'),
        ('delete', 'Suppression'),
    ]
    
    MODULES = [
        ('suppliers', 'Fournisseurs'),
        ('clients', 'Clients'),
        ('catalog', 'Catalogue'),
        ('supplier_ops', 'Opérations fournisseurs'),
        ('production', 'Production'),
        ('stock', 'Stock'),
        ('sales', 'Ventes'),
        ('expenses', 'Dépenses'),
        ('accounts', 'Comptes'),
        ('core', 'Système'),
    ]
    
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Horodatage")
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Utilisateur")
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name="Type d'action")
    module = models.CharField(max_length=20, choices=MODULES, verbose_name="Module")
    
    # Generic foreign key to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    entity_reference = models.CharField(max_length=100, blank=True, verbose_name="Référence entité")
    detail_json = models.TextField(verbose_name="Détails JSON")  # Before/after snapshot
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="Adresse IP")
    
    class Meta:
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journaux d'audit"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'user']),
            models.Index(fields=['module', 'action_type']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.user.username} - {self.get_action_type_display()}"
    
    def get_details(self):
        """Get parsed JSON details"""
        try:
            return json.loads(self.detail_json)
        except:
            return {}
    
    @classmethod
    def log_action(cls, user, action_type, module, instance, details=None, request=None):
        """Log an action to the audit trail"""
        if details is None:
            details = {}
        
        # Get IP address from request
        ip_address = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
        
        # Get entity reference if instance has a reference field
        entity_reference = ''
        if hasattr(instance, 'reference'):
            entity_reference = instance.reference
        elif hasattr(instance, 'pk'):
            entity_reference = str(instance.pk)
        
        return cls.objects.create(
            user=user,
            action_type=action_type,
            module=module,
            content_object=instance,
            entity_reference=entity_reference,
            detail_json=json.dumps(details, default=str, ensure_ascii=False),
            ip_address=ip_address
        )