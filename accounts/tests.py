from django.core import mail
from django.test import TestCase, override_settings

from .forms import SignupRequestForm
from .models import Role, SignupRequest, SignupRequestStatus


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignupApprovalEmailTests(TestCase):
    def test_approval_sends_confirmation_and_welcome_emails(self):
        signup = SignupRequest.objects.create(
            name="Anshul Sharma",
            phone="9999999999",
            email="anshul@example.com",
            requested_role=Role.MANAGER,
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
