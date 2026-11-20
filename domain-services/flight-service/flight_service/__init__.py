"""Flight domain service (DS2 #23). Independent of all other transport services."""

from .service import ADAPTERS, SERVICE_ID, FlightService, create_flight_service

__all__ = ["ADAPTERS", "SERVICE_ID", "FlightService", "create_flight_service"]
