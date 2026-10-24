"""Django settings for the Department of Unnecessary Affairs.

Everything configurable comes from environment variables (see .env.example). The defaults are for local development.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default):
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


def env_list(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


# Debug defaults to on so that `runserver` serves static files and shows errors on your own machine.
# Before deploying anywhere, set DJANGO_DEBUG=false, DJANGO_SECRET_KEY and DJANGO_ALLOWED_HOSTS.
DEBUG = env_bool("DJANGO_DEBUG", "true")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
    SECRET_KEY = "django-insecure-local-development-key-do-not-use-anywhere-else"

# Comma-separated, e.g. "localhost,127.0.0.1". Empty is fine while DEBUG is on (Django allows localhost).
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

# Behind an HTTPS proxy (Render, Railway, Fly, ...) Django needs to be told the public origin, or every POST fails
# the CSRF check. Example: DJANGO_CSRF_TRUSTED_ORIGINS=https://dua-demo.onrender.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if env_bool("DJANGO_BEHIND_PROXY", "false"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cases',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'cases.middleware.KeepSessionOnErrorMiddleware',
    'cases.middleware.FreshStartMiddleware',          # wipes all cases once per server start
]

if not DEBUG:
    # With DEBUG on, runserver serves static files itself. Otherwise WhiteNoise serves what collectstatic collected.
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'dua.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cases.context.site',
            ],
        },
    },
]

WSGI_APPLICATION = 'dua.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'      # `python manage.py collectstatic` writes here

# ---- Case data ----
# Cases are deleted when the server starts (strictly: on its first request), so nothing survives a restart. Set
# WIPE_ON_START=false to keep them in db.sqlite3. Either way each visitor only ever sees their own cases.
WIPE_ON_START = env_bool("WIPE_ON_START", "true") and "test" not in sys.argv

# ---- Demo mode ----
# No model is called. Each office answers its built-in sample inputs from pre-written results (cases/demo_data/),
# which still go through the normal validators. Any other input gets a message saying so.
DEMO_MODE = env_bool("DEMO_MODE", "false")

# ---- Local Ollama ----
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_CONNECT_TIMEOUT = float(os.environ.get("OLLAMA_CONNECT_TIMEOUT", "5"))
OLLAMA_READ_TIMEOUT = float(os.environ.get("OLLAMA_READ_TIMEOUT", "180"))
# Gemma 4 can "think" before answering, which is slow and can leave the JSON empty. Off by default.
OLLAMA_THINK = env_bool("OLLAMA_THINK", "false")
# Context window requested from Ollama. Ollama's own default can be as small as 4096 tokens, which would silently
# cut long documents off. Raise it together with MAX_DOCUMENT_CHARS.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

# ---- Input limits ----
MAX_STATEMENT_CHARS = int(os.environ.get("MAX_STATEMENT_CHARS", "6000"))
MAX_DOCUMENT_CHARS = int(os.environ.get("MAX_DOCUMENT_CHARS", "12000"))
# 12000 characters is at most 48000 bytes of UTF-8.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", "60000"))
# PDFs are parsed in memory with pypdf and only the text is kept. Text-based PDFs only (no OCR).
MAX_PDF_BYTES = int(os.environ.get("MAX_PDF_BYTES", "2000000"))
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "40"))
