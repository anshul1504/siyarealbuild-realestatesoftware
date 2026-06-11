import hashlib
import hmac

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditLog, CompanyProfile, NotificationDelivery, Role, UserProfile
from properties.models import Property, PropertyVisit

from .models import AssignmentMode, Lead, LeadActivity, LeadAssignmentRule, LeadFollowUp, LeadSource, LeadStatus, MetaLeadSource, MetaWebhookEvent
from .services import ingest_meta_payload


class CrmLeadWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = CompanyProfile.objects.create(name="Siya CRM")
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.manager = User.objects.create_user(username="manager@example.com", email="manager@example.com")
        self.executive = User.objects.create_user(username="executive@example.com", email="executive@example.com")
        self.tl = User.objects.create_user(username="tl@example.com", email="tl@example.com")
        self.other = User.objects.create_user(username="other@example.com", email="other@example.com")
        self.external = User.objects.create_user(username="external@example.com", email="external@example.com")
        UserProfile.objects.create(user=self.owner, company=self.company, role=Role.COMPANY_OWNER)
        UserProfile.objects.create(user=self.manager, company=self.company, role=Role.MANAGER)
        UserProfile.objects.create(user=self.tl, company=self.company, role=Role.TL)
        UserProfile.objects.create(user=self.executive, company=self.company, role=Role.EXECUTIVE)
        UserProfile.objects.create(user=self.other, company=self.company, role=Role.EXECUTIVE)
        UserProfile.objects.create(user=self.external, role=Role.MANAGER)

    def test_owner_can_create_lead_and_activity_is_recorded(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("crm:lead_create"),
            data={
                "client_name": "Meta Client",
                "phone": "+91 9999999999",
                "email": "client@example.com",
                "city": "Indore",
                "source": LeadSource.MANUAL,
                "priority": "high",
                "assigned_to": self.executive.id,
            },
        )
        lead = Lead.objects.get(client_name="Meta Client")
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.assigned_to, self.executive)
        self.assertEqual(lead.activities.filter(activity_type=LeadActivity.ActivityType.CREATED).count(), 1)
        self.assertTrue(NotificationDelivery.objects.filter(category="crm_assignment", recipient=self.executive.email).exists())

    def test_assignment_rule_routes_new_manual_lead(self):
        LeadAssignmentRule.objects.create(
            company=self.company,
            name="Indore leads",
            mode=AssignmentMode.CITY,
            city="Indore",
            default_assignee=self.executive,
            priority=1,
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("crm:lead_create"),
            data={
                "client_name": "Rule Buyer",
                "phone": "+91 9000000000",
                "city": "Indore",
                "source": LeadSource.MANUAL,
                "priority": "medium",
            },
        )
        lead = Lead.objects.get(client_name="Rule Buyer")
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.assigned_to, self.executive)

    def test_round_robin_assignment_rule_rotates_by_role(self):
        LeadAssignmentRule.objects.create(company=self.company, name="Round robin executives", mode=AssignmentMode.ROUND_ROBIN, default_role=Role.EXECUTIVE, priority=1)
        self.client.force_login(self.manager)
        for index in range(2):
            self.client.post(
                reverse("crm:lead_create"),
                data={"client_name": f"Round Buyer {index}", "phone": f"+91 900000000{index}", "source": LeadSource.MANUAL, "priority": "medium"},
            )
        self.assertEqual(Lead.objects.get(client_name="Round Buyer 0").assigned_to, self.executive)
        self.assertEqual(Lead.objects.get(client_name="Round Buyer 1").assigned_to, self.other)

    def test_workload_assignment_rule_picks_least_loaded_member(self):
        Lead.objects.create(company=self.company, client_name="Existing Load", phone="+91 9111111111", assigned_to=self.executive)
        LeadAssignmentRule.objects.create(company=self.company, name="Least loaded executives", mode=AssignmentMode.WORKLOAD, default_role=Role.EXECUTIVE, priority=1)
        self.client.force_login(self.manager)
        self.client.post(
            reverse("crm:lead_create"),
            data={"client_name": "Workload Buyer", "phone": "+91 9222222222", "source": LeadSource.MANUAL, "priority": "medium"},
        )
        self.assertEqual(Lead.objects.get(client_name="Workload Buyer").assigned_to, self.other)

    def test_owner_can_create_assignment_rule(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("crm:assignment_rule_create"),
            data={
                "name": "Meta default",
                "mode": AssignmentMode.SOURCE,
                "source": LeadSource.META,
                "city": "",
                "property_category": "",
                "default_assignee": self.manager.id,
                "default_role": "",
                "priority": 10,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("crm:assignment_rule_list"))
        self.assertTrue(LeadAssignmentRule.objects.filter(name="Meta default", default_assignee=self.manager).exists())

    def test_owner_can_edit_assignment_rule(self):
        rule = LeadAssignmentRule.objects.create(company=self.company, name="Old rule", mode=AssignmentMode.SOURCE, source=LeadSource.META, default_assignee=self.manager, priority=5)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("crm:assignment_rule_edit", args=[rule.id]),
            data={
                "name": "Updated rule",
                "mode": AssignmentMode.CITY,
                "source": "",
                "city": "Indore",
                "property_category": "",
                "default_assignee": self.executive.id,
                "default_role": "",
                "priority": 2,
                "is_active": "on",
            },
        )
        rule.refresh_from_db()
        self.assertRedirects(response, reverse("crm:assignment_rule_list"))
        self.assertEqual(rule.name, "Updated rule")
        self.assertEqual(rule.city, "Indore")
        self.assertEqual(rule.default_assignee, self.executive)

    def test_manager_can_archive_and_restore_lead(self):
        lead = Lead.objects.create(company=self.company, client_name="Archive Buyer", phone="+91 9333333333", assigned_to=self.manager)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("crm:lead_archive", args=[lead.id]), {"reason": "Duplicate enquiry"})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_list"))
        self.assertTrue(lead.is_archived)
        self.assertEqual(lead.archive_reason, "Duplicate enquiry")
        list_response = self.client.get(reverse("crm:lead_list"))
        self.assertNotContains(list_response, "Archive Buyer")
        archived_response = self.client.get(reverse("crm:lead_list"), {"archived": "1"})
        self.assertContains(archived_response, "Archive Buyer")
        response = self.client.post(reverse("crm:lead_restore", args=[lead.id]))
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertFalse(lead.is_archived)

    def test_executive_sees_only_assigned_or_created_leads(self):
        assigned = Lead.objects.create(company=self.company, client_name="Assigned", assigned_to=self.executive)
        Lead.objects.create(company=self.company, client_name="Other", assigned_to=self.other)
        self.client.force_login(self.executive)
        response = self.client.get(reverse("crm:lead_list"))
        visible_ids = {lead.id for lead in response.context["leads"]}
        self.assertContains(response, assigned.client_name)
        self.assertIn(assigned.id, visible_ids)
        self.assertNotIn(Lead.objects.get(client_name="Other").id, visible_ids)

    def test_team_lead_sees_only_assigned_or_created_leads(self):
        assigned = Lead.objects.create(company=self.company, client_name="TL Assigned", assigned_to=self.tl)
        Lead.objects.create(company=self.company, client_name="Manager Only", assigned_to=self.manager)
        self.client.force_login(self.tl)
        response = self.client.get(reverse("crm:lead_list"))
        visible_ids = {lead.id for lead in response.context["leads"]}
        self.assertIn(assigned.id, visible_ids)
        self.assertNotIn(Lead.objects.get(client_name="Manager Only").id, visible_ids)

    def test_team_lead_sees_reporting_manager_team_leads(self):
        self.tl.profile.employee_code = "TL-001"
        self.tl.profile.save(update_fields=["employee_code"])
        self.executive.profile.reporting_manager = "TL-001"
        self.executive.profile.save(update_fields=["reporting_manager"])
        team_lead = Lead.objects.create(company=self.company, client_name="Team Lead", assigned_to=self.executive)
        other_lead = Lead.objects.create(company=self.company, client_name="Other Team", assigned_to=self.other)
        self.client.force_login(self.tl)
        response = self.client.get(reverse("crm:lead_list"))
        visible_ids = {lead.id for lead in response.context["leads"]}
        self.assertIn(team_lead.id, visible_ids)
        self.assertNotIn(other_lead.id, visible_ids)
        detail_response = self.client.get(reverse("crm:lead_detail", args=[team_lead.id]))
        self.assertEqual(detail_response.status_code, 200)

    def test_status_update_creates_activity(self):
        lead = Lead.objects.create(company=self.company, client_name="Buyer", assigned_to=self.executive)
        self.client.force_login(self.executive)
        response = self.client.post(reverse("crm:lead_status_update", args=[lead.id]), {"status": LeadStatus.CONTACTED, "note": "Called client."})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.status, LeadStatus.CONTACTED)
        self.assertTrue(lead.activities.filter(activity_type=LeadActivity.ActivityType.STATUS, note="Called client.").exists())
        self.assertTrue(AuditLog.objects.filter(action="crm.status", target_id=str(lead.id)).exists())

    def test_lost_and_closed_status_require_note(self):
        lead = Lead.objects.create(company=self.company, client_name="Lifecycle Buyer", phone="+91 1111111112", assigned_to=self.executive)
        self.client.force_login(self.executive)
        response = self.client.post(reverse("crm:lead_status_update", args=[lead.id]), {"status": LeadStatus.LOST, "note": ""})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertNotEqual(lead.status, LeadStatus.LOST)
        response = self.client.post(reverse("crm:lead_status_update", args=[lead.id]), {"status": LeadStatus.LOST, "note": "Budget mismatch"})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.status, LeadStatus.LOST)
        self.assertEqual(lead.lost_reason, "Budget mismatch")

    def test_lead_form_requires_contact_and_valid_budget(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("crm:lead_create"),
            data={
                "client_name": "Invalid Buyer",
                "budget_min": "2000000",
                "budget_max": "1000000",
                "source": LeadSource.MANUAL,
                "priority": "medium",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], None, "Add at least one client contact: phone or email.")
        self.assertFormError(response.context["form"], "budget_max", "Maximum budget cannot be less than minimum budget.")

    def test_lead_edit_updates_details_and_records_activity(self):
        lead = Lead.objects.create(company=self.company, client_name="Old Buyer", phone="+91 1111111111", assigned_to=self.executive)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("crm:lead_edit", args=[lead.id]),
            data={
                "client_name": "Updated Buyer",
                "phone": "+91 2222222222",
                "email": "",
                "city": "Indore",
                "locality": "",
                "budget_min": "",
                "budget_max": "",
                "requirement": "Needs 3 BHK",
                "property_category": "",
                "listing_for": "",
                "source": LeadSource.MANUAL,
                "priority": "urgent",
                "assigned_to": self.executive.id,
                "property": "",
                "notes": "VIP",
            },
        )
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        lead.refresh_from_db()
        self.assertEqual(lead.client_name, "Updated Buyer")
        self.assertEqual(lead.priority, "urgent")
        self.assertTrue(lead.activities.filter(new_value="details_updated").exists())

    def test_executive_cannot_directly_view_or_edit_unassigned_lead(self):
        lead = Lead.objects.create(company=self.company, client_name="Private Buyer", phone="+91 3333333333")
        self.client.force_login(self.executive)
        detail_response = self.client.get(reverse("crm:lead_detail", args=[lead.id]))
        edit_response = self.client.post(reverse("crm:lead_edit", args=[lead.id]), {"client_name": "Changed", "phone": "+91 4444444444", "source": LeadSource.MANUAL, "priority": "medium"})
        lead.refresh_from_db()
        self.assertRedirects(detail_response, reverse("crm:lead_list"))
        self.assertRedirects(edit_response, reverse("crm:lead_list"))
        self.assertEqual(lead.client_name, "Private Buyer")

    def test_user_without_company_cannot_access_lead(self):
        lead = Lead.objects.create(company=self.company, client_name="Scoped Buyer", phone="+91 5555555555")
        self.client.force_login(self.external)
        response = self.client.get(reverse("crm:lead_detail", args=[lead.id]))
        self.assertRedirects(response, reverse("crm:lead_list"))

    def test_dashboard_and_followup_completion_work(self):
        lead = Lead.objects.create(company=self.company, client_name="Follow Buyer", assigned_to=self.executive)
        followup = LeadFollowUp.objects.create(lead=lead, assigned_to=self.executive, due_at=timezone.now(), note="Call")
        self.client.force_login(self.executive)
        self.assertEqual(self.client.get(reverse("crm:dashboard")).status_code, 200)
        schedule_response = self.client.post(
            reverse("crm:lead_followup_create", args=[lead.id]),
            {"assigned_to": self.executive.id, "due_at": timezone.now().strftime("%Y-%m-%dT%H:%M"), "note": "Second call"},
        )
        self.assertRedirects(schedule_response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertTrue(NotificationDelivery.objects.filter(category="crm_followup", recipient=self.executive.email).exists())
        response = self.client.post(reverse("crm:followup_complete", args=[followup.id]), {"outcome": "Interested"})
        followup.refresh_from_db()
        self.assertRedirects(response, reverse("crm:followup_list"))
        self.assertEqual(followup.status, LeadFollowUp.Status.DONE)
        self.assertTrue(lead.activities.filter(activity_type=LeadActivity.ActivityType.FOLLOW_UP, new_value="completed").exists())

    def test_manager_can_assign_and_add_note(self):
        lead = Lead.objects.create(company=self.company, client_name="Assign Buyer")
        self.client.force_login(self.manager)
        response = self.client.post(reverse("crm:lead_assign", args=[lead.id]), {"assigned_to": self.executive.id, "note": "Assign to sales"})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.assigned_to, self.executive)
        response = self.client.post(reverse("crm:lead_note_create", args=[lead.id]), {"note": "Client wants corner plot."})
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertTrue(lead.activities.filter(activity_type=LeadActivity.ActivityType.NOTE, note="Client wants corner plot.").exists())

    def test_bulk_action_kanban_reports_and_export_work(self):
        lead = Lead.objects.create(company=self.company, client_name="Bulk Buyer")
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("crm:lead_kanban")).status_code, 200)
        self.assertEqual(self.client.get(reverse("crm:reports")).status_code, 200)
        export_response = self.client.get(reverse("crm:lead_export"))
        self.assertEqual(export_response.status_code, 200)
        response = self.client.post(
            reverse("crm:lead_bulk_action"),
            {"lead_ids": str(lead.id), "action": "assign", "assigned_to": self.executive.id, "status": "", "priority": "", "note": "Bulk assign"},
        )
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_list"))
        self.assertEqual(lead.assigned_to, self.executive)

    def test_property_match_and_visit_schedule_from_lead(self):
        property_obj = Property.objects.create(
            owner=self.owner,
            title="Premium Plot",
            city="Indore",
            address="MR 10",
            price=2500000,
        )
        lead = Lead.objects.create(company=self.company, client_name="Visit Buyer", phone="+91 6666666666")
        self.client.force_login(self.manager)
        response = self.client.post(reverse("crm:lead_property_match", args=[lead.id]), {"property": property_obj.id, "note": "Budget match"})
        lead.refresh_from_db()
        self.assertRedirects(response, reverse("crm:lead_detail", args=[lead.id]))
        self.assertEqual(lead.property, property_obj)
        self.assertEqual(lead.status, LeadStatus.PROPERTY_MATCHED)
        response = self.client.post(
            reverse("crm:lead_visit_schedule", args=[lead.id]),
            {"property": property_obj.id, "visit_at": timezone.now().strftime("%Y-%m-%dT%H:%M"), "assigned_employee": self.executive.id, "notes": "Visit planned"},
        )
        lead.refresh_from_db()
        visit = PropertyVisit.objects.get(client_name="Visit Buyer")
        self.assertRedirects(response, reverse("properties:visit_detail", args=[visit.id]))
        self.assertEqual(lead.visit, visit)
        self.assertEqual(lead.status, LeadStatus.VISIT_SCHEDULED)

    def test_meta_ingest_dedupes_by_meta_lead_id(self):
        source = MetaLeadSource.objects.create(company=self.company, page_id="page-1", form_id="form-1", default_assignee=self.manager)
        lead, event = ingest_meta_payload(
            source=source,
            payload={"event_id": "event-1", "leadgen_id": "lead-1"},
            fetched_data={"client_name": "Meta Buyer", "phone": "+91 8888888888", "email": "meta@example.com"},
        )
        duplicate, duplicate_event = ingest_meta_payload(source=source, payload={"event_id": "event-2", "leadgen_id": "lead-1"}, fetched_data={"client_name": "Meta Buyer"})
        self.assertIsNotNone(lead)
        self.assertEqual(lead.assigned_to, self.manager)
        self.assertEqual(event.status, "processed")
        self.assertTrue(NotificationDelivery.objects.filter(category="crm_meta_lead", recipient=self.manager.email).exists())
        self.assertIsNone(duplicate)
        self.assertEqual(duplicate_event.status, "duplicate")

    def test_meta_ingest_uses_mapping_and_dedupes_by_phone(self):
        source = MetaLeadSource.objects.create(
            company=self.company,
            page_id="page-map",
            form_id="form-map",
            default_assignee=self.manager,
            field_mapping={"client_name": "buyer_name", "phone": "mobile"},
        )
        Lead.objects.create(company=self.company, client_name="Existing Buyer", phone="+91 9876543210")
        lead, event = ingest_meta_payload(
            source=source,
            payload={"event_id": "event-map-1", "leadgen_id": "lead-map-1"},
            fetched_data={"buyer_name": "Mapped Buyer", "mobile": "9876543210"},
        )
        self.assertIsNone(lead)
        self.assertEqual(event.status, "duplicate")
        lead, event = ingest_meta_payload(
            source=source,
            payload={"event_id": "event-map-2", "leadgen_id": "lead-map-2"},
            fetched_data={"buyer_name": "Mapped Buyer 2", "mobile": "9123456789"},
        )
        self.assertIsNotNone(lead)
        self.assertEqual(lead.client_name, "Mapped Buyer 2")
        self.assertEqual(lead.phone, "9123456789")

    def test_meta_ingest_uses_assignment_rule(self):
        LeadAssignmentRule.objects.create(company=self.company, name="Meta to executive", mode=AssignmentMode.SOURCE, source=LeadSource.META, default_assignee=self.executive, priority=1)
        source = MetaLeadSource.objects.create(company=self.company, page_id="page-rule", form_id="form-rule", default_assignee=self.manager)
        lead, event = ingest_meta_payload(
            source=source,
            payload={"event_id": "event-rule-1", "leadgen_id": "lead-rule-1"},
            fetched_data={"client_name": "Rule Meta Buyer", "phone": "+91 8111111111"},
        )
        self.assertEqual(event.status, "processed")
        self.assertEqual(lead.assigned_to, self.executive)

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="verify", META_PAGE_ACCESS_TOKEN="page-token", META_APP_SECRET="secret", META_GRAPH_VERSION="v21.0")
    def test_owner_can_view_meta_health_and_edit_source(self):
        source = MetaLeadSource.objects.create(company=self.company, page_id="page-old", form_id="form-old", default_assignee=self.manager)
        MetaWebhookEvent.objects.create(company=self.company, event_id="failed-1", status=MetaWebhookEvent.Status.FAILED, error_message="No source")
        self.client.force_login(self.owner)
        health = self.client.get(reverse("crm:meta_health"))
        self.assertEqual(health.status_code, 200)
        self.assertContains(health, "Configured")
        self.assertContains(health, "v21.0")
        response = self.client.post(
            reverse("crm:meta_source_edit", args=[source.id]),
            data={
                "page_id": "page-new",
                "page_name": "Main Page",
                "form_id": "form-new",
                "form_name": "Buyer Form",
                "default_assignee": self.executive.id,
                "is_active": "on",
                "field_mapping": '{"client_name": "full_name"}',
            },
        )
        source.refresh_from_db()
        self.assertRedirects(response, reverse("crm:meta_source_list"))
        self.assertEqual(source.page_id, "page-new")
        self.assertEqual(source.default_assignee, self.executive)

    def test_manager_cannot_view_owner_meta_health(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("crm:meta_health"))
        self.assertRedirects(response, reverse("crm:dashboard"))

    def test_channel_partner_has_dedicated_lead_view(self):
        User = get_user_model()
        partner = User.objects.create_user(username="partner@example.com", email="partner@example.com")
        UserProfile.objects.create(user=partner, company=self.company, role=Role.CHANNEL_PARTNER)
        assigned = Lead.objects.create(company=self.company, client_name="Partner Buyer", assigned_to=partner, source=LeadSource.REFERRAL)
        Lead.objects.create(company=self.company, client_name="Hidden Buyer", assigned_to=self.executive)
        LeadFollowUp.objects.create(lead=assigned, assigned_to=partner, due_at=timezone.now(), note="Partner call")
        self.client.force_login(partner)
        response = self.client.get(reverse("crm:partner_leads"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Partner Buyer")
        self.assertNotContains(response, "Hidden Buyer")

    def test_non_partner_is_redirected_from_partner_leads(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("crm:partner_leads"))
        self.assertRedirects(response, reverse("crm:dashboard"))

    @override_settings(META_WEBHOOK_VERIFY_TOKEN="verify-me")
    def test_meta_webhook_verification_and_ingest(self):
        MetaLeadSource.objects.create(company=self.company, page_id="page-1", form_id="form-1", default_assignee=self.manager)
        verify = self.client.get(reverse("crm:meta_webhook"), {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "123"})
        self.assertEqual(verify.content, b"123")
        response = self.client.post(
            reverse("crm:meta_webhook"),
            data={
                "entry": [
                    {
                        "id": "page-1",
                        "changes": [
                            {
                                "value": {
                                    "page_id": "page-1",
                                    "form_id": "form-1",
                                    "leadgen_id": "lead-webhook-1",
                                    "full_name": "Webhook Buyer",
                                    "phone_number": "+91 7777777777",
                                }
                            }
                        ],
                    }
                ]
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Lead.objects.filter(meta_lead_id="lead-webhook-1", client_name="Webhook Buyer").exists())

    def test_owner_can_reprocess_failed_meta_event(self):
        event = MetaWebhookEvent.objects.create(
            company=self.company,
            event_id="retry-lead-1",
            payload={"form_id": "form-retry", "page_id": "page-retry", "leadgen_id": "retry-lead-1", "full_name": "Retry Buyer", "phone_number": "+91 8222222222"},
            status=MetaWebhookEvent.Status.FAILED,
            error_message="No active Meta source mapping.",
        )
        MetaLeadSource.objects.create(company=self.company, page_id="page-retry", form_id="form-retry", default_assignee=self.manager)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("crm:meta_event_reprocess", args=[event.id]))
        self.assertRedirects(response, reverse("crm:reports"))
        self.assertTrue(Lead.objects.filter(meta_lead_id="retry-lead-1", client_name="Retry Buyer").exists())

    @override_settings(META_APP_SECRET="secret")
    def test_meta_webhook_rejects_invalid_signature(self):
        response = self.client.post(reverse("crm:meta_webhook"), data={"entry": []}, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=bad")
        self.assertEqual(response.status_code, 403)

    @override_settings(META_APP_SECRET="secret")
    def test_meta_webhook_accepts_valid_signature(self):
        body = b'{"entry":[]}'
        signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        response = self.client.post(reverse("crm:meta_webhook"), data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}")
        self.assertEqual(response.status_code, 200)
