# Siya Real Build Architecture and Development Audit

Status: active development baseline  
Audit scope: implemented functionality, maintainability, workflow gaps, and development readiness

## Current Baseline

- Django checks and migration consistency pass.
- The automated suite covers 51 core scenarios.
- Existing modules include authentication, signup approval, team onboarding, role and email change requests, company master, properties, visits, meetings, events, referrals, targets, popups, and support intake.
- Company-scoped access and owner/manager workflow rules exist, but authorization is repeated across controllers.

## Architecture Findings

### P0 - Functional Integrity

- Add audit logging for destructive and approval actions. Employee deletion currently removes linked operational history without a durable actor/action log.
- Add transaction boundaries around multi-model onboarding, approval, role-change, email-change, and deletion workflows.
- Define a single authorization policy layer. Role checks are repeated in views and can drift between list, detail, and action endpoints.
- Add explicit lifecycle rules for records linked to deleted employees. Decide which records must be retained, anonymized, or removed.

### P1 - Core Workflow Gaps

- Add owner-side employee profile editing with controlled fields and change history.
- Add office-location master management instead of deriving locations only from company text fields.
- Add bulk department/reporting-manager updates with preview and audit history.
- Add reject/reopen actions and review notes consistently across invite and approval queues.
- Add property lifecycle/status history and ownership assignment workflow.
- Add visit follow-up outcomes, reminders, and conversion linkage.
- Add notification delivery state and retry visibility for operational emails.

### P1 - Structure and Maintainability

- Split `accounts/views.py` by domain: auth, company, team, invites, access, requests, communications, and owner operations.
- Split `accounts/forms.py`, `accounts/models.py`, and `accounts/tests.py` along the same boundaries.
- Move side-effect-heavy workflows from models/views into service functions with transactions.
- Create query/selectors for company-scoped list visibility and reusable filters.
- Split the shared CSS file into base, layout, components, and feature-level styles after visual regression coverage exists.

### P2 - Quality and Development Tooling

- Add browser-level tests for responsive navigation, tables, forms, modals, and critical owner workflows.
- Add test factories to reduce repeated user/company/profile setup.
- Add CI checks for Django checks, migration drift, tests, formatting, and static analysis.
- Remove the tracked `demo/` tree after a reference audit confirms no runtime dependencies.
- Add structured application logging and a development error-reporting convention.

## Target Architecture

Keep the existing Django apps while introducing internal domain boundaries:

```text
accounts/
  auth/
  company/
  team/
  access/
  communications/
  owner_operations/
  services/
  selectors/
  policies/
properties/
  services/
  selectors/
  policies/
templates/
  accounts/<domain>/
  properties/
static/
  css/base/
  css/components/
  css/features/
```

Each domain should expose:

- `views.py`: HTTP input/output only
- `forms.py`: validation and input normalization
- `services.py`: transactional state changes and side effects
- `selectors.py`: optimized read queries and visibility rules
- `policies.py`: reusable authorization decisions
- `tests/`: unit, permission, workflow, and integration coverage

## Delivery Phases

1. Stabilize authorization policies, transactions, and audit logging.
2. Complete team operations: employee edit, office locations, bulk updates, and queue lifecycle actions.
3. Complete property and visit lifecycle workflows.
4. Extract domain modules and split CSS with regression tests.
5. Add CI, browser responsiveness tests, observability, and deployment readiness.

## Changes Completed In This Audit Phase

- Added the missing pending-invite edit workflow.
- Locked approved invites from editing.
- Reset verification and send a fresh OTP when an invite email changes.
- Preserved company and role scope during invite editing.
