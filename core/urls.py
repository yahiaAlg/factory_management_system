from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('company-settings/', views.company_settings, name='company_settings'),
    path('system-parameters/', views.system_parameters, name='system_parameters'),
    path('update-parameter/<int:parameter_id>/', views.update_parameter, name='update_parameter'),
]