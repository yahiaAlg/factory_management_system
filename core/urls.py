from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("company-settings/", views.company_settings, name="company_settings"),
    path("system-parameters/", views.system_parameters, name="system_parameters"),
    path("chart-data/", views.chart_data_ajax, name="chart_data_ajax"),
    path("expense-chart-data/", views.expense_chart_ajax, name="expense_chart_ajax"),
    # ── Pièces jointes — generic delete shared by every app ──────────────
    # Every app's detail/edit templates (SupplierDN, SupplierInvoice,
    # Expense, ClientDN, ClientInvoice, ...) point their delete buttons at
    # this single POST-only view instead of each app re-implementing
    # attachment deletion.
    path(
        "pieces-jointes/<int:pk>/supprimer/",
        views.piece_jointe_delete,
        name="piece_jointe_delete",
    ),
]
