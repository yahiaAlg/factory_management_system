"""
Data migration: resolve pre-existing duplicate (target, version) rows in
QualitySpecification before the new uniqueness constraint (next migration)
is added.

Why this is needed: QualitySpecification.save() previously excluded 'version'
from full_clean()'s validation, AND even a plain unique_together on
(raw_material, finished_product, version) would never have caught this,
because exactly one of raw_material/finished_product is always NULL for any
given row, and Django/SQL both skip uniqueness checks whenever a field in the
tuple is NULL. In practice this meant nothing ever stopped two "v1" specs
existing for the same raw material or finished product.

Any environment that hit this bug may already have such duplicates on disk.
Applying the next migration's UniqueConstraint directly against that data
would fail with an IntegrityError. This migration keeps the first-created row
for each (target, version) pair untouched — preserving anything already
locked to it, e.g. a drawn Sample — and renumbers only the later duplicate(s)
to the next free version number for that same target, so no data is deleted
and no existing foreign keys change.

NOTE FOR OPERATORS: this only removes the *version-number collision* so the
schema migration can apply. It does not know which of the duplicate rows has
the "correct" spec lines for your process, and it does not re-point any
Sample that may have been locked to the wrong (e.g. empty) row. If you hit
the original bug — a sample showing "Aucune ligne de spécification pour ce
gate" — check which specification your existing sample(s) are locked to
after this migration runs, and move/copy lines over manually if needed.
"""
from django.db import migrations


def dedupe_versions(apps, schema_editor):
    QualitySpecification = apps.get_model("quality", "QualitySpecification")

    def process(target_field):
        by_target = {}
        qs = QualitySpecification.objects.filter(
            **{f"{target_field}__isnull": False}
        ).order_by("id")
        for spec in qs:
            target_id = getattr(spec, f"{target_field}_id")
            by_target.setdefault(target_id, []).append(spec)

        for target_id, specs in by_target.items():
            used_versions = {s.version for s in specs}
            seen = set()
            for spec in specs:  # oldest (lowest id) first: keep the original
                if spec.version in seen:
                    new_version = max(used_versions) + 1
                    spec.version = new_version
                    spec.save(update_fields=["version"])
                    used_versions.add(new_version)
                    seen.add(new_version)
                else:
                    seen.add(spec.version)

    process("raw_material")
    process("finished_product")


def noop_reverse(apps, schema_editor):
    # Renumbering is not reversible (we don't know the original numbers),
    # and reversing would just reintroduce the bug this migration fixes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("quality", "0002_qualityspecline_accepted_categories_and_more"),
    ]

    operations = [
        migrations.RunPython(dedupe_versions, noop_reverse),
    ]
