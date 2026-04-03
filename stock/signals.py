# stock/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import StockMovement, RawMaterialStockBalance, FinishedProductStockBalance

@receiver(post_save, sender=StockMovement)
def update_stock_balance_on_movement(sender, instance, created, **kwargs):
    """Update stock balance when a movement is created"""
    if created:
        instance.update_stock_balance()

@receiver(post_delete, sender=StockMovement)
def update_stock_balance_on_movement_delete(sender, instance, **kwargs):
    """Update stock balance when a movement is deleted"""
    # Recalculate balance after deletion
    if instance.raw_material:
        try:
            balance = RawMaterialStockBalance.objects.get(raw_material=instance.raw_material)
            # Recalculate from remaining movements
            total_quantity = StockMovement.objects.filter(
                raw_material=instance.raw_material
            ).aggregate(
                total=models.Sum('quantity')
            )['total'] or Decimal('0.000')
            
            balance.quantity = total_quantity
            balance.save()
        except RawMaterialStockBalance.DoesNotExist:
            pass
    
    elif instance.finished_product:
        try:
            balance = FinishedProductStockBalance.objects.get(finished_product=instance.finished_product)
            # Recalculate from remaining movements
            total_quantity = StockMovement.objects.filter(
                finished_product=instance.finished_product
            ).aggregate(
                total=models.Sum('quantity')
            )['total'] or Decimal('0.000')
            
            balance.quantity = total_quantity
            balance.save()
            balance.update_weighted_average_cost()
        except FinishedProductStockBalance.DoesNotExist:
            pass