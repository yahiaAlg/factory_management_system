from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("company-settings/", views.company_settings, name="company_settings"),
    path("system-parameters/", views.system_parameters, name="system_parameters"),
]
