# Generated for Multi-Site Architecture role-locking (functional spec §25.2,
# mirroring the avicole project's Branche role-locking, §3.5.2).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_seed_main_site"),
        ("accounts", "0002_alter_auditlog_module_alter_userprofile_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="site",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Obligatoire pour Responsable Stock/Production et "
                    "Commercial. Optionnel pour Comptable et Consultation "
                    "(vide = vue globale, toutes les sites). Toujours vide "
                    "pour Manager."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="userprofiles",
                to="core.productionsite",
                verbose_name="Site de production",
            ),
        ),
    ]
