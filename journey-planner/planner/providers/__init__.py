"""Providers the planner queries, one or more per mode of transport."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from planner.providers.base import ProviderError, TransportProvider
from planner.providers.dummy_flights import DummyFlightProvider

__all__ = ["ProviderError", "TransportProvider", "get_providers"]


def get_providers() -> list[TransportProvider]:
    """Return the configured providers. Further services are added here."""
    if settings.FLIGHT_PROVIDER == "dummy":
        return [DummyFlightProvider()]
    raise ImproperlyConfigured(
        f"Unknown FLIGHT_PROVIDER {settings.FLIGHT_PROVIDER!r}; only 'dummy' exists so far."
    )
