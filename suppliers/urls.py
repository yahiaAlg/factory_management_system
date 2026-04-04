from django.urls import path
from . import views

app_name = "suppliers"

urlpatterns = [
    path("", views.suppliers_list, name="suppliers_list"),
    path("create/", views.supplier_create, name="supplier_create"),
    path("<int:supplier_id>/", views.supplier_detail, name="supplier_detail"),
    path("<int:supplier_id>/edit/", views.supplier_edit, name="supplier_edit"),
    path(
        "<int:supplier_id>/toggle-active/",
        views.supplier_toggle_active,
        name="supplier_toggle_active",
    ),
]
