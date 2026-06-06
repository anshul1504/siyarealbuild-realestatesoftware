import csv
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .email_utils import send_email_updated_email, send_employee_custom_email, send_event_notification_email, send_meeting_notification_email, send_otp_email, send_owner_custom_signup_email, send_role_change_rejected_email, send_role_change_requested_email, send_role_changed_email, send_signup_pending_review_email
from .forms import (
    CompanyEventForm,
    DesignationCodeRuleForm,
    EmailLoginForm,
    AddEmployeeForm,
    EmployeeEmailChangeRequestForm,
    EmployeeRoleChangeRequestForm,
    EmployeeInviteForm,
    InviteOTPVerifyForm,
    InviteBulkActionForm,
    MeetingForm,
    OTPVerifyForm,
    OwnerCompanyProfileForm,
    ReferralSettingForm,
    RoleMatrixRuleForm,
    RoleTargetForm,
    SignupBulkActionForm,
    SignupRequestCustomEmailForm,
    SignupRequestForm,
    SignupRequestReviewForm,
    SoftwarePopupForm,
    TeamRoleForm,
    TeamEmailMessageForm,
    UserProfileForm,
)
from .models import (
    AuthenticationSupportRequest,
    CompanyEvent,
    CompanyProfile,
    DesignationCodeRule,
    EmailOTP,
    EmployeeEmailChangeRequest,
    EmployeeRoleChangeRequest,
    EmployeeInvite,
    Meeting,
    ReferralReward,
    ReferralSetting,
    Role,
    RoleMatrixRule,
    RoleTarget,
    SignupRequest,
    SignupRequestOwnerMessage,
    SignupRequestStatus,
    SoftwarePopup,
    TeamEmailMessage,
    UserProfile,
)


OTP_RESEND_WAIT_SECONDS = 60
ADD_EMPLOYEE_EMAIL_RESEND_SECONDS = 30
INVITE_RESEND_WAIT_SECONDS = 60


COMPANY_EXPORT_FIELDS = (
    ("Company Name", "name"),
    ("Tagline", "tagline"),
    ("Description", "description"),
    ("Primary Phone", "phone"),
    ("Secondary Phone", "phone_2"),
    ("Third Phone", "phone_3"),
    ("Primary Email", "email"),
    ("Secondary Email", "email_2"),
    ("Third Email", "email_3"),
    ("Website", "website"),
    ("GST Number", "gst_number"),
    ("RERA Number", "rera_number"),
    ("CIN Number", "cin_number"),
    ("PAN Number", "pan_number"),
    ("Bank Name", "bank_name"),
    ("Account Name", "bank_account_name"),
    ("Account Number", "bank_account_number"),
    ("IFSC", "bank_ifsc"),
    ("UPI ID", "upi_id"),
    ("Opening Time", "opening_time"),
    ("Closing Time", "closing_time"),
    ("Weekly Off Days", "weekly_off_days"),
    ("Holiday Notes", "holiday_notes"),
    ("Address", "address"),
    ("City", "city"),
    ("State", "state"),
    ("Pincode", "pincode"),
    ("Last Updated", "updated_at"),
)

EMPLOYEE_EXPORT_FIELDS = (
    ("Name", "name"),
    ("Email", "email"),
    ("Phone", "phone"),
    ("Role", "role"),
    ("Employee Code", "employee_code"),
    ("Designation", "designation"),
    ("Department", "department"),
    ("Reporting Manager", "reporting_manager"),
    ("Joining Date", "joining_date"),
    ("Work Location", "work_location"),
    ("Territory", "territory"),
    ("Aadhaar", "aadhaar_number"),
    ("PAN", "pan_number"),
    ("Emergency Contact", "emergency_contact"),
    ("Bank Name", "bank_name"),
    ("Account Number", "bank_account_number"),
    ("IFSC", "bank_ifsc"),
    ("Address", "address"),
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
    initial = {}
    if referral_code:
        initial = {
            "requested_role": Role.CHANNEL_PARTNER,
            "channel_partner_reference": referral_code,
        }
    form = SignupRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower().strip()
        requested_role = Role.CHANNEL_PARTNER if referral_code else form.cleaned_data["requested_role"]
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
            signup.requested_role = requested_role
            signup.channel_partner_reference = channel_partner_reference
            signup.save(update_fields=["name", "phone", "requested_role", "channel_partner_reference", "updated_at"])
        else:
            signup = SignupRequest.objects.create(
                email=email,
                name=form.cleaned_data["name"],
                phone=form.cleaned_data["phone"],
                requested_role=requested_role,
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
                send_signup_pending_review_email(to_email=email, name=signup.name)
                request.session.pop("otp_email", None)
                request.session.pop("otp_id", None)
                request.session.pop("otp_purpose", None)
                request.session.pop("signup_request_id", None)
                request.session.pop("otp_resend_available_at", None)
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
        if form.cleaned_data["code"] != otp.code:
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


def sign_out(request):
    logout(request)
    return render(request, "accounts/logout.html")


@require_http_methods(["POST"])
def authentication_support_request(request):
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
    user_profile, company, is_owner = _profile_context(request)
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
    user_profile, company, is_owner = _profile_context(request)
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


@login_required
def team_profiles(request):
    user_profile, company, _ = _profile_context(request)
    profiles, can_view_sensitive_profile_data = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can view employee profile details.")
        return redirect("accounts:profile")
    can_delete_employee_profiles = user_profile.role == Role.COMPANY_OWNER

    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    department = request.GET.get("department", "").strip()
    if query:
        profiles = profiles.filter(
            models.Q(user__first_name__icontains=query)
            | models.Q(user__last_name__icontains=query)
            | models.Q(user__email__icontains=query)
            | models.Q(phone__icontains=query)
            | models.Q(employee_code__icontains=query)
            | models.Q(designation__icontains=query)
        )
    if role:
        profiles = profiles.filter(role=role)
    if department:
        profiles = profiles.filter(department__iexact=department)

    paginator = Paginator(profiles, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    departments = (
        profiles.model.objects.filter(company=company)
        .exclude(department="")
        .values_list("department", flat=True)
        .distinct()
        .order_by("department")
    )

    return render(
        request,
        "accounts/team_profiles.html",
        {
            "page_obj": page_obj,
            "profiles": page_obj.object_list,
            "company": company,
            "user_profile": user_profile,
            "can_view_sensitive_profile_data": can_view_sensitive_profile_data,
            "can_delete_employee_profiles": can_delete_employee_profiles,
            "role_choices": Role.choices,
            "selected_role": role,
            "selected_department": department,
            "departments": departments,
            "query": query,
            "query_string": query_params.urlencode(),
        },
    )


@login_required
@require_http_methods(["POST"])
def team_profiles_bulk_delete(request):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER:
        messages.error(request, "Only company owner can delete employee records.")
        return redirect("accounts:team_profiles")

    selected_ids = request.POST.getlist("profile_ids")
    profiles, _ = _visible_team_profiles(user_profile, company)
    selected_profiles = profiles.filter(id__in=selected_ids).exclude(id=user_profile.id)
    if not selected_profiles.exists():
        messages.error(request, "Select at least one employee to delete.")
        return redirect("accounts:team_profiles")

    users = [profile.user for profile in selected_profiles.select_related("user")]
    user_ids = [user.id for user in users]
    user_emails = [user.email.lower().strip() for user in users if user.email]
    deleted_count = len(user_ids)
    _delete_employee_identity_records(company=company, user_ids=user_ids, emails=user_emails)
    get_user_model().objects.filter(id__in=user_ids).delete()
    messages.success(request, f"{deleted_count} employee record(s) deleted from database.")
    return redirect("accounts:team_profiles")


@login_required
@require_http_methods(["POST"])
def team_profiles_bulk_email(request):
    user_profile, company, _ = _profile_context(request)
    profiles, _ = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can email employee groups.")
        return redirect("accounts:team_profiles")

    subject = request.POST.get("subject", "").strip()
    message = request.POST.get("message", "").strip()
    role = request.POST.get("role", "").strip()
    department = request.POST.get("department", "").strip()
    if not subject or not message:
        messages.error(request, "Email subject and message are required.")
        return redirect("accounts:team_profiles")
    if role:
        profiles = profiles.filter(role=role)
    if department:
        profiles = profiles.filter(department__iexact=department)

    recipients = profiles.select_related("user").exclude(user__email="")
    sent_count = 0
    sender_name = request.user.get_full_name() or request.user.email or "Siya Real Build"
    for profile_item in recipients:
        send_employee_custom_email(
            to_email=profile_item.user.email,
            name=profile_item.user.get_full_name() or profile_item.user.email,
            subject=subject,
            message=message,
            sender_name=sender_name,
        )
        sent_count += 1

    if sent_count:
        messages.success(request, f"Email sent to {sent_count} employee(s).")
    else:
        messages.error(request, "No employees matched this email target.")
    return redirect("accounts:team_profiles")


def _team_email_departments(company):
    return (
        UserProfile.objects.filter(company=company)
        .exclude(department="")
        .values_list("department", flat=True)
        .distinct()
        .order_by("department")
    )


@login_required
def team_emails(request):
    user_profile, company, _ = _profile_context(request)
    profiles, _ = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can send team emails.")
        return redirect("accounts:profile")

    form = TeamEmailMessageForm(request.POST or None, departments=_team_email_departments(company))
    if request.method == "POST":
        if form.is_valid():
            role = form.cleaned_data["role"]
            department = form.cleaned_data["department"]
            subject = form.cleaned_data["subject"].strip()
            message = form.cleaned_data["message"].strip()
            target_profiles = profiles
            if role:
                target_profiles = target_profiles.filter(role=role)
            if department:
                target_profiles = target_profiles.filter(department__iexact=department)
            recipients = []
            sender_name = request.user.get_full_name() or request.user.email or "Siya Real Build"
            for profile_item in target_profiles.select_related("user").exclude(user__email=""):
                recipient_name = profile_item.user.get_full_name() or profile_item.user.email
                send_employee_custom_email(
                    to_email=profile_item.user.email,
                    name=recipient_name,
                    subject=subject,
                    message=message,
                    sender_name=sender_name,
                )
                recipients.append({
                    "name": recipient_name,
                    "email": profile_item.user.email,
                    "role": profile_item.get_role_display(),
                    "department": profile_item.department or "",
                })
            if not recipients:
                messages.error(request, "No employees matched this email target.")
                return redirect("accounts:team_emails")
            team_email = TeamEmailMessage.objects.create(
                company=company,
                sent_by=request.user,
                role=role,
                department=department,
                subject=subject,
                message=message,
                recipients=recipients,
                sent_count=len(recipients),
            )
            messages.success(request, f"Email sent to {len(recipients)} employee(s).")
            return redirect("accounts:team_email_detail", email_id=team_email.id)
        messages.error(request, "Please check email details.")

    email_history = TeamEmailMessage.objects.filter(company=company).select_related("sent_by")[:12]
    return render(
        request,
        "accounts/team_emails.html",
        {
            "form": form,
            "email_history": email_history,
            "company": company,
            "user_profile": user_profile,
        },
    )


@login_required
def team_email_list(request):
    user_profile, company, _ = _profile_context(request)
    profiles, _ = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can view team emails.")
        return redirect("accounts:profile")
    emails = TeamEmailMessage.objects.filter(company=company).select_related("sent_by")
    paginator = Paginator(emails, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "accounts/team_email_list.html", {"page_obj": page_obj, "company": company, "user_profile": user_profile})


@login_required
def team_email_detail(request, email_id):
    user_profile, company, _ = _profile_context(request)
    profiles, _ = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can view team emails.")
        return redirect("accounts:profile")
    team_email = get_object_or_404(TeamEmailMessage.objects.select_related("sent_by"), company=company, id=email_id)
    return render(
        request,
        "accounts/team_email_detail.html",
        {
            "team_email": team_email,
            "company": company,
            "user_profile": user_profile,
        },
    )


def _visible_team_profiles(user_profile, company):
    can_view_sensitive_profile_data = user_profile.role == Role.COMPANY_OWNER
    visible_roles = {
        Role.COMPANY_OWNER: {Role.COMPANY_OWNER, Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER},
        Role.MANAGER: {Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER},
        Role.TL: {Role.EXECUTIVE, Role.CHANNEL_PARTNER},
    }.get(user_profile.role)
    if not visible_roles:
        return None, can_view_sensitive_profile_data

    profiles = (
        UserProfile.objects.filter(company=company, role__in=visible_roles)
        .select_related("user", "company")
        .order_by("role", "user__first_name", "user__email")
    )
    if user_profile.role != Role.COMPANY_OWNER:
        profiles = profiles.exclude(id=user_profile.id)
    return profiles, can_view_sensitive_profile_data


@login_required
def team_profile_detail(request, profile_id):
    user_profile, company, _ = _profile_context(request)
    profiles, can_view_sensitive_profile_data = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can view employee profile details.")
        return redirect("accounts:profile")
    employee_profile = get_object_or_404(profiles, id=profile_id)
    return render(
        request,
        "accounts/team_profile_detail.html",
        {
            "employee_profile": employee_profile,
            "company": company,
            "user_profile": user_profile,
            "can_view_sensitive_profile_data": can_view_sensitive_profile_data,
        },
    )


@login_required
@require_http_methods(["POST"])
def team_profile_delete(request, profile_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER:
        messages.error(request, "Only company owner can delete employee records.")
        return redirect("accounts:team_profiles")

    profiles, _ = _visible_team_profiles(user_profile, company)
    employee_profile = get_object_or_404(profiles, id=profile_id)
    if employee_profile.user_id == request.user.id:
        messages.error(request, "Company owner cannot delete their own account from employee directory.")
        return redirect("accounts:team_profile_detail", profile_id=employee_profile.id)

    employee_user = employee_profile.user
    employee_name = employee_user.get_full_name() or employee_user.email or employee_user.username
    _delete_employee_identity_records(
        company=company,
        user_ids=[employee_user.id],
        emails=[employee_user.email.lower().strip()] if employee_user.email else [],
    )
    employee_user.delete()
    messages.success(request, f"{employee_name} has been deleted from employee directory and database.")
    return redirect("accounts:team_profiles")


def _delete_employee_identity_records(*, company, user_ids, emails):
    normalized_emails = [email for email in {email.lower().strip() for email in emails if email}]
    identity_filter = models.Q()
    if user_ids:
        identity_filter |= models.Q(user_id__in=user_ids)
    if normalized_emails:
        identity_filter |= models.Q(email__in=normalized_emails)

    if identity_filter:
        SignupRequest.objects.filter(identity_filter).delete()

    invite_filter = models.Q()
    if user_ids:
        invite_filter |= models.Q(accepted_user_id__in=user_ids)
    if normalized_emails:
        invite_filter |= models.Q(email__in=normalized_emails)
    if invite_filter:
        EmployeeInvite.objects.filter(company=company).filter(invite_filter).delete()

    otp_filter = models.Q()
    if user_ids:
        otp_filter |= models.Q(user_id__in=user_ids)
    if normalized_emails:
        otp_filter |= models.Q(email__in=normalized_emails)
    if otp_filter:
        EmailOTP.objects.filter(otp_filter).delete()

    email_change_filter = models.Q()
    if user_ids:
        email_change_filter |= models.Q(employee_id__in=user_ids)
    if normalized_emails:
        email_change_filter |= models.Q(requested_email__in=normalized_emails)
    if email_change_filter:
        EmployeeEmailChangeRequest.objects.filter(company=company).filter(email_change_filter).delete()

    if normalized_emails:
        for team_email in TeamEmailMessage.objects.filter(company=company):
            recipients = team_email.recipients or []
            cleaned_recipients = [
                recipient
                for recipient in recipients
                if (recipient.get("email") or "").lower().strip() not in normalized_emails
            ]
            if cleaned_recipients != recipients:
                team_email.recipients = cleaned_recipients
                team_email.sent_count = len(cleaned_recipients)
                team_email.save(update_fields=["recipients", "sent_count"])


@login_required
def team_profiles_export(request, export_format):
    user_profile, company, _ = _profile_context(request)
    profiles, can_view_sensitive_profile_data = _visible_team_profiles(user_profile, company)
    if profiles is None:
        messages.error(request, "Only company owner or supervisor can export employee profile details.")
        return redirect("accounts:profile")
    if export_format not in {"csv", "xls"}:
        raise Http404("Unsupported export format.")

    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    department = request.GET.get("department", "").strip()
    if query:
        profiles = profiles.filter(
            models.Q(user__first_name__icontains=query)
            | models.Q(user__last_name__icontains=query)
            | models.Q(user__email__icontains=query)
            | models.Q(phone__icontains=query)
            | models.Q(employee_code__icontains=query)
            | models.Q(designation__icontains=query)
        )
    if role:
        profiles = profiles.filter(role=role)
    if department:
        profiles = profiles.filter(department__iexact=department)

    rows = [["Name", "Email", "Phone", "Role", "Employee Code", "Designation", "Department", "Reporting Manager", "Joining Date", "Work Location", "Aadhaar", "PAN"]]
    for profile_item in profiles:
        rows.append([
            profile_item.user.get_full_name() or profile_item.user.email or profile_item.user.username,
            profile_item.user.email or "",
            profile_item.phone or "",
            profile_item.get_role_display(),
            profile_item.employee_code or "",
            profile_item.designation or "",
            profile_item.department or "",
            profile_item.reporting_manager or "",
            profile_item.joining_date.strftime("%d %b %Y") if profile_item.joining_date else "",
            profile_item.work_location or "",
            profile_item.aadhaar_number if can_view_sensitive_profile_data else profile_item.masked_aadhaar_number,
            profile_item.pan_number if can_view_sensitive_profile_data else profile_item.masked_pan_number,
        ])

    filename = f"employee-directory.{export_format}"
    if export_format == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerows(rows)
        return response

    response = HttpResponse(content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("<table>")
    for row in rows:
        response.write("<tr>")
        for value in row:
            response.write(f"<td>{escape(value)}</td>")
        response.write("</tr>")
    response.write("</table>")
    return response


def _sync_signup_from_user(user):
    signup = SignupRequest.objects.filter(user=user).first()
    if signup:
        signup.name = user.get_full_name() or user.first_name or user.username
        signup.phone = user.profile.phone
        signup.email = user.email
        signup.save(update_fields=["name", "phone", "email", "updated_at"])


def _owner_context_or_redirect(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can access this section.")
        return user_profile, company, False
    if not company:
        company = CompanyProfile.objects.create(name="Siya Real Build", email=request.user.email)
        user_profile.company = company
        user_profile.save(update_fields=["company", "updated_at"])
    return user_profile, company, True


def _owner_render(request, template, context):
    return render(request, template, context)


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
            if not change:
                user_profile, company, _ = _profile_context(request)
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
def company_settings(request):
    user_profile, company, is_owner = _profile_context(request)
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
    user_profile, company, is_owner = _profile_context(request)
    return render(request, "accounts/company_detail.html", {"company": company, "user_profile": user_profile, "is_owner": is_owner})


@login_required
def company_export(request, export_format):
    _, company, _ = _profile_context(request)
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


@login_required
def employee_invites(request):
    user_profile, company, is_owner = _profile_context(request)
    can_manage_team = user_profile.role in {Role.COMPANY_OWNER, Role.MANAGER}
    if not can_manage_team:
        messages.error(request, "Only company owner or manager can invite employees.")
        return redirect("accounts:profile")
    allowed_roles = _allowed_invite_roles(user_profile.role)
    form = EmployeeInviteForm(request.POST or None, prefix="invite", company=company, allowed_roles=allowed_roles)
    if request.method == "POST":
        if form.is_valid():
            invite = form.save(commit=False)
            invite.company = company
            invite.invited_by = request.user
            if not invite.employee_code or invite.employee_code.endswith("-AUTO"):
                invite.employee_code = _next_employee_code(invite.role, company=company)
            invite.last_invite_sent_at = timezone.now()
            invite.save()
            otp = EmailOTP.create_for_email(invite.email)
            verify_url = request.build_absolute_uri(f"{reverse('accounts:verify_invite_email')}?email={invite.email}&code={otp.code}")
            send_otp_email(to_email=invite.email, code=otp.code, purpose="invite", cta_url=verify_url)
            messages.success(request, "Employee invite sent. Role is pre-decided and owner approval is required after email verification.")
            return redirect("accounts:employee_invite_detail", invite_id=invite.id)
        messages.error(request, "Please check invite details.")
    return render(
        request,
        "accounts/invite_create.html",
        {
            "form": form,
            "company": company,
            "user_profile": user_profile,
            "is_owner": is_owner,
            "role_code_prefixes": {
                Role.COMPANY_OWNER: "OWN",
                Role.MANAGER: "MGR",
                Role.TL: "TL",
                Role.EXECUTIVE: "EXE",
                Role.CHANNEL_PARTNER: "CP",
            },
        },
    )


@login_required
def employee_invite_list(request):
    user_profile, company, is_owner = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only company owner or manager can view employee invites.")
        return redirect("accounts:profile")
    allowed_roles = _allowed_invite_roles(user_profile.role)
    base_invites = EmployeeInvite.objects.filter(company=company).select_related("invited_by", "accepted_user", "approved_by")
    invite_counts = {
        "all": base_invites.count(),
        "pending_verification": base_invites.filter(status=EmployeeInvite.Status.PENDING_VERIFICATION).count(),
        "pending_approval": base_invites.filter(status=EmployeeInvite.Status.PENDING_APPROVAL).count(),
        "approved": base_invites.filter(status=EmployeeInvite.Status.APPROVED).count(),
        "rejected": base_invites.filter(status=EmployeeInvite.Status.REJECTED).count(),
    }
    invites = base_invites
    status = request.GET.get("status", "").strip()
    role = request.GET.get("role", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        invites = invites.filter(status=status)
    if role:
        invites = invites.filter(role=role)
    if query:
        invites = invites.filter(models.Q(name__icontains=query) | models.Q(email__icontains=query) | models.Q(phone__icontains=query) | models.Q(employee_code__icontains=query))
    invites = invites.order_by("-updated_at", "-created_at")
    paginator = Paginator(invites, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "accounts/invite_list.html",
        {
            "page_obj": page_obj,
            "company": company,
            "user_profile": user_profile,
            "is_owner": is_owner,
            "status_choices": EmployeeInvite.Status.choices,
            "role_choices": [choice for choice in Role.choices if choice[0] in allowed_roles],
            "selected_status": status,
            "selected_role": role,
            "query": query,
            "query_string": query_params.urlencode(),
            "invite_counts": invite_counts,
        },
    )


@login_required
@require_http_methods(["POST"])
def employee_invite_bulk_action(request):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only owner or manager can manage employee invites.")
        return redirect("accounts:team_profiles")

    action = request.POST.get("bulk_action", "").strip()
    selected_ids = request.POST.getlist("invite_ids")
    selected_invites = EmployeeInvite.objects.filter(company=company, id__in=selected_ids).select_related("accepted_user")
    if not selected_invites.exists():
        messages.error(request, "Select at least one invite.")
        return redirect("accounts:employee_invite_list")

    updated = 0
    skipped = 0
    now = timezone.now()
    for invite in selected_invites:
        if not _can_manage_invite(user_profile, invite):
            skipped += 1
            continue
        if action == "delete":
            if invite.status == EmployeeInvite.Status.APPROVED:
                skipped += 1
                continue
            invite.delete()
            updated += 1
        elif action == "approve":
            approved_user = invite.approve(approved_by=request.user)
            if not approved_user:
                skipped += 1
                continue
            updated += 1
        elif action == "resend":
            if invite.status == EmployeeInvite.Status.APPROVED:
                skipped += 1
                continue
            if invite.last_invite_sent_at and (invite.last_invite_sent_at + timedelta(seconds=INVITE_RESEND_WAIT_SECONDS)) > now:
                skipped += 1
                continue
            otp = EmailOTP.create_for_email(invite.email)
            verify_url = request.build_absolute_uri(f"{reverse('accounts:verify_invite_email')}?email={invite.email}&code={otp.code}")
            send_otp_email(to_email=invite.email, code=otp.code, purpose="invite", cta_url=verify_url)
            invite.last_invite_sent_at = timezone.now()
            invite.resend_count += 1
            invite.save(update_fields=["last_invite_sent_at", "resend_count", "updated_at"])
            updated += 1
        else:
            messages.error(request, "Select a valid bulk action.")
            return redirect("accounts:employee_invite_list")

    if updated:
        messages.success(request, f"{updated} invite(s) updated.")
    if skipped:
        messages.warning(request, f"{skipped} invite(s) skipped because they are locked, cooling down, or outside your role access.")
    return redirect("accounts:employee_invite_list")


def _allowed_invite_roles(actor_role):
    if actor_role == Role.COMPANY_OWNER:
        return {Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}
    if actor_role == Role.MANAGER:
        return {Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}
    return set()


def _can_manage_invite(user_profile, invite):
    return bool(
        user_profile.role in {Role.COMPANY_OWNER, Role.MANAGER}
        and invite.role in _allowed_invite_roles(user_profile.role)
    )


@login_required
@require_http_methods(["POST"])
def employee_invite_resend(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only owner or manager can resend employee invites.")
        return redirect("accounts:team_profiles")
    invite = get_object_or_404(EmployeeInvite, company=company, id=invite_id)
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot resend invites for this role.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if invite.status == EmployeeInvite.Status.APPROVED:
        messages.error(request, "Approved invites cannot be resent.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if invite.last_invite_sent_at:
        available_at = invite.last_invite_sent_at + timedelta(seconds=INVITE_RESEND_WAIT_SECONDS)
        remaining = int((available_at - timezone.now()).total_seconds())
        if remaining > 0:
            messages.error(request, f"Please wait {remaining} seconds before resending this invite.")
            return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    otp = EmailOTP.create_for_email(invite.email)
    verify_url = request.build_absolute_uri(f"{reverse('accounts:verify_invite_email')}?email={invite.email}&code={otp.code}")
    send_otp_email(to_email=invite.email, code=otp.code, purpose="invite", cta_url=verify_url)
    invite.last_invite_sent_at = timezone.now()
    invite.resend_count += 1
    invite.save(update_fields=["last_invite_sent_at", "resend_count", "updated_at"])
    messages.success(request, "Invite verification email resent.")
    return redirect("accounts:employee_invite_detail", invite_id=invite.id)


@login_required
@require_http_methods(["POST"])
def employee_invite_approve(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only owner or manager can approve employee invites.")
        return redirect("accounts:team_profiles")
    invite = get_object_or_404(EmployeeInvite, company=company, id=invite_id)
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot approve invites for this role.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    approved_user = invite.approve(approved_by=request.user)
    if not approved_user:
        messages.error(request, "Invite cannot be approved until email OTP verification is complete.")
    else:
        messages.success(request, "Invite approved and employee account is ready for login.")
    return redirect("accounts:employee_invite_detail", invite_id=invite.id)


@login_required
@require_http_methods(["POST"])
def employee_invite_verify_otp(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only owner or manager can verify employee invites.")
        return redirect("accounts:team_profiles")
    invite = get_object_or_404(EmployeeInvite, company=company, id=invite_id)
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot verify invites for this role.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if invite.status == EmployeeInvite.Status.APPROVED:
        messages.error(request, "Approved invite is already locked.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if invite.is_email_verified:
        messages.success(request, "Invite email is already verified.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)

    code = request.POST.get("code", "").strip()
    if not code:
        messages.error(request, "Enter the invite OTP.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)

    otp = EmailOTP.objects.filter(email__iexact=invite.email, is_used=False).order_by("-created_at").first()
    if not otp or otp.is_expired:
        messages.error(request, "OTP expired. Please resend invite verification.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if otp.attempts >= 5:
        messages.error(request, "Too many attempts. Please resend invite verification.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if code != otp.code:
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        messages.error(request, "Invalid invite OTP.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)

    otp.is_used = True
    otp.save(update_fields=["is_used"])
    _mark_invite_email_verified(invite)
    messages.success(request, "Invite email verified. It is ready for owner approval.")
    return redirect("accounts:employee_invite_detail", invite_id=invite.id)


@login_required
@require_http_methods(["POST"])
def employee_invite_delete(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only owner or manager can delete employee invites.")
        return redirect("accounts:team_profiles")
    invite = get_object_or_404(EmployeeInvite, company=company, id=invite_id)
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot delete invites for this role.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    if invite.status == EmployeeInvite.Status.APPROVED:
        messages.error(request, "Approved invite records are locked because an employee account is already linked.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)
    invite.delete()
    messages.success(request, "Invite deleted.")
    return redirect("accounts:employee_invites")


@login_required
def employee_invite_edit(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    invite = get_object_or_404(EmployeeInvite, company=company, id=invite_id)
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot edit invites for this role.")
        return redirect("accounts:employee_invite_list")
    if invite.status == EmployeeInvite.Status.APPROVED:
        messages.error(request, "Approved invite records are locked.")
        return redirect("accounts:employee_invite_detail", invite_id=invite.id)

    original_email = invite.email
    form = EmployeeInviteForm(
        request.POST or None,
        instance=invite,
        company=company,
        allowed_roles=_allowed_invite_roles(user_profile.role),
    )
    if request.method == "POST" and form.is_valid():
        updated_invite = form.save(commit=False)
        email_changed = updated_invite.email.lower().strip() != original_email.lower().strip()
        if email_changed:
            updated_invite.is_email_verified = False
            updated_invite.status = EmployeeInvite.Status.PENDING_VERIFICATION
            updated_invite.last_invite_sent_at = timezone.now()
            updated_invite.resend_count = 0
        updated_invite.save()
        if email_changed:
            otp = EmailOTP.create_for_email(updated_invite.email)
            verify_url = request.build_absolute_uri(f"{reverse('accounts:verify_invite_email')}?email={updated_invite.email}&code={otp.code}")
            send_otp_email(to_email=updated_invite.email, code=otp.code, purpose="invite", cta_url=verify_url)
            messages.success(request, "Invite updated. The new email must be verified before approval.")
        else:
            messages.success(request, "Invite details updated.")
        return redirect("accounts:employee_invite_detail", invite_id=updated_invite.id)

    return render(
        request,
        "accounts/invite_edit.html",
        {"form": form, "invite": invite, "company": company, "user_profile": user_profile},
    )


@login_required
def employee_invite_detail(request, invite_id):
    user_profile, company, _ = _profile_context(request)
    invite = get_object_or_404(
        EmployeeInvite.objects.select_related("invited_by", "accepted_user", "approved_by"),
        company=company,
        id=invite_id,
    )
    if user_profile.role not in {Role.COMPANY_OWNER, Role.MANAGER}:
        messages.error(request, "Only company owner or manager can view employee invites.")
        return redirect("accounts:profile")
    if not _can_manage_invite(user_profile, invite):
        messages.error(request, "You cannot view invites for this role.")
        return redirect("accounts:employee_invites")
    resend_remaining_seconds = 0
    if invite.last_invite_sent_at and invite.status != EmployeeInvite.Status.APPROVED:
        available_at = invite.last_invite_sent_at + timedelta(seconds=INVITE_RESEND_WAIT_SECONDS)
        resend_remaining_seconds = max(0, int((available_at - timezone.now()).total_seconds()))
    signup = SignupRequest.objects.filter(email__iexact=invite.email).select_related("user").first()
    return render(
        request,
        "accounts/invite_detail.html",
        {
            "invite": invite,
            "signup": signup,
            "company": company,
            "user_profile": user_profile,
            "can_resend_invite": invite.status != EmployeeInvite.Status.APPROVED and resend_remaining_seconds == 0,
            "can_delete_invite": invite.status != EmployeeInvite.Status.APPROVED,
            "resend_remaining_seconds": resend_remaining_seconds,
        },
    )


@login_required
def my_referrals(request):
    user_profile, company, _ = _profile_context(request)
    referral_code = user_profile.employee_code or request.user.email or request.user.username
    referral_path = f"{reverse('accounts:signup')}?{urlencode({'ref': referral_code})}"
    referral_url = request.build_absolute_uri(referral_path)
    setting = ReferralSetting.objects.filter(company=company).first()
    rewards_given = (
        ReferralReward.objects.filter(company=company, referrer=request.user)
        .select_related("referred_user", "referred_user__profile", "signup_request")
        .order_by("-activated_at", "-created_at")
    )
    rewards_received = (
        ReferralReward.objects.filter(company=company, referred_user=request.user)
        .select_related("referrer", "referrer__profile", "signup_request")
        .order_by("-activated_at", "-created_at")
    )
    pending_referred = SignupRequest.objects.filter(
        channel_partner_reference__iexact=referral_code,
        status__in=[SignupRequestStatus.OTP_PENDING, SignupRequestStatus.PENDING_APPROVAL],
    ).order_by("-updated_at", "-created_at")
    referral_stats = {
        "earned": rewards_given.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referrer_reward_amount"))["total"] or 0,
        "received": rewards_received.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referred_reward_amount"))["total"] or 0,
        "active_referrals": rewards_given.filter(status=ReferralReward.Status.ACTIVE).count(),
        "pending": pending_referred.count(),
    }
    return render(
        request,
        "accounts/my_referrals.html",
        {
            "company": company,
            "user_profile": user_profile,
            "setting": setting,
            "referral_code": referral_code,
            "referral_url": referral_url,
            "referral_stats": referral_stats,
            "rewards_given": rewards_given[:10],
            "rewards_received": rewards_received[:10],
            "pending_referred": pending_referred[:10],
        },
    )


@login_required
def add_employee(request):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER:
        messages.error(request, "Only company owner can add employees directly.")
        return redirect("accounts:team_profiles")
    allowed_roles = {Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}
    form = AddEmployeeForm(request.POST or None, request.FILES or None, company=company, allowed_roles=allowed_roles)
    if request.method == "POST":
        if form.is_valid():
            email = form.cleaned_data["email"]
            if request.session.get("add_employee_verified_email") != email:
                messages.error(request, "Please verify employee email before adding employee.")
                return redirect("accounts:add_employee")
            User = get_user_model()
            name = form.cleaned_data["name"]
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                is_active=True,
            )
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.company = company
            profile.role = form.cleaned_data["role"]
            profile.phone = form.cleaned_data["phone"]
            profile.designation = form.cleaned_data["designation"]
            submitted_code = form.cleaned_data["employee_code"]
            profile.employee_code = "" if submitted_code.endswith("-AUTO") else submitted_code
            profile.employee_code = profile.employee_code or _next_employee_code(
                profile.role,
                company=company,
                designation=profile.designation,
            )
            profile.personal_email = form.cleaned_data["personal_email"]
            profile.date_of_birth = form.cleaned_data["date_of_birth"]
            profile.gender = form.cleaned_data["gender"]
            profile.blood_group = form.cleaned_data["blood_group"]
            profile.marital_status = form.cleaned_data["marital_status"]
            profile.department = form.cleaned_data["department"]
            profile.reporting_manager = form.cleaned_data["reporting_manager"]
            profile.work_location = _selected_work_location(company, form.cleaned_data["office_location"], form.cleaned_data["custom_work_location"])
            profile.joining_date = form.cleaned_data["joining_date"]
            profile.aadhaar_number = form.cleaned_data["aadhaar_number"]
            profile.aadhaar_document = form.cleaned_data["aadhaar_document"]
            profile.pan_number = form.cleaned_data["pan_number"]
            profile.pan_document = form.cleaned_data["pan_document"]
            profile.emergency_contact_name = form.cleaned_data["emergency_contact_name"]
            profile.emergency_contact_phone = form.cleaned_data["emergency_contact_phone"]
            profile.bank_name = form.cleaned_data["bank_name"]
            profile.bank_account_name = form.cleaned_data["bank_account_name"]
            profile.bank_account_number = form.cleaned_data["bank_account_number"]
            profile.bank_ifsc = form.cleaned_data["bank_ifsc"]
            profile.address = form.cleaned_data["address"]
            profile.city = form.cleaned_data["city"]
            profile.state = form.cleaned_data["state"]
            profile.pincode = form.cleaned_data["pincode"]
            profile.save()
            SignupRequest.objects.update_or_create(
                email=email,
                defaults={
                    "name": name,
                    "phone": profile.phone,
                    "requested_role": profile.role,
                    "approved_role": profile.role,
                    "status": SignupRequestStatus.APPROVED,
                    "is_email_verified": True,
                    "user": user,
                },
            )
            request.session.pop("add_employee_verified_email", None)
            request.session.pop("add_employee_email_otp_id", None)
            messages.success(request, "Employee added. Email is verified and account is ready for login.")
            return redirect("accounts:team_profiles")
        messages.error(request, "Please check employee details.")
    return render(
        request,
        "accounts/add_employee.html",
        {
            "form": form,
            "company": company,
            "user_profile": user_profile,
            "role_code_prefixes": {
                Role.COMPANY_OWNER: "OWN",
                Role.MANAGER: "MGR",
                Role.TL: "TL",
                Role.EXECUTIVE: "EXE",
                Role.CHANNEL_PARTNER: "CP",
            },
            "add_employee_verified_email": request.session.get("add_employee_verified_email", ""),
        },
    )


def _next_employee_code(role, company=None, designation=""):
    designation = (designation or "").strip()
    if company and designation:
        with transaction.atomic():
            rule = (
                DesignationCodeRule.objects.select_for_update()
                .filter(
                    company=company,
                    role=role,
                    designation__iexact=designation,
                    is_active=True,
                )
                .order_by("id")
                .first()
            )
            if rule:
                code = rule.preview_code()
                rule.next_number += 1
                rule.save(update_fields=["next_number"])
                return code

    prefix_map = {
        Role.COMPANY_OWNER: "OWN",
        Role.MANAGER: "MGR",
        Role.TL: "TL",
        Role.EXECUTIVE: "EXE",
        Role.CHANNEL_PARTNER: "CP",
    }
    prefix = prefix_map.get(role, "EMP")
    profiles = UserProfile.objects.filter(role=role)
    if company:
        profiles = profiles.filter(company=company)
    next_number = profiles.count() + 1
    return f"{prefix}-{next_number:04d}"


def _selected_work_location(company, office_location, custom_work_location):
    if office_location == "custom":
        return custom_work_location
    if office_location == "head_office" and company:
        return ", ".join(part for part in [company.address, company.city, company.state, company.pincode] if part)
    return office_location or ""


@login_required
@require_http_methods(["POST"])
def add_employee_send_otp(request):
    user_profile, _, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER:
        return JsonResponse({"ok": False, "message": "Only company owner can verify employee email."}, status=403)
    email = request.POST.get("email", "").lower().strip()
    if not email:
        return JsonResponse({"ok": False, "message": "Enter employee email first."}, status=400)
    if get_user_model().objects.filter(email__iexact=email).exists():
        return JsonResponse({"ok": False, "message": "This email already exists."}, status=400)
    remaining = _resend_remaining_seconds(request, "add_employee_email_resend_available_at")
    if remaining:
        return JsonResponse({"ok": False, "message": f"Please wait {remaining} seconds before resending OTP.", "remaining": remaining}, status=429)
    otp = EmailOTP.create_for_email(email)
    request.session["add_employee_email"] = email
    request.session["add_employee_email_otp_id"] = otp.id
    request.session["add_employee_email_resend_available_at"] = (timezone.now() + timedelta(seconds=ADD_EMPLOYEE_EMAIL_RESEND_SECONDS)).isoformat()
    send_otp_email(to_email=email, code=otp.code, purpose="invite")
    return JsonResponse({"ok": True, "message": "OTP sent to employee email.", "cooldown": ADD_EMPLOYEE_EMAIL_RESEND_SECONDS})


@login_required
@require_http_methods(["POST"])
def add_employee_verify_otp(request):
    user_profile, _, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER:
        return JsonResponse({"ok": False, "message": "Only company owner can verify employee email."}, status=403)
    email = request.POST.get("email", "").lower().strip()
    code = request.POST.get("code", "").strip()
    otp_id = request.session.get("add_employee_email_otp_id")
    if not email or not code or request.session.get("add_employee_email") != email:
        return JsonResponse({"ok": False, "message": "Request a fresh OTP for this email."}, status=400)
    otp = EmailOTP.objects.filter(id=otp_id, email=email, is_used=False).first()
    if not otp or otp.is_expired:
        return JsonResponse({"ok": False, "message": "OTP expired. Send a new OTP."}, status=400)
    if otp.code != code:
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        return JsonResponse({"ok": False, "message": "Invalid OTP."}, status=400)
    otp.is_used = True
    otp.save(update_fields=["is_used"])
    request.session["add_employee_verified_email"] = email
    return JsonResponse({"ok": True, "message": "Employee email verified."})


@login_required
def access_control(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can manage role access.")
        return redirect("accounts:profile")
    pending_count = EmployeeRoleChangeRequest.objects.filter(company=company, status=EmployeeRoleChangeRequest.Status.PENDING).count()
    recent_requests = EmployeeRoleChangeRequest.objects.filter(company=company).select_related("employee", "employee__profile", "requested_by", "reviewed_by")[:8]
    role_counts = [
        {"label": _role_label(item["role"]), "total": item["total"]}
        for item in UserProfile.objects.filter(company=company).values("role").annotate(total=models.Count("id")).order_by("role")
    ]
    return render(
        request,
        "accounts/role_access_control.html",
        {
            "company": company,
            "user_profile": user_profile,
            "is_owner": is_owner,
            "pending_count": pending_count,
            "recent_requests": recent_requests,
            "role_counts": role_counts,
        },
    )


def _role_label(role):
    return dict(Role.choices).get(role, role)


def _send_role_change_requested(change, request_user):
    send_role_change_requested_email(
        to_email=change.employee.email,
        name=change.employee.get_full_name() or change.employee.email,
        current_role=_role_label(change.current_role),
        requested_role=_role_label(change.requested_role),
        requester_name=request_user.get_full_name() or request_user.email or "Company owner",
    )


@login_required
def role_change_request_list(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can view role change requests.")
        return redirect("accounts:profile")
    requests = EmployeeRoleChangeRequest.objects.filter(company=company).select_related("employee", "employee__profile", "requested_by", "reviewed_by")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    requested_role = request.GET.get("role", "").strip()
    if query:
        requests = requests.filter(
            models.Q(employee__first_name__icontains=query)
            | models.Q(employee__last_name__icontains=query)
            | models.Q(employee__email__icontains=query)
            | models.Q(employee__profile__employee_code__icontains=query)
        )
    if status:
        requests = requests.filter(status=status)
    if requested_role:
        requests = requests.filter(requested_role=requested_role)
    paginator = Paginator(requests, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "accounts/role_change_request_list.html",
        {
            "page_obj": page_obj,
            "requests": page_obj.object_list,
            "status_choices": EmployeeRoleChangeRequest.Status.choices,
            "role_choices": Role.choices,
            "selected_status": status,
            "selected_role": requested_role,
            "query": query,
            "query_string": query_params.urlencode(),
            "company": company,
            "user_profile": user_profile,
        },
    )


@login_required
def role_change_request_create(request):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can request role changes.")
        return redirect("accounts:profile")
    form = EmployeeRoleChangeRequestForm(request.POST or None, company=company, prefix="rolechange")
    if request.method == "POST":
        if form.is_valid():
            employee = form.cleaned_data["employee"]
            change = form.save(commit=False)
            change.company = company
            change.current_role = employee.profile.role
            change.requested_by = request.user
            change.save()
            _send_role_change_requested(change, request.user)
            messages.success(request, "Role change request created and employee email sent.")
            return redirect("accounts:role_change_request_detail", request_id=change.id)
        messages.error(request, "Please check role change details.")
    return render(request, "accounts/role_change_request_create.html", {"form": form, "company": company, "user_profile": user_profile})


@login_required
def role_change_request_detail(request, request_id):
    user_profile, company, is_owner = _profile_context(request)
    if not is_owner:
        messages.error(request, "Only company owner can manage role change requests.")
        return redirect("accounts:profile")
    change = get_object_or_404(
        EmployeeRoleChangeRequest.objects.select_related("employee", "employee__profile", "requested_by", "reviewed_by"),
        company=company,
        id=request_id,
    )
    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        review_note = request.POST.get("review_note", "").strip()
        if action == "approve":
            old_role = _role_label(change.current_role)
            new_role = _role_label(change.requested_role)
            if change.approve(reviewed_by=request.user, review_note=review_note):
                send_role_changed_email(
                    to_email=change.employee.email,
                    name=change.employee.get_full_name() or change.employee.email,
                    old_role=old_role,
                    new_role=new_role,
                    employee_code=change.employee.profile.employee_code,
                    review_note=review_note,
                )
                messages.success(request, "Role change approved and employee notified.")
            else:
                messages.error(request, "Only pending role change requests can be approved.")
            return redirect("accounts:role_change_request_detail", request_id=change.id)
        if action == "reject":
            if change.reject(reviewed_by=request.user, review_note=review_note):
                send_role_change_rejected_email(
                    to_email=change.employee.email,
                    name=change.employee.get_full_name() or change.employee.email,
                    current_role=_role_label(change.current_role),
                    requested_role=_role_label(change.requested_role),
                    review_note=review_note,
                )
                messages.success(request, "Role change request rejected and employee notified.")
            else:
                messages.error(request, "Only pending role change requests can be rejected.")
            return redirect("accounts:role_change_request_detail", request_id=change.id)
    return render(request, "accounts/role_change_request_detail.html", {"change": change, "company": company, "user_profile": user_profile})


@login_required
def owner_codes(request):
    return redirect("accounts:owner_serial_rules")


@login_required
def owner_assigned_codes(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")

    profiles = (
        UserProfile.objects.filter(company=company)
        .select_related("user")
        .order_by("role", "employee_code", "user__first_name", "user__email")
    )
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_department = request.GET.get("department", "").strip()
    code_status = request.GET.get("code_status", "").strip()

    if query:
        profiles = profiles.filter(
            models.Q(user__first_name__icontains=query)
            | models.Q(user__last_name__icontains=query)
            | models.Q(user__email__icontains=query)
            | models.Q(phone__icontains=query)
            | models.Q(employee_code__icontains=query)
            | models.Q(designation__icontains=query)
            | models.Q(department__icontains=query)
        )
    if selected_role:
        profiles = profiles.filter(role=selected_role)
    if selected_department:
        profiles = profiles.filter(department__iexact=selected_department)
    if code_status == "assigned":
        profiles = profiles.exclude(employee_code="")
    elif code_status == "missing":
        profiles = profiles.filter(employee_code="")

    if request.method == "POST" and request.POST.get("form_kind") == "assigned_bulk":
        action = request.POST.get("action")
        selected_ids = request.POST.getlist("profile_ids")
        selected = UserProfile.objects.filter(company=company, id__in=selected_ids)
        if not selected.exists():
            messages.error(request, "Select at least one employee.")
            return redirect("accounts:owner_assigned_codes")
        if action == "generate_missing":
            updated = 0
            for profile in selected.select_related("user"):
                if not profile.employee_code:
                    profile.employee_code = _next_employee_code(profile.role, company=company, designation=profile.designation)
                    profile.save(update_fields=["employee_code", "updated_at"])
                    updated += 1
            messages.success(request, f"Generated {updated} missing employee code(s).")
        elif action == "clear":
            selected = selected.exclude(id=user_profile.id)
            updated = selected.update(employee_code="", updated_at=timezone.now())
            messages.success(request, f"Cleared {updated} employee code(s).")
        else:
            messages.error(request, "Choose a valid bulk action.")
        return redirect("accounts:owner_assigned_codes")

    all_departments = (
        UserProfile.objects.filter(company=company)
        .exclude(department="")
        .order_by("department")
        .values_list("department", flat=True)
        .distinct()
    )
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(profiles, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return _owner_render(
        request,
        "accounts/owner_assigned_codes.html",
        {
            "profiles": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "selected_role": selected_role,
            "selected_department": selected_department,
            "code_status": code_status,
            "departments": all_departments,
            "role_choices": Role.choices,
            "query_string": query_params.urlencode(),
            "total_codes": UserProfile.objects.filter(company=company).exclude(employee_code="").count(),
            "missing_codes": UserProfile.objects.filter(company=company, employee_code="").count(),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_serial_rules(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")

    edit_rule = None
    edit_id = request.GET.get("edit")
    if edit_id:
        edit_rule = DesignationCodeRule.objects.filter(company=company, id=edit_id).first()
        if not edit_rule:
            messages.error(request, "Serial rule not found.")
            return redirect("accounts:owner_serial_rules")

    form = DesignationCodeRuleForm(
        request.POST or None,
        instance=edit_rule,
        company=company,
        prefix="code",
    )
    if request.method == "POST" and request.POST.get("form_kind") == "code":
        if form.is_valid():
            rule = form.save(commit=False)
            rule.company = company
            rule.save()
            messages.success(request, "Employee code serial setup saved.")
            return redirect("accounts:owner_serial_rules")
        messages.error(request, "Please check code rule details.")

    if request.method == "POST" and request.POST.get("form_kind") == "rule_action":
        rule = get_object_or_404(DesignationCodeRule, company=company, id=request.POST.get("rule_id"))
        action = request.POST.get("action")
        if action == "toggle":
            rule.is_active = not rule.is_active
            rule.save(update_fields=["is_active"])
            messages.success(request, "Code rule status updated.")
        elif action == "delete":
            rule.delete()
            messages.success(request, "Code rule deleted.")
        return redirect("accounts:owner_serial_rules")

    if request.method == "POST" and request.POST.get("form_kind") == "rule_bulk":
        action = request.POST.get("action")
        selected = DesignationCodeRule.objects.filter(company=company, id__in=request.POST.getlist("rule_ids"))
        if not selected.exists():
            messages.error(request, "Select at least one serial rule.")
            return redirect("accounts:owner_serial_rules")
        if action == "activate":
            updated = selected.update(is_active=True)
            messages.success(request, f"Activated {updated} serial rule(s).")
        elif action == "deactivate":
            updated = selected.update(is_active=False)
            messages.success(request, f"Deactivated {updated} serial rule(s).")
        elif action == "delete":
            count = selected.count()
            selected.delete()
            messages.success(request, f"Deleted {count} serial rule(s).")
        else:
            messages.error(request, "Choose a valid bulk action.")
        return redirect("accounts:owner_serial_rules")

    rules = DesignationCodeRule.objects.filter(company=company)
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        rules = rules.filter(models.Q(designation__icontains=query) | models.Q(prefix__icontains=query))
    if selected_role:
        rules = rules.filter(role=selected_role)
    if selected_status == "active":
        rules = rules.filter(is_active=True)
    elif selected_status == "inactive":
        rules = rules.filter(is_active=False)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(rules, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    all_rules = DesignationCodeRule.objects.filter(company=company)
    rule_stats = {
        "total": all_rules.count(),
        "active": all_rules.filter(is_active=True).count(),
        "inactive": all_rules.filter(is_active=False).count(),
        "employees_with_codes": UserProfile.objects.filter(company=company).exclude(employee_code="").count(),
    }
    return _owner_render(
        request,
        "accounts/owner_serial_rules.html",
        {
            "form": form,
            "rules": page_obj.object_list,
            "page_obj": page_obj,
            "edit_rule": edit_rule,
            "rule_stats": rule_stats,
            "query": query,
            "selected_role": selected_role,
            "selected_status": selected_status,
            "role_choices": Role.choices,
            "query_string": query_params.urlencode(),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_requests(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    signups = SignupRequest.objects.filter(
        status__in=[SignupRequestStatus.PENDING_APPROVAL, SignupRequestStatus.OTP_PENDING]
    ).order_by("-updated_at", "-created_at")
    signup_form = SignupBulkActionForm(request.POST or None, signups=signups, prefix="signup")
    if request.method == "POST" and request.POST.get("form_kind") == "signup" and signup_form.is_valid():
        selected = SignupRequest.objects.filter(id__in=signup_form.cleaned_data["signup_ids"])
        if not selected.exists():
            messages.error(request, "Select at least one signup request.")
            return redirect("accounts:owner_requests")
        updated = 0
        skipped = 0
        for signup in selected:
            action = signup_form.cleaned_data["action"]
            if action == "approve":
                if not signup.is_email_verified or signup.status == SignupRequestStatus.OTP_PENDING:
                    skipped += 1
                    continue
                signup.approve()
            elif action == "reject":
                signup.reject()
            else:
                signup.status = SignupRequestStatus.PENDING_APPROVAL
                signup.save(update_fields=["status", "updated_at"])
            updated += 1
        if updated:
            messages.success(request, f"{updated} signup request(s) updated.")
        if skipped:
            messages.warning(request, f"{skipped} signup request(s) skipped because email verification is pending.")
        return redirect("accounts:owner_requests")
    request_counts = {
        "signup_pending": signups.filter(status=SignupRequestStatus.PENDING_APPROVAL, is_email_verified=True).count(),
        "signup_otp": signups.filter(status=SignupRequestStatus.OTP_PENDING).count(),
        "signup_approved": SignupRequest.objects.filter(status=SignupRequestStatus.APPROVED).count(),
        "signup_rejected": SignupRequest.objects.filter(status=SignupRequestStatus.REJECTED).count(),
    }
    return _owner_render(
        request,
        "accounts/owner_requests.html",
        {
            "signup_form": signup_form,
            "signups": signups,
            "request_counts": request_counts,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_signup_request_list(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")

    requests = SignupRequest.objects.all().order_by("-updated_at", "-created_at")
    status = request.GET.get("status", "").strip()
    role = request.GET.get("role", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        requests = requests.filter(status=status)
    if role:
        requests = requests.filter(requested_role=role)
    if query:
        requests = requests.filter(models.Q(name__icontains=query) | models.Q(email__icontains=query) | models.Q(phone__icontains=query))

    paginator = Paginator(requests, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return _owner_render(
        request,
        "accounts/signup_request_list.html",
        {
            "page_obj": page_obj,
            "status_choices": SignupRequestStatus.choices,
            "role_choices": Role.choices,
            "selected_status": status,
            "selected_role": role,
            "query": query,
            "query_string": query_params.urlencode(),
            "company": company,
            "user_profile": user_profile,
        },
    )


@login_required
@require_http_methods(["POST"])
def owner_signup_request_bulk_delete(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")

    selected_ids = request.POST.getlist("signup_ids")
    selected_requests = SignupRequest.objects.filter(id__in=selected_ids)
    if not selected_requests.exists():
        messages.error(request, "Select at least one signup request to delete.")
        return redirect("accounts:owner_signup_request_list")

    emails = [email.lower().strip() for email in selected_requests.values_list("email", flat=True) if email]
    user_ids = [user_id for user_id in selected_requests.values_list("user_id", flat=True) if user_id]
    deleted_count = selected_requests.count()

    invite_filter = models.Q()
    if emails:
        invite_filter |= models.Q(email__in=emails)
    if user_ids:
        invite_filter |= models.Q(accepted_user_id__in=user_ids)
    if invite_filter:
        EmployeeInvite.objects.filter(company=company).filter(invite_filter).delete()

    otp_filter = models.Q()
    if emails:
        otp_filter |= models.Q(email__in=emails)
    if user_ids:
        otp_filter |= models.Q(user_id__in=user_ids)
    if otp_filter:
        EmailOTP.objects.filter(otp_filter).delete()

    selected_requests.delete()
    messages.success(request, f"{deleted_count} signup request(s) deleted.")
    return redirect("accounts:owner_signup_request_list")


@login_required
def owner_signup_request_detail(request, request_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    signup = get_object_or_404(SignupRequest, id=request_id)
    review_form = SignupRequestReviewForm(request.POST or None, instance=signup, prefix="review")
    email_form = SignupRequestCustomEmailForm(request.POST or None, prefix="email")

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"save_review", "approve", "reject"}:
            if review_form.is_valid():
                signup = review_form.save()
                if action == "approve":
                    if not signup.is_email_verified or signup.status == SignupRequestStatus.OTP_PENDING:
                        messages.error(request, "This signup cannot be approved until email verification is complete.")
                    else:
                        signup.approve()
                        messages.success(request, "Signup request approved and applicant notified.")
                        return redirect("accounts:owner_signup_request_detail", request_id=signup.id)
                elif action == "reject":
                    signup.reject()
                    messages.success(request, "Signup request rejected and applicant notified.")
                    return redirect("accounts:owner_signup_request_detail", request_id=signup.id)
                else:
                    messages.success(request, "Review details saved.")
                    return redirect("accounts:owner_signup_request_detail", request_id=signup.id)
            else:
                messages.error(request, "Please check review details.")
        elif action == "send_email":
            if email_form.is_valid():
                subject = email_form.cleaned_data["subject"].strip()
                message = email_form.cleaned_data["message"].strip()
                send_owner_custom_signup_email(
                    to_email=signup.email,
                    name=signup.name,
                    subject=subject,
                    message=message,
                )
                SignupRequestOwnerMessage.objects.create(
                    signup_request=signup,
                    sent_by=request.user,
                    subject=subject,
                    message=message,
                )
                messages.success(request, "Custom email sent to applicant.")
                return redirect("accounts:owner_signup_request_detail", request_id=signup.id)
            messages.error(request, "Please check custom email details.")

    return _owner_render(
        request,
        "accounts/signup_request_detail.html",
        {
            "signup": signup,
            "review_form": review_form,
            "email_form": email_form,
            "messages_sent": signup.owner_messages.select_related("sent_by"),
            "company": company,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_meetings(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        form_kind = request.POST.get("form_kind")
        if form_kind == "meeting_bulk":
            selected = Meeting.objects.filter(company=company, id__in=request.POST.getlist("meeting_ids"))
            if request.POST.get("action") == "delete" and selected.exists():
                count = selected.count()
                selected.delete()
                messages.success(request, f"Deleted {count} meeting(s).")
            else:
                messages.error(request, "Select meetings and choose delete.")
            return redirect("accounts:owner_meetings")
        if form_kind == "meeting_action":
            meeting = get_object_or_404(Meeting.objects.filter(company=company), id=request.POST.get("meeting_id"))
            if request.POST.get("action") == "status":
                status = request.POST.get("status")
                note = request.POST.get("status_note", "").strip()
                if status not in dict(Meeting.Status.choices):
                    messages.error(request, "Choose a valid meeting status.")
                    return redirect("accounts:owner_meetings")
                if status == Meeting.Status.CANCELLED and not note:
                    messages.error(request, "Cancellation reason is required.")
                    return redirect("accounts:owner_meetings")
                meeting.status = status
                meeting.status_note = note
                meeting.is_active = status == Meeting.Status.ACTIVE
                meeting.save(update_fields=["status", "status_note", "is_active"])
                messages.success(request, "Meeting status updated.")
                _send_meeting_emails(request, meeting, f"Online meeting {meeting.get_status_display().lower()}")
            return redirect("accounts:owner_meetings")

    meetings = Meeting.objects.filter(company=company).select_related("created_by")
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        meetings = meetings.filter(models.Q(title__icontains=query) | models.Q(description__icontains=query) | models.Q(meeting_link__icontains=query))
    if selected_role:
        meetings = [meeting for meeting in meetings if selected_role in (meeting.roles or [])]
    if selected_status in dict(Meeting.Status.choices):
        meetings = meetings.filter(status=selected_status) if hasattr(meetings, "filter") else [meeting for meeting in meetings if meeting.status == selected_status]
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(meetings, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return _owner_render(
        request,
        "accounts/owner_meetings.html",
        {
            "meetings": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "selected_role": selected_role,
            "selected_status": selected_status,
            "query_string": query_params.urlencode(),
            "role_choices": Role.choices,
            "status_choices": Meeting.Status.choices,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_meeting_create(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = MeetingForm(request.POST or None, company=company, prefix="meeting")
    if request.method == "POST" and form.is_valid():
        meeting = form.save(commit=False)
        meeting.company = company
        meeting.created_by = request.user
        meeting.audience_type = Meeting.AudienceType.ROLE
        meeting.location = ""
        meeting.status = Meeting.Status.ACTIVE if meeting.is_active else Meeting.Status.CANCELLED
        meeting.save()
        meeting.employees.clear()
        messages.success(request, "Online meeting created.")
        _send_meeting_emails(request, meeting, "Online meeting scheduled")
        return redirect("accounts:owner_meetings")
    return _owner_render(
        request,
        "accounts/owner_meeting_form.html",
        {"form": form, "mode": "create", "submit_label": "Create Meeting", "user_profile": user_profile},
    )


@login_required
def owner_meeting_edit(request, meeting_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    meeting = get_object_or_404(Meeting.objects.filter(company=company), id=meeting_id)
    form = MeetingForm(request.POST or None, instance=meeting, company=company, prefix="meeting")
    if request.method == "POST" and form.is_valid():
        meeting = form.save(commit=False)
        meeting.audience_type = Meeting.AudienceType.ROLE
        meeting.location = ""
        meeting.status = Meeting.Status.ACTIVE if meeting.is_active else meeting.status
        meeting.save()
        meeting.employees.clear()
        messages.success(request, "Online meeting updated.")
        _send_meeting_emails(request, meeting, "Online meeting updated")
        return redirect("accounts:owner_meetings")
    return _owner_render(
        request,
        "accounts/owner_meeting_form.html",
        {"form": form, "meeting": meeting, "mode": "edit", "submit_label": "Update Meeting", "user_profile": user_profile},
    )


def _profile_email_targets(profiles):
    targets = []
    seen = set()
    for profile_item in profiles.select_related("user"):
        email = (profile_item.user.email or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        targets.append({
            "email": email,
            "name": profile_item.user.get_full_name() or email,
            "role": profile_item.get_role_display(),
        })
    return targets


def _meeting_email_targets(meeting):
    profiles = UserProfile.objects.filter(company=meeting.company).exclude(user__email="")
    profiles = profiles.filter(role__in=meeting.roles or [])
    return _profile_email_targets(profiles)


def _event_email_targets(event):
    profiles = UserProfile.objects.filter(company=event.company).exclude(user__email="")
    if not event.is_global:
        profiles = profiles.filter(role__in=event.roles or [])
    return _profile_email_targets(profiles)


def _format_dt(value):
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p") if value else ""


def _send_meeting_emails(request, meeting, action_label):
    sent_count = 0
    failed_count = 0
    for target in _meeting_email_targets(meeting):
        try:
            send_meeting_notification_email(
                to_email=target["email"],
                name=target["name"],
                meeting_title=meeting.title,
                starts_at=_format_dt(meeting.starts_at),
                ends_at=_format_dt(meeting.ends_at),
                location=meeting.location,
                meeting_link=meeting.meeting_link,
                description=meeting.description,
                action_label=action_label,
            )
            sent_count += 1
        except Exception:
            failed_count += 1
    if sent_count:
        messages.success(request, f"Meeting email sent to {sent_count} employee(s).")
    if failed_count:
        messages.warning(request, f"Meeting saved, but {failed_count} email(s) could not be sent.")


def _event_audience_label(event):
    if event.is_global:
        return "All roles"
    return ", ".join(_role_label(role) for role in (event.roles or [])) or "Selected roles"


def _send_event_emails(request, event, action_label):
    sent_count = 0
    failed_count = 0
    for target in _event_email_targets(event):
        try:
            send_event_notification_email(
                to_email=target["email"],
                name=target["name"],
                event_title=event.title,
                starts_at=_format_dt(event.starts_at),
                ends_at=_format_dt(event.ends_at),
                caption=event.caption,
                description=event.description,
                action_label=action_label,
                audience_label=_event_audience_label(event),
            )
            sent_count += 1
        except Exception:
            failed_count += 1
    if sent_count:
        messages.success(request, f"Event email sent to {sent_count} employee(s).")
    if failed_count:
        messages.warning(request, f"Event action completed, but {failed_count} email(s) could not be sent.")


@login_required
def owner_events(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")

    form_kind = request.POST.get("form_kind")
    if request.method == "POST" and form_kind == "event_bulk":
        selected = CompanyEvent.objects.filter(company=company, id__in=request.POST.getlist("event_ids"))
        action = request.POST.get("action")
        if not selected.exists():
            messages.error(request, "Select at least one event.")
            return redirect("accounts:owner_events")
        if action == "activate":
            for event in selected:
                _send_event_emails(request, event, "Event activated")
            updated = selected.update(is_active=True)
            messages.success(request, f"Activated {updated} event(s).")
        elif action == "deactivate":
            for event in selected:
                _send_event_emails(request, event, "Event deactivated")
            updated = selected.update(is_active=False)
            messages.success(request, f"Deactivated {updated} event(s).")
        elif action == "popup_on":
            for event in selected:
                _send_event_emails(request, event, "Event marked important")
            updated = selected.update(show_as_popup=True)
            messages.success(request, f"Enabled popup for {updated} event(s).")
        elif action == "popup_off":
            for event in selected:
                _send_event_emails(request, event, "Event popup removed")
            updated = selected.update(show_as_popup=False)
            messages.success(request, f"Disabled popup for {updated} event(s).")
        elif action == "delete":
            for event in selected:
                _send_event_emails(request, event, "Event cancelled")
            count = selected.count()
            selected.delete()
            messages.success(request, f"Deleted {count} event(s).")
        else:
            messages.error(request, "Choose a valid bulk action.")
        return redirect("accounts:owner_events")

    events = CompanyEvent.objects.filter(company=company).select_related("created_by")
    selected_period = request.GET.get("period", "upcoming").strip()
    today = timezone.localdate()
    if selected_period == "past":
        events = events.filter(starts_at__date__lt=today)
    elif selected_period == "upcoming":
        events = events.filter(starts_at__date__gte=today)
    elif selected_period == "active":
        events = events.filter(is_active=True)
    elif selected_period == "inactive":
        events = events.filter(is_active=False)
    elif selected_period == "popup":
        events = events.filter(show_as_popup=True)
    elif selected_period != "all":
        selected_period = "upcoming"
        events = events.filter(starts_at__date__gte=today)

    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(events, 8)
    page_obj = paginator.get_page(request.GET.get("page"))
    all_events = CompanyEvent.objects.filter(company=company)
    upcoming_count = all_events.filter(starts_at__date__gte=today).count()
    past_count = all_events.filter(starts_at__date__lt=today).count()
    return _owner_render(
        request,
        "accounts/owner_events.html",
        {
            "events": page_obj.object_list,
            "page_obj": page_obj,
            "selected_period": selected_period,
            "query_string": query_params.urlencode(),
            "event_stats": {
                "total": all_events.count(),
                "upcoming": upcoming_count,
                "past": past_count,
                "active": all_events.filter(is_active=True).count(),
                "inactive": all_events.filter(is_active=False).count(),
                "popup": all_events.filter(show_as_popup=True).count(),
            },
            "user_profile": user_profile,
        },
    )


def _event_visible_for_role(event, role):
    return bool(event.is_global or role in (event.roles or []))


@login_required
def owner_event_create(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = CompanyEventForm(request.POST or None, request.FILES or None, prefix="event")
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.company = company
        event.created_by = request.user
        event.save()
        messages.success(request, "Event published.")
        _send_event_emails(request, event, "Event published")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return _owner_render(
        request,
        "accounts/owner_event_form.html",
        {"form": form, "mode": "create", "submit_label": "Publish Event", "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def owner_event_detail(request, event_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    event = get_object_or_404(
        CompanyEvent.objects.filter(company=company).select_related("created_by"),
        id=event_id,
    )
    form_kind = request.POST.get("form_kind")
    if request.method == "POST" and form_kind == "event_action":
        action = request.POST.get("action")
        if action == "toggle":
            event.is_active = not event.is_active
            event.save(update_fields=["is_active"])
            messages.success(request, "Event status updated.")
            _send_event_emails(request, event, "Event activated" if event.is_active else "Event deactivated")
        elif action == "popup":
            event.show_as_popup = not event.show_as_popup
            event.save(update_fields=["show_as_popup"])
            messages.success(request, "Event popup setting updated.")
            _send_event_emails(request, event, "Event marked important" if event.show_as_popup else "Event popup removed")
        elif action == "delete":
            _send_event_emails(request, event, "Event cancelled")
            event.delete()
            messages.success(request, "Event deleted.")
            return redirect("accounts:owner_events")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return _owner_render(
        request,
        "accounts/owner_event_detail.html",
        {"event": event, "user_profile": user_profile},
    )


@login_required
def owner_event_edit(request, event_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    event = get_object_or_404(CompanyEvent.objects.filter(company=company), id=event_id)
    form = CompanyEventForm(request.POST or None, request.FILES or None, instance=event, prefix="event")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Event updated.")
        _send_event_emails(request, event, "Event updated")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return _owner_render(
        request,
        "accounts/owner_event_edit.html",
        {"event": event, "form": form, "submit_label": "Update Event", "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def event_detail(request, event_id):
    user_profile, company, _ = _profile_context(request)
    event = get_object_or_404(CompanyEvent, company=company, id=event_id, is_active=True)
    role = getattr(user_profile, "role", "")
    if not event.is_global and role not in (event.roles or []):
        raise Http404("Event not found")
    return render(request, "accounts/event_detail.html", {"event": event, "user_profile": user_profile})


@login_required
def owner_referrals(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    setting, _ = ReferralSetting.objects.get_or_create(company=company)
    form = ReferralSettingForm(request.POST or None, instance=setting, prefix="referral")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Referral settings updated.")
        return redirect("accounts:owner_referrals")
    rewards = (
        ReferralReward.objects.filter(company=company)
        .select_related("referrer", "referrer__profile", "referred_user", "referred_user__profile", "signup_request")
        .order_by("-activated_at", "-created_at")
    )
    referral_stats = {
        "active_rewards": rewards.filter(status=ReferralReward.Status.ACTIVE).count(),
        "total_referrer_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referrer_reward_amount"))["total"] or 0,
        "total_referred_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referred_reward_amount"))["total"] or 0,
        "pending_references": SignupRequest.objects.filter(
            channel_partner_reference__gt="",
            status__in=[SignupRequestStatus.OTP_PENDING, SignupRequestStatus.PENDING_APPROVAL],
        ).count(),
    }
    paginator = Paginator(rewards, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return _owner_render(
        request,
        "accounts/owner_referrals.html",
        {
            "form": form,
            "setting": setting,
            "referral_stats": referral_stats,
            "page_obj": page_obj,
            "rewards": page_obj.object_list,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_targets(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = RoleTargetForm(request.POST or None, company=company, prefix="target")
    if request.method == "POST" and form.is_valid():
        target = form.save(commit=False)
        target.company = company
        target.assigned_by = request.user
        target.save()
        messages.success(request, "Target saved.")
        return redirect("accounts:owner_targets")
    return _owner_render(request, "accounts/owner_targets.html", {"form": form, "targets": RoleTarget.objects.filter(company=company), "user_profile": user_profile})


def _set_single_active_popup(company, popup):
    if popup.is_active:
        SoftwarePopup.objects.filter(company=company, is_active=True).exclude(id=popup.id).update(is_active=False)


@login_required
def owner_popups(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        selected_ids = request.POST.getlist("popup_ids")
        action = request.POST.get("bulk_action", "").strip()
        selected_popups = SoftwarePopup.objects.filter(company=company, id__in=selected_ids)
        if not selected_popups.exists():
            messages.error(request, "Select at least one popup.")
            return redirect("accounts:owner_popups")
        if action == "activate":
            if selected_popups.count() != 1:
                messages.error(request, "Only one popup can be active. Select one popup to activate.")
                return redirect("accounts:owner_popups")
            popup = selected_popups.first()
            SoftwarePopup.objects.filter(company=company).exclude(id=popup.id).update(is_active=False)
            popup.is_active = True
            popup.save(update_fields=["is_active"])
            messages.success(request, "Popup activated. Other popups were deactivated automatically.")
        elif action == "deactivate":
            updated = selected_popups.update(is_active=False)
            messages.success(request, f"{updated} popup(s) deactivated.")
        elif action == "delete":
            deleted_count = selected_popups.count()
            selected_popups.delete()
            messages.success(request, f"{deleted_count} popup(s) deleted.")
        else:
            messages.error(request, "Choose a valid popup action.")
        return redirect("accounts:owner_popups")

    popups = SoftwarePopup.objects.filter(company=company).order_by("-is_active", "-created_at")
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        popups = popups.filter(models.Q(title__icontains=query) | models.Q(message__icontains=query) | models.Q(deal_label__icontains=query))
    if selected_role:
        popups = [popup for popup in popups if selected_role in (popup.roles or [])]
    if selected_status == "active":
        popups = popups.filter(is_active=True) if hasattr(popups, "filter") else [popup for popup in popups if popup.is_active]
    elif selected_status == "inactive":
        popups = popups.filter(is_active=False) if hasattr(popups, "filter") else [popup for popup in popups if not popup.is_active]
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(popups, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return _owner_render(
        request,
        "accounts/owner_popups.html",
        {
            "popups": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "selected_role": selected_role,
            "selected_status": selected_status,
            "query_string": query_params.urlencode(),
            "role_choices": Role.choices,
            "status_choices": (("active", "Active"), ("inactive", "Inactive")),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_popup_create(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save(commit=False)
        popup.company = company
        popup.save()
        _set_single_active_popup(company, popup)
        messages.success(request, "Offer popup created.")
        return redirect("accounts:owner_popups")
    return _owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": None, "mode": "create", "user_profile": user_profile},
    )


@login_required
def owner_popup_detail(request, popup_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=company)
    return _owner_render(
        request,
        "accounts/owner_popup_detail.html",
        {"popup": popup, "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def owner_popup_edit(request, popup_id):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=company)
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, instance=popup, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save()
        _set_single_active_popup(company, popup)
        messages.success(request, "Offer popup updated.")
        return redirect("accounts:owner_popups")
    return _owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": popup, "mode": "edit", "user_profile": user_profile},
    )


@login_required
def owner_role_matrix(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = RoleMatrixRuleForm(request.POST or None, prefix="matrix")
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.company = company
        rule.save()
        messages.success(request, "Role matrix rule saved.")
        return redirect("accounts:owner_role_matrix")
    return _owner_render(request, "accounts/owner_role_matrix.html", {"form": form, "rules": RoleMatrixRule.objects.filter(company=company), "user_profile": user_profile})


@login_required
def owner_email_changes(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST" and request.POST.get("approve_request"):
        change = EmployeeEmailChangeRequest.objects.filter(company=company, id=request.POST.get("approve_request")).first()
        if change:
            if change.status != EmployeeEmailChangeRequest.Status.PENDING:
                messages.error(request, "Only pending email change requests can be approved.")
            elif not change.is_email_verified:
                messages.error(request, "Verify the OTP sent to the new email before changing employee email.")
            else:
                old_email = change.employee.email
                if change.approve(approved_by=request.user):
                    _send_email_change_applied_email(change, old_email)
                    messages.success(request, "Employee email changed.")
                else:
                    messages.error(request, "Email request is not verified yet.")
        return redirect("accounts:owner_email_changes")
    if request.method == "POST" and request.POST.get("verify_request"):
        change = EmployeeEmailChangeRequest.objects.filter(
            company=company,
            id=request.POST.get("verify_request"),
            status=EmployeeEmailChangeRequest.Status.PENDING,
        ).first()
        otp_code = request.POST.get("otp_code", "").strip()
        if not change:
            messages.error(request, "Email change request not found.")
            return redirect("accounts:owner_email_changes")
        otp = EmailOTP.objects.filter(email__iexact=change.requested_email, is_used=False).order_by("-created_at").first()
        if not otp or otp.is_expired:
            messages.error(request, "OTP expired. Resend a new OTP.")
            return redirect("accounts:owner_email_changes")
        if otp.attempts >= 5:
            messages.error(request, "Too many OTP attempts. Resend a new OTP.")
            return redirect("accounts:owner_email_changes")
        if otp_code != otp.code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            messages.error(request, "Invalid OTP.")
            return redirect("accounts:owner_email_changes")
        User = get_user_model()
        if User.objects.filter(email__iexact=change.requested_email).exclude(id=change.employee_id).exists():
            messages.error(request, "This email is already used by another employee.")
            return redirect("accounts:owner_email_changes")
        change.mark_verified()
        messages.success(request, "OTP verified. You can approve the email change now.")
        otp.is_used = True
        otp.user = change.employee
        otp.save(update_fields=["is_used", "user"])
        return redirect("accounts:owner_email_changes")
    if request.method == "POST" and request.POST.get("resend_request"):
        change = EmployeeEmailChangeRequest.objects.filter(
            company=company,
            id=request.POST.get("resend_request"),
            status=EmployeeEmailChangeRequest.Status.PENDING,
        ).first()
        if change:
            latest_otp = EmailOTP.objects.filter(email__iexact=change.requested_email).order_by("-created_at").first()
            if latest_otp:
                elapsed = (timezone.now() - latest_otp.created_at).total_seconds()
                if elapsed < OTP_RESEND_WAIT_SECONDS:
                    messages.error(request, f"Please wait {int(OTP_RESEND_WAIT_SECONDS - elapsed)} seconds before resending OTP.")
                    return redirect("accounts:owner_email_changes")
            otp = EmailOTP.create_for_email(change.requested_email)
            otp.user = change.employee
            otp.save(update_fields=["user"])
            send_otp_email(to_email=change.requested_email, code=otp.code, purpose="email_change")
            messages.success(request, "OTP resent to requested email.")
        return redirect("accounts:owner_email_changes")
    if request.method == "POST" and request.POST.get("reject_request"):
        change = EmployeeEmailChangeRequest.objects.filter(company=company, id=request.POST.get("reject_request")).first()
        if change:
            change.status = EmployeeEmailChangeRequest.Status.REJECTED
            change.save(update_fields=["status", "updated_at"])
            messages.success(request, "Email change request rejected.")
        return redirect("accounts:owner_email_changes")

    requests = EmployeeEmailChangeRequest.objects.filter(company=company).select_related("employee", "employee__profile", "requested_by", "approved_by")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    otp_state = request.GET.get("otp", "").strip()
    role = request.GET.get("role", "").strip()
    if query:
        requests = requests.filter(
            models.Q(employee__first_name__icontains=query)
            | models.Q(employee__last_name__icontains=query)
            | models.Q(employee__email__icontains=query)
            | models.Q(requested_email__icontains=query)
            | models.Q(employee__profile__employee_code__icontains=query)
        )
    if status:
        requests = requests.filter(status=status)
    if otp_state == "verified":
        requests = requests.filter(is_email_verified=True)
    elif otp_state == "pending":
        requests = requests.filter(is_email_verified=False, status=EmployeeEmailChangeRequest.Status.PENDING)
    if role:
        requests = requests.filter(employee__profile__role=role)

    paginator = Paginator(requests, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return _owner_render(
        request,
        "accounts/owner_email_changes.html",
        {
            "page_obj": page_obj,
            "requests": page_obj.object_list,
            "status_choices": EmployeeEmailChangeRequest.Status.choices,
            "role_choices": Role.choices,
            "selected_status": status,
            "selected_otp": otp_state,
            "selected_role": role,
            "query": query,
            "query_string": query_params.urlencode(),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_email_change_create(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = EmployeeEmailChangeRequestForm(request.POST or None, company=company, prefix="emailchange")
    if request.method == "POST" and form.is_valid():
        change = form.save(commit=False)
        change.company = company
        change.requested_by = request.user
        change.save()
        otp = EmailOTP.create_for_email(change.requested_email)
        otp.user = change.employee
        otp.save(update_fields=["user"])
        send_otp_email(to_email=change.requested_email, code=otp.code, purpose="email_change")
        messages.success(request, "Email change request saved and OTP sent to requested email.")
        return redirect("accounts:owner_email_changes")

    return _owner_render(
        request,
        "accounts/owner_email_change_create.html",
        {
            "form": form,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_support(request):
    user_profile, company, allowed = _owner_context_or_redirect(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        support = AuthenticationSupportRequest.objects.filter(id=request.POST.get("support_id")).first()
        if support:
            support.is_resolved = request.POST.get("status") == "resolved"
            support.save(update_fields=["is_resolved"])
            messages.success(request, "Support ticket status updated.")
        return redirect("accounts:owner_support")
    return _owner_render(request, "accounts/owner_support.html", {"support_requests": AuthenticationSupportRequest.objects.all(), "user_profile": user_profile})
