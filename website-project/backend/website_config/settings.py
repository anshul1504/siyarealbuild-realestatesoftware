"""Django settings for the standalone Siya public website."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# Core runtime configuration

SECRET_KEY = os.environ.get("WEBSITE_SECRET_KEY", "django-insecure-website-local-only")
DEBUG = os.environ.get("WEBSITE_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    item.strip()
    for item in os.environ.get(
        "WEBSITE_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    ).split(",")
    if item.strip()
]


# Django applications and middleware

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "website_config.urls"
WSGI_APPLICATION = "website_config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "website.context_processors.site_settings",
            ],
        },
    }
]


# Database, localization, and authentication

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Static assets, uploads, and email

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
EMAIL_BACKEND = os.environ.get(
    "WEBSITE_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)


# Jazzmin superadmin presentation

JAZZMIN_SETTINGS = {
    "site_title": "Siya Website Admin",
    "site_header": "Siya Real Build Website",
    "site_brand": "Siya Website CMS",
    "welcome_sign": "Manage the complete Siya public website",
    "copyright": "Siya Real Build",
    "show_sidebar": True,
    "navigation_expanded": True,
    "icons": {
        "website.sitesettings": "fas fa-cog",
        "website.project": "fas fa-building",
        "website.propertylisting": "fas fa-map-marked-alt",
        "website.enquiry": "fas fa-envelope",
        "website.sitevisitrequest": "fas fa-calendar-check",
    },
}
