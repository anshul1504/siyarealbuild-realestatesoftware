import csv
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Prefetch
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.email_utils import send_property_document_email, send_property_share_email
from accounts.models import Role
from accounts.services import record_audit

from ..forms import DEFAULT_AMENITIES, BookingAgreementForm, BookingInstallmentForm, BookingPaymentForm, ColonyPlotForm, ColonyPlotFormSet, PlotBookingForm, PlotQuotationForm, PropertyCommissionRuleFormSet, PropertyDeveloperForm, PropertyDocumentReviewForm, PropertyDocumentUploadForm, PropertyForm, PropertyShareEmailForm
from ..models import BookingAgreement, BookingPayment, ColonyPlot, PlotBooking, PlotQuotation, Property, PropertyCommissionPayout, PropertyDocument, PropertyPhoto, PropertyVisit
from ..pdf_utils import booking_pdf_bytes, plot_pdf_bytes, property_pdf_bytes, quotation_pdf_bytes
from ..policies import can_manage_commission_payouts
from ..services import (
    archive_property,
    apply_colony_pricing,
    approve_booking_request,
    bulk_archive_properties,
    bulk_update_property_status,
    create_booking,
    create_booking_agreement,
    create_booking_installment,
    create_plot,
    create_property,
    create_quotation,
    receive_booking_payment,
    resync_property_commissions,
    review_property_document,
    restore_property,
    update_booking_agreement,
    update_booking_request,
    update_commission_payout,
    update_plot,
    update_property,
    update_quotation,
)
from ..validators import validate_property_image
from .helpers import (
    can_archive_property_for,
    can_create_property_for,
    can_delete_property_for,
    can_export_properties_for,
    can_manage_properties_for,
    can_restore_property_for,
    can_share_property_for,
    can_update_property_for,
    property_share_message,
    save_property_uploads,
    visible_properties_for,
)


def _filtered_properties(request, queryset):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    listing_for = request.GET.get("listing_for", "").strip()
    if query:
        queryset = queryset.filter(
            models.Q(title__icontains=query)
            | models.Q(city__icontains=query)
            | models.Q(locality__icontains=query)
            | models.Q(address__icontains=query)
            | models.Q(rera_number__icontains=query)
            | models.Q(tcp_approval_number__icontains=query)
        )
    if category:
        queryset = queryset.filter(category=category)
    if status:
        queryset = queryset.filter(status=status)
    if listing_for:
        queryset = queryset.filter(listing_for=listing_for)
    return queryset, query, category, status, listing_for


def _plot_finder_queryset(request):
    colony_query = request.GET.get("colony", request.GET.get("q", "")).strip()
    plot_number = request.GET.get("plot_number", "").strip()
    status = request.GET.get("status", "").strip()
    plots = ColonyPlot.objects.filter(property__in=visible_properties_for(request)).select_related("property")
    if colony_query:
        plots = plots.filter(
            models.Q(property__title__icontains=colony_query)
            | models.Q(property__colony_name__icontains=colony_query)
            | models.Q(property__development_name__icontains=colony_query)
            | models.Q(property__city__icontains=colony_query)
            | models.Q(property__locality__icontains=colony_query)
        )
    if plot_number:
        plots = plots.filter(plot_number__icontains=plot_number)
    if status:
        plots = plots.filter(status=status)
    return plots, colony_query, plot_number, status


@login_required
def property_list(request):
    include_archived = request.GET.get("archived") == "1" and can_restore_property_for(request)
    if include_archived:
        properties = visible_properties_for(request, include_archived=True).filter(is_archived=True)
    else:
        properties = visible_properties_for(request)
    properties = properties.select_related("owner").prefetch_related("photos")
    properties, query, category, status, listing_for = _filtered_properties(request, properties)
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
            "can_export": can_export_properties_for(request),
            "can_restore": can_restore_property_for(request),
            "can_delete": can_delete_property_for(request),
            "showing_archived": include_archived,
        },
    )


@login_required
def plot_finder(request):
    plots, colony_query, plot_number, status = _plot_finder_queryset(request)
    workflow = request.GET.get("workflow", "").strip()
    workflow_labels = {
        "quotation_booking": "Quotation & Booking",
        "commission": "Commission Management",
        "visit": "Site Visit Management",
    }
    plots = plots.prefetch_related("quotations", "bookings", "bookings__commission_payouts", "visits")
    paginator = Paginator(plots.order_by("property__title", "plot_number"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "properties/plot_finder.html",
        {
            "plots": page_obj.object_list,
            "page_obj": page_obj,
            "query_string": query_params.urlencode(),
            "colony_query": colony_query,
            "plot_number": plot_number,
            "selected_status": status,
            "workflow": workflow,
            "workflow_label": workflow_labels.get(workflow, "Plot Finder"),
            "status_choices": ColonyPlot.Status.choices,
            "can_manage": can_manage_properties_for(request),
            "can_manage_commissions": can_export_properties_for(request),
        },
    )


@login_required
def quotation_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    quotations = PlotQuotation.objects.filter(plot__property__in=visible_properties_for(request)).select_related("plot", "plot__property", "created_by")
    if query:
        quotations = quotations.filter(models.Q(client_name__icontains=query) | models.Q(client_phone__icontains=query) | models.Q(plot__plot_number__icontains=query) | models.Q(plot__property__title__icontains=query))
    if status:
        quotations = quotations.filter(status=status)
    page_obj = Paginator(quotations, 25).get_page(request.GET.get("page"))
    return render(request, "properties/quotation_list.html", {"quotations": page_obj.object_list, "page_obj": page_obj, "query": query, "selected_status": status, "status_choices": PlotQuotation.Status.choices})


@login_required
def booking_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    bookings = PlotBooking.objects.filter(plot__property__in=visible_properties_for(request)).select_related("plot", "plot__property", "created_by", "approved_by")
    if query:
        bookings = bookings.filter(models.Q(client_name__icontains=query) | models.Q(client_phone__icontains=query) | models.Q(government_id_number__icontains=query) | models.Q(plot__plot_number__icontains=query) | models.Q(plot__property__title__icontains=query))
    if status:
        bookings = bookings.filter(status=status)
    page_obj = Paginator(bookings, 25).get_page(request.GET.get("page"))
    return render(request, "properties/booking_list.html", {"bookings": page_obj.object_list, "page_obj": page_obj, "query": query, "selected_status": status, "status_choices": PlotBooking.Status.choices})


@login_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(
        PlotBooking.objects.filter(plot__property__in=visible_properties_for(request))
        .select_related("plot", "plot__property", "created_by", "approved_by", "quotation")
        .prefetch_related("installments", "payments", "agreements", "commission_payouts"),
        id=booking_id,
    )
    user_role = getattr(getattr(request.user, "profile", None), "role", "")
    payouts = booking.commission_payouts.all()
    if user_role != Role.COMPANY_OWNER:
        payouts = payouts.filter(role=user_role)
    return render(request, "properties/booking_detail.html", {"booking": booking, "property_obj": booking.plot.property, "plot": booking.plot, "commission_payouts": payouts, "can_edit": user_role == Role.COMPANY_OWNER})


@login_required
def commission_rules(request):
    if not can_export_properties_for(request):
        messages.error(request, "You do not have access to manage commission rules.")
        return redirect("properties:list")
    property_id = request.GET.get("property") or request.POST.get("property")
    properties = visible_properties_for(request).filter(category=Property.Category.COLONY).order_by("title")
    property_obj = properties.filter(id=property_id).first() if property_id else properties.first()
    formset = PropertyCommissionRuleFormSet(request.POST or None, instance=property_obj, prefix="commissions") if property_obj else None
    if request.method == "POST":
        if not property_obj:
            messages.error(request, "Select a colony before saving commission rules.")
            return redirect("properties:commission_rules")
        if formset and formset.is_valid():
            formset.save()
            synced_count = resync_property_commissions(property_obj, actor=request.user)
            messages.success(request, f"Role-wise commission rules updated and synced with {synced_count} existing booking(s).")
            return redirect(f"{reverse('properties:commission_rules')}?property={property_obj.id}")
    return render(
        request,
        "properties/commission_rules.html",
        {
            "properties": properties,
            "property_obj": property_obj,
            "commission_formset": formset,
            "selected_property_id": str(property_obj.id) if property_obj else "",
        },
    )


@login_required
def property_export(request):
    if not can_export_properties_for(request):
        messages.error(request, "You do not have access to export properties.")
        return redirect("properties:list")
    properties, *_ = _filtered_properties(request, visible_properties_for(request).select_related("owner", "assigned_to", "developer"))
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="properties.csv"'
    writer = csv.writer(response)
    writer.writerow(["Title", "Category", "For", "Status", "City", "Locality", "Address", "Area", "Price", "Owner", "Assigned To", "RERA", "TCP", "Created"])
    for prop in properties:
        writer.writerow(
            [
                prop.title,
                prop.get_category_display(),
                prop.get_listing_for_display(),
                prop.get_status_display(),
                prop.city,
                prop.locality,
                prop.address,
                prop.area_sqft,
                prop.price,
                prop.owner.get_full_name() or prop.owner.email,
                prop.assigned_to.get_full_name() or prop.assigned_to.email if prop.assigned_to else "",
                prop.rera_number,
                prop.tcp_approval_number,
                prop.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    return response


@login_required
def property_pdf(request, property_id):
    property_obj = get_object_or_404(
        visible_properties_for(request).select_related("owner__profile__company", "developer").prefetch_related("photos", "documents", "plots"),
        id=property_id,
    )
    response = HttpResponse(property_pdf_bytes(property_obj), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="property-{property_obj.id}.pdf"'
    return response


@login_required
def property_bulk_action(request):
    if not can_archive_property_for(request):
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
    elif action == "archive":
        archived = bulk_archive_properties(queryset=selected, actor=request.user)
        messages.success(request, f"{archived} property record(s) archived.")
    else:
        messages.error(request, "Invalid bulk action.")
    return redirect("properties:list")


@login_required
def property_create(request):
    if not can_create_property_for(request):
        messages.error(request, "You do not have access to add properties.")
        return redirect("properties:list")
    form = PropertyForm(request.POST or None, request.FILES or None, user=request.user)
    plot_formset = ColonyPlotFormSet(request.POST or None, prefix="plots")
    commission_formset = PropertyCommissionRuleFormSet(request.POST or None, prefix="commissions")
    forms_valid = form.is_valid() and plot_formset.is_valid() and commission_formset.is_valid()
    if forms_valid and form.cleaned_data.get("category") == Property.Category.COLONY:
        total_plots = form.cleaned_data.get("total_plots") or 0
        submitted_plots = [
            item
            for item in plot_formset.cleaned_data
            if item and not item.get("DELETE") and item.get("plot_number")
        ]
        if len(submitted_plots) != total_plots:
            form.add_error("total_plots", "Total plots and filled plot inventory rows must match.")
            forms_valid = False
    if request.method == "POST" and forms_valid:
        prop = create_property(form=form, owner=request.user)
        save_property_uploads(prop, form, request)
        commission_formset.instance = prop
        commission_formset.save()
        if prop.category == Property.Category.COLONY:
            plot_formset.instance = prop
            plots = plot_formset.save()
            for plot in plots:
                apply_colony_pricing(plot)
                plot.save(update_fields=["base_rate", "plc_rate", "extra_charges", "price"])
            prop.available_plots = prop.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED, ColonyPlot.Status.BOOKED]).count() or prop.available_plots
            prop.save(update_fields=["available_plots", "updated_at"])
        messages.success(request, "Property added successfully.")
        return redirect("properties:list")
    if request.method == "POST" and not forms_valid:
        messages.error(request, "Property was not saved. Please correct the highlighted fields and try again.")
    return render(
        request,
        "properties/property_form.html",
        {"form": form, "plot_formset": plot_formset, "commission_formset": commission_formset, "mode": "create", "property_obj": None},
    )


@login_required
def developer_create(request):
    if not can_create_property_for(request):
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
        .prefetch_related("photos", "documents", "plots", "commission_rules", "visits", "visits__assigned_employee", "visits__plot"),
        id=property_id,
    )
    user_role = getattr(getattr(request.user, "profile", None), "role", "")
    visible_commission_rules = property_obj.commission_rules.filter(is_active=True)
    if user_role != Role.COMPANY_OWNER:
        visible_commission_rules = visible_commission_rules.filter(role=user_role)
    can_manage = can_update_property_for(request, property_obj)
    plot_page_obj = Paginator(property_obj.plots.all(), 10).get_page(request.GET.get("plot_page"))
    visit_page_obj = Paginator(
        property_obj.visits.select_related("assigned_employee", "plot"),
        10,
    ).get_page(request.GET.get("visit_page"))
    visit_stats = property_obj.visits.aggregate(
        total=Count("id"),
        completed=Count("id", filter=models.Q(status=PropertyVisit.Status.COMPLETED)),
        scheduled=Count("id", filter=models.Q(status=PropertyVisit.Status.SCHEDULED)),
    )
    photos = list(property_obj.photos.all())
    documents = list(property_obj.documents.all())
    share_photos = [
        {"photo": photo, "url": request.build_absolute_uri(photo.image.url)}
        for photo in photos
    ]
    share_documents = [
        {
            "document": document,
            "url": request.build_absolute_uri(
                reverse("properties:document_download", args=[property_obj.id, document.id])
            ),
        }
        for document in documents
    ]
    map_documents = [
        {
            "document": document,
            "is_image": Path(document.file.name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"},
        }
        for document in documents
        if document.document_type == PropertyDocument.DocumentType.MAP
    ]
    legal_documents = [document for document in documents if document.document_type != PropertyDocument.DocumentType.MAP]
    amenity_names = dict(DEFAULT_AMENITIES)
    return render(
        request,
        "properties/property_detail.html",
        {
            "property_obj": property_obj,
            "can_manage": can_manage,
            "can_archive": can_archive_property_for(request, property_obj),
            "can_delete": can_delete_property_for(request, property_obj),
            "can_share": can_share_property_for(request, property_obj),
            "photos": photos,
            "share_photos": share_photos,
            "share_documents": share_documents,
            "cover_photo": photos[0] if photos else None,
            "selected_amenity_labels": [amenity_names.get(value, value.replace("_", " ").title()) for value in property_obj.selected_amenities],
            "documents": documents,
            "map_documents": map_documents,
            "legal_documents": legal_documents,
            "document_review_status_choices": PropertyDocument.ReviewStatus.choices,
            "document_upload_form": PropertyDocumentUploadForm(),
            "plots": plot_page_obj.object_list,
            "plot_page_obj": plot_page_obj,
            "visits": visit_page_obj.object_list,
            "visit_page_obj": visit_page_obj,
            "status_history": property_obj.status_history.select_related("changed_by")[:20],
            "visit_stats": visit_stats,
            "share_form": PropertyShareEmailForm(),
            "share_message": property_share_message(property_obj, request=request),
            "visible_commission_rules": visible_commission_rules,
        },
    )


@login_required
def property_share_email(request, property_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_share_property_for(request, property_obj):
        messages.error(request, "You do not have access to share property details.")
        return redirect("properties:detail", property_id=property_obj.id)
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
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to edit properties.")
        return redirect("properties:list")
    form = PropertyForm(request.POST or None, request.FILES or None, instance=property_obj, user=request.user)
    plot_formset = ColonyPlotFormSet(request.POST or None, instance=property_obj, prefix="plots")
    commission_formset = PropertyCommissionRuleFormSet(request.POST or None, instance=property_obj, prefix="commissions")
    forms_valid = form.is_valid() and plot_formset.is_valid() and commission_formset.is_valid()
    if forms_valid and form.cleaned_data.get("category") == Property.Category.COLONY:
        total_plots = form.cleaned_data.get("total_plots") or 0
        submitted_plots = [
            item
            for item in plot_formset.cleaned_data
            if item and not item.get("DELETE") and item.get("plot_number")
        ]
        if len(submitted_plots) != total_plots:
            form.add_error("total_plots", "Total plots and filled plot inventory rows must match.")
            forms_valid = False
    if request.method == "POST" and forms_valid:
        prop = update_property(form=form, property_obj=property_obj, actor=request.user)
        save_property_uploads(prop, form, request)
        commission_formset.instance = prop
        commission_formset.save()
        resync_property_commissions(prop, actor=request.user)
        if prop.category == Property.Category.COLONY:
            plot_formset.instance = prop
            plots = plot_formset.save()
            for plot in plots:
                apply_colony_pricing(plot)
                plot.save(update_fields=["base_rate", "plc_rate", "extra_charges", "price"])
            prop.available_plots = prop.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED, ColonyPlot.Status.BOOKED]).count() or prop.available_plots
            prop.save(update_fields=["available_plots", "updated_at"])
        messages.success(request, "Property updated successfully.")
        return redirect("properties:detail", property_id=prop.id)
    if request.method == "POST" and not forms_valid:
        messages.error(request, "Property was not updated. Please correct the highlighted fields and try again.")
    return render(
        request,
        "properties/property_form.html",
        {
            "form": form,
            "plot_formset": plot_formset,
            "commission_formset": commission_formset,
            "mode": "edit",
            "property_obj": property_obj,
        },
    )


@login_required
def property_archive(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_archive_property_for(request, property_obj):
        messages.error(request, "You do not have access to archive properties.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    archive_property(property_obj=property_obj, actor=request.user, note=request.POST.get("archive_note", "").strip())
    messages.success(request, "Property archived successfully.")
    return redirect("properties:list")


@login_required
def property_restore(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request, include_archived=True), id=property_id, is_archived=True)
    if not can_restore_property_for(request, property_obj):
        messages.error(request, "Only company owners can restore archived properties.")
        return redirect("properties:list")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    restore_property(property_obj=property_obj, actor=request.user)
    messages.success(request, "Property restored successfully.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_delete(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request, include_archived=True), id=property_id)
    if not can_delete_property_for(request, property_obj):
        messages.error(request, "Only the company owner can permanently delete properties.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    property_label = property_obj.title
    record_audit(
        actor=request.user,
        action="property.deleted",
        target=property_obj,
        company=getattr(getattr(request.user, "profile", None), "company", None),
        details={"property_id": property_obj.id, "category": property_obj.category, "city": property_obj.city},
    )
    property_obj.delete()
    messages.success(request, f"{property_label} permanently deleted.")
    return redirect("properties:list")


@login_required
def property_photo_primary(request, property_id, photo_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if getattr(getattr(request.user, "profile", None), "role", "") != Role.COMPANY_OWNER:
        messages.error(request, "Only the Company Owner can change the property cover photo.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    photo = get_object_or_404(PropertyPhoto, property=property_obj, id=photo_id)
    property_obj.photos.update(is_primary=False)
    photo.is_primary = True
    photo.save(update_fields=["is_primary"])
    messages.success(request, "Cover photo updated.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_cover_photo_upload(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if getattr(getattr(request.user, "profile", None), "role", "") != Role.COMPANY_OWNER:
        messages.error(request, "Only the Company Owner can change the property cover photo.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    image = request.FILES.get("cover_photo")
    if not image:
        messages.error(request, "Select a cover photo to upload.")
        return redirect("properties:detail", property_id=property_obj.id)
    try:
        validate_property_image(image)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("properties:detail", property_id=property_obj.id)
    property_obj.photos.update(is_primary=False)
    PropertyPhoto.objects.create(property=property_obj, image=image, is_primary=True)
    messages.success(request, "Cover photo uploaded successfully.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_photo_delete(request, property_id, photo_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to manage property media.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    photo = get_object_or_404(PropertyPhoto, property=property_obj, id=photo_id)
    was_primary = photo.is_primary
    photo.delete()
    if was_primary:
        next_photo = property_obj.photos.order_by("id").first()
        if next_photo:
            next_photo.is_primary = True
            next_photo.save(update_fields=["is_primary"])
    messages.success(request, "Photo deleted.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_document_delete(request, property_id, document_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to manage property documents.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    document = get_object_or_404(PropertyDocument, property=property_obj, id=document_id)
    document.delete()
    messages.success(request, "Document deleted.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_documents_upload(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to upload property documents.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = PropertyDocumentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Documents could not be uploaded. Check file type and size.")
        return redirect("properties:detail", property_id=property_obj.id)
    for document in form.cleaned_data["documents"]:
        PropertyDocument.objects.create(property=property_obj, document_type=form.cleaned_data["document_type"], title=document.name, file=document)
    messages.success(request, f"{len(form.cleaned_data['documents'])} document(s) uploaded successfully.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_document_review(request, property_id, document_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to review property documents.")
        return redirect("properties:detail", property_id=property_obj.id)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    document = get_object_or_404(PropertyDocument, property=property_obj, id=document_id)
    form = PropertyDocumentReviewForm(request.POST, instance=document)
    if form.is_valid():
        review_property_document(form=form, document=document, actor=request.user)
        messages.success(request, "Document review status updated.")
    else:
        messages.error(request, "Document review could not be saved.")
    return redirect("properties:detail", property_id=property_obj.id)


@login_required
def property_document_download(request, property_id, document_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    document = get_object_or_404(PropertyDocument, property=property_obj, id=document_id)
    if not document.file:
        raise Http404("Document not found.")
    return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.file.name.rsplit("/", 1)[-1])


@login_required
def colony_plot_detail(request, property_id, plot_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    visits = plot.visits.select_related("assigned_employee", "scheduled_by")[:25]
    user_role = getattr(getattr(request.user, "profile", None), "role", "")
    visible_payouts = PropertyCommissionPayout.objects.select_related("paid_by")
    if user_role != Role.COMPANY_OWNER:
        visible_payouts = visible_payouts.filter(role=user_role)
    bookings = plot.bookings.select_related("created_by", "quotation").prefetch_related(
        "installments",
        "payments",
        Prefetch("commission_payouts", queryset=visible_payouts, to_attr="visible_commission_payouts"),
    )[:10]
    return render(
        request,
        "properties/plot_detail.html",
        {
            "property_obj": property_obj,
            "plot": plot,
            "visits": visits,
            "quotations": plot.quotations.select_related("created_by")[:10],
            "bookings": bookings,
            "installment_form": BookingInstallmentForm(),
            "payment_form": BookingPaymentForm(),
            "payment_mode_choices": BookingPayment.PaymentMode.choices,
            "agreement_type_choices": BookingAgreement.AgreementType.choices,
            "agreement_status_choices": BookingAgreement.Status.choices,
            "commission_payout_status_choices": PropertyCommissionPayout.Status.choices,
            "can_edit": can_update_property_for(request, property_obj),
            "can_manage": False,
            "can_manage_commissions": user_role == Role.COMPANY_OWNER,
        },
    )


@login_required
def colony_plot_pdf(request, property_id, plot_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    response = HttpResponse(plot_pdf_bytes(plot), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="plot-{plot.plot_number}-details.pdf"'
    return response


@login_required
def colony_plot_create(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_manage_commission_payouts(request.user):
        messages.error(request, "You do not have access to add colony plots.")
        return redirect("properties:detail", property_id=property_id)
    form = ColonyPlotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plot = create_plot(form=form, property_obj=property_obj, actor=request.user)
        messages.success(request, "Plot saved successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_form.html", {"form": form, "property_obj": property_obj, "mode": "create"})


@login_required
def colony_plot_edit(request, property_id, plot_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    if getattr(getattr(request.user, "profile", None), "role", "") != Role.COMPANY_OWNER:
        messages.error(request, "You do not have access to edit colony plots.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    is_owner = getattr(getattr(request.user, "profile", None), "role", "") == Role.COMPANY_OWNER
    form = ColonyPlotForm(request.POST or None, instance=plot)
    if not is_owner:
        form.fields.pop("status", None)
    if request.method == "POST" and form.is_valid():
        plot = update_plot(form=form, plot=plot, actor=request.user)
        messages.success(request, "Plot updated successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_form.html", {"form": form, "property_obj": property_obj, "plot": plot, "mode": "edit"})


@login_required
def plot_quotation_create(request, property_id, plot_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to create plot quotations.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    money = lambda value: Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base_amount = money(Decimal(plot.area_sqft or 0) * Decimal(plot.base_rate or 0))
    initial = {
        "plot_area_sqft": plot.area_sqft,
        "plot_length_ft": plot.length_ft,
        "plot_width_ft": plot.width_ft,
        "plot_facing": plot.get_facing_display() if plot.facing else "",
        "base_amount": base_amount,
        "plc_amount": money(base_amount * Decimal(plot.plc_rate or 0) / Decimal("100")),
        "charges_amount": money(plot.extra_charges),
    }
    form = PlotQuotationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        quotation = create_quotation(form=form, plot=plot, actor=request.user)
        if quotation.client_email:
            send_property_document_email(
                to_email=quotation.client_email,
                subject=f"Plot quotation #{quotation.id} - {property_obj.title}",
                title=f"Quotation for plot {plot.plot_number}",
                intro=f"Hi {quotation.client_name}, your plot quotation is attached.",
                body=f"Total quotation amount: Rs {quotation.total_amount}.",
                pdf_bytes=quotation_pdf_bytes(quotation),
                filename=f"quotation-{quotation.id}.pdf",
            )
        messages.success(request, "Quotation saved successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_quotation_form.html", {"form": form, "property_obj": property_obj, "plot": plot})


@login_required
def plot_quotation_edit(request, property_id, plot_id, quotation_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    quotation = get_object_or_404(PlotQuotation, id=quotation_id, plot=plot)
    form = PlotQuotationForm(request.POST or None, instance=quotation)
    if request.method == "POST" and form.is_valid():
        update_quotation(form=form, quotation=quotation, actor=request.user)
        messages.success(request, "Quotation updated successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_quotation_form.html", {"form": form, "property_obj": property_obj, "plot": plot, "quotation": quotation, "mode": "edit"})


@login_required
def plot_booking_create(request, property_id, plot_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to book plots.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    is_owner = getattr(getattr(request.user, "profile", None), "role", "") == Role.COMPANY_OWNER
    money = lambda value: Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base_amount = money(Decimal(plot.area_sqft or 0) * Decimal(plot.base_rate or 0))
    form = PlotBookingForm(request.POST or None, request.FILES or None, plot=plot, allow_direct_booking=is_owner, initial={"plot_area_sqft": plot.area_sqft, "plot_length_ft": plot.length_ft, "plot_width_ft": plot.width_ft, "plot_facing": plot.get_facing_display() if plot.facing else "", "agreed_rate": money(plot.base_rate), "plc_amount": money(base_amount * Decimal(plot.plc_rate or 0) / Decimal("100")), "charges_amount": money(plot.extra_charges)})
    if request.method == "POST" and form.is_valid():
        try:
            booking = create_booking(form=form, plot=plot, actor=request.user)
        except ValueError as exc:
            form.add_error(None, str(exc))
            booking = None
        if booking is None:
            return render(request, "properties/plot_booking_form.html", {"form": form, "property_obj": property_obj, "plot": plot})
        if booking.client_email and is_owner:
            send_property_document_email(
                to_email=booking.client_email,
                subject=f"Booking confirmation #{booking.id} - {property_obj.title}",
                title=f"Booking confirmation for plot {plot.plot_number}",
                intro=f"Hi {booking.client_name}, your booking confirmation is attached.",
                body=f"Deal value: Rs {booking.total_deal_value}. Balance: Rs {booking.balance_amount}.",
                pdf_bytes=booking_pdf_bytes(booking),
                filename=f"booking-{booking.id}.pdf",
            )
        messages.success(request, "Plot booking saved successfully." if is_owner else "Booking request sent to the company owner for approval.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_booking_form.html", {"form": form, "property_obj": property_obj, "plot": plot})


@login_required
def plot_booking_edit(request, property_id, plot_id, booking_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    if not can_update_property_for(request, property_obj):
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    is_owner = getattr(getattr(request.user, "profile", None), "role", "") == Role.COMPANY_OWNER
    if not is_owner and booking.status != PlotBooking.Status.REQUESTED:
        messages.error(request, "Only the company owner can edit an approved booking.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    form = PlotBookingForm(request.POST or None, request.FILES or None, instance=booking, plot=plot, allow_direct_booking=is_owner)
    if request.method == "POST" and form.is_valid():
        update_booking_request(form=form, booking=booking, actor=request.user)
        messages.success(request, "Booking updated successfully.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    return render(request, "properties/plot_booking_form.html", {"form": form, "property_obj": property_obj, "plot": plot, "booking": booking, "mode": "edit"})


@login_required
def booking_request_approve(request, property_id, plot_id, booking_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if getattr(getattr(request.user, "profile", None), "role", "") != Role.COMPANY_OWNER:
        messages.error(request, "Only the company owner can approve booking requests.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot, status=PlotBooking.Status.REQUESTED)
    try:
        booking = approve_booking_request(booking=booking, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    if booking.client_email:
        send_property_document_email(
            to_email=booking.client_email,
            subject=f"Booking confirmation #{booking.id} - {property_obj.title}",
            title=f"Booking confirmation for plot {plot.plot_number}",
            intro=f"Hi {booking.client_name}, your booking request has been approved.",
            body=f"Deal value: Rs {booking.total_deal_value}. Balance: Rs {booking.balance_amount}.",
            pdf_bytes=booking_pdf_bytes(booking),
            filename=f"booking-{booking.id}.pdf",
        )
    messages.success(request, "Booking request approved and plot booked successfully.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_installment_create(request, property_id, plot_id, booking_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to manage booking installments.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = BookingInstallmentForm(request.POST)
    if form.is_valid():
        create_booking_installment(form=form, booking=booking, actor=request.user)
        messages.success(request, "Installment added successfully.")
    else:
        messages.error(request, "Installment could not be added. Check amount and due date.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_payment_create(request, property_id, plot_id, booking_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to receive booking payments.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = BookingPaymentForm(request.POST, booking=booking)
    if form.is_valid():
        receive_booking_payment(form=form, booking=booking, actor=request.user)
        messages.success(request, "Payment received successfully.")
    else:
        messages.error(request, "Payment could not be recorded. Check amount and installment balance.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_agreement_create(request, property_id, plot_id, booking_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to manage booking agreements.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = BookingAgreementForm(request.POST, request.FILES)
    if form.is_valid():
        create_booking_agreement(form=form, booking=booking, actor=request.user)
        messages.success(request, "Agreement saved successfully.")
    else:
        messages.error(request, "Agreement could not be saved. Check required dates for signed/registered status.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_agreement_update(request, property_id, plot_id, booking_id, agreement_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if not can_update_property_for(request, property_obj):
        messages.error(request, "You do not have access to update booking agreements.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    agreement = get_object_or_404(BookingAgreement, id=agreement_id, booking=booking)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = BookingAgreementForm(request.POST, request.FILES, instance=agreement)
    if form.is_valid():
        update_booking_agreement(form=form, agreement=agreement, actor=request.user)
        messages.success(request, "Agreement updated successfully.")
    else:
        messages.error(request, "Agreement could not be updated. Check required dates for signed/registered status.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_commission_payout_update(request, property_id, plot_id, booking_id, payout_id):
    property_obj = get_object_or_404(visible_properties_for(request).prefetch_related("plots"), id=property_id)
    if getattr(getattr(request.user, "profile", None), "role", "") != Role.COMPANY_OWNER:
        messages.error(request, "You do not have access to update commission payouts.")
        return redirect("properties:plot_detail", property_id=property_id, plot_id=plot_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    payout = get_object_or_404(PropertyCommissionPayout, id=payout_id, booking=booking)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    status = request.POST.get("status", "")
    if status not in dict(PropertyCommissionPayout.Status.choices):
        messages.error(request, "Invalid commission payout status.")
        return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)
    update_commission_payout(
        payout=payout,
        status=status,
        actor=request.user,
        payout_reference=request.POST.get("payout_reference", "").strip(),
        note=request.POST.get("note", "").strip(),
    )
    messages.success(request, "Commission payout updated successfully.")
    return redirect("properties:plot_detail", property_id=property_obj.id, plot_id=plot.id)


@login_required
def booking_agreement_download(request, property_id, plot_id, booking_id, agreement_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    agreement = get_object_or_404(BookingAgreement, id=agreement_id, booking=booking)
    if not agreement.file:
        raise Http404("Agreement not found.")
    return FileResponse(agreement.file.open("rb"), as_attachment=True, filename=agreement.file.name.rsplit("/", 1)[-1])


@login_required
def plot_quotation_pdf(request, property_id, plot_id, quotation_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    quotation = get_object_or_404(PlotQuotation, id=quotation_id, plot=plot)
    response = HttpResponse(quotation_pdf_bytes(quotation), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="quotation-{quotation.id}.pdf"'
    return response


@login_required
def plot_booking_pdf(request, property_id, plot_id, booking_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    plot = get_object_or_404(property_obj.plots, id=plot_id)
    booking = get_object_or_404(PlotBooking, id=booking_id, plot=plot)
    response = HttpResponse(booking_pdf_bytes(booking), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="booking-{booking.id}.pdf"'
    return response
