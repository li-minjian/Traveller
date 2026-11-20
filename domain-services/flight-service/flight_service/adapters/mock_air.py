"""Mock flight provider ``mock-air``: a direct flight between any two cities.

Built like a real adapter, in three steps:

1. ``build_query``: DS1 request -> provider query (IATA codes, passenger types
   ADT/CHD/INF instead of ages)
2. ``MockAirApi.search``: stands in for the external API; answers in the
   provider's own format (UTC times, prices as strings, seat counts)
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

PROVIDER_ID = "mock-air"
CARRIER_CODE = "MA"
CARRIER_NAME = "Mock Air"
CLOCK_TIMES = ("07:00", "13:00", "19:00")
CRUISE_SPEED_KMH = 700
GROUND_MINUTES = 40  # taxiing, climb, approach
UNKNOWN_AIRPORT_PREFIX = "city:"

#: City -> (IATA code, airport name)
AIRPORTS = {
    "berlin": ("BER", "Berlin Brandenburg"),
    "hamburg": ("HAM", "Hamburg"),
    "munich": ("MUC", "München"),
    "cologne": ("CGN", "Köln/Bonn"),
    "frankfurt-am-main": ("FRA", "Frankfurt"),
    "stuttgart": ("STR", "Stuttgart"),
    "leipzig": ("LEJ", "Leipzig/Halle"),
    "dresden": ("DRS", "Dresden"),
    "paris": ("CDG", "Paris Charles de Gaulle"),
    "vienna": ("VIE", "Wien"),
    "zurich": ("ZRH", "Zürich"),
    "amsterdam": ("AMS", "Amsterdam Schiphol"),
}
_CITY_BY_IATA = {code: city for city, (code, _) in AIRPORTS.items()}

FARE_NAMES = {"LIGHT": "Economy Light", "CLASSIC": "Economy Classic"}


class MockAirAdapter:
    def __init__(self, *, failure: ErrorCode | None = None, delay_seconds: float = 0.0):
        self._failure = failure
        self._delay_seconds = delay_seconds
        self._api = MockAirApi()

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


def airport_code(location_id: str) -> str:
    """IATA code; cities without a known airport get a provider-internal code."""
    if location_id in AIRPORTS:
        return AIRPORTS[location_id][0]
    return f"{UNKNOWN_AIRPORT_PREFIX}{location_id}"


def airport_stop(code: str) -> Stop:
    if code in _CITY_BY_IATA:
        city = _CITY_BY_IATA[code]
        return Stop(city, AIRPORTS[city][1], code)
    if code.startswith(UNKNOWN_AIRPORT_PREFIX):
        city = code.removeprefix(UNKNOWN_AIRPORT_PREFIX)
        return Stop(city, f"{city_name(city)} Airport", None)
    raise InvalidProviderResponse(f"Unknown airport code {code!r}.")


def build_query(request: JourneySearchRequest) -> dict[str, Any]:
    ages = [passenger.age for passenger in request.passengers]
    return {
        "origin": airport_code(request.origin_id),
        "destination": airport_code(request.destination_id),
        "departFrom": request.departure_after.isoformat(),
        "departUntil": request.departure_before.isoformat() if request.departure_before else None,
        # Typical flight-API passenger types instead of ages.
        "passengers": {
            "ADT": sum(1 for age in ages if age is None or age >= 12),
            "CHD": sum(1 for age in ages if age is not None and 2 <= age < 12),
            "INF": sum(1 for age in ages if age is not None and age < 2),
        },
    }


# --- 2. simulated provider API ------------------------------------------------- #

PASSENGER_TYPE_SHARE = {"ADT": Decimal(1), "CHD": Decimal("0.75"), "INF": Decimal("0.1")}


class MockAirApi:
    """Deterministic stand-in for an external flight API."""

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        origin = airport_stop(query["origin"]).location_id
        destination = airport_stop(query["destination"]).location_id
        earliest = datetime.fromisoformat(query["departFrom"])
        latest = datetime.fromisoformat(query["departUntil"]) if query["departUntil"] else None

        km = distance_km(origin, destination)
        minutes = 5 * round((GROUND_MINUTES + km / CRUISE_SPEED_KMH * 60) / 5)
        base_number = stable_number(origin, destination) % 9000 + 1000
        light = (Decimal(49) + Decimal(str(round(km * 0.10, 2)))).quantize(Decimal("0.01"))
        classic = light + Decimal(50)
        share = sum(PASSENGER_TYPE_SHARE[kind] * count for kind, count in query["passengers"].items())

        flights = []
        for departure in departures(earliest, latest, CLOCK_TIMES):
            slot = CLOCK_TIMES.index(departure.strftime("%H:%M"))
            flights.append(
                {
                    "carrier": {"code": CARRIER_CODE, "name": CARRIER_NAME},
                    "number": str(base_number + slot),
                    "origin": query["origin"],
                    "destination": query["destination"],
                    "departureTime": _utc(departure),
                    "arrivalTime": _utc(departure + timedelta(minutes=minutes)),
                    "fareFamilies": [
                        {
                            "name": "LIGHT",
                            "price": {"amount": _amount(light * share), "currency": "EUR"},
                            # 0 = sold out on some days
                            "seatsAvailable": (base_number + slot + departure.toordinal()) % 4,
                        },
                        {
                            "name": "CLASSIC",
                            "price": {"amount": _amount(classic * share), "currency": "EUR"},
                            "seatsAvailable": 9,
                        },
                    ],
                }
            )
        return {"flights": flights}


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _amount(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --- 3. provider answer -> DS1 journeys ---------------------------------------- #


def parse_response(raw: Any, request: JourneySearchRequest) -> list[Journey]:
    """Normalize the provider answer. Malformed answers raise ``InvalidProviderResponse``."""
    try:
        return [_parse_flight(flight, request) for flight in raw["flights"]]
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as exc:
        # ValueError includes DS1 ContractValidationError: data the contract cannot express.
        raise InvalidProviderResponse(f"Malformed flight answer: {exc!r}") from exc


def _parse_flight(flight: dict[str, Any], request: JourneySearchRequest) -> Journey:
    local_tz = request.departure_after.tzinfo
    departure = datetime.fromisoformat(flight["departureTime"]).astimezone(local_tz)
    arrival = datetime.fromisoformat(flight["arrivalTime"]).astimezone(local_tz)
    carrier = flight["carrier"]
    flight_number = f"{carrier['code']} {flight['number']}"
    journey_id = f"{PROVIDER_ID}-{flight_number.replace(' ', '').lower()}-{departure:%Y%m%dT%H%M}"

    leg = Leg(
        mode=TransportMode.FLIGHT,
        origin=airport_stop(flight["origin"]),
        destination=airport_stop(flight["destination"]),
        departure_at=departure,
        arrival_at=arrival,
        operator=carrier.get("name"),
        service_number=flight_number,
    )
    offers = tuple(_parse_fare(fare, journey_id) for fare in flight["fareFamilies"])
    return Journey(id=journey_id, provider_id=PROVIDER_ID, legs=(leg,), offers=offers)


def _parse_fare(fare: dict[str, Any], journey_id: str) -> Offer:
    name = fare["name"]
    raw_price = fare.get("price")
    price = (
        None
        if raw_price is None
        else Money(Decimal(raw_price["amount"]), raw_price["currency"], PriceBasis.TRIP_TOTAL)
    )
    seats = fare.get("seatsAvailable")
    if seats is None:
        availability = Availability.UNKNOWN
    else:
        availability = Availability.AVAILABLE if seats > 0 else Availability.SOLD_OUT
    return Offer(
        id=f"{journey_id}-{name.lower()}",
        provider_id=PROVIDER_ID,
        price=price,
        availability=availability,
        is_price_estimate=False,  # live quote from the provider
        fare_name=FARE_NAMES.get(name, name.title()),
    )
