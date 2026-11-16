"""Three deterministic mock transport services that follow the DS1 contract.

They exist to show (and test) that the Journey Planner can query different
services the same way. Real services with provider adapters follow in DS2/DS6.

* ``flight`` and ``train``: fixed timetables; every day has the same departures.
  Times use the UTC offset of ``request.departure_after``. Fares depend on the
  passengers' ages (unknown age = adult).
* ``taxi``: on-demand rides between any two points in the known cities; price
  from distance, per vehicle.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .contract import (
    Availability,
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
    ServiceError,
    Stop,
    TransportMode,
)

MAX_SEARCH_DAYS = 7
CENT = Decimal("0.01")


def _money(amount: Decimal, currency: str = "EUR") -> Money:
    return Money(amount.quantize(CENT, rounding=ROUND_HALF_UP), currency, PriceBasis.TRIP_TOTAL)


class _MockService:
    """Common mock behaviour: provider outages and slow answers.

    ``unavailable_providers`` simulates provider outages (-> ``partial`` or
    ``unavailable``); ``delay_seconds`` simulates a slow service.
    """

    def __init__(
        self,
        service_id: str,
        provider_ids: Sequence[str],
        *,
        unavailable_providers: Iterable[str] = (),
        delay_seconds: float = 0.0,
    ):
        self._service_id = service_id
        self._providers = tuple(provider_ids)
        self._unavailable = frozenset(unavailable_providers)
        self._delay_seconds = delay_seconds

    @property
    def service_id(self) -> str:
        return self._service_id

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return self._providers

    async def search_journeys(self, request: JourneySearchRequest) -> JourneySearchResult:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)

        provider_errors = [
            ServiceError(code=ErrorCode.PROVIDER_UNAVAILABLE, message="Mock provider is switched off.", provider_id=p)
            for p in self._providers
            if p in self._unavailable
        ]
        if len(provider_errors) == len(self._providers):
            return JourneySearchResult.unavailable(self._service_id, *provider_errors)

        journeys = [
            journey
            for provider_id in self._providers
            if provider_id not in self._unavailable
            for journey in self._search(request, provider_id)
        ]
        journeys.sort(key=lambda j: (j.departure_at, j.id))
        return JourneySearchResult.from_journeys(self._service_id, journeys, provider_errors)

    def _search(self, request: JourneySearchRequest, provider_id: str) -> list[Journey]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Timetable services: flight, train
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _LegTemplate:
    mode: TransportMode
    origin: Stop
    destination: Stop
    departs: str  # "HH:MM"
    arrives: str  # "HH:MM", or "HH:MM+1" for the next day
    operator: str | None
    service_number: str | None


@dataclass(frozen=True, slots=True)
class _OfferTemplate:
    fare_name: str | None
    adult_price: Decimal | None  # None: price unknown
    currency: str = "EUR"
    availability: Availability = Availability.AVAILABLE
    is_price_estimate: bool = False


@dataclass(frozen=True, slots=True)
class _JourneyTemplate:
    provider_id: str
    key: str
    legs: tuple[_LegTemplate, ...]
    offers: tuple[_OfferTemplate, ...] | None  # None: provider has no price data

    @property
    def route(self) -> tuple[str, str]:
        return self.legs[0].origin.location_id, self.legs[-1].destination.location_id


#: Share of the adult fare a passenger pays, by age (None = age not given).
FareFactor = Callable[[int | None], Decimal]


def rail_fare_factor(age: int | None) -> Decimal:
    if age is None or age >= 15:
        return Decimal(1)
    return Decimal(0) if age < 6 else Decimal("0.5")


def air_fare_factor(age: int | None) -> Decimal:
    if age is None or age >= 12:
        return Decimal(1)
    return Decimal("0.1") if age < 2 else Decimal("0.75")


class MockTimetableService(_MockService):
    """Answers from a fixed daily timetable."""

    def __init__(
        self,
        service_id: str,
        timetable: Iterable[_JourneyTemplate],
        fare_factor: FareFactor,
        **options,  # noqa: ANN003
    ):
        self._timetable = tuple(timetable)
        self._fare_factor = fare_factor
        super().__init__(service_id, tuple(dict.fromkeys(t.provider_id for t in self._timetable)), **options)

    def _search(self, request: JourneySearchRequest, provider_id: str) -> list[Journey]:
        route = (request.origin_id, request.destination_id)
        return [
            journey
            for day in _search_days(request)
            for template in self._timetable
            if template.provider_id == provider_id and template.route == route
            for journey in [self._build(template, day, request)]
            if _in_window(journey.departure_at, request)
        ]

    def _build(self, template: _JourneyTemplate, day: date, request: JourneySearchRequest) -> Journey:
        tz = request.departure_after.tzinfo
        journey_id = f"{template.provider_id}-{template.key}-{day.isoformat()}"
        legs = tuple(
            Leg(
                mode=leg.mode,
                origin=leg.origin,
                destination=leg.destination,
                departure_at=_at(day, leg.departs, tz),
                arrival_at=_at(day, leg.arrives, tz),
                operator=leg.operator,
                service_number=leg.service_number,
            )
            for leg in template.legs
        )
        offers = None
        if template.offers is not None:
            offers = tuple(
                Offer(
                    id=f"{journey_id}-{index}",
                    provider_id=template.provider_id,
                    price=None
                    if offer.adult_price is None
                    else _money(self._total(offer.adult_price, request.passengers), offer.currency),
                    availability=offer.availability,
                    is_price_estimate=offer.is_price_estimate,
                    fare_name=offer.fare_name,
                )
                for index, offer in enumerate(template.offers)
            )
        return Journey(id=journey_id, provider_id=template.provider_id, legs=legs, offers=offers)

    def _total(self, adult_price: Decimal, passengers: Sequence[Passenger]) -> Decimal:
        return sum((adult_price * self._fare_factor(p.age) for p in passengers), Decimal(0))


def _search_days(request: JourneySearchRequest) -> list[date]:
    first = request.departure_after.date()
    if request.departure_before is None:
        return [first]
    last = request.departure_before.astimezone(request.departure_after.tzinfo).date()
    span = min((last - first).days, MAX_SEARCH_DAYS - 1)
    return [first + timedelta(days=offset) for offset in range(span + 1)]


def _in_window(departure: datetime, request: JourneySearchRequest) -> bool:
    if departure < request.departure_after:
        return False
    return request.departure_before is None or departure <= request.departure_before


def _at(day: date, clock: str, tz) -> datetime:  # noqa: ANN001 - tzinfo
    days_later = 0
    if "+" in clock:
        clock, extra = clock.split("+")
        days_later = int(extra)
    hours, minutes = (int(part) for part in clock.split(":"))
    return datetime.combine(day + timedelta(days=days_later), time(hours, minutes), tzinfo=tz)


# --------------------------------------------------------------------------- #
# On-demand service: taxi / ride-hailing
# --------------------------------------------------------------------------- #

#: City centres, used when the request gives no exact coordinates.
CITY_CENTRES: dict[str, Coordinates] = {
    "berlin": Coordinates(52.5200, 13.4050),
    "potsdam": Coordinates(52.3906, 13.0645),
    "munich": Coordinates(48.1374, 11.5755),
    "cologne": Coordinates(50.9375, 6.9603),
    "frankfurt-am-main": Coordinates(50.1109, 8.6821),
    "paris": Coordinates(48.8566, 2.3522),
}

ROAD_FACTOR = 1.3  # road distance / straight-line distance
MAX_RIDE_KM = 150.0


@dataclass(frozen=True, slots=True)
class _VehicleClass:
    fare_name: str
    seats: int
    base: Decimal
    per_km: Decimal
    range_factor: Decimal | None  # None: single estimate; else upper = price * factor


@dataclass(frozen=True, slots=True)
class _RideProvider:
    provider_id: str
    operator: str
    vehicle_classes: tuple[_VehicleClass, ...]


TAXI_PROVIDERS: Sequence[_RideProvider] = (
    _RideProvider(
        "mock-taxi",
        "Mock Taxi",
        (
            _VehicleClass("Taxi", 4, Decimal("4.30"), Decimal("2.80"), None),
            _VehicleClass("Großraumtaxi", 8, Decimal("11.30"), Decimal("2.80"), None),
        ),
    ),
    _RideProvider(
        "mock-ride",
        "Mock Ride",
        (
            _VehicleClass("Standard", 4, Decimal("3.00"), Decimal("1.90"), Decimal("1.25")),
            _VehicleClass("XL", 6, Decimal("5.00"), Decimal("2.60"), Decimal("1.25")),
        ),
    ),
)


class MockTaxiService(_MockService):
    """Door-to-door rides. One journey per provider, departing at ``departure_after``.

    Unknown city without coordinates or rides over ``MAX_RIDE_KM`` -> no journey.
    Offers only for vehicle classes with enough seats; none fits -> ``offers: []``.
    """

    def __init__(self, providers: Iterable[_RideProvider] = TAXI_PROVIDERS, **options):  # noqa: ANN003
        self._ride_providers = {p.provider_id: p for p in providers}
        super().__init__("taxi", tuple(self._ride_providers), **options)

    def _search(self, request: JourneySearchRequest, provider_id: str) -> list[Journey]:
        start = request.origin_coordinates or CITY_CENTRES.get(request.origin_id)
        end = request.destination_coordinates or CITY_CENTRES.get(request.destination_id)
        if start is None or end is None:
            return []
        road_km = _distance_km(start, end) * ROAD_FACTOR
        if road_km > MAX_RIDE_KM:
            return []

        provider = self._ride_providers[provider_id]
        departure = request.departure_after
        arrival = departure + timedelta(minutes=_driving_minutes(road_km))
        journey_id = f"{provider_id}-{departure.strftime('%Y%m%dT%H%M')}"
        km = Decimal(str(round(road_km, 1)))

        offers = tuple(
            Offer(
                id=f"{journey_id}-{index}",
                provider_id=provider_id,
                price=_money(price := vc.base + vc.per_km * km),
                price_upper=None if vc.range_factor is None else _money(price * vc.range_factor),
                availability=Availability.AVAILABLE,
                is_price_estimate=True,
                fare_name=vc.fare_name,
            )
            for index, vc in enumerate(provider.vehicle_classes)
            if vc.seats >= request.passenger_count
        )
        leg = Leg(
            mode=TransportMode.TAXI,
            origin=Stop(request.origin_id, coordinates=start),
            destination=Stop(request.destination_id, coordinates=end),
            departure_at=departure,
            arrival_at=arrival,
            operator=provider.operator,
            is_on_demand=True,
        )
        if _in_window(departure, request):
            return [Journey(id=journey_id, provider_id=provider_id, legs=(leg,), offers=offers)]
        return []


def _driving_minutes(road_km: float) -> int:
    """First 10 km at city speed (25 km/h), the rest at 70 km/h."""
    city_km = min(road_km, 10.0)
    return max(1, round(city_km / 25 * 60 + (road_km - city_km) / 70 * 60))


def _distance_km(a: Coordinates, b: Coordinates) -> float:
    """Great-circle distance (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# --------------------------------------------------------------------------- #
# Fixed timetable data
# --------------------------------------------------------------------------- #

BER = Stop("berlin", "Berlin Brandenburg Airport", "BER")
MUC = Stop("munich", "Munich Airport", "MUC")
CDG = Stop("paris", "Paris Charles de Gaulle", "CDG")
FRA = Stop("frankfurt-am-main", "Frankfurt Airport", "FRA")
BERLIN_HBF = Stop("berlin", "Berlin Hbf", None)
MUENCHEN_HBF = Stop("munich", "München Hbf", None)
KOELN_HBF = Stop("cologne", "Köln Hbf", None)
PARIS_NORD = Stop("paris", "Paris Nord", None)


def _flight(origin: Stop, destination: Stop, departs: str, arrives: str, number: str, airline: str) -> _LegTemplate:
    return _LegTemplate(TransportMode.FLIGHT, origin, destination, departs, arrives, airline, number)


def _train(origin: Stop, destination: Stop, departs: str, arrives: str, number: str) -> _LegTemplate:
    return _LegTemplate(TransportMode.TRAIN, origin, destination, departs, arrives, "Mock Rail", number)


def _fares(*fares: tuple[str | None, str | None]) -> tuple[_OfferTemplate, ...]:
    return tuple(_OfferTemplate(name, None if price is None else Decimal(price)) for name, price in fares)


FLIGHT_TIMETABLE: Sequence[_JourneyTemplate] = (
    _JourneyTemplate(
        "mock-airline", "ma100", (_flight(BER, MUC, "07:05", "08:15", "MA 100", "Mock Air"),),
        _fares(("Economy Light", "89"), ("Economy Classic", "129")),
    ),
    _JourneyTemplate(
        "mock-airline", "ma104", (_flight(BER, MUC, "18:40", "19:50", "MA 104", "Mock Air"),),
        (
            _OfferTemplate("Economy Light", Decimal("119"), availability=Availability.SOLD_OUT),
            _OfferTemplate("Economy Classic", Decimal("159.90")),
        ),
    ),
    _JourneyTemplate(
        "mock-charter", "mc7", (_flight(BER, MUC, "12:30", "13:45", "MC 7", "Mock Charter"),),
        _fares(("Basic", None)),  # price unknown
    ),
    _JourneyTemplate(
        "mock-airline", "ma300", (_flight(BER, CDG, "09:00", "10:55", "MA 300", "Mock Air"),),
        _fares(("Economy Light", "99")),
    ),
    _JourneyTemplate(
        "mock-airline", "ma210-ma410",
        (
            _flight(BER, FRA, "06:30", "07:40", "MA 210", "Mock Air"),
            _flight(FRA, CDG, "08:45", "10:00", "MA 410", "Mock Air"),
        ),
        _fares(("Economy Light", "74.50")),
    ),
)

TRAIN_TIMETABLE: Sequence[_JourneyTemplate] = (
    _JourneyTemplate(
        "mock-rail", "ice501", (_train(BERLIN_HBF, MUENCHEN_HBF, "08:00", "12:04", "ICE 501"),),
        (
            _OfferTemplate("Super Sparpreis", Decimal("29.99")),
            _OfferTemplate("Flexpreis", Decimal("149.90"), is_price_estimate=True),
        ),
    ),
    _JourneyTemplate(
        "mock-rail", "ice1001", (_train(BERLIN_HBF, MUENCHEN_HBF, "14:00", "18:02", "ICE 1001"),),
        None,  # timetable only, no price information
    ),
    _JourneyTemplate(
        "mock-rail", "ice645-est9450",
        (
            _train(BERLIN_HBF, KOELN_HBF, "06:46", "11:13", "ICE 645"),
            _train(KOELN_HBF, PARIS_NORD, "11:43", "15:05", "EST 9450"),
        ),
        (),  # known: no offers (e.g. booking not open yet)
    ),
)


def mock_flight_service(**options) -> MockTimetableService:  # noqa: ANN003
    """Flight mock with providers ``mock-airline`` and ``mock-charter``. Infants < 2: 10 %, children < 12: 75 %."""
    return MockTimetableService("flight", FLIGHT_TIMETABLE, air_fare_factor, **options)


def mock_train_service(**options) -> MockTimetableService:  # noqa: ANN003
    """Train mock with provider ``mock-rail``. Children < 6 free, < 15 half price."""
    return MockTimetableService("train", TRAIN_TIMETABLE, rail_fare_factor, **options)


def mock_taxi_service(**options) -> MockTaxiService:  # noqa: ANN003
    """Taxi mock with providers ``mock-taxi`` (fixed estimate) and ``mock-ride`` (price range, Uber-like)."""
    return MockTaxiService(**options)
