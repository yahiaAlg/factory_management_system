import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0004_site_step2_backfill"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rawmaterialstockbalance",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="raw_material_stock_balances",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AlterField(
            model_name="finishedproductstockbalance",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="finished_product_stock_balances",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_movements",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AlterField(
            model_name="stockadjustment",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_adjustments",
                to="core.productionsite",
                verbose_name="Site",
            ),
        ),
        migrations.AddConstraint(
            model_name="rawmaterialstockbalance",
            constraint=models.UniqueConstraint(
                fields=("site", "raw_material"), name="uniq_rm_balance_per_site"
            ),
        ),
        migrations.AddConstraint(
            model_name="finishedproductstockbalance",
            constraint=models.UniqueConstraint(
                fields=("site", "finished_product"), name="uniq_fp_balance_per_site"
            ),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(
                fields=["site", "raw_material", "movement_date"],
                name="stock_stock_site_id_d253f5_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(
                fields=["site", "finished_product", "movement_date"],
                name="stock_stock_site_id_97f648_idx",
            ),
        ),
    ]
