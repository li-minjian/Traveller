"""Django settings for the Journey Planner.

The planner has no database and no LLM. It only uses Django for HTTP,
validation and tests, so it shares the backend's dependencies and conventions.
"""

import os

_TRUE = {"1", "true", "yes", "on"}


def env(name: str, default: str) -> str:
    value = os.environ.get(name, "")
    return value if value.strip() else default


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-do-not-use-in-production")
DEBUG = env("DJANGO_DEBUG", "false").strip().lower() in _TRUE
ALLOWED_HOSTS = [
    host.strip()
    for host in env("PLANNER_ALLOWED_HOSTS", "localhost,127.0.0.1,journey-planner").split(",")
    if host.strip()
]

INSTALLED_APPS = ["rest_framework", "planner"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {}
TEST_RUNNER = "planner.testing.NoDatabaseTestRunner"

TIME_ZONE = "UTC"
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "planner.errors.exception_handler",
}

# Which provider answers flight searches. "dummy" returns fixed example
# flights. The real Flight Service (DS1 #21, DS6 #41) is added as a further
# provider in planner/providers/ and selected here.
FLIGHT_PROVIDER = env("FLIGHT_PROVIDER", "dummy").strip().lower()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"level": "ERROR"}},
}
