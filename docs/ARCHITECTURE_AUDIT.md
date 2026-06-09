# Siya Real Build Architecture Audit

Status: architecture cleanup complete

## Current Structure

- `accounts/url_groups`: domain-grouped account routes.
- `accounts/view_modules`: authentication/profile/company, onboarding, team directory, access control, meetings/events, and owner workflow views.
- `accounts/policies.py`: reusable authorization decisions.
- `accounts/services.py`: transactional employee updates and audit logging.
- `properties/view_modules`: dashboard, inventory, sharing, plots, and visit views.
- `properties/selectors.py`, `properties/policies.py`, and `properties/services.py`: query, authorization, and lifecycle boundaries.
- `config`: project settings, root URLs, and error handlers.
- `templates`: feature-grouped server-rendered UI.

## Architecture Rules

- Keep URL routing grouped by business domain under `accounts/url_groups/`.
- Put authorization decisions in `policies.py`.
- Put reusable queries in `selectors.py`.
- Put transactional state changes and audit logging in `services.py`.
- Keep views focused on request parsing, messages, and rendering.
- Preserve migrations, user uploads, databases, and backups during cleanup.

## Deliberate Boundaries

- `accounts/views.py` and `properties/views.py` are compatibility facades only.
- `accounts/forms.py` remains a central form registry because forms share model and role choices; splitting it would add import churn without changing runtime ownership.
- `accounts/models.py` remains the Django app schema boundary so migration imports and historical migration state stay stable.
- Database migrations, user media, local databases, and backups are preserved during cleanup.

## Verification

- Django system checks pass.
- Migration consistency check reports no model changes.
- Ruff passes across `accounts`, `properties`, and `config`.
- The complete automated suite passes.
- No unresolved Git conflict markers remain.

## Generated Files

The following stay outside Git: virtual environments, caches, logs, local databases, media uploads, static build output, environment secrets, coverage output, and local backups.
