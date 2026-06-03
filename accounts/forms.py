from django import forms

from django.contrib.auth import get_user_model

from .models import CompanyProfile, EmployeeInvite, Role, SignupRequest, SignupRequestStatus, UserProfile


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
        labels = {"channel_partner_reference": "Employee / Invite Code"}
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
                attrs={"class": "form-control", "placeholder": "Employee or invite code", "id": "registerInviteCode"}
            ),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        User = get_user_model()
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError("This email is already approved. Please login.")

        existing_signup = SignupRequest.objects.filter(email__iexact=email).first()
        if existing_signup:
            if existing_signup.status == SignupRequestStatus.REJECTED:
                raise forms.ValidationError("This email signup request was rejected. Please contact admin.")
            raise forms.ValidationError("This email is already registered for signup approval.")
        return email

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


class UserProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}))

    class Meta:
        model = UserProfile
        fields = ["profile_image", "phone", "designation", "address", "city", "state"]
        widgets = {
            "profile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "designation": forms.TextInput(attrs={"class": "form-control", "placeholder": "Designation"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Personal address"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = self.user.get_full_name() or self.user.first_name
        self.fields["email"].initial = self.user.email
        if not self.instance.phone:
            self.fields["phone"].initial = "+91 "

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
        fields = ["name", "phone", "email", "website", "gst_number", "rera_number", "address", "city", "state"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Company name"}),
            "phone": forms.TextInput(attrs=PHONE_INPUT_ATTRS),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "company@example.com"}),
            "website": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://example.com"}),
            "gst_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "GST number"}),
            "rera_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "RERA number"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Company address"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("phone"))
        digits = "".join(ch for ch in phone if ch.isdigit())[2:]
        if digits and len(digits) != 10:
            raise forms.ValidationError("Please enter a valid 10 digit mobile number.")
        return phone if digits else ""


class EmployeeInviteForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].initial = self.fields["phone"].initial or "+91 "

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

    def clean_phone(self):
        phone = normalize_indian_phone(self.cleaned_data.get("phone"))
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
                    next_number = UserProfile.objects.filter(role=role).count() + 1
                    member.profile.employee_code = f"{prefix}-{next_number:04d}"
                    member.profile.save(update_fields=["role", "employee_code", "updated_at"])
                else:
                    member.profile.save(update_fields=["role", "updated_at"])
