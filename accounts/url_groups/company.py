from django.urls import path

from accounts.view_modules import auth_profile_company, events_meetings, onboarding


urlpatterns = [
    path("company/", auth_profile_company.company_detail, name="company_detail"),
    path("company/export/<str:export_format>/", auth_profile_company.company_export, name="company_export"),
    path("company/settings/", auth_profile_company.company_settings, name="company_settings"),
    path("company/history/", auth_profile_company.company_history, name="company_history"),
    path("events/<int:event_id>/", events_meetings.event_detail, name="event_detail"),
    path("referrals/", onboarding.my_referrals, name="my_referrals"),
]
