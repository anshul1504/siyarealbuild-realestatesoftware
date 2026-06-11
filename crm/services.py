import json
import re
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounts.models import AuditLog, NotificationDelivery, Role
from properties.models import PropertyVisit

from .models import AssignmentMode, Lead, LeadActivity, LeadAssignmentRule, LeadFollowUp, LeadStatus, MetaLeadSource, MetaWebhookEvent


STANDARD_FIELD_ALIASES = {
    "client_name": {"client_name", "full_name", "name", "first_name"},
    "phone": {"phone", "phone_number", "mobile", "mobile_number", "contact_number"},
    "email": {"email", "email_address"},
    "city": {"city", "location_city"},
    "locality": {"locality", "area", "location"},
    "requirement": {"requirement", "requirements", "message", "comments"},
    "budget_min": {"budget_min", "min_budget"},
    "budget_max": {"budget_max", "max_budget", "budget"},
}


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def record_audit(lead, *, actor=None, action, details=None):
    AuditLog.objects.create(
        company=lead.company,
        actor=actor,
        action=action,
        target_type="crm.lead",
        target_id=str(lead.id),
        target_label=lead.client_name,
        details=details or {},
    )


def record_notification(*, lead, sent_by=None, recipient_user=None, category, subject, error_message=""):
    if not recipient_user or not getattr(recipient_user, "email", ""):
        return None
    return NotificationDelivery.objects.create(
        company=lead.company,
        sent_by=sent_by,
        category=category,
        recipient=recipient_user.email,
        subject=subject,
        status=NotificationDelivery.Status.FAILED if error_message else NotificationDelivery.Status.SENT,
        error_message=error_message,
    )


def record_activity(lead, *, actor=None, activity_type=LeadActivity.ActivityType.NOTE, old_value="", new_value="", note="", metadata=None):
    activity = LeadActivity.objects.create(
        lead=lead,
        actor=actor,
        activity_type=activity_type,
        old_value=old_value or "",
        new_value=new_value or "",
        note=note or "",
        metadata=metadata or {},
    )
    record_audit(
        lead,
        actor=actor,
        action=f"crm.{activity_type}",
        details={"old_value": old_value or "", "new_value": new_value or "", "note": note or "", "metadata": metadata or {}},
    )
    return activity


def assignee_from_rule(rule):
    if rule.default_assignee_id:
        return rule.default_assignee
    if rule.default_role:
        member = rule.company.members.filter(role=rule.default_role).select_related("user").first()
        return member.user if member else None
    return None


def matching_assignment_rules(company, data):
    rules = LeadAssignmentRule.objects.filter(company=company, is_active=True).select_related("default_assignee", "company")
    source = data.get("source") or ""
    city = (data.get("city") or "").strip().lower()
    category = data.get("property_category") or ""
    return rules.filter(
        models.Q(mode=AssignmentMode.DEFAULT)
        | models.Q(mode=AssignmentMode.SOURCE, source=source)
        | models.Q(mode=AssignmentMode.CITY, city__iexact=city)
        | models.Q(mode=AssignmentMode.CATEGORY, property_category=category)
    )


def auto_assignee_for_lead(company, data):
    for rule in matching_assignment_rules(company, data):
        assignee = assignee_from_rule(rule)
        if assignee:
            return assignee, rule
    return None, None


@transaction.atomic
def create_lead(*, company, actor, data):
    if not data.get("assigned_to"):
        assignee, rule = auto_assignee_for_lead(company, data)
        if assignee:
            data["assigned_to"] = assignee
    lead = Lead.objects.create(
        company=company,
        created_by=actor,
        assigned_by=actor if data.get("assigned_to") else None,
        **data,
    )
    record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.CREATED, new_value=lead.get_status_display(), note="Lead created.")
    if lead.assigned_to_id:
        record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.ASSIGNED, new_value=str(lead.assigned_to), note="Lead assigned.")
        record_notification(lead=lead, sent_by=actor, recipient_user=lead.assigned_to, category="crm_assignment", subject=f"New CRM lead assigned: {lead.client_name}")
    return lead


@transaction.atomic
def update_lead_details(lead, *, actor, data, changed_fields=None):
    changed_fields = set(changed_fields or [])
    tracked_fields = [
        "client_name",
        "phone",
        "email",
        "city",
        "locality",
        "budget_min",
        "budget_max",
        "requirement",
        "property_category",
        "listing_for",
        "source",
        "priority",
        "property",
        "notes",
    ]
    changed = []
    for field in tracked_fields:
        if field not in data:
            continue
        old_value = getattr(lead, field)
        new_value = data[field]
        if old_value != new_value or field in changed_fields:
            setattr(lead, field, new_value)
            changed.append(field)
    if "assigned_to" in data and (lead.assigned_to_id != getattr(data["assigned_to"], "id", None) or "assigned_to" in changed_fields):
        lead.assigned_to = data["assigned_to"]
        lead.assigned_by = actor
        changed.extend(["assigned_to", "assigned_by"])
    if changed:
        lead.save(update_fields=[*set(changed), "updated_at"])
        record_activity(
            lead,
            actor=actor,
            activity_type=LeadActivity.ActivityType.NOTE,
            new_value="details_updated",
            note=f"Lead details updated: {', '.join(sorted(set(changed)))}.",
        )
    return lead


@transaction.atomic
def update_lead_status(lead, *, actor, status, note=""):
    old_status = lead.status
    lead.status = status
    if status in {LeadStatus.CLOSED, LeadStatus.BOOKED} and not lead.converted_at:
        lead.converted_at = timezone.now()
    if status == LeadStatus.LOST:
        lead.lost_reason = note
    lead.save(update_fields=["status", "converted_at", "lost_reason", "updated_at"])
    record_activity(
        lead,
        actor=actor,
        activity_type=LeadActivity.ActivityType.STATUS,
        old_value=old_status,
        new_value=status,
        note=note,
    )
    return lead


@transaction.atomic
def assign_lead(lead, *, actor, assigned_to, note=""):
    old_assignee = str(lead.assigned_to) if lead.assigned_to_id else "Unassigned"
    lead.assigned_to = assigned_to
    lead.assigned_by = actor
    lead.save(update_fields=["assigned_to", "assigned_by", "updated_at"])
    record_activity(
        lead,
        actor=actor,
        activity_type=LeadActivity.ActivityType.ASSIGNED,
        old_value=old_assignee,
        new_value=str(assigned_to) if assigned_to else "Unassigned",
        note=note or "Lead assignment updated.",
    )
    record_notification(lead=lead, sent_by=actor, recipient_user=assigned_to, category="crm_assignment", subject=f"CRM lead assignment updated: {lead.client_name}")
    return lead


def add_lead_note(lead, *, actor, note):
    return record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.NOTE, note=note)


def create_followup(lead, *, actor, assigned_to, due_at, note=""):
    followup = LeadFollowUp.objects.create(lead=lead, assigned_to=assigned_to, due_at=due_at, note=note)
    lead.next_follow_up_at = due_at
    lead.status = LeadStatus.FOLLOW_UP
    lead.save(update_fields=["next_follow_up_at", "status", "updated_at"])
    record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.FOLLOW_UP, new_value=str(due_at), note=note)
    record_notification(lead=lead, sent_by=actor, recipient_user=assigned_to, category="crm_followup", subject=f"CRM follow-up scheduled: {lead.client_name}")
    return followup


@transaction.atomic
def complete_followup(followup, *, actor, outcome="", note=""):
    followup.status = LeadFollowUp.Status.DONE
    followup.completed_at = timezone.now()
    followup.outcome = outcome
    if note:
        followup.note = note
    followup.save(update_fields=["status", "completed_at", "outcome", "note"])
    record_activity(
        followup.lead,
        actor=actor,
        activity_type=LeadActivity.ActivityType.FOLLOW_UP,
        new_value="completed",
        note=outcome or note or "Follow-up completed.",
    )
    next_open = followup.lead.followups.filter(status=LeadFollowUp.Status.OPEN).order_by("due_at").first()
    followup.lead.next_follow_up_at = next_open.due_at if next_open else None
    followup.lead.save(update_fields=["next_follow_up_at", "updated_at"])
    return followup


@transaction.atomic
def match_property_to_lead(lead, *, actor, property_obj, note=""):
    lead.property = property_obj
    lead.status = LeadStatus.PROPERTY_MATCHED
    lead.save(update_fields=["property", "status", "updated_at"])
    property_obj.lead_count = property_obj.crm_leads.count()
    property_obj.save(update_fields=["lead_count", "updated_at"])
    record_activity(
        lead,
        actor=actor,
        activity_type=LeadActivity.ActivityType.NOTE,
        new_value=str(property_obj),
        note=note or "Property matched with lead.",
    )
    return lead


@transaction.atomic
def schedule_visit_from_lead(lead, *, actor, property_obj, visit_at, assigned_employee=None, notes=""):
    visit = PropertyVisit.objects.create(
        property=property_obj,
        scheduled_by=actor,
        assigned_employee=assigned_employee or lead.assigned_to,
        client_name=lead.client_name,
        client_phone=lead.phone,
        client_email=lead.email,
        visit_at=visit_at,
        notes=notes,
    )
    lead.property = property_obj
    lead.visit = visit
    lead.status = LeadStatus.VISIT_SCHEDULED
    lead.save(update_fields=["property", "visit", "status", "updated_at"])
    record_activity(
        lead,
        actor=actor,
        activity_type=LeadActivity.ActivityType.VISIT,
        new_value=str(visit_at),
        note=notes or "Site visit scheduled from CRM.",
        metadata={"visit_id": visit.id, "property_id": property_obj.id},
    )
    return visit


@transaction.atomic
def bulk_update_leads(*, leads, actor, action, assigned_to=None, status="", priority="", note=""):
    updated = 0
    for lead in leads:
        if action == "assign":
            assign_lead(lead, actor=actor, assigned_to=assigned_to, note=note)
            updated += 1
        elif action == "status" and status:
            update_lead_status(lead, actor=actor, status=status, note=note)
            updated += 1
        elif action == "priority" and priority:
            old_priority = lead.priority
            lead.priority = priority
            lead.save(update_fields=["priority", "updated_at"])
            record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.NOTE, old_value=old_priority, new_value=priority, note=note or "Priority updated.")
            updated += 1
    return updated


def fetch_meta_lead_data(leadgen_id, *, access_token=None):
    token = access_token or getattr(settings, "META_PAGE_ACCESS_TOKEN", "")
    if not token:
        return {}
    version = getattr(settings, "META_GRAPH_API_VERSION", "v20.0")
    query = urlencode({"access_token": token})
    url = f"https://graph.facebook.com/{version}/{leadgen_id}?{query}"
    try:
        with urlopen(url, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except (OSError, URLError):
        return {}
    payload = json.loads(raw or "{}")
    mapped = {"meta_lead_id": leadgen_id}
    for item in payload.get("field_data", []) or []:
        name = item.get("name")
        values = item.get("values") or []
        value = values[0] if values else ""
        if name in {"full_name", "name"}:
            mapped["client_name"] = value
        elif name in {"phone_number", "phone"}:
            mapped["phone"] = value
        elif name == "email":
            mapped["email"] = value
        elif name == "city":
            mapped["city"] = value
        else:
            mapped.setdefault("requirement", "")
            if value:
                mapped["requirement"] = (mapped["requirement"] + f"{name}: {value}\n").strip()
    return mapped


def flatten_meta_data(fetched_data):
    if not isinstance(fetched_data, dict):
        return {}
    if "field_data" not in fetched_data:
        return fetched_data
    flattened = {}
    for item in fetched_data.get("field_data", []) or []:
        name = item.get("name")
        values = item.get("values") or []
        if name:
            flattened[name] = values[0] if values else ""
    return flattened


def mapped_meta_data(source, fetched_data):
    raw_data = flatten_meta_data(fetched_data)
    mapping = source.field_mapping or {}
    mapped = {}
    for lead_field, meta_field in mapping.items():
        if lead_field in {field.name for field in Lead._meta.fields} and meta_field in raw_data:
            mapped[lead_field] = raw_data.get(meta_field)
    for lead_field, aliases in STANDARD_FIELD_ALIASES.items():
        if mapped.get(lead_field):
            continue
        for alias in aliases:
            if raw_data.get(alias):
                mapped[lead_field] = raw_data[alias]
                break
    extra_lines = []
    known_meta_fields = {value for value in mapping.values() if isinstance(value, str)}
    for aliases in STANDARD_FIELD_ALIASES.values():
        known_meta_fields.update(aliases)
    for key, value in raw_data.items():
        if value and key not in known_meta_fields:
            extra_lines.append(f"{key}: {value}")
    if extra_lines:
        mapped["requirement"] = "\n".join([mapped.get("requirement", ""), *extra_lines]).strip()
    return mapped


def find_duplicate_lead(company, *, meta_lead_id="", phone="", email=""):
    if meta_lead_id:
        existing = Lead.objects.filter(meta_lead_id=meta_lead_id).first()
        if existing:
            return existing
    normalized_phone = normalize_phone(phone)
    for lead in Lead.objects.filter(company=company):
        if normalized_phone and normalize_phone(lead.phone) == normalized_phone:
            return lead
        if email and lead.email and lead.email.lower() == email.lower():
            return lead
    return None


def default_assignee_for_meta(source):
    if source.default_assignee_id:
        return source.default_assignee
    company = source.company
    if source.default_role:
        member = company.members.filter(role=source.default_role).select_related("user").first()
        return member.user if member else None
    manager = company.members.filter(role=Role.MANAGER).select_related("user").first()
    return manager.user if manager else None


def default_assignee_for_meta_data(source, data):
    assignee, _ = auto_assignee_for_lead(source.company, {**data, "source": "meta"})
    return assignee or default_assignee_for_meta(source)


@transaction.atomic
def ingest_meta_payload(*, source, payload, fetched_data=None):
    event_id = str(payload.get("event_id") or payload.get("leadgen_id") or payload.get("id") or "")
    event, created = MetaWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={"company": source.company, "payload": payload},
    )
    if not created:
        event.status = MetaWebhookEvent.Status.DUPLICATE
        event.save(update_fields=["status"])
        return None, event
    data = mapped_meta_data(source, fetched_data or {})
    meta_lead_id = str(data.get("meta_lead_id") or payload.get("leadgen_id") or event_id)
    duplicate = find_duplicate_lead(source.company, meta_lead_id=meta_lead_id, phone=data.get("phone", ""), email=data.get("email", ""))
    if duplicate:
        event.status = MetaWebhookEvent.Status.DUPLICATE
        event.error_message = f"Duplicate lead: {duplicate.id}"
        event.save(update_fields=["status", "error_message"])
        record_activity(duplicate, activity_type=LeadActivity.ActivityType.META_SYNC, new_value="duplicate", note="Duplicate Meta lead received.", metadata={"event_id": event_id})
        return None, event
    lead = Lead.objects.create(
        company=source.company,
        client_name=data.get("client_name") or data.get("full_name") or "Meta Lead",
        phone=data.get("phone") or data.get("phone_number") or "",
        email=data.get("email") or "",
        city=data.get("city") or "",
        requirement=data.get("requirement") or "",
        source="meta",
        meta_lead_id=meta_lead_id,
        meta_form_id=source.form_id,
        meta_page_id=source.page_id,
        assigned_to=default_assignee_for_meta_data(source, data),
    )
    record_activity(lead, activity_type=LeadActivity.ActivityType.META_SYNC, new_value="received", note="Lead received from Meta.")
    record_notification(lead=lead, recipient_user=lead.assigned_to, category="crm_meta_lead", subject=f"New Meta lead received: {lead.client_name}")
    event.status = MetaWebhookEvent.Status.PROCESSED
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "processed_at"])
    return lead, event


@transaction.atomic
def reprocess_meta_event(event, *, actor=None):
    payload = event.payload or {}
    form_id = str(payload.get("form_id") or "")
    page_id = str(payload.get("page_id") or "")
    leadgen_id = str(payload.get("leadgen_id") or event.event_id or "")
    source = MetaLeadSource.objects.filter(form_id=form_id, page_id=page_id, is_active=True).select_related("company", "default_assignee").first()
    if not source:
        event.status = MetaWebhookEvent.Status.FAILED
        event.error_message = "No active Meta source mapping."
        event.save(update_fields=["status", "error_message"])
        return None, event
    event.delete()
    lead, new_event = ingest_meta_payload(
        source=source,
        payload={"event_id": leadgen_id, "leadgen_id": leadgen_id, "form_id": form_id, "page_id": page_id},
        fetched_data=payload,
    )
    if lead:
        record_activity(lead, actor=actor, activity_type=LeadActivity.ActivityType.META_SYNC, new_value="reprocessed", note="Meta event reprocessed.")
    return lead, new_event
