from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models, transaction
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
    requested_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
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
        role = self.approved_role
        if not role:
            raise ValidationError({"approved_role": "Select a role before approving this signup request."})
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
        company = CompanyProfile.objects.order_by("id").first()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if company and profile.company_id != company.id:
            profile.company = company
        profile.role = role
        if self.phone:
            profile.phone = self.phone
        if self.channel_partner_reference and not profile.channel_partner_reference:
            profile.channel_partner_reference = self.channel_partner_reference
        profile.save(update_fields=["company", "role", "phone", "channel_partner_reference", "updated_at"])
        ReferralReward.activate_for_signup(self, company=company)
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


class SignupRequestOwnerMessage(models.Model):
    signup_request = models.ForeignKey(SignupRequest, on_delete=models.CASCADE, related_name="owner_messages")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.signup_request.email} - {self.subject}"


class EmailOTP(models.Model):
    email = models.EmailField(db_index=True)
    code = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    signup_request = models.ForeignKey(SignupRequest, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - OTP"

    @classmethod
    def create_for_email(cls, email, signup_request=None):
        raw_code = f"{secrets.randbelow(1_000_000):06d}"
        otp = cls.objects.create(
            email=email.lower().strip(),
            code=make_password(raw_code),
            expires_at=timezone.now() + timedelta(minutes=10),
            signup_request=signup_request,
        )
        otp.code = raw_code
        return otp

    def matches(self, raw_code):
        return check_password(raw_code, self.code)

    def set_code(self, raw_code):
        self.code = make_password(raw_code)
        self.save(update_fields=["code"])

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class CompanyProfile(models.Model):
    singleton_key = models.BooleanField(default=True, editable=False, unique=True)
    logo = models.ImageField(upload_to="company/", blank=True)
    name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    phone_2 = models.CharField(max_length=20, blank=True)
    phone_3 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    email_2 = models.EmailField(blank=True)
    email_3 = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    gst_number = models.CharField(max_length=32, blank=True)
    rera_number = models.CharField(max_length=64, blank=True)
    cin_number = models.CharField(max_length=64, blank=True)
    pan_number = models.CharField(max_length=32, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=160, blank=True)
    bank_account_number = models.CharField(max_length=40, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)
    upi_id = models.CharField(max_length=80, blank=True)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    weekly_off_days = models.CharField(max_length=160, blank=True)
    holiday_notes = models.TextField(blank=True)
    tagline = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or "Siya Real Build"


class OfficeLocation(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="office_locations")
    name = models.CharField(max_length=120)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("company", "name")
        db_table = "accounts_companyofficelocation"

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action = models.CharField(max_length=80)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=80, blank=True)
    target_label = models.CharField(max_length=240, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class NotificationDelivery(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    company = models.ForeignKey(CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="notification_deliveries")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="notification_deliveries")
    category = models.CharField(max_length=80)
    recipient = models.EmailField()
    subject = models.CharField(max_length=180)
    status = models.CharField(max_length=16, choices=Status.choices)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class TeamEmailMessage(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="team_emails")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    department = models.CharField(max_length=80, blank=True)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    recipients = models.JSONField(default=list, blank=True)
    sent_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class UserProfile(models.Model):
    class GovernmentIdType(models.TextChoices):
        AADHAAR = "aadhaar", "Aadhaar"
        VOTER_ID = "voter_id", "Voter ID"
        PASSPORT = "passport", "Passport"
        DRIVING_LICENSE = "driving_license", "Driving License"
        OTHER = "other", "Other"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Single"
        MARRIED = "married", "Married"
        OTHER = "other", "Other"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    company = models.ForeignKey(CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.EXECUTIVE)
    profile_image = models.ImageField(upload_to="profiles/", blank=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=80, blank=True)
    employee_code = models.CharField(max_length=32, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=24, choices=Gender.choices, blank=True)
    blood_group = models.CharField(max_length=8, blank=True)
    marital_status = models.CharField(max_length=16, choices=MaritalStatus.choices, blank=True)
    personal_email = models.EmailField(blank=True)
    government_id_type = models.CharField(max_length=32, choices=GovernmentIdType.choices, blank=True)
    government_id_number = models.CharField(max_length=64, blank=True)
    aadhaar_number = models.CharField(max_length=20, blank=True)
    aadhaar_document = models.FileField(upload_to="profiles/documents/", blank=True)
    pan_number = models.CharField(max_length=16, blank=True)
    pan_document = models.FileField(upload_to="profiles/documents/", blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=80, blank=True)
    reporting_manager = models.CharField(max_length=120, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    work_location = models.CharField(max_length=120, blank=True)
    territory = models.CharField(max_length=120, blank=True)
    channel_partner_reference = models.CharField(max_length=160, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=160, blank=True)
    bank_account_number = models.CharField(max_length=40, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee_code"],
                condition=~models.Q(employee_code=""),
                name="unique_company_employee_code",
            ),
        ]

    def __str__(self):
        return self.user.get_full_name() or self.user.email or self.user.username

    @property
    def is_company_owner(self):
        return self.role == Role.COMPANY_OWNER

    @property
    def masked_aadhaar_number(self):
        digits = "".join(ch for ch in self.aadhaar_number if ch.isdigit())
        if len(digits) >= 4:
            return f"XXXX XXXX {digits[-4:]}"
        return "Not added"

    @property
    def masked_pan_number(self):
        value = (self.pan_number or "").upper()
        if len(value) >= 4:
            return f"{value[:3]}XXXX{value[-1]}"
        return "Not added"


class EmployeeProfileChange(models.Model):
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="change_history")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EmployeeInvite(models.Model):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending Email Verification"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_invites")
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.EXECUTIVE)
    employee_code = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_VERIFICATION)
    is_email_verified = models.BooleanField(default=False)
    accepted_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_invites")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_invites")
    approved_at = models.DateTimeField(null=True, blank=True)
    last_invite_sent_at = models.DateTimeField(null=True, blank=True)
    resend_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("company", "email")

    def __str__(self):
        return f"{self.name} - {self.email}"

    @transaction.atomic
    def approve(self, approved_by=None):
        if not self.is_email_verified:
            return None
        previous = None
        if self.pk:
            previous = EmployeeInvite.objects.filter(pk=self.pk).only("status", "accepted_user_id").first()
        was_already_approved = bool(
            previous
            and previous.status == self.Status.APPROVED
            and previous.accepted_user_id
        )
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
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.company = self.company
        profile.role = self.role
        profile.phone = self.phone
        if self.employee_code:
            profile.employee_code = self.employee_code
        profile.save(update_fields=["company", "role", "phone", "employee_code", "updated_at"])
        self.accepted_user = user
        self.status = self.Status.APPROVED
        if approved_by:
            self.approved_by = approved_by
        self.approved_at = self.approved_at or timezone.now()
        self.save(update_fields=["accepted_user", "status", "approved_by", "approved_at", "updated_at"])
        SignupRequest.objects.update_or_create(
            email=self.email.lower().strip(),
            defaults={
                "name": self.name,
                "phone": self.phone,
                "requested_role": self.role,
                "approved_role": self.role,
                "status": SignupRequestStatus.APPROVED,
                "is_email_verified": True,
                "user": user,
            },
        )
        if not was_already_approved:
            from .email_utils import send_signup_approval_confirmation_email, send_welcome_email

            role_label = Role(self.role).label
            send_signup_approval_confirmation_email(to_email=self.email, name=self.name, role_label=role_label)
            send_welcome_email(to_email=self.email, name=self.name, role_label=role_label)
        return user

    def reject(self):
        self.status = self.Status.REJECTED
        self.save(update_fields=["status", "updated_at"])


class AuthenticationSupportRequest(models.Model):
    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=160, blank=True)
    issue = models.TextField()
    page_url = models.CharField(max_length=300, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.contact or 'No contact'}"


class DesignationCodeRule(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="designation_code_rules")
    role = models.CharField(max_length=32, choices=Role.choices)
    designation = models.CharField(max_length=80)
    prefix = models.CharField(max_length=16)
    next_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "role", "designation")
        ordering = ["role", "designation"]

    def __str__(self):
        return f"{self.get_role_display()} - {self.designation}"

    def preview_code(self):
        return f"{self.prefix}-{self.next_number:04d}"


class Meeting(models.Model):
    class AudienceType(models.TextChoices):
        GLOBAL = "global", "All Roles"
        ROLE = "role", "Role Wise"
        EMPLOYEE = "employee", "Employee Wise"
        TEAM = "team", "Team Wise"
        GROUP = "group", "Group Wise"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="meetings")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_meetings")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    audience_type = models.CharField(max_length=20, choices=AudienceType.choices, default=AudienceType.GLOBAL)
    roles = models.JSONField(default=list, blank=True)
    employees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="assigned_meetings")
    location = models.CharField(max_length=180, blank=True)
    meeting_link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    status_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.title


class CompanyEvent(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="events")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_events")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    caption = models.CharField(max_length=240, blank=True)
    cover_image = models.ImageField(upload_to="events/covers/", blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    is_global = models.BooleanField(default=True)
    roles = models.JSONField(default=list, blank=True)
    show_as_popup = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.title


class ReferralSetting(models.Model):
    company = models.OneToOneField(CompanyProfile, on_delete=models.CASCADE, related_name="referral_setting")
    is_active = models.BooleanField(default=False)
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=40, blank=True)
    referrer_reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referred_reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referrer_coupon_code = models.CharField(max_length=40, blank=True)
    referred_coupon_code = models.CharField(max_length=40, blank=True)
    terms = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Referral settings - {self.company}"

    def clean(self):
        errors = {}
        if self.referrer_reward_amount and self.referrer_reward_amount > 0 and self.referrer_coupon_code:
            errors["referrer_coupon_code"] = "Choose either reward amount or coupon for the referrer, not both."
        if self.referred_reward_amount and self.referred_reward_amount > 0 and self.referred_coupon_code:
            errors["referred_coupon_code"] = "Choose either reward amount or coupon for the new Channel Partner, not both."
        if errors:
            raise ValidationError(errors)


class ReferralReward(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="referral_rewards")
    setting = models.ForeignKey(ReferralSetting, on_delete=models.SET_NULL, null=True, blank=True, related_name="rewards")
    signup_request = models.OneToOneField(SignupRequest, on_delete=models.CASCADE, related_name="referral_reward")
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_rewards_given")
    referred_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_rewards_received")
    referral_code = models.CharField(max_length=160)
    referrer_reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referred_reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=40, blank=True)
    referrer_coupon_code = models.CharField(max_length=40, blank=True)
    referred_coupon_code = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    activated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activated_at", "-created_at"]

    def __str__(self):
        return f"{self.referral_code} -> {self.referred_user}"

    @classmethod
    def activate_for_signup(cls, signup, company=None):
        role = signup.approved_role or signup.requested_role
        if role != Role.CHANNEL_PARTNER or not signup.user_id:
            return None
        referral_code = (signup.channel_partner_reference or "").strip()
        if not referral_code:
            return None
        company = company or CompanyProfile.objects.order_by("id").first()
        if not company:
            return None
        setting = ReferralSetting.objects.filter(company=company, is_active=True).first()
        if not setting:
            return None
        referrer_amount = setting.referrer_reward_amount
        referred_amount = setting.referred_reward_amount
        referrer_coupon = setting.referrer_coupon_code
        referred_coupon = setting.referred_coupon_code
        referrer_profile = (
            UserProfile.objects.filter(company=company)
            .exclude(user=signup.user)
            .filter(
                models.Q(employee_code__iexact=referral_code)
                | models.Q(user__email__iexact=referral_code)
                | models.Q(user__username__iexact=referral_code)
            )
            .select_related("user")
            .first()
        )
        if not referrer_profile:
            return None
        reward, created = cls.objects.get_or_create(
            signup_request=signup,
            defaults={
                "company": company,
                "setting": setting,
                "referrer": referrer_profile.user,
                "referred_user": signup.user,
                "referral_code": referral_code,
                "referrer_reward_amount": referrer_amount,
                "referred_reward_amount": referred_amount,
                "coupon_code": referrer_coupon or referred_coupon,
                "referrer_coupon_code": referrer_coupon,
                "referred_coupon_code": referred_coupon,
            },
        )
        if created:
            from .email_utils import send_referral_reward_email

            referrer_name = referrer_profile.user.get_full_name() or referrer_profile.user.email
            referred_name = signup.user.get_full_name() or signup.user.email
            send_referral_reward_email(
                to_email=referrer_profile.user.email,
                name=referrer_name,
                reward_amount=referrer_amount,
                coupon_code=referrer_coupon,
                referred_name=referred_name,
                is_referrer=True,
            )
            send_referral_reward_email(
                to_email=signup.user.email,
                name=referred_name,
                reward_amount=referred_amount,
                coupon_code=referred_coupon,
                referrer_name=referrer_name,
                is_referrer=False,
            )
        return reward if created else reward


class RoleTarget(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="targets")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assigned_targets")
    role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="targets")
    title = models.CharField(max_length=160)
    target_value = models.PositiveIntegerField(default=0)
    metric = models.CharField(max_length=80, default="Leads")
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class SoftwarePopup(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="popups")
    title = models.CharField(max_length=160)
    message = models.TextField()
    deal_label = models.CharField(max_length=80, blank=True)
    offer_image = models.ImageField(upload_to="popups/offers/", blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class RoleMatrixRule(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="role_matrix")
    role = models.CharField(max_length=32, choices=Role.choices)
    module = models.CharField(max_length=80)
    can_view = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        unique_together = ("company", "role", "module")
        ordering = ["role", "module"]

    def __str__(self):
        return f"{self.get_role_display()} - {self.module}"


class EmployeeEmailChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="email_change_requests")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_change_requests")
    requested_email = models.EmailField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_email_change_requests")
    is_email_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_email_change_requests")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee} -> {self.requested_email}"

    def mark_verified(self):
        self.is_email_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=["is_email_verified", "verified_at", "updated_at"])

    @transaction.atomic
    def approve(self, approved_by=None):
        if self.status != self.Status.PENDING or not self.is_email_verified:
            return False
        User = get_user_model()
        if User.objects.filter(email__iexact=self.requested_email).exclude(pk=self.employee_id).exists():
            return False
        old_email = (self.employee.email or "").lower().strip()
        new_email = self.requested_email.lower().strip()
        self.employee.email = new_email
        self.employee.username = new_email
        self.employee.save(update_fields=["email", "username"])
        signup = SignupRequest.objects.filter(user=self.employee).first()
        if signup:
            signup.email = new_email
            signup.save(update_fields=["email", "updated_at"])
        SignupRequest.objects.filter(email__iexact=old_email, user__isnull=True).update(email=new_email)
        EmployeeInvite.objects.filter(company=self.company, accepted_user=self.employee).update(email=new_email)
        EmployeeInvite.objects.filter(company=self.company, email__iexact=old_email, accepted_user__isnull=True).update(email=new_email)
        self.status = self.Status.APPROVED
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return True


class EmployeeRoleChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="role_change_requests")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_change_requests")
    current_role = models.CharField(max_length=32, choices=Role.choices)
    requested_role = models.CharField(max_length=32, choices=Role.choices)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_role_change_requests")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_role_change_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee} {self.current_role} -> {self.requested_role}"

    @transaction.atomic
    def approve(self, reviewed_by=None, review_note=""):
        if self.status != self.Status.PENDING:
            return False
        profile = self.employee.profile
        if profile.role != self.current_role or profile.role == self.requested_role:
            return False
        profile.role = self.requested_role
        if not profile.employee_code:
            from .employee_codes import next_employee_code
            profile.employee_code = next_employee_code(self.requested_role, company=self.company)
            profile.save(update_fields=["role", "employee_code", "updated_at"])
        else:
            profile.save(update_fields=["role", "updated_at"])
        SignupRequest.objects.filter(user=self.employee).update(approved_role=self.requested_role, updated_at=timezone.now())
        EmployeeInvite.objects.filter(company=self.company, accepted_user=self.employee).update(role=self.requested_role)
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_note = review_note
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        return True

    def reject(self, reviewed_by=None, review_note=""):
        if self.status != self.Status.PENDING:
            return False
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_note = review_note
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        return True

    def reopen(self):
        if self.status == self.Status.PENDING:
            return False
        self.status = self.Status.PENDING
        self.reviewed_by = None
        self.reviewed_at = None
        self.review_note = ""
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        return True
