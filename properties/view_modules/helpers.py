from django.urls import reverse

from ..models import Property, PropertyDocument, PropertyPhoto
from ..policies import can_manage_properties
from ..selectors import visible_properties


def visible_properties_for(request):
    return visible_properties(request.user)


def can_manage_properties_for(request):
    return can_manage_properties(request.user)


def save_property_uploads(prop, form, request):
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


def property_share_message(property_obj, request=None):
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
