from django.urls import path

from accounts.view_modules import access_control, onboarding, team_directory


urlpatterns = [
    path("team/profiles/", team_directory.team_profiles, name="team_profiles"),
    path("team/profiles/bulk-delete/", team_directory.team_profiles_bulk_delete, name="team_profiles_bulk_delete"),
    path("team/profiles/bulk-email/", team_directory.team_profiles_bulk_email, name="team_profiles_bulk_email"),
    path("team/profiles/export/<str:export_format>/", team_directory.team_profiles_export, name="team_profiles_export"),
    path("team/profiles/<int:profile_id>/", team_directory.team_profile_detail, name="team_profile_detail"),
    path("team/profiles/<int:profile_id>/edit/", team_directory.team_profile_edit, name="team_profile_edit"),
    path("team/profiles/<int:profile_id>/history/", team_directory.team_profile_history, name="team_profile_history"),
    path("team/profiles/<int:profile_id>/documents/<str:document_type>/", team_directory.profile_document, name="profile_document"),
    path("team/profiles/bulk-update/", team_directory.team_profiles_bulk_update, name="team_profiles_bulk_update"),
    path("team/profiles/<int:profile_id>/delete/", team_directory.team_profile_delete, name="team_profile_delete"),
    path("team/emails/", team_directory.team_emails, name="team_emails"),
    path("team/emails/list/", team_directory.team_email_list, name="team_email_list"),
    path("team/emails/<int:email_id>/", team_directory.team_email_detail, name="team_email_detail"),
    path("team/add-employee/", onboarding.add_employee, name="add_employee"),
    path("team/add-employee/send-otp/", onboarding.add_employee_send_otp, name="add_employee_send_otp"),
    path("team/add-employee/verify-otp/", onboarding.add_employee_verify_otp, name="add_employee_verify_otp"),
    path("invites/", onboarding.employee_invites, name="employee_invites"),
    path("invites/list/", onboarding.employee_invite_list, name="employee_invite_list"),
    path("invites/bulk-action/", onboarding.employee_invite_bulk_action, name="employee_invite_bulk_action"),
    path("invites/<int:invite_id>/", onboarding.employee_invite_detail, name="employee_invite_detail"),
    path("invites/<int:invite_id>/edit/", onboarding.employee_invite_edit, name="employee_invite_edit"),
    path("invites/<int:invite_id>/approve/", onboarding.employee_invite_approve, name="employee_invite_approve"),
    path("invites/<int:invite_id>/resend/", onboarding.employee_invite_resend, name="employee_invite_resend"),
    path("invites/<int:invite_id>/verify-otp/", onboarding.employee_invite_verify_otp, name="employee_invite_verify_otp"),
    path("invites/<int:invite_id>/delete/", onboarding.employee_invite_delete, name="employee_invite_delete"),
    path("access/", access_control.access_control, name="access_control"),
    path("access/role-requests/", access_control.role_change_request_list, name="role_change_request_list"),
    path("access/role-requests/new/", access_control.role_change_request_create, name="role_change_request_create"),
    path("access/role-requests/<int:request_id>/", access_control.role_change_request_detail, name="role_change_request_detail"),
]
