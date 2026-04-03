# supplier_ops/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SupplierDN


@receiver(post_save, sender=SupplierDN)
def update_stock_on_dn_validation(sender, instance, created, **kwargs):
    """Create RM receipt StockMovements when a SupplierDN transitions to 'validated'.

    SPEC BR-RM-05: stock movements are created here, not in the model's
    validate() method, so the model stays free of stock-layer imports.

    The existing-movement guard prevents duplicate movements if the signal
    fires more than once (e.g. admin inline saves).
    """
    if instance.status != "validated" or created:
        return

    from stock.models import StockMovement

    for line in instance.lines.all():
        already_exists = StockMovement.objects.filter(
            raw_material=line.raw_material,
            movement_type="receipt",
            source_document_type="supplier_dn",
            source_document_id=instance.id,
            source_line_id=line.id,
        ).exists()

        if not already_exists:
            StockMovement.objects.create(
                raw_material=line.raw_material,
                movement_type="receipt",
                quantity=line.quantity_received,
                unit_price=line.agreed_unit_price,
                source_document_type="supplier_dn",
                source_document_id=instance.id,
                source_line_id=line.id,
                movement_date=instance.delivery_date,
                created_by=instance.validated_by,
                remarks=f"Réception BL {instance.reference}",
            )


# FIX: removed update_dn_total_on_line_change signal.
#
# The original signal called instance.supplier_dn.save() on every
# SupplierDNLine save.  This caused two problems:
#
#   1. REDUNDANT: SupplierDNLine.save() already does a direct
#      SupplierDN.objects.filter(pk=...).update(total_amount_ht=...) —
#      the signal was re-doing the same work.
#
#   2. DANGEROUS: calling supplier_dn.save() re-fires this very
#      post_save signal on SupplierDN.  If the DN is already 'validated',
#      the update_stock_on_dn_validation handler re-runs and, without the
#      duplicate guard, would have created duplicate StockMovements.
#      Even with the guard the extra DB round-trips are wasteful.
#
# The total is kept consistent by SupplierDNLine.save()'s direct .update()
# call, which is sufficient and safe.
