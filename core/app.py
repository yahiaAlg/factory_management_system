# core/apps.py
from django.apps import AppConfig


def _apply_admin_branding(company):
    """Push CompanyInformation fields into the Django admin site."""
    from django.contrib import admin

    name = company.raison_sociale or "Administration"
    admin.site.site_header = name
    admin.site.site_title = name
    admin.site.index_title = f"Espace d'administration — {name}"


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Paramètres"

    def ready(self):
        # Register signal handlers (PieceJointe file cleanup, ...).
        from . import signals  # noqa: F401

        # Apply branding from the singleton as soon as the app is loaded.
        # Wrapped in a broad try/except so a missing migration or empty DB
        # never prevents the server from starting.
        try:
            from .models import CompanyInformation

            company = CompanyInformation.objects.first()
            if company:
                _apply_admin_branding(company)
        except Exception:
            pass
