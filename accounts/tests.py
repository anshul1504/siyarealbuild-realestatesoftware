from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from .admin import CompanyProfileAdmin
from django.test import TestCase, override_settings
from datetime import timedelta

from .forms import AddEmployeeForm, CompanyEventForm, CompanyProfileForm, SignupRequestForm, SoftwarePopupForm
from .models import AuditLog, AuthenticationSupportRequest, CompanyProfile, EmailOTP, EmployeeEmailChangeRequest, EmployeeInvite, EmployeeRoleChangeRequest, NotificationDelivery, OfficeLocation, ReferralReward, Role, RoleMatrixRule, RoleTarget, SignupRequest, SignupRequestOwnerMessage, SignupRequestStatus, SoftwarePopup, TeamEmailMessage, UserProfile


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignupApprovalEmailTests(TestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_otp_is_hashed_at_rest_and_matches_only_raw_code(self):
        otp = EmailOTP.create_for_email("secure@example.com")
        raw_code = otp.code
        otp.refresh_from_db()

        self.assertNotEqual(otp.code, raw_code)
        self.assertTrue(otp.matches(raw_code))
        self.assertFalse(otp.matches("000000"))

    @override_settings(AUTH_RATE_LIMIT_EMAIL_ATTEMPTS=1, AUTH_RATE_LIMIT_IP_ATTEMPTS=100)
    def test_login_otp_requests_are_rate_limited_by_email(self):
        User = get_user_model()
        user = User.objects.create_user(username="approved@example.com", email="approved@example.com")
        SignupRequest.objects.create(
            name="Approved",
            phone="+91 9999999999",
            email=user.email,
            approved_role=Role.EXECUTIVE,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
            user=user,
        )

        first = self.client.post(reverse("accounts:login"), {"email": user.email})
        second = self.client.post(reverse("accounts:login"), {"email": user.email})

        self.assertRedirects(first, reverse("accounts:verify"))
        self.assertRedirects(second, reverse("accounts:login"))
        self.assertEqual(EmailOTP.objects.filter(email=user.email).count(), 1)

    def test_user_can_logout_other_active_sessions(self):
        User = get_user_model()
        user = User.objects.create_user(username="approved@example.com", email="approved@example.com")
        self.client.force_login(user)
        current_session_key = self.client.session.session_key
        other_client = self.client_class()
        other_client.force_login(user)
        other_session_key = other_client.session.session_key

        response = self.client.post(reverse("accounts:logout_other_sessions"))

        self.assertRedirects(response, reverse("accounts:profile"))
        from django.contrib.sessions.models import Session
        self.assertTrue(Session.objects.filter(session_key=current_session_key).exists())
        self.assertFalse(Session.objects.filter(session_key=other_session_key).exists())

    def test_login_otp_cannot_be_used_after_approval_is_revoked(self):
        User = get_user_model()
        user = User.objects.create_user(username="approved@example.com", email="approved@example.com")
        signup = SignupRequest.objects.create(
            name="Approved User",
            phone="+91 9999999999",
            email=user.email,
            requested_role=Role.EXECUTIVE,
            approved_role=Role.EXECUTIVE,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
            user=user,
        )
        otp = EmailOTP.create_for_email(user.email, signup_request=signup)
        session = self.client.session
        session["otp_email"] = user.email
        session["otp_id"] = otp.id
        session["otp_purpose"] = "login"
        session.save()
        signup.status = SignupRequestStatus.REJECTED
        signup.save(update_fields=["status", "updated_at"])

        response = self.client.post(reverse("accounts:verify"), {"code": otp.code})

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_protected_role_pages_redirect_anonymous_users_to_login(self):
        protected_urls = [
            reverse("accounts:access_control"),
            reverse("accounts:role_change_request_list"),
            reverse("accounts:employee_invites"),
            reverse("accounts:employee_invite_list"),
        ]

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response.url)

    def test_pending_signup_cannot_change_authenticated_users_role(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        user = User.objects.create_user(username="employee@example.com", email="employee@example.com")
        profile = UserProfile.objects.create(user=user, role=Role.EXECUTIVE, company=company)
        SignupRequest.objects.create(
            name="Employee",
            phone="+91 9999999999",
            email=user.email,
            requested_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.role, Role.EXECUTIVE)

    def test_manager_invite_list_excludes_roles_outside_manager_scope(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Future Owner",
            email="future-owner@example.com",
            role=Role.COMPANY_OWNER,
        )
        visible_invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Future Executive",
            email="future-executive@example.com",
            role=Role.EXECUTIVE,
        )
        self.client.force_login(manager)

        response = self.client.get(reverse("accounts:employee_invite_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Future Owner")
        self.assertContains(response, visible_invite.name)

    def test_owner_can_edit_pending_invite_and_email_change_resets_verification(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Executive",
            email="old@example.com",
            role=Role.EXECUTIVE,
            is_email_verified=True,
            status=EmployeeInvite.Status.PENDING_APPROVAL,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:employee_invite_edit", args=[invite.id]),
            data={"name": "Updated Executive", "email": "new@example.com", "phone": "", "role": Role.EXECUTIVE, "employee_code": "SIYA-EXE-001", "note": "Updated"},
        )

        invite.refresh_from_db()
        self.assertRedirects(response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        self.assertEqual(invite.email, "new@example.com")
        self.assertFalse(invite.is_email_verified)
        self.assertEqual(invite.status, EmployeeInvite.Status.PENDING_VERIFICATION)
        self.assertTrue(EmailOTP.objects.filter(email="new@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_approved_invite_cannot_be_edited(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(company=company, invited_by=owner, name="Executive", email="exec@example.com", role=Role.EXECUTIVE, is_email_verified=True, status=EmployeeInvite.Status.APPROVED)
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:employee_invite_edit", args=[invite.id]))

        self.assertRedirects(response, reverse("accounts:employee_invite_detail", args=[invite.id]))

    def test_signup_request_sends_signup_otp_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            data={
                "name": "Anshul Sharma",
                "phone": "+91 9999999999",
                "email": "anshul@example.com",
                "requested_role": Role.MANAGER,
                "channel_partner_reference": "",
            },
        )

        self.assertRedirects(response, reverse("accounts:verify"))
        signup = SignupRequest.objects.get(email="anshul@example.com")
        self.assertEqual(signup.status, SignupRequestStatus.OTP_PENDING)
        self.assertEqual(signup.requested_role, "")
        self.assertFalse(signup.is_email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["anshul@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Verify your Siya Real Build signup")

    def test_authentication_support_request_is_saved_for_admin(self):
        response = self.client.post(
            reverse("accounts:support_request"),
            data={
                "support_name": "Anshul Sharma",
                "support_contact": "anshul@example.com",
                "support_issue": "I need help with signup approval.",
                "page_url": "/auth/signup/",
            },
        )

        self.assertEqual(response.status_code, 200)
        support_request = AuthenticationSupportRequest.objects.get()
        self.assertEqual(support_request.name, "Anshul Sharma")
        self.assertEqual(support_request.contact, "anshul@example.com")
        self.assertEqual(support_request.page_url, "/auth/signup/")

    def test_signup_otp_verification_sends_pending_review_email(self):
        self.client.post(
            reverse("accounts:signup"),
            data={
                "name": "Anshul Sharma",
                "phone": "+91 9999999999",
                "email": "anshul@example.com",
                "requested_role": Role.MANAGER,
                "channel_partner_reference": "",
            },
        )
        mail.outbox = []
        signup = SignupRequest.objects.get(email="anshul@example.com")
        otp = signup.emailotp_set.latest("created_at")
        otp.set_code("123456")

        response = self.client.post(reverse("accounts:verify"), data={"code": "123456"})

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["anshul@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build signup request is under review")
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupRequestStatus.PENDING_APPROVAL)

    def test_approval_sends_confirmation_and_welcome_emails(self):
        signup = SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
            approved_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )

        signup.approve()

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["anshul@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build signup request is approved")
        self.assertEqual(mail.outbox[1].to, ["anshul@example.com"])
        self.assertEqual(mail.outbox[1].subject, "Welcome to Siya Real Build")
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupRequestStatus.APPROVED)
        self.assertIsNotNone(signup.user)

    def test_repeat_approval_does_not_send_duplicate_emails(self):
        signup = SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
            approved_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        signup.approve()
        mail.outbox = []

        signup.approve()

        self.assertEqual(len(mail.outbox), 0)

    def test_rejection_sends_rejection_email_once(self):
        signup = SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
            admin_note="Company details could not be verified.",
        )

        signup.reject()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["anshul@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build signup request was rejected")
        self.assertIn("Company details could not be verified.", mail.outbox[0].body)

        mail.outbox = []
        signup.reject()
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_form_rejects_duplicate_email(self):
        SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        form = SignupRequestForm(
            data={
                "name": "Another User",
                "phone": "8888888888",
                "email": "anshul@example.com",
                "requested_role": Role.EXECUTIVE,
                "channel_partner_reference": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_signup_form_allows_unverified_otp_pending_email_retry(self):
        SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="+91 9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
            status=SignupRequestStatus.OTP_PENDING,
            is_email_verified=False,
        )
        form = SignupRequestForm(
            data={
                "name": "Anshul Sharma",
                "phone": "+91 8888888888",
                "email": "anshul@example.com",
                "requested_role": Role.EXECUTIVE,
                "channel_partner_reference": "",
            }
        )

        self.assertTrue(form.is_valid())

    def test_company_details_are_shared_and_read_only_for_non_owner(self):
        User = get_user_model()
        user = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        UserProfile.objects.create(user=user, role=Role.MANAGER)
        company = CompanyProfile.objects.create(
            name="Siya Real Build Pvt. Ltd.",
            phone="+91 9999999999",
            email="company@example.com",
            gst_number="GST123",
            rera_number="RERA123",
            city="Indore",
            state="Madhya Pradesh",
        )

        self.client.force_login(user)
        response = self.client.get(reverse("accounts:company_detail"))

        self.assertContains(response, "Siya Real Build Pvt. Ltd.")
        self.assertNotContains(response, "GST123")
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.company, company)

        response = self.client.post(reverse("accounts:company_settings"), data={"company-name": "Changed"})
        self.assertRedirects(response, reverse("accounts:company_detail"))
        company.refresh_from_db()
        self.assertEqual(company.name, "Siya Real Build Pvt. Ltd.")

    def test_non_owner_company_view_and_export_hide_sensitive_details(self):
        User = get_user_model()
        user = User.objects.create_user(username="executive@example.com", email="executive@example.com")
        company = CompanyProfile.objects.create(
            name="Siya Real Build",
            email="company@example.com",
            gst_number="23ABCDE1234F1Z5",
            pan_number="ABCDE1234F",
            bank_account_number="123456789012",
            bank_ifsc="HDFC0123456",
        )
        UserProfile.objects.create(user=user, role=Role.EXECUTIVE, company=company)
        self.client.force_login(user)

        detail = self.client.get(reverse("accounts:company_detail"))
        export = self.client.get(reverse("accounts:company_export", args=["csv"]))

        self.assertNotContains(detail, "123456789012")
        self.assertNotContains(detail, "ABCDE1234F")
        self.assertNotContains(export, "123456789012")
        self.assertNotContains(export, "HDFC0123456")
        self.assertContains(export, "Siya Real Build")

    def test_company_overview_lists_active_office_locations(self):
        User = get_user_model()
        user = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        company = CompanyProfile.objects.create(name="Siya Real Build", email="company@example.com")
        UserProfile.objects.create(user=user, role=Role.MANAGER, company=company)
        OfficeLocation.objects.create(company=company, name="Head Office", city="Indore", is_active=True)
        OfficeLocation.objects.create(company=company, name="Closed Office", city="Bhopal", is_active=False)
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:company_detail"))

        self.assertContains(response, "Head Office")
        self.assertNotContains(response, "Closed Office")

    def test_authenticated_user_can_export_company_details(self):
        User = get_user_model()
        user = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        company = CompanyProfile.objects.create(
            name="Siya Real Build Pvt. Ltd.",
            email="company@example.com",
            gst_number="GST123",
            bank_ifsc="HDFC0123456",
            weekly_off_days="Sunday",
            holiday_notes="Diwali closed",
        )
        UserProfile.objects.create(user=user, role=Role.COMPANY_OWNER, company=company)
        self.client.force_login(user)

        csv_response = self.client.get(reverse("accounts:company_export", args=["csv"]))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn('filename="company-details.csv"', csv_response["Content-Disposition"])
        self.assertContains(csv_response, "Siya Real Build Pvt. Ltd.")
        self.assertContains(csv_response, "GST123")

        excel_response = self.client.get(reverse("accounts:company_export", args=["xls"]))
        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(excel_response["Content-Type"], "application/vnd.ms-excel")
        self.assertIn('filename="company-details.xls"', excel_response["Content-Disposition"])
        self.assertContains(excel_response, "HDFC0123456")
        self.assertContains(excel_response, "Sunday")

    def test_company_owner_can_update_company_master_details(self):
        User = get_user_model()
        user = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        company = CompanyProfile.objects.create(name="Old Company", email="old@example.com")
        UserProfile.objects.create(user=user, role=Role.COMPANY_OWNER, company=company)

        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:company_settings"),
            data={
                "company-name": "Siya Real Build Pvt. Ltd.",
                "company-tagline": "Real estate growth platform",
                "company-description": "Company profile",
                "company-phone": "+91 9999999999",
                "company-phone_2": "",
                "company-phone_3": "",
                "company-email": "info@siyarealbuild.com",
                "company-email_2": "",
                "company-email_3": "",
                "company-website": "siyarealbuild.com",
                "company-gst_number": "23ABCDE1234F1Z5",
                "company-rera_number": "RERA123",
                "company-cin_number": "",
                "company-pan_number": "ABCDE1234F",
                "company-bank_name": "HDFC Bank",
                "company-bank_account_name": "Siya Real Build Pvt Ltd",
                "company-bank_account_number": "123456789012",
                "company-bank_ifsc": "HDFC0123456",
                "company-upi_id": "siya@hdfc",
                "company-opening_time": "10:00",
                "company-closing_time": "19:00",
                "company-weekly_off_days": "Sunday",
                "company-holiday_notes": "National holidays closed",
                "company-address": "Main Road",
                "company-city": "Indore",
                "company-state": "Madhya Pradesh",
                "company-pincode": "452001",
            },
        )

        self.assertRedirects(response, reverse("accounts:company_settings"))
        company.refresh_from_db()
        self.assertEqual(company.name, "Siya Real Build Pvt. Ltd.")
        self.assertEqual(company.website, "https://siyarealbuild.com")
        self.assertEqual(company.gst_number, "23ABCDE1234F1Z5")
        self.assertEqual(company.pan_number, "ABCDE1234F")
        self.assertEqual(company.bank_ifsc, "HDFC0123456")
        self.assertEqual(company.opening_time.strftime("%H:%M"), "10:00")
        self.assertEqual(company.closing_time.strftime("%H:%M"), "19:00")
        self.assertEqual(company.weekly_off_days, "Sunday")
        audit = AuditLog.objects.get(action="company.updated", company=company)
        self.assertEqual(audit.actor, user)
        self.assertIn("name", audit.details)

        history = self.client.get(reverse("accounts:company_history"))
        self.assertContains(history, "Company Change History")
        self.assertContains(history, "company.updated")

    def test_non_owner_cannot_view_company_history(self):
        User = get_user_model()
        user = User.objects.create_user(username="executive@example.com", email="executive@example.com")
        company = CompanyProfile.objects.create(name="Siya Real Build", email="company@example.com")
        UserProfile.objects.create(user=user, role=Role.EXECUTIVE, company=company)
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:company_history"))

        self.assertRedirects(response, reverse("accounts:company_detail"))

    def test_company_form_rejects_duplicate_contacts_and_invalid_schedule(self):
        form = CompanyProfileForm(
            data={
                "name": "Siya Real Build",
                "email": "same@example.com",
                "email_2": "same@example.com",
                "phone": "+91 9999999999",
                "phone_2": "+91 9999999999",
                "opening_time": "19:00",
                "closing_time": "10:00",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("closing_time", form.errors)
        self.assertIn("__all__", form.errors)

    def test_user_can_update_full_profile_details(self):
        User = get_user_model()
        user = User.objects.create_user(username="executive@example.com", email="executive@example.com")
        profile = UserProfile.objects.create(user=user, role=Role.EXECUTIVE)
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:profile_edit"),
            data={
                "profile-full_name": "Amit Verma",
                "profile-email": "executive@example.com",
                "profile-phone": "+91 9999999999",
                "profile-designation": "Sales Executive",
                "profile-date_of_birth": "1995-05-12",
                "profile-gender": UserProfile.Gender.MALE,
                "profile-blood_group": "B+",
                "profile-marital_status": UserProfile.MaritalStatus.SINGLE,
                "profile-personal_email": "amit.personal@example.com",
                "profile-aadhaar_number": "1234 5678 9012",
                "profile-pan_number": "ABCDE1234F",
                "profile-emergency_contact_name": "Ravi Verma",
                "profile-emergency_contact_phone": "+91 8888888888",
                "profile-department": "Sales",
                "profile-reporting_manager": "Team Lead",
                "profile-joining_date": "2026-01-01",
                "profile-work_location": "Indore Office",
                "profile-territory": "Indore East",
                "profile-channel_partner_reference": "",
                "profile-bank_name": "HDFC Bank",
                "profile-bank_account_name": "Amit Verma",
                "profile-bank_account_number": "123456789012",
                "profile-bank_ifsc": "HDFC0123456",
                "profile-address": "Main Road",
                "profile-city": "Indore",
                "profile-state": "Madhya Pradesh",
                "profile-pincode": "452001",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile"))
        profile.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(user.get_full_name(), "Amit Verma")
        self.assertEqual(profile.aadhaar_number, "123456789012")
        self.assertEqual(profile.pan_number, "ABCDE1234F")
        self.assertEqual(profile.department, "")
        self.assertEqual(profile.bank_ifsc, "HDFC0123456")
        self.assertEqual(profile.emergency_contact_phone, "+91 8888888888")
        self.assertTrue(profile.change_history.filter(changed_by=user).exists())

    def test_self_profile_edit_cannot_change_official_work_fields(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        user = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        profile = UserProfile.objects.create(user=user, role=Role.EXECUTIVE, company=company, department="Sales", designation="Executive")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:profile_edit"),
            data={"profile-full_name": "Executive User", "profile-email": user.email, "profile-department": "Finance", "profile-designation": "Manager"},
        )

        self.assertRedirects(response, reverse("accounts:profile"))
        profile.refresh_from_db()
        self.assertEqual(profile.department, "Sales")
        self.assertEqual(profile.designation, "Executive")

    def test_manager_employee_detail_hides_private_bank_and_address_data(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        employee = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        profile = UserProfile.objects.create(
            user=employee, role=Role.EXECUTIVE, company=company, bank_account_number="123456789012",
            address="Private Address", personal_email="private@example.com", reporting_manager="manager@example.com",
        )
        self.client.force_login(manager)

        response = self.client.get(reverse("accounts:team_profile_detail", args=[profile.id]))

        self.assertNotContains(response, "123456789012")
        self.assertNotContains(response, "Private Address")
        self.assertNotContains(response, "private@example.com")
        self.assertContains(response, "Owner only")

    def test_owner_employee_edit_records_real_change_history(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        employee = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        profile = UserProfile.objects.create(user=employee, role=Role.EXECUTIVE, company=company, department="Sales")
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:team_profile_edit", args=[profile.id]),
            data={"full_name": "Executive User", "email": employee.email, "department": "Operations"},
        )

        self.assertRedirects(response, reverse("accounts:team_profile_detail", args=[profile.id]))
        change = profile.change_history.get()
        self.assertEqual(change.changes["department"]["from"], "Sales")
        self.assertEqual(change.changes["department"]["to"], "Operations")
        history = self.client.get(reverse("accounts:team_profile_history", args=[profile.id]))
        self.assertContains(history, "Operations")

    def test_profile_documents_are_available_only_to_self_or_owner(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        employee = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        profile = UserProfile.objects.create(user=employee, role=Role.EXECUTIVE, company=company)
        profile.aadhaar_document.save("aadhaar.pdf", ContentFile(b"private-document"), save=True)

        self.client.force_login(manager)
        denied = self.client.get(reverse("accounts:profile_document", args=[profile.id, "aadhaar"]))
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(owner)
        allowed = self.client.get(reverse("accounts:profile_document", args=[profile.id, "aadhaar"]))
        self.assertEqual(allowed.status_code, 200)

    def test_any_role_email_change_creates_request_and_updates_after_otp(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        user = User.objects.create_user(username="executive@example.com", email="executive@example.com", first_name="Amit")
        UserProfile.objects.create(user=user, role=Role.EXECUTIVE, company=company)
        SignupRequest.objects.create(
            name="Amit",
            phone="+91 9999999999",
            email="executive@example.com",
            requested_role=Role.EXECUTIVE,
            approved_role=Role.EXECUTIVE,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
            user=user,
        )
        self.client.force_login(user)
        mail.outbox = []

        response = self.client.post(
            reverse("accounts:profile_edit"),
            data={
                "profile-full_name": "Amit Verma",
                "profile-email": "new-executive@example.com",
                "profile-phone": "+91 9999999999",
                "profile-designation": "Sales Executive",
                "profile-date_of_birth": "",
                "profile-gender": "",
                "profile-blood_group": "",
                "profile-marital_status": "",
                "profile-personal_email": "",
                "profile-aadhaar_number": "",
                "profile-pan_number": "",
                "profile-emergency_contact_name": "",
                "profile-emergency_contact_phone": "",
                "profile-department": "",
                "profile-reporting_manager": "",
                "profile-joining_date": "",
                "profile-work_location": "",
                "profile-territory": "",
                "profile-channel_partner_reference": "",
                "profile-bank_name": "",
                "profile-bank_account_name": "",
                "profile-bank_account_number": "",
                "profile-bank_ifsc": "",
                "profile-address": "",
                "profile-city": "",
                "profile-state": "",
                "profile-pincode": "",
            },
        )

        self.assertRedirects(response, reverse("accounts:verify_email_change"))
        change = EmployeeEmailChangeRequest.objects.get(employee=user)
        self.assertEqual(change.requested_email, "new-executive@example.com")
        self.assertFalse(change.is_email_verified)
        user.refresh_from_db()
        self.assertEqual(user.email, "executive@example.com")
        self.assertEqual(mail.outbox[0].subject, "Verify your new Siya Real Build email")

        otp = EmailOTP.objects.get(email="new-executive@example.com")
        otp.set_code("123456")
        mail.outbox = []
        response = self.client.post(reverse("accounts:verify_email_change"), data={"code": "123456"})

        self.assertRedirects(response, reverse("accounts:profile"))
        user.refresh_from_db()
        change.refresh_from_db()
        signup = SignupRequest.objects.get(user=user)
        self.assertEqual(user.email, "new-executive@example.com")
        self.assertEqual(user.username, "new-executive@example.com")
        self.assertEqual(signup.email, "new-executive@example.com")
        self.assertTrue(change.is_email_verified)
        self.assertEqual(change.status, EmployeeEmailChangeRequest.Status.APPROVED)
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build email has been updated")

    def test_owner_manual_email_change_requires_otp_before_update(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        employee = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=employee, role=Role.EXECUTIVE, company=company)
        self.client.force_login(owner)
        mail.outbox = []

        response = self.client.post(
            reverse("accounts:owner_email_change_create"),
            data={
                "emailchange-employee": employee.id,
                "emailchange-requested_email": "manual-exec@example.com",
                "emailchange-reason": "Employee requested by phone.",
            },
        )

        self.assertRedirects(response, reverse("accounts:owner_email_changes"))
        change = EmployeeEmailChangeRequest.objects.get(employee=employee)
        self.assertEqual(change.requested_by, owner)
        self.assertFalse(change.is_email_verified)
        self.assertEqual(mail.outbox[0].subject, "Verify your new Siya Real Build email")

        response = self.client.post(reverse("accounts:owner_email_changes"), data={"approve_request": change.id})

        self.assertRedirects(response, reverse("accounts:owner_email_changes"))
        employee.refresh_from_db()
        self.assertEqual(employee.email, "exec@example.com")

        otp = EmailOTP.objects.get(email="manual-exec@example.com")
        otp.set_code("123456")
        mail.outbox = []
        response = self.client.post(
            reverse("accounts:owner_email_changes"),
            data={"verify_request": change.id, "otp_code": "123456"},
        )

        self.assertRedirects(response, reverse("accounts:owner_email_changes"))
        employee.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(employee.email, "exec@example.com")
        self.assertTrue(change.is_email_verified)
        self.assertEqual(change.status, EmployeeEmailChangeRequest.Status.PENDING)

        response = self.client.post(reverse("accounts:owner_email_changes"), data={"approve_request": change.id})

        self.assertRedirects(response, reverse("accounts:owner_email_changes"))
        employee.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(employee.email, "manual-exec@example.com")
        self.assertEqual(employee.username, "manual-exec@example.com")
        self.assertTrue(change.is_email_verified)
        self.assertEqual(change.status, EmployeeEmailChangeRequest.Status.APPROVED)
        self.assertEqual(change.approved_by, owner)
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build email has been updated")
        self.assertIn("New email: manual-exec@example.com", mail.outbox[0].body)

    def test_owner_email_change_list_filters_and_searches_requests(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com", first_name="Manager")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company, employee_code="MGR-0001")
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, employee_code="EXE-0001")
        EmployeeEmailChangeRequest.objects.create(
            company=company,
            employee=manager,
            requested_by=owner,
            requested_email="new-manager@example.com",
            is_email_verified=True,
        )
        EmployeeEmailChangeRequest.objects.create(
            company=company,
            employee=executive,
            requested_by=owner,
            requested_email="new-exec@example.com",
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_email_changes"), data={"q": "MGR-0001", "otp": "verified"})

        self.assertContains(response, "new-manager@example.com")
        self.assertNotContains(response, "new-exec@example.com")
        self.assertContains(response, "New Email Change Request")

    def test_supervisor_can_view_allowed_employee_profiles_with_masked_ids(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", first_name="Owner")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, aadhaar_number="123456789012", pan_number="ABCDE1234F", reporting_manager="manager@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        self.client.force_login(manager)

        response = self.client.get(reverse("accounts:team_profiles"))

        self.assertContains(response, "Executive")
        self.assertContains(response, "XXXX XXXX 9012")
        self.assertContains(response, "ABCXXXXF")
        self.assertContains(response, "Owner only")
        self.assertNotContains(response, "123456789012")
        self.assertNotContains(response, "owner@example.com")

    def test_manager_directory_is_limited_to_assigned_team(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        assigned = User.objects.create_user(username="assigned@example.com", email="assigned@example.com", first_name="Assigned")
        unassigned = User.objects.create_user(username="unassigned@example.com", email="unassigned@example.com", first_name="Unassigned")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company, employee_code="SIYA-MGR-001")
        UserProfile.objects.create(user=assigned, role=Role.EXECUTIVE, company=company, reporting_manager="SIYA-MGR-001")
        UserProfile.objects.create(user=unassigned, role=Role.EXECUTIVE, company=company)
        self.client.force_login(manager)

        response = self.client.get(reverse("accounts:team_profiles"))

        self.assertContains(response, "Assigned")
        self.assertNotContains(response, "Unassigned")

    def test_role_matrix_can_block_team_directory_view(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        RoleMatrixRule.objects.create(company=company, role=Role.MANAGER, module="team_management", can_view=False)
        self.client.force_login(manager)

        response = self.client.get(reverse("accounts:team_profiles"))

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_operations_dashboard_renders_owner_summary(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        AuthenticationSupportRequest.objects.create(name="Client", contact="client@example.com", issue="Need help")
        RoleTarget.objects.create(company=company, assigned_by=owner, role=Role.EXECUTIVE, title="Lead Target", target_value=10, metric="Leads", starts_on=timezone.localdate(), ends_on=timezone.localdate())
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_operations_dashboard"))

        self.assertContains(response, "Operations Dashboard")
        self.assertContains(response, "Open Support")
        self.assertContains(response, "Active Targets")

    def test_owner_core_checklist_renders_all_image_items(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_core_checklist"))

        self.assertContains(response, "Core Checklist")
        self.assertContains(response, "Pending</span><strong>0")
        self.assertContains(response, "Company detail add/edit")
        self.assertContains(response, "Coupon during booking")
        self.assertContains(response, "Role matrix manage")
        self.assertContains(response, "Change employee email")

    def test_support_status_update_records_note_and_audit(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        support = AuthenticationSupportRequest.objects.create(name="Client", contact="client@example.com", issue="Need help")
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:owner_support"), data={"support_id": support.id, "status": "resolved", "owner_note": "Called and closed."})

        self.assertRedirects(response, reverse("accounts:owner_support"))
        support.refresh_from_db()
        self.assertTrue(support.is_resolved)
        self.assertEqual(support.owner_note, "Called and closed.")
        self.assertIsNotNone(support.resolved_at)
        self.assertTrue(AuditLog.objects.filter(action="operations.support_updated").exists())

    def test_operations_support_list_is_scoped_to_company_users(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        other_company = CompanyProfile.objects.create(name="Other Company", singleton_key=False)
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        employee = User.objects.create_user(username="employee@example.com", email="employee@example.com")
        other_employee = User.objects.create_user(username="other@example.com", email="other@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=employee, role=Role.EXECUTIVE, company=company)
        UserProfile.objects.create(user=other_employee, role=Role.EXECUTIVE, company=other_company)
        AuthenticationSupportRequest.objects.create(name="Visible", contact=employee.email, issue="Need help")
        AuthenticationSupportRequest.objects.create(name="Hidden", contact=other_employee.email, issue="Other help")
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_support"))

        self.assertContains(response, "Visible")
        self.assertNotContains(response, "Hidden")

    def test_administration_sidebar_and_support_pagination_render(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        for index in range(18):
            AuthenticationSupportRequest.objects.create(name=f"Client {index}", contact=f"client{index}@example.com", issue="Need help")
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_support"))

        self.assertContains(response, "Administration")
        self.assertContains(response, "Support Desk")
        self.assertContains(response, "Page 1 of 2")

    def test_meeting_create_records_delivery_and_audit(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:owner_meeting_create"),
            data={
                "meeting-title": "Sales Review",
                "meeting-description": "Weekly review",
                "meeting-starts_at": "2026-06-12T10:00",
                "meeting-ends_at": "2026-06-12T11:00",
                "meeting-roles": [Role.EXECUTIVE],
                "meeting-meeting_link": "https://meet.example.com/sales",
                "meeting-is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("accounts:owner_meetings"))
        self.assertTrue(AuditLog.objects.filter(action="operations.meeting_created").exists())
        self.assertTrue(NotificationDelivery.objects.filter(category="meeting", recipient="exec@example.com", status=NotificationDelivery.Status.SENT).exists())

    def test_target_detail_updates_progress_and_audit(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        target = RoleTarget.objects.create(company=company, assigned_by=owner, role=Role.EXECUTIVE, title="Lead Target", target_value=20, metric="Leads", starts_on=timezone.localdate(), ends_on=timezone.localdate())
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:owner_target_detail", args=[target.id]), data={"current_value": "12", "status": RoleTarget.Status.ACTIVE, "note": "On track"})

        self.assertRedirects(response, reverse("accounts:owner_target_detail", args=[target.id]))
        target.refresh_from_db()
        self.assertEqual(target.current_value, 12)
        self.assertEqual(target.progress_percent, 60)
        self.assertTrue(AuditLog.objects.filter(action="operations.target_progress_updated").exists())

    def test_company_owner_can_view_full_employee_profile_ids(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", first_name="Owner")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, aadhaar_number="123456789012", pan_number="ABCDE1234F")
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:team_profiles"))

        self.assertContains(response, "123456789012")
        self.assertContains(response, "ABCDE1234F")

    def test_direct_add_employee_does_not_allow_company_owner_role(self):
        form = AddEmployeeForm(
            data={
                "name": "Second Owner",
                "email": "second-owner@example.com",
                "phone": "",
                "role": Role.COMPANY_OWNER,
                "employee_code": "",
                "personal_email": "",
                "gender": "",
                "blood_group": "",
                "marital_status": "",
                "designation": "",
                "department": "",
                "reporting_manager": "",
                "office_location": "",
                "custom_work_location": "",
                "aadhaar_number": "",
                "pan_number": "",
                "emergency_contact_name": "",
                "emergency_contact_phone": "",
                "bank_name": "",
                "bank_account_name": "",
                "bank_account_number": "",
                "bank_ifsc": "",
                "address": "",
                "city": "",
                "state": "",
                "pincode": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("role", form.errors)

    def test_add_employee_rejects_legacy_employee_code_format(self):
        company = CompanyProfile.objects.create(name="Siya Real Build")
        form = AddEmployeeForm(
            data={
                "name": "Executive",
                "email": "exec@example.com",
                "phone": "+91 9999999999",
                "role": Role.EXECUTIVE,
                "employee_code": "EXE-0001",
            },
            company=company,
            allowed_roles={Role.EXECUTIVE},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employee_code", form.errors)

    def test_owner_can_request_and_approve_employee_role_change(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", first_name="Owner")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        executive_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, employee_code="EXE-0001")
        self.client.force_login(owner)
        mail.outbox = []

        response = self.client.post(
            reverse("accounts:role_change_request_create"),
            data={
                "rolechange-employee": executive.id,
                "rolechange-requested_role": Role.TL,
                "rolechange-reason": "Promoted to team lead.",
            },
        )

        change = EmployeeRoleChangeRequest.objects.get(employee=executive)
        self.assertRedirects(response, reverse("accounts:role_change_request_detail", args=[change.id]))
        self.assertEqual(change.current_role, Role.EXECUTIVE)
        self.assertEqual(change.requested_role, Role.TL)
        self.assertEqual(mail.outbox[0].subject, "Your Siya Real Build role change request is under review")

        response = self.client.post(
            reverse("accounts:role_change_request_detail", args=[change.id]),
            data={"action": "approve", "review_note": "Approved for new responsibility."},
        )

        self.assertRedirects(response, reverse("accounts:role_change_request_detail", args=[change.id]))
        executive_profile.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(executive_profile.role, Role.TL)
        self.assertEqual(change.status, EmployeeRoleChangeRequest.Status.APPROVED)
        self.assertEqual(change.reviewed_by, owner)
        self.assertEqual(mail.outbox[-1].subject, "Your Siya Real Build role has been updated")

    def test_role_change_request_list_and_detail_render(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, employee_code="EXE-0001")
        change = EmployeeRoleChangeRequest.objects.create(
            company=company,
            employee=executive,
            current_role=Role.EXECUTIVE,
            requested_role=Role.MANAGER,
            requested_by=owner,
            reason="Leadership move.",
        )
        self.client.force_login(owner)

        list_response = self.client.get(reverse("accounts:role_change_request_list"), data={"q": "EXE-0001", "status": "pending"})
        detail_response = self.client.get(reverse("accounts:role_change_request_detail", args=[change.id]))

        self.assertContains(list_response, "Executive to Manager")
        self.assertContains(detail_response, "Leadership move.")

    def test_company_owner_can_delete_employee_from_directory(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", first_name="Owner")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        employee_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:team_profile_delete", args=[employee_profile.id]))

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertFalse(User.objects.filter(email="exec@example.com").exists())
        self.assertFalse(UserProfile.objects.filter(id=employee_profile.id).exists())

    def test_employee_delete_removes_signup_invite_and_email_references(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", first_name="Owner")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        employee_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        signup = SignupRequest.objects.create(
            name="Executive",
            phone="+91 9999999999",
            email="exec@example.com",
            requested_role=Role.EXECUTIVE,
            approved_role=Role.EXECUTIVE,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
            user=executive,
        )
        SignupRequestOwnerMessage.objects.create(signup_request=signup, sent_by=owner, subject="Note", message="Old note")
        EmailOTP.create_for_email("exec@example.com", signup_request=signup)
        EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Executive",
            email="exec@example.com",
            role=Role.EXECUTIVE,
            accepted_user=executive,
            status=EmployeeInvite.Status.APPROVED,
            is_email_verified=True,
        )
        EmployeeEmailChangeRequest.objects.create(company=company, employee=executive, requested_email="new-exec@example.com")
        team_email = TeamEmailMessage.objects.create(
            company=company,
            sent_by=owner,
            subject="Team",
            message="Message",
            recipients=[
                {"name": "Executive", "email": "exec@example.com", "role": "Executive", "department": ""},
                {"name": "Other", "email": "other@example.com", "role": "Executive", "department": ""},
            ],
            sent_count=2,
        )
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:team_profile_delete", args=[employee_profile.id]))

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertFalse(User.objects.filter(email="exec@example.com").exists())
        self.assertFalse(SignupRequest.objects.filter(email="exec@example.com").exists())
        self.assertFalse(SignupRequestOwnerMessage.objects.filter(signup_request=signup).exists())
        self.assertFalse(EmailOTP.objects.filter(email="exec@example.com").exists())
        self.assertFalse(EmployeeInvite.objects.filter(email="exec@example.com").exists())
        self.assertFalse(EmployeeEmailChangeRequest.objects.filter(employee=executive).exists())
        team_email.refresh_from_db()
        self.assertEqual(team_email.sent_count, 1)
        self.assertEqual(team_email.recipients[0]["email"], "other@example.com")

    def test_supervisor_cannot_delete_employee_from_directory(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        employee_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        self.client.force_login(manager)

        response = self.client.post(reverse("accounts:team_profile_delete", args=[employee_profile.id]))

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertTrue(User.objects.filter(email="exec@example.com").exists())
        self.assertTrue(UserProfile.objects.filter(id=employee_profile.id).exists())

    def test_company_owner_can_bulk_delete_employees_from_directory(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        tl = User.objects.create_user(username="tl@example.com", email="tl@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        executive_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        tl_profile = UserProfile.objects.create(user=tl, role=Role.TL, company=company)
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:team_profiles_bulk_delete"),
            data={"profile_ids": [str(executive_profile.id), str(tl_profile.id)]},
        )

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertFalse(User.objects.filter(email="exec@example.com").exists())
        self.assertFalse(User.objects.filter(email="tl@example.com").exists())
        self.assertFalse(UserProfile.objects.filter(id__in=[executive_profile.id, tl_profile.id]).exists())

    def test_bulk_employee_delete_removes_signup_and_invite_records(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        tl = User.objects.create_user(username="tl@example.com", email="tl@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        executive_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        tl_profile = UserProfile.objects.create(user=tl, role=Role.TL, company=company)
        SignupRequest.objects.create(name="Executive", phone="+91 9999999999", email="exec@example.com", requested_role=Role.EXECUTIVE, status=SignupRequestStatus.APPROVED, is_email_verified=True, user=executive)
        SignupRequest.objects.create(name="TL", phone="+91 8888888888", email="tl@example.com", requested_role=Role.TL, status=SignupRequestStatus.APPROVED, is_email_verified=True, user=tl)
        EmployeeInvite.objects.create(company=company, invited_by=owner, name="Executive", email="exec@example.com", role=Role.EXECUTIVE, accepted_user=executive, status=EmployeeInvite.Status.APPROVED, is_email_verified=True)
        EmployeeInvite.objects.create(company=company, invited_by=owner, name="TL", email="tl@example.com", role=Role.TL, accepted_user=tl, status=EmployeeInvite.Status.APPROVED, is_email_verified=True)
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:team_profiles_bulk_delete"),
            data={"profile_ids": [str(executive_profile.id), str(tl_profile.id)]},
        )

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertFalse(SignupRequest.objects.filter(email__in=["exec@example.com", "tl@example.com"]).exists())
        self.assertFalse(EmployeeInvite.objects.filter(email__in=["exec@example.com", "tl@example.com"]).exists())

    def test_supervisor_cannot_bulk_delete_employees_from_directory(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        employee_profile = UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        self.client.force_login(manager)

        response = self.client.post(reverse("accounts:team_profiles_bulk_delete"), data={"profile_ids": [str(employee_profile.id)]})

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertTrue(User.objects.filter(email="exec@example.com").exists())
        self.assertTrue(UserProfile.objects.filter(id=employee_profile.id).exists())

    def test_owner_can_send_bulk_employee_email_by_role(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:team_profiles_bulk_email"),
            data={"role": Role.EXECUTIVE, "department": "", "subject": "Team Update", "message": "Please check dashboard."},
        )

        self.assertRedirects(response, reverse("accounts:team_profiles"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["exec@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Team Update")

    def test_team_email_page_sends_and_records_email_history(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company, department="Sales")
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:team_emails"),
            data={"role": Role.EXECUTIVE, "department": "Sales", "subject": "Sales Update", "message": "Follow up today."},
        )

        team_email = TeamEmailMessage.objects.get(subject="Sales Update")
        self.assertRedirects(response, reverse("accounts:team_email_detail", args=[team_email.id]))
        self.assertEqual(team_email.sent_count, 1)
        self.assertEqual(team_email.recipients[0]["email"], "exec@example.com")
        self.assertTrue(NotificationDelivery.objects.filter(category="team_email", recipient="exec@example.com", status=NotificationDelivery.Status.SENT).exists())

    def test_team_email_records_per_recipient_delivery_failure(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        executive = User.objects.create_user(username="exec@example.com", email="exec@example.com", first_name="Executive")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=company)
        self.client.force_login(owner)

        with patch("accounts.view_modules.team_directory.send_employee_custom_email", side_effect=RuntimeError("smtp failed")):
            response = self.client.post(
                reverse("accounts:team_emails"),
                data={"role": Role.EXECUTIVE, "department": "", "subject": "Sales Update", "message": "Please review."},
            )

        team_email = TeamEmailMessage.objects.get(subject="Sales Update")
        self.assertRedirects(response, reverse("accounts:team_email_detail", args=[team_email.id]))
        self.assertEqual(team_email.recipients[0]["status"], NotificationDelivery.Status.FAILED)
        self.assertTrue(NotificationDelivery.objects.filter(category="team_email", recipient="exec@example.com", status=NotificationDelivery.Status.FAILED).exists())

        detail_response = self.client.get(reverse("accounts:team_email_detail", args=[team_email.id]))
        self.assertContains(detail_response, "Sales Update")
        self.assertContains(detail_response, "exec@example.com")

    def test_company_owner_bulk_queue_does_not_offer_approval_without_role_assignment(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="Approved User",
            phone="+91 9999999999",
            email="approved@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_requests"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<option value="approve">Approve</option>', html=True)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupRequestStatus.PENDING_APPROVAL)

    def test_company_owner_cannot_approve_unverified_signup_request(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="OTP Pending User",
            phone="+91 9999999999",
            email="otp@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.OTP_PENDING,
            is_email_verified=False,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:owner_requests"),
            data={
                "form_kind": "signup",
                "signup-action": "approve",
                "signup-signup_ids": [str(signup.id)],
            },
        )

        self.assertEqual(response.status_code, 200)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupRequestStatus.OTP_PENDING)
        self.assertFalse(User.objects.filter(email="otp@example.com").exists())

    def test_invite_email_verification_waits_for_owner_approval(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Invite User",
            email="invite@example.com",
            role=Role.EXECUTIVE,
            employee_code="SIYA-EXE-007",
        )
        otp = EmailOTP.create_for_email(invite.email)

        response = self.client.post(
            reverse("accounts:verify_invite_email"),
            data={"email": invite.email, "code": otp.code},
        )

        self.assertRedirects(response, reverse("accounts:login"))
        invite.refresh_from_db()
        self.assertTrue(invite.is_email_verified)
        self.assertEqual(invite.status, EmployeeInvite.Status.PENDING_APPROVAL)
        self.assertFalse(User.objects.filter(email="invite@example.com").exists())
        signup = SignupRequest.objects.get(email="invite@example.com")
        self.assertEqual(signup.status, SignupRequestStatus.PENDING_APPROVAL)
        self.assertTrue(signup.is_email_verified)
        self.assertIsNone(signup.user)

    def test_company_owner_can_approve_verified_invite(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Invite User",
            email="invite@example.com",
            phone="+91 9999999999",
            role=Role.EXECUTIVE,
            employee_code="SIYA-EXE-007",
            is_email_verified=True,
            status=EmployeeInvite.Status.PENDING_APPROVAL,
        )
        self.client.force_login(owner)
        mail.outbox = []

        response = self.client.post(reverse("accounts:employee_invite_approve", args=[invite.id]))

        self.assertRedirects(response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        invite.refresh_from_db()
        self.assertEqual(invite.status, EmployeeInvite.Status.APPROVED)
        user = User.objects.get(email="invite@example.com")
        self.assertEqual(user.profile.company, company)
        self.assertEqual(user.profile.role, Role.EXECUTIVE)
        self.assertEqual(user.profile.employee_code, "SIYA-EXE-007")
        signup = SignupRequest.objects.get(email="invite@example.com")
        self.assertEqual(signup.status, SignupRequestStatus.APPROVED)
        self.assertEqual(signup.user, user)
        self.assertEqual(invite.approved_by, owner)
        self.assertIsNotNone(invite.approved_at)
        self.assertEqual(len(mail.outbox), 2)

    def test_manager_cannot_invite_manager_or_owner_roles(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=company)
        self.client.force_login(manager)

        response = self.client.post(
            reverse("accounts:employee_invites"),
            data={
                "invite-name": "Bad Invite",
                "invite-email": "bad@example.com",
                "invite-phone": "+91 9999999999",
                "invite-role": Role.MANAGER,
                "invite-employee_code": "SIYA-MGR-002",
                "invite-note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EmployeeInvite.objects.filter(email="bad@example.com").exists())
        self.assertContains(response, "Select a valid choice.")

    def test_invite_allows_email_with_old_signup_request_but_no_active_account(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        SignupRequest.objects.create(
            name="Old Signup",
            phone="+91 9999999999",
            email="thewebfixofficial@gmail.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:employee_invites"),
            data={
                "invite-name": "The Webfix",
                "invite-email": "thewebfixofficial@gmail.com",
                "invite-phone": "+91 9999999999",
                "invite-role": Role.EXECUTIVE,
                "invite-employee_code": "SIYA-EXE-099",
                "invite-note": "",
            },
        )

        invite = EmployeeInvite.objects.get(email="thewebfixofficial@gmail.com")
        self.assertRedirects(response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        self.assertEqual(invite.employee_code, "SIYA-EXE-099")
        self.assertFalse(User.objects.filter(email="thewebfixofficial@gmail.com").exists())

    def test_owner_can_verify_invite_otp_from_invite_detail(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Detail Verify",
            email="detail-verify@example.com",
            role=Role.EXECUTIVE,
            status=EmployeeInvite.Status.PENDING_VERIFICATION,
        )
        otp = EmailOTP.create_for_email(invite.email)
        self.client.force_login(owner)

        detail_response = self.client.get(reverse("accounts:employee_invite_detail", args=[invite.id]))
        self.assertContains(detail_response, "Email OTP Verification")
        self.assertContains(detail_response, "Verify OTP")

        response = self.client.post(reverse("accounts:employee_invite_verify_otp", args=[invite.id]), data={"code": otp.code})

        self.assertRedirects(response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        invite.refresh_from_db()
        self.assertTrue(invite.is_email_verified)
        self.assertEqual(invite.status, EmployeeInvite.Status.PENDING_APPROVAL)
        signup = SignupRequest.objects.get(email="detail-verify@example.com")
        self.assertEqual(signup.status, SignupRequestStatus.PENDING_APPROVAL)
        self.assertTrue(signup.is_email_verified)

    def test_invite_detail_filters_and_cooldown_are_enforced(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Cooldown User",
            email="cooldown@example.com",
            role=Role.EXECUTIVE,
            status=EmployeeInvite.Status.PENDING_VERIFICATION,
            last_invite_sent_at=timezone.now(),
        )
        EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Approved User",
            email="approved-invite@example.com",
            role=Role.TL,
            status=EmployeeInvite.Status.APPROVED,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        detail_response = self.client.get(reverse("accounts:employee_invite_detail", args=[invite.id]))
        self.assertContains(detail_response, "Cooldown User")
        self.assertContains(detail_response, "Resend in")
        self.assertContains(detail_response, "data-invite-resend-countdown")

        resend_response = self.client.post(reverse("accounts:employee_invite_resend", args=[invite.id]))
        self.assertRedirects(resend_response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        invite.refresh_from_db()
        self.assertEqual(invite.resend_count, 0)

        filtered_response = self.client.get(reverse("accounts:employee_invite_list"), {"status": EmployeeInvite.Status.APPROVED})
        self.assertContains(filtered_response, "Approved User")
        self.assertNotContains(filtered_response, "Cooldown User")

    def test_invite_list_is_paginated(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        for index in range(12):
            EmployeeInvite.objects.create(
                company=company,
                invited_by=owner,
                name=f"Invite {index}",
                email=f"invite{index}@example.com",
                role=Role.EXECUTIVE,
            )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:employee_invite_list"))

        self.assertContains(response, "Invite List")
        self.assertContains(response, "Page 1 of 2")

    def test_invite_list_bulk_delete_and_resend(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        delete_invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Delete Invite",
            email="delete-invite@example.com",
            role=Role.EXECUTIVE,
        )
        resend_invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Resend Invite",
            email="resend-invite@example.com",
            role=Role.EXECUTIVE,
            last_invite_sent_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(owner)
        mail.outbox = []

        delete_response = self.client.post(
            reverse("accounts:employee_invite_bulk_action"),
            data={"bulk_action": "delete", "invite_ids": [str(delete_invite.id)]},
        )
        self.assertRedirects(delete_response, reverse("accounts:employee_invite_list"))
        self.assertFalse(EmployeeInvite.objects.filter(id=delete_invite.id).exists())

        resend_response = self.client.post(
            reverse("accounts:employee_invite_bulk_action"),
            data={"bulk_action": "resend", "invite_ids": [str(resend_invite.id)]},
        )
        self.assertRedirects(resend_response, reverse("accounts:employee_invite_list"))
        resend_invite.refresh_from_db()
        self.assertEqual(resend_invite.resend_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_invite_list_bulk_approves_verified_invite(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Bulk Approve",
            email="bulk-approve@example.com",
            role=Role.EXECUTIVE,
            employee_code="SIYA-EXE-100",
            is_email_verified=True,
            status=EmployeeInvite.Status.PENDING_APPROVAL,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:employee_invite_bulk_action"),
            data={"bulk_action": "approve", "invite_ids": [str(invite.id)]},
        )

        self.assertRedirects(response, reverse("accounts:employee_invite_list"))
        invite.refresh_from_db()
        self.assertEqual(invite.status, EmployeeInvite.Status.APPROVED)
        self.assertTrue(User.objects.filter(email="bulk-approve@example.com").exists())

    def test_approved_invite_cannot_be_resent_or_deleted(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        invite = EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Approved User",
            email="approved-lock@example.com",
            role=Role.EXECUTIVE,
            status=EmployeeInvite.Status.APPROVED,
            is_email_verified=True,
            last_invite_sent_at=timezone.now() - timedelta(minutes=5),
        )
        self.client.force_login(owner)

        resend_response = self.client.post(reverse("accounts:employee_invite_resend", args=[invite.id]))
        self.assertRedirects(resend_response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        delete_response = self.client.post(reverse("accounts:employee_invite_delete", args=[invite.id]))
        self.assertRedirects(delete_response, reverse("accounts:employee_invite_detail", args=[invite.id]))
        self.assertTrue(EmployeeInvite.objects.filter(id=invite.id).exists())

    def test_company_owner_approval_page_lists_signup_and_invites(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        SignupRequest.objects.create(
            name="Pending Signup",
            phone="+91 9999999999",
            email="pending@example.com",
            requested_role=Role.MANAGER,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        SignupRequest.objects.create(
            name="Approved Signup",
            phone="+91 8888888888",
            email="approved-history@example.com",
            requested_role=Role.EXECUTIVE,
            approved_role=Role.EXECUTIVE,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
        )
        EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Invite User",
            email="invite@example.com",
            role=Role.EXECUTIVE,
            is_email_verified=True,
            status=EmployeeInvite.Status.PENDING_APPROVAL,
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_requests"))

        self.assertContains(response, "Pending Signup")
        self.assertContains(response, "Approved Signups")
        self.assertNotContains(response, "Invite User")
        self.assertNotContains(response, "Employee Invites")
        self.assertContains(response, "Verified Signups")

    def test_company_owner_signup_request_list_has_history_filters_and_pagination(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        for index in range(15):
            SignupRequest.objects.create(
                name=f"Applicant {index}",
                phone="+91 9999999999",
                email=f"applicant{index}@example.com",
                requested_role=Role.EXECUTIVE,
                status=SignupRequestStatus.APPROVED if index % 2 == 0 else SignupRequestStatus.REJECTED,
                is_email_verified=True,
            )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_signup_request_list"))

        self.assertContains(response, "Signup Request List")
        self.assertContains(response, "Page 1 of 2")

        response = self.client.get(reverse("accounts:owner_signup_request_list"), {"status": SignupRequestStatus.REJECTED, "q": "Applicant 1"})
        self.assertContains(response, "Applicant 1")
        self.assertNotContains(response, "Applicant 0")

    def test_company_owner_can_bulk_delete_signup_requests_from_list(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="Delete Me",
            phone="+91 9999999999",
            email="delete-me@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        EmailOTP.create_for_email("delete-me@example.com", signup_request=signup)
        EmployeeInvite.objects.create(
            company=company,
            invited_by=owner,
            name="Delete Me",
            email="delete-me@example.com",
            role=Role.EXECUTIVE,
            status=EmployeeInvite.Status.PENDING_APPROVAL,
            is_email_verified=True,
        )
        keep_signup = SignupRequest.objects.create(
            name="Keep Me",
            phone="+91 8888888888",
            email="keep-me@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:owner_signup_request_bulk_delete"), data={"signup_ids": [str(signup.id)]})

        self.assertRedirects(response, reverse("accounts:owner_signup_request_list"))
        self.assertFalse(SignupRequest.objects.filter(email="delete-me@example.com").exists())
        self.assertFalse(EmployeeInvite.objects.filter(email="delete-me@example.com").exists())
        self.assertFalse(EmailOTP.objects.filter(email="delete-me@example.com").exists())
        self.assertTrue(SignupRequest.objects.filter(id=keep_signup.id).exists())

    def test_company_owner_bulk_signup_delete_requires_selection(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="Keep Me",
            phone="+91 8888888888",
            email="keep-me@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.post(reverse("accounts:owner_signup_request_bulk_delete"), data={})

        self.assertRedirects(response, reverse("accounts:owner_signup_request_list"))
        self.assertTrue(SignupRequest.objects.filter(id=signup.id).exists())

    def test_company_owner_can_view_signup_request_detail_and_send_custom_email(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="Detail User",
            phone="+91 9999999999",
            email="detail@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("accounts:owner_signup_request_detail", args=[signup.id]))
        self.assertContains(response, "Detail User")
        self.assertContains(response, "Custom Email")

        response = self.client.post(
            reverse("accounts:owner_signup_request_detail", args=[signup.id]),
            data={
                "action": "send_email",
                "email-subject": "Need more details",
                "email-message": "Please share your manager reference.",
            },
        )

        self.assertRedirects(response, reverse("accounts:owner_signup_request_detail", args=[signup.id]))
        self.assertEqual(SignupRequestOwnerMessage.objects.filter(signup_request=signup).count(), 1)
        self.assertEqual(mail.outbox[-1].to, ["detail@example.com"])
        self.assertEqual(mail.outbox[-1].subject, "Need more details")

    def test_company_owner_can_approve_signup_from_detail_page(self):
        User = get_user_model()
        company = CompanyProfile.objects.create(name="Siya Real Build")
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER, company=company)
        signup = SignupRequest.objects.create(
            name="Detail Approval",
            phone="+91 9999999999",
            email="detail-approval@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("accounts:owner_signup_request_detail", args=[signup.id]),
            data={
                "action": "approve",
                "review-approved_role": Role.MANAGER,
                "review-admin_note": "Looks good.",
            },
        )

        self.assertRedirects(response, reverse("accounts:owner_signup_request_detail", args=[signup.id]))
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupRequestStatus.APPROVED)
        self.assertEqual(signup.approved_role, Role.MANAGER)

    def test_only_one_company_profile_can_exist(self):
        CompanyProfile.objects.create(name="Siya Real Build")

        with self.assertRaises(IntegrityError):
            CompanyProfile.objects.create(name="Another Company")

    def test_company_admin_add_is_available_only_until_company_exists(self):
        User = get_user_model()
        superuser = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="password",
        )
        request = type("Request", (), {"user": superuser})()
        company_admin = CompanyProfileAdmin(CompanyProfile, AdminSite())

        self.assertTrue(company_admin.has_add_permission(request))
        CompanyProfile.objects.create(name="Siya Real Build")
        self.assertFalse(company_admin.has_add_permission(request))

    def test_company_admin_uses_company_master_fields_without_owner(self):
        company_admin = CompanyProfileAdmin(CompanyProfile, AdminSite())
        field_names = [
            field
            for _, options in company_admin.fieldsets
            for field in options["fields"]
        ]

        self.assertNotIn("owner", field_names)
        self.assertIn("logo", field_names)
        self.assertIn("phone_3", field_names)
        self.assertIn("email_3", field_names)
        self.assertIn("gst_number", field_names)
        self.assertIn("rera_number", field_names)


class MarketingOfferWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = CompanyProfile.objects.create(name="Siya Real Build", email="company@example.com")
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=self.owner, role=Role.COMPANY_OWNER, company=self.company)
        self.referrer = User.objects.create_user(username="referrer@example.com", email="referrer@example.com")
        UserProfile.objects.create(user=self.referrer, role=Role.MANAGER, company=self.company)
        self.referred = User.objects.create_user(username="referred@example.com", email="referred@example.com")
        UserProfile.objects.create(user=self.referred, role=Role.CHANNEL_PARTNER, company=self.company)
        self.signup = SignupRequest.objects.create(
            name="Referred User",
            phone="+91 9999999999",
            email=self.referred.email,
            requested_role=Role.CHANNEL_PARTNER,
            approved_role=Role.CHANNEL_PARTNER,
            status=SignupRequestStatus.APPROVED,
            is_email_verified=True,
            user=self.referred,
        )

    def test_marketing_dashboard_renders_for_owner(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:owner_marketing_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketing Dashboard")

    def test_referral_reward_payout_action_and_export(self):
        reward = ReferralReward.objects.create(
            company=self.company,
            signup_request=self.signup,
            referrer=self.referrer,
            referred_user=self.referred,
            referral_code="REF-001",
            referrer_reward_amount=500,
            referred_reward_amount=250,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("accounts:owner_referrals"),
            data={"reward_id": reward.id, "reward_action": ReferralReward.PayoutStatus.PAID, "payout_note": "Paid by UPI"},
        )

        self.assertRedirects(response, reverse("accounts:owner_referrals"))
        reward.refresh_from_db()
        self.assertEqual(reward.payout_status, ReferralReward.PayoutStatus.PAID)
        self.assertIsNotNone(reward.paid_at)
        self.assertTrue(AuditLog.objects.filter(action="marketing.reward_payout_updated").exists())

        export_response = self.client.get(reverse("accounts:owner_referrals"), {"export": "csv"})
        self.assertEqual(export_response.status_code, 200)
        self.assertContains(export_response, "REF-001")

    def test_marketing_view_only_role_cannot_update_referral_settings(self):
        manager = get_user_model().objects.create_user(username="marketing-view@example.com", email="marketing-view@example.com")
        UserProfile.objects.create(user=manager, role=Role.MANAGER, company=self.company)
        RoleMatrixRule.objects.create(company=self.company, role=Role.MANAGER, module="marketing", can_view=True, can_update=False)
        self.client.force_login(manager)

        response = self.client.post(
            reverse("accounts:owner_referrals"),
            data={
                "referral-is_active": "on",
                "referral-referrer_reward_amount": "1000",
                "referral-referrer_coupon_code": "",
                "referral-referred_reward_amount": "500",
                "referral-referred_coupon_code": "",
                "referral-terms": "Updated by view-only user",
            },
        )

        self.assertRedirects(response, reverse("accounts:owner_referrals"))
        setting = self.company.referral_setting
        self.assertFalse(setting.is_active)
        self.assertEqual(setting.referrer_reward_amount, 0)

    def test_referral_pending_count_only_includes_company_referrer_codes(self):
        self.referrer.profile.employee_code = "SIYA-MGR-001"
        self.referrer.profile.save(update_fields=["employee_code", "updated_at"])
        SignupRequest.objects.create(
            name="Visible Pending",
            phone="+91 9999999999",
            email="visible-pending@example.com",
            channel_partner_reference="SIYA-MGR-001",
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        SignupRequest.objects.create(
            name="Hidden Pending",
            phone="+91 9999999999",
            email="hidden-pending@example.com",
            channel_partner_reference="OTHER-CODE",
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:owner_referrals"))

        self.assertContains(response, "1 referral reference")

    def test_popup_tracking_and_role_overlap_activation(self):
        manager_popup = SoftwarePopup.objects.create(
            company=self.company,
            title="Manager Offer",
            message="Offer",
            roles=[Role.MANAGER],
            is_active=True,
        )
        executive_popup = SoftwarePopup.objects.create(
            company=self.company,
            title="Executive Offer",
            message="Offer",
            roles=[Role.EXECUTIVE],
            is_active=True,
        )
        replacement = SoftwarePopup.objects.create(
            company=self.company,
            title="New Manager Offer",
            message="Offer",
            roles=[Role.MANAGER],
            is_active=False,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("accounts:owner_popups"),
            data={"popup_ids": [str(replacement.id)], "bulk_action": "activate"},
        )

        self.assertRedirects(response, reverse("accounts:owner_popups"))
        manager_popup.refresh_from_db()
        executive_popup.refresh_from_db()
        replacement.refresh_from_db()
        self.assertFalse(manager_popup.is_active)
        self.assertTrue(executive_popup.is_active)
        self.assertTrue(replacement.is_active)

        track_response = self.client.post(reverse("accounts:popup_track", args=[replacement.id, "click"]))
        replacement.refresh_from_db()
        self.assertEqual(track_response.status_code, 200)
        self.assertEqual(replacement.clicks, 1)

    def test_popup_form_requires_cta_label_and_url_together(self):
        form = SoftwarePopupForm(
            data={
                "popup-title": "Offer",
                "popup-message": "Message",
                "popup-deal_label": "Deal",
                "popup-cta_label": "Book now",
                "popup-cta_url": "",
                "popup-roles": [Role.MANAGER],
                "popup-is_active": "on",
            },
            instance=SoftwarePopup(company=self.company, offer_image="popups/offers/existing.jpg"),
            prefix="popup",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("CTA label and CTA URL", str(form.errors))

    def test_popup_form_rejects_non_image_offer_upload(self):
        form = SoftwarePopupForm(
            data={
                "popup-title": "Offer",
                "popup-message": "Message",
                "popup-deal_label": "Deal",
                "popup-roles": [Role.MANAGER],
                "popup-is_active": "on",
            },
            files={"popup-offer_image": SimpleUploadedFile("offer.pdf", b"pdf", content_type="application/pdf")},
            prefix="popup",
        )

        self.assertFalse(form.is_valid())
        self.assertIn("offer_image", form.errors)

    def test_event_form_rejects_non_image_cover_upload(self):
        form = CompanyEventForm(
            data={
                "title": "Launch",
                "caption": "Caption",
                "description": "Desc",
                "starts_at": "2026-06-15T10:00",
                "ends_at": "2026-06-15T12:00",
                "roles": [Role.MANAGER],
                "is_active": "on",
            },
            files={"cover_image": SimpleUploadedFile("cover.pdf", b"pdf", content_type="application/pdf")},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_sidebar_shows_my_referrals_without_owner_marketing_links(self):
        executive = get_user_model().objects.create_user(username="exec-sidebar@example.com", email="exec-sidebar@example.com")
        UserProfile.objects.create(user=executive, role=Role.EXECUTIVE, company=self.company)
        self.client.force_login(executive)

        response = self.client.get(reverse("properties:dashboard"))

        self.assertContains(response, "Marketing & Referrals")
        self.assertContains(response, "My Referrals")
        self.assertNotContains(response, "Marketing Dashboard")
        self.assertNotContains(response, "Referral Settings")
