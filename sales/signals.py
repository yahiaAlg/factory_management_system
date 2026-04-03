from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ClientDN

@receiver(post_save, sender=ClientDN)
def update_stock_on_client_dn_validation(sender, instance, created, **kwargs):
    """Update finished product stock when client DN is validated"""
    if instance.status == 'validated' and not created:
        # Update stock balances for each line
        for line in instance.lines.all():
            from stock.models import StockMovement
            
            # Check if movement already exists to avoid duplicates
            existing_movement = StockMovement.objects.filter(
                finished_product=line.finished_product,
                movement_type='delivery',
                source_document_type='client_dn',
                source_document_id=instance.id,
                source_line_id=line.id
            ).first()
            
            if not existing_movement:
                StockMovement.objects.create(
                    finished_product=line.finished_product,
                    movement_type='delivery',
                    quantity=-line.quantity_delivered,  # Negative for delivery
                    unit_price=line.selling_unit_price_ht,
                    source_document_type='client_dn',
                    source_document_id=instance.id,
                    source_line_id=line.id,
                    movement_date=instance.delivery_date,
                    created_by=instance.validated_by,
                    remarks=f"Livraison BL {instance.reference}"
                )