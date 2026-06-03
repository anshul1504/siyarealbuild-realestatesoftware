# Siya Real Build

Django based real estate management starter with email OTP login.

## Run locally

```powershell
.\.venv\Scripts\activate
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

OTP emails use Django's console email backend in development, so the code appears in the terminal where `runserver` is running.
