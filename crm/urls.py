from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.crm_dashboard, name="dashboard"),
    path("leads/", views.lead_list, name="lead_list"),
    path("leads/kanban/", views.lead_kanban, name="lead_kanban"),
    path("leads/unassigned/", views.unassigned_leads, name="unassigned_leads"),
    path("leads/bulk-action/", views.lead_bulk_action, name="lead_bulk_action"),
    path("reports/", views.crm_reports, name="reports"),
    path("export/", views.lead_export, name="lead_export"),
    path("new/", views.lead_create, name="lead_create"),
    path("follow-ups/", views.followup_list, name="followup_list"),
    path("follow-ups/<int:followup_id>/complete/", views.followup_complete, name="followup_complete"),
    path("<int:lead_id>/", views.lead_detail, name="lead_detail"),
    path("<int:lead_id>/edit/", views.lead_edit, name="lead_edit"),
    path("<int:lead_id>/status/", views.lead_status_update, name="lead_status_update"),
    path("<int:lead_id>/follow-up/", views.lead_followup_create, name="lead_followup_create"),
    path("<int:lead_id>/assign/", views.lead_assign, name="lead_assign"),
    path("<int:lead_id>/notes/", views.lead_note_create, name="lead_note_create"),
    path("<int:lead_id>/match-property/", views.lead_property_match, name="lead_property_match"),
    path("<int:lead_id>/schedule-visit/", views.lead_visit_schedule, name="lead_visit_schedule"),
    path("meta/sources/", views.meta_source_list, name="meta_source_list"),
    path("meta/sources/new/", views.meta_source_create, name="meta_source_create"),
    path("meta/webhook/", views.meta_webhook, name="meta_webhook"),
]
