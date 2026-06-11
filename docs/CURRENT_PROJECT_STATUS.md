# Current Project Status and Full Audit Sheet

Audit date: 2026-06-11

## Executive Status

The project has connected Django workflows for authentication, Company Owner approvals, team management, role access, company settings, referrals, property CRM, client sharing, visits, email notifications, and operational owner tools.

The highest-risk area is no longer missing pages. It is consistency across permissions, company scoping, state transitions, audit logs, and automated tests as the feature surface grows.

## Cleanup Status

| Area | Status | Notes |
| --- | --- | --- |
| Runtime Python modules | Clean | Domain logic is split across `accounts/view_modules`, `accounts/url_groups`, `properties/view_modules`, policies, selectors, and services. No legacy route dependency on `accounts/views.py` is expected. |
| Templates | Clean with review required | Pages are connected to live views. Shared partials exist for pagination, company summary, event forms, support widget, and property tables. |
| Static assets | Cleaned | Unreferenced downloaded/demo `.html` assets under `static/assets/js`, `static/assets/images`, and unused vendor demo folders were removed. Font files referenced by active CSS were intentionally kept. |
| Local/generated files | Guarded | `db.sqlite3`, `db.*.sqlite3`, logs, caches, media, staticfiles, and backups are ignored by Git. Existing local DB backups are treated as local safety files, not source code. |
| Audit documentation | Updated | This file is the current audit sheet. The deleted legacy `ARCHITECTURE_AUDIT.md` should not be restored unless a separate historical audit is needed. |
| Branch hygiene | Partially clean | Local work is now on `main`, aligned with `origin/main`. The stale `agents/property-module-review-fixes` branch is still present because it is attached to a linked worktree. |

## Signup and Approval Workflow

- Public signup collects identity, contact details, email verification, and an optional referral code.
- Applicants do not select or request a role.
- The Company Owner must assign a role while reviewing and approving a verified signup.
- Referral rewards activate only when the Company Owner approves the referred signup as Channel Partner.
- Invite and direct Add Employee workflows keep their existing owner-assigned role behavior.

## Role-Wise Issues

### Company Owner

- Owner has broad operational control, so destructive actions and approval decisions must consistently create audit records.
- Bulk signup approval cannot safely assign one role to different applicants; individual review is the correct approval path.
- Owner configuration areas should continue to be checked for company scoping and duplicate sources of truth.

### Manager

- Manager visibility and mutation permissions need a complete module-by-module policy test matrix.
- Team visibility must remain company-scoped and must not expose owner-only configuration or approval actions.

### Team Lead

- TL access should be explicitly limited to assigned team data where applicable, rather than relying only on broad role checks.
- Escalation and reassignment workflows need consistent ownership checks.

### Executive

- Executive records and actions should be limited to owned or assigned CRM data.
- Export, bulk action, and client-sharing permissions need regression tests to prevent accidental privilege expansion.

### Channel Partner

- Referral rewards correctly depend on final approved role, but referral reporting, coupon lifecycle, and duplicate/fraud controls need ongoing review.
- Channel Partner property and lead visibility should be verified against explicit assignment rules.

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
| Email system | Shared notification templates and delivery helper | Background retry/queue strategy is not production-grade yet | P2 | Failure-path tests and operational alerting plan |
| Admin | Django admin available with project models | Admin destructive actions should be restricted in production | P2 | Staff permission review and deploy checklist |
| Error handling | Custom error pages and handler views | Monitoring and exception reporting are not yet a full production stack | P2 | Sentry/log aggregation decision before go-live |

## Security and Permission Audit

| Aspect | Current Position | Required Before Production |
| --- | --- | --- |
| Authentication | OTP and login flows exist | Add/verify rate limits, lockouts, and suspicious activity logging |
| Authorization | Role helpers and policies exist | Complete role-by-module tests for list/detail/create/update/delete/export/bulk/direct URL |
| Company scoping | Many querysets are company-scoped | Audit every operational queryset and add tests where data crosses modules |
| Assigned-record scoping | Property and team workflows have assignment concepts | Confirm TL/Executive/Channel Partner boundaries explicitly |
| Audit logs | Core audit model exists | Enforce logs for approvals, rejections, role changes, deletes, and sensitive config edits |
| File uploads/media | Profile/company media support exists | Validate file type/size and production storage settings |
| Secrets/config | `.env` patterns are ignored | Confirm production `DEBUG=False`, hosts, CSRF, email, and database env vars |

## Testing Audit

| Test Area | Status | Gap |
| --- | --- | --- |
| Django system check | Required after cleanup | Must stay green after every architecture change |
| Migrations | Required after model changes | Run `makemigrations --check --dry-run` before release |
| Unit/workflow tests | Existing account/property tests present | Needs broader permission matrix |
| UI smoke | Templates are connected | Browser smoke is still useful after major visual changes |
| Production checks | Not enough alone | Add backup, monitoring, background jobs, and security header verification |

## Code Health Status

| Area | Current State | Remaining Work |
| --- | --- | --- |
| Branches | `main` is the active local branch and tracks `origin/main`. | Remove the linked worktree before deleting `agents/property-module-review-fixes`. |
| Accounts module | Split into URL groups, view modules, services, policies, and shared audit helpers. | Add a complete permission matrix for role-specific direct URL access. |
| Properties module | Started hardening. Property create/update/bulk status/delete now goes through service-layer lifecycle/audit paths, and bulk action requires login. | Continue with assigned-record scoping, export controls, and property permission matrix. |
| Core/config module | Minimal config, URLs, settings, error handlers. | Production settings review remains before deployment. |
| Static assets | Demo/downloaded unused HTML assets removed. | Keep vendor font files unless CSS is replaced with proper font extensions. |

## Recommended Backlog

1. Complete the property module permission matrix for view, create, update, delete, export, bulk actions, share email, visits, and direct URL access.
2. Audit every property queryset for company scoping and assigned-record scoping.
3. Build the broader role-by-module permission test matrix for Accounts and Owner operations.
4. Ensure all approvals, rejections, role changes, bulk deletes, and sensitive configuration edits write audit logs.
5. Add end-to-end tests for signup, owner role assignment, referral reward activation, invite onboarding, and role changes.
6. Add production readiness checks for backups, monitoring, email failure handling, background jobs, rate limits, and security headers.

## Release Readiness Verdict

Not production-ready yet. The app is feature-complete enough for internal testing, but production readiness requires permission-matrix coverage, queryset scoping verification, audit-log completeness, email failure handling, monitoring, backups, and final deploy checks.
