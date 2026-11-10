from django.apps import AppConfig


class PlanningConfig(AppConfig):
    """Application data: planning sessions created by users."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "planning"
