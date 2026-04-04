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
        "supplier-dns/<int:dn_id>/print/",
        views.supplier_dn_print,
        name="supplier_dn_print",
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
    # Supplier Payments
    path(
        "supplier-invoices/<int:invoice_id>/pay/",
        views.supplier_payment_create,
        name="supplier_payment_create",
    ),
    # AJAX endpoints
    path(
        "reconciliation/<int:invoice_id>/",
        views.reconciliation_ajax,
        name="reconciliation_ajax",
    ),
]
