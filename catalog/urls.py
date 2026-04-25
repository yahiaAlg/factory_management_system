from django.urls import path
from . import views

app_name = "catalog"

urlpatterns = [
    # Raw Materials
    path("raw-materials/", views.raw_materials_list, name="raw_materials_list"),
    path(
        "raw-materials/create/", views.raw_material_create, name="raw_material_create"
    ),
    path(
        "raw-materials/<int:material_id>/",
        views.raw_material_detail,
        name="raw_material_detail",
    ),
    path(
        "raw-materials/<int:material_id>/edit/",
        views.raw_material_edit,
        name="raw_material_edit",
    ),
    # Finished Products
    path(
        "finished-products/",
        views.finished_products_list,
        name="finished_products_list",
    ),
    path(
        "finished-products/create/",
        views.finished_product_create,
        name="finished_product_create",
    ),
    path(
        "finished-products/<int:product_id>/",
        views.finished_product_detail,
        name="finished_product_detail",
    ),
    # Finished Products
    path(
        "finished-products/",
        views.finished_products_list,
        name="finished_products_list",
    ),
    path(
        "finished-products/create/",
        views.finished_product_create,
        name="finished_product_create",
    ),
    path(
        "finished-products/<int:product_id>/edit/",
        views.finished_product_edit,
        name="finished_product_edit",
    ),
    path(
        "finished-products/<int:product_id>/deactivate/",
        views.finished_product_deactivate,
        name="finished_product_deactivate",
    ),
    path(
        "finished-products/<int:product_id>/activate/",
        views.finished_product_activate,
        name="finished_product_activate",
    ),
    path(
        "finished-products/quick-create/",
        views.finished_product_quick_create,
        name="finished_product_quick_create",
    ),
    # Units
    path(
        "raw-materials/<int:material_id>/unit/",
        views.raw_material_get_unit,
        name="raw_material_get_unit",
    ),
    path(
        "raw-materials/quick-create/",
        views.raw_material_quick_create,
        name="raw_material_quick_create",
    ),
]
