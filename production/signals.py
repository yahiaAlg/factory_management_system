# production/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ProductionOrder

@receiver(post_save, sender=ProductionOrder)
def update_stock_on_production_completion(sender, instance, created, **kwargs):
    """Update stock when production order is completed"""
    if instance.status == 'completed' and not created:
        from stock.models import StockMovement
        
        # Create raw material consumption movements
        for line in instance.consumption_lines.all():
            if line.qty_actual is not None and line.qty_actual > 0:
                # Check if movement already exists to avoid duplicates
                existing_movement = StockMovement.objects.filter(
                    raw_material=line.raw_material,
                    movement_type='consumption',
                    source_document_type='production_order',
                    source_document_id=instance.id,
                    source_line_id=line.id
                ).first()
                
                if not existing_movement:
                    StockMovement.objects.create(
                        raw_material=line.raw_material,
                        movement_type='consumption',
                        quantity=-line.qty_actual,  # Negative for consumption
                        unit_price=line.raw_material.reference_price,
                        source_document_type='production_order',
                        source_document_id=instance.id,
                        source_line_id=line.id,
                        movement_date=instance.closure_date,
                        created_by=instance.closed_by,
                        remarks=f"Consommation OP {instance.reference}"
                    )
        
        # Create finished goods production movement
        if instance.actual_qty_produced and instance.actual_qty_produced > 0:
            existing_fg_movement = StockMovement.objects.filter(
                finished_product=instance.formulation.finished_product,
                movement_type='production',
                source_document_type='production_order',
                source_document_id=instance.id
            ).first()
            
            if not existing_fg_movement:
                StockMovement.objects.create(
                    finished_product=instance.formulation.finished_product,
                    movement_type='production',
                    quantity=instance.actual_qty_produced,
                    unit_cost=instance.get_unit_cost(),
                    source_document_type='production_order',
                    source_document_id=instance.id,
                    movement_date=instance.closure_date,
                    created_by=instance.closed_by,
                    remarks=f"Production OP {instance.reference}"
                )