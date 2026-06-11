# Current Project Status and Full Audit Sheet

Audit date: 2026-06-11

## Executive Status

The project has connected Django workflows for authentication, Company Owner approvals, team management, role access, company settings, referrals, property CRM, client sharing, visits, email notifications, operational owner tools, and dedicated CRM lead management.

The highest-risk area is no longer missing pages. It is consistency across permissions, company scoping, state transitions, audit logs, automated tests, Meta integration reliability, and role-specific CRM boundaries as the feature surface grows.

## Cleanup Status

| Area | Status | Notes |
| --- | --- | --- |
| Runtime Python modules | Clean | Domain logic is split across `accounts/view_modules`, `accounts/url_groups`, `properties/view_modules`, policies, selectors, and services. CRM now follows the same module pattern with dedicated policies, selectors, services, views, forms, and tests. |
| Templates | Clean with review required | Pages are connected to live views. Shared partials exist for pagination, company summary, event forms, support widget, property tables, and CRM screens. |
| Static assets | Cleaned | Unreferenced downloaded/demo `.html` assets under `static/assets/js`, `static/assets/images`, and unused vendor demo folders were removed. Font files referenced by active CSS were intentionally kept. |
| Local/generated files | Guarded | `db.sqlite3`, `db.*.sqlite3`, logs, caches, media, staticfiles, and backups are ignored by Git. Existing local DB backups are treated as local safety files, not source code. |
| Audit documentation | Updated | This file is the current project sheet. `docs/CRM_DEVELOPMENT_AUDIT_AND_PLAN.md` is the dedicated CRM audit and roadmap. |
| Branch hygiene | Partially clean | Local work is on `main`. The stale `agents/property-module-review-fixes` branch may still be present if attached to a linked worktree. |

## Signup and Approval Workflow

- Public signup collects identity, contact details, email verification, and an optional referral code.
- Applicants do not select or request a role.
- The Company Owner must assign a role while reviewing and approving a verified signup.
- Referral rewards activate only when the Company Owner approves the referred signup as Channel Partner.
- Invite and direct Add Employee workflows keep their existing owner-assigned role behavior.

## CRM Status

- Dedicated `crm` app is installed and routed under `/crm/`.
- CRM sidebar navigation is available in the authenticated workspace.
- Lead dashboard, list, kanban, create/edit/detail, assignment, status updates, notes, follow-ups, property matching, visit scheduling, reports, and export are implemented.
- Meta source mapping and webhook ingestion foundation are implemented.
- Meta webhook verification token and optional app-secret signature validation are available through environment settings.
- Duplicate detection covers Meta lead ID, normalized phone, and email.
- CRM activities also write global audit records.
- TL and Executive visibility is restricted to leads they own through assignment or creation unless a higher-level team hierarchy is added later.

## Role-Wise Issues

### Company Owner

- Owner has broad operational control, so destructive actions and approval decisions must consistently create audit records.
- Bulk signup approval cannot safely assign one role to different applicants; individual review is the correct approval path.
- Owner configuration areas should continue to be checked for company scoping and duplicate sources of truth.
- Owner can configure Meta lead sources, but production Meta OAuth/token health UI is still pending.

### Manager

- Manager visibility and mutation permissions need a complete module-by-module policy test matrix.
- Team visibility must remain company-scoped and must not expose owner-only configuration or approval actions.
- Manager can operate CRM leads, assignments, exports, and reports inside company scope.

### Team Lead

- TL CRM visibility is currently restricted to assigned or self-created leads because there is no structured team hierarchy field yet.
- A proper TL team tree is required before TL can safely see subordinate Executive leads.
- Escalation and reassignment workflows need consistent ownership checks.

### Executive

- Executive records and actions should be limited to owned or assigned CRM data.
- Export, bulk action, and client-sharing permissions need regression tests to prevent accidental privilege expansion.
- CRM direct URL tests now cover unassigned/private lead access restrictions.

### Channel Partner

- Referral rewards correctly depend on final approved role, but referral reporting, coupon lifecycle, and duplicate/fraud controls need ongoing review.
- Channel Partner property and lead visibility should be verified against explicit assignment rules.
- Dedicated Channel Partner CRM workflow is still pending.

## Module Audit Sheet

| Module | Implemented | Risk / Gap | Priority | Recommended Check |
| --- | --- | --- | --- | --- |
| Authentication | Login, logout, signup, OTP, support intake, verified invite/email-change paths | Rate limiting and repeated OTP abuse controls should be reviewed before production | P1 | Tests for OTP cooldown, expired OTP, duplicate signup, and support submission |
| Signup approvals | Owner review assigns final role, referral reward activates only after Channel Partner approval | Bulk approval should remain avoided for mixed-role applicants | P1 | Detail-review tests for approve/reject and audit trail |
| Employee invites | Create, list, edit, detail, resend/delete style workflows exist | Invite edit/delete must remain owner/company scoped | P1 | Direct URL permission tests across roles |
| Add Employee | Owner/direct employee creation with OTP gating and code assignment | Welcome email failure handling should be visible to owner/admin | P2 | End-to-end create employee test with email delivery fallback |
| Employee directory | List, detail, edit, bulk update, history | Manager/TL/Executive visibility rules need a full matrix | P0 | Role-by-module permission matrix |
| Role access | Role matrix, role-change requests, approval/review pages | Privilege escalation prevention must be regression-tested | P0 | Direct URL tests for every role and mutation |
| Company settings | Singleton company profile, settings, overview, change history | Sensitive edits must consistently log before/after state | P1 | AuditLog assertions for company changes |
| Owner operations | Audit logs, support queue, office locations, notification deliveries | Duplicate configuration sources should be watched as features grow | P2 | Queryset company-scope tests |
| Marketing tools | Events, meetings, popups, targets, referrals | Delivery status and audience scoping should be tested | P2 | NotificationDelivery and role audience tests |
| Property CRM | Dashboard, list, create/edit/detail, plot drilldown, visits, bulk actions, sharing, service-layer create/update/bulk lifecycle audit | Assigned-record scoping and export permissions are highest risk | P0 | View/create/update/delete/export permission tests |
| Lead CRM | Dashboard, list, kanban, create/edit/detail, assignment, bulk actions, follow-ups, property matching, visit scheduling, Meta webhook foundation, reports, export, audit activity | Meta OAuth, assignment rules, TL hierarchy, Channel Partner CRM, notifications, retry queue, and richer analytics remain | P0 | CRM role matrix, Meta webhook, duplicate, lifecycle, export, and direct URL tests |
| Email system | Shared notification templates and delivery helper | Background retry/queue strategy is not production-grade yet | P2 | Failure-path tests and operational alerting plan |
| Admin | Django admin available with project models | Admin destructive actions should be restricted in production | P2 | Staff permission review and deploy checklist |
| Error handling | Custom error pages and handler views | Monitoring and exception reporting are not yet a full production stack | P2 | Sentry/log aggregation decision before go-live |

## Security and Permission Audit

| Aspect | Current Position | Required Before Production |
| --- | --- | --- |
| Authentication | OTP and login flows exist | Add/verify rate limits, lockouts, and suspicious activity logging |
| Authorization | Role helpers and policies exist | Complete role-by-module tests for list/detail/create/update/delete/export/bulk/direct URL |
| Company scoping | Many querysets are company-scoped | Audit every operational queryset and add tests where data crosses modules |
| Assigned-record scoping | Property, visit, and CRM workflows have assignment concepts | Confirm TL/Executive/Channel Partner boundaries explicitly |
| Meta webhook security | Verify-token and optional app-secret signature validation exist | Add full OAuth/token lifecycle and webhook health monitoring |
| Audit logs | Core audit model exists and CRM activity writes global audit rows | Enforce logs for approvals, rejections, role changes, deletes, and sensitive config edits |
| File uploads/media | Profile/company media support exists | Validate file type/size and production storage settings |
| Secrets/config | `.env` patterns are ignored | Confirm production `DEBUG=False`, hosts, CSRF, email, Meta, and database env vars |

## Testing Audit

| Test Area | Status | Gap |
| --- | --- | --- |
| Django system check | Required after cleanup | Must stay green after every architecture change |
| Migrations | Required after model changes | Run `makemigrations --check --dry-run` before release |
| Unit/workflow tests | Account, property, and CRM tests present | Needs broader permission matrix |
| UI smoke | Templates are connected | Browser smoke is still useful after major visual changes |
| Production checks | Not enough alone | Add backup, monitoring, background jobs, and security header verification |

## Code Health Status

| Area | Current State | Remaining Work |
| --- | --- | --- |
| Branches | `main` is the active local branch and tracks `origin/main`. | Remove any stale linked worktree branch only when no longer needed. |
| Accounts module | Split into URL groups, view modules, services, policies, and shared audit helpers. | Add a complete permission matrix for role-specific direct URL access. |
| Properties module | Property create/update/bulk status/delete goes through service-layer lifecycle/audit paths, and bulk action requires login. | Continue with assigned-record scoping, export controls, and property permission matrix. |
| CRM module | Dedicated app with models, forms, views, selectors, policies, services, templates, admin, migration, and tests. | Complete production Meta OAuth, assignment automation, Channel Partner CRM, notifications, and advanced analytics. |
| Core/config module | Minimal config, URLs, settings, error handlers. | Production settings review remains before deployment. |
| Static assets | Demo/downloaded unused HTML assets removed. | Keep vendor font files unless CSS is replaced with proper font extensions. |

## Recommended Backlog

1. Complete the CRM production phase: Meta OAuth/token health, failed-event retry, assignment rules, TL hierarchy, Channel Partner CRM, notifications, and richer reports.
2. Complete the property module permission matrix for view, create, update, delete, export, bulk actions, share email, visits, and direct URL access.
3. Audit every property and CRM queryset for company scoping and assigned-record scoping.
4. Build the broader role-by-module permission test matrix for Accounts, Owner operations, Properties, and CRM.
5. Ensure all approvals, rejections, role changes, bulk deletes, sensitive configuration edits, and CRM conversions write audit logs.
6. Add end-to-end tests for signup, owner role assignment, referral reward activation, invite onboarding, role changes, and CRM lead conversion.
7. Add production readiness checks for backups, monitoring, email failure handling, background jobs, rate limits, Meta token health, and security headers.

## Release Readiness Verdict

Not production-ready yet. The app is feature-complete enough for internal testing, but production readiness requires permission-matrix coverage, queryset scoping verification, audit-log completeness, email failure handling, monitoring, backups, Meta OAuth/token health, background job strategy, and final deploy checks.
