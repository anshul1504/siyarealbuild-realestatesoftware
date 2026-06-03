from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.request_otp, name="login"),
    path("signup/", views.signup_request, name="signup"),
    path("verify/", views.verify_otp, name="verify"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("profile/", views.profile, name="profile"),
    path("profile/verify-email/", views.verify_email_change, name="verify_email_change"),
    path("profile/resend-email-otp/", views.resend_email_change_otp, name="resend_email_change_otp"),
    path("company/", views.company_settings, name="company_settings"),
    path("invites/", views.employee_invites, name="employee_invites"),
    path("access/", views.access_control, name="access_control"),
    path("logout/", views.sign_out, name="logout"),
]
