from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.email_utils import send_property_share_email
from accounts.models import Role

from ..forms import ColonyPlotForm, ColonyPlotFormSet, PlotBookingForm, PlotQuotationForm, PropertyDeveloperForm, PropertyForm, PropertyShareEmailForm
from ..models import ColonyPlot, Property, PropertyVisit
from ..services import bulk_delete_properties, bulk_update_property_status, create_booking, create_plot, create_property, create_quotation, update_plot, update_property
from .helpers import can_manage_properties_for, property_share_message, save_property_uploads, visible_properties_for


@login_required
def property_list(request):
    properties = visible_properties_for(request).select_related("owner").prefetch_related("photos")
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
            "can_manage": can_manage_properties_for(request),
        },
    )


@login_required
def property_bulk_action(request):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to bulk update properties.")
        return redirect("properties:list")
    if request.method != "POST":
        return redirect("properties:list")
    property_ids = request.POST.getlist("property_ids")
    action = request.POST.get("bulk_action")
    selected = visible_properties_for(request).filter(id__in=property_ids)
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
        updated = bulk_update_property_status(queryset=selected, status=status_map[action], actor=request.user)
        messages.success(request, f"{updated} property record(s) updated.")
    elif action == "delete":
        deleted = bulk_delete_properties(queryset=selected, actor=request.user)
        messages.success(request, f"{deleted} property record(s) deleted.")
    else:
        messages.error(request, "Invalid bulk action.")
    return redirect("properties:list")


@login_required
def property_create(request):
    user_profile = getattr(request.user, "profile", None)
    if getattr(user_profile, "role", None) not in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}:
        messages.error(request, "You do not have access to add properties.")
        return redirect("properties:list")
    form = PropertyForm(request.POST or None, request.FILES or None, user=request.user)
    plot_formset = ColonyPlotFormSet(request.POST or None, prefix="plots")
    if request.method == "POST" and form.is_valid() and plot_formset.is_valid():
        prop = create_property(form=form, owner=request.user)
        save_property_uploads(prop, form, request)
        if prop.category == Property.Category.COLONY:
            plot_formset.instance = prop
            plot_formset.save()
            prop.available_plots = prop.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED]).count() or prop.available_plots
            prop.save(update_fields=["available_plots", "updated_at"])
        messages.success(request, "Property added successfully.")
        return redirect("properties:list")
    return render(request, "properties/property_form.html", {"form": form, "plot_formset": plot_formset, "mode": "create", "property_obj": None})


@login_required
def developer_create(request):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to add developers.")
        return redirect("properties:list")
    company = getattr(getattr(request.user, "profile", None), "company", None)
    if not company:
        messages.error(request, "Company profile is required before adding developers.")
        return redirect("properties:list")
    form = PropertyDeveloperForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        developer = form.save(commit=False)
        developer.company = company
        developer.save()
        messages.success(request, "Developer saved successfully.")
        return redirect("properties:create")
    return render(request, "properties/developer_form.html", {"form": form})


@login_required
def property_detail(request, property_id):
    property_obj = get_object_or_404(
        visible_properties_for(request)
        .select_related("owner", "owner__profile")
        .prefetch_related("photos", "documents", "plots", "visits", "visits__assigned_employee", "visits__plot"),
        id=property_id,
    )
    can_manage = can_manage_properties_for(request)
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
            "status_history": property_obj.status_history.select_related("changed_by")[:20],
            "visit_stats": visit_stats,
            "share_form": PropertyShareEmailForm(),
            "share_message": property_share_message(property_obj, request=request),
        },
    )


@login_required
def property_share_email(request, property_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    form = PropertyShareEmailForm(request.POST)
    if not form.is_valid():
        for error in form.errors.get("emails", []):
            messages.error(request, error)
        return redirect("properties:detail", property_id=property_obj.id)

    sender_name = request.user.get_full_name() or request.user.email or "Siya Real Build"
    property_url = request.build_absolute_uri(reverse("properties:detail", args=[property_obj.id]))
    summary = property_share_message(property_obj, request=request)
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
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to edit properties.")
        return redirect("properties:list")
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    form = PropertyForm(request.POST or None, request.FILES or None, instance=property_obj, user=request.user)
    plot_formset = ColonyPlotFormSet(request.POST or None, instance=property_obj, prefix="plots")
    if request.method == "POST" and form.is_valid() and plot_formset.is_valid():
        prop = update_property(form=form, property_obj=property_obj, actor=request.user)
        save_property_uploads(prop, form, request)
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
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    visits = plot.visits.select_related("assigned_employee", "scheduled_by")[:25]
    return render(
        request,
        "properties/plot_detail.html",
        {
            "property_obj": property_obj,
            "plot": plot,
            "visits": visits,
            "quotations": plot.quotations.select_related("created_by")[:10],
            "bookings": plot.bookings.select_related("created_by", "quotation")[:10],
            "can_manage": can_manage_properties_for(request),
        },
    )


@login_required
def colony_plot_create(request, property_id):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to add colony plots.")
        return redirect("properties:detail", property_id=property_id)
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    form = ColonyPlotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plot = create_plot(form=form, property_obj=property_obj, actor=request.user)
        messages.success(request, "Plot saved successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_form.html", {"form": form, "property_obj": property_obj, "mode": "create"})


@login_required
def colony_plot_edit(request, property_id, plot_id):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to edit colony plots.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    form = ColonyPlotForm(request.POST or None, instance=plot)
    if request.method == "POST" and form.is_valid():
        plot = update_plot(form=form, plot=plot, actor=request.user)
        messages.success(request, "Plot updated successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_form.html", {"form": form, "property_obj": property_obj, "plot": plot, "mode": "edit"})


@login_required
def plot_quotation_create(request, property_id, plot_id):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to create plot quotations.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    initial = {
        "base_amount": plot.area_sqft * plot.base_rate,
        "plc_amount": plot.area_sqft * plot.plc_rate,
        "charges_amount": plot.extra_charges,
    }
    form = PlotQuotationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        quotation = create_quotation(form=form, plot=plot, actor=request.user)
        messages.success(request, "Quotation saved successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_quotation_form.html", {"form": form, "property_obj": property_obj, "plot": plot})


@login_required
def plot_booking_create(request, property_id, plot_id):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to book plots.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    form = PlotBookingForm(request.POST or None, plot=plot, initial={"agreed_rate": plot.base_rate, "plc_amount": plot.area_sqft * plot.plc_rate, "charges_amount": plot.extra_charges})
    if request.method == "POST" and form.is_valid():
        create_booking(form=form, plot=plot, actor=request.user)
        messages.success(request, "Plot booking saved successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_booking_form.html", {"form": form, "property_obj": property_obj, "plot": plot})
