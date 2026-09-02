from django.urls import path
from . import views

app_name = "supplier_ops"

urlpatterns = [
    # Supplier Delivery Notes
    path("supplier-dns/", views.supplier_dns_list, name="supplier_dns_list"),
    path("supplier-dns/create/", views.supplier_dn_create, name="supplier_dn_create"),
    path(
        "supplier-dns/<int:dn_id>/", views.supplier_dn_detail, name="supplier_dn_detail"
    ),
    path(
        "supplier-dns/<int:dn_id>/validate/",
        views.supplier_dn_validate,
        name="supplier_dn_validate",
    ),
    path(
        "supplier-dns/<int:dn_id>/qc-release/",
        views.supplier_dn_qc_release,
        name="supplier_dn_qc_release",
    ),
    path(
        "supplier-dns/<int:dn_id>/submit/",
        views.supplier_dn_submit,
        name="supplier_dn_submit",
    ),
    path(
        "supplier-dns/<int:dn_id>/print/",
        views.supplier_dn_print,
        name="supplier_dn_print",
    ),
    path(
        "supplier-dns/<int:dn_id>/add-document/",
        views.supplier_dn_add_document,
        name="supplier_dn_add_document",
    ),
    # Supplier Invoices
    path(
        "supplier-invoices/",
        views.supplier_invoices_list,
        name="supplier_invoices_list",
    ),
    path(
        "supplier-invoices/create/",
        views.supplier_invoice_create,
        name="supplier_invoice_create",
    ),
    path(
        "supplier-invoices/<int:invoice_id>/",
        views.supplier_invoice_detail,
        name="supplier_invoice_detail",
    ),
    path(
        "supplier-invoices/<int:invoice_id>/print/",
        views.supplier_invoice_print,
        name="supplier_invoice_print",
    ),
    path(
        "supplier-invoices/<int:invoice_id>/add-document/",
        views.supplier_invoice_add_document,
        name="supplier_invoice_add_document",
    ),
    # Supplier Payments
    path(
        "supplier-invoices/<int:invoice_id>/pay/",
        views.supplier_payment_create,
        name="supplier_payment_create",
    ),
    # Status transitions
    path(
        "supplier-dns/<int:dn_id>/change-status/",
        views.supplier_dn_change_status,
        name="supplier_dn_change_status",
    ),
    path(
        "supplier-invoices/<int:invoice_id>/change-status/",
        views.supplier_invoice_change_status,
        name="supplier_invoice_change_status",
    ),
    # AJAX endpoints
    path(
        "ajax/supplier-dns/<int:supplier_id>/",
        views.supplier_dns_for_supplier,
        name="supplier_dns_for_supplier",
    ),
    # Supplier account settlement (FIFO)
    path(
        "suppliers/<int:supplier_id>/settle/",
        views.supplier_account_settlement,
        name="supplier_account_settlement",
    ),
    # §23 (planned) — Prepayment / Opening Balance / Statement of Account
    path(
        "suppliers/<int:supplier_id>/avances/nouvelle/",
        views.supplier_advance_create,
        name="supplier_advance_create",
    ),
    path(
        "suppliers/<int:supplier_id>/solde-ouverture/",
        views.supplier_opening_balance_create,
        name="supplier_opening_balance_create",
    ),
    path(
        "suppliers/<int:supplier_id>/releve/",
        views.supplier_statement,
        name="supplier_statement",
    ),
]
