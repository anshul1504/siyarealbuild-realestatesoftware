from django.db import transaction
from django.utils import timezone

from accounts.services import record_audit

from .models import PropertyStatusHistory, PropertyVisit


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
        record_audit(actor=actor, action="property.status_changed", target=prop, company=actor.profile.company, details={"from": old_status, "to": prop.status})
    if old_assignee != prop.assigned_to_id:
        record_audit(actor=actor, action="property.assigned", target=prop, company=actor.profile.company, details={"assigned_to_id": prop.assigned_to_id})
    return prop


@transaction.atomic
def update_visit(*, form, actor):
    visit = form.save()
    if visit.outcome in {PropertyVisit.Outcome.BOOKED, PropertyVisit.Outcome.CLOSED} and not visit.converted_at:
        visit.converted_at = timezone.now()
        visit.save(update_fields=["converted_at", "updated_at"])
    record_audit(actor=actor, action="property_visit.updated", target=visit, company=actor.profile.company, details={"status": visit.status, "outcome": visit.outcome})
    return visit
