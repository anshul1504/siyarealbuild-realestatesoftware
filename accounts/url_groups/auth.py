from django.urls import path

from accounts.view_modules import auth_profile_company


urlpatterns = [
    path("login/", auth_profile_company.request_otp, name="login"),
    path("signup/", auth_profile_company.signup_request, name="signup"),
    path("verify/", auth_profile_company.verify_otp, name="verify"),
    path("invite/verify/", auth_profile_company.verify_invite_email, name="verify_invite_email"),
    path("resend-otp/", auth_profile_company.resend_otp, name="resend_otp"),
    path("profile/", auth_profile_company.profile, name="profile"),
    path("profile/edit/", auth_profile_company.profile_edit, name="profile_edit"),
    path("profile/verify-email/", auth_profile_company.verify_email_change, name="verify_email_change"),
    path("profile/resend-email-otp/", auth_profile_company.resend_email_change_otp, name="resend_email_change_otp"),
    path("support-request/", auth_profile_company.authentication_support_request, name="support_request"),
    path("logout/", auth_profile_company.sign_out, name="logout"),
]
