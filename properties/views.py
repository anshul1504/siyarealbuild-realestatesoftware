from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.utils import timezone

from accounts.email_utils import send_property_share_email
from accounts.models import AuthenticationSupportRequest, CompanyEvent, Role, SignupRequest, SignupRequestStatus, SoftwarePopup
from .forms import ColonyPlotFormSet, PropertyForm, PropertyShareEmailForm, PropertyVisitForm
from .models import ColonyPlot, Property, PropertyDocument, PropertyPhoto, PropertyVisit


@login_required
def dashboard(request):
    properties = _visible_properties(request)
    stats = properties.aggregate(total_value=Sum("price"), total_properties=Count("id"))
    recent = properties[:5]
    user_profile = getattr(request.user, "profile", None)
    company = getattr(user_profile, "company", None)
    user_role = getattr(user_profile, "role", "")
    is_company_owner = bool(getattr(user_profile, "role", None) == Role.COMPANY_OWNER)
    can_manage_properties = bool(getattr(user_profile, "role", None) in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL})
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
        dashboard_offer_popup = (
            SoftwarePopup.objects.filter(company=company, is_active=True)
            .exclude(offer_image="")
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .order_by("-created_at")
        )
        dashboard_offer_popup = next((popup for popup in dashboard_offer_popup if user_role in (popup.roles or [])), None)
    return render(
        request,
        "properties/dashboard.html",
        {
            "properties": recent,
            "stats": stats,
            "active_count": properties.exclude(status__in=["sold", "rented"]).count(),
            "lead_total": sum(p.lead_count for p in properties),
            "is_company_owner": is_company_owner,
            "can_manage_properties": can_manage_properties,
            "pending_signup_requests": pending_signup_requests,
            "support_requests": support_requests,
            "visible_events": visible_events,
            "dashboard_offer_popup": dashboard_offer_popup,
        },
    )


@login_required
def property_list(request):
    properties = _visible_properties(request).select_related("owner").prefetch_related("photos")
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    listing_for = request.GET.get("listing_for", "").strip()
    if query:
        properties = properties.filter(
            models.Q(title__icontains=query)
            | models.Q(city__icontains=query)
            | models.Q(locality__icontains=query)
            | models.Q(address__icontains=query)
            | models.Q(rera_number__icontains=query)
            | models.Q(tcp_approval_number__icontains=query)
        )
    if category:
        properties = properties.filter(category=category)
    if status:
        properties = properties.filter(status=status)
    if listing_for:
        properties = properties.filter(listing_for=listing_for)
    paginator = Paginator(properties, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "properties/property_list.html",
        {
            "properties": page_obj.object_list,
            "page_obj": page_obj,
            "category_choices": Property.Category.choices,
            "status_choices": Property.Status.choices,
            "listing_choices": Property.ListingFor.choices,
            "selected_category": category,
            "selected_status": status,
            "selected_listing_for": listing_for,
            "query": query,
            "query_string": query_params.urlencode(),
            "can_manage": _can_manage_properties(request),
        },
    )


@login_required
def property_bulk_action(request):
    if not _can_manage_properties(request):
        messages.error(request, "You do not have access to bulk update properties.")
        return redirect("properties:list")
    if request.method != "POST":
        return redirect("properties:list")
    property_ids = request.POST.getlist("property_ids")
    action = request.POST.get("bulk_action")
    selected = _visible_properties(request).filter(id__in=property_ids)
    count = selected.count()
    if not property_ids or not action:
        messages.error(request, "Select properties and choose an action.")
        return redirect("properties:list")
    status_map = {
        "available": Property.Status.AVAILABLE,
        "hold": Property.Status.HOLD,
        "negotiation": Property.Status.NEGOTIATION,
        "sold": Property.Status.SOLD,
        "rented": Property.Status.RENTED,
    }
    if action in status_map:
        selected.update(status=status_map[action], updated_at=timezone.now())
        messages.success(request, f"{count} property record(s) updated.")
    elif action == "delete":
        selected.delete()
        messages.success(request, f"{count} property record(s) deleted.")
    else:
        messages.error(request, "Invalid bulk action.")
    return redirect("properties:list")


@login_required
def property_create(request):
    user_profile = getattr(request.user, "profile", None)
    if getattr(user_profile, "role", None) not in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}:
        messages.error(request, "You do not have access to add properties.")
        return redirect("properties:list")
    form = PropertyForm(request.POST or None, request.FILES or None)
    plot_formset = ColonyPlotFormSet(request.POST or None, prefix="plots")
    if request.method == "POST" and form.is_valid() and plot_formset.is_valid():
        prop = form.save(commit=False)
        prop.owner = request.user
        prop.save()
        _save_property_uploads(prop, form, request)
        if prop.category == Property.Category.COLONY:
            plot_formset.instance = prop
            plot_formset.save()
            prop.available_plots = prop.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED]).count() or prop.available_plots
            prop.save(update_fields=["available_plots", "updated_at"])
        messages.success(request, "Property added successfully.")
        return redirect("properties:list")
    return render(request, "properties/property_form.html", {"form": form, "plot_formset": plot_formset, "mode": "create", "property_obj": None})


@login_required
def property_detail(request, property_id):
    property_obj = get_object_or_404(
        _visible_properties(request)
        .select_related("owner", "owner__profile")
        .prefetch_related("photos", "documents", "plots", "visits", "visits__assigned_employee", "visits__plot"),
        id=property_id,
    )
    can_manage = _can_manage_properties(request)
    visits = property_obj.visits.select_related("assigned_employee", "plot")[:10]
    visit_stats = property_obj.visits.aggregate(
        total=Count("id"),
        completed=Count("id", filter=models.Q(status=PropertyVisit.Status.COMPLETED)),
        scheduled=Count("id", filter=models.Q(status=PropertyVisit.Status.SCHEDULED)),
    )
    return render(
        request,
        "properties/property_detail.html",
        {
            "property_obj": property_obj,
            "can_manage": can_manage,
            "photos": property_obj.photos.all(),
            "documents": property_obj.documents.all(),
            "plots": property_obj.plots.all(),
            "visits": visits,
            "visit_stats": visit_stats,
            "share_form": PropertyShareEmailForm(),
            "share_message": _property_share_message(property_obj, request=request),
        },
    )


@login_required
def property_share_email(request, property_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    property_obj = get_object_or_404(_visible_properties(request).prefetch_related("plots"), id=property_id)
    form = PropertyShareEmailForm(request.POST)
    if not form.is_valid():
        for error in form.errors.get("emails", []):
            messages.error(request, error)
        return redirect("properties:detail", property_id=property_obj.id)

    sender_name = request.user.get_full_name() or request.user.email or "Siya Real Build"
    property_url = request.build_absolute_uri(reverse("properties:detail", args=[property_obj.id]))
    summary = _property_share_message(property_obj, request=request)
    custom_message = form.cleaned_data.get("message", "").strip()
    if custom_message:
        summary = f"{custom_message}\n\n{summary}"
    sent_count = 0
    for email in form.cleaned_data["emails"]:
        send_property_share_email(
            to_email=email,
            property_title=property_obj.title,
            property_summary=summary,
            sender_name=sender_name,
            property_url=property_url,
        )
        sent_count += 1
    messages.success(request, f"Property details sent to {sent_count} client email address(es).")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_edit(request, property_id):
    if not _can_manage_properties(request):
        messages.error(request, "You do not have access to edit properties.")
        return redirect("properties:list")
    property_obj = get_object_or_404(_visible_properties(request), id=property_id)
    form = PropertyForm(request.POST or None, request.FILES or None, instance=property_obj)
    plot_formset = ColonyPlotFormSet(request.POST or None, instance=property_obj, prefix="plots")
    if request.method == "POST" and form.is_valid() and plot_formset.is_valid():
        prop = form.save(commit=False)
        prop.owner = property_obj.owner
        prop.save()
        _save_property_uploads(prop, form, request)
        if prop.category == Property.Category.COLONY:
            plot_formset.instance = prop
            plot_formset.save()
            prop.available_plots = prop.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED]).count() or prop.available_plots
            prop.save(update_fields=["available_plots", "updated_at"])
        messages.success(request, "Property updated successfully.")
        return redirect("properties:detail", property_id=prop.id)
    return render(
        request,
        "properties/property_form.html",
        {
            "form": form,
            "plot_formset": plot_formset,
            "mode": "edit",
            "property_obj": property_obj,
        },
    )


@login_required
def colony_plot_detail(request, property_id, plot_id):
    property_obj = get_object_or_404(_visible_properties(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    visits = plot.visits.select_related("assigned_employee", "scheduled_by")[:25]
    return render(
        request,
        "properties/plot_detail.html",
        {
            "property_obj": property_obj,
            "plot": plot,
            "visits": visits,
            "can_manage": _can_manage_properties(request),
        },
    )


@login_required
def property_visit_list(request, property_id):
    property_obj = get_object_or_404(_visible_properties(request), id=property_id)
    visits = property_obj.visits.select_related("assigned_employee", "scheduled_by", "plot")
    return render(
        request,
        "properties/visit_list.html",
        {
            "property_obj": property_obj,
            "visits": visits,
            "can_manage": _can_manage_properties(request),
        },
    )


@login_required
def property_visit_create(request, property_id, plot_id=None):
    if not _can_manage_properties(request):
        messages.error(request, "You do not have access to schedule property visits.")
        return redirect("properties:detail", property_id=property_id)
    property_obj = get_object_or_404(_visible_properties(request), id=property_id)
    initial = {}
    if plot_id:
        initial["plot"] = get_object_or_404(property_obj.plots, id=plot_id)
    form = PropertyVisitForm(request.POST or None, property_obj=property_obj, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        visit = form.save(commit=False)
        visit.property = property_obj
        visit.scheduled_by = request.user
        visit.save()
        messages.success(request, "Property visit scheduled successfully.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    return render(
        request,
        "properties/visit_form.html",
        {
            "form": form,
            "property_obj": property_obj,
            "mode": "create",
        },
    )


@login_required
def property_visit_detail(request, visit_id):
    visit = get_object_or_404(
        PropertyVisit.objects.select_related("property", "plot", "assigned_employee", "scheduled_by"),
        id=visit_id,
        property__in=_visible_properties(request),
    )
    return render(
        request,
        "properties/visit_detail.html",
        {
            "visit": visit,
            "property_obj": visit.property,
            "can_manage": _can_manage_properties(request),
        },
    )


@login_required
def property_visit_edit(request, visit_id):
    visit = get_object_or_404(PropertyVisit.objects.select_related("property"), id=visit_id, property__in=_visible_properties(request))
    if not _can_manage_properties(request):
        messages.error(request, "You do not have access to edit property visits.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    form = PropertyVisitForm(request.POST or None, instance=visit, property_obj=visit.property, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Property visit updated successfully.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    return render(
        request,
        "properties/visit_form.html",
        {
            "form": form,
            "property_obj": visit.property,
            "visit": visit,
            "mode": "edit",
        },
    )


@login_required
def property_visit_delete(request, visit_id):
    visit = get_object_or_404(PropertyVisit, id=visit_id, property__in=_visible_properties(request))
    property_id = visit.property_id
    if not _can_manage_properties(request):
        messages.error(request, "You do not have access to delete property visits.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    if request.method == "POST":
        visit.delete()
        messages.success(request, "Property visit deleted successfully.")
        return redirect("properties:visits", property_id=property_id)
    return redirect("properties:visit_detail", visit_id=visit.id)


def _visible_properties(request):
    user_profile = getattr(request.user, "profile", None)
    company = getattr(user_profile, "company", None)
    role = getattr(user_profile, "role", "")
    if role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL} and company:
        return Property.objects.filter(owner__profile__company=company)
    return Property.objects.filter(owner=request.user)


def _can_manage_properties(request):
    user_profile = getattr(request.user, "profile", None)
    return getattr(user_profile, "role", None) in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}


def _save_property_uploads(prop, form, request):
    for index, image in enumerate(request.FILES.getlist("photos")):
        PropertyPhoto.objects.create(property=prop, image=image, is_primary=index == 0)
    document_type = form.cleaned_data.get("document_type") or PropertyDocument.DocumentType.OTHER
    for document in request.FILES.getlist("documents"):
        PropertyDocument.objects.create(
            property=prop,
            document_type=document_type,
            title=getattr(document, "name", ""),
            file=document,
        )


def _property_share_message(property_obj, request=None):
    lines = [
        f"{property_obj.title}",
        f"Category: {property_obj.get_category_display()}",
        f"For: {property_obj.get_listing_for_display()}",
        f"Status: {property_obj.get_status_display()}",
        f"Location: {property_obj.city}{', ' + property_obj.locality if property_obj.locality else ''}",
        f"Address: {property_obj.address}",
        f"Price: Rs. {property_obj.price}",
        f"Area: {property_obj.area_sqft} sqft",
    ]
    if property_obj.category == Property.Category.COLONY:
        lines.extend(
            [
                f"Total plots: {property_obj.total_plots}",
                f"Available plots: {property_obj.available_plots}",
                f"Amenities: {property_obj.amenities or '-'}",
                f"Garden count: {property_obj.garden_count}",
                f"Corner plots: {property_obj.corner_plot_count}",
                f"Garden-facing plots: {property_obj.garden_facing_plot_count}",
                f"PLC rules: {property_obj.plc_rules or '-'}",
            ]
        )
    if property_obj.rera_number:
        lines.append(f"RERA: {property_obj.rera_number}")
    if property_obj.tcp_approval_number:
        lines.append(f"T&CP: {property_obj.tcp_approval_number}")
    if property_obj.nearby_connectivity:
        lines.append(f"Connectivity: {property_obj.nearby_connectivity}")
    if property_obj.nearby_commercial:
        lines.append(f"Nearby commercial: {property_obj.nearby_commercial}")
    if property_obj.nearby_residential:
        lines.append(f"Nearby residential: {property_obj.nearby_residential}")
    if property_obj.map_link:
        lines.append(f"Map: {property_obj.map_link}")
    if request:
        lines.append(f"Detail link: {request.build_absolute_uri(reverse('properties:detail', args=[property_obj.id]))}")
    if property_obj.contact_name or property_obj.contact_phone:
        lines.append(f"Contact: {property_obj.contact_name or '-'} {property_obj.contact_phone or ''}".strip())
    return "\n".join(lines)

# Create your views here.
