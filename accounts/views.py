from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .email_utils import send_otp_email
from .forms import CompanyProfileForm, EmailLoginForm, EmployeeInviteForm, OTPVerifyForm, SignupRequestForm, TeamRoleForm, UserProfileForm
from .models import CompanyProfile, EmailOTP, EmployeeInvite, Role, SignupRequest, SignupRequestStatus, UserProfile


@require_http_methods(["GET", "POST"])
def request_otp(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    form = EmailLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        approved_request = SignupRequest.objects.filter(
            email__iexact=email,
            status=SignupRequestStatus.APPROVED,
            user__isnull=False,
        ).first()
        if not user or not approved_request:
            messages.error(request, "Your account is not approved yet. Please submit a signup request first.")
            return redirect("accounts:signup")

        otp = EmailOTP.create_for_email(email)
        request.session["otp_email"] = email
        request.session["otp_id"] = otp.id
        request.session["otp_purpose"] = "login"
        send_otp_email(to_email=email, code=otp.code, purpose="login")
        messages.success(request, "OTP sent to your email.")
        return redirect("accounts:verify")

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def signup_request(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    form = SignupRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        existing_user = get_user_model().objects.filter(email__iexact=email, is_active=True).exists()
        if existing_user:
            messages.error(request, "This email is already approved. Please login.")
            return redirect("accounts:login")

        signup = SignupRequest.objects.create(
            email=email,
            name=form.cleaned_data["name"],
            phone=form.cleaned_data["phone"],
            requested_role=form.cleaned_data["requested_role"],
            channel_partner_reference=form.cleaned_data["channel_partner_reference"],
            status=SignupRequestStatus.OTP_PENDING,
            is_email_verified=False,
        )
        otp = EmailOTP.create_for_email(email, signup_request=signup)
        request.session["otp_email"] = email
        request.session["otp_id"] = otp.id
        request.session["otp_purpose"] = "signup"
        request.session["signup_request_id"] = signup.id
        send_otp_email(to_email=email, code=otp.code, purpose="signup")
        messages.success(request, "OTP sent. Verify your email to send the request to admin.")
        return redirect("accounts:verify")

    return render(request, "accounts/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def verify_otp(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    email = request.session.get("otp_email")
    otp_id = request.session.get("otp_id")
    purpose = request.session.get("otp_purpose", "login")
    if not email or not otp_id:
        messages.error(request, "Please request a fresh OTP.")
        return redirect("accounts:login")

    form = OTPVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp = EmailOTP.objects.filter(id=otp_id, email=email, is_used=False).first()
        if not otp or otp.is_expired:
            messages.error(request, "OTP expired. Request a new one.")
            return redirect("accounts:login")

        if otp.attempts >= 5:
            messages.error(request, "Too many attempts. Request a new OTP.")
            return redirect("accounts:login")

        if form.cleaned_data["code"] != otp.code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            messages.error(request, "Invalid OTP.")
        else:
            otp.is_used = True
            if purpose == "signup":
                signup = SignupRequest.objects.filter(id=request.session.get("signup_request_id"), email=email).first()
                if not signup:
                    messages.error(request, "Signup request not found. Please submit again.")
                    return redirect("accounts:signup")
                signup.is_email_verified = True
                signup.status = SignupRequestStatus.PENDING_APPROVAL
                signup.save(update_fields=["is_email_verified", "status", "updated_at"])
                otp.signup_request = signup
                otp.save(update_fields=["is_used", "signup_request"])
                request.session.pop("otp_email", None)
                request.session.pop("otp_id", None)
                request.session.pop("otp_purpose", None)
                request.session.pop("signup_request_id", None)
                messages.success(request, "Signup request sent to admin. You can login after approval.")
                return redirect("accounts:login")

            user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
            if not user:
                messages.error(request, "Account is not approved yet.")
                return redirect("accounts:login")
            otp.user = user
            otp.save(update_fields=["is_used", "user"])
            login(request, user)
            request.session.pop("otp_email", None)
            request.session.pop("otp_id", None)
            request.session.pop("otp_purpose", None)
            return redirect("properties:dashboard")

    return render(request, "accounts/verify.html", {"form": form, "email": email, "purpose": purpose})


@require_http_methods(["POST"])
def resend_otp(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    email = request.session.get("otp_email")
    purpose = request.session.get("otp_purpose", "login")
    signup_request_id = request.session.get("signup_request_id")
    if not email:
        messages.error(request, "Please request a fresh OTP.")
        return redirect("accounts:login")

    signup = None
    if purpose == "signup":
        signup = SignupRequest.objects.filter(id=signup_request_id, email__iexact=email).first()
        if not signup:
            messages.error(request, "Signup request not found. Please submit again.")
            return redirect("accounts:signup")

    otp = EmailOTP.create_for_email(email, signup_request=signup)
    request.session["otp_id"] = otp.id
    send_otp_email(to_email=email, code=otp.code, purpose=purpose)
    messages.success(request, "A new OTP has been sent to your email.")
    return redirect("accounts:verify")


def sign_out(request):
    logout(request)
    return render(request, "accounts/logout.html")


def _profile_context(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    signup = SignupRequest.objects.filter(user=request.user).first() or SignupRequest.objects.filter(email__iexact=request.user.email).first()
    changed = False
    if signup:
        if not user_profile.phone and signup.phone:
            user_profile.phone = signup.phone
            changed = True
        signup_role = signup.approved_role or signup.requested_role
        if signup_role and user_profile.role == Role.EXECUTIVE:
            user_profile.role = signup_role
            changed = True
        if not user_profile.employee_code and signup.channel_partner_reference:
            user_profile.employee_code = signup.channel_partner_reference
            changed = True
    if changed:
        user_profile.save(update_fields=["phone", "role", "employee_code", "updated_at"])
    company = user_profile.company or CompanyProfile.objects.filter(owner=request.user).first()
    if not company:
        company = CompanyProfile.objects.create(owner=request.user, email=request.user.email)
        user_profile.company = company
        user_profile.role = Role.COMPANY_OWNER
        user_profile.employee_code = ""
        user_profile.save(update_fields=["company", "role", "updated_at"])

    is_owner = company.owner_id == request.user.id or user_profile.role == Role.COMPANY_OWNER
    if not user_profile.employee_code:
        prefix_map = {
            Role.COMPANY_OWNER: "OWN",
            Role.MANAGER: "MGR",
            Role.TL: "TL",
            Role.EXECUTIVE: "EXE",
            Role.CHANNEL_PARTNER: "CP",
        }
        prefix = prefix_map.get(user_profile.role, "EMP")
        next_number = UserProfile.objects.filter(role=user_profile.role).count() + 1
        user_profile.employee_code = f"{prefix}-{next_number:04d}"
        user_profile.save(update_fields=["employee_code", "updated_at"])
    return user_profile, company, is_owner


@login_required
def profile(request):
    user_profile, company, is_owner = _profile_context(request)
    profile_form = UserProfileForm(request.POST or None, request.FILES or None, instance=user_profile, user=request.user, prefix="profile")

    if request.method == "POST":
        if profile_form.is_valid():
            new_email = profile_form.cleaned_data["email"].lower().strip()
            current_email = (request.user.email or "").lower().strip()
            if new_email != current_email:
                profile_form.save(skip_email=True)
                signup = SignupRequest.objects.filter(user=request.user).first()
                if signup:
                    signup.name = request.user.get_full_name() or request.user.first_name or request.user.username
                    signup.phone = request.user.profile.phone
                    signup.save(update_fields=["name", "phone", "updated_at"])
                otp = EmailOTP.create_for_email(new_email, signup_request=signup)
                request.session["pending_email_change"] = new_email
                request.session["pending_email_otp_id"] = otp.id
                send_otp_email(to_email=new_email, code=otp.code, purpose="email_change")
                messages.success(request, "OTP sent to your new email. Verify it to complete email change.")
                return redirect("accounts:verify_email_change")

            profile_form.save()
            _sync_signup_from_user(request.user)
            messages.success(request, "Profile details updated.")
            return redirect("accounts:profile")
        messages.error(request, "Please check the form details.")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "company": company,
            "user_profile": user_profile,
            "is_owner": is_owner,
        },
    )


def _sync_signup_from_user(user):
    signup = SignupRequest.objects.filter(user=user).first()
    if signup:
        signup.name = user.get_full_name() or user.first_name or user.username
        signup.phone = user.profile.phone
        signup.email = user.email
        signup.save(update_fields=["name", "phone", "email", "updated_at"])


@login_required
@require_http_methods(["GET", "POST"])
def verify_email_change(request):
    pending_email = request.session.get("pending_email_change")
    otp_id = request.session.get("pending_email_otp_id")
    if not pending_email or not otp_id:
        messages.error(request, "Please request a fresh email change OTP.")
        return redirect("accounts:profile")

    form = OTPVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp = EmailOTP.objects.filter(id=otp_id, email=pending_email, is_used=False).first()
        if not otp or otp.is_expired:
            messages.error(request, "OTP expired. Request a new one.")
            return redirect("accounts:profile")
        if otp.attempts >= 5:
            messages.error(request, "Too many attempts. Request a new OTP.")
            return redirect("accounts:profile")
        if form.cleaned_data["code"] != otp.code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            messages.error(request, "Invalid OTP.")
        else:
            User = get_user_model()
            if User.objects.filter(email__iexact=pending_email).exclude(id=request.user.id).exists():
                messages.error(request, "This email is already used by another account.")
                return redirect("accounts:profile")
            if SignupRequest.objects.filter(email__iexact=pending_email).exclude(user=request.user).exists():
                messages.error(request, "This email is already used by another signup request.")
                return redirect("accounts:profile")
            request.user.email = pending_email
            request.user.username = pending_email
            request.user.save(update_fields=["email", "username"])
            _sync_signup_from_user(request.user)
            otp.is_used = True
            otp.user = request.user
            otp.save(update_fields=["is_used", "user"])
            request.session.pop("pending_email_change", None)
            request.session.pop("pending_email_otp_id", None)
            messages.success(request, "Email verified and updated.")
            return redirect("accounts:profile")

    return render(request, "accounts/verify_email_change.html", {"form": form, "email": pending_email})


@login_required
@require_http_methods(["POST"])
def resend_email_change_otp(request):
    pending_email = request.session.get("pending_email_change")
    if not pending_email:
        messages.error(request, "Please request a fresh email change OTP.")
        return redirect("accounts:profile")
    signup = SignupRequest.objects.filter(user=request.user).first()
    otp = EmailOTP.create_for_email(pending_email, signup_request=signup)
    request.session["pending_email_otp_id"] = otp.id
    send_otp_email(to_email=pending_email, code=otp.code, purpose="email_change")
    messages.success(request, "A new OTP has been sent to your new email.")
    return redirect("accounts:verify_email_change")


@login_required
def company_settings(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can manage company details.")
        return redirect("accounts:profile")
    form = CompanyProfileForm(request.POST or None, instance=company, prefix="company")
    if request.method == "POST":
        if form.is_valid():
            company = form.save(commit=False)
            company.owner = request.user
            company.save()
            messages.success(request, "Company details updated.")
            return redirect("accounts:company_settings")
        messages.error(request, "Please check company details.")
    return render(request, "accounts/company.html", {"form": form, "company": company, "user_profile": user_profile, "is_owner": is_owner})


@login_required
def employee_invites(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can invite employees.")
        return redirect("accounts:profile")
    form = EmployeeInviteForm(request.POST or None, prefix="invite")
    if request.method == "POST":
        if form.is_valid():
            invite = form.save(commit=False)
            invite.company = company
            invite.invited_by = request.user
            invite.save()
            messages.success(request, "Employee invite saved.")
            return redirect("accounts:employee_invites")
        messages.error(request, "Please check invite details.")
    invites = EmployeeInvite.objects.filter(company=company)
    return render(request, "accounts/invites.html", {"form": form, "invites": invites, "company": company, "user_profile": user_profile, "is_owner": is_owner})


@login_required
def access_control(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can manage role access.")
        return redirect("accounts:profile")
    form = TeamRoleForm(request.POST or None, company=company, prefix="roles")
    if request.method == "POST":
        if form.is_valid():
            form.save(company)
            messages.success(request, "Team role access updated.")
            return redirect("accounts:access_control")
        messages.error(request, "Please check role details.")
    return render(request, "accounts/access.html", {"form": form, "company": company, "user_profile": user_profile, "is_owner": is_owner})
