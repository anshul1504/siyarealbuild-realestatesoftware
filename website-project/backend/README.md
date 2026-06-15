# Siya Public Website Backend

Standalone Django + Jazzmin website CMS. It is isolated from the internal CRM.

## Included

- Admin-controlled site branding, SEO, contact details, social links, and homepage content
- Hero banners, projects, properties, galleries, services, testimonials, and FAQs
- Public property search, project/property details, enquiry forms, and site-visit requests
- Jazzmin superadmin inbox and content controls

## Run

```powershell
cd website-project\backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_website
python manage.py createsuperuser
python manage.py runserver 8001
```

Open:

- Website: `http://127.0.0.1:8001/`
- Jazzmin superadmin: `http://127.0.0.1:8001/superadmin/`

Everything visible on the public website can be managed from the superadmin. Replace the seeded demo images/content there.

## Verify

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
```
