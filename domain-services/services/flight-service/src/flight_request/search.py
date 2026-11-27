"""Flight search: request -> airports around origin and destination -> adapters -> result (contract/openapi.yaml).

For every pair of origin and destination airport each adapter is asked once
(in parallel, each with its own timeout). A failing pair becomes an error
with the provider ID; the other pairs still count. Status rules:
domain-services/contract/README.md §4 (``success``, ``no_results``, ``partial``, ``unavailable``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from adapters.base import FlightAdapter, ProviderError
from airport_finder import Airport, AirportFinder

from . import contract_json
from .request import RequestInvalid, SearchRequest, parse_request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchSettings:
    radius_km: float = 30.0
    radius_step_km: float = 10.0
    max_radius_km: float = 2000.0
    max_airports: int = 3
    adapter_timeout_seconds: float = 8.0  # below the Journey Planner's 10 s


class FlightSearch:
    def __init__(self, finder: AirportFinder, adapters: Sequence[FlightAdapter], settings: SearchSettings = SearchSettings()):
        if not adapters:
            raise ValueError("The flight service needs at least one adapter.")
        self.finder = finder
        self.adapters = tuple(adapters)
        self.settings = settings

    async def search(self, request: SearchRequest) -> dict[str, Any]:
        origins = self._airports(request.origin.latitude, request.origin.longitude)
        destinations = self._airports(request.destination.latitude, request.destination.longitude)
        tasks = [
            (adapter, origin, destination)
            for origin in origins
            for destination in destinations
            if origin.iata != destination.iata
            for adapter in self.adapters
        ]
        if not tasks:
            return contract_json.result([], [], all_failed=False)  # same airport on both sides: no flight

        outcomes = await asyncio.gather(*(self._query(*task, request) for task in tasks))
        journeys = [journey for found, _ in outcomes for journey in found]
        errors = [error for _, error in outcomes if error is not None]
        journeys.sort(key=lambda j: (j["legs"][0]["departure_at"], j["id"]))
        return contract_json.result(journeys, errors, all_failed=len(errors) == len(tasks))

    def _airports(self, latitude: float, longitude: float) -> list[Airport]:
        area = self.finder.nearest(
            latitude,
            longitude,
            radius_km=self.settings.radius_km,
            step_km=self.settings.radius_step_km,
            max_radius_km=self.settings.max_radius_km,
            max_airports=self.settings.max_airports,
        )
        return [nearby.airport for nearby in area.airports]

    async def _query(
        self, adapter: FlightAdapter, origin: Airport, destination: Airport, request: SearchRequest
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        pair = f"{origin.iata}-{destination.iata}"
        try:
            async with asyncio.timeout(self.settings.adapter_timeout_seconds):
                return await adapter.search(origin, destination, request), None
        except TimeoutError:
            code, message = "timeout", f"{pair}: no answer within {self.settings.adapter_timeout_seconds:g} seconds."
        except ProviderError as exc:
            code, message = exc.code, f"{pair}: {exc.message}"
        except Exception:
            logger.exception("Provider %s, %s: unexpected error in adapter", adapter.provider_id, pair)
            code, message = "internal_error", f"{pair}: the provider adapter failed unexpectedly."
        # Provider, airport pair and code only: no token, no times, no coordinates.
        logger.warning("Provider %s, %s: %s", adapter.provider_id, pair, code)
        return [], contract_json.error(code, message, provider_id=adapter.provider_id)


async def handle_search(body: bytes, search: FlightSearch) -> tuple[int, dict[str, Any]]:
    """HTTP body in, (status code, JSON body) out. Used by the FastAPI endpoint."""
    try:
        data = json.loads(body or b"null")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, contract_json.parse_error_body("Body is not valid JSON.")
    try:
        request = parse_request(data)
    except RequestInvalid as exc:
        return 400, contract_json.validation_error_body(exc.fields)
    return 200, await search.search(request)
