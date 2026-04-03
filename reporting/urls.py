from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.reporting_dashboard, name='reporting_dashboard'),
    
    # Financial Reports
    path('financial-result/', views.financial_result_report, name='financial_result_report'),
    path('receivables-aging/', views.receivables_aging_report, name='receivables_aging_report'),
    path('payables-aging/', views.payables_aging_report, name='payables_aging_report'),
    
    # Operational Reports
    path('production-yield/', views.production_yield_report, name='production_yield_report'),
    path('expense-breakdown/', views.expense_breakdown_report, name='expense_breakdown_report'),
    path('stock-valuation/', views.stock_valuation_report, name='stock_valuation_report'),
    
    # Export
    path('export/<str:report_type>/csv/', views.export_report_csv, name='export_report_csv'),
    
    # AJAX endpoints
    path('kpi-dashboard/', views.kpi_dashboard_ajax, name='kpi_dashboard_ajax'),
]