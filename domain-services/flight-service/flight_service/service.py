"""Flight service (DS2 #23): implements the DS1 ``TransportService`` for ``mode: flight``.

Self-contained: own provider adapters, error handling and configuration. It
shares no code with other transport services; its only external dependency is
the DS1 contract it offers to the Journey Planner.

    Journey Planner --DS1--> FlightService --ProviderAdapter--> flight provider APIs

The service queries all configured adapters in parallel, turns adapter
failures into DS1 errors with the provider ID and picks the DS1 status. It does
no ranking, filtering or combining of journeys.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from .adapters.mock_air import MockAirAdapter
from .contract import (
    ContractValidationError,
    ErrorCode,
    Journey,
    JourneySearchRequest,
    JourneySearchResult,
    ServiceError,
    TransportMode,
)
from .errors import ProviderError

logger = logging.getLogger(__name__)

SERVICE_ID = "flight"
MODE = TransportMode.FLIGHT
PROVIDERS_ENV_VAR = "FLIGHT_SERVICE_PROVIDERS"
DEFAULT_PROVIDERS = ("mock-air",)
DEFAULT_ADAPTER_TIMEOUT_SECONDS = 8.0  # below the Journey Planner's 10 s default


@runtime_checkable
class ProviderAdapter(Protocol):
    """Internal interface between this service and one flight provider (not part of DS1).

    ``search`` translates the request into the provider's terms, calls the
    provider and maps the answer to DS1 journeys with ``provider_id`` set. An
    empty list means: the provider answered and has no journey. Failures are
    raised as ``ProviderError``.
    """

    @property
    def provider_id(self) -> str: ...

    async def search(self, request: JourneySearchRequest) -> Sequence[Journey]: ...


#: Available provider adapters. A real flight API adapter is registered here.
ADAPTERS: dict[str, Callable[..., ProviderAdapter]] = {
    "mock-air": MockAirAdapter,
}


class FlightService:
    def __init__(
        self,
        adapters: Sequence[ProviderAdapter],
        *,
        adapter_timeout_seconds: float = DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    ):
        if not adapters:
            raise ValueError("The flight service needs at least one provider adapter.")
        provider_ids = [adapter.provider_id for adapter in adapters]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError(f"Duplicate provider IDs: {provider_ids}.")
        self._adapters = tuple(adapters)
        self._timeout = adapter_timeout_seconds

    @property
    def service_id(self) -> str:
        return SERVICE_ID

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(adapter.provider_id for adapter in self._adapters)

    async def search_journeys(self, request: JourneySearchRequest) -> JourneySearchResult:
        outcomes = await asyncio.gather(*(self._query(adapter, request) for adapter in self._adapters))
        journeys = [journey for found, _ in outcomes for journey in found]
        errors = [error for _, error in outcomes if error is not None]

        if len(errors) == len(self._adapters):
            return JourneySearchResult.unavailable(SERVICE_ID, *errors)
        journeys.sort(key=lambda journey: (journey.departure_at, journey.id))
        return JourneySearchResult.from_journeys(SERVICE_ID, journeys, errors)

    async def _query(
        self, adapter: ProviderAdapter, request: JourneySearchRequest
    ) -> tuple[list[Journey], ServiceError | None]:
        provider_id = adapter.provider_id
        try:
            async with asyncio.timeout(self._timeout):
                journeys = list(await adapter.search(request))
            _check(adapter, journeys)
        except TimeoutError:
            return [], _error(provider_id, ErrorCode.TIMEOUT, f"No answer within {self._timeout:g} seconds.")
        except ProviderError as exc:
            return [], _error(provider_id, exc.code, exc.message)
        except ContractValidationError as exc:
            logger.warning("Provider %s: unusable data: %s", provider_id, exc)
            return [], _error(provider_id, ErrorCode.INVALID_PROVIDER_RESPONSE, "The provider returned unusable data.")
        except Exception:
            logger.exception("Provider %s: unexpected error in adapter", provider_id)
            return [], _error(provider_id, ErrorCode.INTERNAL_ERROR, "The provider adapter failed unexpectedly.")
        return journeys, None


def _check(adapter: ProviderAdapter, journeys: list[Journey]) -> None:
    """Adapters may only return flight journeys of their own provider."""
    for journey in journeys:
        if not isinstance(journey, Journey):
            raise ContractValidationError({"journeys": ["Adapter returned a non-Journey object."]})
        if journey.provider_id != adapter.provider_id:
            raise ContractValidationError({"provider_id": [f"Expected {adapter.provider_id!r}."]})
        if any(leg.mode is not MODE for leg in journey.legs):
            raise ContractValidationError({"mode": [f"Expected only {MODE.value!r} legs."]})


def _error(provider_id: str, code: ErrorCode, message: str) -> ServiceError:
    # Log provider and code only: no credentials and no search parameters.
    logger.warning("Service %s, provider %s: %s", SERVICE_ID, provider_id, code.value)
    return ServiceError(code=code, message=message, provider_id=provider_id)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def configured_providers() -> tuple[str, ...]:
    """``FLIGHT_SERVICE_PROVIDERS`` (comma-separated), else the default."""
    names = tuple(name.strip() for name in os.environ.get(PROVIDERS_ENV_VAR, "").split(",") if name.strip())
    return names or DEFAULT_PROVIDERS


def create_flight_service(
    providers: Sequence[str] | None = None,
    *,
    adapter_options: Mapping[str, Mapping[str, Any]] | None = None,
    adapter_timeout_seconds: float = DEFAULT_ADAPTER_TIMEOUT_SECONDS,
) -> FlightService:
    """Build the service with one adapter per configured provider.

    ``adapter_options`` passes keyword arguments to single adapters, e.g.
    ``{"mock-air": {"failure": ErrorCode.TIMEOUT}}``. Unknown provider names
    fail at start-up, not at the first search.
    """
    names = tuple(providers) if providers is not None else configured_providers()
    unknown = [name for name in names if name not in ADAPTERS]
    if unknown:
        raise ValueError(f"Unknown flight provider(s) {unknown}; available: {sorted(ADAPTERS)}.")
    options = adapter_options or {}
    adapters = [ADAPTERS[name](**options.get(name, {})) for name in names]
    return FlightService(adapters, adapter_timeout_seconds=adapter_timeout_seconds)
