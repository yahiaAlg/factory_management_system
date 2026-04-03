from django.urls import path
from . import views

urlpatterns = [
    # Stock Lists
    path('raw-materials/', views.raw_materials_stock_list, name='raw_materials_stock_list'),
    path('finished-products/', views.finished_products_stock_list, name='finished_products_stock_list'),
    path('movements/', views.stock_movements_list, name='stock_movements_list'),
    
    # Stock Details
    path('raw-materials/<int:material_id>/', views.raw_material_stock_detail, name='raw_material_stock_detail'),
    path('finished-products/<int:product_id>/', views.finished_product_stock_detail, name='finished_product_stock_detail'),
    
    # Stock Adjustments
    path('adjustments/', views.stock_adjustments_list, name='stock_adjustments_list'),
    path('adjustments/create/', views.stock_adjustment_create, name='stock_adjustment_create'),
    path('adjustments/<int:adjustment_id>/', views.stock_adjustment_detail, name='stock_adjustment_detail'),
    path('adjustments/<int:adjustment_id>/approve/', views.stock_adjustment_approve, name='stock_adjustment_approve'),
    
    # Alerts and Reports
    path('alerts/', views.stock_alerts_dashboard, name='stock_alerts_dashboard'),
    
    # AJAX endpoints
    path('availability-check/', views.stock_availability_ajax, name='stock_availability_ajax'),
]