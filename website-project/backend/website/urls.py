from django.urls import path
from . import views

app_name = "website"
urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("projects/", views.projects, name="project_list"),
    path("contact/", views.contact, name="contact"),
    path("post-property/", views.post_property, name="post_property"),
    path("team/", views.team, name="team"),
    path("gallery/", views.gallery, name="gallery"),
    path("properties/", views.property_list, name="property_list"),
    path("properties/<slug:slug>/", views.property_detail, name="property_detail"),
    path(
        "properties/<slug:slug>/site-visit/",
        views.site_visit_request,
        name="site_visit_request",
    ),
    path("whatsapp-qr.svg", views.whatsapp_qr, name="whatsapp_qr"),
    path("projects/<slug:slug>/", views.project_detail, name="project_detail"),
]
