from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import AuditLog, Role
from accounts.test_factories import create_company, create_user

from .forms import ColonyPlotForm, PropertyForm, PropertyVisitForm
from .models import BookingAgreement, BookingInstallment, BookingPayment, ColonyPlot, MISReportSnapshot, PlotBooking, PlotQuotation, PlotStatusHistory, Property, PropertyCommissionPayout, PropertyCommissionRule, PropertyDeveloper, PropertyDocument, PropertyPhoto, PropertyStatusHistory, PropertyVisit
from .services import create_property, create_plot, update_property, update_visit


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

    def test_colony_master_does_not_require_overall_area(self):
        data = {field: (getattr(self.property, field) if getattr(self.property, field) is not None else "") for field in PropertyForm.Meta.fields if field != "assigned_to"}
        data.update(
            {
                "title": "Colony Without Master Area",
                "category": Property.Category.COLONY,
                "area_sqft": "",
                "colony_name": "Colony Without Master Area",
                "development_name": "Phase 1",
                "development_status": "under_development",
                "total_plots": 1,
                "residential_rate_per_sqft": 2000,
                "commercial_rate_per_sqft": 2500,
                "lig_rate_per_sqft": 1800,
                "ews_rate_per_sqft": 1600,
            }
        )
        form = PropertyForm(data, user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

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

    def test_bulk_archive_action_records_audit_and_preserves_property(self):
        prop_id = self.property.id
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:bulk_action"),
            data={"property_ids": [str(prop_id)], "bulk_action": "archive"},
        )

        self.assertRedirects(response, reverse("properties:list"))
        self.assertTrue(Property.objects.filter(id=prop_id, is_archived=True).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.archived", target_id=str(prop_id), target_label="Test Plot").exists())

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

    def test_archived_property_is_hidden_and_owner_can_restore(self):
        self.property.is_archived = True
        self.property.archived_by = self.owner
        self.property.save(update_fields=["is_archived", "archived_by", "updated_at"])
        self.client.force_login(self.owner)

        list_response = self.client.get(reverse("properties:list"))
        self.assertNotContains(list_response, "Test Plot")
        archived_response = self.client.get(reverse("properties:list") + "?archived=1")
        self.assertContains(archived_response, "Test Plot")
        restore_response = self.client.post(reverse("properties:restore", args=[self.property.id]))

        self.assertRedirects(restore_response, reverse("properties:detail", args=[self.property.id]))
        self.property.refresh_from_db()
        self.assertFalse(self.property.is_archived)
        self.assertTrue(AuditLog.objects.filter(action="property.restored", target_id=str(self.property.id)).exists())

    def test_only_owner_can_permanently_delete_property(self):
        property_id = self.property.id
        manager = create_user(company=self.company, role=Role.MANAGER, email="delete-manager@example.com")
        self.client.force_login(manager)
        denied = self.client.post(reverse("properties:delete", args=[property_id]))
        self.assertTrue(Property.objects.filter(id=property_id).exists())
        self.assertRedirects(denied, reverse("properties:detail", args=[property_id]))

        self.client.force_login(self.owner)
        response = self.client.post(reverse("properties:delete", args=[property_id]))
        self.assertRedirects(response, reverse("properties:list"))
        self.assertFalse(Property.objects.filter(id=property_id).exists())
        self.assertTrue(AuditLog.objects.filter(action="property.deleted", target_id=str(property_id), target_label="Test Plot").exists())

    def test_manager_can_export_properties_but_executive_cannot(self):
        manager = create_user(company=self.company, role=Role.MANAGER, email="manager@example.com")
        self.client.force_login(manager)
        response = self.client.get(reverse("properties:export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Test Plot", response.content.decode())

        self.client.force_login(self.employee)
        denied_response = self.client.get(reverse("properties:export"))
        self.assertRedirects(denied_response, reverse("properties:list"))

    def test_owner_mis_report_can_be_saved_and_exported(self):
        colony = Property.objects.create(owner=self.owner, title="MIS Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road", area_sqft=10000)
        plot = ColonyPlot.objects.create(property=colony, plot_number="MIS-01", area_sqft=1000, base_rate=1500, price=1500000, status=ColonyPlot.Status.BOOKED)
        booking = PlotBooking.objects.create(
            plot=plot,
            quotation=None,
            client_name="MIS Buyer",
            client_phone="+91 9000000001",
            booking_date=timezone.now().date(),
            booking_amount=100000,
            total_deal_value=1500000,
            paid_amount=100000,
            balance_amount=1400000,
            created_by=self.owner,
        )
        BookingPayment.objects.create(booking=booking, received_on=timezone.now().date(), amount=100000, received_by=self.owner)
        self.client.force_login(self.owner)

        url = reverse("properties:owner_mis_report")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner MIS Report")
        self.assertContains(response, "Total Deal Value")
        self.assertContains(response, "Commission Payable")

        save_response = self.client.post(url)
        self.assertRedirects(save_response, url)
        self.assertTrue(MISReportSnapshot.objects.filter(company=self.company, generated_by=self.owner, title__contains="Owner MIS").exists())

        export_response = self.client.get(url + "?export=csv")
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "text/csv")
        self.assertIn("Total Deal Value", export_response.content.decode())

        self.client.force_login(self.employee)
        denied_response = self.client.get(url)
        self.assertEqual(denied_response.status_code, 403)

    def test_assigned_employee_can_view_assigned_visit(self):
        visit = PropertyVisit.objects.create(
            property=self.property,
            scheduled_by=self.owner,
            assigned_employee=self.employee,
            client_name="Assigned Client",
            visit_at=timezone.now(),
        )
        self.client.force_login(self.employee)
        response = self.client.get(reverse("properties:visit_detail", args=[visit.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Client")

    def test_visit_image_upload_and_role_access(self):
        image_bytes = b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:visit_create", args=[self.property.id]),
            data={
                "client_name": "Photo Client",
                "client_phone": "+91 9000000000",
                "client_email": "photo@example.com",
                "visit_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "assigned_employee": self.employee.id,
                "status": PropertyVisit.Status.SCHEDULED,
                "outcome": PropertyVisit.Outcome.PENDING,
                "notes": "Site image captured",
                "image": SimpleUploadedFile("site.gif", image_bytes, content_type="image/gif"),
            },
        )

        visit = PropertyVisit.objects.get(client_name="Photo Client")
        self.assertRedirects(response, reverse("properties:visit_detail", args=[visit.id]))
        self.assertTrue(visit.image.name.startswith("properties/visits/"))
        detail_response = self.client.get(reverse("properties:visit_detail", args=[visit.id]))
        self.assertContains(detail_response, "Site Photo")
        self.assertContains(detail_response, "View Image")

        self.client.force_login(self.employee)
        edit_response = self.client.post(
            reverse("properties:visit_edit", args=[visit.id]),
            data={
                "client_name": "Photo Client Updated",
                "client_phone": "+91 9000000000",
                "client_email": "photo@example.com",
                "visit_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "assigned_employee": self.employee.id,
                "status": PropertyVisit.Status.COMPLETED,
                "outcome": PropertyVisit.Outcome.INTERESTED,
                "notes": "Updated with assigned employee access",
                "image": SimpleUploadedFile("assigned.gif", image_bytes, content_type="image/gif"),
            },
        )

        self.assertRedirects(edit_response, reverse("properties:visit_detail", args=[visit.id]))
        visit.refresh_from_db()
        self.assertEqual(visit.client_name, "Photo Client Updated")
        self.assertIn("assigned", visit.image.name)

        other_employee = create_user(company=self.company, role=Role.EXECUTIVE, email="other-employee@example.com")
        self.client.force_login(other_employee)
        denied_response = self.client.post(
            reverse("properties:visit_edit", args=[visit.id]),
            data={
                "client_name": "Blocked Update",
                "visit_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "status": PropertyVisit.Status.CANCELLED,
                "outcome": PropertyVisit.Outcome.NOT_INTERESTED,
            },
        )
        self.assertEqual(denied_response.status_code, 404)

    def test_visit_workspace_lists_visible_visits(self):
        PropertyVisit.objects.create(
            property=self.property,
            scheduled_by=self.owner,
            assigned_employee=self.employee,
            client_name="Workspace Client",
            visit_at=timezone.now(),
        )
        self.client.force_login(self.employee)
        response = self.client.get(reverse("properties:visit_index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visit Workspace")
        self.assertContains(response, "Workspace Client")

    def test_tl_cannot_create_property_by_direct_url(self):
        tl = create_user(company=self.company, role=Role.TL, email="tl@example.com")
        self.client.force_login(tl)
        response = self.client.get(reverse("properties:create"))

        self.assertRedirects(response, reverse("properties:list"))

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

    def test_owner_can_manage_property_media(self):
        first = PropertyPhoto.objects.create(
            property=self.property,
            image=SimpleUploadedFile("one.jpg", b"one", content_type="image/jpeg"),
            is_primary=True,
        )
        second = PropertyPhoto.objects.create(
            property=self.property,
            image=SimpleUploadedFile("two.jpg", b"two", content_type="image/jpeg"),
        )
        document = PropertyDocument.objects.create(
            property=self.property,
            document_type=PropertyDocument.DocumentType.RERA,
            title="RERA",
            file=SimpleUploadedFile("rera.pdf", b"pdf", content_type="application/pdf"),
        )
        self.client.force_login(self.owner)

        cover_response = self.client.post(reverse("properties:photo_primary", args=[self.property.id, second.id]))
        self.assertRedirects(cover_response, reverse("properties:detail", args=[self.property.id]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

        photo_delete_response = self.client.post(reverse("properties:photo_delete", args=[self.property.id, second.id]))
        self.assertRedirects(photo_delete_response, reverse("properties:detail", args=[self.property.id]))
        self.assertFalse(PropertyPhoto.objects.filter(id=second.id).exists())
        first.refresh_from_db()
        self.assertTrue(first.is_primary)

        upload_response = self.client.post(
            reverse("properties:cover_photo_upload", args=[self.property.id]),
            data={"cover_photo": SimpleUploadedFile("cover.jpg", b"cover", content_type="image/jpeg")},
        )
        self.assertRedirects(upload_response, reverse("properties:detail", args=[self.property.id]))
        self.assertEqual(self.property.photos.filter(is_primary=True).count(), 1)
        self.assertTrue(self.property.photos.get(is_primary=True).image.name.rsplit("/", 1)[-1].startswith("cover"))

        document_delete_response = self.client.post(reverse("properties:document_delete", args=[self.property.id, document.id]))
        self.assertRedirects(document_delete_response, reverse("properties:detail", args=[self.property.id]))
        self.assertFalse(PropertyDocument.objects.filter(id=document.id).exists())

    def test_owner_can_review_property_document_and_sync_legal_status(self):
        document = PropertyDocument.objects.create(
            property=self.property,
            document_type=PropertyDocument.DocumentType.LEGAL,
            title="Legal Search",
            file=SimpleUploadedFile("legal.pdf", b"pdf", content_type="application/pdf"),
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:document_review", args=[self.property.id, document.id]),
            data={
                "document_number": "LEGAL-001",
                "issued_on": timezone.now().date().strftime("%Y-%m-%d"),
                "expires_on": "",
                "review_status": PropertyDocument.ReviewStatus.VERIFIED,
                "review_note": "Verified by legal team",
            },
        )

        self.assertRedirects(response, reverse("properties:detail", args=[self.property.id]))
        document.refresh_from_db()
        self.property.refresh_from_db()
        self.assertEqual(document.review_status, PropertyDocument.ReviewStatus.VERIFIED)
        self.assertEqual(document.reviewed_by, self.owner)
        self.assertEqual(self.property.legal_status, Property.LegalStatus.CLEAR)
        self.assertTrue(AuditLog.objects.filter(action="property_document.reviewed", target_id=str(self.property.id)).exists())

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
            residential_rate_per_sqft=1500,
            electricity_charge=20,
            maintenance_charge=15,
            corner_plc_rate=10,
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
                "facing": ColonyPlot.Facing.EAST,
                "road_width_ft": "30",
                "base_rate": "1",
                "plc_rate": "1",
                "extra_charges": "1",
                "price": "0",
                "is_corner": "on",
                "status": ColonyPlot.Status.AVAILABLE,
                "notes": "Corner plot",
            },
        )
        plot = ColonyPlot.objects.get(property=colony, plot_number="A-01")
        self.assertRedirects(create_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(plot.price, 1685000)
        self.assertEqual(plot.base_rate, 1500)
        self.assertEqual(plot.extra_charges, 35000)
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
                "facing": ColonyPlot.Facing.EAST,
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
        PropertyCommissionRule.objects.create(property=colony, role=Role.EXECUTIVE, calculation_type=PropertyCommissionRule.CalculationType.PERCENTAGE, value=2)
        self.client.force_login(self.owner)
        detail_response = self.client.get(reverse("properties:detail", args=[colony.id]))
        self.assertContains(detail_response, "Commission Rules")
        self.assertContains(detail_response, "Executive")
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
                "coupon_code": "WELCOME5000",
                "coupon_discount_amount": "5000",
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
        self.assertEqual(booking.coupon_code, "WELCOME5000")
        self.assertEqual(booking.total_deal_value, 2555000)
        self.assertEqual(booking.commission_amount, 48000)
        self.assertEqual(booking.paid_amount, 100000)
        self.assertEqual(booking.balance_amount, 2455000)
        payout = PropertyCommissionPayout.objects.get(booking=booking, role=Role.EXECUTIVE)
        self.assertEqual(payout.amount, 48000)
        self.assertEqual(payout.status, PropertyCommissionPayout.Status.UNPAID)
        self.assertTrue(BookingInstallment.objects.filter(booking=booking, title="Booking amount", status=BookingInstallment.Status.PAID).exists())
        self.assertTrue(BookingPayment.objects.filter(booking=booking, amount=100000).exists())

        payout_response = self.client.post(
            reverse("properties:booking_commission_payout_update", args=[colony.id, plot.id, booking.id, payout.id]),
            data={"status": PropertyCommissionPayout.Status.PAID, "payout_reference": "UPI-COMM-1", "note": "Paid to executive"},
        )
        self.assertRedirects(payout_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        payout.refresh_from_db()
        self.assertEqual(payout.status, PropertyCommissionPayout.Status.PAID)
        self.assertEqual(payout.payout_reference, "UPI-COMM-1")
        self.assertEqual(payout.paid_by, self.owner)
        self.assertIsNotNone(payout.paid_at)
        self.assertTrue(AuditLog.objects.filter(action="property_commission.payout_updated", target_id=str(colony.id)).exists())

        installment_response = self.client.post(
            reverse("properties:booking_installment_create", args=[colony.id, plot.id, booking.id]),
            data={
                "title": "Registry payment",
                "due_date": timezone.now().date().strftime("%Y-%m-%d"),
                "amount": "500000",
                "note": "Due before registry",
            },
        )
        installment = BookingInstallment.objects.get(booking=booking, title="Registry payment")
        self.assertRedirects(installment_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(installment.status, BookingInstallment.Status.PENDING)

        payment_response = self.client.post(
            reverse("properties:booking_payment_create", args=[colony.id, plot.id, booking.id]),
            data={
                "installment": installment.id,
                "received_on": timezone.now().date().strftime("%Y-%m-%d"),
                "amount": "200000",
                "mode": BookingPayment.PaymentMode.UPI,
                "reference_number": "UTR123",
                "note": "Part payment",
            },
        )
        self.assertRedirects(payment_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        booking.refresh_from_db()
        installment.refresh_from_db()
        self.assertEqual(booking.paid_amount, 300000)
        self.assertEqual(booking.balance_amount, 2255000)
        self.assertEqual(installment.paid_amount, 200000)
        self.assertEqual(installment.status, BookingInstallment.Status.PARTIAL)
        self.assertTrue(AuditLog.objects.filter(action="property_booking.payment_received", target_id=str(colony.id)).exists())

        agreement_response = self.client.post(
            reverse("properties:booking_agreement_create", args=[colony.id, plot.id, booking.id]),
            data={
                "agreement_type": BookingAgreement.AgreementType.SALE,
                "title": "Sale Agreement",
                "status": BookingAgreement.Status.SIGNED,
                "agreement_number": "AGR-001",
                "stamp_number": "STAMP-001",
                "prepared_on": timezone.now().date().strftime("%Y-%m-%d"),
                "signed_on": timezone.now().date().strftime("%Y-%m-%d"),
                "registered_on": "",
                "registration_office": "",
                "next_action_date": "",
                "note": "Signed by buyer",
            },
        )
        agreement = BookingAgreement.objects.get(booking=booking, title="Sale Agreement")
        self.assertRedirects(agreement_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(agreement.status, BookingAgreement.Status.SIGNED)
        self.assertEqual(agreement.created_by, self.owner)

        registered_response = self.client.post(
            reverse("properties:booking_agreement_update", args=[colony.id, plot.id, booking.id, agreement.id]),
            data={
                "agreement_type": agreement.agreement_type,
                "title": agreement.title,
                "status": BookingAgreement.Status.REGISTERED,
                "agreement_number": agreement.agreement_number,
                "stamp_number": agreement.stamp_number,
                "prepared_on": agreement.prepared_on.strftime("%Y-%m-%d"),
                "signed_on": agreement.signed_on.strftime("%Y-%m-%d"),
                "registered_on": timezone.now().date().strftime("%Y-%m-%d"),
                "registration_office": "Indore SRO",
                "next_action_date": "",
                "note": "Registered",
            },
        )
        agreement.refresh_from_db()
        self.assertRedirects(registered_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertEqual(agreement.status, BookingAgreement.Status.REGISTERED)
        self.assertEqual(agreement.registration_office, "Indore SRO")
        self.assertTrue(AuditLog.objects.filter(action="property_booking.agreement_updated", target_id=str(colony.id)).exists())

    def test_plot_finder_searches_colony_and_plot_number(self):
        self.client.force_login(self.owner)
        colony = Property.objects.create(
            owner=self.owner,
            title="Green Valley Phase 1",
            category=Property.Category.COLONY,
            colony_name="Green Valley Premium Colony",
            city="Indore",
            address="Ring Road",
            area_sqft=10000,
        )
        plot = ColonyPlot.objects.create(property=colony, plot_number="GV-A-11", area_sqft=1100, base_rate=1800)
        Property.objects.create(owner=self.owner, title="Other Colony", category=Property.Category.COLONY, colony_name="Other Colony", city="Indore", address="AB Road", area_sqft=8000)

        response = self.client.get(reverse("properties:plot_finder"), {"colony": "green valley", "plot_number": "A-11"})

        self.assertContains(response, "Plot Finder")
        self.assertContains(response, "Green Valley Premium Colony")
        self.assertContains(response, "GV-A-11")
        self.assertContains(response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        self.assertContains(response, reverse("properties:plot_quotation_create", args=[colony.id, plot.id]))
        self.assertContains(response, reverse("properties:plot_booking_create", args=[colony.id, plot.id]))
        self.assertContains(response, reverse("properties:plot_visit_create", args=[colony.id, plot.id]))
        self.assertNotContains(response, "Other Colony")

        workflow_response = self.client.get(reverse("properties:plot_finder"), {"workflow": "quotation_booking"})
        self.assertContains(workflow_response, "Quotation &amp; Booking")
        self.assertContains(workflow_response, "Site Visit Management")
        self.assertContains(workflow_response, "Commission Management")

    def test_commission_rules_page_sets_role_wise_percentage_fixed_and_per_sqft(self):
        self.client.force_login(self.owner)
        colony = Property.objects.create(
            owner=self.owner,
            title="Commission Colony",
            category=Property.Category.COLONY,
            colony_name="Commission Colony",
            city="Indore",
            address="Ring Road",
            area_sqft=10000,
        )

        response = self.client.post(
            reverse("properties:commission_rules"),
            data={
                "property": colony.id,
                "commissions-TOTAL_FORMS": "5",
                "commissions-INITIAL_FORMS": "0",
                "commissions-MIN_NUM_FORMS": "0",
                "commissions-MAX_NUM_FORMS": "1000",
                "commissions-0-role": Role.EXECUTIVE,
                "commissions-0-calculation_type": PropertyCommissionRule.CalculationType.PERCENTAGE,
                "commissions-0-value": "2.5",
                "commissions-0-note": "Sales percentage",
                "commissions-0-is_active": "on",
                "commissions-1-role": Role.MANAGER,
                "commissions-1-calculation_type": PropertyCommissionRule.CalculationType.FIXED_AMOUNT,
                "commissions-1-value": "15000",
                "commissions-1-note": "Manager fixed",
                "commissions-1-is_active": "on",
                "commissions-2-role": Role.TL,
                "commissions-2-calculation_type": PropertyCommissionRule.CalculationType.PER_SQFT,
                "commissions-2-value": "10",
                "commissions-2-note": "TL area payout",
                "commissions-2-is_active": "on",
            },
        )

        self.assertRedirects(response, f"{reverse('properties:commission_rules')}?property={colony.id}")
        self.assertEqual(colony.commission_rules.count(), 3)
        plot = ColonyPlot.objects.create(property=colony, plot_number="C-11", area_sqft=1000, base_rate=2000)
        quote_response = self.client.post(
            reverse("properties:plot_booking_create", args=[colony.id, plot.id]),
            data={
                "client_name": "Commission Buyer",
                "client_phone": "+91 9000000000",
                "client_email": "buyer@example.com",
                "booking_date": timezone.localdate().strftime("%Y-%m-%d"),
                "booking_amount": "100000",
                "agreed_rate": "2000",
                "discount_amount": "0",
                "coupon_code": "",
                "coupon_discount_amount": "0",
                "plc_amount": "0",
                "charges_amount": "0",
                "payment_mode": "UPI",
                "status": PlotBooking.Status.BOOKED,
                "note": "",
            },
        )
        self.assertRedirects(quote_response, reverse("properties:plot_detail", args=[colony.id, plot.id]))
        booking = PlotBooking.objects.get(plot=plot)
        self.assertEqual(booking.commission_amount, 75000)
        self.assertTrue(PropertyCommissionPayout.objects.filter(booking=booking, role=Role.EXECUTIVE, amount=50000).exists())
        self.assertTrue(PropertyCommissionPayout.objects.filter(booking=booking, role=Role.MANAGER, amount=15000).exists())
        self.assertTrue(PropertyCommissionPayout.objects.filter(booking=booking, role=Role.TL, amount=10000).exists())

    def test_commission_rule_setup_is_hidden_from_tl_and_executive(self):
        tl = create_user(company=self.company, role=Role.TL, email="tl-commission@example.com")
        executive = create_user(company=self.company, role=Role.EXECUTIVE, email="exec-commission@example.com")
        for user in (tl, executive):
            self.client.force_login(user)
            response = self.client.get(reverse("properties:commission_rules"))
            self.assertRedirects(response, reverse("properties:list"))
            finder_response = self.client.get(reverse("properties:plot_finder"))
            self.assertNotContains(finder_response, "Commission Management")
            self.assertNotContains(finder_response, "Payout Ledger")

    def test_booking_edit_syncs_paid_amount_commission_and_plot_status(self):
        colony = Property.objects.create(owner=self.owner, title="Ledger Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road")
        plot = ColonyPlot.objects.create(property=colony, plot_number="L-01", area_sqft=1000, base_rate=2000)
        PropertyCommissionRule.objects.create(property=colony, role=Role.EXECUTIVE, calculation_type=PropertyCommissionRule.CalculationType.PERCENTAGE, value=2)
        self.client.force_login(self.owner)
        create_data = {
            "client_name": "Ledger Buyer",
            "client_phone": "+91 9000000000",
            "booking_date": timezone.localdate().strftime("%Y-%m-%d"),
            "booking_amount": "100000",
            "paid_amount_received": "60000",
            "agreed_rate": "2000",
            "discount_amount": "0",
            "coupon_code": "",
            "coupon_discount_amount": "0",
            "plc_amount": "0",
            "charges_amount": "0",
            "payment_mode": "UPI",
            "payment_reference": "UTR-1",
            "status": PlotBooking.Status.BOOKED,
            "note": "",
        }
        self.client.post(reverse("properties:plot_booking_create", args=[colony.id, plot.id]), data=create_data)
        booking = PlotBooking.objects.get(plot=plot)
        self.assertEqual(booking.paid_amount, 60000)
        self.assertEqual(booking.balance_amount, 1940000)

        edit_data = {**create_data, "paid_amount_received": "80000", "agreed_rate": "2500", "status": PlotBooking.Status.CONVERTED}
        self.client.post(reverse("properties:plot_booking_edit", args=[colony.id, plot.id, booking.id]), data=edit_data)
        booking.refresh_from_db()
        plot.refresh_from_db()
        self.assertEqual(booking.paid_amount, 80000)
        self.assertEqual(booking.commission_amount, 50000)
        self.assertEqual(plot.status, ColonyPlot.Status.SOLD)

        edit_data["status"] = PlotBooking.Status.CANCELLED
        self.client.post(reverse("properties:plot_booking_edit", args=[colony.id, plot.id, booking.id]), data=edit_data)
        plot.refresh_from_db()
        self.assertEqual(plot.status, ColonyPlot.Status.AVAILABLE)

    def test_booking_form_rejects_paid_amount_above_deal_value(self):
        colony = Property.objects.create(owner=self.owner, title="Overpay Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road")
        plot = ColonyPlot.objects.create(property=colony, plot_number="O-01", area_sqft=1000, base_rate=2000)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:plot_booking_create", args=[colony.id, plot.id]),
            data={
                "client_name": "Overpay Buyer",
                "booking_date": timezone.localdate().strftime("%Y-%m-%d"),
                "booking_amount": "100000",
                "paid_amount_received": "3000000",
                "agreed_rate": "2000",
                "discount_amount": "0",
                "coupon_code": "",
                "coupon_discount_amount": "0",
                "plc_amount": "0",
                "charges_amount": "0",
                "payment_mode": "Cash",
                "status": PlotBooking.Status.BOOKED,
            },
        )
        self.assertContains(response, "Paid amount cannot exceed the total deal value.")

    def test_owner_cannot_create_second_active_booking_for_plot(self):
        colony = Property.objects.create(owner=self.owner, title="Single Booking Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road")
        plot = ColonyPlot.objects.create(property=colony, plot_number="S-01", area_sqft=1000, base_rate=2000)
        PlotBooking.objects.create(
            plot=plot,
            client_name="First Buyer",
            booking_date=timezone.localdate(),
            agreed_rate=2000,
            status=PlotBooking.Status.BOOKED,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:plot_booking_create", args=[colony.id, plot.id]),
            data={
                "client_name": "Second Buyer",
                "booking_date": timezone.localdate().strftime("%Y-%m-%d"),
                "booking_amount": "100000",
                "paid_amount_received": "0",
                "agreed_rate": "2000",
                "discount_amount": "0",
                "coupon_discount_amount": "0",
                "plc_amount": "0",
                "charges_amount": "0",
                "status": PlotBooking.Status.BOOKED,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This plot already has an active booking.")
        self.assertEqual(plot.bookings.count(), 1)

    def test_unallocated_payment_cannot_exceed_booking_balance(self):
        colony = Property.objects.create(owner=self.owner, title="Payment Guard Colony", category=Property.Category.COLONY, city="Indore", address="Ring Road")
        plot = ColonyPlot.objects.create(property=colony, plot_number="P-01", area_sqft=1000, base_rate=2000)
        booking = PlotBooking.objects.create(
            plot=plot,
            client_name="Payment Buyer",
            booking_date=timezone.localdate(),
            agreed_rate=2000,
            paid_amount=1900000,
            status=PlotBooking.Status.BOOKED,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("properties:booking_payment_create", args=[colony.id, plot.id, booking.id]),
            data={"received_on": timezone.localdate(), "amount": "200000", "mode": BookingPayment.PaymentMode.CASH},
            follow=True,
        )
        self.assertContains(response, "Payment could not be recorded.")
        self.assertFalse(booking.payments.exists())

    def test_create_plot_recalculates_colony_pricing_server_side(self):
        colony = Property.objects.create(
            owner=self.owner,
            title="Priced Colony",
            category=Property.Category.COLONY,
            city="Indore",
            address="Ring Road",
            area_sqft=10000,
            total_plots=1,
            commercial_rate_per_sqft=2200,
            electricity_charge=5,
            maintenance_charge=5,
            main_road_plc_rate=5,
            wide_road_plc_rate=2,
        )
        form = ColonyPlotForm(
            {
                "plot_number": "C-01",
                "plot_category": ColonyPlot.PlotCategory.COMMERCIAL,
                "custom_category": "",
                "block": "C",
                "area_sqft": 1000,
                "length_ft": "50",
                "width_ft": "20",
                "facing": ColonyPlot.Facing.MAIN_ROAD,
                "road_width_ft": "60",
                "base_rate": "1",
                "plc_rate": "1",
                "extra_charges": "1",
                "price": "1",
                "is_main_road": "on",
                "is_wide_road": "on",
                "status": ColonyPlot.Status.AVAILABLE,
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        plot = create_plot(form=form, property_obj=colony, actor=self.owner)

        self.assertEqual(plot.base_rate, 2200)
        self.assertEqual(plot.plc_rate, 7)
        self.assertEqual(plot.extra_charges, 10000)
        self.assertEqual(plot.price, 2364000)
