from django.urls import path
from . import views

urlpatterns = [
    # Formulations
    path('formulations/', views.formulations_list, name='formulations_list'),
    path('formulations/create/', views.formulation_create, name='formulation_create'),
    path('formulations/<int:formulation_id>/', views.formulation_detail, name='formulation_detail'),
    path('formulations/<int:formulation_id>/edit/', views.formulation_edit, name='formulation_edit'),
    
    # Production Orders
    path('production-orders/', views.production_orders_list, name='production_orders_list'),
    path('production-orders/create/', views.production_order_create, name='production_order_create'),
    path('production-orders/<int:order_id>/', views.production_order_detail, name='production_order_detail'),
    path('production-orders/<int:order_id>/launch/', views.production_order_launch, name='production_order_launch'),
    path('production-orders/<int:order_id>/close/', views.production_order_close, name='production_order_close'),
    
    # Reports
    path('yield-report/', views.production_yield_report, name='production_yield_report'),
    
    # AJAX endpoints
    path('formulation-scaling/', views.formulation_scaling_ajax, name='formulation_scaling_ajax'),
]