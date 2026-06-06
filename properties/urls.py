from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("properties/", views.property_list, name="list"),
    path("properties/bulk-action/", views.property_bulk_action, name="bulk_action"),
    path("properties/new/", views.property_create, name="create"),
    path("properties/<int:property_id>/", views.property_detail, name="detail"),
    path("properties/<int:property_id>/edit/", views.property_edit, name="edit"),
    path("properties/<int:property_id>/share-email/", views.property_share_email, name="share_email"),
    path("properties/<int:property_id>/plots/<int:plot_id>/", views.colony_plot_detail, name="plot_detail"),
    path("properties/<int:property_id>/visits/", views.property_visit_list, name="visits"),
    path("properties/<int:property_id>/visits/new/", views.property_visit_create, name="visit_create"),
    path("properties/<int:property_id>/plots/<int:plot_id>/visits/new/", views.property_visit_create, name="plot_visit_create"),
    path("visits/<int:visit_id>/", views.property_visit_detail, name="visit_detail"),
    path("visits/<int:visit_id>/edit/", views.property_visit_edit, name="visit_edit"),
    path("visits/<int:visit_id>/delete/", views.property_visit_delete, name="visit_delete"),
]
