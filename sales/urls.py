from django.urls import path
from . import views

app_name = "sales"

urlpatterns = [
    # Dashboard
    path("dashboard/", views.sales_dashboard, name="sales_dashboard"),
    # Client Delivery Notes
    path("client-dns/", views.client_dns_list, name="client_dns_list"),
    path("client-dns/create/", views.client_dn_create, name="client_dn_create"),
    path("client-dns/<int:dn_id>/", views.client_dn_detail, name="client_dn_detail"),
    path(
        "client-dns/<int:dn_id>/validate/",
        views.client_dn_validate,
        name="client_dn_validate",
    ),
    path(
        "client-dns/<int:dn_id>/print/", views.client_dn_print, name="client_dn_print"
    ),
    # Client Invoices
    path("client-invoices/", views.client_invoices_list, name="client_invoices_list"),
    path(
        "client-invoices/create/",
        views.client_invoice_create,
        name="client_invoice_create",
    ),
    path(
        "client-invoices/<int:invoice_id>/",
        views.client_invoice_detail,
        name="client_invoice_detail",
    ),
    path(
        "client-invoices/<int:invoice_id>/print/",
        views.client_invoice_print,
        name="client_invoice_print",
    ),
    # Client Payments
    path(
        "client-invoices/<int:invoice_id>/collect/",
        views.client_payment_create,
        name="client_payment_create",
    ),
    path(
        "client-payments/<int:payment_id>/receipt/",
        views.client_payment_receipt_print,
        name="client_payment_receipt_print",
    ),
]
