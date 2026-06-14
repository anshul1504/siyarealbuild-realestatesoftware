from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from ..forms import OfficeLocationForm, RoleMatrixRuleForm
from ..models import AuthenticationSupportRequest, AuditLog, CompanyEvent, Meeting, NotificationDelivery, OfficeLocation, RoleMatrixRule, RoleTarget, SoftwarePopup, UserProfile
from ..operations import OPERATIONS_MODULE, can_perform_operations
from ..services import record_audit
from .owner_common import owner_context, owner_render


def _support_queryset_for_company(company):
    other_company_emails = UserProfile.objects.exclude(company=company).values("user__email")
    return AuthenticationSupportRequest.objects.exclude(contact__in=other_company_emails)


@login_required
def owner_operations_dashboard(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    context = {
        "support_open": _support_queryset_for_company(company).filter(is_resolved=False).count(),
        "meetings_active": Meeting.objects.filter(company=company, is_active=True).count(),
        "events_active": CompanyEvent.objects.filter(company=company, is_active=True).count(),
        "popups_active": SoftwarePopup.objects.filter(company=company, is_active=True).count(),
        "targets_active": RoleTarget.objects.filter(company=company, status=RoleTarget.Status.ACTIVE).count(),
        "office_locations": OfficeLocation.objects.filter(company=company, is_active=True).count(),
        "failed_deliveries": NotificationDelivery.objects.filter(models.Q(company=company) | models.Q(company__isnull=True), status=NotificationDelivery.Status.FAILED).count(),
        "recent_audits": AuditLog.objects.filter(company=company).select_related("actor")[:8],
        "recent_deliveries": NotificationDelivery.objects.filter(models.Q(company=company) | models.Q(company__isnull=True))[:8],
        "user_profile": user_profile,
    }
    return owner_render(request, "accounts/owner_operations_dashboard.html", context)


@login_required
def owner_core_checklist(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    checklist = [
        ("Company detail add/edit", "Company master and settings are available for controlled add/edit.", reverse("accounts:company_detail")),
        ("Profile setting for owner", "Owner profile and email verification flow are active.", reverse("accounts:profile")),
        ("Employee code serial", "Serial rules and assigned code tracking are managed from owner operations.", reverse("accounts:owner_serial_rules")),
        ("Bulk invite / invite employee", "Invite list, bulk action, approval, resend, edit and add-employee flows are live.", reverse("accounts:employee_invite_list")),
        ("Referral reward", "Referral payout and coupon reward settings are owner controlled.", reverse("accounts:owner_referrals")),
        ("Coupon during booking", "Plot booking captures coupon code and coupon discount in deal value.", reverse("properties:list")),
        ("Create team meeting", "Owner can create, edit and track team meetings.", reverse("accounts:owner_meeting_create")),
        ("Post event", "Owner can post, edit and publish company events.", reverse("accounts:owner_event_create")),
        ("Add property / edit property", "Property create, edit, media, plots and document review workflow is active.", reverse("properties:create")),
        ("Manage commission", "Property commission rules and booking payout ledger are available.", reverse("properties:list")),
        ("See activity of each employee", "Audit logs and employee profile history expose staff activity.", reverse("accounts:owner_audit_logs")),
        ("Set target", "Role target creation, detail, edit and status tracking are live.", reverse("accounts:owner_targets")),
        ("Set popup / offer image", "Marketing popup and offer image management is available.", reverse("accounts:owner_popups")),
        ("Quotation to booking conversion", "Owner MIS reports generated quotation-to-booking conversion.", reverse("properties:owner_mis_report")),
        ("Role matrix manage", "Role-wise module permissions can be configured.", reverse("accounts:owner_role_matrix")),
        ("Change employee email", "Owner can initiate employee email changes on behalf of staff.", reverse("accounts:owner_email_changes")),
    ]
    return owner_render(
        request,
        "accounts/owner_core_checklist.html",
        {"checklist": checklist, "completed_count": len(checklist), "user_profile": user_profile, "company": company},
    )


@login_required
def owner_role_matrix(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST" and not can_perform_operations(user_profile, "update"):
        messages.error(request, "You do not have permission to update operations settings.")
        return redirect("accounts:owner_role_matrix")
    form = RoleMatrixRuleForm(request.POST or None, prefix="matrix")
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.company = company
        rule.save()
        record_audit(actor=request.user, action="operations.role_matrix_saved", target=rule, company=company)
        messages.success(request, "Role matrix rule saved.")
        return redirect("accounts:owner_role_matrix")
    return owner_render(request, "accounts/owner_role_matrix.html", {"form": form, "rules": RoleMatrixRule.objects.filter(company=company), "user_profile": user_profile})


@login_required
def owner_support(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        if not can_perform_operations(user_profile, "update"):
            messages.error(request, "You do not have permission to update support tickets.")
            return redirect("accounts:owner_support")
        support = _support_queryset_for_company(company).filter(id=request.POST.get("support_id")).first()
        if support:
            support.is_resolved = request.POST.get("status") == "resolved"
            support.owner_note = request.POST.get("owner_note", "").strip()
            support.resolved_at = timezone.now() if support.is_resolved else None
            support.save(update_fields=["is_resolved", "owner_note", "resolved_at"])
            record_audit(actor=request.user, action="operations.support_updated", target=support, company=company, details={"resolved": support.is_resolved})
            messages.success(request, "Support ticket status updated.")
        return redirect("accounts:owner_support")
    support_requests = _support_queryset_for_company(company)
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status == "open":
        support_requests = support_requests.filter(is_resolved=False)
    elif status == "resolved":
        support_requests = support_requests.filter(is_resolved=True)
    if query:
        support_requests = support_requests.filter(models.Q(name__icontains=query) | models.Q(contact__icontains=query) | models.Q(issue__icontains=query))
    paginator = Paginator(support_requests.order_by("-created_at"), 15)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return owner_render(
        request,
        "accounts/owner_support.html",
        {
            "support_requests": page_obj.object_list,
            "page_obj": page_obj,
            "query_string": query_params.urlencode(),
            "selected_status": status,
            "query": query,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_office_locations(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    location = OfficeLocation.objects.filter(company=company, id=request.GET.get("edit")).first()
    form = OfficeLocationForm(request.POST or None, instance=location)
    if request.method == "POST":
        if request.POST.get("delete_id"):
            if not can_perform_operations(user_profile, "delete"):
                messages.error(request, "You do not have permission to delete office locations.")
                return redirect("accounts:owner_office_locations")
            target = get_object_or_404(OfficeLocation, company=company, id=request.POST["delete_id"])
            record_audit(actor=request.user, action="office_location.deleted", target=target, company=company)
            target.delete()
            return redirect("accounts:owner_office_locations")
        if form.is_valid():
            if not can_perform_operations(user_profile, "update"):
                messages.error(request, "You do not have permission to update office locations.")
                return redirect("accounts:owner_office_locations")
            target = form.save(commit=False)
            target.company = company
            target.save()
            record_audit(actor=request.user, action="office_location.saved", target=target, company=company)
            return redirect("accounts:owner_office_locations")
    query = request.GET.get("q", "").strip()
    locations = OfficeLocation.objects.filter(company=company)
    if query:
        locations = locations.filter(models.Q(name__icontains=query) | models.Q(city__icontains=query) | models.Q(address__icontains=query))
    return owner_render(request, "accounts/owner_office_locations.html", {"form": form, "locations": locations, "query": query, "user_profile": user_profile})


@login_required
def owner_audit_logs(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    logs = AuditLog.objects.filter(company=company).select_related("actor")
    query = request.GET.get("q", "").strip()
    if query:
        logs = logs.filter(models.Q(action__icontains=query) | models.Q(target_label__icontains=query) | models.Q(target_type__icontains=query))
    paginator = Paginator(logs.order_by("-created_at"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return owner_render(
        request,
        "accounts/owner_audit_logs.html",
        {"logs": page_obj.object_list, "page_obj": page_obj, "query_string": query_params.urlencode(), "query": query, "user_profile": user_profile},
    )


@login_required
def owner_notification_deliveries(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    deliveries = NotificationDelivery.objects.filter(models.Q(company=company) | models.Q(company__isnull=True))
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        deliveries = deliveries.filter(status=status)
    if query:
        deliveries = deliveries.filter(models.Q(recipient__icontains=query) | models.Q(subject__icontains=query) | models.Q(category__icontains=query))
    paginator = Paginator(deliveries.order_by("-created_at"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return owner_render(
        request,
        "accounts/owner_notification_deliveries.html",
        {
            "deliveries": page_obj.object_list,
            "page_obj": page_obj,
            "query_string": query_params.urlencode(),
            "status_choices": NotificationDelivery.Status.choices,
            "selected_status": status,
            "query": query,
            "user_profile": user_profile,
        },
    )
