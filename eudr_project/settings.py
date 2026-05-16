import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-in-production",
)
DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shopify_auth",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.ShopifyEmbedMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "eudr_project.urls"

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
                "core.context_processors.shopify_app",
            ],
        },
    },
]

WSGI_APPLICATION = "eudr_project.wsgi.application"

if os.environ.get("DATABASE_URL"):
    import dj_database_url

    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "eudr-cache",
        "TIMEOUT": 300,
    }
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
RQ_QUEUES = {
    "default": {
        "URL": REDIS_URL,
        "DEFAULT_TIMEOUT": 300,
    },
}

# --- Shopify App Config ---
SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY", "")
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET", "")
SHOPIFY_API_SCOPES = [
    "read_products",
    "write_products",
    "read_locales",
]
SHOPIFY_API_VERSION = "2026-04"
SHOPIFY_APP_URL = os.environ.get("SHOPIFY_APP_URL", "https://localhost:8000")

# --- Billing Plans (EUDR-specific) ---
EUDR_PLANS = {
    "starter": {
        "name": "Starter",
        "price": 19.00,
        "sku_limit": 100,
        "dds_limit_monthly": 50,
        "plot_limit": 25,
        "trial_days": 14,
        "features": ["basic_widget", "manual_dds", "csv_import"],
    },
    "pro": {
        "name": "Pro",
        "price": 49.00,
        "sku_limit": 2000,
        "dds_limit_monthly": 1000,
        "plot_limit": 500,
        "trial_days": 14,
        "features": [
            "basic_widget", "manual_dds", "csv_import",
            "bulk_dds", "geolocation_polygons", "risk_assessment",
            "multi_language", "pdf_export",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 99.00,
        "sku_limit": None,
        "dds_limit_monthly": None,
        "plot_limit": None,
        "trial_days": 14,
        "features": [
            "basic_widget", "manual_dds", "csv_import",
            "bulk_dds", "geolocation_polygons", "risk_assessment",
            "multi_language", "pdf_export",
            "api_access", "priority_support",
            # "multi_store" — planned Q3 2026 (depends on Shopify Plus shop linking)
            # "eu_infosys_integration" — planned Q4 2026 (depends on EU TRACES API GA, slated June 2026)
        ],
    },
}

SECURE_CONTENT_TYPE_NOSNIFF = True

CSRF_TRUSTED_ORIGINS = [
    os.environ.get("SHOPIFY_APP_URL", "https://localhost:8000"),
    "https://admin.shopify.com",
    "https://*.myshopify.com",
]
CSRF_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True
