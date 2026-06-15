"""Shared public-template context."""

from .models import PropertyCategory, SiteSettings


def site_settings(request):
    return {
        "site_settings": SiteSettings.objects.first(),
        "footer_property_categories": PropertyCategory.objects.filter(is_active=True)[
            :5
        ],
    }
