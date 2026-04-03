from django.contrib import admin
from .models import (
    RawMaterialStockBalance, FinishedProductStockBalance, 
    StockMovement, StockAdjustment, StockAdjustmentLine
)

@admin.register(RawMaterialStockBalance)
class RawMaterialStockBalanceAdmin(admin.ModelAdmin):
    list_display = [
        'raw_material', 'quantity', 'get_stock_status', 
        'get_stock_value', 'last_movement_date'
    ]
    list_filter = ['last_movement_date']
    search_fields = ['raw_material__designation', 'raw_material__reference']
    readonly_fields = ['quantity', 'last_movement_date', 'last_updated']
    
    def get_stock_status(self, obj):
        return obj.get_stock_status()
    get_stock_status.short_description = 'Statut'
    
    def get_stock_value(self, obj):
        value = obj.get_stock_value()
        return f"{value:,.2f} DZD"
    get_stock_value.short_description = 'Valeur stock'

@admin.register(FinishedProductStockBalance)
class FinishedProductStockBalanceAdmin(admin.ModelAdmin):
    list_display = [
        'finished_product', 'quantity', 'weighted_average_cost',
        'get_stock_value', 'last_movement_date'
    ]
    list_filter = ['last_movement_date']
    search_fields = ['finished_product__designation', 'finished_product__reference']
    readonly_fields = ['quantity', 'weighted_average_cost', 'last_movement_date', 'last_updated']
    
    def get_stock_value(self, obj):
        value = obj.get_stock_value()
        return f"{value:,.2f} DZD"
    get_stock_value.short_description = 'Valeur stock'

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        'movement_date', 'movement_type', 'get_material', 'quantity',
        'source_document_type', 'created_by', 'created_at'
    ]
    list_filter = ['movement_type', 'source_document_type', 'movement_date']
    search_fields = ['raw_material__designation', 'finished_product__designation', 'remarks']
    readonly_fields = ['created_by', 'created_at']
    
    def get_material(self, obj):
        return obj.raw_material or obj.finished_product
    get_material.short_description = 'Matériel'

class StockAdjustmentLineInline(admin.TabularInline):
    model = StockAdjustmentLine
    extra = 1
    readonly_fields = ['quantity_adjustment']

@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'adjustment_type', 'adjustment_date',
        'approved_by', 'created_by', 'created_at'
    ]
    list_filter = ['adjustment_type', 'adjustment_date']
    search_fields = ['reference', 'reason']
    readonly_fields = ['reference', 'approved_by', 'approved_at', 'created_by', 'created_at']
    inlines = [StockAdjustmentLineInline]
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)