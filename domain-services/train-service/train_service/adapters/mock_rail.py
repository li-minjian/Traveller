"""Mock rail provider ``mock-rail``: a direct train between any two cities.

Built like a real adapter, in three steps:

1. ``build_query``: DS1 request -> provider query (provider station codes, ages)
2. ``MockRailApi.search``: stands in for the external API; answers in the
   provider's own format (UTC times, prices in cents, product codes)
3. ``parse_response``: provider answer -> DS1 journeys (local times, Money,
   availability, fare names)

A real adapter (DS3 decides which API) replaces step 2 with HTTP calls and
adapts steps 1 and 3 to that API's format.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..contract import (
    Availability,
    ErrorCode,
    Journey,
    JourneySearchRequest,
    Leg,
    Money,
    Offer,
    PriceBasis,
    Stop,
    TransportMode,
)
from ..errors import InvalidProviderResponse
from .mock_support import city_name, departures, distance_km, simulate, stable_number

PROVIDER_ID = "mock-rail"
OPERATOR = "Mock Rail"
STATION_PREFIX = "mr:"
CLOCK_TIMES = ("06:00", "09:00", "12:00", "15:00", "18:00")
RAIL_DETOUR_FACTOR = 1.2  # track length / straight-line distance
AVERAGE_SPEED_KMH = 140

STATION_NAMES = {
    "berlin": "Berlin Hbf",
    "hamburg": "Hamburg Hbf",
    "munich": "München Hbf",
    "cologne": "Köln Hbf",
    "frankfurt-am-main": "Frankfurt (Main) Hbf",
    "stuttgart": "Stuttgart Hbf",
    "leipzig": "Leipzig Hbf",
    "dresden": "Dresden Hbf",
    "paris": "Paris Est",
    "vienna": "Wien Hbf",
    "zurich": "Zürich HB",
    "amsterdam": "Amsterdam Centraal",
}

FARE_NAMES = {"SPARPREIS": "Sparpreis", "FLEXPREIS": "Flexpreis"}


class MockRailAdapter:
    def __init__(self, *, failure: ErrorCode | None = None, delay_seconds: float = 0.0):
        self._failure = failure
        self._delay_seconds = delay_seconds
        self._api = MockRailApi()

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    async def search(self, request: JourneySearchRequest) -> Sequence[Journey]:
        await simulate(self._failure, self._delay_seconds)
        if request.origin_id == request.destination_id:
            return []  # a ride within one city (taxi request): no direct connection here
        raw = self._api.search(build_query(request))
        return parse_response(raw, request)


# --- 1. DS1 request -> provider query ------------------------------------------ #


def station_code(location_id: str) -> str:
    return f"{STATION_PREFIX}{location_id}"


def station_name(location_id: str) -> str:
    return STATION_NAMES.get(location_id, f"{city_name(location_id)} Hbf")


def build_query(request: JourneySearchRequest) -> dict[str, Any]:
    return {
        "fromStation": station_code(request.origin_id),
        "toStation": station_code(request.destination_id),
        "earliestDeparture": request.departure_after.isoformat(),
        "latestDeparture": request.departure_before.isoformat() if request.departure_before else None,
        "travellers": [{"age": passenger.age} for passenger in request.passengers],
    }


# --- 2. simulated provider API ------------------------------------------------- #


class MockRailApi:
    """Deterministic stand-in for an external rail API."""

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        origin = _city(query["fromStation"])
        destination = _city(query["toStation"])
        earliest = datetime.fromisoformat(query["earliestDeparture"])
        latest = datetime.fromisoformat(query["latestDeparture"]) if query["latestDeparture"] else None
        ages = [traveller["age"] for traveller in query["travellers"]]

        track_km = distance_km(origin, destination) * RAIL_DETOUR_FACTOR
        minutes = round(track_km / AVERAGE_SPEED_KMH * 60) + 15
        product = "ICE" if track_km >= 150 else "RE"
        base_number = stable_number(origin, destination) % 900 + 100
        spar = max(Decimal("17.99"), Decimal(round(track_km * 0.07)) + Decimal("0.99"))
        flex = max(Decimal("29.90"), Decimal(round(track_km * 0.22)) + Decimal("0.90"))

        connections = []
        for departure in departures(earliest, latest, CLOCK_TIMES):
            # Depends only on route, slot and day, not on the search window.
            slot = CLOCK_TIMES.index(departure.strftime("%H:%M"))
            arrival = departure + timedelta(minutes=minutes)
            connections.append(
                {
                    "trainNumber": f"{product} {base_number + 2 * slot}",
                    "from": query["fromStation"],
                    "to": query["toStation"],
                    "departureUtc": _utc(departure),
                    "arrivalUtc": _utc(arrival),
                    "fares": [
                        {
                            "product": "SPARPREIS",
                            "totalCents": _cents(spar, ages),
                            "currency": "EUR",
                            "binding": True,
                            # about every fifth connection: saver fares sold out
                            "bookable": (base_number + slot + departure.toordinal()) % 5 != 0,
                        },
                        {
                            "product": "FLEXPREIS",
                            "totalCents": _cents(flex, ages),
                            "currency": "EUR",
                            "binding": True,
                            "bookable": True,
                        },
                    ],
                }
            )
        return {"connections": connections}


def _city(code: str) -> str:
    if not code.startswith(STATION_PREFIX):
        raise InvalidProviderResponse(f"Unknown station code {code!r}.")
    return code.removeprefix(STATION_PREFIX)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def rail_fare_share(age: int | None) -> Decimal:
    """Share of the adult fare: under 6 free, under 15 half, unknown age = adult."""
    if age is None or age >= 15:
        return Decimal(1)
    return Decimal(0) if age < 6 else Decimal("0.5")


def _cents(adult_fare: Decimal, ages: list[int | None]) -> int:
    total = sum((adult_fare * rail_fare_share(age) for age in ages), Decimal(0))
    return int((total * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --- 3. provider answer -> DS1 journeys ---------------------------------------- #


def parse_response(raw: Any, request: JourneySearchRequest) -> list[Journey]:
    """Normalize the provider answer. Malformed answers raise ``InvalidProviderResponse``."""
    try:
        return [_parse_connection(connection, request) for connection in raw["connections"]]
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as exc:
        # ValueError includes DS1 ContractValidationError: data the contract cannot express.
        raise InvalidProviderResponse(f"Malformed rail answer: {exc!r}") from exc


def _parse_connection(connection: dict[str, Any], request: JourneySearchRequest) -> Journey:
    local_tz = request.departure_after.tzinfo
    departure = datetime.fromisoformat(connection["departureUtc"]).astimezone(local_tz)
    arrival = datetime.fromisoformat(connection["arrivalUtc"]).astimezone(local_tz)
    origin = _city(connection["from"])
    destination = _city(connection["to"])
    train_number = connection["trainNumber"]
    journey_id = f"{PROVIDER_ID}-{train_number.replace(' ', '').lower()}-{departure:%Y%m%dT%H%M}"

    leg = Leg(
        mode=TransportMode.TRAIN,
        origin=Stop(origin, station_name(origin)),
        destination=Stop(destination, station_name(destination)),
        departure_at=departure,
        arrival_at=arrival,
        operator=OPERATOR,
        service_number=train_number,
    )
    offers = tuple(_parse_fare(fare, journey_id) for fare in connection["fares"])
    return Journey(id=journey_id, provider_id=PROVIDER_ID, legs=(leg,), offers=offers)


def _parse_fare(fare: dict[str, Any], journey_id: str) -> Offer:
    product = fare["product"]
    cents = fare.get("totalCents")
    price = None if cents is None else Money(Decimal(cents) / 100, fare["currency"], PriceBasis.TRIP_TOTAL)
    bookable = fare.get("bookable")
    availability = {True: Availability.AVAILABLE, False: Availability.SOLD_OUT}.get(bookable, Availability.UNKNOWN)
    return Offer(
        id=f"{journey_id}-{product.lower()}",
        provider_id=PROVIDER_ID,
        price=price,
        availability=availability,
        is_price_estimate=not fare.get("binding", False),
        fare_name=FARE_NAMES.get(product, product.title()),
    )
