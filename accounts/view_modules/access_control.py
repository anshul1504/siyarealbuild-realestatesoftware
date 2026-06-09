from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render

from ..email_utils import send_role_change_rejected_email, send_role_change_requested_email, send_role_changed_email
from ..forms import EmployeeRoleChangeRequestForm
from ..models import EmployeeRoleChangeRequest, Role, UserProfile
from .auth_profile_company import profile_context
def access_control(request):
    user_profile, company, is_owner = profile_context(request)
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
def role_change_request_list(request):
    user_profile, company, is_owner = profile_context(request)
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
    user_profile, company, is_owner = profile_context(request)
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
    user_profile, company, is_owner = profile_context(request)
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
