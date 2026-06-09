from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.models import AuthenticationSupportRequest, CompanyEvent, Role, SignupRequest, SignupRequestStatus, SoftwarePopup

from .helpers import visible_properties_for


@login_required
def dashboard(request):
    properties = visible_properties_for(request)
    stats = properties.aggregate(total_value=Sum("price"), total_properties=Count("id"))
    recent = properties[:5]
    user_profile = getattr(request.user, "profile", None)
    company = getattr(user_profile, "company", None)
    user_role = getattr(user_profile, "role", "")
    is_company_owner = user_role == Role.COMPANY_OWNER
    can_manage_properties = user_role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}
    pending_signup_requests = SignupRequest.objects.none()
    support_requests = AuthenticationSupportRequest.objects.none()
    if is_company_owner:
        pending_signup_requests = SignupRequest.objects.filter(
            status=SignupRequestStatus.PENDING_APPROVAL,
            is_email_verified=True,
        )[:5]
        support_requests = AuthenticationSupportRequest.objects.filter(is_resolved=False)[:5]
    visible_events = CompanyEvent.objects.none()
    dashboard_offer_popup = None
    if company:
        visible_events = [
            event
            for event in CompanyEvent.objects.filter(company=company, is_active=True)
            if event.is_global or user_role in (event.roles or [])
        ][:8]
        now = timezone.now()
        active_popups = (
            SoftwarePopup.objects.filter(company=company, is_active=True)
            .exclude(offer_image="")
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .order_by("-created_at")
        )
        dashboard_offer_popup = next((popup for popup in active_popups if user_role in (popup.roles or [])), None)
    return render(
        request,
        "properties/dashboard.html",
        {
            "properties": recent,
            "stats": stats,
            "active_count": properties.exclude(status__in=["sold", "rented"]).count(),
            "lead_total": sum(prop.lead_count for prop in properties),
            "is_company_owner": is_company_owner,
            "can_manage_properties": can_manage_properties,
            "pending_signup_requests": pending_signup_requests,
            "support_requests": support_requests,
            "visible_events": visible_events,
            "dashboard_offer_popup": dashboard_offer_popup,
        },
    )
