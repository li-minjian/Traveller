"""Interface between the flight search and the provider adapters.

An adapter searches flights between two airports and returns journeys
(dicts, see ``flight_request/contract_json.py``). An empty list means: the provider
answered and has no flight. Failures are raised as ``ProviderError`` with
the error code from contract/openapi.yaml; nothing provider-specific leaves the adapter.
"""

from __future__ import annotations

from typing import Any, Protocol

from airport_finder import Airport
from flight_request.request import SearchRequest


class ProviderError(Exception):
    code = "provider_unavailable"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderTimeout(ProviderError):
    code = "timeout"


class ProviderRateLimited(ProviderError):
    code = "rate_limited"


class ProviderUnavailable(ProviderError):
    code = "provider_unavailable"


class ProviderAuthenticationFailed(ProviderError):
    code = "authentication_failed"


class InvalidProviderResponse(ProviderError):
    code = "invalid_provider_response"


class FlightAdapter(Protocol):
    provider_id: str

    async def search(self, origin: Airport, destination: Airport, request: SearchRequest) -> list[dict[str, Any]]: ...
