from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal

class RawMaterialCategory(models.Model):
    """Categories for raw materials"""
    
    name = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Catégorie matière première"
        verbose_name_plural = "Catégories matières premières"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class UnitOfMeasure(models.Model):
    """Units of measure for materials and products"""
    
    code = models.CharField(max_length=10, unique=True, verbose_name="Code")
    name = models.CharField(max_length=50, verbose_name="Nom")
    symbol = models.CharField(max_length=10, verbose_name="Symbole")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    class Meta:
        verbose_name = "Unité de mesure"
        verbose_name_plural = "Unités de mesure"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.symbol})"

class RawMaterial(models.Model):
    """Raw materials catalog"""
    
    STOCK_STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('running_low', 'Stock faible'),
        ('stockout', 'Rupture'),
        ('on_order', 'En commande'),
    ]
    
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence")
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    category = models.ForeignKey(RawMaterialCategory, on_delete=models.PROTECT, verbose_name="Catégorie")
    unit_of_measure = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, verbose_name="Unité de mesure")
    
    # Supplier information
    default_supplier = models.ForeignKey(
        'suppliers.Supplier', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Fournisseur par défaut"
    )
    
    # Pricing
    reference_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prix de référence"
    )
    
    # Stock thresholds
    alert_threshold = models.DecimalField(
        max_digits=10, 
        decimal_places=3,
        default=Decimal('0.000'),
        validators=[MinValueValidator(Decimal('0.000'))],
        verbose_name="Seuil d'alerte"
    )
    stockout_threshold = models.DecimalField(
        max_digits=10, 
        decimal_places=3,
        default=Decimal('0.000'),
        validators=[MinValueValidator(Decimal('0.000'))],
        verbose_name="Seuil de rupture"
    )
    
    # Status and metadata
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Matière première"
        verbose_name_plural = "Matières premières"
        ordering = ['reference']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['category', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.reference} - {self.designation}"
    
    def get_current_stock(self):
        """Get current stock quantity"""
        try:
            from stock.models import RawMaterialStockBalance
            balance = RawMaterialStockBalance.objects.get(raw_material=self)
            return balance.quantity
        except:
            return Decimal('0.000')
    
    def get_stock_status(self):
        """Calculate current stock status"""
        current_stock = self.get_current_stock()
        
        # Check if there's an active order
        from supplier_ops.models import SupplierDN
        has_active_order = SupplierDN.objects.filter(
            lines__raw_material=self,
            status__in=['pending', 'validated']
        ).exists()
        
        if has_active_order:
            return 'on_order'
        elif current_stock <= self.stockout_threshold:
            return 'stockout'
        elif current_stock <= self.alert_threshold:
            return 'running_low'
        else:
            return 'available'
    
    def get_stock_status_display_class(self):
        """Get CSS class for stock status display"""
        status = self.get_stock_status()
        classes = {
            'available': 'success',
            'running_low': 'warning',
            'stockout': 'danger',
            'on_order': 'info'
        }
        return classes.get(status, 'secondary')
    
    def clean(self):
        """Validate model fields"""
        from django.core.exceptions import ValidationError
        
        if self.alert_threshold <= self.stockout_threshold:
            raise ValidationError({
                'alert_threshold': 'Le seuil d\'alerte doit être supérieur au seuil de rupture'
            })

class FinishedProduct(models.Model):
    """Finished products catalog"""
    
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence")
    designation = models.CharField(max_length=200, verbose_name="Désignation")
    sales_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, verbose_name="Unité de vente")
    
    # Pricing
    reference_selling_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prix de vente de référence"
    )
    
    # Stock management
    alert_threshold = models.DecimalField(
        max_digits=10, 
        decimal_places=3,
        default=Decimal('0.000'),
        validators=[MinValueValidator(Decimal('0.000'))],
        verbose_name="Seuil d'alerte stock"
    )
    
    # Production link
    source_formulation = models.ForeignKey(
        'production.Formulation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Formulation source"
    )
    
    # Status and metadata
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Produit fini"
        verbose_name_plural = "Produits finis"
        ordering = ['reference']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.reference} - {self.designation}"
    
    def get_current_stock(self):
        """Get current stock quantity"""
        try:
            from stock.models import FinishedProductStockBalance
            balance = FinishedProductStockBalance.objects.get(finished_product=self)
            return balance.quantity
        except:
            return Decimal('0.000')
    
    def get_stock_status(self):
        """Calculate current stock status"""
        current_stock = self.get_current_stock()
        
        if current_stock <= Decimal('0'):
            return 'stockout'
        elif current_stock <= self.alert_threshold:
            return 'running_low'
        else:
            return 'available'
    
    def get_weighted_average_cost(self):
        """Calculate weighted average cost from production batches"""
        from production.models import ProductionOrder
        
        completed_orders = ProductionOrder.objects.filter(
            formulation__finished_product=self,
            status='completed'
        ).exclude(actual_qty_produced__lte=0)
        
        if not completed_orders.exists():
            return Decimal('0.00')
        
        total_cost = Decimal('0.00')
        total_quantity = Decimal('0.000')
        
        for order in completed_orders:
            batch_cost = order.calculate_batch_cost()
            if batch_cost > 0:
                total_cost += batch_cost * order.actual_qty_produced
                total_quantity += order.actual_qty_produced
        
        if total_quantity > 0:
            return total_cost / total_quantity
        
        return Decimal('0.00')
    
    def get_unit_gross_margin(self):
        """Calculate unit gross margin"""
        wac = self.get_weighted_average_cost()
        return self.reference_selling_price - wac
    
    def get_margin_rate(self):
        """Calculate margin rate percentage"""
        if self.reference_selling_price <= 0:
            return Decimal('0.00')
        
        gross_margin = self.get_unit_gross_margin()
        return (gross_margin / self.reference_selling_price) * 100