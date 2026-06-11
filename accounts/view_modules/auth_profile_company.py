import csv
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.conf import settings
from django.db import models
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from ..email_utils import send_email_updated_email, send_otp_email, send_signup_pending_review_email
from ..forms import EmailLoginForm, InviteOTPVerifyForm, OTPVerifyForm, OwnerCompanyProfileForm, SignupRequestForm, UserProfileForm
from ..models import AuthenticationSupportRequest, CompanyProfile, EmailOTP, EmployeeEmailChangeRequest, EmployeeInvite, Role, SignupRequest, SignupRequestStatus, UserProfile
from ..security import auth_request_limited, client_ip, rate_limit_exceeded
from .onboarding import _next_employee_code


OTP_RESEND_WAIT_SECONDS = 60

COMPANY_EXPORT_FIELDS = (
    ("Company Name", "name"), ("Tagline", "tagline"), ("Description", "description"),
    ("Primary Phone", "phone"), ("Secondary Phone", "phone_2"), ("Third Phone", "phone_3"),
    ("Primary Email", "email"), ("Secondary Email", "email_2"), ("Third Email", "email_3"),
    ("Website", "website"), ("GST Number", "gst_number"), ("RERA Number", "rera_number"),
    ("CIN Number", "cin_number"), ("PAN Number", "pan_number"), ("Bank Name", "bank_name"),
    ("Account Name", "bank_account_name"), ("Account Number", "bank_account_number"), ("IFSC", "bank_ifsc"),
    ("UPI ID", "upi_id"), ("Opening Time", "opening_time"), ("Closing Time", "closing_time"),
    ("Weekly Off Days", "weekly_off_days"), ("Holiday Notes", "holiday_notes"), ("Address", "address"),
    ("City", "city"), ("State", "state"), ("Pincode", "pincode"), ("Last Updated", "updated_at"),
)

def _set_resend_wait(request, session_key):
    available_at = timezone.now() + timedelta(seconds=OTP_RESEND_WAIT_SECONDS)
    request.session[session_key] = available_at.isoformat()


def _resend_remaining_seconds(request, session_key):
    raw_available_at = request.session.get(session_key)
    if not raw_available_at:
        return 0
    try:
        available_at = datetime.fromisoformat(raw_available_at)
    except ValueError:
        request.session.pop(session_key, None)
        return 0
    remaining = int((available_at - timezone.now()).total_seconds())
    return max(0, remaining)


@require_http_methods(["GET", "POST"])
def request_otp(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    form = EmailLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        if auth_request_limited(request, email):
            messages.error(request, "Too many authentication requests. Please wait before trying again.")
            return redirect("accounts:login")
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
        _set_resend_wait(request, "otp_resend_available_at")
        send_otp_email(to_email=email, code=otp.code, purpose="login")
        messages.success(request, "OTP sent to your email.")
        return redirect("accounts:verify")

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def signup_request(request):
    if request.user.is_authenticated:
        return redirect("properties:dashboard")

    referral_code = (request.POST.get("referral_code") or request.GET.get("ref") or "").strip()
    initial = {"channel_partner_reference": referral_code} if referral_code else {}
    form = SignupRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        if auth_request_limited(request, email):
            messages.error(request, "Too many authentication requests. Please wait before trying again.")
            return redirect("accounts:signup")
        channel_partner_reference = referral_code if referral_code else form.cleaned_data["channel_partner_reference"]
        company = CompanyProfile.objects.order_by("id").first()
        if referral_code and not _referrer_profile_for_code(referral_code, company=company):
            form.add_error("channel_partner_reference", "This referral link is not valid. Please ask the referrer to share a fresh link from My Referrals.")
            return render(
                request,
                "accounts/signup.html",
                {
                    "form": form,
                    "referral_code": referral_code,
                    "is_referral_signup": True,
                },
            )
        existing_user = get_user_model().objects.filter(email__iexact=email, is_active=True).exists()
        if existing_user:
            messages.error(request, "This email is already approved. Please login.")
            return redirect("accounts:login")

        signup = SignupRequest.objects.filter(
            email__iexact=email,
            status=SignupRequestStatus.OTP_PENDING,
            is_email_verified=False,
        ).first()
        if signup:
            signup.name = form.cleaned_data["name"]
            signup.phone = form.cleaned_data["phone"]
            signup.channel_partner_reference = channel_partner_reference
            signup.save(update_fields=["name", "phone", "channel_partner_reference", "updated_at"])
        else:
            signup = SignupRequest.objects.create(
                email=email,
                name=form.cleaned_data["name"],
                phone=form.cleaned_data["phone"],
                channel_partner_reference=channel_partner_reference,
                status=SignupRequestStatus.OTP_PENDING,
                is_email_verified=False,
            )
        otp = EmailOTP.create_for_email(email, signup_request=signup)
        request.session["otp_email"] = email
        request.session["otp_id"] = otp.id
        request.session["otp_purpose"] = "signup"
        request.session["signup_request_id"] = signup.id
        _set_resend_wait(request, "otp_resend_available_at")
        send_otp_email(to_email=email, code=otp.code, purpose="signup")
        messages.success(request, "OTP sent. Verify your email to send the request to admin.")
        return redirect("accounts:verify")

    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
            "referral_code": referral_code,
            "is_referral_signup": bool(referral_code),
        },
    )


def _referrer_profile_for_code(referral_code, company=None, exclude_user=None):
    code = (referral_code or "").strip()
    if not code:
        return None
    profiles = UserProfile.objects.select_related("user")
    if company:
        profiles = profiles.filter(company=company)
    if exclude_user:
        profiles = profiles.exclude(user=exclude_user)
    return (
        profiles.filter(
            models.Q(employee_code__iexact=code)
            | models.Q(user__email__iexact=code)
            | models.Q(user__username__iexact=code)
        )
        .order_by("id")
        .first()
    )


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

        if not otp.matches(form.cleaned_data["code"]):
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
                send_signup_pending_review_email(to_email=email, name=signup.name)
                request.session.pop("otp_email", None)
                request.session.pop("otp_id", None)
                request.session.pop("otp_purpose", None)
                request.session.pop("signup_request_id", None)
                request.session.pop("otp_resend_available_at", None)
                messages.success(request, "Signup request sent to admin. You can login after approval.")
                return redirect("accounts:login")

            user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
            is_approved = SignupRequest.objects.filter(
                email__iexact=email,
                user=user,
                status=SignupRequestStatus.APPROVED,
                is_email_verified=True,
            ).exists()
            if not user or not is_approved:
                messages.error(request, "Account is not approved yet.")
                return redirect("accounts:login")
            otp.user = user
            otp.save(update_fields=["is_used", "user"])
            login(request, user)
            request.session.pop("otp_email", None)
            request.session.pop("otp_id", None)
            request.session.pop("otp_purpose", None)
            request.session.pop("otp_resend_available_at", None)
            return redirect("properties:dashboard")

    return render(
        request,
        "accounts/verify.html",
        {
            "form": form,
            "email": email,
            "purpose": purpose,
            "resend_remaining_seconds": _resend_remaining_seconds(request, "otp_resend_available_at"),
        },
    )


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

    remaining_seconds = _resend_remaining_seconds(request, "otp_resend_available_at")
    if remaining_seconds:
        messages.error(request, f"Please wait {remaining_seconds} seconds before resending OTP.")
        return redirect("accounts:verify")

    signup = None
    if purpose == "signup":
        signup = SignupRequest.objects.filter(id=signup_request_id, email__iexact=email).first()
        if not signup:
            messages.error(request, "Signup request not found. Please submit again.")
            return redirect("accounts:signup")

    otp = EmailOTP.create_for_email(email, signup_request=signup)
    request.session["otp_id"] = otp.id
    _set_resend_wait(request, "otp_resend_available_at")
    send_otp_email(to_email=email, code=otp.code, purpose=purpose)
    messages.success(request, "A new OTP has been sent to your email.")
    return redirect("accounts:verify")


@require_http_methods(["GET", "POST"])
def verify_invite_email(request):
    initial = {"email": request.GET.get("email", ""), "code": request.GET.get("code", "")}
    form = InviteOTPVerifyForm(request.POST or None, initial=initial)
    if request.method == "GET" and request.GET.get("email") and request.GET.get("code"):
        form = InviteOTPVerifyForm(request.GET)
    if (request.method == "POST" or request.GET.get("email")) and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        invite = EmployeeInvite.objects.filter(email__iexact=email).exclude(status=EmployeeInvite.Status.REJECTED).first()
        otp = EmailOTP.objects.filter(email__iexact=email, is_used=False).order_by("-created_at").first()
        User = get_user_model()
        direct_user = User.objects.filter(email__iexact=email, is_active=False).first()
        if not invite and not direct_user:
            messages.error(request, "Invite not found for this email.")
            return redirect("accounts:verify_invite_email")
        if not otp or otp.is_expired:
            messages.error(request, "OTP expired. Please ask company owner to resend invite.")
            return redirect("accounts:verify_invite_email")
        if otp.attempts >= 5:
            messages.error(request, "Too many attempts. Please ask company owner to resend invite.")
            return redirect("accounts:verify_invite_email")
        if not otp.matches(form.cleaned_data["code"]):
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            messages.error(request, "Invalid OTP.")
            return redirect("accounts:verify_invite_email")
        otp.is_used = True
        otp.save(update_fields=["is_used"])
        if invite:
            _mark_invite_email_verified(invite)
        elif direct_user:
            direct_user.is_active = True
            direct_user.save(update_fields=["is_active"])
            profile, _ = UserProfile.objects.get_or_create(user=direct_user)
            SignupRequest.objects.update_or_create(
                email=direct_user.email.lower().strip(),
                defaults={
                    "name": direct_user.get_full_name() or direct_user.first_name or direct_user.email,
                    "phone": profile.phone,
                    "requested_role": profile.role,
                    "approved_role": profile.role,
                    "status": SignupRequestStatus.APPROVED,
                    "is_email_verified": True,
                    "user": direct_user,
                },
            )
        messages.success(request, "Invite email verified. Your account will be login-ready after owner approval.")
        return redirect("accounts:login")
    return render(request, "accounts/verify_invite_email.html", {"form": form})


def _mark_invite_email_verified(invite):
    invite.is_email_verified = True
    invite.status = EmployeeInvite.Status.PENDING_APPROVAL
    invite.save(update_fields=["is_email_verified", "status", "updated_at"])
    SignupRequest.objects.update_or_create(
        email=invite.email.lower().strip(),
        defaults={
            "name": invite.name,
            "phone": invite.phone,
            "requested_role": invite.role,
            "approved_role": "",
            "status": SignupRequestStatus.PENDING_APPROVAL,
            "is_email_verified": True,
            "user": None,
        },
    )
    send_signup_pending_review_email(to_email=invite.email, name=invite.name)


@login_required
@require_http_methods(["POST"])
def sign_out(request):
    logout(request)
    return render(request, "accounts/logout.html")


@require_http_methods(["POST"])
def authentication_support_request(request):
    if rate_limit_exceeded("support-ip", client_ip(request), settings.SUPPORT_RATE_LIMIT_ATTEMPTS):
        return JsonResponse({"ok": False, "message": "Too many support requests. Please try again later."}, status=429)
    name = request.POST.get("support_name", "").strip()
    contact = request.POST.get("support_contact", "").strip()
    issue = request.POST.get("support_issue", "").strip()
    page_url = request.POST.get("page_url", "").strip()

    if not name or not issue:
        return JsonResponse({"ok": False, "message": "Please provide your name and issue details."}, status=400)

    AuthenticationSupportRequest.objects.create(
        name=name[:120],
        contact=contact[:160],
        issue=issue,
        page_url=page_url[:300],
    )
    return JsonResponse({
        "ok": True,
        "message": "Thank you. Your request has been submitted, and our team will contact you shortly.",
    })


def profile_context(request):
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    signup = SignupRequest.objects.filter(
        user=request.user,
        status=SignupRequestStatus.APPROVED,
        is_email_verified=True,
    ).first()
    changed = False
    if signup:
        if not user_profile.phone and signup.phone:
            user_profile.phone = signup.phone
            changed = True
        signup_role = signup.approved_role or signup.requested_role
        if signup_role and user_profile.role == Role.EXECUTIVE:
            user_profile.role = signup_role
            changed = True
        if not user_profile.channel_partner_reference and signup.channel_partner_reference:
            user_profile.channel_partner_reference = signup.channel_partner_reference
            changed = True
    if changed:
        user_profile.save(update_fields=["phone", "role", "employee_code", "channel_partner_reference", "updated_at"])
    company = CompanyProfile.objects.order_by("id").first()
    if company and user_profile.company_id != company.id:
        user_profile.company = company
        user_profile.save(update_fields=["company", "updated_at"])

    is_owner = user_profile.role == Role.COMPANY_OWNER
    if not user_profile.employee_code:
        user_profile.employee_code = _next_employee_code(user_profile.role, company=company)
        user_profile.save(update_fields=["employee_code", "updated_at"])
    return user_profile, company, is_owner


@login_required
def profile(request):
    user_profile, company, is_owner = profile_context(request)
    return render(
        request,
        "accounts/profile.html",
        {
            "company": company,
            "user_profile": user_profile,
            "is_owner": is_owner,
        },
    )


@login_required
def profile_edit(request):
    user_profile, company, is_owner = profile_context(request)
    profile_form = UserProfileForm(request.POST or None, request.FILES or None, instance=user_profile, user=request.user, prefix="profile")

    if request.method == "POST":
        if profile_form.is_valid():
            new_email = profile_form.cleaned_data["email"].lower().strip()
            current_email = (request.user.email or "").lower().strip()
            if new_email != current_email:
                User = get_user_model()
                if User.objects.filter(email__iexact=new_email).exclude(id=request.user.id).exists():
                    messages.error(request, "This email is already used by another employee.")
                    return redirect("accounts:profile_edit")
                if EmployeeEmailChangeRequest.objects.filter(
                    company=company,
                    requested_email__iexact=new_email,
                    status=EmployeeEmailChangeRequest.Status.PENDING,
                ).exclude(employee=request.user).exists():
                    messages.error(request, "This email already has a pending change request.")
                    return redirect("accounts:profile_edit")
                profile_form.save(skip_email=True)
                signup = SignupRequest.objects.filter(user=request.user).first()
                if signup:
                    signup.name = request.user.get_full_name() or request.user.first_name or request.user.username
                    signup.phone = request.user.profile.phone
                    signup.save(update_fields=["name", "phone", "updated_at"])
                EmployeeEmailChangeRequest.objects.filter(
                    company=company,
                    employee=request.user,
                    status=EmployeeEmailChangeRequest.Status.PENDING,
                ).exclude(requested_email__iexact=new_email).update(status=EmployeeEmailChangeRequest.Status.REJECTED)
                change, _ = EmployeeEmailChangeRequest.objects.update_or_create(
                    company=company,
                    employee=request.user,
                    requested_email=new_email,
                    status=EmployeeEmailChangeRequest.Status.PENDING,
                    defaults={
                        "requested_by": request.user,
                        "reason": "Self-service profile email update",
                        "is_email_verified": False,
                        "verified_at": None,
                        "approved_by": None,
                        "approved_at": None,
                    },
                )
                otp = EmailOTP.create_for_email(new_email, signup_request=signup)
                otp.user = request.user
                otp.save(update_fields=["user"])
                request.session["pending_email_change"] = new_email
                request.session["pending_email_otp_id"] = otp.id
                request.session["pending_email_change_request_id"] = change.id
                _set_resend_wait(request, "pending_email_resend_available_at")
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
        "accounts/profile_edit.html",
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


def _send_email_change_applied_email(change, old_email):
    profile = getattr(change.employee, "profile", None)
    role_label = profile.get_role_display() if profile else ""
    employee_code = profile.employee_code if profile else ""
    send_email_updated_email(
        to_email=change.requested_email,
        name=change.employee.get_full_name() or change.employee.username,
        old_email=old_email,
        new_email=change.requested_email,
        role_label=role_label,
        employee_code=employee_code,
    )


@login_required
@require_http_methods(["GET", "POST"])
def verify_email_change(request):
    pending_email = request.session.get("pending_email_change")
    otp_id = request.session.get("pending_email_otp_id")
    change_id = request.session.get("pending_email_change_request_id")
    if not pending_email or not otp_id:
        messages.error(request, "Please request a fresh email change OTP.")
        return redirect("accounts:profile")
    change = None
    if change_id:
        change = EmployeeEmailChangeRequest.objects.filter(
            id=change_id,
            employee=request.user,
            requested_email__iexact=pending_email,
            status=EmployeeEmailChangeRequest.Status.PENDING,
        ).first()

    form = OTPVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp = EmailOTP.objects.filter(id=otp_id, email=pending_email, is_used=False).first()
        if not otp or otp.is_expired:
            messages.error(request, "OTP expired. Request a new one.")
            return redirect("accounts:profile")
        if otp.attempts >= 5:
            messages.error(request, "Too many attempts. Request a new OTP.")
            return redirect("accounts:profile")
        if not otp.matches(form.cleaned_data["code"]):
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
            if not change:
                user_profile, company, _ = profile_context(request)
                change = EmployeeEmailChangeRequest.objects.create(
                    company=company,
                    employee=request.user,
                    requested_by=request.user,
                    requested_email=pending_email,
                    reason="Self-service profile email update",
                )
            change.mark_verified()
            old_email = request.user.email
            if not change.approve(approved_by=request.user):
                messages.error(request, "Email request is not verified yet.")
                return redirect("accounts:profile")
            otp.is_used = True
            otp.user = request.user
            otp.save(update_fields=["is_used", "user"])
            request.session.pop("pending_email_change", None)
            request.session.pop("pending_email_otp_id", None)
            request.session.pop("pending_email_change_request_id", None)
            request.session.pop("pending_email_resend_available_at", None)
            _send_email_change_applied_email(change, old_email)
            messages.success(request, "Email verified and updated.")
            return redirect("accounts:profile")

    return render(
        request,
        "accounts/verify_email_change.html",
        {
            "form": form,
            "email": pending_email,
            "resend_remaining_seconds": _resend_remaining_seconds(request, "pending_email_resend_available_at"),
        },
    )


@login_required
@require_http_methods(["POST"])
def resend_email_change_otp(request):
    pending_email = request.session.get("pending_email_change")
    change_id = request.session.get("pending_email_change_request_id")
    if not pending_email:
        messages.error(request, "Please request a fresh email change OTP.")
        return redirect("accounts:profile")
    if change_id and not EmployeeEmailChangeRequest.objects.filter(
        id=change_id,
        employee=request.user,
        requested_email__iexact=pending_email,
        status=EmployeeEmailChangeRequest.Status.PENDING,
    ).exists():
        messages.error(request, "Please request a fresh email change OTP.")
        return redirect("accounts:profile")
    remaining_seconds = _resend_remaining_seconds(request, "pending_email_resend_available_at")
    if remaining_seconds:
        messages.error(request, f"Please wait {remaining_seconds} seconds before resending OTP.")
        return redirect("accounts:verify_email_change")
    signup = SignupRequest.objects.filter(user=request.user).first()
    otp = EmailOTP.create_for_email(pending_email, signup_request=signup)
    otp.user = request.user
    otp.save(update_fields=["user"])
    request.session["pending_email_otp_id"] = otp.id
    _set_resend_wait(request, "pending_email_resend_available_at")
    send_otp_email(to_email=pending_email, code=otp.code, purpose="email_change")
    messages.success(request, "A new OTP has been sent to your new email.")
    return redirect("accounts:verify_email_change")


@login_required
@require_http_methods(["POST"])
def logout_other_sessions(request):
    current_key = request.session.session_key
    removed = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        if session.session_key == current_key:
            continue
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(request.user.pk):
            session.delete()
            removed += 1
    messages.success(request, f"{removed} other active session(s) signed out.")
    return redirect("accounts:profile")


@login_required
def company_settings(request):
    user_profile, company, is_owner = profile_context(request)
    if not is_owner:
        return redirect("accounts:company_detail")
    if is_owner:
        form = OwnerCompanyProfileForm(request.POST or None, request.FILES or None, instance=company, prefix="company")
        if request.method == "POST":
            if form.is_valid():
                company = form.save()
                if user_profile.company_id != company.id:
                    user_profile.company = company
                    user_profile.save(update_fields=["company", "updated_at"])
                messages.success(request, "Company details updated.")
                return redirect("accounts:company_settings")
            messages.error(request, "Please check company details.")
        return render(request, "accounts/company_settings.html", {"form": form, "company": company, "user_profile": user_profile, "is_owner": is_owner})


@login_required
def company_detail(request):
    user_profile, company, is_owner = profile_context(request)
    return render(request, "accounts/company_detail.html", {"company": company, "user_profile": user_profile, "is_owner": is_owner})


@login_required
def company_export(request, export_format):
    _, company, _ = profile_context(request)
    if export_format not in {"csv", "xls"}:
        raise Http404("Unsupported export format.")

    filename = f"company-details.{export_format}"
    rows = []
    for label, field_name in COMPANY_EXPORT_FIELDS:
        value = getattr(company, field_name, "") if company else ""
        if field_name == "updated_at" and value:
            value = timezone.localtime(value).strftime("%d %b %Y, %I:%M %p")
        if field_name in {"opening_time", "closing_time"} and value:
            value = value.strftime("%I:%M %p")
        rows.append((label, value or "Not added"))

    if export_format == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(["Field", "Value"])
        writer.writerows(rows)
        return response

    response = HttpResponse(content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>")
    for label, value in rows:
        response.write(f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>")
    response.write("</tbody></table>")
    return response
