from django.apps import AppConfig


class ReferenceDataConfig(AppConfig):
    """Reference data: historical benchmark cases, read-only through the API."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reference_data"
