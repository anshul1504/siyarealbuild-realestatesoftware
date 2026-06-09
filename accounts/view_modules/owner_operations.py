from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import get_object_or_404, redirect

from ..forms import OfficeLocationForm, RoleMatrixRuleForm
from ..models import AuthenticationSupportRequest, AuditLog, NotificationDelivery, OfficeLocation, RoleMatrixRule
from ..services import record_audit
from .owner_common import owner_context, owner_render


@login_required
def owner_role_matrix(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = RoleMatrixRuleForm(request.POST or None, prefix="matrix")
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.company = company
        rule.save()
        messages.success(request, "Role matrix rule saved.")
        return redirect("accounts:owner_role_matrix")
    return owner_render(request, "accounts/owner_role_matrix.html", {"form": form, "rules": RoleMatrixRule.objects.filter(company=company), "user_profile": user_profile})


@login_required
def owner_support(request):
    user_profile, _company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        support = AuthenticationSupportRequest.objects.filter(id=request.POST.get("support_id")).first()
        if support:
            support.is_resolved = request.POST.get("status") == "resolved"
            support.save(update_fields=["is_resolved"])
            messages.success(request, "Support ticket status updated.")
        return redirect("accounts:owner_support")
    return owner_render(request, "accounts/owner_support.html", {"support_requests": AuthenticationSupportRequest.objects.all(), "user_profile": user_profile})


@login_required
def owner_office_locations(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    location = OfficeLocation.objects.filter(company=company, id=request.GET.get("edit")).first()
    form = OfficeLocationForm(request.POST or None, instance=location)
    if request.method == "POST":
        if request.POST.get("delete_id"):
            target = get_object_or_404(OfficeLocation, company=company, id=request.POST["delete_id"])
            record_audit(actor=request.user, action="office_location.deleted", target=target, company=company)
            target.delete()
            return redirect("accounts:owner_office_locations")
        if form.is_valid():
            target = form.save(commit=False)
            target.company = company
            target.save()
            record_audit(actor=request.user, action="office_location.saved", target=target, company=company)
            return redirect("accounts:owner_office_locations")
    return owner_render(request, "accounts/owner_office_locations.html", {"form": form, "locations": OfficeLocation.objects.filter(company=company), "user_profile": user_profile})


@login_required
def owner_audit_logs(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    return owner_render(request, "accounts/owner_audit_logs.html", {"logs": AuditLog.objects.filter(company=company).select_related("actor")[:200], "user_profile": user_profile})


@login_required
def owner_notification_deliveries(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    deliveries = NotificationDelivery.objects.filter(models.Q(company=company) | models.Q(company__isnull=True))[:200]
    return owner_render(request, "accounts/owner_notification_deliveries.html", {"deliveries": deliveries, "user_profile": user_profile})
