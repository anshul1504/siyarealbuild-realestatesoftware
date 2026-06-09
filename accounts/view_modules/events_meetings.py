from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..email_utils import send_event_notification_email, send_meeting_notification_email
from ..forms import CompanyEventForm, MeetingForm
from ..models import CompanyEvent, Meeting, Role, UserProfile
from .owner_common import owner_context, owner_render


def _profile_context(request):
    user_profile = getattr(request.user, "profile", None)
    return user_profile, getattr(user_profile, "company", None), getattr(user_profile, "role", "") == Role.COMPANY_OWNER


def _role_label(role):
    return dict(Role.choices).get(role, role)
@login_required
def owner_meetings(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        form_kind = request.POST.get("form_kind")
        if form_kind == "meeting_bulk":
            selected = Meeting.objects.filter(company=company, id__in=request.POST.getlist("meeting_ids"))
            if request.POST.get("action") == "delete" and selected.exists():
                count = selected.count()
                selected.delete()
                messages.success(request, f"Deleted {count} meeting(s).")
            else:
                messages.error(request, "Select meetings and choose delete.")
            return redirect("accounts:owner_meetings")
        if form_kind == "meeting_action":
            meeting = get_object_or_404(Meeting.objects.filter(company=company), id=request.POST.get("meeting_id"))
            if request.POST.get("action") == "status":
                status = request.POST.get("status")
                note = request.POST.get("status_note", "").strip()
                if status not in dict(Meeting.Status.choices):
                    messages.error(request, "Choose a valid meeting status.")
                    return redirect("accounts:owner_meetings")
                if status == Meeting.Status.CANCELLED and not note:
                    messages.error(request, "Cancellation reason is required.")
                    return redirect("accounts:owner_meetings")
                meeting.status = status
                meeting.status_note = note
                meeting.is_active = status == Meeting.Status.ACTIVE
                meeting.save(update_fields=["status", "status_note", "is_active"])
                messages.success(request, "Meeting status updated.")
                _send_meeting_emails(request, meeting, f"Online meeting {meeting.get_status_display().lower()}")
            return redirect("accounts:owner_meetings")

    meetings = Meeting.objects.filter(company=company).select_related("created_by")
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        meetings = meetings.filter(models.Q(title__icontains=query) | models.Q(description__icontains=query) | models.Q(meeting_link__icontains=query))
    if selected_role:
        meetings = [meeting for meeting in meetings if selected_role in (meeting.roles or [])]
    if selected_status in dict(Meeting.Status.choices):
        meetings = meetings.filter(status=selected_status) if hasattr(meetings, "filter") else [meeting for meeting in meetings if meeting.status == selected_status]
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(meetings, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return owner_render(
        request,
        "accounts/owner_meetings.html",
        {
            "meetings": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "selected_role": selected_role,
            "selected_status": selected_status,
            "query_string": query_params.urlencode(),
            "role_choices": Role.choices,
            "status_choices": Meeting.Status.choices,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_meeting_create(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = MeetingForm(request.POST or None, company=company, prefix="meeting")
    if request.method == "POST" and form.is_valid():
        meeting = form.save(commit=False)
        meeting.company = company
        meeting.created_by = request.user
        meeting.audience_type = Meeting.AudienceType.ROLE
        meeting.location = ""
        meeting.status = Meeting.Status.ACTIVE if meeting.is_active else Meeting.Status.CANCELLED
        meeting.save()
        meeting.employees.clear()
        messages.success(request, "Online meeting created.")
        _send_meeting_emails(request, meeting, "Online meeting scheduled")
        return redirect("accounts:owner_meetings")
    return owner_render(
        request,
        "accounts/owner_meeting_form.html",
        {"form": form, "mode": "create", "submit_label": "Create Meeting", "user_profile": user_profile},
    )


@login_required
def owner_meeting_edit(request, meeting_id):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    meeting = get_object_or_404(Meeting.objects.filter(company=company), id=meeting_id)
    form = MeetingForm(request.POST or None, instance=meeting, company=company, prefix="meeting")
    if request.method == "POST" and form.is_valid():
        meeting = form.save(commit=False)
        meeting.audience_type = Meeting.AudienceType.ROLE
        meeting.location = ""
        meeting.status = Meeting.Status.ACTIVE if meeting.is_active else meeting.status
        meeting.save()
        meeting.employees.clear()
        messages.success(request, "Online meeting updated.")
        _send_meeting_emails(request, meeting, "Online meeting updated")
        return redirect("accounts:owner_meetings")
    return owner_render(
        request,
        "accounts/owner_meeting_form.html",
        {"form": form, "meeting": meeting, "mode": "edit", "submit_label": "Update Meeting", "user_profile": user_profile},
    )


def _profile_email_targets(profiles):
    targets = []
    seen = set()
    for profile_item in profiles.select_related("user"):
        email = (profile_item.user.email or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        targets.append({
            "email": email,
            "name": profile_item.user.get_full_name() or email,
            "role": profile_item.get_role_display(),
        })
    return targets


def _meeting_email_targets(meeting):
    profiles = UserProfile.objects.filter(company=meeting.company).exclude(user__email="")
    profiles = profiles.filter(role__in=meeting.roles or [])
    return _profile_email_targets(profiles)


def _event_email_targets(event):
    profiles = UserProfile.objects.filter(company=event.company).exclude(user__email="")
    if not event.is_global:
        profiles = profiles.filter(role__in=event.roles or [])
    return _profile_email_targets(profiles)


def _format_dt(value):
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M %p") if value else ""


def _send_meeting_emails(request, meeting, action_label):
    sent_count = 0
    failed_count = 0
    for target in _meeting_email_targets(meeting):
        try:
            send_meeting_notification_email(
                to_email=target["email"],
                name=target["name"],
                meeting_title=meeting.title,
                starts_at=_format_dt(meeting.starts_at),
                ends_at=_format_dt(meeting.ends_at),
                location=meeting.location,
                meeting_link=meeting.meeting_link,
                description=meeting.description,
                action_label=action_label,
            )
            sent_count += 1
        except Exception:
            failed_count += 1
    if sent_count:
        messages.success(request, f"Meeting email sent to {sent_count} employee(s).")
    if failed_count:
        messages.warning(request, f"Meeting saved, but {failed_count} email(s) could not be sent.")


def _event_audience_label(event):
    if event.is_global:
        return "All roles"
    return ", ".join(_role_label(role) for role in (event.roles or [])) or "Selected roles"


def _send_event_emails(request, event, action_label):
    sent_count = 0
    failed_count = 0
    for target in _event_email_targets(event):
        try:
            send_event_notification_email(
                to_email=target["email"],
                name=target["name"],
                event_title=event.title,
                starts_at=_format_dt(event.starts_at),
                ends_at=_format_dt(event.ends_at),
                caption=event.caption,
                description=event.description,
                action_label=action_label,
                audience_label=_event_audience_label(event),
            )
            sent_count += 1
        except Exception:
            failed_count += 1
    if sent_count:
        messages.success(request, f"Event email sent to {sent_count} employee(s).")
    if failed_count:
        messages.warning(request, f"Event action completed, but {failed_count} email(s) could not be sent.")


@login_required
def owner_events(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")

    form_kind = request.POST.get("form_kind")
    if request.method == "POST" and form_kind == "event_bulk":
        selected = CompanyEvent.objects.filter(company=company, id__in=request.POST.getlist("event_ids"))
        action = request.POST.get("action")
        if not selected.exists():
            messages.error(request, "Select at least one event.")
            return redirect("accounts:owner_events")
        if action == "activate":
            for event in selected:
                _send_event_emails(request, event, "Event activated")
            updated = selected.update(is_active=True)
            messages.success(request, f"Activated {updated} event(s).")
        elif action == "deactivate":
            for event in selected:
                _send_event_emails(request, event, "Event deactivated")
            updated = selected.update(is_active=False)
            messages.success(request, f"Deactivated {updated} event(s).")
        elif action == "popup_on":
            for event in selected:
                _send_event_emails(request, event, "Event marked important")
            updated = selected.update(show_as_popup=True)
            messages.success(request, f"Enabled popup for {updated} event(s).")
        elif action == "popup_off":
            for event in selected:
                _send_event_emails(request, event, "Event popup removed")
            updated = selected.update(show_as_popup=False)
            messages.success(request, f"Disabled popup for {updated} event(s).")
        elif action == "delete":
            for event in selected:
                _send_event_emails(request, event, "Event cancelled")
            count = selected.count()
            selected.delete()
            messages.success(request, f"Deleted {count} event(s).")
        else:
            messages.error(request, "Choose a valid bulk action.")
        return redirect("accounts:owner_events")

    events = CompanyEvent.objects.filter(company=company).select_related("created_by")
    selected_period = request.GET.get("period", "upcoming").strip()
    today = timezone.localdate()
    if selected_period == "past":
        events = events.filter(starts_at__date__lt=today)
    elif selected_period == "upcoming":
        events = events.filter(starts_at__date__gte=today)
    elif selected_period == "active":
        events = events.filter(is_active=True)
    elif selected_period == "inactive":
        events = events.filter(is_active=False)
    elif selected_period == "popup":
        events = events.filter(show_as_popup=True)
    elif selected_period != "all":
        selected_period = "upcoming"
        events = events.filter(starts_at__date__gte=today)

    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(events, 8)
    page_obj = paginator.get_page(request.GET.get("page"))
    all_events = CompanyEvent.objects.filter(company=company)
    upcoming_count = all_events.filter(starts_at__date__gte=today).count()
    past_count = all_events.filter(starts_at__date__lt=today).count()
    return owner_render(
        request,
        "accounts/owner_events.html",
        {
            "events": page_obj.object_list,
            "page_obj": page_obj,
            "selected_period": selected_period,
            "query_string": query_params.urlencode(),
            "event_stats": {
                "total": all_events.count(),
                "upcoming": upcoming_count,
                "past": past_count,
                "active": all_events.filter(is_active=True).count(),
                "inactive": all_events.filter(is_active=False).count(),
                "popup": all_events.filter(show_as_popup=True).count(),
            },
            "user_profile": user_profile,
        },
    )


def _event_visible_for_role(event, role):
    return bool(event.is_global or role in (event.roles or []))


@login_required
def owner_event_create(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = CompanyEventForm(request.POST or None, request.FILES or None, prefix="event")
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.company = company
        event.created_by = request.user
        event.save()
        messages.success(request, "Event published.")
        _send_event_emails(request, event, "Event published")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return owner_render(
        request,
        "accounts/owner_event_form.html",
        {"form": form, "mode": "create", "submit_label": "Publish Event", "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def owner_event_detail(request, event_id):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    event = get_object_or_404(
        CompanyEvent.objects.filter(company=company).select_related("created_by"),
        id=event_id,
    )
    form_kind = request.POST.get("form_kind")
    if request.method == "POST" and form_kind == "event_action":
        action = request.POST.get("action")
        if action == "toggle":
            event.is_active = not event.is_active
            event.save(update_fields=["is_active"])
            messages.success(request, "Event status updated.")
            _send_event_emails(request, event, "Event activated" if event.is_active else "Event deactivated")
        elif action == "popup":
            event.show_as_popup = not event.show_as_popup
            event.save(update_fields=["show_as_popup"])
            messages.success(request, "Event popup setting updated.")
            _send_event_emails(request, event, "Event marked important" if event.show_as_popup else "Event popup removed")
        elif action == "delete":
            _send_event_emails(request, event, "Event cancelled")
            event.delete()
            messages.success(request, "Event deleted.")
            return redirect("accounts:owner_events")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return owner_render(
        request,
        "accounts/owner_event_detail.html",
        {"event": event, "user_profile": user_profile},
    )


@login_required
def owner_event_edit(request, event_id):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    event = get_object_or_404(CompanyEvent.objects.filter(company=company), id=event_id)
    form = CompanyEventForm(request.POST or None, request.FILES or None, instance=event, prefix="event")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Event updated.")
        _send_event_emails(request, event, "Event updated")
        return redirect("accounts:owner_event_detail", event_id=event.id)
    return owner_render(
        request,
        "accounts/owner_event_edit.html",
        {"event": event, "form": form, "submit_label": "Update Event", "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def event_detail(request, event_id):
    user_profile, company, _ = _profile_context(request)
    event = get_object_or_404(CompanyEvent, company=company, id=event_id, is_active=True)
    role = getattr(user_profile, "role", "")
    if not event.is_global and role not in (event.roles or []):
        raise Http404("Event not found")
    return render(request, "accounts/event_detail.html", {"event": event, "user_profile": user_profile})

