"""
Minimal Django settings for the Shipeasy Python Entity Guide example.

This is a single-page, read-only demo. There are no models and no
migrations to run — the SQLite DATABASES entry only exists because Django
expects one to be configured.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Demo-only secret. Do NOT reuse in production.
SECRET_KEY = "django-insecure-shipeasy-entity-guide-demo-key"

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "guideapp",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "guideproj.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    },
]

WSGI_APPLICATION = "guideproj.wsgi.application"

# No models / migrations are used, but Django wants a DATABASES entry.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
