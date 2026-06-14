from django.db import models, transaction
from django.utils import timezone

from accounts.services import record_audit
from accounts.models import Role

from .models import BookingAgreement, BookingInstallment, BookingPayment, ColonyPlot, PlotBooking, PlotStatusHistory, Property, PropertyCommissionPayout, PropertyCommissionRule, PropertyDocument, PropertyStatusHistory, PropertyVisit


def actor_company(actor):
    return getattr(getattr(actor, "profile", None), "company", None)


def colony_category_rate(property_obj, plot_category):
    rate_map = {
        ColonyPlot.PlotCategory.RESIDENTIAL: property_obj.residential_rate_per_sqft,
        ColonyPlot.PlotCategory.COMMERCIAL: property_obj.commercial_rate_per_sqft,
        ColonyPlot.PlotCategory.LIG: property_obj.lig_rate_per_sqft,
        ColonyPlot.PlotCategory.MIG: property_obj.mig_rate_per_sqft,
        ColonyPlot.PlotCategory.HIG: property_obj.hig_rate_per_sqft,
        ColonyPlot.PlotCategory.EWS: property_obj.ews_rate_per_sqft,
    }
    return rate_map.get(plot_category) or property_obj.base_rate_per_sqft


def colony_charge_per_sqft(property_obj):
    return (
        (property_obj.electricity_charge or 0)
        + (property_obj.maintenance_charge or 0)
        + (property_obj.development_charge or 0)
        + (property_obj.registry_charge or 0)
        + (property_obj.other_charge or 0)
    )


def colony_plc_rate(property_obj, plot):
    return (
        (property_obj.corner_plc_rate if plot.is_corner else 0)
        + (property_obj.garden_facing_plc_rate if plot.is_garden_facing else 0)
        + (property_obj.main_road_plc_rate if plot.is_main_road else 0)
        + (property_obj.wide_road_plc_rate if plot.is_wide_road else 0)
    )


def apply_colony_pricing(plot):
    property_obj = plot.property
    if not property_obj or property_obj.category != Property.Category.COLONY:
        return plot
    plot.base_rate = colony_category_rate(property_obj, plot.plot_category)
    plot.plc_rate = colony_plc_rate(property_obj, plot)
    plot.extra_charges = (plot.area_sqft or 0) * colony_charge_per_sqft(property_obj)
    base_amount = (plot.area_sqft or 0) * plot.base_rate
    plot.price = base_amount + (base_amount * plot.plc_rate / 100) + plot.extra_charges
    return plot


def calculate_commission_snapshot(property_obj, base_amount, area_sqft):
    snapshot = []
    total = 0
    for rule in property_obj.commission_rules.filter(is_active=True):
        if rule.calculation_type == PropertyCommissionRule.CalculationType.PERCENTAGE:
            amount = base_amount * rule.value / 100
        elif rule.calculation_type == PropertyCommissionRule.CalculationType.PER_SQFT:
            amount = area_sqft * rule.value
        else:
            amount = rule.value
        total += amount
        snapshot.append(
            {
                "role": rule.role,
                "type": rule.calculation_type,
                "value": str(rule.value),
                "amount": str(amount),
                "note": rule.note,
            }
        )
    return total, snapshot


def sync_commission_payouts(booking, actor=None):
    active_roles = set()
    for item in booking.commission_snapshot or []:
        role = item.get("role")
        if not role:
            continue
        active_roles.add(role)
        payout, created = PropertyCommissionPayout.objects.get_or_create(
            booking=booking,
            role=role,
            defaults={
                "calculation_type": item.get("type", ""),
                "rule_value": item.get("value") or 0,
                "amount": item.get("amount") or 0,
                "note": item.get("note", ""),
                "generated_by": actor,
            },
        )
        if created:
            continue
        if payout.status == PropertyCommissionPayout.Status.UNPAID:
            payout.calculation_type = item.get("type", "")
            payout.rule_value = item.get("value") or 0
            payout.amount = item.get("amount") or 0
            payout.note = item.get("note", "")
            payout.save(update_fields=["calculation_type", "rule_value", "amount", "note", "updated_at"])
    booking.commission_payouts.filter(status=PropertyCommissionPayout.Status.UNPAID).exclude(role__in=active_roles).delete()
    return booking.commission_payouts.all()


@transaction.atomic
def resync_property_commissions(property_obj, actor=None):
    bookings = PlotBooking.objects.select_related("plot").filter(
        plot__property=property_obj,
        status__in=[PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED],
    )
    for booking in bookings:
        area_sqft = booking.plot_area_sqft or booking.plot.area_sqft or 0
        base_amount = area_sqft * (booking.agreed_rate or 0)
        commission_amount, commission_snapshot = calculate_commission_snapshot(property_obj, base_amount, area_sqft)
        booking.commission_amount = commission_amount
        booking.commission_snapshot = commission_snapshot
        booking.save(update_fields=["commission_amount", "commission_snapshot", "updated_at"])
        sync_commission_payouts(booking, actor=actor)
    return bookings.count()


@transaction.atomic
def update_commission_payout(*, payout, status, actor, payout_reference="", note=""):
    payout = PropertyCommissionPayout.objects.select_for_update().get(pk=payout.pk)
    payout.status = status
    payout.payout_reference = payout_reference
    payout.note = note
    if status == PropertyCommissionPayout.Status.PAID:
        payout.paid_by = actor
        payout.paid_at = timezone.now()
    else:
        payout.paid_by = None
        payout.paid_at = None
    payout.save(update_fields=["status", "payout_reference", "note", "paid_by", "paid_at", "updated_at"])
    record_audit(
        actor=actor,
        action="property_commission.payout_updated",
        target=payout.booking.plot.property,
        company=actor_company(actor),
        details={"booking_id": payout.booking_id, "payout_id": payout.id, "role": payout.role, "status": status},
    )
    return payout


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
def archive_property(*, property_obj, actor, note=""):
    if property_obj.is_archived:
        return property_obj
    property_obj.is_archived = True
    property_obj.archived_at = timezone.now()
    property_obj.archived_by = actor
    property_obj.archive_note = note
    property_obj.save(update_fields=["is_archived", "archived_at", "archived_by", "archive_note", "updated_at"])
    record_audit(
        actor=actor,
        action="property.archived",
        target=property_obj,
        company=actor_company(actor),
        details={"property_id": property_obj.id, "status": property_obj.status, "category": property_obj.category, "note": note},
    )
    return property_obj


@transaction.atomic
def restore_property(*, property_obj, actor):
    if not property_obj.is_archived:
        return property_obj
    property_obj.is_archived = False
    property_obj.archived_at = None
    property_obj.archived_by = None
    property_obj.archive_note = ""
    property_obj.save(update_fields=["is_archived", "archived_at", "archived_by", "archive_note", "updated_at"])
    record_audit(
        actor=actor,
        action="property.restored",
        target=property_obj,
        company=actor_company(actor),
        details={"property_id": property_obj.id, "status": property_obj.status, "category": property_obj.category},
    )
    return property_obj


@transaction.atomic
def bulk_archive_properties(*, queryset, actor, note="Bulk archive"):
    archived = 0
    company = actor_company(actor)
    for prop in queryset.select_for_update():
        if prop.is_archived:
            continue
        record_audit(
            actor=actor,
            action="property.archived",
            target=prop,
            company=company,
            target_label=str(prop),
            details={"property_id": prop.id, "status": prop.status, "category": prop.category, "source": "bulk_action", "note": note},
        )
        prop.is_archived = True
        prop.archived_at = timezone.now()
        prop.archived_by = actor
        prop.archive_note = note
        prop.save(update_fields=["is_archived", "archived_at", "archived_by", "archive_note", "updated_at"])
        archived += 1
    return archived


@transaction.atomic
def update_visit(*, form, actor):
    visit = form.save()
    if visit.outcome in {PropertyVisit.Outcome.BOOKED, PropertyVisit.Outcome.CLOSED} and not visit.converted_at:
        visit.converted_at = timezone.now()
        visit.save(update_fields=["converted_at", "updated_at"])
    record_audit(actor=actor, action="property_visit.updated", target=visit, company=actor_company(actor), details={"status": visit.status, "outcome": visit.outcome})
    return visit


@transaction.atomic
def create_plot(*, form, property_obj, actor):
    plot = form.save(commit=False)
    plot.property = property_obj
    apply_colony_pricing(plot)
    plot.save()
    PlotStatusHistory.objects.create(plot=plot, to_status=plot.status, changed_by=actor, note="Plot created")
    record_audit(actor=actor, action="property_plot.created", target=property_obj, company=actor_company(actor), details={"plot_id": plot.id, "plot_number": plot.plot_number, "status": plot.status})
    sync_available_plots(property_obj)
    return plot


@transaction.atomic
def update_plot(*, form, plot, actor):
    persisted = ColonyPlot.objects.select_for_update().only("status").get(pk=plot.pk)
    old_status = persisted.status
    updated = form.save(commit=False)
    apply_colony_pricing(updated)
    updated.save()
    if old_status != updated.status:
        PlotStatusHistory.objects.create(plot=updated, from_status=old_status, to_status=updated.status, changed_by=actor)
        record_audit(actor=actor, action="property_plot.status_changed", target=updated.property, company=actor_company(actor), details={"plot_id": updated.id, "from": old_status, "to": updated.status})
    else:
        record_audit(actor=actor, action="property_plot.updated", target=updated.property, company=actor_company(actor), details={"plot_id": updated.id, "plot_number": updated.plot_number})
    sync_available_plots(updated.property)
    return updated


def sync_available_plots(property_obj):
    property_obj.available_plots = property_obj.plots.exclude(status__in=[ColonyPlot.Status.SOLD, ColonyPlot.Status.RESERVED, ColonyPlot.Status.BOOKED]).count()
    property_obj.total_plots = max(property_obj.total_plots, property_obj.plots.count())
    property_obj.save(update_fields=["available_plots", "total_plots", "updated_at"])


def sync_property_legal_status(property_obj):
    docs = property_obj.documents.all()
    if docs.filter(review_status=PropertyDocument.ReviewStatus.REJECTED).exists():
        property_obj.legal_status = Property.LegalStatus.UNDER_REVIEW
    elif docs.exists() and not docs.exclude(review_status=PropertyDocument.ReviewStatus.VERIFIED).exists():
        property_obj.legal_status = Property.LegalStatus.CLEAR
    elif docs.exists():
        property_obj.legal_status = Property.LegalStatus.UNDER_REVIEW
    property_obj.save(update_fields=["legal_status", "updated_at"])
    return property_obj


@transaction.atomic
def review_property_document(*, form, document, actor):
    document = PropertyDocument.objects.select_for_update().get(pk=document.pk)
    reviewed = form.save(commit=False)
    document.document_number = reviewed.document_number
    document.issued_on = reviewed.issued_on
    document.expires_on = reviewed.expires_on
    document.review_status = reviewed.review_status
    document.review_note = reviewed.review_note
    document.reviewed_by = actor
    document.reviewed_at = timezone.now()
    document.save(update_fields=["document_number", "issued_on", "expires_on", "review_status", "review_note", "reviewed_by", "reviewed_at"])
    sync_property_legal_status(document.property)
    record_audit(
        actor=actor,
        action="property_document.reviewed",
        target=document.property,
        company=actor_company(actor),
        details={"document_id": document.id, "document_type": document.document_type, "review_status": document.review_status},
    )
    return document


def sync_booking_ledger(booking):
    paid_amount = booking.payments.aggregate(total=models.Sum("amount"))["total"] or 0
    booking.paid_amount = paid_amount
    booking.balance_amount = max((booking.total_deal_value or 0) - paid_amount, 0)
    booking.save(update_fields=["paid_amount", "balance_amount", "updated_at"])
    today = timezone.localdate()
    for installment in booking.installments.all():
        installment_paid = installment.payments.aggregate(total=models.Sum("amount"))["total"] or 0
        installment.paid_amount = installment_paid
        if installment.status != BookingInstallment.Status.CANCELLED:
            if installment_paid >= installment.amount:
                installment.status = BookingInstallment.Status.PAID
            elif installment_paid > 0:
                installment.status = BookingInstallment.Status.PARTIAL
            elif installment.due_date < today:
                installment.status = BookingInstallment.Status.OVERDUE
            else:
                installment.status = BookingInstallment.Status.PENDING
        installment.save(update_fields=["paid_amount", "status", "updated_at"])
    return booking


@transaction.atomic
def create_quotation(*, form, plot, actor):
    quotation = form.save(commit=False)
    quotation.plot = plot
    quotation.created_by = actor
    quotation.plot_area_sqft = quotation.plot_area_sqft or plot.area_sqft
    quotation.plot_length_ft = quotation.plot_length_ft or plot.length_ft
    quotation.plot_width_ft = quotation.plot_width_ft or plot.width_ft
    quotation.plot_facing = quotation.plot_facing or (plot.get_facing_display() if plot.facing else "")
    quotation.save()
    record_audit(actor=actor, action="property_plot.quotation_created", target=plot.property, company=actor_company(actor), details={"plot_id": plot.id, "quotation_id": quotation.id, "total": str(quotation.total_amount)})
    return quotation


@transaction.atomic
def update_quotation(*, form, quotation, actor):
    quotation = form.save()
    record_audit(actor=actor, action="property_plot.quotation_updated", target=quotation.plot.property, company=actor_company(actor), details={"plot_id": quotation.plot_id, "quotation_id": quotation.id, "total": str(quotation.total_amount)})
    return quotation


@transaction.atomic
def create_booking(*, form, plot, actor):
    plot = ColonyPlot.objects.select_for_update().get(pk=plot.pk)
    booking = form.save(commit=False)
    booking._paid_amount_received = form.cleaned_data.get("paid_amount_received")
    if booking._paid_amount_received is None:
        booking._paid_amount_received = booking.booking_amount
    booking.plot = plot
    booking.created_by = actor
    booking.plot_area_sqft = booking.plot_area_sqft or plot.area_sqft
    booking.plot_length_ft = booking.plot_length_ft or plot.length_ft
    booking.plot_width_ft = booking.plot_width_ft or plot.width_ft
    booking.plot_facing = booking.plot_facing or (plot.get_facing_display() if plot.facing else "")
    commission_amount, commission_snapshot = calculate_commission_snapshot(plot.property, plot.area_sqft * booking.agreed_rate, plot.area_sqft)
    booking.commission_amount = commission_amount
    booking.commission_snapshot = commission_snapshot
    is_owner = getattr(getattr(actor, "profile", None), "role", "") == Role.COMPANY_OWNER
    if not is_owner:
        booking.status = PlotBooking.Status.REQUESTED
        booking.approved_by = None
    elif booking.status in {PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED}:
        booking.approved_by = actor
    if booking.status in {PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED} and plot.bookings.filter(
        status__in=[PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED]
    ).exists():
        raise ValueError("This plot already has an active booking.")
    booking.save()
    if booking.status == PlotBooking.Status.REQUESTED:
        record_audit(actor=actor, action="property_plot.booking_requested", target=plot.property, company=actor_company(actor), details={"plot_id": plot.id, "booking_id": booking.id})
        return booking
    _finalize_booking(booking=booking, actor=actor)
    return booking


@transaction.atomic
def update_booking_request(*, form, booking, actor):
    previous_status = PlotBooking.objects.only("status").get(pk=booking.pk).status
    booking = form.save()
    paid_amount_received = form.cleaned_data.get("paid_amount_received")
    booking_installment = booking.installments.filter(title="Booking amount", note="Auto-created from booking form.").first()
    initial_payment = booking.payments.filter(note="Initial booking payment.").first()
    if booking_installment:
        booking_installment.amount = booking.booking_amount
        booking_installment.due_date = booking.booking_date
        booking_installment.save(update_fields=["amount", "due_date", "updated_at"])
    if initial_payment and paid_amount_received == 0:
        initial_payment.delete()
    elif initial_payment:
        initial_payment.amount = paid_amount_received if paid_amount_received is not None else initial_payment.amount
        initial_payment.received_on = booking.booking_date
        initial_payment.reference_number = booking.payment_reference or booking.payment_mode
        initial_payment.save(update_fields=["amount", "received_on", "reference_number"])
    elif paid_amount_received and booking.status != PlotBooking.Status.REQUESTED:
        BookingPayment.objects.create(
            booking=booking,
            installment=booking_installment,
            received_on=booking.booking_date,
            amount=paid_amount_received,
            mode=BookingPayment.PaymentMode.OTHER,
            reference_number=booking.payment_reference or booking.payment_mode,
            received_by=actor,
            note="Initial booking payment.",
        )
    sync_booking_ledger(booking)
    area_sqft = booking.plot_area_sqft or booking.plot.area_sqft or 0
    commission_amount, commission_snapshot = calculate_commission_snapshot(booking.plot.property, area_sqft * booking.agreed_rate, area_sqft)
    booking.commission_amount = commission_amount
    booking.commission_snapshot = commission_snapshot
    booking.save(update_fields=["commission_amount", "commission_snapshot", "updated_at"])
    sync_commission_payouts(booking, actor=actor)
    if previous_status != booking.status:
        _sync_plot_status_from_booking(booking=booking, actor=actor, previous_booking_status=previous_status)
    record_audit(actor=actor, action="property_plot.booking_updated", target=booking.plot.property, company=actor_company(actor), details={"plot_id": booking.plot_id, "booking_id": booking.id, "status": booking.status})
    return booking


def _sync_plot_status_from_booking(*, booking, actor, previous_booking_status=""):
    plot = booking.plot
    old_plot_status = plot.status
    if booking.status == PlotBooking.Status.BOOKED:
        plot.status = ColonyPlot.Status.BOOKED
    elif booking.status == PlotBooking.Status.CONVERTED:
        plot.status = ColonyPlot.Status.SOLD
    elif booking.status == PlotBooking.Status.CANCELLED:
        has_active_booking = plot.bookings.exclude(pk=booking.pk).filter(status__in=[PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED]).exists()
        if not has_active_booking:
            plot.status = ColonyPlot.Status.AVAILABLE
    if plot.status != old_plot_status:
        plot.save(update_fields=["status"])
        PlotStatusHistory.objects.create(
            plot=plot,
            from_status=old_plot_status,
            to_status=plot.status,
            changed_by=actor,
            note=f"Booking status changed from {previous_booking_status or '-'} to {booking.status}.",
        )
        sync_available_plots(plot.property)
    return plot


def _finalize_booking(*, booking, actor):
    plot = booking.plot
    paid_amount_received = getattr(booking, "_paid_amount_received", booking.booking_amount)
    booking_installment = BookingInstallment.objects.create(
        booking=booking,
        title="Booking amount",
        due_date=booking.booking_date,
        amount=booking.booking_amount,
        paid_amount=paid_amount_received,
        status=BookingInstallment.Status.PAID if paid_amount_received >= booking.booking_amount and booking.booking_amount else BookingInstallment.Status.PENDING,
        note="Auto-created from booking form.",
    )
    if paid_amount_received:
        BookingPayment.objects.create(
            booking=booking,
            installment=booking_installment,
            received_on=booking.booking_date,
            amount=paid_amount_received,
            mode=BookingPayment.PaymentMode.OTHER,
            reference_number=booking.payment_mode,
            received_by=actor,
            note="Initial booking payment.",
        )
    sync_commission_payouts(booking, actor=actor)
    sync_booking_ledger(booking)
    if booking.status in {PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED}:
        _sync_plot_status_from_booking(booking=booking, actor=actor)
    record_audit(actor=actor, action="property_plot.booking_created", target=plot.property, company=actor_company(actor), details={"plot_id": plot.id, "booking_id": booking.id, "status": booking.status})
    sync_available_plots(plot.property)
    return booking


@transaction.atomic
def approve_booking_request(*, booking, actor):
    booking = PlotBooking.objects.select_for_update().select_related("plot", "plot__property").get(pk=booking.pk)
    if booking.status != PlotBooking.Status.REQUESTED:
        return booking
    plot = ColonyPlot.objects.select_for_update().get(pk=booking.plot_id)
    if plot.bookings.exclude(pk=booking.pk).filter(status__in=[PlotBooking.Status.BOOKED, PlotBooking.Status.CONVERTED]).exists():
        raise ValueError("This plot already has an active booking.")
    booking.status = PlotBooking.Status.BOOKED
    booking.approved_by = actor
    booking.save(update_fields=["status", "approved_by", "updated_at"])
    _finalize_booking(booking=booking, actor=actor)
    record_audit(actor=actor, action="property_plot.booking_request_approved", target=booking.plot.property, company=actor_company(actor), details={"plot_id": booking.plot_id, "booking_id": booking.id})
    return booking


@transaction.atomic
def create_booking_installment(*, form, booking, actor):
    installment = form.save(commit=False)
    installment.booking = booking
    installment.save()
    sync_booking_ledger(booking)
    record_audit(
        actor=actor,
        action="property_booking.installment_created",
        target=booking.plot.property,
        company=actor_company(actor),
        details={"booking_id": booking.id, "installment_id": installment.id, "amount": str(installment.amount)},
    )
    return installment


@transaction.atomic
def receive_booking_payment(*, form, booking, actor):
    payment = form.save(commit=False)
    payment.booking = booking
    payment.received_by = actor
    payment.save()
    sync_booking_ledger(booking)
    record_audit(
        actor=actor,
        action="property_booking.payment_received",
        target=booking.plot.property,
        company=actor_company(actor),
        details={"booking_id": booking.id, "payment_id": payment.id, "amount": str(payment.amount)},
    )
    return payment


@transaction.atomic
def create_booking_agreement(*, form, booking, actor):
    agreement = form.save(commit=False)
    agreement.booking = booking
    agreement.created_by = actor
    agreement.updated_by = actor
    agreement.save()
    record_audit(
        actor=actor,
        action="property_booking.agreement_created",
        target=booking.plot.property,
        company=actor_company(actor),
        details={"booking_id": booking.id, "agreement_id": agreement.id, "status": agreement.status},
    )
    return agreement


@transaction.atomic
def update_booking_agreement(*, form, agreement, actor):
    agreement = form.save(commit=False)
    agreement.updated_by = actor
    agreement.save()
    record_audit(
        actor=actor,
        action="property_booking.agreement_updated",
        target=agreement.booking.plot.property,
        company=actor_company(actor),
        details={"booking_id": agreement.booking_id, "agreement_id": agreement.id, "status": agreement.status},
    )
    return agreement
