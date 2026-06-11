from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..email_utils import send_owner_custom_signup_email
from ..forms import DesignationCodeRuleForm, SignupBulkActionForm, SignupRequestCustomEmailForm, SignupRequestReviewForm
from ..models import DesignationCodeRule, EmailOTP, EmployeeInvite, Role, SignupRequest, SignupRequestOwnerMessage, SignupRequestStatus, UserProfile
from .onboarding import _next_employee_code
from .owner_common import owner_context, owner_render


@login_required
def owner_codes(request):
    return redirect("accounts:owner_serial_rules")


@login_required
def owner_assigned_codes(request):
    user_profile, company, allowed = owner_context(request)
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

    return owner_render(
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
    user_profile, company, allowed = owner_context(request)
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
    return owner_render(
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
    user_profile, company, allowed = owner_context(request)
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
        for signup in selected:
            action = signup_form.cleaned_data["action"]
            if action == "reject":
                signup.reject()
            else:
                signup.status = SignupRequestStatus.PENDING_APPROVAL
                signup.save(update_fields=["status", "updated_at"])
            updated += 1
        if updated:
            messages.success(request, f"{updated} signup request(s) updated.")
        return redirect("accounts:owner_requests")
    request_counts = {
        "signup_pending": signups.filter(status=SignupRequestStatus.PENDING_APPROVAL, is_email_verified=True).count(),
        "signup_otp": signups.filter(status=SignupRequestStatus.OTP_PENDING).count(),
        "signup_approved": SignupRequest.objects.filter(status=SignupRequestStatus.APPROVED).count(),
        "signup_rejected": SignupRequest.objects.filter(status=SignupRequestStatus.REJECTED).count(),
    }
    return owner_render(
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
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")

    requests = SignupRequest.objects.all().order_by("-updated_at", "-created_at")
    status = request.GET.get("status", "").strip()
    role = request.GET.get("role", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        requests = requests.filter(status=status)
    if role:
        requests = requests.filter(approved_role=role)
    if query:
        requests = requests.filter(models.Q(name__icontains=query) | models.Q(email__icontains=query) | models.Q(phone__icontains=query))

    paginator = Paginator(requests, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return owner_render(
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
    user_profile, company, allowed = owner_context(request)
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
    user_profile, company, allowed = owner_context(request)
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
                    elif not signup.approved_role:
                        review_form.add_error("approved_role", "Select a role before approving this signup request.")
                        messages.error(request, "Select a role before approving this signup request.")
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

    return owner_render(
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
