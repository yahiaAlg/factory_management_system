# Multi-site (functional spec §25.2) — step 1 of 3. SupplierDN has 1
# existing row in this environment, so `site` is added nullable first;
# step 2 (0007) backfills it onto "Site Principal", step 3 (0008) makes
# it required.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("supplier_ops", "0005_alter_supplierdn_status"),
        ("core", "0004_seed_main_site"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierdn",
            name="site",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="supplier_dns",
                to="core.productionsite",
                verbose_name="Site de réception",
                help_text="Site dont le stock de matières premières est crédité à la validation (fonc. spec §25.2.3).",
            ),
        ),
    ]
