# Siya Real Build

Django-based real estate operations platform for company onboarding, team management, property inventory, visits, CRM leads, Meta lead ingestion, referrals, operations, and owner controls.

## Current status

- Property module is connected end to end: category-first add flow, colony pricing, plot inventory, plot finder, backend price calculation, media/documents, archive/restore, export, sharing, visits, quotations, bookings, coupon discounts, installments, payments, agreements, commission rules, and payout ledger.
- CRM module is connected end to end for internal use: lead lifecycle, assignment rules, follow-ups, reports, exports, Meta webhook foundation, duplicate checks, and partner workspace.
- Accounts/owner workflows include signup approval, invite onboarding, employee directory, company settings, role changes, referrals, meetings, events, popups, audit logs, and notifications.
- Local clone readiness is good after migrations and seed data. Production readiness still requires real environment values, HTTPS settings, monitoring, CI/E2E, and external Meta app/token setup.
- Security hardening now removes committed SMTP/password defaults and enforces fail-closed production settings when `SIYA_ENV=production`.

## Run locally

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\activate
python manage.py migrate
python manage.py check
python manage.py test
python manage.py seed_properties
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

The project reads deployment-sensitive settings from `SIYA_*` environment variables. The example configuration uses Django's console email backend so OTPs appear in the development terminal. Never commit real SMTP credentials or production secrets.

## Backup

Create a local backup bundle before major changes or handoff:

```powershell
python manage.py backup_workspace
```

The command writes a timestamped zip under `backups/` with `db.sqlite3`, media files, `manifest.json`, and a `.sha256` checksum. Use `--skip-media` for a database-only backup. Stop the app before restoring, restore only to matching code/migration versions, then run `python manage.py migrate` and `python manage.py check`.

## Verification

Run these checks before merging changes:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

For a production environment, set `SIYA_ENV=production`, `SIYA_DEBUG=false`, configure production-only allowed hosts and CSRF origins, provide a strong secret key, configure `SIYA_DATABASE_URL` with PostgreSQL, configure SMTP, enable HTTPS settings, configure Meta credentials if CRM lead ads are used, then run:

```powershell
python manage.py check --deploy
```

Expected local verification before handoff:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test accounts properties crm config -v 1
ruff check accounts properties crm config
```
