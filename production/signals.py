# production/signals.py
#
# TIMING BUG FIX — original design:
#
#   ProductionOrder.close() does:
#     1. self.save()                     ← post_save fires HERE (status='completed')
#     2. line.qty_actual = x; line.save() ← lines updated AFTER the signal
#
#   Consequence: when the original single post_save handler ran, all consumption
#   lines still had qty_actual=None, so the `if line.qty_actual is not None`
#   guard prevented every RM movement from being created.  Only the FG
#   production movement could have been created (actual_qty_produced IS set on
#   the PO by the time self.save() is called), but even that was bundled in the
#   same guard block and was effectively unreachable.
#
# FIX — split into two independent signals:
#
#   Signal A (ProductionOrder post_save):
#     Creates the finished-goods PRODUCTION movement.
#     actual_qty_produced and get_unit_cost() are both available at this point.
#
#   Signal B (ProductionOrderLine post_save):
#     Creates the raw-material CONSUMPTION movement for that line when
#     qty_actual is set and the parent PO is already completed.
#     Fires once per line as close() saves each line individually.

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ProductionOrder, ProductionOrderLine


# ---------------------------------------------------------------------------
# Signal A — finished-goods stock credit on PO completion
# ---------------------------------------------------------------------------


@receiver(post_save, sender=ProductionOrder)
def create_fg_movement_on_po_completion(sender, instance, created, **kwargs):
    """Credit finished-goods stock when a ProductionOrder is completed.

    actual_qty_produced and get_unit_cost() are available at the point
    ProductionOrder.close() calls self.save(), so this fires correctly.
    """
    if instance.status != "completed" or created:
        return
    if not instance.actual_qty_produced or instance.actual_qty_produced <= 0:
        return

    from stock.models import StockMovement

    already_exists = StockMovement.objects.filter(
        finished_product=instance.formulation.finished_product,
        movement_type="production",
        source_document_type="production_order",
        source_document_id=instance.id,
    ).exists()

    if not already_exists:
        StockMovement.objects.create(
            finished_product=instance.formulation.finished_product,
            movement_type="production",
            quantity=instance.actual_qty_produced,
            unit_cost=instance.get_unit_cost(),
            source_document_type="production_order",
            source_document_id=instance.id,
            movement_date=instance.closure_date,
            created_by=instance.closed_by,
            remarks=f"Production OP {instance.reference}",
        )


# ---------------------------------------------------------------------------
# Signal B — raw-material consumption deduction per line
# ---------------------------------------------------------------------------


@receiver(post_save, sender=ProductionOrderLine)
def create_rm_consumption_on_line_save(sender, instance, created, **kwargs):
    """Deduct raw-material stock when a consumption line's qty_actual is recorded.

    ProductionOrder.close() saves lines one by one AFTER the PO itself is
    saved.  This signal fires for each line and creates the RM movement as
    soon as qty_actual is committed, with a duplicate guard so re-saves are
    idempotent.

    SPEC BR-PROD-05: uses qty_actual (not qty_theoretical) for RM deductions.
    """
    if instance.qty_actual is None or instance.qty_actual <= 0:
        return

    po = instance.production_order
    if po.status != "completed":
        return

    from stock.models import StockMovement

    already_exists = StockMovement.objects.filter(
        raw_material=instance.raw_material,
        movement_type="consumption",
        source_document_type="production_order",
        source_document_id=po.id,
        source_line_id=instance.id,
    ).exists()

    if not already_exists:
        StockMovement.objects.create(
            raw_material=instance.raw_material,
            movement_type="consumption",
            quantity=-instance.qty_actual,  # negative = outflow
            unit_price=instance.raw_material.reference_price,
            source_document_type="production_order",
            source_document_id=po.id,
            source_line_id=instance.id,
            movement_date=po.closure_date,
            created_by=po.closed_by,
            remarks=f"Consommation OP {po.reference}",
        )
