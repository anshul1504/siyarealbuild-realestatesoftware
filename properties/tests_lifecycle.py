from django.test import TestCase
from django.utils import timezone

from accounts.models import AuditLog, Role
from accounts.test_factories import create_company, create_user

from .forms import PropertyForm, PropertyVisitForm
from .models import Property, PropertyStatusHistory, PropertyVisit
from .services import update_property, update_visit


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
