"""Shared public-template context."""

from django.urls import reverse

from .models import PropertyCategory, SiteSettings


def site_settings(request):
    settings = SiteSettings.objects.first()
    portal_login_url = reverse("accounts:login")
    portal_login_label = "Login"
    if settings:
        configured_url = (settings.portal_login_url or "").strip()
        if configured_url and configured_url != "#":
            portal_login_url = configured_url
        if (settings.portal_login_label or "").strip():
            portal_login_label = settings.portal_login_label.strip()
    return {
        "site_settings": settings,
        "footer_property_categories": PropertyCategory.objects.filter(is_active=True)[
            :5
        ],
        "portal_login_url": portal_login_url,
        "portal_login_label": portal_login_label,
    }
