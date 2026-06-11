import csv

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from ..email_utils import send_employee_custom_email
from ..forms import EmployeeBulkUpdateForm, TeamEmailMessageForm, UserProfileForm
from ..models import EmailOTP, EmployeeEmailChangeRequest, EmployeeInvite, EmployeeProfileChange, NotificationDelivery, Role, SignupRequest, TeamEmailMessage, UserProfile
from ..policies import role_matrix_allows, visible_team_profiles_for
from ..services import bulk_update_profiles, record_audit, record_notification_delivery, update_employee_profile


def _profile_context(request):
    user_profile = getattr(request.user, "profile", None)
    return user_profile, getattr(user_profile, "company", None), getattr(user_profile, "role", "") == Role.COMPANY_OWNER
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
    if user_profile.role != Role.COMPANY_OWNER or not role_matrix_allows(user_profile, "delete"):
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
    record_audit(actor=request.user, action="employee.bulk_deleted", target=request.user, company=company, details={"count": deleted_count, "employee_ids": user_ids})
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
        try:
            send_employee_custom_email(
                to_email=profile_item.user.email,
                name=profile_item.user.get_full_name() or profile_item.user.email,
                subject=subject,
                message=message,
                sender_name=sender_name,
            )
            record_notification_delivery(company=company, sent_by=request.user, category="team_bulk_email", recipient=profile_item.user.email, subject=subject, status=NotificationDelivery.Status.SENT)
            sent_count += 1
        except Exception as exc:
            record_notification_delivery(company=company, sent_by=request.user, category="team_bulk_email", recipient=profile_item.user.email, subject=subject, status=NotificationDelivery.Status.FAILED, error_message=str(exc)[:500])

    if sent_count:
        record_audit(actor=request.user, action="employee.bulk_email_sent", target=request.user, company=company, details={"count": sent_count, "role": role, "department": department, "subject": subject})
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
                try:
                    send_employee_custom_email(
                        to_email=profile_item.user.email,
                        name=recipient_name,
                        subject=subject,
                        message=message,
                        sender_name=sender_name,
                    )
                    delivery_status = NotificationDelivery.Status.SENT
                    delivery_error = ""
                except Exception as exc:
                    delivery_status = NotificationDelivery.Status.FAILED
                    delivery_error = str(exc)[:500]
                record_notification_delivery(company=company, sent_by=request.user, category="team_email", recipient=profile_item.user.email, subject=subject, status=delivery_status, error_message=delivery_error)
                recipients.append({
                    "name": recipient_name,
                    "email": profile_item.user.email,
                    "role": profile_item.get_role_display(),
                    "department": profile_item.department or "",
                    "status": delivery_status,
                    "error": delivery_error,
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
            record_audit(actor=request.user, action="employee.team_email_sent", target=team_email, company=company, details={"count": len(recipients), "role": role, "department": department})
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
    return visible_team_profiles_for(user_profile, company)


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
            "can_view_private_profile_data": can_view_sensitive_profile_data,
        },
    )


@login_required
def team_profile_edit(request, profile_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER or not role_matrix_allows(user_profile, "update"):
        messages.error(request, "Only company owner can edit employee profiles.")
        return redirect("accounts:team_profile_detail", profile_id=profile_id)
    profile = get_object_or_404(UserProfile.objects.select_related("user"), id=profile_id, company=company)
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=profile, user=profile.user, allow_official_fields=True)
    if request.method == "POST" and form.is_valid():
        update_employee_profile(profile=profile, form=form, actor=request.user)
        messages.success(request, "Employee profile updated and recorded.")
        return redirect("accounts:team_profile_detail", profile_id=profile.id)
    section_names = {
        "Basic": {"full_name", "email", "profile_image", "phone", "designation"},
        "Personal & KYC": {"date_of_birth", "gender", "blood_group", "marital_status", "personal_email", "aadhaar_number", "aadhaar_document", "pan_number", "pan_document"},
        "Official Work Details": {"department", "reporting_manager", "joining_date", "work_location", "territory", "channel_partner_reference"},
        "Bank, Emergency & Address": {"bank_name", "bank_account_name", "bank_account_number", "bank_ifsc", "emergency_contact_name", "emergency_contact_phone", "address", "city", "state", "pincode"},
    }
    form_sections = [(name, [form[field] for field in form.fields if field in fields]) for name, fields in section_names.items()]
    return render(request, "accounts/team_profile_edit.html", {"form": form, "form_sections": form_sections, "employee_profile": profile, "user_profile": user_profile})


@login_required
def team_profile_history(request, profile_id):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER or not role_matrix_allows(user_profile, "update"):
        messages.error(request, "Only company owner can view employee profile history.")
        return redirect("accounts:team_profile_detail", profile_id=profile_id)
    profile = get_object_or_404(UserProfile.objects.select_related("user"), id=profile_id, company=company)
    changes = EmployeeProfileChange.objects.filter(profile=profile).select_related("changed_by")[:100]
    return render(request, "accounts/team_profile_history.html", {"employee_profile": profile, "changes": changes, "user_profile": user_profile})


@login_required
def profile_document(request, profile_id, document_type):
    user_profile, company, _ = _profile_context(request)
    profile = get_object_or_404(UserProfile, id=profile_id, company=company)
    if request.user != profile.user and user_profile.role != Role.COMPANY_OWNER:
        raise Http404("Document not found.")
    field_name = {"aadhaar": "aadhaar_document", "pan": "pan_document"}.get(document_type)
    if not field_name:
        raise Http404("Document not found.")
    document = getattr(profile, field_name)
    if not document:
        raise Http404("Document not found.")
    return FileResponse(document.open("rb"), as_attachment=True, filename=document.name.rsplit("/", 1)[-1])


@login_required
def team_profiles_bulk_update(request):
    user_profile, company, _ = _profile_context(request)
    if user_profile.role != Role.COMPANY_OWNER or not role_matrix_allows(user_profile, "delete"):
        return redirect("properties:dashboard")
    profiles = UserProfile.objects.filter(company=company).exclude(role=Role.COMPANY_OWNER).select_related("user")
    form = EmployeeBulkUpdateForm(request.POST or None, profiles=profiles)
    if request.method == "POST" and form.is_valid():
        count = bulk_update_profiles(profiles=profiles.filter(id__in=form.cleaned_data["profile_ids"]), actor=request.user, department=form.cleaned_data["department"], reporting_manager=form.cleaned_data["reporting_manager"], work_location=form.cleaned_data["work_location"])
        messages.success(request, f"{count} employee profile(s) updated.")
        return redirect("accounts:team_profiles")
    return render(request, "accounts/team_profiles_bulk_update.html", {"form": form, "user_profile": user_profile})


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
    record_audit(
        actor=request.user,
        action="employee.deleted",
        target=employee_profile,
        company=company,
        target_label=employee_name,
        details={"email": employee_user.email, "role": employee_profile.role, "employee_code": employee_profile.employee_code},
    )
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
