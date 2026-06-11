from django.conf import settings
from django.db import models

from accounts.models import CompanyProfile, Role
from properties.models import Property, PropertyVisit


class LeadSource(models.TextChoices):
    META = "meta", "Meta Lead Ads"
    MANUAL = "manual", "Manual"
    WEBSITE = "website", "Website"
    REFERRAL = "referral", "Referral"
    WHATSAPP = "whatsapp", "WhatsApp"
    PROPERTY_SHARE = "property_share", "Property Share"


class LeadStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    QUALIFIED = "qualified", "Qualified"
    PROPERTY_MATCHED = "property_matched", "Property Matched"
    VISIT_SCHEDULED = "visit_scheduled", "Site Visit Scheduled"
    VISIT_COMPLETED = "visit_completed", "Site Visit Completed"
    FOLLOW_UP = "follow_up", "Follow-up"
    NEGOTIATION = "negotiation", "Negotiation"
    BOOKED = "booked", "Booked"
    CLOSED = "closed", "Closed"
    LOST = "lost", "Lost"
    DUPLICATE = "duplicate", "Duplicate"


class LeadPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class Lead(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="crm_leads")
    client_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True, db_index=True)
    city = models.CharField(max_length=80, blank=True)
    locality = models.CharField(max_length=120, blank=True)
    budget_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    requirement = models.TextField(blank=True)
    property_category = models.CharField(max_length=40, choices=Property.Category.choices, blank=True)
    listing_for = models.CharField(max_length=20, choices=Property.ListingFor.choices, blank=True)
    source = models.CharField(max_length=30, choices=LeadSource.choices, default=LeadSource.MANUAL)
    source_reference = models.CharField(max_length=160, blank=True)
    meta_lead_id = models.CharField(max_length=120, blank=True, unique=True, null=True)
    meta_form_id = models.CharField(max_length=120, blank=True)
    meta_page_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=32, choices=LeadStatus.choices, default=LeadStatus.NEW)
    priority = models.CharField(max_length=20, choices=LeadPriority.choices, default=LeadPriority.MEDIUM)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_crm_leads")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_crm_lead_actions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_crm_leads")
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_leads")
    visit = models.ForeignKey(PropertyVisit, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_leads")
    next_follow_up_at = models.DateTimeField(null=True, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.CharField(max_length=220, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "assigned_to"]),
            models.Index(fields=["company", "source"]),
        ]

    def __str__(self):
        return f"{self.client_name} - {self.get_status_display()}"


class LeadActivity(models.Model):
    class ActivityType(models.TextChoices):
        CREATED = "created", "Created"
        STATUS = "status", "Status Changed"
        ASSIGNED = "assigned", "Assigned"
        NOTE = "note", "Note"
        FOLLOW_UP = "follow_up", "Follow-up"
        VISIT = "visit", "Site Visit"
        META_SYNC = "meta_sync", "Meta Sync"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    old_value = models.CharField(max_length=220, blank=True)
    new_value = models.CharField(max_length=220, blank=True)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LeadFollowUp(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"
        MISSED = "missed", "Missed"
        CANCELLED = "cancelled", "Cancelled"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=160, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "-created_at"]


class MetaLeadSource(models.Model):
    company = models.ForeignKey(CompanyProfile, on_delete=models.CASCADE, related_name="meta_lead_sources")
    page_id = models.CharField(max_length=120)
    page_name = models.CharField(max_length=160, blank=True)
    form_id = models.CharField(max_length=120)
    form_name = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True)
    default_assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    default_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "page_id", "form_id")
        ordering = ["page_name", "form_name"]


class MetaWebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        DUPLICATE = "duplicate", "Duplicate"

    company = models.ForeignKey(CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="meta_webhook_events")
    event_id = models.CharField(max_length=160, unique=True)
    source = models.CharField(max_length=80, default="meta")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
