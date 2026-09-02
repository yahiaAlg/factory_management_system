# stock/signals.py
#
# NOTE (spec BR-RM-05): StockMovement records are NEVER deleted — they are
# the immutable audit trail for all stock changes.  The post_delete handler
# below is therefore removed: it contradicts the spec and was also broken
# (missing 'models' and 'Decimal' imports).
#
# The only permitted write paths for stock balances are:
#   - stock.signals.supplier_dn_validated  (via supplier_ops/signals.py)
#   - stock.signals.production_order_closed (via production/signals.py)
#   - stock.signals.client_dn_validated    (via sales/signals.py)
#   - StockAdjustment.approve()
#   - stock.signals.mirror_dual_article_movement (below, BR-DUAL-01 only)
#
# StockMovement.save() already calls update_stock_balance() directly, so no
# post_save signal is needed for ordinary balance updates — it would
# double-update the balance. The one signal registered below does NOT
# duplicate that: it creates a *second*, separate StockMovement row (for
# the dual-entry twin), whose own save() then updates the twin's balance
# exactly the same way any other movement would.

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BR-DUAL-01 — dual-entry article: mirror every StockMovement onto the
# twin's stock (RawMaterial ⟷ FinishedProduct, via
# RawMaterial.twin_finished_product — see catalog/models.py).
#
# Unlike the avicole reference implementation this project was adapted
# from, there is no accompanying cost-sync rule here: RawMaterial only
# carries a static reference_price (no computed weighted-average cost to
# keep aligned), and FinishedProduct.wac is computed exclusively from
# "production"-type movements, so a mirrored "receipt"/"delivery"/etc.
# movement does not feed it — that is an existing, unrelated limitation of
# FinishedProductStockBalance.update_weighted_average_cost(), not
# something this signal attempts to work around.
# ---------------------------------------------------------------------------


@receiver(post_save, sender="stock.StockMovement")
def mirror_dual_article_movement(sender, instance, created, **kwargs):
    """
    When a StockMovement is created for one side of a dual-entry article
    (a RawMaterial linked to a FinishedProduct via
    RawMaterial.twin_finished_product, BR-DUAL-01), create a mirrored
    StockMovement of the same quantity/type on the twin's side.

    Flagged is_dual_mirror=True on the mirrored row so this handler never
    re-mirrors it and loops forever. Only the quantity/type mirror is
    performed here; the twin's balance updates itself the normal way, via
    the mirrored StockMovement's own save() → update_stock_balance().
    """
    if not created or instance.is_dual_mirror:
        return

    twin_raw_material = None
    twin_finished_product = None

    if instance.raw_material_id and instance.raw_material.twin_finished_product_id:
        twin_finished_product = instance.raw_material.twin_finished_product
    elif instance.finished_product_id and hasattr(
        instance.finished_product, "twin_raw_material"
    ):
        twin_raw_material = instance.finished_product.twin_raw_material
    else:
        return  # not a dual-entry article — nothing to mirror

    from .models import StockMovement

    mirror_note = "Synchronisation automatique (article à double entrée)"
    remarks = f"{mirror_note} — {instance.remarks}" if instance.remarks else mirror_note

    StockMovement.objects.create(
        site=instance.site,
        raw_material=twin_raw_material,
        finished_product=twin_finished_product,
        movement_type=instance.movement_type,
        quantity=instance.quantity,
        unit_price=instance.unit_price,
        unit_cost=instance.unit_cost,
        source_document_type=instance.source_document_type,
        source_document_id=instance.source_document_id,
        source_line_id=instance.source_line_id,
        movement_date=instance.movement_date,
        remarks=remarks,
        created_by=instance.created_by,
        is_dual_mirror=True,
    )

    logger.debug(
        "Dual-article mirror: StockMovement pk=%s (%s) -> mirrored %s onto %s.",
        instance.pk,
        instance.get_movement_type_display(),
        instance.quantity,
        twin_finished_product or twin_raw_material,
    )
