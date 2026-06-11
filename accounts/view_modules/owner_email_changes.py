from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import redirect
from django.utils import timezone

from ..email_utils import send_email_updated_email, send_otp_email
from ..forms import EmployeeEmailChangeRequestForm
from ..models import EmailOTP, EmployeeEmailChangeRequest, Role
from ..services import record_audit
from .owner_common import owner_context, owner_render


OTP_RESEND_WAIT_SECONDS = 60


def _send_email_change_applied_email(change, old_email):
    profile = getattr(change.employee, "profile", None)
    send_email_updated_email(
        to_email=change.requested_email,
        name=change.employee.get_full_name() or change.employee.username,
        old_email=old_email,
        new_email=change.requested_email,
        role_label=profile.get_role_display() if profile else "",
        employee_code=profile.employee_code if profile else "",
    )
@login_required
def owner_email_changes(request):
    user_profile, company, allowed = owner_context(request)
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
                    record_audit(actor=request.user, action="employee.email_change_approved", target=change, company=company, details={"old_email": old_email, "new_email": change.requested_email})
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
        if not otp.matches(otp_code):
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
            record_audit(actor=request.user, action="employee.email_change_rejected", target=change, company=company)
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
    return owner_render(
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
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = EmployeeEmailChangeRequestForm(request.POST or None, company=company, prefix="emailchange")
    if request.method == "POST" and form.is_valid():
        change = form.save(commit=False)
        change.company = company
        change.requested_by = request.user
        change.save()
        record_audit(actor=request.user, action="employee.email_change_requested", target=change, company=company, details={"requested_email": change.requested_email})
        otp = EmailOTP.create_for_email(change.requested_email)
        otp.user = change.employee
        otp.save(update_fields=["user"])
        send_otp_email(to_email=change.requested_email, code=otp.code, purpose="email_change")
        messages.success(request, "Email change request saved and OTP sent to requested email.")
        return redirect("accounts:owner_email_changes")

    return owner_render(
        request,
        "accounts/owner_email_change_create.html",
        {
            "form": form,
            "user_profile": user_profile,
        },
    )
