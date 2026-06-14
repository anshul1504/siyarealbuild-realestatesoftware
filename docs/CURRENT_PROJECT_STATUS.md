# Current Project Status

Status date: 2026-06-14

## Release Assessment

Siya Real Build is ready for controlled single-company internal beta use. Core accounts, CRM, property inventory, colony/plot, quotation, booking, payment, commission, visit, referral, audit, export, and owner-operation workflows are implemented and covered by the Django regression suite.

The repository is product-ready for the AWS live-deployment phase. Public launch approval still depends on provisioning and verifying the real AWS infrastructure, credentials, domain, email, persistent media, monitoring, and backup restore drills.

## Internal Core

| Area | Status |
| --- | --- |
| Accounts, onboarding, roles, owner approvals | Complete |
| Team/company operations and audit logs | Complete |
| CRM leads, assignment, follow-ups, visits, reports | Complete |
| Property categories, inventory, archive/restore, sharing | Complete |
| Colony plots, server-side pricing, finder, status history | Complete |
| Quotations, booking requests/approval, agreements | Complete |
| Installments, payments, commissions, payout ledger | Complete |
| Role-aware access tests | Complete |

## Audit Fixes - 2026-06-14

- Prevented creation or approval of a second active booking for the same plot.
- Added row locking around active-booking creation/approval checks.
- Prevented unallocated payments from exceeding the booking balance.
- Restored current project/property audit handoff documents.

## Verification

- `python manage.py check`: passed.
- `python manage.py makemigrations --check --dry-run`: passed, no changes detected.
- `python manage.py test accounts properties crm config --verbosity 1`: passed, 154 tests.
- `python -m compileall -q accounts properties crm config`: passed.
- `git diff --check`: passed.
- `python manage.py check --deploy`: six expected local-development warnings.
- Production environment simulation `check --deploy`: only HSTS include-subdomains/preload warnings remain; enable after final domain policy approval.
- `ruff`: unavailable in the current Python environment.

## External Backlog

- Provision AWS ECS/ECR, RDS PostgreSQL, ALB/ACM, Route 53, EFS, Secrets Manager, and CloudWatch.
- Configure real production secrets, domain, HTTPS, SMTP, and PostgreSQL values.
- Add browser E2E and perform production backup/restore drills.
- Complete external Meta app/token setup and operational verification.
- Move sensitive/private uploaded documents behind authorized delivery instead of direct media serving.

## Product-Ready Deployment Foundation

- Docker/Gunicorn runtime and non-root container user.
- PostgreSQL production driver.
- WhiteNoise compressed manifest static serving in production.
- Database-backed `/health/` endpoint for load balancers.
- GitHub Actions checks for migrations, tests, checks, and static collection.
- Strict production validation for HTTPS CSRF origins and non-console email.
- AWS deployment and launch-gate runbook.
- CloudFormation stack for ECS, RDS, EFS, ALB, Secrets Manager, logs, alarms, and SNS.
- PowerShell bootstrap deployment script and GitHub OIDC deployment workflow.
