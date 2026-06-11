from django.db import transaction
from django.utils import timezone

from accounts.services import record_audit

from .models import ColonyPlot, PlotBooking, PlotStatusHistory, PropertyStatusHistory, PropertyVisit


def actor_company(actor):
    return getattr(getattr(actor, "profile", None), "company", None)


@transaction.atomic
def create_property(*, form, owner):
    prop = form.save(commit=False)
    prop.owner = owner
    prop.save()
    form.save_m2m()
    PropertyStatusHistory.objects.create(property=prop, to_status=prop.status, changed_by=owner, note="Property created")
    record_audit(
        actor=owner,
        action="property.created",
        target=prop,
        company=actor_company(owner),
        details={"status": prop.status, "category": prop.category},
    )
    return prop


@transaction.atomic
def update_property(*, form, property_obj, actor):
    persisted = (
        property_obj.__class__.objects.select_for_update()
        .only("status", "assigned_to_id")
        .get(pk=property_obj.pk)
    )
    old_status = persisted.status
    old_assignee = persisted.assigned_to_id
    prop = form.save()
    if old_status != prop.status:
        PropertyStatusHistory.objects.create(property=prop, from_status=old_status, to_status=prop.status, changed_by=actor)
        record_audit(actor=actor, action="property.status_changed", target=prop, company=actor_company(actor), details={"from": old_status, "to": prop.status})
    if old_assignee != prop.assigned_to_id:
        record_audit(actor=actor, action="property.assigned", target=prop, company=actor_company(actor), details={"assigned_to_id": prop.assigned_to_id})
    return prop


@transaction.atomic
def bulk_update_property_status(*, queryset, status, actor):
    updated = 0
    for prop in queryset.select_for_update():
        old_status = prop.status
        if old_status == status:
            continue
        prop.status = status
        prop.save(update_fields=["status", "updated_at"])
        PropertyStatusHistory.objects.create(property=prop, from_status=old_status, to_status=status, changed_by=actor)
        record_audit(
            actor=actor,
            action="property.status_changed",
            target=prop,
            company=actor_company(actor),
            details={"from": old_status, "to": status, "source": "bulk_action"},
        )
        updated += 1
    return updated


@transaction.atomic
def bulk_delete_properties(*, queryset, actor):
    deleted = 0
    company = actor_company(actor)
    for prop in queryset.select_for_update():
        record_audit(
            actor=actor,
            action="property.deleted",
            target=prop,
            company=company,
            target_label=str(prop),
            details={"property_id": prop.id, "status": prop.status, "category": prop.category},
        )
        prop.delete()
        deleted += 1
    return deleted


@transaction.atomic
def update_visit(*, form, actor):
    visit = form.save()
    if visit.outcome in {PropertyVisit.Outcome.BOOKED, PropertyVisit.Outcome.CLOSED} and not visit.converted_at:
        visit.converted_at = timezone.now()
        visit.save(update_fields=["converted_at", "updated_at"])
    record_audit(actor=actor, action="property_visit.updated", target=visit, company=actor_company(actor), details={"status": visit.status, "outcome": visit.outcome})
    return visit


@transaction.atomic
def create_plot(*, form, property_obj, actor):
    plot = form.save(commit=False)
    plot.property = property_obj
    plot.save()
    PlotStatusHistory.objects.create(plot=plot, to_status=plot.status, changed_by=actor, note="Plot created")
    record_audit(actor=actor, action="property_plot.created", target=property_obj, company=actor_company(actor), details={"plot_id": plot.id, "plot_number": plot.plot_number, "status": plot.status})
    sync_available_plots(property_obj)
    return plot


@transaction.atomic
def update_plot(*, form, plot, actor):
    persisted = ColonyPlot.objects.select_for_update().only("status").get(pk=plot.pk)
    old_status = persisted.status
    updated = form.save()
    if old_status != updated.status:
        PlotStatusHistory.objects.create(plot=updated, from_status=old_status, to_status=updated.status, changed_by=actor)
        record_audit(actor=actor, action="property_plot.status_changed", target=updated.property, company=actor_company(actor), details={"plot_id": updated.id, "from": old_status, "to": updated.status})
    else:
        record_audit(actor=actor, action="property_plot.updated", target=updated.property, company=actor_company(actor), details={"plot_id": updated.id, "plot_number": updated.plot_number})
    sync_available_plots(updated.property)
    return updated


def sync_available_plots(property_obj):
    property_obj.available_plots = property_obj.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED, ColonyPlot.Status.BOOKED]).count()
    property_obj.total_plots = max(property_obj.total_plots, property_obj.plots.count())
    property_obj.save(update_fields=["available_plots", "total_plots", "updated_at"])


@transaction.atomic
def create_quotation(*, form, plot, actor):
    quotation = form.save(commit=False)
    quotation.plot = plot
    quotation.created_by = actor
    quotation.save()
    record_audit(actor=actor, action="property_plot.quotation_created", target=plot.property, company=actor_company(actor), details={"plot_id": plot.id, "quotation_id": quotation.id, "total": str(quotation.total_amount)})
    return quotation


@transaction.atomic
def create_booking(*, form, plot, actor):
    booking = form.save(commit=False)
    booking.plot = plot
    booking.created_by = actor
    if booking.status in {PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED}:
        booking.approved_by = actor
    booking.save()
    if booking.status == PlotBooking.Status.BOOKED:
        old_status = plot.status
        plot.status = ColonyPlot.Status.BOOKED
        plot.save(update_fields=["status"])
        PlotStatusHistory.objects.create(plot=plot, from_status=old_status, to_status=plot.status, changed_by=actor, note=f"Booked by {booking.client_name}")
    record_audit(actor=actor, action="property_plot.booking_created", target=plot.property, company=actor_company(actor), details={"plot_id": plot.id, "booking_id": booking.id, "status": booking.status})
    sync_available_plots(plot.property)
    return booking
