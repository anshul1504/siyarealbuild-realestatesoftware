from django.contrib.auth.decorators import login_required
import csv

from django.db import models
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import AuthenticationSupportRequest, CompanyEvent, Role, SignupRequest, SignupRequestStatus, SoftwarePopup
from crm.models import Lead, LeadFollowUp, LeadStatus
from crm.selectors import visible_leads_for

from ..models import BookingAgreement, BookingInstallment, BookingPayment, ColonyPlot, MISReportSnapshot, PlotBooking, Property, PropertyCommissionPayout, PropertyDocument, PropertyVisit
from ..policies import can_create_property
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
    can_add_property = can_create_property(request.user)
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
    if not is_company_owner:
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

    plots = ColonyPlot.objects.filter(property__in=properties)
    plot_status_counts = {row["status"]: row["count"] for row in plots.values("status").annotate(count=Count("id"))}
    plot_total = plots.count()
    plot_chart = [
        {
            "label": _choice_label(ColonyPlot.Status.choices, status),
            "count": plot_status_counts.get(status, 0),
            "percent": _percent(plot_status_counts.get(status, 0), plot_total),
        }
        for status, _label in ColonyPlot.Status.choices
    ]

    bookings = PlotBooking.objects.filter(plot__property__in=properties)
    booking_totals = bookings.aggregate(
        total=Count("id"),
        deal_value=Sum("total_deal_value"),
        paid=Sum("paid_amount"),
        balance=Sum("balance_amount"),
    )
    booking_total = booking_totals["total"] or 0
    booking_status_counts = {row["status"]: row["count"] for row in bookings.values("status").annotate(count=Count("id"))}
    booking_chart = [
        {
            "label": _choice_label(PlotBooking.Status.choices, status),
            "count": booking_status_counts.get(status, 0),
            "percent": _percent(booking_status_counts.get(status, 0), booking_total),
        }
        for status, _label in PlotBooking.Status.choices
    ]
    today = timezone.localdate()
    overdue_installments = BookingInstallment.objects.filter(booking__in=bookings).exclude(
        status__in=[BookingInstallment.Status.PAID, BookingInstallment.Status.CANCELLED]
    ).filter(due_date__lt=today)
    agreements = BookingAgreement.objects.filter(booking__in=bookings)
    documents = PropertyDocument.objects.filter(property__in=properties)
    commissions = PropertyCommissionPayout.objects.filter(booking__in=bookings)
    if user_role != Role.COMPANY_OWNER:
        commissions = commissions.filter(role=user_role)
    commission_totals = commissions.aggregate(
        payable=Sum("amount"),
        paid=Sum("amount", filter=models.Q(status=PropertyCommissionPayout.Status.PAID)),
    )
    commission_booking_count = commissions.values("booking_id").distinct().count()
    commission_paid_count = commissions.filter(status=PropertyCommissionPayout.Status.PAID).count()
    commission_pending_count = commissions.exclude(status__in=[PropertyCommissionPayout.Status.PAID, PropertyCommissionPayout.Status.CANCELLED]).count()

    leads = visible_leads_for(request.user).filter(is_archived=False)
    lead_total = leads.count()
    lead_converted = leads.filter(status__in=[LeadStatus.BOOKED, LeadStatus.CLOSED]).count()
    unassigned_leads = leads.filter(assigned_to__isnull=True).count() if user_role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL} else 0
    lead_followups = LeadFollowUp.objects.filter(lead__in=leads, status=LeadFollowUp.Status.OPEN)
    overdue_lead_followups = lead_followups.filter(due_at__lt=timezone.now()).count()
    upcoming_lead_followups = lead_followups.filter(due_at__gte=timezone.now()).count()
    lead_status_counts = {row["status"]: row["count"] for row in leads.values("status").annotate(count=Count("id"))}
    lead_chart = [
        {
            "label": _choice_label(LeadStatus.choices, status),
            "count": lead_status_counts.get(status, 0),
            "percent": _percent(lead_status_counts.get(status, 0), lead_total),
        }
        for status, _label in LeadStatus.choices
        if lead_status_counts.get(status, 0)
    ]

    role_actions = [
        {"label": "Property Directory", "caption": "Search inventory, status, plots and client-share actions.", "url_name": "properties:list", "icon": "home"},
        {"label": "Plot Finder", "caption": "Find colony plots and open quotation, booking or visit workflows.", "url_name": "properties:plot_finder", "icon": "search"},
        {"label": "Lead Pipeline", "caption": "Manage enquiries, assignment, follow-ups and conversions.", "url_name": "crm:lead_list", "icon": "lead"},
        {"label": "Site Visits", "caption": "Track scheduled visits, outcomes and follow-up work.", "url_name": "properties:visit_index", "icon": "calendar"},
        {"label": "My Profile", "caption": "Keep contact, role and personal details updated.", "url_name": "accounts:profile", "icon": "user"},
    ]
    if can_add_property:
        role_actions.insert(1, {"label": "Add Property", "caption": "Register a new sale, rent, colony or plot inventory.", "url_name": "properties:create", "icon": "plus"})
    if user_role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}:
        role_actions.append({"label": "Employee Directory", "caption": "Track team ownership and role-wise property work.", "url_name": "accounts:team_profiles", "icon": "users"})
    if user_role in {Role.COMPANY_OWNER, Role.MANAGER}:
        role_actions.append({"label": "Owner MIS & Payouts", "caption": "Review sales, collections, documents and commission payouts.", "url_name": "properties:owner_mis_report", "icon": "report"})
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
            "visit_total": visit_total,
            "completed_visits": completed_visits,
            "followups_due": followups_due,
            "booked_visits": booked_visits,
            "plot_total": plot_total,
            "plot_chart": plot_chart,
            "booking_total": booking_total,
            "booking_deal_value": booking_totals["deal_value"] or 0,
            "booking_paid": booking_totals["paid"] or 0,
            "booking_balance": booking_totals["balance"] or 0,
            "booking_chart": booking_chart,
            "overdue_installment_count": overdue_installments.count(),
            "pending_agreement_count": agreements.exclude(status__in=[BookingAgreement.Status.SIGNED, BookingAgreement.Status.REGISTERED]).count(),
            "pending_document_count": documents.filter(review_status=PropertyDocument.ReviewStatus.PENDING).count(),
            "commission_payable": commission_totals["payable"] or 0,
            "commission_paid": commission_totals["paid"] or 0,
            "commission_unpaid": (commission_totals["payable"] or 0) - (commission_totals["paid"] or 0),
            "commission_booking_count": commission_booking_count,
            "commission_paid_count": commission_paid_count,
            "commission_pending_count": commission_pending_count,
            "lead_total": lead_total,
            "lead_converted": lead_converted,
            "lead_conversion_percent": _percent(lead_converted, lead_total),
            "unassigned_leads": unassigned_leads,
            "overdue_lead_followups": overdue_lead_followups,
            "upcoming_lead_followups": upcoming_lead_followups,
            "lead_chart": lead_chart,
            "role_actions": role_actions,
            "is_company_owner": is_company_owner,
            "can_manage_properties": can_manage_properties,
            "can_add_property": can_add_property,
            "pending_signup_requests": pending_signup_requests,
            "support_requests": support_requests,
            "visible_events": visible_events,
            "dashboard_offer_popup": dashboard_offer_popup,
        },
    )


def _date_range(request):
    today = timezone.localdate()
    start = request.GET.get("start") or today.replace(day=1).isoformat()
    end = request.GET.get("end") or today.isoformat()
    return start, end


def _owner_mis_context(request):
    properties = visible_properties_for(request)
    company = getattr(getattr(request.user, "profile", None), "company", None)
    start, end = _date_range(request)
    plots = ColonyPlot.objects.filter(property__in=properties)
    bookings = PlotBooking.objects.filter(plot__property__in=properties)
    period_bookings = bookings.filter(booking_date__gte=start, booking_date__lte=end)
    payments = BookingPayment.objects.filter(booking__in=bookings)
    period_payments = payments.filter(received_on__gte=start, received_on__lte=end)
    commission_payouts = PropertyCommissionPayout.objects.filter(booking__in=bookings)
    user_role = getattr(getattr(request.user, "profile", None), "role", "")
    if user_role != Role.COMPANY_OWNER:
        commission_payouts = commission_payouts.filter(role=user_role)
    installments = BookingInstallment.objects.filter(booking__in=bookings)
    today = timezone.localdate()
    agreements = BookingAgreement.objects.filter(booking__in=bookings)
    documents = PropertyDocument.objects.filter(property__in=properties)
    leads = Lead.objects.filter(company=company) if company else Lead.objects.none()
    lead_followups = LeadFollowUp.objects.filter(lead__in=leads)
    property_total = properties.count()
    booking_totals = bookings.aggregate(
        deal_value=Sum("total_deal_value"),
        paid=Sum("paid_amount"),
        balance=Sum("balance_amount"),
    )
    period_booking_totals = period_bookings.aggregate(total=Count("id"), deal_value=Sum("total_deal_value"))
    payment_totals = period_payments.aggregate(total=Sum("amount"), count=Count("id"))
    commission_totals = commission_payouts.aggregate(total=Sum("amount"), paid=Sum("amount", filter=models.Q(status=PropertyCommissionPayout.Status.PAID)))
    commission_status_counts = {row["status"]: row["count"] for row in commission_payouts.values("status").annotate(count=Count("id"))}
    overdue_installments = installments.exclude(status__in=[BookingInstallment.Status.PAID, BookingInstallment.Status.CANCELLED]).filter(due_date__lt=today)
    status_counts = {row["status"]: row["count"] for row in properties.values("status").annotate(count=Count("id"))}
    booking_status_counts = {row["status"]: row["count"] for row in bookings.values("status").annotate(count=Count("id"))}
    agreement_status_counts = {row["status"]: row["count"] for row in agreements.values("status").annotate(count=Count("id"))}
    document_status_counts = {row["review_status"]: row["count"] for row in documents.values("review_status").annotate(count=Count("id"))}
    context = {
        "start": start,
        "end": end,
        "property_total": property_total,
        "active_properties": properties.exclude(status__in=[Property.Status.SOLD, Property.Status.RENTED]).count(),
        "sold_or_rented": properties.filter(status__in=[Property.Status.SOLD, Property.Status.RENTED]).count(),
        "total_plots": plots.count(),
        "available_plots": plots.filter(status=ColonyPlot.Status.AVAILABLE).count(),
        "booked_plots": plots.filter(status=ColonyPlot.Status.BOOKED).count(),
        "sold_plots": plots.filter(status=ColonyPlot.Status.SOLD).count(),
        "period_booking_count": period_booking_totals["total"] or 0,
        "period_booking_value": period_booking_totals["deal_value"] or 0,
        "total_deal_value": booking_totals["deal_value"] or 0,
        "total_paid": booking_totals["paid"] or 0,
        "total_balance": booking_totals["balance"] or 0,
        "period_payment_total": payment_totals["total"] or 0,
        "period_payment_count": payment_totals["count"] or 0,
        "commission_payable": commission_totals["total"] or 0,
        "commission_paid": commission_totals["paid"] or 0,
        "commission_unpaid": (commission_totals["total"] or 0) - (commission_totals["paid"] or 0),
        "overdue_installments": overdue_installments.select_related("booking", "booking__plot")[:20],
        "overdue_installment_count": overdue_installments.count(),
        "pending_agreements": agreements.exclude(status__in=[BookingAgreement.Status.SIGNED, BookingAgreement.Status.REGISTERED]).count(),
        "registered_agreements": agreements.filter(status=BookingAgreement.Status.REGISTERED).count(),
        "pending_documents": documents.filter(review_status=PropertyDocument.ReviewStatus.PENDING).count(),
        "verified_documents": documents.filter(review_status=PropertyDocument.ReviewStatus.VERIFIED).count(),
        "lead_total": leads.count(),
        "lead_converted": leads.filter(status__in=[LeadStatus.BOOKED, LeadStatus.CLOSED]).count(),
        "lead_overdue_followups": lead_followups.filter(status=LeadFollowUp.Status.OPEN, due_at__lt=timezone.now()).count(),
        "property_status_rows": [{"label": _choice_label(Property.Status.choices, key), "count": status_counts.get(key, 0)} for key, _ in Property.Status.choices],
        "booking_status_rows": [{"label": _choice_label(PlotBooking.Status.choices, key), "count": booking_status_counts.get(key, 0)} for key, _ in PlotBooking.Status.choices],
        "agreement_status_rows": [{"label": _choice_label(BookingAgreement.Status.choices, key), "count": agreement_status_counts.get(key, 0)} for key, _ in BookingAgreement.Status.choices],
        "commission_status_rows": [{"label": _choice_label(PropertyCommissionPayout.Status.choices, key), "count": commission_status_counts.get(key, 0)} for key, _ in PropertyCommissionPayout.Status.choices],
        "document_status_rows": [{"label": _choice_label(PropertyDocument.ReviewStatus.choices, key), "count": document_status_counts.get(key, 0)} for key, _ in PropertyDocument.ReviewStatus.choices],
        "recent_snapshots": MISReportSnapshot.objects.filter(company=company, report_type=MISReportSnapshot.ReportType.OWNER)[:8] if company else [],
    }
    context["snapshot_data"] = {
        key: str(value)
        for key, value in context.items()
        if key
        in {
            "property_total",
            "active_properties",
            "sold_or_rented",
            "total_plots",
            "available_plots",
            "booked_plots",
            "sold_plots",
            "period_booking_count",
            "period_booking_value",
            "total_deal_value",
            "total_paid",
            "total_balance",
            "period_payment_total",
            "period_payment_count",
            "commission_payable",
            "commission_paid",
            "commission_unpaid",
            "overdue_installment_count",
            "pending_agreements",
            "registered_agreements",
            "pending_documents",
            "verified_documents",
            "lead_total",
            "lead_converted",
            "lead_overdue_followups",
        }
    }
    return context


@login_required
def owner_mis_report(request):
    user_profile = getattr(request.user, "profile", None)
    if getattr(user_profile, "role", "") not in {Role.COMPANY_OWNER, Role.MANAGER}:
        return render(request, "errors/error.html", {"status_code": 403, "message": "You do not have access to owner MIS reports."}, status=403)
    context = _owner_mis_context(request)
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="owner-mis-report.csv"'
        writer = csv.writer(response)
        writer.writerow(["Metric", "Value"])
        for key, value in context["snapshot_data"].items():
            writer.writerow([key.replace("_", " ").title(), value])
        return response
    if request.method == "POST":
        company = getattr(user_profile, "company", None)
        if company:
            MISReportSnapshot.objects.create(
                company=company,
                title=f"Owner MIS {context['start']} to {context['end']}",
                period_start=context["start"],
                period_end=context["end"],
                data=context["snapshot_data"],
                generated_by=request.user,
            )
        return redirect("properties:owner_mis_report")
    return render(request, "properties/owner_mis_report.html", context)
