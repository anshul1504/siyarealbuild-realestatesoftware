import re

from django import forms

from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    CompanyEvent,
    CompanyProfile,
    DesignationCodeRule,
    EmployeeEmailChangeRequest,
    EmployeeRoleChangeRequest,
    EmployeeInvite,
    Meeting,
    ReferralSetting,
    Role,
    RoleMatrixRule,
    RoleTarget,
    SignupRequest,
    SignupRequestStatus,
    SoftwarePopup,
    UserProfile,
)


PHONE_INPUT_ATTRS = {
    "class": "form-control indian-phone-input",
    "placeholder": "+91 9876543210",
    "autocomplete": "tel",
    "inputmode": "tel",
    "data-country-code": "+91",
}


def normalize_indian_phone(value):
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[2:]
    digits = digits[:10]
    return f"+91 {digits}" if digits else "+91 "


class EmailLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "info@example.com",
                "autocomplete": "email",
                "id": "loginEmail",
            }
        )
    )


class SignupRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].initial = self.fields["phone"].initial or "+91 "

    class Meta:
        model = SignupRequest
        fields = ["name", "phone", "email", "requested_role", "channel_partner_reference"]
        labels = {"channel_partner_reference": "Referral Code"}
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Full Name", "autocomplete": "name", "id": "registerName"}
            ),
            "phone": forms.TextInput(attrs={**PHONE_INPUT_ATTRS, "id": "registerPhone"}),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "info@example.com", "autocomplete": "email", "id": "registerEmail"}
            ),
            "requested_role": forms.Select(attrs={"class": "form-control", "id": "registerRole"}),
            "channel_partner_reference": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Referrer employee code or email", "id": "registerInviteCode"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError("This email is already approved. Please login.")

        existing_signup = SignupRequest.objects.filter(email__iexact=email).first()
        if existing_signup:
            if (
                existing_signup.status == SignupRequestStatus.OTP_PENDING
                and not existing_signup.is_email_verified
            ):
                self.allow_existing_signup_retry = True
                return email
            if existing_signup.status == SignupRequestStatus.REJECTED:
                raise forms.ValidationError("This email signup request was rejected. Please contact admin.")
            raise forms.ValidationError("This email is already registered for signup approval.")
        return email

    def validate_unique(self):
        if getattr(self, "allow_existing_signup_retry", False):
            return
        super().validate_unique()

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data["phone"])
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone


class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "class": "form-control otp-input",
                "id": "otpCode",
            }
        ),
    )


class InviteOTPVerifyForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "employee@example.com"}))
    code = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={"class": "form-control otp-input", "placeholder": "000000", "inputmode": "numeric"}),
    )


class UserProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}))

    class Meta:
        model = UserProfile
        fields = [
            "profile_image",
            "phone",
            "designation",
            "date_of_birth",
            "gender",
            "blood_group",
            "marital_status",
            "personal_email",
            "aadhaar_number",
            "aadhaar_document",
            "pan_number",
            "pan_document",
            "emergency_contact_name",
            "emergency_contact_phone",
            "department",
            "reporting_manager",
            "joining_date",
            "work_location",
            "territory",
            "channel_partner_reference",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "bank_ifsc",
            "address",
            "city",
            "state",
            "pincode",
        ]
        widgets = {
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "designation": forms.TextInput(attrs={"class": "form-control", "placeholder": "Designation"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "gender": forms.Select(attrs={"class": "form-control"}),
            "blood_group": forms.TextInput(attrs={"class": "form-control", "placeholder": "B+ / O+ / AB-"}),
            "marital_status": forms.Select(attrs={"class": "form-control"}),
            "personal_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "personal@example.com"}),
            "aadhaar_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "12 digit Aadhaar number"}),
            "aadhaar_document": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*"}),
            "pan_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "ABCDE1234F"}),
            "pan_document": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*"}),
            "emergency_contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Emergency contact name"}),
            "emergency_contact_phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "Sales, Marketing, Operations"}),
            "reporting_manager": forms.TextInput(attrs={"class": "form-control", "placeholder": "Reporting manager"}),
            "joining_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "work_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "Office / branch / site"}),
            "territory": forms.TextInput(attrs={"class": "form-control", "placeholder": "Area, city, or sales territory"}),
            "channel_partner_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "Channel partner reference"}),
            "bank_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Bank name"}),
            "bank_account_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account holder name"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account number"}),
            "bank_ifsc": forms.TextInput(attrs={"class": "form-control", "placeholder": "IFSC code"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Personal address"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "pincode": forms.TextInput(attrs={"class": "form-control", "placeholder": "452001"}),
        }
        labels = {
            "date_of_birth": "Date of Birth",
            "personal_email": "Personal Email",
            "aadhaar_number": "Aadhaar Number",
            "aadhaar_document": "Aadhaar Document",
            "pan_number": "PAN Number",
            "pan_document": "PAN Document",
            "emergency_contact_name": "Emergency Contact Name",
            "emergency_contact_phone": "Emergency Contact Phone",
            "reporting_manager": "Reporting Manager",
            "joining_date": "Joining Date",
            "work_location": "Work Location",
            "channel_partner_reference": "Channel Partner Reference",
            "bank_ifsc": "Bank IFSC",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = self.user.get_full_name() or self.user.first_name
        self.fields["email"].initial = self.user.email
        if not self.instance.phone:
            self.fields["phone"].initial = "+91 "
        if not self.instance.emergency_contact_phone:
            self.fields["emergency_contact_phone"].initial = "+91 "

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exclude(id=self.user.id).exists():
            raise forms.ValidationError("This email is already used by another account.")
        if SignupRequest.objects.filter(email__iexact=email).exclude(user=self.user).exists():
            raise forms.ValidationError("This email is already used by another signup request.")
        return email

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""

    def clean_emergency_contact_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("emergency_contact_phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit emergency mobile number.")
        return phone if digits else ""

    def clean_pan_number(self):
        value = (self.cleaned_data.get("pan_number") or "").upper().strip()
        if value and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value):
            raise forms.ValidationError("Enter a valid PAN number.")
        return value

    def clean_aadhaar_number(self):
        value = re.sub(r"\D", "", self.cleaned_data.get("aadhaar_number") or "")
        if value and len(value) != 12:
            raise forms.ValidationError("Enter a valid 12 digit Aadhaar number.")
        return value

    def clean_bank_ifsc(self):
        value = (self.cleaned_data.get("bank_ifsc") or "").upper().strip()
        if value and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", value):
            raise forms.ValidationError("Enter a valid IFSC code.")
        return value

    def clean_bank_account_number(self):
        value = (self.cleaned_data.get("bank_account_number") or "").strip()
        if value and not re.fullmatch(r"[0-9]{6,20}", value):
            raise forms.ValidationError("Enter a valid bank account number.")
        return value

    def clean_aadhaar_document(self):
        return self._clean_profile_document("aadhaar_document")

    def clean_pan_document(self):
        return self._clean_profile_document("pan_document")

    def _clean_profile_document(self, field_name):
        document = self.cleaned_data.get(field_name)
        if not document or not hasattr(document, "size"):
            return document
        if document.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Document size must be 5 MB or less.")
        content_type = getattr(document, "content_type", "")
        allowed = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        if content_type and content_type not in allowed:
            raise forms.ValidationError("Upload PDF, JPG, PNG, or WebP only.")
        return document

    def clean_pincode(self):
        value = (self.cleaned_data.get("pincode") or "").strip()
        if value and not re.fullmatch(r"[1-9][0-9]{5}", value):
            raise forms.ValidationError("Enter a valid 6 digit pincode.")
        return value

    def save(self, commit=True, skip_email=False):
        profile = super().save(commit=False)
        full_name = self.cleaned_data["full_name"].strip()
        parts = full_name.split(" ", 1)
        self.user.first_name = parts[0] if parts else ""
        self.user.last_name = parts[1] if len(parts) > 1 else ""
        if not skip_email:
            self.user.email = self.cleaned_data["email"].lower().strip()
            self.user.username = self.user.email or self.user.username
        if commit:
            update_fields = ["first_name", "last_name"]
            if not skip_email:
                update_fields += ["email", "username"]
            self.user.save(update_fields=update_fields)
            profile.save()
        return profile


class CompanyProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.phone:
            self.fields["phone"].initial = "+91 "

    class Meta:
        model = CompanyProfile
        fields = [
            "logo",
            "name",
            "tagline",
            "description",
            "phone",
            "phone_2",
            "phone_3",
            "email",
            "email_2",
            "email_3",
            "website",
            "gst_number",
            "rera_number",
            "cin_number",
            "pan_number",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "bank_ifsc",
            "upi_id",
            "opening_time",
            "closing_time",
            "weekly_off_days",
            "holiday_notes",
            "address",
            "city",
            "state",
            "pincode",
        ]
        widgets = {
            "logo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Company name"}),
            "phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "phone_2": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "phone_3": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "company@example.com"}),
            "email_2": forms.EmailInput(attrs={"class": "form-control", "placeholder": "support@example.com"}),
            "email_3": forms.EmailInput(attrs={"class": "form-control", "placeholder": "sales@example.com"}),
            "website": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://example.com"}),
            "gst_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "GST number"}),
            "rera_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "RERA number"}),
            "cin_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "CIN number"}),
            "pan_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "PAN number"}),
            "bank_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Bank name"}),
            "bank_account_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account holder name"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account number"}),
            "bank_ifsc": forms.TextInput(attrs={"class": "form-control", "placeholder": "IFSC code"}),
            "upi_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "company@upi"}),
            "opening_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "closing_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "weekly_off_days": forms.TextInput(attrs={"class": "form-control", "placeholder": "Sunday or Saturday, Sunday"}),
            "holiday_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Holiday dates or off-day notes"}),
            "tagline": forms.TextInput(attrs={"class": "form-control", "placeholder": "Company tagline"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Company description"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Company address"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "pincode": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Company name is required.")
        return name

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if not email:
            raise forms.ValidationError("Primary email is required.")
        return email

    def clean_website(self):
        website = (self.cleaned_data.get("website") or "").strip()
        if website.startswith("http://"):
            website = f"https://{website.removeprefix('http://')}"
        elif website and not website.startswith("https://"):
            website = f"https://{website}"
        return website

    def clean_gst_number(self):
        value = (self.cleaned_data.get("gst_number") or "").upper().strip()
        if value and not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]", value):
            raise forms.ValidationError("Enter a valid 15 character GST number.")
        return value

    def clean_pan_number(self):
        value = (self.cleaned_data.get("pan_number") or "").upper().strip()
        if value and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value):
            raise forms.ValidationError("Enter a valid PAN number.")
        return value

    def clean_cin_number(self):
        value = (self.cleaned_data.get("cin_number") or "").upper().strip()
        if value and len(value) != 21:
            raise forms.ValidationError("CIN must be 21 characters.")
        return value

    def clean_bank_ifsc(self):
        value = (self.cleaned_data.get("bank_ifsc") or "").upper().strip()
        if value and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", value):
            raise forms.ValidationError("Enter a valid IFSC code.")
        return value

    def clean_bank_account_number(self):
        value = (self.cleaned_data.get("bank_account_number") or "").strip()
        if value and not re.fullmatch(r"[0-9]{6,20}", value):
            raise forms.ValidationError("Enter a valid bank account number.")
        return value

    def clean_upi_id(self):
        value = (self.cleaned_data.get("upi_id") or "").lower().strip()
        if value and not re.fullmatch(r"[a-z0-9.\-_]{2,}@[a-z0-9.\-_]{2,}", value):
            raise forms.ValidationError("Enter a valid UPI ID.")
        return value

    def clean_pincode(self):
        value = (self.cleaned_data.get("pincode") or "").strip()
        if value and not re.fullmatch(r"[1-9][0-9]{5}", value):
            raise forms.ValidationError("Enter a valid 6 digit pincode.")
        return value

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "size") and logo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Logo size must be 2 MB or less.")
        return logo

    def clean_phone(self):
        return self._clean_optional_phone("phone")

    def clean_phone_2(self):
        return self._clean_optional_phone("phone_2")

    def clean_phone_3(self):
        return self._clean_optional_phone("phone_3")

    def _clean_optional_phone(self, field_name):
        phone = normalize_indian_phone(self.cleaned_data.get(field_name))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""


class EmployeeInviteForm(forms.ModelForm):
    def __init__(self, *args, company=None, allowed_roles=None, **kwargs):
        self.company = company
        self.allowed_roles = set(allowed_roles or [choice[0] for choice in Role.choices])
        super().__init__(*args, **kwargs)
        self.fields["phone"].initial = self.fields["phone"].initial or "+91 "
        self.fields["role"].choices = [choice for choice in Role.choices if choice[0] in self.allowed_roles]

    class Meta:
        model = EmployeeInvite
        fields = ["name", "email", "phone", "role", "employee_code", "note"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Employee name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "employee@example.com"}),
            "phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "role": forms.Select(attrs={"class": "form-control"}),
            "employee_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Employee code"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Invite note"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError("This email already has an active account.")
        existing_invites = EmployeeInvite.objects.filter(company=self.company, email__iexact=email).exclude(status=EmployeeInvite.Status.REJECTED)
        if self.instance.pk:
            existing_invites = existing_invites.exclude(pk=self.instance.pk)
        if self.company and existing_invites.exists():
            raise forms.ValidationError("An invite for this email already exists.")
        return email

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""

    def clean_role(self):
        role = self.cleaned_data["role"]
        if role not in self.allowed_roles:
            raise forms.ValidationError("You cannot invite employees for this role.")
        return role


class AddEmployeeForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Employee name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "employee@example.com"}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs=PHONE_INPUT_ATTRS))
    role = forms.ChoiceField(choices=Role.choices, widget=forms.Select(attrs={"class": "form-control"}))
    employee_code = forms.CharField(required=False, max_length=32, widget=forms.TextInput(attrs={"class": "form-control"}))
    personal_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": "form-control"}))
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    gender = forms.ChoiceField(required=False, choices=[("", "---------"), *UserProfile.Gender.choices], widget=forms.Select(attrs={"class": "form-control"}))
    blood_group = forms.CharField(required=False, max_length=8, widget=forms.TextInput(attrs={"class": "form-control"}))
    marital_status = forms.ChoiceField(required=False, choices=[("", "---------"), *UserProfile.MaritalStatus.choices], widget=forms.Select(attrs={"class": "form-control"}))
    designation = forms.CharField(required=False, max_length=80, widget=forms.TextInput(attrs={"class": "form-control"}))
    department = forms.CharField(required=False, max_length=80, widget=forms.TextInput(attrs={"class": "form-control"}))
    reporting_manager = forms.CharField(required=False, max_length=120, widget=forms.TextInput(attrs={"class": "form-control"}))
    office_location = forms.ChoiceField(required=False, choices=[("", "Select office")], widget=forms.Select(attrs={"class": "form-control"}))
    custom_work_location = forms.CharField(required=False, max_length=160, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Custom office address"}))
    joining_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    aadhaar_number = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={"class": "form-control"}))
    aadhaar_document = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*"}))
    pan_number = forms.CharField(required=False, max_length=16, widget=forms.TextInput(attrs={"class": "form-control"}))
    pan_document = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*"}))
    emergency_contact_name = forms.CharField(required=False, max_length=120, widget=forms.TextInput(attrs={"class": "form-control"}))
    emergency_contact_phone = forms.CharField(required=False, widget=forms.TextInput(attrs=PHONE_INPUT_ATTRS))
    bank_name = forms.CharField(required=False, max_length=120, widget=forms.TextInput(attrs={"class": "form-control"}))
    bank_account_name = forms.CharField(required=False, max_length=160, widget=forms.TextInput(attrs={"class": "form-control"}))
    bank_account_number = forms.CharField(required=False, max_length=40, widget=forms.TextInput(attrs={"class": "form-control"}))
    bank_ifsc = forms.CharField(required=False, max_length=20, widget=forms.TextInput(attrs={"class": "form-control"}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
    city = forms.CharField(required=False, max_length=80, widget=forms.TextInput(attrs={"class": "form-control"}))
    state = forms.CharField(required=False, max_length=80, widget=forms.TextInput(attrs={"class": "form-control"}))
    pincode = forms.CharField(required=False, max_length=12, widget=forms.TextInput(attrs={"class": "form-control"}))

    def __init__(self, *args, company=None, allowed_roles=None, **kwargs):
        self.allowed_roles = set(allowed_roles or [Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER])
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [choice for choice in Role.choices if choice[0] in self.allowed_roles]
        self.fields["phone"].initial = self.fields["phone"].initial or "+91 "
        self.fields["emergency_contact_phone"].initial = self.fields["emergency_contact_phone"].initial or "+91 "
        locations = []
        if company:
            head_office = ", ".join(part for part in [company.address, company.city, company.state, company.pincode] if part)
            if head_office:
                locations.append(("head_office", f"Head Office - {head_office}"))
            locations.extend(
                (location, location)
                for location in UserProfile.objects.filter(company=company).exclude(work_location="").values_list("work_location", flat=True).distinct()
            )
        self.fields["office_location"].choices = [("", "Select office"), *locations, ("custom", "Other / custom location")]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email already exists.")
        return email

    def clean_role(self):
        role = self.cleaned_data["role"]
        if role not in self.allowed_roles:
            raise forms.ValidationError("You cannot add an employee with this role.")
        return role

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""

    def clean_emergency_contact_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("emergency_contact_phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""


class TeamRoleForm(forms.Form):
    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        members = User.objects.filter(profile__company=company).select_related("profile")
        for member in members:
            self.fields[f"role_{member.id}"] = forms.ChoiceField(
                label=member.get_full_name() or member.email or member.username,
                choices=Role.choices,
                initial=member.profile.role,
                widget=forms.Select(attrs={"class": "form-control"}),
            )

    def save(self, company):
        User = get_user_model()
        members = User.objects.filter(profile__company=company).select_related("profile")
        prefix_map = {
            Role.COMPANY_OWNER: "OWN",
            Role.MANAGER: "MGR",
            Role.TL: "TL",
            Role.EXECUTIVE: "EXE",
            Role.CHANNEL_PARTNER: "CP",
        }
        for member in members:
            role = self.cleaned_data.get(f"role_{member.id}")
            if role:
                member.profile.role = role
                if not member.profile.employee_code:
                    prefix = prefix_map.get(role, "EMP")
                    next_number = UserProfile.objects.filter(company=company, role=role).count() + 1
                    member.profile.employee_code = f"{prefix}-{next_number:04d}"
                    member.profile.save(update_fields=["role", "employee_code", "updated_at"])
                else:
                    member.profile.save(update_fields=["role", "updated_at"])


class OwnerCompanyProfileForm(CompanyProfileForm):
    pass


class DesignationCodeRuleForm(forms.ModelForm):
    class Meta:
        model = DesignationCodeRule
        fields = ["role", "designation", "prefix", "next_number", "is_active"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control", "placeholder": "Executive"}),
            "prefix": forms.TextInput(attrs={"class": "form-control", "placeholder": "EXE"}),
            "next_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def clean_designation(self):
        return (self.cleaned_data.get("designation") or "").strip()

    def clean_prefix(self):
        value = (self.cleaned_data.get("prefix") or "").upper().strip()
        if not re.fullmatch(r"[A-Z0-9]{2,16}", value):
            raise forms.ValidationError("Use 2-16 letters or numbers only.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        company = self.company or getattr(self.instance, "company", None)
        role = cleaned_data.get("role")
        designation = cleaned_data.get("designation")
        if company and role and designation:
            duplicate = DesignationCodeRule.objects.filter(
                company=company,
                role=role,
                designation__iexact=designation,
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError("A serial rule already exists for this role and designation.")
        return cleaned_data


class InviteBulkActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(("approve", "Approve"), ("reject", "Reject"), ("pending", "Move to Pending")),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    invite_ids = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, invites, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invite_ids"].choices = [(invite.id, str(invite)) for invite in invites]


class SignupBulkActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(("approve", "Approve"), ("reject", "Reject"), ("pending", "Move to Pending")),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    signup_ids = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, signups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signup_ids"].choices = [(signup.id, str(signup)) for signup in signups]


class SignupRequestReviewForm(forms.ModelForm):
    class Meta:
        model = SignupRequest
        fields = ["approved_role", "admin_note"]
        widgets = {
            "approved_role": forms.Select(attrs={"class": "form-control"}),
            "admin_note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Internal review note or rejection reason"}),
        }


class SignupRequestCustomEmailForm(forms.Form):
    subject = forms.CharField(
        max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Email subject"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Write the message to the applicant"}),
    )


class MeetingForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=Role.choices,
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Meeting
        fields = ["title", "description", "starts_at", "ends_at", "roles", "meeting_link", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Weekly sales review, project briefing, client follow-up"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Agenda, discussion points, preparation notes, or joining instructions"}),
            "starts_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "roles": forms.CheckboxSelectMultiple(choices=Role.choices),
            "meeting_link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://meet.google.com/..." }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meeting_link"].required = True

    def clean_roles(self):
        return self.cleaned_data.get("roles") or []

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("roles"):
            raise forms.ValidationError("Select at least one role for this online meeting.")
        if not cleaned_data.get("meeting_link"):
            raise forms.ValidationError("Online meeting link is required.")
        return cleaned_data


class CompanyEventForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=Role.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = CompanyEvent
        fields = ["title", "caption", "description", "cover_image", "starts_at", "ends_at", "is_global", "roles", "show_as_popup", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Project launch, team celebration, open house"}),
            "caption": forms.TextInput(attrs={"class": "form-control", "placeholder": "Short social post caption"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Event details, agenda, venue notes, or announcement copy"}),
            "cover_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "starts_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "is_global": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "roles": forms.CheckboxSelectMultiple(choices=Role.choices),
            "show_as_popup": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_roles(self):
        return self.cleaned_data.get("roles") or []

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("is_global") and not cleaned_data.get("roles"):
            raise forms.ValidationError("Select at least one role when event is not global.")
        return cleaned_data



class ReferralSettingForm(forms.ModelForm):
    class Meta:
        model = ReferralSetting
        fields = [
            "is_active",
            "referrer_reward_amount",
            "referrer_coupon_code",
            "referred_reward_amount",
            "referred_coupon_code",
            "terms",
        ]
        labels = {
            "is_active": "Activate referral rewards",
            "referrer_reward_amount": "Reward for person who refers",
            "referrer_coupon_code": "Coupon for person who refers",
            "referred_reward_amount": "Reward for new Channel Partner",
            "referred_coupon_code": "Coupon for new Channel Partner",
            "terms": "Referral terms",
        }
        widgets = {
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "referrer_reward_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0, "placeholder": "1000.00"}),
            "referrer_coupon_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "REFERRER1000"}),
            "referred_reward_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0, "placeholder": "500.00"}),
            "referred_coupon_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "WELCOMECP500"}),
            "terms": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Reward is released when referred signup is approved as Channel Partner."}),
        }

    def clean_referrer_coupon_code(self):
        return (self.cleaned_data.get("referrer_coupon_code") or "").upper().strip()

    def clean_referred_coupon_code(self):
        return (self.cleaned_data.get("referred_coupon_code") or "").upper().strip()

    def clean_referrer_reward_amount(self):
        amount = self.cleaned_data.get("referrer_reward_amount")
        if amount is not None and amount < 0:
            raise forms.ValidationError("Reward amount cannot be negative.")
        return amount

    def clean_referred_reward_amount(self):
        amount = self.cleaned_data.get("referred_reward_amount")
        if amount is not None and amount < 0:
            raise forms.ValidationError("Reward amount cannot be negative.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        referrer_amount = cleaned_data.get("referrer_reward_amount")
        referred_amount = cleaned_data.get("referred_reward_amount")
        referrer_coupon = cleaned_data.get("referrer_coupon_code")
        referred_coupon = cleaned_data.get("referred_coupon_code")
        if referrer_amount and referrer_amount > 0 and referrer_coupon:
            self.add_error("referrer_coupon_code", "Choose either reward amount or coupon for the referrer, not both.")
        if referred_amount and referred_amount > 0 and referred_coupon:
            self.add_error("referred_coupon_code", "Choose either reward amount or coupon for the new Channel Partner, not both.")
        return cleaned_data


class RoleTargetForm(forms.ModelForm):
    class Meta:
        model = RoleTarget
        fields = ["title", "role", "employee", "target_value", "metric", "starts_on", "ends_on", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-control"}),
            "employee": forms.Select(attrs={"class": "form-control"}),
            "target_value": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "metric": forms.TextInput(attrs={"class": "form-control"}),
            "starts_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "ends_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["employee"].queryset = get_user_model().objects.filter(profile__company=company)
        self.fields["employee"].required = False
        self.fields["role"].required = False


class OfferImageInput(forms.ClearableFileInput):
    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        input_html = super(forms.ClearableFileInput, self).render(name, None, attrs, renderer)
        if not value:
            return input_html
        checkbox_html = ""
        if not self.is_required:
            checkbox_html = format_html(
                '<label><input type="checkbox" name="{}" id="{}"> Remove image</label>',
                self.clear_checkbox_name(name),
                self.clear_checkbox_id(name),
            )
        return format_html(
            '<div class="offer-image-current-file"><span>Existing image is attached.</span>{}</div>{}',
            mark_safe(checkbox_html),
            mark_safe(input_html),
        )


class SoftwarePopupForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=Role.choices,
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = SoftwarePopup
        fields = ["title", "message", "deal_label", "offer_image", "starts_at", "ends_at", "roles", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Festive offer, site visit offer, booking discount"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Short popup message shown below the offer image"}),
            "deal_label": forms.TextInput(attrs={"class": "form-control", "placeholder": "Limited Offer, New Launch, Hot Deal"}),
            "offer_image": OfferImageInput(attrs={"class": "form-control", "accept": "image/*"}),
            "starts_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "roles": forms.CheckboxSelectMultiple(choices=Role.choices),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_roles(self):
        return self.cleaned_data.get("roles") or []

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("roles"):
            raise forms.ValidationError("Select at least one role for popup visibility.")
        if not cleaned_data.get("offer_image") and not getattr(self.instance, "offer_image", None):
            raise forms.ValidationError("Upload an offer image for this popup.")
        return cleaned_data


class RoleMatrixRuleForm(forms.ModelForm):
    class Meta:
        model = RoleMatrixRule
        fields = ["role", "module", "can_view", "can_create", "can_update", "can_delete"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-control"}),
            "module": forms.TextInput(attrs={"class": "form-control", "placeholder": "Properties"}),
            "can_view": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "can_create": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "can_update": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "can_delete": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EmployeeEmailChangeRequestForm(forms.ModelForm):
    class Meta:
        model = EmployeeEmailChangeRequest
        fields = ["employee", "requested_email", "reason"]
        widgets = {
            "employee": forms.Select(attrs={"class": "form-control"}),
            "requested_email": forms.EmailInput(attrs={"class": "form-control"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, company, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = get_user_model().objects.filter(profile__company=company)

    def clean_requested_email(self):
        email = self.cleaned_data["requested_email"].lower().strip()
        employee = self.cleaned_data.get("employee")
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exclude(id=getattr(employee, "id", None)).exists():
            raise forms.ValidationError("This email is already used by another employee.")
        pending = EmployeeEmailChangeRequest.objects.filter(
            company=self.company,
            requested_email__iexact=email,
            status=EmployeeEmailChangeRequest.Status.PENDING,
        )
        if self.instance.pk:
            pending = pending.exclude(pk=self.instance.pk)
        if pending.exists():
            raise forms.ValidationError("This email already has a pending change request.")
        return email


class EmployeeRoleChangeRequestForm(forms.ModelForm):
    class Meta:
        model = EmployeeRoleChangeRequest
        fields = ["employee", "requested_role", "reason"]
        widgets = {
            "employee": forms.Select(attrs={"class": "form-control"}),
            "requested_role": forms.Select(attrs={"class": "form-control"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Why should this employee role change?"}),
        }

    def __init__(self, *args, company, allowed_roles=None, **kwargs):
        self.company = company
        self.allowed_roles = set(allowed_roles or [Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER])
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = get_user_model().objects.filter(profile__company=company).exclude(profile__role=Role.COMPANY_OWNER)
        self.fields["requested_role"].choices = [choice for choice in Role.choices if choice[0] in self.allowed_roles]

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get("employee")
        requested_role = cleaned_data.get("requested_role")
        if employee and requested_role:
            current_role = employee.profile.role
            if current_role == requested_role:
                raise forms.ValidationError("Requested role must be different from the current role.")
            if EmployeeRoleChangeRequest.objects.filter(
                company=self.company,
                employee=employee,
                status=EmployeeRoleChangeRequest.Status.PENDING,
            ).exists():
                raise forms.ValidationError("This employee already has a pending role change request.")
        return cleaned_data


class TeamEmailMessageForm(forms.Form):
    role = forms.ChoiceField(
        choices=[("", "All visible roles"), *Role.choices],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    department = forms.ChoiceField(
        choices=[("", "All departments")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject = forms.CharField(
        max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Email subject"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7, "placeholder": "Write message for selected employees"}),
    )

    def __init__(self, *args, departments=None, **kwargs):
        super().__init__(*args, **kwargs)
        department_choices = [("", "All departments")]
        department_choices.extend((department, department) for department in departments or [])
        self.fields["department"].choices = department_choices
