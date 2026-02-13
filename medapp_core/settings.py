"""
medapp_core/settings.py

Purpose:
  - Conservative, backwards-compatible settings for local development.
  - Adds automatic discovery of app-level frontend template and static
    directories that follow the pattern: <app_name>_frontend/templates
    and <app_name>_frontend/static. This lets teams keep frontend assets
    inside each app's frontend folder without moving files or changing URLs.

Important:
  - This file is intended to be a drop-in replacement for your current
    settings.py. Back up the original before replacing.
  - No changes to URL routes or installed apps ordering are made here.
"""

from pathlib import Path
import os

# ---------------------------------------------------------------------------
# Base directory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
LOGIN_URL = "accounts:register"  # or "accounts:login" if you prefer


# ---------------------------------------------------------------------------
# Security & debug (keep as in your environment)
# ---------------------------------------------------------------------------
SECRET_KEY = 'django-insecure--@r#m)kg+n$^l#^%)0!+_3h#gh%a3d9xr3174+i3h)%o7wzjab'
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# ---------------------------------------------------------------------------
# Installed apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django defaults
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Utilities
    'django_extensions',

    # Django REST Framework (keeps browsable API templates available)
    'rest_framework',

    # Project apps (preserve order; do not remove)
    'accounts',
    'hospitals',
    'doctors',
    'patients',
    'departments',
    'schedules',
    'appointments',
    'prescriptions',
    'reports',
    'adminpanel',
    'mlmodule',
]

# Custom user model (unchanged)
AUTH_USER_MODEL = 'accounts.CustomUser'

# ---------------------------------------------------------------------------
# Middleware (unchanged)
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'medapp_core.urls'

# ---------------------------------------------------------------------------
# Helper: discover app-level frontend template and static directories
# ---------------------------------------------------------------------------
# This block scans the project root (BASE_DIR) for folders named like:
#   <app_name>_frontend/templates
#   <app_name>_frontend/static
# and adds them to TEMPLATES['DIRS'] and STATICFILES_DIRS respectively.
# This is non-destructive and only adds directories if they exist.
FRONTEND_TEMPLATE_DIRS = []
FRONTEND_STATIC_DIRS = []

try:
    for entry in BASE_DIR.iterdir():
        if not entry.is_dir():
            continue

        # Example: departments_frontend/templates
        frontend_templates = entry / f"{entry.name}_frontend" / "templates"
        if frontend_templates.exists():
            FRONTEND_TEMPLATE_DIRS.append(str(frontend_templates))

        # Example: departments_frontend/static
        frontend_static = entry / f"{entry.name}_frontend" / "static"
        if frontend_static.exists():
            FRONTEND_STATIC_DIRS.append(str(frontend_static))
except Exception:
    # If anything goes wrong during discovery, we silently continue.
    # This avoids breaking the app if filesystem permissions or paths differ.
    FRONTEND_TEMPLATE_DIRS = []
    FRONTEND_STATIC_DIRS = []

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Project-level templates directory (keep your existing project templates)
        'DIRS': [str(BASE_DIR / 'templates')] + FRONTEND_TEMPLATE_DIRS,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Make STATIC_URL and MEDIA_URL available in templates
                'django.template.context_processors.static',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'medapp_core.wsgi.application'

# ---------------------------------------------------------------------------
# Database (unchanged)
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ---------------------------------------------------------------------------
# Password validation (unchanged)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# ---------------------------------------------------------------------------
# Internationalization (unchanged)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'

# Keep your project-level static directory
STATICFILES_DIRS = [str(BASE_DIR / 'static')] + FRONTEND_STATIC_DIRS

# Where collectstatic will gather files for production
STATIC_ROOT = str(BASE_DIR / 'staticfiles')

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = str(BASE_DIR / 'media')

# ---------------------------------------------------------------------------
# Django REST Framework (safe defaults for development)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


