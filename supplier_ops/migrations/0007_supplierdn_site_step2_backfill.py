from django.db import migrations


def backfill_site(apps, schema_editor):
    ProductionSite = apps.get_model("core", "ProductionSite")
    main_site = ProductionSite.objects.order_by("id").first()
    if main_site is None:
        return
    SupplierDN = apps.get_model("supplier_ops", "SupplierDN")
    SupplierDN.objects.filter(site__isnull=True).update(site=main_site)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("supplier_ops", "0006_supplierdn_site_step1_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill_site, noop_reverse),
    ]
