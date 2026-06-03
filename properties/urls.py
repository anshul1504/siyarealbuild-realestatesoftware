from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("properties/", views.property_list, name="list"),
    path("properties/new/", views.property_create, name="create"),
]
