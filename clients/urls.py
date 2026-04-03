from django.urls import path
from . import views

urlpatterns = [
    path('', views.clients_list, name='clients_list'),
    path('create/', views.client_create, name='client_create'),
    path('<int:client_id>/', views.client_detail, name='client_detail'),
    path('<int:client_id>/edit/', views.client_edit, name='client_edit'),
    path('<int:client_id>/toggle-active/', views.client_toggle_active, name='client_toggle_active'),
    path('<int:client_id>/update-credit-status/', views.client_update_credit_status, name='client_update_credit_status'),
    path('search/', views.client_search_ajax, name='client_search_ajax'),
]