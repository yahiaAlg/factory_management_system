# reporting/admin.py
from django.contrib import admin
from .models import FinancialPeriod, ReportTemplate, ReportExecution

@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'period_type', 'start_date', 'end_date', 'is_closed', 'created_by']
    list_filter = ['period_type', 'is_closed', 'start_date']
    search_fields = ['name']
    readonly_fields = ['created_by', 'created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'is_active', 'created_by', 'created_at']
    list_filter = ['report_type', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_by', 'created_at']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['template', 'execution_date', 'status', 'executed_by']
    list_filter = ['status', 'execution_date', 'template__report_type']
    search_fields = ['template__name']
    readonly_fields = ['executed_by', 'execution_date']
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.executed_by = request.user
        super().save_model(request, obj, form, change)