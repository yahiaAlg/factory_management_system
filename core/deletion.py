# core/deletion.py
"""Shared helper for "hard delete" actions on master-data records
(raw materials, finished products, suppliers, ...).

Rather than hand-maintaining a per-model list of "is this referenced
elsewhere" checks (which drifts out of sync as new FKs get added
elsewhere in the app — see catalog.RawMaterial._is_referenced(), which
only checks 2 of the ~8 relations that actually point at it), this uses
Django's own deletion machinery to compute the real, current answer:

- If any relation uses on_delete=PROTECT and has at least one row
  pointing at the instance, Django itself refuses the delete — we
  surface exactly what's blocking it instead of a raw 500.
- If any relation uses on_delete=CASCADE, deleting the instance would
  silently delete those related rows too. We surface that as a
  warning up front instead of letting it happen silently.

This is the same machinery Django's own admin site delete-confirmation
page uses (django.contrib.admin.utils.NestedObjects), applied here to
this app's own UI instead.
"""
from django.db.models.deletion import Collector, ProtectedError


def describe_delete_plan(instance):
    """Return a dict describing what would happen if `instance` were deleted.

    {
        "blocked": bool,             # True if a PROTECT relation blocks deletion
        "blockers": [(label, count)],   # what's blocking, if blocked
        "cascades": [(label, count)],   # other rows that would ALSO be deleted, if not blocked
    }
    """
    collector = Collector(using=instance._state.db or "default")
    try:
        collector.collect([instance])
    except ProtectedError as exc:
        blockers = {}
        for obj in exc.protected_objects:
            label = obj._meta.verbose_name_plural
            blockers[label] = blockers.get(label, 0) + 1
        return {
            "blocked": True,
            "blockers": sorted(blockers.items()),
            "cascades": [],
        }

    cascades = {}
    for model, instances in collector.data.items():
        if model is type(instance):
            continue
        label = model._meta.verbose_name_plural
        cascades[label] = cascades.get(label, 0) + len(instances)

    # Django also has a "fast delete" path for simple cascades (no signals
    # to fire, nothing else pointing at them) — it bypasses collector.data
    # entirely and deletes straight from these querysets, so it has to be
    # checked separately or a real CASCADE relation (e.g. a SamplingPlan
    # pointing at this raw material) goes completely undetected here.
    for qs in collector.fast_deletes:
        if qs.model is type(instance):
            continue
        count = qs.count()
        if not count:
            continue
        label = qs.model._meta.verbose_name_plural
        cascades[label] = cascades.get(label, 0) + count

    return {
        "blocked": False,
        "blockers": [],
        "cascades": sorted(cascades.items()),
    }


def can_hard_delete(instance):
    """Quick boolean check for template use — True only when deleting
    `instance` would touch nothing else at all (no blockers, no cascades).
    Used to decide whether the trash icon is active or disabled."""
    plan = describe_delete_plan(instance)
    return not plan["blocked"] and not plan["cascades"]
