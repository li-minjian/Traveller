"""Single import point for the DS1 contract in this service.

The contract lives in ``journey-planner/domain_services/contract.py`` (DS1 #21).
All service code imports it from here, so moving the contract into a shared
package later only changes this file.

In this repository the contract is found automatically: if ``domain_services``
is not importable, ``journey-planner/`` is added to the Python path. A
deployment (Docker, IN02) installs or copies the contract instead.
"""

import sys
from pathlib import Path

try:
    import domain_services.contract  # noqa: F401
except ModuleNotFoundError:
    # Appended, not prepended: local packages (e.g. tests) must keep priority.
    sys.path.append(str(Path(__file__).resolve().parents[3] / "journey-planner"))

from domain_services.contract import (  # noqa: E402
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

__all__ = [
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
]
