"""Journey Planner. So far: the generic caller for all transport domain services (DS1 #21).

``contract`` implements the DS1 contract (domain-services/contract/openapi.yaml) as
Python types; ``http_binding`` maps them to HTTP, ``mocks`` are example services.
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
