from django.apps import AppConfig


class QualityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quality'
    verbose_name = 'Qualité / Laboratoire'

    def ready(self):
        import quality.signals  # noqa: F401
