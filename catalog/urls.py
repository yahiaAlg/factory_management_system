from django.urls import path
from . import views

urlpatterns = [
    # Raw Materials
    path('raw-materials/', views.raw_materials_list, name='raw_materials_list'),
    path('raw-materials/create/', views.raw_material_create, name='raw_material_create'),
    path('raw-materials/<int:material_id>/', views.raw_material_detail, name='raw_material_detail'),
    path('raw-materials/<int:material_id>/edit/', views.raw_material_edit, name='raw_material_edit'),
    
    # Finished Products
    path('finished-products/', views.finished_products_list, name='finished_products_list'),
    path('finished-products/create/', views.finished_product_create, name='finished_product_create'),
    path('finished-products/<int:product_id>/', views.finished_product_detail, name='finished_product_detail'),
    
    # AJAX endpoints
    path('check-stock-availability/', views.check_stock_availability, name='check_stock_availability'),
]