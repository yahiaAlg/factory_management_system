from django.contrib import admin

from .models import (
    Property,
    QualitySpecification,
    QualitySpecLine,
    SamplingPlan,
    Sample,
    TestResult,
    NonConformityReport,
)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "applies_to", "unit_label", "result_data_type", "is_active")
    list_filter = ("applies_to", "result_data_type", "is_active")
    search_fields = ("name", "test_method_reference")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class QualitySpecLineInline(admin.TabularInline):
    model = QualitySpecLine
    extra = 1


@admin.register(QualitySpecification)
class QualitySpecificationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "target", "version", "effective_date", "is_active")
    list_filter = ("is_active",)
    inlines = [QualitySpecLineInline]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SamplingPlan)
class SamplingPlanAdmin(admin.ModelAdmin):
    list_display = ("__str__", "control_point", "frequency", "is_active")
    list_filter = ("control_point", "is_active", "frequency")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class TestResultInline(admin.TabularInline):
    model = TestResult
    extra = 0
    readonly_fields = ("outcome", "recorded_by", "recorded_at")


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("reference", "control_point", "status", "sampled_by", "sampled_at")
    list_filter = ("control_point", "status")
    search_fields = ("reference",)
    inlines = [TestResultInline]
    readonly_fields = ("reference",)


@admin.register(NonConformityReport)
class NonConformityReportAdmin(admin.ModelAdmin):
    list_display = ("reference", "gate", "trigger_type", "status", "disposition", "created_at")
    list_filter = ("gate", "status", "disposition", "trigger_type")
    search_fields = ("reference", "description")
    readonly_fields = ("reference",)
