from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..email_utils import send_otp_email, send_signup_pending_review_email
from django.views.decorators.http import require_http_methods

from ..forms import AddEmployeeForm, EmployeeInviteForm
from ..models import DesignationCodeRule, EmailOTP, EmployeeInvite, ReferralReward, ReferralSetting, Role, SignupRequest, SignupRequestStatus, UserProfile


ADD_EMPLOYEE_EMAIL_RESEND_SECONDS = 30
INVITE_RESEND_WAIT_SECONDS = 60


def _profile_context(request):
    user_profile = getattr(request.user, "profile", None)
    return user_profile, getattr(user_profile, "company", None), getattr(user_profile, "role", "") == Role.COMPANY_OWNER


def _resend_remaining_seconds(request, session_key):
    raw_available_at = request.session.get(session_key)
    if not raw_available_at:
        return 0
    try:
        available_at = datetime.fromisoformat(raw_available_at)
    except ValueError:
        request.session.pop(session_key, None)
        return 0
    return max(0, int((available_at - timezone.now()).total_seconds()))


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
