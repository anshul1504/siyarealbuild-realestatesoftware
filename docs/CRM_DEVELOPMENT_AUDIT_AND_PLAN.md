# CRM Development Audit and Completion Plan

Audit date: 2026-06-11

## Executive Verdict

The CRM is no longer only a planning idea. It now has a working Django app, lead pipeline, role-aware visibility, lead assignment, follow-ups, property matching, visit scheduling, CSV export, reports, activity history, Meta source configuration, and Meta webhook ingestion foundation.

Current practical readiness is about 85% for an internal operational CRM and about 70-75% for a production-grade Meta-connected CRM. The remaining work is mostly external-platform integration, background processing, and richer analytics rather than core CRM workflows.

## Current Completion Estimate

- CRM app wiring: 100%
- Lead CRUD and detail workspace: 85%
- Role-wise access foundation: 80%
- Follow-up workflow: 85%
- Property and site-visit integration: 80%
- Assignment automation: 75%
- Meta webhook foundation: 80%
- Meta production integration: 55%
- Duplicate detection and lifecycle rules: 80%
- Reports and analytics: 60%
- Frontend CRM polish: 70%
- Production readiness: 55%

Overall professional CRM progress: 80-85% complete for internal use, and 70-75% complete for production Meta-connected use.

## Existing Features

- Dedicated `crm` Django app.
- Sidebar navigation for CRM Dashboard, Lead Pipeline, Kanban Pipeline, Lead Queue, Add Lead, Follow-ups, Reports, and Meta Sources.
- Lead model with client details, budget, requirement, property category, listing purpose, source, Meta identifiers, status, priority, assignment, property link, visit link, follow-up timestamps, lost reason, and notes.
- Lead statuses: New, Contacted, Qualified, Property Matched, Site Visit Scheduled, Site Visit Completed, Follow-up, Negotiation, Booked, Closed, Lost, Duplicate.
- Lead sources: Meta Lead Ads, Manual, Website, Referral, WhatsApp, Property Share.
- Lead activity timeline for created, status, assignment, note, follow-up, visit, and Meta sync events.
- Lead follow-up model with Open, Done, Missed, Cancelled states.
- Meta source model with page/form mapping, active flag, default assignee, default role, and JSON field mapping.
- Meta webhook event model for received, processed, failed, and duplicate events.
- Dashboard metrics for total leads, new today, unassigned, overdue, active pipeline, converted, source counts, status counts, recent leads, and due follow-ups.
- Lead list search and filters by status, source, and priority.
- Kanban board grouped by lead status.
- Lead create/edit/detail pages.
- Lead assignment, status update, internal note, follow-up scheduling, follow-up completion.
- Property matching from CRM lead.
- Site visit scheduling from CRM lead into `PropertyVisit`.
- Bulk lead assign/status/priority update for permitted roles.
- CSV export for permitted roles.
- Admin registration for CRM models.
- Meta webhook verification token support.
- Meta Graph fetch hook through page access token setting.
- Meta duplicate guard by Meta lead ID, normalized phone, and email.
- Meta app signature verification support through `SIYA_META_APP_SECRET`.
- Global `AuditLog` creation for CRM lead activity.
- Owner-configurable CRM assignment rules for default, source, city, and property-category routing.
- Failed Meta event reprocess action from reports.
- Advanced lead filters for assignee, city, and date range.
- Assignee distribution and Meta health metrics in reports.
- Notification delivery records for CRM assignment, follow-up scheduling, and Meta lead assignment.
- Test coverage for core CRM workflows.

## Role-Wise Current Behavior

Company Owner:
- Can configure Meta sources.
- Can see company CRM leads.
- Can assign leads.
- Can export leads.
- Can view reports.

Manager:
- Can see company CRM leads.
- Can assign leads.
- Can bulk update leads.
- Can export leads.
- Can view reports.

Team Lead:
- Can assign leads when the lead is visible.
- Visibility is intentionally restricted to leads assigned to or created by the TL until a structured team hierarchy exists.

Executive:
- Can see assigned or self-created leads only.
- Can update visible leads and follow-ups.
- Cannot directly access unassigned/private leads.

Channel Partner:
- Currently limited to assigned or self-created lead visibility.
- Dedicated channel-partner lead/referral conversion and payout workflow is still pending.

No-company user:
- Cannot access company CRM data.

## Compulsory Remaining Work

P0:
- Add a structured team hierarchy for Team Lead visibility instead of relying on `reporting_manager` text.
- Add dedicated Channel Partner CRM workflow for referral leads, partner-owned leads, conversion visibility, and payout status.
- Add round-robin and workload-based assignment on top of existing owner-configured assignment rules.
- Add proper lead archive/delete flow with audit log.
- Add Meta token management UI.
- Add Meta OAuth/page/form sync for real production connection.
- Add production monitoring for token expiry and background job failures.

P1:
- Add advanced lead filters: assignee, created date, follow-up date, city, budget, property category, listing purpose, and source reference.
- Add drag/drop Kanban status update with permission checks.
- Add charts for source performance, funnel conversion, overdue aging, and team performance.
- Add notification delivery for new assignment, reassignment, overdue follow-up, failed Meta event, and converted lead.
- Add website lead form ingestion.
- Add referral-to-CRM automatic lead creation.
- Add WhatsApp quick action and optional WhatsApp Business API integration.

P2:
- Add saved filters and user-specific CRM dashboard preferences.
- Add export format options beyond CSV.
- Add campaign/form level Meta analytics.
- Add scheduled sync for missed Meta leads.
- Add lead scoring.
- Add SLA policy configuration.

## Development Execution Order

1. Stabilize CRM P0 backend rules.
   - Role policy matrix.
   - Status lifecycle validation.
   - Duplicate detection.
   - Audit log coverage.
   - Meta webhook signature verification.

2. Complete Meta production foundation.
   - Owner Meta settings.
   - Source mapping UI.
   - Failed event retry.
   - Token status and webhook health.

3. Complete role-wise operational workflows.
   - TL team hierarchy.
   - Channel Partner CRM.
   - Assignment rule engine.
   - Lead transfer and reassignment history.

4. Upgrade frontend CRM workspace.
   - Dashboard charts.
   - Advanced list filters.
   - Drag/drop Kanban.
   - Better lead detail action panel.

5. Add reporting and automation.
   - Team performance.
   - Conversion funnel.
   - Source performance.
   - SLA aging.
   - Notifications.

## Current Verification Standard

Before pushing any CRM completion batch:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py test --verbosity 1`

## Release Readiness

The CRM is suitable for internal testing after the current P0 hardening pass. It should not be called production-complete until Meta OAuth/token operations, assignment automation, channel-partner CRM, notification handling, and richer reports are finished and tested.
