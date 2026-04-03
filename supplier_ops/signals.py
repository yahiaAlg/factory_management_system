# supplier_ops/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import SupplierDN, SupplierDNLine

@receiver(post_save, sender=SupplierDN)
def update_stock_on_dn_validation(sender, instance, created, **kwargs):
    """Update raw material stock when supplier DN is validated"""
    if instance.status == 'validated' and not created:
        # Update stock balances for each line
        for line in instance.lines.all():
            from stock.models import StockMovement
            
            # Check if movement already exists to avoid duplicates
            existing_movement = StockMovement.objects.filter(
                raw_material=line.raw_material,
                movement_type='receipt',
                source_document_type='supplier_dn',
                source_document_id=instance.id,
                source_line_id=line.id
            ).first()
            
            if not existing_movement:
                StockMovement.objects.create(
                    raw_material=line.raw_material,
                    movement_type='receipt',
                    quantity=line.quantity_received,
                    unit_price=line.agreed_unit_price,
                    source_document_type='supplier_dn',
                    source_document_id=instance.id,
                    source_line_id=line.id,
                    movement_date=instance.delivery_date,
                    created_by=instance.validated_by,
                    remarks=f"Réception BL {instance.reference}"
                )

@receiver(post_save, sender=SupplierDNLine)
def update_dn_total_on_line_change(sender, instance, **kwargs):
    """Update DN total when lines are modified"""
    if instance.supplier_dn_id:
        instance.supplier_dn.save()