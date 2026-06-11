import csv
import hmac
import hashlib
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import (
    LeadAssignmentForm,
    LeadAssignmentRuleForm,
    LeadArchiveForm,
    LeadBulkActionForm,
    LeadFollowUpCompleteForm,
    LeadFollowUpForm,
    LeadForm,
    LeadNoteForm,
    LeadStatusForm,
    LeadVisitForm,
    MetaLeadSourceForm,
    PropertyMatchForm,
)
from .models import Lead, LeadAssignmentRule, LeadFollowUp, LeadPriority, LeadSource, LeadStatus, MetaLeadSource, MetaWebhookEvent
from .policies import can_assign_leads, can_configure_meta, can_edit_lead, can_view_lead, user_company
from .selectors import visible_leads_for
from .services import (
    add_lead_note,
    archive_lead,
    assign_lead,
    bulk_update_leads,
    complete_followup,
    create_followup,
    create_lead,
    fetch_meta_lead_data,
    ingest_meta_payload,
    match_property_to_lead,
    reprocess_meta_event,
    restore_lead,
    schedule_visit_from_lead,
    update_lead_details,
    update_lead_status,
)


def valid_meta_signature(request):
    app_secret = getattr(settings, "META_APP_SECRET", "")
    if not app_secret:
        return True
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


@login_required
def crm_dashboard(request):
    leads = visible_leads_for(request.user)
    now = timezone.now()
    today = now.date()
    open_statuses = [LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED, LeadStatus.PROPERTY_MATCHED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION]
    source_counts = [{"label": label, "count": leads.filter(source=value).count()} for value, label in LeadSource.choices]
    status_counts = [{"label": label, "count": leads.filter(status=value).count()} for value, label in LeadStatus.choices]
    due_followups = LeadFollowUp.objects.filter(lead__in=leads, status=LeadFollowUp.Status.OPEN, due_at__date__lte=today).select_related("lead", "assigned_to")[:8]
    context = {
        "total_leads": leads.count(),
        "new_today": leads.filter(created_at__date=today).count(),
        "unassigned": leads.filter(assigned_to__isnull=True).count(),
        "overdue_followups": LeadFollowUp.objects.filter(lead__in=leads, status=LeadFollowUp.Status.OPEN, due_at__lt=now).count(),
        "active_pipeline": leads.filter(status__in=open_statuses).count(),
        "converted": leads.filter(status__in=[LeadStatus.BOOKED, LeadStatus.CLOSED]).count(),
        "recent_leads": leads[:8],
        "due_followups": due_followups,
        "source_counts": source_counts,
        "status_counts": status_counts,
        "can_configure_meta": can_configure_meta(request.user),
    }
    return render(request, "crm/dashboard.html", context)


@login_required
def lead_list(request):
    include_archived = request.GET.get("archived") == "1"
    if include_archived and can_assign_leads(request.user):
        leads = Lead.objects.filter(company=user_company(request.user), is_archived=True).select_related("assigned_to", "created_by", "property", "company")
    else:
        leads = visible_leads_for(request.user)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    source = request.GET.get("source", "").strip()
    priority = request.GET.get("priority", "").strip()
    assignee = request.GET.get("assigned_to", "").strip()
    created_from = request.GET.get("created_from", "").strip()
    created_to = request.GET.get("created_to", "").strip()
    city = request.GET.get("city", "").strip()
    if query:
        leads = leads.filter(Q(client_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    if status:
        leads = leads.filter(status=status)
    if source:
        leads = leads.filter(source=source)
    if priority:
        leads = leads.filter(priority=priority)
    if assignee:
        leads = leads.filter(assigned_to_id=assignee)
    if city:
        leads = leads.filter(city__icontains=city)
    if created_from:
        leads = leads.filter(created_at__date__gte=created_from)
    if created_to:
        leads = leads.filter(created_at__date__lte=created_to)
    page_obj = Paginator(leads, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "crm/lead_list.html",
        {
            "page_obj": page_obj,
            "leads": page_obj.object_list,
            "query": query,
            "selected_status": status,
            "selected_source": source,
            "selected_priority": priority,
            "selected_assignee": assignee,
            "created_from": created_from,
            "created_to": created_to,
            "city": city,
            "include_archived": include_archived,
            "status_choices": LeadStatus.choices,
            "source_choices": LeadSource.choices,
            "priority_choices": LeadPriority.choices,
            "bulk_form": LeadBulkActionForm(user=request.user),
            "assignee_choices": LeadAssignmentForm(user=request.user).fields["assigned_to"].queryset,
            "can_assign": can_assign_leads(request.user),
        },
    )


@login_required
def lead_kanban(request):
    leads = visible_leads_for(request.user)
    columns = []
    for value, label in LeadStatus.choices:
        column_leads = leads.filter(status=value)
        columns.append({"value": value, "label": label, "leads": column_leads[:25], "count": column_leads.count()})
    return render(request, "crm/lead_kanban.html", {"columns": columns})


@login_required
def unassigned_leads(request):
    if not can_assign_leads(request.user):
        messages.error(request, "You cannot access unassigned lead queue.")
        return redirect("crm:dashboard")
    leads = visible_leads_for(request.user).filter(assigned_to__isnull=True)
    page_obj = Paginator(leads, 25).get_page(request.GET.get("page"))
    return render(request, "crm/unassigned_leads.html", {"page_obj": page_obj, "leads": page_obj.object_list, "bulk_form": LeadBulkActionForm(user=request.user)})


@login_required
def lead_bulk_action(request):
    if not can_assign_leads(request.user):
        messages.error(request, "You cannot perform bulk CRM actions.")
        return redirect("crm:lead_list")
    form = LeadBulkActionForm(request.POST, user=request.user)
    if form.is_valid():
        leads = visible_leads_for(request.user).filter(id__in=form.cleaned_data["lead_ids"])
        updated = bulk_update_leads(
            leads=leads,
            actor=request.user,
            action=form.cleaned_data["action"],
            assigned_to=form.cleaned_data["assigned_to"],
            status=form.cleaned_data["status"],
            priority=form.cleaned_data["priority"],
            note=form.cleaned_data["note"],
        )
        messages.success(request, f"{updated} lead(s) updated.")
    else:
        messages.error(request, "Please select leads and a valid bulk action.")
    return redirect(request.POST.get("next") or "crm:lead_list")


@login_required
def lead_create(request):
    company = user_company(request.user)
    if not company:
        messages.error(request, "Company profile is required before creating CRM leads.")
        return redirect("properties:dashboard")
    form = LeadForm(request.POST or None, user=request.user, company=company)
    if form.is_valid():
        lead = create_lead(company=company, actor=request.user, data=form.cleaned_data)
        messages.success(request, "Lead created.")
        return redirect("crm:lead_detail", lead_id=lead.id)
    return render(request, "crm/lead_form.html", {"form": form, "mode": "create"})


@login_required
def lead_edit(request, lead_id):
    lead = get_object_or_404(Lead.objects.select_related("company", "assigned_to", "property"), id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot edit this lead.")
        return redirect("crm:lead_list")
    form = LeadForm(request.POST or None, user=request.user, company=lead.company, instance=lead)
    if form.is_valid():
        update_lead_details(lead, actor=request.user, data=form.cleaned_data, changed_fields=form.changed_data)
        messages.success(request, "Lead details updated.")
        return redirect("crm:lead_detail", lead_id=lead.id)
    return render(request, "crm/lead_form.html", {"form": form, "mode": "edit", "lead": lead})


@login_required
def lead_detail(request, lead_id):
    lead = get_object_or_404(Lead.objects.select_related("company", "assigned_to", "created_by", "property"), id=lead_id)
    if not can_view_lead(request.user, lead):
        messages.error(request, "You cannot view this lead.")
        return redirect("crm:lead_list")
    return render(
        request,
        "crm/lead_detail.html",
        {
            "lead": lead,
            "status_form": LeadStatusForm(initial={"status": lead.status}),
            "assignment_form": LeadAssignmentForm(user=request.user, initial={"assigned_to": lead.assigned_to_id}),
            "followup_form": LeadFollowUpForm(user=request.user),
            "visit_form": LeadVisitForm(user=request.user, company=lead.company, initial={"property": lead.property_id, "assigned_employee": lead.assigned_to_id}),
            "match_form": PropertyMatchForm(company=lead.company, initial={"property": lead.property_id}),
            "note_form": LeadNoteForm(),
            "archive_form": LeadArchiveForm(),
            "activities": lead.activities.select_related("actor")[:30],
            "followups": lead.followups.select_related("assigned_to")[:20],
            "can_edit": can_edit_lead(request.user, lead),
            "can_assign": can_assign_leads(request.user),
        },
    )


@login_required
def lead_status_update(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot update this lead.")
        return redirect("crm:lead_list")
    form = LeadStatusForm(request.POST)
    if form.is_valid():
        update_lead_status(lead, actor=request.user, status=form.cleaned_data["status"], note=form.cleaned_data["note"])
        messages.success(request, "Lead status updated.")
    else:
        messages.error(request, "Please add the required status note before updating this lead.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_followup_create(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot add follow-up for this lead.")
        return redirect("crm:lead_list")
    form = LeadFollowUpForm(request.POST, user=request.user)
    if form.is_valid():
        create_followup(lead, actor=request.user, assigned_to=form.cleaned_data["assigned_to"], due_at=form.cleaned_data["due_at"], note=form.cleaned_data["note"])
        messages.success(request, "Follow-up scheduled.")
    else:
        messages.error(request, "Please check follow-up details.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_assign(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_assign_leads(request.user) or not can_view_lead(request.user, lead):
        messages.error(request, "You cannot assign this lead.")
        return redirect("crm:lead_detail", lead_id=lead.id)
    form = LeadAssignmentForm(request.POST, user=request.user)
    if form.is_valid():
        assign_lead(lead, actor=request.user, assigned_to=form.cleaned_data["assigned_to"], note=form.cleaned_data["note"])
        messages.success(request, "Lead assignment updated.")
    else:
        messages.error(request, "Please check assignment details.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_note_create(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot add notes to this lead.")
        return redirect("crm:lead_list")
    form = LeadNoteForm(request.POST)
    if form.is_valid():
        add_lead_note(lead, actor=request.user, note=form.cleaned_data["note"])
        messages.success(request, "Note added.")
    else:
        messages.error(request, "Please enter a note.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_archive(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_assign_leads(request.user) or not can_view_lead(request.user, lead):
        messages.error(request, "You cannot archive this lead.")
        return redirect("crm:lead_list")
    form = LeadArchiveForm(request.POST)
    if form.is_valid():
        archive_lead(lead, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(request, "Lead archived.")
    return redirect("crm:lead_list")


@login_required
def lead_restore(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_assign_leads(request.user) or lead.company_id != getattr(user_company(request.user), "id", None):
        messages.error(request, "You cannot restore this lead.")
        return redirect("crm:lead_list")
    restore_lead(lead, actor=request.user)
    messages.success(request, "Lead restored.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_property_match(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot match property for this lead.")
        return redirect("crm:lead_list")
    form = PropertyMatchForm(request.POST, company=lead.company)
    if form.is_valid():
        match_property_to_lead(lead, actor=request.user, property_obj=form.cleaned_data["property"], note=form.cleaned_data["note"])
        messages.success(request, "Property matched with lead.")
    else:
        messages.error(request, "Please select a valid property.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def lead_visit_schedule(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if not can_edit_lead(request.user, lead):
        messages.error(request, "You cannot schedule visit for this lead.")
        return redirect("crm:lead_list")
    form = LeadVisitForm(request.POST, user=request.user, company=lead.company)
    if form.is_valid():
        visit = schedule_visit_from_lead(
            lead,
            actor=request.user,
            property_obj=form.cleaned_data["property"],
            visit_at=form.cleaned_data["visit_at"],
            assigned_employee=form.cleaned_data["assigned_employee"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(request, "Site visit scheduled from CRM.")
        return redirect("properties:visit_detail", visit_id=visit.id)
    messages.error(request, "Please check visit details.")
    return redirect("crm:lead_detail", lead_id=lead.id)


@login_required
def followup_list(request):
    leads = visible_leads_for(request.user)
    status = request.GET.get("status", LeadFollowUp.Status.OPEN)
    followups = LeadFollowUp.objects.filter(lead__in=leads).select_related("lead", "assigned_to")
    if status:
        followups = followups.filter(status=status)
    page_obj = Paginator(followups, 25).get_page(request.GET.get("page"))
    return render(request, "crm/followup_list.html", {"page_obj": page_obj, "followups": page_obj.object_list, "selected_status": status, "status_choices": LeadFollowUp.Status.choices, "complete_form": LeadFollowUpCompleteForm()})


@login_required
def followup_complete(request, followup_id):
    followup = get_object_or_404(LeadFollowUp.objects.select_related("lead"), id=followup_id)
    if not can_edit_lead(request.user, followup.lead):
        messages.error(request, "You cannot complete this follow-up.")
        return redirect("crm:followup_list")
    form = LeadFollowUpCompleteForm(request.POST)
    if form.is_valid():
        complete_followup(followup, actor=request.user, outcome=form.cleaned_data["outcome"], note=form.cleaned_data["note"])
        messages.success(request, "Follow-up completed.")
    else:
        messages.error(request, "Please check follow-up outcome.")
    return redirect(request.POST.get("next") or "crm:followup_list")


@login_required
def meta_source_list(request):
    if not can_configure_meta(request.user):
        messages.error(request, "Only Company Owner can configure Meta lead sources.")
        return redirect("crm:lead_list")
    company = user_company(request.user)
    sources = MetaLeadSource.objects.filter(company=company)
    return render(request, "crm/meta_source_list.html", {"sources": sources})


@login_required
def meta_source_create(request):
    if not can_configure_meta(request.user):
        messages.error(request, "Only Company Owner can configure Meta lead sources.")
        return redirect("crm:lead_list")
    company = user_company(request.user)
    form = MetaLeadSourceForm(request.POST or None, user=request.user)
    if form.is_valid():
        source = form.save(commit=False)
        source.company = company
        source.save()
        messages.success(request, "Meta lead source saved.")
        return redirect("crm:meta_source_list")
    return render(request, "crm/meta_source_form.html", {"form": form})


@login_required
def assignment_rule_list(request):
    if not can_configure_meta(request.user):
        messages.error(request, "Only Company Owner can configure CRM assignment rules.")
        return redirect("crm:dashboard")
    rules = LeadAssignmentRule.objects.filter(company=user_company(request.user)).select_related("default_assignee")
    return render(request, "crm/assignment_rule_list.html", {"rules": rules})


@login_required
def assignment_rule_create(request):
    if not can_configure_meta(request.user):
        messages.error(request, "Only Company Owner can configure CRM assignment rules.")
        return redirect("crm:dashboard")
    form = LeadAssignmentRuleForm(request.POST or None, user=request.user)
    if form.is_valid():
        rule = form.save(commit=False)
        rule.company = user_company(request.user)
        rule.save()
        messages.success(request, "CRM assignment rule saved.")
        return redirect("crm:assignment_rule_list")
    return render(request, "crm/assignment_rule_form.html", {"form": form})


@login_required
def meta_event_reprocess(request, event_id):
    if not can_configure_meta(request.user):
        messages.error(request, "Only Company Owner can reprocess Meta events.")
        return redirect("crm:reports")
    event = get_object_or_404(MetaWebhookEvent, id=event_id, company=user_company(request.user))
    lead, new_event = reprocess_meta_event(event, actor=request.user)
    if lead:
        messages.success(request, "Meta event reprocessed and lead created.")
    else:
        messages.warning(request, f"Meta event reprocessed with status {new_event.get_status_display()}.")
    return redirect("crm:reports")


@login_required
def crm_reports(request):
    leads = visible_leads_for(request.user)
    now = timezone.now()
    assignee_counts = (
        leads.values("assigned_to__email", "assigned_to__first_name", "assigned_to__last_name")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )
    context = {
        "source_counts": [{"label": label, "count": leads.filter(source=value).count()} for value, label in LeadSource.choices],
        "status_counts": [{"label": label, "count": leads.filter(status=value).count()} for value, label in LeadStatus.choices],
        "priority_counts": [{"label": label, "count": leads.filter(priority=value).count()} for value, label in LeadPriority.choices],
        "overdue_followups": LeadFollowUp.objects.filter(lead__in=leads, status=LeadFollowUp.Status.OPEN, due_at__lt=now).select_related("lead", "assigned_to")[:20],
        "meta_events": MetaWebhookEvent.objects.filter(company=user_company(request.user)).select_related("company")[:20],
        "assignee_counts": assignee_counts,
        "failed_meta_count": MetaWebhookEvent.objects.filter(company=user_company(request.user), status=MetaWebhookEvent.Status.FAILED).count(),
    }
    return render(request, "crm/reports.html", context)


@login_required
def lead_export(request):
    if not can_assign_leads(request.user):
        messages.error(request, "You cannot export CRM leads.")
        return redirect("crm:dashboard")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="crm-leads.csv"'
    writer = csv.writer(response)
    writer.writerow(["Client", "Phone", "Email", "City", "Source", "Status", "Priority", "Assigned To", "Created At"])
    for lead in visible_leads_for(request.user).select_related("assigned_to"):
        assigned_to = ""
        if lead.assigned_to:
            assigned_to = lead.assigned_to.get_full_name() or lead.assigned_to.email
        writer.writerow([
            lead.client_name,
            lead.phone,
            lead.email,
            lead.city,
            lead.get_source_display(),
            lead.get_status_display(),
            lead.get_priority_display(),
            assigned_to,
            lead.created_at.strftime("%Y-%m-%d %H:%M"),
        ])
    return response


@csrf_exempt
def meta_webhook(request):
    verify_token = getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "")
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if mode == "subscribe" and verify_token and token == verify_token:
            return HttpResponse(challenge)
        return HttpResponse("Invalid verification token", status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    if not valid_meta_signature(request):
        return JsonResponse({"ok": False, "error": "Invalid Meta signature"}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    processed = 0
    errors = []
    entries = payload.get("entry") if isinstance(payload, dict) else []
    for entry in entries or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            form_id = str(value.get("form_id") or "")
            page_id = str(value.get("page_id") or entry.get("id") or "")
            leadgen_id = str(value.get("leadgen_id") or "")
            source = MetaLeadSource.objects.filter(form_id=form_id, page_id=page_id, is_active=True).select_related("company", "default_assignee").first()
            if not source:
                event_id = leadgen_id or f"unknown-{timezone.now().timestamp()}"
                MetaWebhookEvent.objects.get_or_create(
                    event_id=event_id,
                    defaults={
                        "payload": value,
                        "status": MetaWebhookEvent.Status.FAILED,
                        "error_message": "No active Meta source mapping.",
                    },
                )
                errors.append({"leadgen_id": leadgen_id, "error": "source_not_found"})
                continue
            fetched_data = fetch_meta_lead_data(leadgen_id) or value
            ingest_meta_payload(source=source, payload={"event_id": leadgen_id, "leadgen_id": leadgen_id, "form_id": form_id, "page_id": page_id}, fetched_data=fetched_data)
            source.last_synced_at = timezone.now()
            source.save(update_fields=["last_synced_at"])
            processed += 1
    return JsonResponse({"ok": True, "processed": processed, "errors": errors})
