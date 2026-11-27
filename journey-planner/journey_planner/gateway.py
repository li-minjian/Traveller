"""Generic caller: how the Journey Planner queries any number of transport services.

There is no per-service logic here. A new service (train, bus, ...) only has to
implement ``TransportService``; this module does not change.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from .contract import (
    ContractValidationError,
    ErrorCode,
    JourneySearchRequest,
    JourneySearchResult,
    ServiceError,
    TransportService,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0


async def search_one(
    service: TransportService,
    request: JourneySearchRequest,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> JourneySearchResult:
    """Query one service. Never raises: every failure becomes an ``unavailable`` result.

    This guards the Journey Planner against services that break the contract
    (hang, raise, or return something that is not a valid result).
    """
    service_id = service.service_id
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await service.search_journeys(request)
    except TimeoutError:
        logger.warning("Transport service %s timed out after %gs", service_id, timeout_seconds)
        return JourneySearchResult.unavailable(
            service_id,
            ServiceError(code=ErrorCode.TIMEOUT, message=f"No answer within {timeout_seconds:g} seconds."),
        )
    except ContractValidationError:
        logger.exception("Transport service %s produced data that violates the DS1 contract", service_id)
        return _internal_error(service_id, "The service returned data that violates the contract.")
    except Exception:
        logger.exception("Transport service %s raised an unexpected error", service_id)
        return _internal_error(service_id, "The service failed unexpectedly.")

    if not isinstance(result, JourneySearchResult):
        logger.error("Transport service %s returned %r instead of a JourneySearchResult", service_id, type(result))
        return _internal_error(service_id, "The service returned no valid result.")
    if result.service_id != service_id:
        logger.error("Transport service %s answered as %s", service_id, result.service_id)
        return _internal_error(service_id, "The service answered with a different service_id.")
    return result


async def search_all(
    services: Iterable[TransportService],
    request: JourneySearchRequest,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[JourneySearchResult]:
    """Query all services concurrently; one result per service, in the given order.

    A failing service only affects its own result.
    """
    return list(
        await asyncio.gather(
            *(search_one(service, request, timeout_seconds=timeout_seconds) for service in services)
        )
    )


def _internal_error(service_id: str, message: str) -> JourneySearchResult:
    return JourneySearchResult.unavailable(
        service_id,
        ServiceError(code=ErrorCode.INTERNAL_ERROR, message=message, is_retryable=False),
    )
