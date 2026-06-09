from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import PropertyVisitForm
from ..models import PropertyVisit
from ..services import update_visit
from .helpers import can_manage_properties_for, visible_properties_for


@login_required
def property_visit_list(request, property_id):
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    visits = property_obj.visits.select_related("assigned_employee", "scheduled_by", "plot")
    return render(request, "properties/visit_list.html", {"property_obj": property_obj, "visits": visits, "can_manage": can_manage_properties_for(request)})


@login_required
def property_visit_create(request, property_id, plot_id=None):
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to schedule property visits.")
        return redirect("properties:detail", property_id=property_id)
    property_obj = get_object_or_404(visible_properties_for(request), id=property_id)
    initial = {"plot": get_object_or_404(property_obj.plots, id=plot_id)} if plot_id else {}
    form = PropertyVisitForm(request.POST or None, property_obj=property_obj, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        visit = form.save(commit=False)
        visit.property = property_obj
        visit.scheduled_by = request.user
        visit.save()
        messages.success(request, "Property visit scheduled successfully.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    return render(request, "properties/visit_form.html", {"form": form, "property_obj": property_obj, "mode": "create"})


@login_required
def property_visit_detail(request, visit_id):
    visit = get_object_or_404(
        PropertyVisit.objects.select_related("property", "plot", "assigned_employee", "scheduled_by"),
        id=visit_id,
        property__in=visible_properties_for(request),
    )
    return render(request, "properties/visit_detail.html", {"visit": visit, "property_obj": visit.property, "can_manage": can_manage_properties_for(request)})


@login_required
def property_visit_edit(request, visit_id):
    visit = get_object_or_404(PropertyVisit.objects.select_related("property"), id=visit_id, property__in=visible_properties_for(request))
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to edit property visits.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    form = PropertyVisitForm(request.POST or None, instance=visit, property_obj=visit.property, user=request.user)
    if request.method == "POST" and form.is_valid():
        update_visit(form=form, actor=request.user)
        messages.success(request, "Property visit updated successfully.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    return render(request, "properties/visit_form.html", {"form": form, "property_obj": visit.property, "visit": visit, "mode": "edit"})


@login_required
def property_visit_delete(request, visit_id):
    visit = get_object_or_404(PropertyVisit, id=visit_id, property__in=visible_properties_for(request))
    property_id = visit.property_id
    if not can_manage_properties_for(request):
        messages.error(request, "You do not have access to delete property visits.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    if request.method == "POST":
        visit.delete()
        messages.success(request, "Property visit deleted successfully.")
        return redirect("properties:visits", property_id=property_id)
    return redirect("properties:visit_detail", visit_id=visit.id)
