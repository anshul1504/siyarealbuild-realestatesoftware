from django.urls import include, path


app_name = "accounts"

urlpatterns = [
    path("", include("accounts.url_groups.auth")),
    path("", include("accounts.url_groups.company")),
    path("", include("accounts.url_groups.team")),
    path("", include("accounts.url_groups.owner")),
]
