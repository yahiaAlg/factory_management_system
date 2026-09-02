# Multi-site (functional spec §25.2). ClientDN has zero rows in this
# environment (confirmed before writing this migration), so a single NOT
# NULL AddField is safe — see production/migrations/0006 for the same
# reasoning. A deployment with existing ClientDN rows should instead use
# the nullable→backfill→require 3-step pattern (see stock/ or
# supplier_ops/ migrations for that pattern).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0004_clientinvoice_is_opening_balance_clientinvoice_notes_and_more"),
        ("core", "0004_seed_main_site"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientdn",
            name="site",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="client_dns",
                to="core.productionsite",
                verbose_name="Site expéditeur",
                help_text="Site dont le stock de produits finis est débité à la validation (fonc. spec §25.2.3).",
            ),
            preserve_default=False,
        ),
    ]
