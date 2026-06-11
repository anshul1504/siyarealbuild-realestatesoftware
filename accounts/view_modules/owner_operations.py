from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from ..forms import OfficeLocationForm, RoleMatrixRuleForm
from ..models import AuthenticationSupportRequest, AuditLog, CompanyEvent, Meeting, NotificationDelivery, OfficeLocation, RoleMatrixRule, RoleTarget, SoftwarePopup
from ..operations import OPERATIONS_MODULE, can_perform_operations
from ..services import record_audit
from .owner_common import owner_context, owner_render


@login_required
def owner_operations_dashboard(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    context = {
        "support_open": AuthenticationSupportRequest.objects.filter(is_resolved=False).count(),
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
        support = AuthenticationSupportRequest.objects.filter(id=request.POST.get("support_id")).first()
        if support:
            support.is_resolved = request.POST.get("status") == "resolved"
            support.owner_note = request.POST.get("owner_note", "").strip()
            support.resolved_at = timezone.now() if support.is_resolved else None
            support.save(update_fields=["is_resolved", "owner_note", "resolved_at"])
            record_audit(actor=request.user, action="operations.support_updated", target=support, company=company, details={"resolved": support.is_resolved})
            messages.success(request, "Support ticket status updated.")
        return redirect("accounts:owner_support")
    support_requests = AuthenticationSupportRequest.objects.all()
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status == "open":
        support_requests = support_requests.filter(is_resolved=False)
    elif status == "resolved":
        support_requests = support_requests.filter(is_resolved=True)
    if query:
        support_requests = support_requests.filter(models.Q(name__icontains=query) | models.Q(contact__icontains=query) | models.Q(issue__icontains=query))
    return owner_render(request, "accounts/owner_support.html", {"support_requests": support_requests[:100], "selected_status": status, "query": query, "user_profile": user_profile})


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
    return owner_render(request, "accounts/owner_audit_logs.html", {"logs": logs[:200], "query": query, "user_profile": user_profile})


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
    return owner_render(request, "accounts/owner_notification_deliveries.html", {"deliveries": deliveries[:200], "status_choices": NotificationDelivery.Status.choices, "selected_status": status, "query": query, "user_profile": user_profile})
