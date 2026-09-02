from django.urls import path
from . import views

app_name = "expenses"

urlpatterns = [
    # Dashboard
    path("dashboard/", views.expenses_dashboard, name="expenses_dashboard"),
    # Expenses
    path("", views.expenses_list, name="expenses_list"),
    path("create/", views.expense_create, name="expense_create"),
    path("<int:expense_id>/", views.expense_detail, name="expense_detail"),
    path("<int:expense_id>/validate/", views.expense_validate, name="expense_validate"),
    path(
        "<int:expense_id>/mark-paid/", views.expense_mark_paid, name="expense_mark_paid"
    ),
    # Supporting Documents
    path(
        "<int:expense_id>/add-document/",
        views.supporting_document_create,
        name="supporting_document_create",
    ),
    # Reports
    path("report/", views.expenses_report, name="expenses_report"),
]
