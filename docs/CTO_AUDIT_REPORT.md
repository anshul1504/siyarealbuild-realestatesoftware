# Siya Real Build - CTO-Level Technical, Product, Business, Security, and Readiness Audit

Audit date: 2026-06-13  
Audit basis: current local source tree, Django system checks, migration drift check, role/route smoke checks, and automated test run.

## 2026-06-14 Deep Audit Update

The current candidate release passed repository-wide checks after two additional core business safeguards were implemented:

- Active plot booking creation and owner approval now lock and reject a second booked/converted booking for the same plot.
- Booking payments now reject amounts above the booking's remaining balance even when no installment is selected.

Verification: `python manage.py check` passed; migration drift check passed; all 153 requested tests passed; compileall and `git diff --check` passed. Ruff is not installed. `check --deploy` reports the six expected local-development warnings documented in the external backlog.

## 2026-06-14 Product-Ready AWS Handoff Update

Repository-side deployment readiness now includes Docker/Gunicorn, PostgreSQL runtime support, production-only WhiteNoise manifest static assets, a database-backed health endpoint, GitHub Actions CI, stricter production environment validation, and an AWS ECS/RDS/EFS/ALB deployment runbook.

The next phase is infrastructure execution, not core product development. Live launch remains conditional on real AWS provisioning, production `check --deploy`, migrations, domain/HTTPS/email verification, persistent media verification, monitoring, and restore drills.

## 0. Core Completion Update - 2026-06-13

Current core development status: **100% complete for internal beta CRM/property operations scope**.

This completion statement covers the agreed internal core workflows: onboarding/roles, company/team operations, property and colony inventory, plot finder, quotation and booking workflow, coupon discount capture, installment/payment ledger, booking agreement lifecycle, site visits, CRM lead lifecycle, assignment rules, owner MIS reporting, referral payout actions, role-wise commission rules, and property commission payout ledger.

Latest verification:

| Check | Result |
| --- | --- |
| `python manage.py makemigrations --check --dry-run` | Passed: no changes detected. |
| `python manage.py migrate` | Passed through current migrations including `properties.0019_plotbooking_coupon_code_and_more`. |
| `python manage.py check` | Passed: no issues. |
| Owner route smoke | Passed: key dashboard/property/CRM/team/owner routes returned OK for owner context. |
| `python manage.py test accounts properties crm config --verbosity 1` | Passed: 144 tests. |

Important boundary: external production/SaaS readiness is still separate from internal core completion. CI/CD, browser E2E, formal REST/mobile API, external Meta app/token setup, production HTTPS/host/secrets, monitoring, and real production backup drills remain outside this internal completion scope.

Frontend core update:

| Surface | Status |
| --- | --- |
| Owner MIS report | Updated with commission payable, paid/unpaid totals, document status, and commission status. |
| Property detail | Updated with role-wise commission rules so booking payout setup is visible before sale flow. |
| Plot detail | Updated booking ledger surface with commission payout controls, installments, payments, agreements, and registry documents. |
| Plot Finder | Added direct colony/project + plot number search with detail, quotation, booking, and visit actions. |
| Navigation | Sidebar now exposes Plot Finder, Quotation & Booking, Site Visit Management, Commission Management, and Payout Ledger. |
| UI polish | Toast encoding artifacts were normalized to ASCII status labels. |

Security hardening update:

| Area | Status |
| --- | --- |
| SMTP credentials | Removed hard-coded SMTP password/user defaults from settings and `.env.example`. |
| Local email | Defaults to Django console email backend for safe local OTP testing. |
| Production validation | `SIYA_ENV=production` now fails fast if debug, secret key, hosts, database URL, SMTP, or HTTPS settings are unsafe/missing. |
| Production database | `SIYA_DATABASE_URL` supports PostgreSQL URLs for production deployment configuration. |
| Regression tests | Added production settings validation tests under `config/tests.py`. |

Backup/restore update:

| Area | Status |
| --- | --- |
| Local backup command | Added `python manage.py backup_workspace` for SQLite, media, manifest, and checksum bundles. |
| Restore guidance | Backup manifest includes restore notes; README documents backup/restore usage. |
| Verification | Added management-command regression coverage in `config/tests.py`. |

## 1. Executive Summary

| Item | Assessment |
| --- | --- |
| Project name | Siya Real Build |
| Purpose | Internal real estate operations platform covering onboarding, team management, property inventory, site visits, CRM leads, Meta lead ingestion, referrals, events, meetings, and owner controls. |
| Target audience | Real estate company owners, managers, team leads, executives, channel partners, and operations staff. |
| User roles | Company Owner, Manager, TL, Executive, Channel Partner, Django admin/superuser. |
| Business model fit | Internal CRM/ERP first; can support investor demos and controlled internal rollout, but not production SaaS without hardening. |
| Software category | Real Estate CRM + lightweight ERP/workflow system. |
| Current development stage | Beta / pre-production for single-company internal use. Not production-ready for public SaaS. |

### Scores

| Area | Score | Reason |
| --- | ---: | --- |
| Project health | 92/100 | Internal core workflows are implemented and regression tested; external production readiness remains separate. |
| Technical score | 86/100 | Services/selectors/policies cover the important workflow boundaries; large templates/files remain maintainability debt. |
| Product score | 90/100 | Internal real estate CRM/property workflows are now complete for beta usage. |
| Business readiness | 84/100 | Demo and controlled internal operations are ready; production operations and compliance hardening remain. |
| Production readiness | 72/100 | Production settings fail closed and backup tooling exists; real deployment, monitoring, CI/E2E, and external integrations remain. |

**Verdict:** approve for investor demo and controlled internal beta. Do not approve for public production/SaaS launch until deployment, monitoring, CI/E2E, private media/security hardening, and external integration setup are complete.

## 2. Project Structure Audit

| Area | Evidence | Assessment |
| --- | --- | --- |
| Apps/modules | `accounts`, `properties`, `crm`, `config` | Clear domain split. Good foundation. |
| View organization | `accounts/view_modules/*`, `properties/view_modules/*`, `crm/views.py` | Accounts/properties have started decomposing large views; CRM still centralizes many workflows in one view file. |
| URLs | `accounts/url_groups/*`, `properties/urls.py`, `crm/urls.py` | Good route grouping for accounts; CRM/property routes are readable. |
| Models | `accounts/models.py`, `properties/models.py`, `crm/models.py` | Rich domain model, but large model files and mixed business logic remain. |
| Services/selectors/policies | Present in all major apps | Strong positive: core workflow logic is moving out of views. |
| Templates | `templates/accounts`, `templates/properties`, `templates/crm`, `templates/base.html` | Extensive server-rendered UI. Large `base.html` and inline page JS/CSS reduce maintainability. |
| Static assets | `static/assets/css/siya-auth.css`, vendor libs | Responsive guards exist, but one CSS file is very large and has repeated/overriding sidebar rules. |

Architecture quality score: **7.5/10**

Recommended improvements:

| Priority | Improvement | Reason |
| --- | --- | --- |
| P1 | Split `accounts/models.py` and large view/template scripts by domain. | Current files are workable but expensive to review and extend. |
| P1 | Keep all business transitions in services and make views thin. | Some model methods and views still perform workflow side effects directly. |
| P2 | Move inline template JS/CSS into versioned static modules. | Better cacheability, testability, and frontend maintainability. |
| P2 | Add architecture docs back under `docs/`. | Current tree shows deleted project docs; roadmap/audit history should be preserved intentionally. |

## 3. Database Audit

| Strength | Evidence |
| --- | --- |
| Meaningful relationships | Company, profiles, properties, plots, visits, leads, activities, follow-ups, assignment rules, rewards. |
| Constraints | Singleton company profile, unique employee code per company, unique plot number per property, unique Meta webhook event, lead indexes. |
| Auditability | `AuditLog`, `LeadActivity`, status-history models, notification-delivery records. |

| Risk | Evidence | Impact | Priority |
| --- | --- | --- | --- |
| SQLite local default | Local development falls back to SQLite; production mode requires `SIYA_DATABASE_URL`. | Good for local work; production still needs a real PostgreSQL instance and deployment proof. | High |
| Sensitive fields not encrypted | Profile documents, IDs, bank details stored via normal model fields/files. | Compliance and data-exposure risk. | High |
| Partial indexing | CRM leads have useful indexes; many dashboard/filter fields across accounts/properties lack explicit indexes. | Slower dashboards at scale. | Medium |
| Redundant property category fields | `category` and `property_type` mirror each other in `Property.save()`. | Data drift risk if bypassed or bulk-updated. | Medium |

Database quality score: **7/10**

## 4. Feature Inventory

| Module | Feature | Status | Completion % | Notes |
| --- | --- | --- | ---: | --- |
| Accounts | OTP login | Complete | 90 | Has hashed OTP, expiry, rate-limit tests. |
| Accounts | Public signup + owner approval | Complete | 90 | Owner assigns approved role; duplicate/pending flows tested. |
| Accounts | Employee invite onboarding | Complete | 88 | OTP verification, approval, resend, edit, delete, bulk actions covered. |
| Accounts | Team directory | Complete | 85 | Role-scoped visibility, masked sensitive data, export, bulk update/delete. |
| Accounts | Role/access matrix | Partial | 70 | Rules exist for modules, but not a full enterprise permission engine. |
| Accounts | Company master | Complete | 85 | Singleton company, settings, export, history. |
| Accounts | Events/meetings | Partial | 70 | Internal workflow exists; calendar/deep reminders are limited. |
| Accounts | Referrals | Partial | 75 | Referral reward and payout actions exist; commission settlement is not full accounting. |
| Accounts | Support system | Partial | 65 | Intake and owner status update exist; no SLA/chat/ticket lifecycle depth. |
| Properties | Category property directory | Complete | 85 | Category-aware listings and creation flow. |
| Properties | Colony plot inventory | Complete | 85 | Plots, pricing, PLC, status history, quotations/bookings. |
| Properties | Media/documents | Partial | 70 | Upload models exist; document lifecycle/versioning/security is limited. |
| Properties | Site visits | Complete | 82 | Visit CRUD, assignment visibility, conversion flags. |
| Properties | Property sharing | Partial | 70 | Email share flow exists; no public portal/client tracking depth. |
| Properties | Commission rules | Complete | 88 | Owner/manager role-wise percentage, fixed amount, and per-sqft rules with booking payout ledger. |
| CRM | Lead lifecycle | Complete | 85 | Create/edit/status/archive/restore/activity/follow-up. |
| CRM | Assignment engine | Complete | 82 | Rules for source/city/category/round-robin/workload. |
| CRM | Meta lead ingestion | Partial | 75 | Webhook, signature check, mapping, dedupe, reprocess; production token/app setup external. |
| CRM | Reports/export | Partial | 65 | Basic reports/export; no advanced MIS/funnel analytics. |
| API | REST API | Missing | 10 | App is server-rendered; no DRF/API layer found. |
| DevOps | Deployment pipeline | Missing | 20 | No CI/CD, Docker, backup/monitoring scripts observed. |
| Testing | Automated tests | Complete for core workflows | 84 | 144 tests pass; browser E2E/security/performance coverage is still external hardening. |

## 5. Real Estate Domain Gap Analysis

| Domain capability | Current status | Gap |
| --- | --- | --- |
| Residential/commercial/land listings | Strong | Good category coverage. |
| Colony inventory tracking | Strong | Plot-level lifecycle present. |
| Lead capture/assignment/follow-up | Strong | Meta + manual + assignment rules implemented. |
| Site visits | Strong | Scheduling and conversion status exist. |
| Booking management | Strong | Plot booking, coupon discount, installment, payment, agreement, and commission payout surfaces exist. |
| Installment tracking | Strong | Installment schedule and paid/balance status are implemented. |
| Payment tracking | Strong | Booking payment ledger and balance recalculation are implemented. |
| Broker/agent CRM | Partial | Channel partner role exists; broker ledger and lifecycle missing. |
| Commission management | Strong | Role-wise rules, booking snapshots, payout status, and owner MIS totals exist. |
| Legal documents/agreements | Strong for internal beta | Booking agreement/registry document lifecycle exists; e-signature remains external/future. |
| MIS reports | Strong for internal beta | Owner MIS export/snapshot flow exists; advanced BI remains future. |
| Occupancy/availability | Partial | Availability/status for property/plots; occupancy workflows missing. |

## 6. Missing Features Analysis

### Critical Missing Features

| Feature | Business impact | Priority | Complexity | Effort |
| --- | --- | --- | --- | --- |
| Production deployment execution | Required before public launch. | External | Medium | Future deployment phase |
| CI/browser E2E | Prevents UI regressions in release process. | External | Medium | Future QA phase |
| Private media and PII encryption policy | Needed for compliance-grade document storage. | High | Medium | Future security phase |
| REST/mobile API | Required only if mobile app/external clients are planned. | External | High | Future API phase |

### Important Missing Features

| Feature | Impact | Priority | Complexity | Effort |
| --- | --- | --- | --- | --- |
| File upload validation/storage policy | Protects documents and media. | High | Medium | 2-4 days |
| Audit log expansion | Compliance and accountability. | Medium | Medium | 3-5 days |
| Advanced MIS/funnel analytics | Owner decision-making beyond internal beta. | Medium | Medium | Future BI phase |

### Nice-To-Have Features

| Feature | Impact | Priority | Complexity | Effort |
| --- | --- | --- | --- | --- |
| WhatsApp/SMS integrations | Better lead conversion. | Medium | Medium | 1-2 weeks |
| Mobile app/API | Field team productivity. | Medium | High | 1-2 months |
| Client portal | Better buyer experience. | Medium | High | 1-2 months |
| AI lead scoring | Growth optimization. | Low | Medium | 1-2 weeks |

## 7. Frontend Audit

Frontend quality score: **7/10**  
UX score: **7.2/10**

| Strength | Evidence |
| --- | --- |
| Full internal dashboard shell | `templates/base.html` has sidebar, header, profile, support widget, role-gated navigation. |
| Responsive guardrails | `static/assets/css/siya-auth.css` includes shared containment and mobile sidebar handling. |
| Real workflow screens | Property wizard, CRM lead detail, team/owner screens, visits, reports. |

| Issue | Evidence | Risk |
| --- | --- | --- |
| Large base template | Navigation, modals, support widget, and many scripts in one file. | Hard to test and maintain. |
| Inline page JS/CSS | `property_form.html` has significant embedded wizard logic. | Regression risk and poor cacheability. |
| Encoding artifacts | Resolved in `base.html` toast UI. | Closed. |
| Accessibility gaps | Icon-only controls and custom menus need deeper keyboard/focus validation. | Medium compliance risk. |

## 8. API Audit

API quality score: **3/10**

The project is primarily server-rendered Django. It has form endpoints, JSON helper endpoints for OTP/add-employee actions, and a Meta webhook endpoint, but no formal REST/GraphQL API layer, OpenAPI schema, API auth strategy, versioning, pagination contract, or client SDK surface.

| Area | Status |
| --- | --- |
| Internal form endpoints | Implemented |
| Meta webhook | Implemented with signature verification when secret is configured |
| REST API | Missing |
| API pagination/filtering contract | Missing |
| API error contract | Missing |

## 9. Security Audit

Security score: **6.2/10**

| Severity | Finding | Evidence | Recommendation |
| --- | --- | --- | --- |
| Resolved | SMTP password default in source/config example | Settings and `.env.example` no longer contain the exposed password fallback. | Rotate any previously exposed real credential outside the repo. |
| Mitigated | Debug defaults to true for local mode | Production mode fails if `SIYA_DEBUG=true`. | Keep local convenience, enforce production fail-closed. |
| Mitigated | Production HTTPS controls default off | Production mode fails unless SSL redirect, secure cookies, and HSTS are enabled. | Verify with `check --deploy` in deployment. |
| Mitigated | SQLite default | Local mode uses SQLite; production mode requires PostgreSQL URL. | Provision and test production PostgreSQL. |
| Medium | File uploads need stronger validation/storage policy | Documents/images stored under media with limited observed central validation. | Validate type/size, use private storage for ID/legal docs. |
| Medium | CSRF-exempt webhook | `crm.views.meta_webhook` is `csrf_exempt`. | Acceptable for webhooks only with mandatory signature in production and logging. |
| Medium | PII exposure risk | Aadhaar/PAN/bank/profile docs present. | Encrypt sensitive fields or strict access controls/audits. |

Positive security notes:

| Control | Evidence |
| --- | --- |
| OTP hashed at rest | `EmailOTP` uses `make_password` / `check_password`; tests cover it. |
| Role-scoped data access | `accounts/policies.py`, `properties/policies.py`, `crm/policies.py`. |
| CSRF on normal forms | Templates use `{% csrf_token %}`. |
| Clickjacking/content sniffing controls | `X_FRAME_OPTIONS = "DENY"`, `SECURE_CONTENT_TYPE_NOSNIFF = True`. |

## 10. Performance Audit

Performance score: **6.5/10**

| Strength | Risk |
| --- | --- |
| Some query optimization and indexes exist in CRM. | Dashboard/report queries may degrade without more indexes and query profiling. |
| Server-rendered Django is simple and cheap to host. | Large templates and static CSS/JS bundles may grow without asset discipline. |
| Exports exist. | Large CSV/export actions may time out without async jobs. |

Recommendations:

| Priority | Recommendation |
| --- | --- |
| P1 | Add `select_related`/`prefetch_related` audits for list/detail dashboards. |
| P1 | Add database indexes for common property filters: company/owner/assigned/status/category/is_archived/city. |
| P2 | Move large exports/email sends to background jobs. |
| P2 | Add page response time tests for key pages with seeded data. |

## 11. Code Quality Audit

Code quality score: **8.2/10**

| Positive | Concern |
| --- | --- |
| Meaningful domain names and Django conventions. | Very large model/test/template files. |
| Services/selectors/policies are present. | Business side effects still exist in models and views. |
| Tests cover many workflows. | `ruff` could not run in this local environment because the package is not installed. |
| README has clear local commands. | External CI/E2E enforcement is still future work. |

## 12. Testing Audit

Testing readiness score: **8.4/10**  
Estimated automated coverage by risk area: **80-85% of core backend workflows**, lower for browser E2E/security/performance.

Verification run:

| Check | Result |
| --- | --- |
| `python manage.py check` | Passed: no issues. |
| `python manage.py makemigrations --check --dry-run` | Passed: no changes detected. |
| Owner route smoke | Passed: main owner/property/CRM/team routes returned OK. |
| `python manage.py test accounts properties crm config --verbosity 1` | Passed: 144 tests. |

Gaps:

| Gap | Impact |
| --- | --- |
| No browser/E2E tests for property wizard/sidebar/CRM screens. | UI regressions can pass backend tests. |
| Browser E2E tests are not present. | Complex UI regressions can pass backend tests. |
| No performance/load tests. | Scale readiness unproven. |
| No CI observed. | Tests depend on local discipline. |

## 13. DevOps & Deployment Audit

DevOps score: **6.5/10**

| Area | Status |
| --- | --- |
| Environment variables | Strong for local/internal: production mode fails closed for unsafe settings. |
| Production DB | Configured by env: production mode requires PostgreSQL URL. |
| Static/media deployment | Partial: `STATIC_ROOT`/`MEDIA_ROOT` configured. |
| CI/CD | Missing in inspected tree. |
| Docker/process manager | Missing in inspected tree. |
| Monitoring/log aggregation | Missing beyond console logging. |
| Backups | Missing. |
| HTTPS/security headers | Configurable but default off. |

## 14. Project Completion Analysis

| Area | Completion | Reason |
| --- | ---: | --- |
| Backend | 82% | Major workflows implemented and tested. Missing payment/legal/accounting depth. |
| Frontend | 74% | Broad screens implemented; needs E2E, accessibility, and maintainability work. |
| Database | 76% | Rich schema, but production DB/index/security work pending. |
| API | 15% | No formal API layer. |
| Security | 62% | Auth/authorization good, but secret/default/PII/upload production risks. |
| Testing | 72% | Strong unit/integration tests; no E2E/performance/security CI layer. |
| Feature completion | 73% | Internal CRM/property/team workflows strong; transaction/accounting/legal missing. |
| DevOps | 45% | Local readiness good; production operations missing. |
| Overall project completion | 72% | Real beta product, not production enterprise platform. |

## 15. Technical Debt Report

| Debt level | Item | Effort |
| --- | --- | --- |
| Critical | Remove committed/default secrets and add production env validation. | 0.5-1 day |
| Critical | Add PostgreSQL/env database support and deployment profile. | 1-2 days |
| Major | Split large templates/scripts/CSS into reusable assets. | 1-2 weeks |
| Major | Move remaining business side effects to services. | 1 week |
| Major | Add E2E/CI pipeline. | 1 week |
| Minor | Normalize encoding artifacts and UI text consistency. | 0.5-1 day |
| Minor | Recreate/restore docs intentionally. | 0.5-1 day |

## 16. Product Roadmap

### Phase 1 - Must Have Features

| Item | Priority | Impact | Effort | Timeline |
| --- | --- | --- | --- | --- |
| Secret rotation/settings hardening | Critical | Launch safety | Low | 1 day |
| PostgreSQL + backup + deploy checklist | Critical | Production baseline | Medium | 3-5 days |
| Payment/installment ledger | Critical | Real estate transaction readiness | High | 2-4 weeks |
| Legal document lifecycle | Critical | Compliance/sales readiness | High | 2-4 weeks |
| CI + E2E smoke tests | High | Release confidence | Medium | 1 week |

### Phase 2 - Growth Features

| Item | Priority | Impact | Effort | Timeline |
| --- | --- | --- | --- | --- |
| Advanced MIS reports | High | Owner decisions | Medium | 1-2 weeks |
| WhatsApp/SMS lead engagement | High | Conversion | Medium | 1-2 weeks |
| Commission payout ledger | High | Partner management | Medium | 1-2 weeks |
| Client sharing portal tracking | Medium | Sales enablement | High | 2-4 weeks |

### Phase 3 - Advanced Features

| Item | Priority | Impact | Effort | Timeline |
| --- | --- | --- | --- | --- |
| Mobile app/API | Medium | Field productivity | High | 1-2 months |
| SaaS multi-tenant architecture | Medium | Commercial expansion | Very high | 2-4 months |
| AI lead scoring | Low | Optimization | Medium | 1-2 weeks |

## 17. SWOT Analysis

| Strengths | Weaknesses |
| --- | --- |
| Broad real estate-specific workflow coverage. | Production/devops hardening incomplete. |
| Passing backend test suite. | No formal API, CI, E2E, or performance tests. |
| Clear role model and owner controls. | Sensitive production defaults in settings/example. |
| CRM + property + onboarding in one internal workspace. | Large templates/CSS/model files increase maintenance cost. |

| Opportunities | Threats |
| --- | --- |
| Can become a strong internal ERP for small/mid real estate teams. | Credential exposure or weak deployment can block acquisition/investment. |
| Meta lead integration gives practical acquisition channel. | Competitors with accounting/legal/mobile workflows may appear more complete. |
| Channel partner/referral expansion possible. | Without payment/legal modules, it remains CRM-heavy rather than full ERP. |

## 18. Final CTO Verdict

| Readiness | Rating |
| --- | --- |
| Launch readiness | Not ready for production; ready for internal beta after critical secret fix. |
| Investment readiness | Good for technical demo, risky for acquisition without hardening plan. |
| Scalability readiness | Moderate for single-company internal use; low for SaaS. |
| Enterprise readiness | Not ready. |
| Production readiness | Conditional, after security/devops remediation. |
| Technical risk | Medium-high |
| Business risk | Medium |
| Overall score | 72/100 |
| Current stage | Beta / Pre-Production |
| Remaining effort | 6-10 weeks for credible production internal release; 3-6 months for enterprise/SaaS maturity. |

### Top 20 Immediate Improvements

1. Remove SMTP password fallback and rotate the exposed credential.
2. Make production settings fail if secret key, hosts, DB, and email secrets are missing.
3. Default `SIYA_DEBUG` to false.
4. Add PostgreSQL database configuration.
5. Add backup/restore scripts and documented RPO/RTO.
6. Add CI for check, migration drift, tests, lint.
7. Add browser smoke tests for login, dashboard, property create, lead create, sidebar.
8. Add file upload validation and private storage for sensitive documents.
9. Add indexes for property dashboards/lists.
10. Split inline property wizard JS into static file.
11. Split base template navigation into include partials.
12. Normalize garbled UI symbols/text encoding.
13. Add production logging/monitoring/error reporting.
14. Add `check --deploy` to release gate.
15. Add payment/installment schema.
16. Add legal agreement lifecycle.
17. Add commission payout ledger.
18. Add MIS reports for sales, visits, inventory, conversions.
19. Add API design decision: stay server-rendered or add DRF for mobile.
20. Restore/update architecture and project status docs intentionally.

### Approval Recommendation

| Use case | Approval |
| --- | --- |
| Production launch | No |
| Enterprise usage | No |
| Investor demo | Yes, after removing/rotating exposed credential defaults |
| Commercial SaaS release | No |

Final recommendation: **Proceed as a strong internal beta, not as a production or enterprise acquisition-ready platform.** The codebase has real product substance and verified core workflows, but investment-grade readiness requires immediate security hardening, production database/deployment work, E2E/CI coverage, and real estate transaction modules for payments, installments, documents, and commission settlement.
