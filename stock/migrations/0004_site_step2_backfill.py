from django.db import migrations


def backfill_site(apps, schema_editor):
    ProductionSite = apps.get_model("core", "ProductionSite")
    main_site = ProductionSite.objects.order_by("id").first()
    if main_site is None:
        # Nothing to backfill onto — 0004_seed_main_site in core should
        # already have created one, but guard against an empty table.
        return

    RawMaterialStockBalance = apps.get_model("stock", "RawMaterialStockBalance")
    FinishedProductStockBalance = apps.get_model(
        "stock", "FinishedProductStockBalance"
    )
    StockMovement = apps.get_model("stock", "StockMovement")
    StockAdjustment = apps.get_model("stock", "StockAdjustment")

    RawMaterialStockBalance.objects.filter(site__isnull=True).update(site=main_site)
    FinishedProductStockBalance.objects.filter(site__isnull=True).update(
        site=main_site
    )
    StockMovement.objects.filter(site__isnull=True).update(site=main_site)
    StockAdjustment.objects.filter(site__isnull=True).update(site=main_site)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0003_site_step1_add_nullable"),
    ]

    operations = [
        migrations.RunPython(backfill_site, noop_reverse),
    ]
