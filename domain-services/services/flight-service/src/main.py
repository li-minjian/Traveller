"""Flight Service: HTTP endpoint defined in domain-services/contract/openapi.yaml.

    POST /api/v1/journey-searches/   JourneySearchRequest -> JourneySearchResult
    GET  /health

Start (from src/):  uvicorn main:create_app_from_env --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from adapters.travelpayouts import TravelpayoutsAdapter
from airport_finder import AirportFinder
from config import Settings
from flight_request.search import FlightSearch, handle_search

SEARCH_PATH = "/api/v1/journey-searches/"


def create_app(search: FlightSearch) -> FastAPI:
    app = FastAPI(title="Flight Service", version="1.0")

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service_id": "flight",
            "providers": [adapter.provider_id for adapter in search.adapters],
            "airports": len(search.finder),
        }

    @app.post(SEARCH_PATH)
    async def journey_searches(request: Request) -> JSONResponse:
        status_code, payload = await handle_search(await request.body(), search)
        return JSONResponse(payload, status_code=status_code)

    return app


def create_app_from_env() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()  # fails at start-up without token
    adapter = TravelpayoutsAdapter(
        settings.travelpayouts_token,
        currency=settings.travelpayouts_currency,
        marker=settings.travelpayouts_marker,
    )
    return create_app(FlightSearch(AirportFinder.from_files(), [adapter], settings.search))

