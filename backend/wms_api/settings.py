import os
from pathlib import Path

from dotenv import load_dotenv
from corsheaders.defaults import default_headers


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Read an environment flag as a boolean. Troubleshoot: accepted 1/true/yes/on values and the default.
def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Split a comma-separated environment setting into a list. Troubleshoot: spaces, commas, and empty entries.
def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be configured in the environment.")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "cycle_counts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "wms_api.urls"
TEMPLATES = []
WSGI_APPLICATION = "wms_api.wsgi.application"
ASGI_APPLICATION = "wms_api.asgi.application"

mssql_extra_params = []
if env_bool("DB_TRUSTED_CONNECTION", True):
    mssql_extra_params.append("Trusted_Connection=yes")
if env_bool("DB_ENCRYPT", True):
    mssql_extra_params.append("Encrypt=yes")
if env_bool("DB_TRUST_SERVER_CERTIFICATE", False):
    mssql_extra_params.append("TrustServerCertificate=yes")

DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.getenv("DB_NAME"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "1433"),
        "USER": os.getenv("DB_USER", ""),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "OPTIONS": {
            "driver": os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
            "extra_params": ";".join(mssql_extra_params),
        },
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"

# The timezone semantics of the legacy datetime columns still need confirmation.
# Disabling conversion avoids silently shifting their stored values during read-only use.
USE_I18N = True
USE_TZ = False

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174",
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["cycle_counts.authentication.StaffAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Avoid importing Django's auth models; this foundation does not own auth tables.
    "UNAUTHENTICATED_USER": None,
}

CORS_ALLOW_HEADERS = [*default_headers, "x-counter-session"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
