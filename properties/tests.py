from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import AuthenticationSupportRequest, Role, SignupRequest, SignupRequestStatus, UserProfile


class DashboardAuthenticationRequestTests(TestCase):
    def test_company_owner_sees_pending_signup_and_support_requests(self):
        User = get_user_model()
        owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        UserProfile.objects.create(user=owner, role=Role.COMPANY_OWNER)
        SignupRequest.objects.create(
            name="Pending User",
            phone="+91 9999999999",
            email="pending@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        AuthenticationSupportRequest.objects.create(
            name="Support User",
            contact="support@example.com",
            issue="OTP was not received.",
        )

        self.client.force_login(owner)
        response = self.client.get(reverse("properties:dashboard"))

        self.assertContains(response, "Pending Signup Requests")
        self.assertContains(response, "pending@example.com")
        self.assertContains(response, "Authentication Support")
        self.assertContains(response, "OTP was not received.")

    def test_non_owner_does_not_see_authentication_request_sections(self):
        User = get_user_model()
        user = User.objects.create_user(username="user@example.com", email="user@example.com")
        UserProfile.objects.create(user=user, role=Role.EXECUTIVE)
        SignupRequest.objects.create(
            name="Pending User",
            phone="+91 9999999999",
            email="pending@example.com",
            requested_role=Role.EXECUTIVE,
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )
        AuthenticationSupportRequest.objects.create(
            name="Support User",
            contact="support@example.com",
            issue="OTP was not received.",
        )

        self.client.force_login(user)
        response = self.client.get(reverse("properties:dashboard"))

        self.assertNotContains(response, "Pending Signup Requests")
        self.assertNotContains(response, "Authentication Support")
