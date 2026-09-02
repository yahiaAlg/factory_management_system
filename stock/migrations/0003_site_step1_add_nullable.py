# Multi-site (functional spec §25.2) — step 1 of 3.
#
# Adds `site` as NULLABLE first because RawMaterialStockBalance (7 rows),
# StockMovement (7 rows) already have data in this environment: a straight
# NOT NULL add would fail. Step 2 (0004) backfills every existing row onto
# the seeded "Site Principal", then step 3 (0005) makes `site` required and
# adds the per-site uniqueness constraints/indexes.
#
# Also converts RawMaterialStockBalance.raw_material and
# FinishedProductStockBalance.finished_product from OneToOneField to
# ForeignKey: once more than one ProductionSite exists, a material can have
# more than one balance row (one per site), so the 1:1 constraint no longer
# holds.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0002_stockmovement_is_dual_mirror"),
        ("core", "0004_seed_main_site"),
        ("catalog", "0005_rawmaterial_twin_finished_product"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rawmaterialstockbalance",
            name="raw_material",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stock_balances",
                to="catalog.rawmaterial",
            ),
        ),
        migrations.AlterField(
            model_name="finishedproductstockbalance",
            name="finished_product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stock_balances",
                to="catalog.finishedproduct",
            ),
        ),
        migrations.AddField(
            model_name="rawmaterialstockbalance",
            name="site",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="raw_material_stock_balances",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AddField(
            model_name="finishedproductstockbalance",
            name="site",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="finished_product_stock_balances",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="site",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_movements",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AddField(
            model_name="stockadjustment",
            name="site",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_adjustments",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
    ]
