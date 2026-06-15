"""Public website page, lead-capture, and utility views."""

import qrcode
import qrcode.image.svg

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    EnquiryForm,
    HomeSiteVisitForm,
    PropertySubmissionForm,
    SiteVisitRequestForm,
)
from .models import (
    AchievementCounter,
    FAQ,
    GalleryItem,
    HeroBanner,
    Project,
    PropertyCategory,
    PropertyListing,
    Service,
    SiteSettings,
    TeamMember,
    Testimonial,
)

PROPERTY_PAGE_SIZE = 9
TEAM_PAGE_SIZE = 12
GALLERY_PAGE_SIZE = 9


# Marketing pages


def home(request):
    visit_form = HomeSiteVisitForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and visit_form.is_valid():
        visit_form.save()
        messages.success(
            request,
            "Your site visit request has been received. Our team will confirm it shortly.",
        )
        return redirect("website:home")
    return render(
        request,
        "website/home.html",
        {
            "heroes": HeroBanner.objects.filter(is_active=True)[:6],
            "properties": PropertyListing.objects.filter(is_active=True).order_by(
                "-is_featured", "sort_order", "id"
            )[:6],
            "services": Service.objects.filter(is_active=True)[:6],
            "counters": AchievementCounter.objects.filter(is_active=True)[:6],
            "testimonials": Testimonial.objects.filter(is_active=True)[:6],
            "faqs": FAQ.objects.filter(is_active=True)[:8],
            "home_visit_form": visit_form,
        },
    )


def about(request):
    return render(
        request,
        "website/about.html",
        {
            "counters": AchievementCounter.objects.filter(is_active=True)[:6],
            "testimonials": Testimonial.objects.filter(is_active=True),
            "faqs": FAQ.objects.filter(is_active=True),
        },
    )


def services(request):
    return render(
        request,
        "website/services.html",
        {
            "services": Service.objects.filter(is_active=True),
            "faqs": FAQ.objects.filter(is_active=True),
        },
    )


def projects(request):
    return render(
        request,
        "website/project_list.html",
        {"projects": Project.objects.filter(is_active=True)},
    )


# Lead capture


def contact(request):
    form = EnquiryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Thank you. Our property team will contact you shortly."
        )
        return redirect("website:contact")
    return render(request, "website/contact.html", {"form": form})


def post_property(request):
    form = PropertySubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Your property has been submitted for review. Our team will contact you shortly.",
        )
        return redirect("website:post_property")
    return render(request, "website/post_property.html", {"form": form})


# Directory and detail pages


def team(request):
    paginator = Paginator(TeamMember.objects.filter(is_active=True), TEAM_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request, "website/team.html", {"members": page_obj, "page_obj": page_obj}
    )


def gallery(request):
    category = request.GET.get("category", "").strip()
    items = GalleryItem.objects.filter(is_active=True)
    if category:
        items = items.filter(category=category)
    paginator = Paginator(items, GALLERY_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "website/gallery.html",
        {
            "items": page_obj,
            "page_obj": page_obj,
            "category": category,
            "categories": GalleryItem.Category.choices,
        },
    )


def property_list(request):
    properties = PropertyListing.objects.filter(is_active=True).select_related(
        "project", "category"
    )
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    location = request.GET.get("location", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    bedrooms = request.GET.get("bedrooms", "").strip()
    sort = request.GET.get("sort", "featured").strip()
    if query:
        properties = properties.filter(
            Q(title__icontains=query)
            | Q(location__icontains=query)
            | Q(summary__icontains=query)
        )
    if category:
        properties = properties.filter(category__slug=category)
    if location:
        properties = properties.filter(location=location)
    if min_price.isdigit():
        properties = properties.filter(price__gte=min_price)
    if max_price.isdigit():
        properties = properties.filter(price__lte=max_price)
    if bedrooms.isdigit():
        properties = properties.filter(bedrooms__gte=bedrooms)
    orderings = {
        "featured": ("-is_featured", "sort_order", "id"),
        "price_low": ("price", "id"),
        "price_high": ("-price", "id"),
        "newest": ("-id",),
    }
    properties = properties.order_by(*orderings.get(sort, orderings["featured"]))
    paginator = Paginator(properties, PROPERTY_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    locations = (
        PropertyListing.objects.filter(is_active=True)
        .order_by("location")
        .values_list("location", flat=True)
        .distinct()
    )
    return render(
        request,
        "website/property_list.html",
        {
            "properties": page_obj,
            "page_obj": page_obj,
            "query": query,
            "category": category,
            "location": location,
            "min_price": min_price,
            "max_price": max_price,
            "bedrooms": bedrooms,
            "sort": sort,
            "categories": PropertyCategory.objects.filter(is_active=True),
            "locations": locations,
            "result_count": paginator.count,
        },
    )


def property_detail(request, slug):
    property_obj = get_object_or_404(
        PropertyListing.objects.filter(is_active=True).prefetch_related("gallery"),
        slug=slug,
    )
    enquiry_form = EnquiryForm(
        request.POST
        if request.method == "POST" and "enquiry_submit" in request.POST
        else None,
        initial={"property": property_obj},
    )
    if (
        request.method == "POST"
        and "enquiry_submit" in request.POST
        and enquiry_form.is_valid()
    ):
        enquiry_form.save()
        messages.success(request, "Your enquiry has been submitted.")
        return redirect(property_obj)
    related_properties = PropertyListing.objects.filter(
        is_active=True, category=property_obj.category
    ).exclude(pk=property_obj.pk)[:3]
    amenities = [
        item.strip() for item in property_obj.amenities.splitlines() if item.strip()
    ]
    return render(
        request,
        "website/property_detail.html",
        {
            "property_obj": property_obj,
            "enquiry_form": enquiry_form,
            "amenities": amenities,
            "related_properties": related_properties,
        },
    )


def project_detail(request, slug):
    project = get_object_or_404(
        Project.objects.filter(is_active=True).prefetch_related(
            "gallery", "properties"
        ),
        slug=slug,
    )
    return render(request, "website/project_detail.html", {"project": project})


# Workflow actions and utilities


def site_visit_request(request, slug):
    property_obj = get_object_or_404(
        PropertyListing.objects.filter(is_active=True), slug=slug
    )
    if request.method != "POST":
        return redirect(property_obj)
    form = SiteVisitRequestForm(request.POST, initial={"property": property_obj})
    if form.is_valid():
        visit = form.save(commit=False)
        visit.property = property_obj
        visit.save()
        messages.success(
            request, "Site visit request received. Our team will confirm it shortly."
        )
    else:
        messages.error(request, "Please check the site visit details.")
    return redirect(property_obj)


def whatsapp_qr(request):
    settings = SiteSettings.objects.first()
    number = settings.whatsapp_number if settings else ""
    image = qrcode.make(
        f"https://wa.me/{number}",
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8,
        border=2,
    )
    response = HttpResponse(content_type="image/svg+xml")
    image.save(response)
    return response
