# Multi-site (functional spec §25.2). ProductionOrder has zero rows in
# this environment (confirmed before writing this migration), so a single
# NOT NULL AddField is safe — no backfill step needed, unlike stock/
# supplier_ops where existing rows required a nullable→backfill→require
# sequence. A real deployment with existing ProductionOrder rows should
# follow that same 3-step pattern instead of applying this migration as-is.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0005_productionorder_gate_b_ack_by_and_more"),
        ("core", "0004_seed_main_site"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionorder",
            name="site",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="production_orders",
                to="core.productionsite",
                verbose_name="Site",
                help_text=(
                    "Site où l'ordre est exécuté (fonc. spec §25.2.3) : la matière "
                    "première est consommée depuis le stock de CE site, et le "
                    "produit fini y est ajouté."
                ),
            ),
            preserve_default=False,
        ),
    ]
