"""Builds the JSON defined in domain-services/contract/openapi.yaml as plain dicts.

The contract has no shared code; these helpers only make sure every field of
openapi.yaml is always present (missing values are ``null``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

CONTRACT_VERSION = "1.0"
SERVICE_ID = "flight"

RETRYABLE = {
    "validation_error": False,
    "timeout": True,
    "rate_limited": True,
    "provider_unavailable": True,
    "authentication_failed": False,
    "invalid_provider_response": False,
    "internal_error": False,
}


def stop(location_id: str | None, *, name: str | None, code: str | None, latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "location_id": location_id,
        "name": name,
        "code": code,
        "coordinates": {"latitude": latitude, "longitude": longitude},
    }


def flight_leg(
    origin: dict[str, Any],
    destination: dict[str, Any],
    departure_at: datetime,
    arrival_at: datetime,
    *,
    operator: str | None,
    service_number: str | None,
) -> dict[str, Any]:
    return {
        "mode": "flight",
        "origin": origin,
        "destination": destination,
        "departure_at": departure_at.isoformat(),
        "arrival_at": arrival_at.isoformat(),
        "operator": operator,
        "service_number": service_number,
        "is_on_demand": False,
    }


def money(amount: Decimal, currency: str, basis: str) -> dict[str, Any]:
    value = amount.quantize(Decimal("0.01"))
    return {"amount": int(value) if value == value.to_integral_value() else float(value), "currency": currency, "basis": basis}


def offer(
    offer_id: str,
    provider_id: str,
    *,
    price: dict[str, Any] | None,
    availability: str = "unknown",
    is_price_estimate: bool,
    fare_name: str | None = None,
    booking_url: str | None = None,
) -> dict[str, Any]:
    return {
        "id": offer_id,
        "provider_id": provider_id,
        "price": price,
        "price_upper": None,
        "availability": availability,
        "is_price_estimate": is_price_estimate,
        "fare_name": fare_name,
        "booking_url": booking_url,
    }


def journey(journey_id: str, provider_id: str, legs: list[dict[str, Any]], offers: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"id": journey_id, "provider_id": provider_id, "legs": legs, "offers": offers}


def error(code: str, message: str, *, provider_id: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "provider_id": provider_id, "field": None, "is_retryable": RETRYABLE[code]}


def result(journeys: list[dict[str, Any]], errors: list[dict[str, Any]], *, all_failed: bool) -> dict[str, Any]:
    """Picks the status from journeys and errors (domain-services/contract/README.md §4)."""
    if all_failed:
        status, journeys = "unavailable", []
    elif errors:
        status = "partial"
    else:
        status = "success" if journeys else "no_results"
    return {
        "contract_version": CONTRACT_VERSION,
        "service_id": SERVICE_ID,
        "status": status,
        "journeys": journeys,
        "errors": errors,
        "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def validation_error_body(fields: dict[str, list[str]]) -> dict[str, Any]:
    """HTTP 400 body (API conventions §4)."""
    return {"error": {"code": "validation_error", "message": "The input is invalid.", "fields": fields}}


def parse_error_body(message: str) -> dict[str, Any]:
    return {"error": {"code": "parse_error", "message": message}}
