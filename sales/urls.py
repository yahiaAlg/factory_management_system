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
    path("client-dns/<int:dn_id>/edit/", views.client_dn_edit, name="client_dn_edit"),
    path(
        "client-dns/<int:dn_id>/ajouter-justificatif/",
        views.client_dn_add_document,
        name="client_dn_add_document",
    ),
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
        "client-dns/for-client/<int:client_id>/",
        views.client_dns_for_client,
        name="client_dns_for_client",
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
    path(
        "client-invoices/<int:invoice_id>/change-status/",
        views.client_invoice_change_status,
        name="client_invoice_change_status",
    ),
    path(
        "client-invoices/<int:invoice_id>/ajouter-justificatif/",
        views.client_invoice_add_document,
        name="client_invoice_add_document",
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
    # AJAX helpers
    path(
        "ajax/finished-product/<int:product_id>/info/",
        views.finished_product_info,
        name="finished_product_info",
    ),
    # Client account settlement (FIFO)
    path(
        "clients/<int:client_id>/settle/",
        views.client_account_settlement,
        name="client_account_settlement",
    ),
    # §23 (planned) — Prepayment / Opening Balance / Statement of Account
    path(
        "clients/<int:client_id>/avances/nouvelle/",
        views.client_advance_create,
        name="client_advance_create",
    ),
    path(
        "clients/<int:client_id>/solde-ouverture/",
        views.client_opening_balance_create,
        name="client_opening_balance_create",
    ),
    path(
        "clients/<int:client_id>/releve/",
        views.client_statement,
        name="client_statement",
    ),
]
