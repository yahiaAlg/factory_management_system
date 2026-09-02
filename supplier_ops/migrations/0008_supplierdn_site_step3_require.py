import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("supplier_ops", "0007_supplierdn_site_step2_backfill"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplierdn",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="supplier_dns",
                to="core.productionsite",
                verbose_name="Site de réception",
                help_text="Site dont le stock de matières premières est crédité à la validation (fonc. spec §25.2.3).",
            ),
        ),
    ]
