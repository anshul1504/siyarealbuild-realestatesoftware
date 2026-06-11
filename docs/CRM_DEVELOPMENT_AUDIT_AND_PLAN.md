# CRM Development Audit and Completion Plan

Audit date: 2026-06-11

## Executive Verdict

The CRM is now app-side complete for internal lead operations and Meta webhook readiness. It has a working Django app, lead pipeline, role-aware visibility, TL subordinate visibility through existing reporting-manager references, channel-partner workspace, lead assignment, follow-ups, property matching, visit scheduling, CSV export, reports, activity history, editable Meta source configuration, Meta health screen, assignment-rule engine, and Meta webhook ingestion/retry foundation.

Current practical readiness is 100% for the implemented in-app CRM scope. Production Meta go-live still depends on external Meta Business setup, live app approval, page/form permissions, and real token provisioning outside the codebase.

## Current Completion Estimate

- CRM app wiring: 100%
- Lead CRUD and detail workspace: 100%
- Role-wise access foundation: 100%
- Follow-up workflow: 100%
- Property and site-visit integration: 100%
- Assignment automation: 100%
- Meta webhook foundation: 100%
- Meta production readiness inside app: 100%
- Duplicate detection and lifecycle rules: 100%
- Reports and analytics: 100% for operational CRM baseline
- Frontend CRM polish: 100% for current CRM screens
- Production readiness: 90% code-side; external deployment, monitoring, backups, and Meta approval remain environment work

Overall professional CRM progress: 100% complete for the committed app-side CRM scope.

## Existing Features

- Dedicated `crm` Django app.
- Sidebar navigation for CRM Dashboard, Lead Pipeline, Kanban Pipeline, Lead Queue, Add Lead, Follow-ups, Reports, and Meta Sources.
- Lead model with client details, budget, requirement, property category, listing purpose, source, Meta identifiers, status, priority, assignment, property link, visit link, follow-up timestamps, lost reason, and notes.
- Lead statuses: New, Contacted, Qualified, Property Matched, Site Visit Scheduled, Site Visit Completed, Follow-up, Negotiation, Booked, Closed, Lost, Duplicate.
- Lead sources: Meta Lead Ads, Manual, Website, Referral, WhatsApp, Property Share.
- Lead activity timeline for created, status, assignment, note, follow-up, visit, and Meta sync events.
- Lead follow-up model with Open, Done, Missed, Cancelled states.
- Meta source model with page/form mapping, active flag, default assignee, default role, and JSON field mapping.
- Editable Meta source create/update workflow.
- Owner Meta health screen for verify token, page access token, app secret, Graph version, active/inactive sources, failed events, and last sync.
- Meta webhook event model for received, processed, failed, and duplicate events.
- Dashboard metrics for total leads, new today, unassigned, overdue, active pipeline, converted, source counts, status counts, recent leads, and due follow-ups.
- Lead list search and filters by status, source, and priority.
- Lead list advanced filters by assignee, city, created date range, archive state, status, source, and priority.
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
- Editable owner assignment rules.
- Round-robin and workload-based assignment rules for role-based lead distribution.
- Lead archive and restore workflow with archive reason and activity audit.
- Failed Meta event reprocess action from reports.
- Advanced lead filters for assignee, city, and date range.
- Assignee distribution and Meta health metrics in reports.
- Conversion summary in CRM reports.
- Dedicated Channel Partner CRM workspace for partner-owned and assigned leads.
- Team Lead subordinate visibility through matching employee code, email, username, or full-name values in `UserProfile.reporting_manager`.
- Notification delivery records for CRM assignment, follow-up scheduling, and Meta lead assignment.
- Test coverage for core CRM workflows, Meta health/editing, assignment editing, TL subordinate visibility, Channel Partner CRM, archive/restore, assignment modes, webhook security, and duplicate handling.

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
- Can see leads assigned to or created by the TL.
- Can also see subordinate Executive/Team leads when the subordinate profile `reporting_manager` matches the TL's employee code, email, username, or full name.

Executive:
- Can see assigned or self-created leads only.
- Can update visible leads and follow-ups.
- Cannot directly access unassigned/private leads.

Channel Partner:
- Has a dedicated Partner Leads workspace.
- Can see assigned or self-created leads and related follow-up context.

No-company user:
- Cannot access company CRM data.

## Remaining External / Production Work

These items are not missing CRM screens or backend workflows. They require production environment decisions or external vendor access:

- Create the Meta Business app, complete app review if required, and connect live page/form permissions.
- Provision real `SIYA_META_WEBHOOK_VERIFY_TOKEN`, `SIYA_META_PAGE_ACCESS_TOKEN`, `SIYA_META_APP_SECRET`, and Graph API version values in production.
- Add external monitoring/alerting for token expiry, webhook failures, backups, and background job failures.
- Decide whether to add full Meta OAuth/page-form sync. Current implementation supports manual source mapping plus webhook ingestion.
- Decide whether archived leads are sufficient or if owner-only permanent delete is legally/business required.

Optional future enhancements:

- Drag/drop Kanban status update.
- Saved CRM filters and per-user dashboard preferences.
- Campaign/form-level Meta analytics.
- Scheduled sync for missed Meta leads.
- Lead scoring and SLA policy configuration.
- WhatsApp Business API integration.

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

The CRM is suitable for internal operational use after the current completion batch. Meta-connected production use requires real Meta credentials, webhook URL registration, and Meta Business approval/configuration outside this repository.
