# Siya Real Build

Django-based real estate operations platform under active development.

## Run locally

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\activate
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

The project reads deployment-sensitive settings from `SIYA_*` environment variables. The example configuration uses Django's console email backend so OTPs appear in the development terminal. Never commit real SMTP credentials or production secrets.

## Verification

Run these checks before merging changes:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

For a production environment, set `SIYA_DEBUG=false`, configure the allowed hosts and CSRF origins, provide a strong secret key, configure SMTP, enable HTTPS settings, then run:

```powershell
python manage.py check --deploy
```
