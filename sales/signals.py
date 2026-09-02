# sales/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ClientDN, ClientPayment


@receiver(post_save, sender=ClientDN)
def update_stock_on_client_dn_validation(sender, instance, created, **kwargs):
    """Update finished product stock when client DN is validated"""
    if instance.status == "validated" and not created:
        for line in instance.lines.all():
            from stock.models import StockMovement

            existing_movement = StockMovement.objects.filter(
                finished_product=line.finished_product,
                movement_type="delivery",
                source_document_type="client_dn",
                source_document_id=instance.id,
                source_line_id=line.id,
            ).first()

            if not existing_movement:
                StockMovement.objects.create(
                    site=instance.site,
                    finished_product=line.finished_product,
                    movement_type="delivery",
                    quantity=-line.quantity_delivered,
                    unit_price=line.selling_unit_price_ht,
                    source_document_type="client_dn",
                    source_document_id=instance.id,
                    source_line_id=line.id,
                    movement_date=instance.delivery_date,
                    created_by=instance.validated_by,
                    remarks=f"Livraison BL {instance.reference}",
                )


@receiver(post_save, sender=ClientPayment)
def client_payment_post_save(sender, instance, created, **kwargs):
    """Recompute invoice balance_due after a payment is saved (spec S7)."""
    if instance.client_invoice_id:
        instance.client_invoice.recompute_balance_due()


@receiver(post_delete, sender=ClientPayment)
def client_payment_post_delete(sender, instance, **kwargs):
    """Recompute invoice balance_due if a payment is deleted."""
    if instance.client_invoice_id:
        try:
            instance.client_invoice.recompute_balance_due()
        except Exception:
            pass
