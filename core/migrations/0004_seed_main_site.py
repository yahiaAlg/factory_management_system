from django.db import migrations


def seed_main_site(apps, schema_editor):
    ProductionSite = apps.get_model("core", "ProductionSite")
    if not ProductionSite.objects.exists():
        ProductionSite.objects.create(
            name="Site Principal",
            code="MAIN",
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    # Intentionally left as a no-op: removing the seeded site on reverse
    # migration could orphan any site-scoped records created against it.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_productionsite"),
    ]

    operations = [
        migrations.RunPython(seed_main_site, noop_reverse),
    ]
