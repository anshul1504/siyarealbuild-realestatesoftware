from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditLog, Role
from accounts.test_factories import create_company, create_user

from .forms import PropertyForm, PropertyVisitForm
from .models import Property, PropertyStatusHistory, PropertyVisit
from .services import create_property, update_property, update_visit


class PropertyLifecycleTests(TestCase):
    def setUp(self):
        self.company = create_company()
        self.owner = create_user(company=self.company, role=Role.COMPANY_OWNER, email="owner@example.com")
        self.employee = create_user(company=self.company, role=Role.EXECUTIVE, email="employee@example.com")
        self.property = Property.objects.create(owner=self.owner, title="Test Plot", category=Property.Category.PLOT, city="Indore", address="Test", area_sqft=1000)

    def test_property_status_and_assignment_are_recorded(self):
        data = {field: getattr(self.property, field) for field in PropertyForm.Meta.fields if field not in {"assigned_to"}}
        data.update({"status": Property.Status.HOLD, "assigned_to": self.employee.id})
        form = PropertyForm(data, instance=self.property, user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        update_property(form=form, property_obj=self.property, actor=self.owner)
        self.assertTrue(PropertyStatusHistory.objects.filter(property=self.property, to_status=Property.Status.HOLD).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.assigned").exists())

    def test_property_create_is_audited_through_service(self):
        data = {field: (getattr(self.property, field) if getattr(self.property, field) is not None else "") for field in PropertyForm.Meta.fields if field != "assigned_to"}
        data.update({"title": "Created Plot", "price": "1000000", "area_sqft": "1200"})
        form = PropertyForm(data, user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        prop = create_property(form=form, owner=self.owner)

        self.assertTrue(PropertyStatusHistory.objects.filter(property=prop, to_status=Property.Status.AVAILABLE).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.created", target_id=str(prop.id)).exists())

    def test_bulk_status_action_records_history_and_audit(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:bulk_action"),
            data={"property_ids": [str(self.property.id)], "bulk_action": "hold"},
        )

        self.assertRedirects(response, reverse("properties:list"))
        self.property.refresh_from_db()
        self.assertEqual(self.property.status, Property.Status.HOLD)
        self.assertTrue(PropertyStatusHistory.objects.filter(property=self.property, to_status=Property.Status.HOLD).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.status_changed", target_id=str(self.property.id)).exists())

    def test_bulk_delete_action_records_audit_before_delete(self):
        prop_id = self.property.id
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:bulk_action"),
            data={"property_ids": [str(prop_id)], "bulk_action": "delete"},
        )

        self.assertRedirects(response, reverse("properties:list"))
        self.assertFalse(Property.objects.filter(id=prop_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.deleted", target_id=str(prop_id), target_label="Test Plot").exists())

    def test_bulk_action_requires_login(self):
        response = self.client.post(
            reverse("properties:bulk_action"),
            data={"property_ids": [str(self.property.id)], "bulk_action": "hold"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login/", response["Location"])

    def test_booked_visit_is_marked_converted(self):
        visit = PropertyVisit.objects.create(property=self.property, scheduled_by=self.owner, client_name="Client", visit_at=timezone.now())
        form = PropertyVisitForm(
            {"client_name": "Client", "visit_at": timezone.now().strftime("%Y-%m-%dT%H:%M"), "status": PropertyVisit.Status.COMPLETED, "outcome": PropertyVisit.Outcome.BOOKED},
            instance=visit,
            property_obj=self.property,
            user=self.owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        updated = update_visit(form=form, actor=self.owner)
        self.assertIsNotNone(updated.converted_at)
