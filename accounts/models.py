from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    COMPANY_OWNER = "company_owner", "Company Owner"
    MANAGER = "manager", "Manager"
    TL = "tl", "TL"
    EXECUTIVE = "executive", "Executive"
    CHANNEL_PARTNER = "channel_partner", "Channel Partner"


class SignupRequestStatus(models.TextChoices):
    OTP_PENDING = "otp_pending", "OTP Pending"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class SignupRequest(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    requested_role = models.CharField(max_length=32, choices=Role.choices)
    approved_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    channel_partner_reference = models.CharField(max_length=160, blank=True)
    status = models.CharField(
        max_length=24,
        choices=SignupRequestStatus.choices,
        default=SignupRequestStatus.OTP_PENDING,
    )
    is_email_verified = models.BooleanField(default=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.email}"

    def approve(self):
        previous = None
        if self.pk:
            previous = SignupRequest.objects.filter(pk=self.pk).only("status", "user_id").first()
        was_already_approved = bool(
            previous
            and previous.status == SignupRequestStatus.APPROVED
            and previous.user_id
        )
        role = self.approved_role or self.requested_role
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username=self.email.lower().strip(),
            defaults={
                "email": self.email.lower().strip(),
                "first_name": self.name,
                "is_active": True,
            },
        )
        user.email = self.email.lower().strip()
        user.first_name = self.name
        user.is_active = True
        user.save(update_fields=["email", "first_name", "is_active"])
        self.user = user
        self.approved_role = role
        self.status = SignupRequestStatus.APPROVED
        self.save(update_fields=["user", "approved_role", "status", "updated_at"])
        if not was_already_approved:
            from .email_utils import send_signup_approval_confirmation_email, send_welcome_email

            role_label = Role(role).label
            send_signup_approval_confirmation_email(to_email=self.email, name=self.name, role_label=role_label)
            send_welcome_email(to_email=self.email, name=self.name, role_label=role_label)
        return user

    def reject(self):
        previous = None
        if self.pk:
            previous = SignupRequest.objects.filter(pk=self.pk).only("status").first()
        was_already_rejected = bool(previous and previous.status == SignupRequestStatus.REJECTED)
        self.status = SignupRequestStatus.REJECTED
        self.save(update_fields=["status", "updated_at"])
        if not was_already_rejected:
            from .email_utils import send_signup_rejection_email

            send_signup_rejection_email(to_email=self.email, name=self.name, admin_note=self.admin_note)


class EmailOTP(models.Model):
    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=6)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    signup_request = models.ForeignKey(SignupRequest, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.code}"

    @classmethod
    def create_for_email(cls, email, signup_request=None):
        return cls.objects.create(
            email=email.lower().strip(),
            code=f"{secrets.randbelow(1_000_000):06d}",
            expires_at=timezone.now() + timedelta(minutes=10),
            signup_request=signup_request,
        )

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class CompanyProfile(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_company")
    name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    gst_number = models.CharField(max_length=32, blank=True)
    rera_number = models.CharField(max_length=64, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or f"{self.owner} company"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    company = models.ForeignKey(CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.EXECUTIVE)
    profile_image = models.ImageField(upload_to="profiles/", blank=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=80, blank=True)
    employee_code = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.email or self.user.username

    @property
    def is_company_owner(self):
        return self.role == Role.COMPANY_OWNER


class EmployeeInvite(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invites")
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.EXECUTIVE)
    employee_code = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    accepted_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_invites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("company", "email")

    def __str__(self):
        return f"{self.name} - {self.email}"
