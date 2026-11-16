"""DS1 (#21): how the Journey Planner talks to all transport domain services.

Import from here; the submodules are an implementation detail.
"""

from .contract import (
    CONTRACT_VERSION,
    Availability,
    ContractValidationError,
    Coordinates,
    ErrorCode,
    Journey,
    JourneySearchRequest,
    JourneySearchResult,
    Leg,
    Money,
    Offer,
    Passenger,
    PriceBasis,
    SearchStatus,
    ServiceError,
    Stop,
    TransportMode,
    TransportService,
)
from .gateway import DEFAULT_TIMEOUT_SECONDS, search_all, search_one

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_TIMEOUT_SECONDS",
    "Availability",
    "ContractValidationError",
    "Coordinates",
    "ErrorCode",
    "Journey",
    "JourneySearchRequest",
    "JourneySearchResult",
    "Leg",
    "Money",
    "Offer",
    "Passenger",
    "PriceBasis",
    "SearchStatus",
    "ServiceError",
    "Stop",
    "TransportMode",
    "TransportService",
    "search_all",
    "search_one",
]
