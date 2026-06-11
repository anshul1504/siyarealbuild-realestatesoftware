from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditLog, Role
from accounts.test_factories import create_company, create_user

from .forms import PropertyForm, PropertyVisitForm
from .models import ColonyPlot, PlotBooking, PlotQuotation, PlotStatusHistory, Property, PropertyDeveloper, PropertyStatusHistory, PropertyVisit
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

    def test_assigned_employee_can_view_assigned_property(self):
        assigned_property = Property.objects.create(
            owner=self.owner,
            assigned_to=self.employee,
            title="Assigned Plot",
            category=Property.Category.PLOT,
            city="Indore",
            address="Assigned",
            area_sqft=900,
        )
        self.client.force_login(self.employee)
        response = self.client.get(reverse("properties:detail", args=[assigned_property.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Plot")

    def test_owner_can_create_developer(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:developer_create"),
            data={
                "name": "Prime Developer",
                "company_name": "Prime Infra",
                "contact_person": "Amit",
                "mobile": "+91 9999999999",
                "email": "dev@example.com",
                "office_address": "Indore",
                "rera_number": "RERA-DEV",
                "notes": "Trusted developer",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("properties:create"))
        self.assertTrue(PropertyDeveloper.objects.filter(company=self.company, name="Prime Developer").exists())

    def test_colony_plot_create_and_edit_records_status_history(self):
        colony = Property.objects.create(
            owner=self.owner,
            title="Royal Colony",
            category=Property.Category.COLONY,
            city="Indore",
            address="Bypass",
            area_sqft=10000,
            total_plots=1,
            base_rate_per_sqft=1500,
            electricity_charge=25000,
            maintenance_charge=10000,
            corner_plc_rate=100,
        )
        self.client.force_login(self.owner)
        create_response = self.client.post(
            reverse("properties:plot_create", args=[colony.id]),
            data={
                "plot_number": "A-01",
                "plot_category": ColonyPlot.PlotCategory.RESIDENTIAL,
                "custom_category": "",
                "block": "A",
                "area_sqft": 1000,
                "length_ft": "50",
                "width_ft": "20",
                "facing": "East",
                "road_width_ft": "30",
                "base_rate": "1500",
                "plc_rate": "100",
                "extra_charges": "35000",
                "price": "0",
                "is_corner": "on",
                "status": ColonyPlot.Status.AVAILABLE,
                "notes": "Corner plot",
            },
        )
        plot = ColonyPlot.objects.get(property=colony, plot_number="A-01")
        self.assertRedirects(create_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(plot.price, 1635000)
        self.assertTrue(PlotStatusHistory.objects.filter(plot=plot, to_status=ColonyPlot.Status.AVAILABLE).exists())
        edit_response = self.client.post(
            reverse("properties:plot_edit", args=[colony.id, plot.id]),
            data={
                "plot_number": "A-01",
                "plot_category": ColonyPlot.PlotCategory.RESIDENTIAL,
                "custom_category": "",
                "block": "A",
                "area_sqft": 1000,
                "length_ft": "50",
                "width_ft": "20",
                "facing": "East",
                "road_width_ft": "30",
                "base_rate": "1500",
                "plc_rate": "100",
                "extra_charges": "35000",
                "price": "1635000",
                "is_corner": "on",
                "status": ColonyPlot.Status.BOOKED,
                "notes": "Booked plot",
            },
        )
        plot.refresh_from_db()
        self.assertRedirects(edit_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(plot.status, ColonyPlot.Status.BOOKED)
        self.assertTrue(PlotStatusHistory.objects.filter(plot=plot, from_status=ColonyPlot.Status.AVAILABLE, to_status=ColonyPlot.Status.BOOKED).exists())

    def test_plot_quotation_and_booking_workflow(self):
        colony = Property.objects.create(owner=self.owner, title="Booking Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road", area_sqft=10000)
        plot = ColonyPlot.objects.create(property=colony, plot_number="B-01", area_sqft=1200, base_rate=2000, plc_rate=100, extra_charges=50000)
        self.client.force_login(self.owner)
        quote_response = self.client.post(
            reverse("properties:plot_quotation_create", args=[colony.id, plot.id]),
            data={
                "client_name": "Buyer One",
                "client_phone": "+91 9000000000",
                "client_email": "buyer@example.com",
                "base_amount": "2400000",
                "plc_amount": "120000",
                "charges_amount": "50000",
                "discount_amount": "10000",
                "valid_until": timezone.now().date().strftime("%Y-%m-%d"),
                "terms": "Valid for 7 days",
                "status": PlotQuotation.Status.SENT,
            },
        )
        quotation = PlotQuotation.objects.get(plot=plot, client_name="Buyer One")
        self.assertRedirects(quote_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(quotation.total_amount, 2560000)
        booking_response = self.client.post(
            reverse("properties:plot_booking_create", args=[colony.id, plot.id]),
            data={
                "quotation": quotation.id,
                "client_name": "Buyer One",
                "client_phone": "+91 9000000000",
                "client_email": "buyer@example.com",
                "booking_date": timezone.now().date().strftime("%Y-%m-%d"),
                "booking_amount": "100000",
                "agreed_rate": "2000",
                "discount_amount": "10000",
                "plc_amount": "120000",
                "charges_amount": "50000",
                "payment_mode": "UPI",
                "status": PlotBooking.Status.BOOKED,
                "note": "Token received",
            },
        )
        plot.refresh_from_db()
        booking = PlotBooking.objects.get(plot=plot, client_name="Buyer One")
        self.assertRedirects(booking_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(plot.status, ColonyPlot.Status.BOOKED)
        self.assertEqual(booking.total_deal_value, 2560000)
