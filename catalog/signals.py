# catalog/signals.py
#
# BR-DUAL-01 — dual-entry article: when a RawMaterial is linked to a
# FinishedProduct via RawMaterial.twin_finished_product, the two catalogue
# rows represent the same physical article seen from two sides (bought as
# a raw material, also sold/stocked as a finished product). This module
# keeps designation / unit_of_measure ⟷ sales_unit / is_active in sync in
# real time, in both directions.
#
# Each handler uses .update() (bypasses save()/signals) so a sync write on
# one side can never recurse back into the other side's handler.
#
# The matching stock-balance mirror (every StockMovement on either side
# mirrored onto the other's stock balance) lives in stock/signals.py.
#
# NOTE: unlike the avicole reference implementation, no cost/price sync is
# implemented here. RawMaterial only carries a static reference_price
# (not a computed weighted-average cost), while FinishedProduct.wac is
# computed exclusively from "production" movements — the two are not the
# same kind of figure, so there is no equivalent to mirror.

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="catalog.RawMaterial")
def sync_finished_product_twin(sender, instance, created, **kwargs):
    """When a RawMaterial with a twin_finished_product is saved, push its
    designation/unit_of_measure/is_active onto the twin."""
    if not instance.twin_finished_product_id:
        return

    from catalog.models import FinishedProduct

    FinishedProduct.objects.filter(pk=instance.twin_finished_product_id).exclude(
        designation=instance.designation,
        sales_unit_id=instance.unit_of_measure_id,
        is_active=instance.is_active,
    ).update(
        designation=instance.designation,
        sales_unit_id=instance.unit_of_measure_id,
        is_active=instance.is_active,
    )


@receiver(post_save, sender="catalog.FinishedProduct")
def sync_raw_material_twin(sender, instance, created, **kwargs):
    """Mirror image of sync_finished_product_twin — pushes changes from the
    FinishedProduct side back onto its RawMaterial twin, if any."""
    if not hasattr(instance, "twin_raw_material"):
        return

    from catalog.models import RawMaterial

    raw_material = instance.twin_raw_material
    RawMaterial.objects.filter(pk=raw_material.pk).exclude(
        designation=instance.designation,
        unit_of_measure_id=instance.sales_unit_id,
        is_active=instance.is_active,
    ).update(
        designation=instance.designation,
        unit_of_measure_id=instance.sales_unit_id,
        is_active=instance.is_active,
    )
