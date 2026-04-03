from django.apps import AppConfig


class SupplierOpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'supplier_ops'

    def ready(self):
        import supplier_ops.signals