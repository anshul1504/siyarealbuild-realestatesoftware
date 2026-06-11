from django.db import transaction
from django.utils import timezone

from accounts.services import record_audit

from .models import PropertyStatusHistory, PropertyVisit


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
