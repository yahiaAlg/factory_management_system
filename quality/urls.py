from django.urls import path

from . import views

app_name = "quality"

urlpatterns = [
    path("dashboard/", views.quality_dashboard, name="quality_dashboard"),
    path("samples/", views.sample_register, name="sample_register"),
    path("samples/<int:sample_id>/", views.sample_detail, name="sample_detail"),
    path(
        "samples/<int:sample_id>/results/",
        views.sample_result_entry,
        name="sample_result_entry",
    ),
    path(
        "results/<int:result_id>/override/",
        views.result_qa_override,
        name="result_qa_override",
    ),
    path(
        "gate-a/dn-line/<int:dn_line_id>/draw/",
        views.gate_a_sample_draw,
        name="gate_a_sample_draw",
    ),
    path(
        "gate-bc/order/<int:order_id>/<str:gate>/draw/",
        views.gate_bc_sample_draw,
        name="gate_bc_sample_draw",
    ),
    path("ncrs/", views.ncr_list, name="ncr_list"),
    path("ncrs/<int:ncr_id>/", views.ncr_detail, name="ncr_detail"),

    # Configuration CRUD — Property / Test Catalogue
    path("config/properties/", views.property_list, name="property_list"),
    path("config/properties/new/", views.property_form, name="property_create"),
    path("config/properties/<int:property_id>/edit/", views.property_form, name="property_edit"),
    path(
        "config/properties/<int:property_id>/toggle-active/",
        views.property_toggle_active,
        name="property_toggle_active",
    ),

    # Configuration CRUD — Quality Specifications
    path("config/specifications/", views.specification_list, name="specification_list"),
    path("config/specifications/new/", views.specification_form, name="specification_create"),
    path(
        "config/specifications/<int:spec_id>/edit/",
        views.specification_form,
        name="specification_edit",
    ),
    path(
        "config/specifications/<int:spec_id>/toggle-active/",
        views.specification_toggle_active,
        name="specification_toggle_active",
    ),

    # Configuration CRUD — Sampling Plans
    path("config/sampling-plans/", views.sampling_plan_list, name="sampling_plan_list"),
    path("config/sampling-plans/new/", views.sampling_plan_form, name="sampling_plan_create"),
    path(
        "config/sampling-plans/<int:plan_id>/edit/",
        views.sampling_plan_form,
        name="sampling_plan_edit",
    ),
    path(
        "config/sampling-plans/<int:plan_id>/toggle-active/",
        views.sampling_plan_toggle_active,
        name="sampling_plan_toggle_active",
    ),
]
