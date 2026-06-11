from django.contrib import admin

from .models import Lead, LeadActivity, LeadAssignmentRule, LeadFollowUp, MetaLeadSource, MetaWebhookEvent


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ("actor", "activity_type", "old_value", "new_value", "note", "created_at")
    can_delete = False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("client_name", "phone", "status", "priority", "source", "assigned_to", "company", "created_at")
    list_filter = ("company", "status", "priority", "source", "created_at")
    search_fields = ("client_name", "phone", "email", "meta_lead_id", "city", "locality")
    inlines = [LeadActivityInline]


@admin.register(LeadFollowUp)
class LeadFollowUpAdmin(admin.ModelAdmin):
    list_display = ("lead", "assigned_to", "due_at", "status", "completed_at")
    list_filter = ("status", "due_at")
    search_fields = ("lead__client_name", "lead__phone", "assigned_to__email")


@admin.register(LeadAssignmentRule)
class LeadAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "source", "city", "property_category", "default_assignee", "default_role", "priority", "is_active")
    list_filter = ("company", "mode", "source", "property_category", "is_active")
    search_fields = ("name", "city", "default_assignee__email")


@admin.register(MetaLeadSource)
class MetaLeadSourceAdmin(admin.ModelAdmin):
    list_display = ("page_name", "form_name", "company", "is_active", "default_assignee", "last_synced_at")
    list_filter = ("company", "is_active")
    search_fields = ("page_id", "page_name", "form_id", "form_name")


@admin.register(MetaWebhookEvent)
class MetaWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "company", "status", "created_at", "processed_at")
    list_filter = ("status", "created_at")
    search_fields = ("event_id", "source", "error_message")
