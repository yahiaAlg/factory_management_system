# quality/signals.py
"""Auto-open a Non-Conformity Report whenever a Sample's computed outcome
becomes Non-Conforming (Section 7.3). Pre-fills as much context as is
available. Idempotent: never opens a second NCR for the same sample."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Sample


@receiver(post_save, sender=Sample)
def auto_open_ncr_on_failed_sample(sender, instance, created, **kwargs):
    if created or instance.status != "non_conforming":
        return

    from .models import NonConformityReport

    if instance.ncrs.exists():
        return

    failing = instance.results.filter(outcome="fail", qa_override=False).select_related(
        "spec_line__property"
    )
    lines = ", ".join(
        f"{r.spec_line.property.name}={r.recorded_value}" for r in failing
    ) or "voir résultats de l'échantillon"

    NonConformityReport.objects.create(
        gate=instance.control_point,
        trigger_type="failed_sample",
        sample=instance,
        supplier_dn_line=instance.supplier_dn_line,
        production_order=instance.production_order,
        description=(
            f"Auto-ouverte : échantillon {instance.reference} non conforme "
            f"({lines})."
        ),
        opened_by=instance.sampled_by,
    )
