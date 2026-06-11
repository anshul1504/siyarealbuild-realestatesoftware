from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.models import AuthenticationSupportRequest, CompanyEvent, Role, SignupRequest, SignupRequestStatus, SoftwarePopup

from ..models import Property, PropertyVisit
from .helpers import visible_properties_for


def _percent(value, total):
    if not total:
        return 0
    return round((value / total) * 100)


def _choice_label(choices, value):
    return dict(choices).get(value, value.replace("_", " ").title())


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
    total_properties = stats["total_properties"] or 0
    total_value = stats["total_value"] or 0
    active_count = properties.exclude(status__in=[Property.Status.SOLD, Property.Status.RENTED]).count()
    lead_total = sum(prop.lead_count for prop in properties)
    avg_price = round(total_value / total_properties) if total_properties else 0
    total_plots = properties.aggregate(total=Sum("total_plots"))["total"] or 0
    available_plots = properties.aggregate(total=Sum("available_plots"))["total"] or 0
    conversion_count = properties.filter(status__in=[Property.Status.SOLD, Property.Status.RENTED]).count()
    conversion_percent = _percent(conversion_count, total_properties)

    status_counts = {row["status"]: row["count"] for row in properties.values("status").annotate(count=Count("id"))}
    status_chart = [
        {
            "label": _choice_label(Property.Status.choices, status),
            "count": status_counts.get(status, 0),
            "percent": _percent(status_counts.get(status, 0), total_properties),
        }
        for status, _label in Property.Status.choices
    ]
    category_counts = {row["category"]: row["count"] for row in properties.values("category").annotate(count=Count("id"))}
    category_chart = sorted(
        [
            {
                "label": _choice_label(Property.Category.choices, category),
                "count": count,
                "percent": _percent(count, total_properties),
            }
            for category, count in category_counts.items()
        ],
        key=lambda item: item["count"],
        reverse=True,
    )[:6]
    listing_counts = {row["listing_for"]: row["count"] for row in properties.values("listing_for").annotate(count=Count("id"))}
    listing_chart = [
        {
            "label": _choice_label(Property.ListingFor.choices, listing_for),
            "count": listing_counts.get(listing_for, 0),
            "percent": _percent(listing_counts.get(listing_for, 0), total_properties),
        }
        for listing_for, _label in Property.ListingFor.choices
    ]

    visits = PropertyVisit.objects.filter(property__in=properties)
    if not is_company_owner and user_role not in {Role.MANAGER, Role.TL}:
        visits = visits.filter(models.Q(assigned_employee=request.user) | models.Q(scheduled_by=request.user))
    upcoming_visits = visits.filter(visit_at__gte=timezone.now(), status=PropertyVisit.Status.SCHEDULED).count()
    completed_visits = visits.filter(status=PropertyVisit.Status.COMPLETED).count()
    followups_due = visits.filter(outcome=PropertyVisit.Outcome.NEGOTIATION).count() + visits.filter(status=PropertyVisit.Status.FOLLOW_UP).count()
    booked_visits = visits.filter(outcome__in=[PropertyVisit.Outcome.BOOKED, PropertyVisit.Outcome.CLOSED]).count()
    visit_total = visits.count()
    visit_chart = [
        {"label": "Upcoming", "count": upcoming_visits, "percent": _percent(upcoming_visits, max(visit_total, 1))},
        {"label": "Completed", "count": completed_visits, "percent": _percent(completed_visits, max(visit_total, 1))},
        {"label": "Follow-up", "count": followups_due, "percent": _percent(followups_due, max(visit_total, 1))},
        {"label": "Booked", "count": booked_visits, "percent": _percent(booked_visits, max(visit_total, 1))},
    ]

    role_actions = [
        {"label": "Property Directory", "caption": "Search inventory, status, plots and client-share actions.", "url_name": "properties:list", "icon": "home"},
        {"label": "My Profile", "caption": "Keep contact, role and personal details updated.", "url_name": "accounts:profile", "icon": "user"},
        {"label": "Company Overview", "caption": "View business details, contact points and documents.", "url_name": "accounts:company_detail", "icon": "building"},
    ]
    if can_manage_properties:
        role_actions.insert(1, {"label": "Add Property", "caption": "Register a new sale, rent, colony or plot inventory.", "url_name": "properties:create", "icon": "plus"})
    if user_role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}:
        role_actions.append({"label": "Employee Directory", "caption": "Track team ownership and role-wise property work.", "url_name": "accounts:team_profiles", "icon": "users"})
    if is_company_owner:
        role_actions.append({"label": "Approvals", "caption": "Review signup requests and access changes.", "url_name": "accounts:owner_requests", "icon": "check"})
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
            "active_count": active_count,
            "lead_total": lead_total,
            "total_value": total_value,
            "avg_price": avg_price,
            "total_plots": total_plots,
            "available_plots": available_plots,
            "conversion_count": conversion_count,
            "conversion_percent": conversion_percent,
            "status_chart": status_chart,
            "category_chart": category_chart,
            "listing_chart": listing_chart,
            "visit_chart": visit_chart,
            "upcoming_visits": upcoming_visits,
            "completed_visits": completed_visits,
            "followups_due": followups_due,
            "booked_visits": booked_visits,
            "role_actions": role_actions,
            "is_company_owner": is_company_owner,
            "can_manage_properties": can_manage_properties,
            "pending_signup_requests": pending_signup_requests,
            "support_requests": support_requests,
            "visible_events": visible_events,
            "dashboard_offer_popup": dashboard_offer_popup,
        },
    )
