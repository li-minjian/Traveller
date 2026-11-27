"""DS1 (#21): shared contract between the Journey Planner and all transport services.

Every transport service (flight, train, taxi, later bus, ...) is reached the same way:

    result = await service.search_journeys(request)

The Journey Planner only knows the types in this module. It never sees
provider APIs, provider IDs formats or provider error types.

The same contract is available over HTTP/JSON (see ``http_binding.py`` and
``openapi.yaml``). ``to_dict()`` / ``from_dict()`` produce and accept exactly
the JSON documented there.

Invariants are checked when an object is constructed, so an instance of
``JourneySearchRequest`` or ``JourneySearchResult`` is always valid.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

CONTRACT_VERSION = "1.0"

#: Location IDs and service IDs: lowercase slug, e.g. "berlin", "frankfurt-am-main".
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
MAX_PASSENGERS = 9
MAX_AGE = 120


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class TransportMode(StrEnum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    FERRY = "ferry"
    TAXI = "taxi"  # taxi and ride-hailing (Uber, Bolt, ...); ``Leg.operator`` names the company


class SearchStatus(StrEnum):
    """Outcome of one ``search_journeys`` call.

    Only ``NO_RESULTS`` means "there is no connection". Every other status
    without journeys means "we do not know".
    """

    SUCCESS = "success"  # all providers answered, at least one journey
    NO_RESULTS = "no_results"  # all providers answered, none has a journey
    PARTIAL = "partial"  # some providers failed, the others answered (journeys may be empty)
    UNAVAILABLE = "unavailable"  # no provider answered (timeout, outage, ...)
    INVALID_REQUEST = "invalid_request"  # the service rejects the request


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    INTERNAL_ERROR = "internal_error"


#: Error codes for which repeating the same request later can succeed.
RETRYABLE_ERROR_CODES = frozenset(
    {ErrorCode.TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE}
)


class Availability(StrEnum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


class PriceBasis(StrEnum):
    TRIP_TOTAL = "trip_total"  # whole journey, all passengers
    PER_PERSON = "per_person"  # whole journey, one passenger


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


class ContractValidationError(ValueError):
    """Raised when data does not satisfy the DS1 contract.

    ``fields`` maps a dotted path (``"journeys.0.legs.1.arrival_at"``) to messages,
    in the same shape as ``error.fields`` in the backend API conventions.
    """

    def __init__(self, fields: Mapping[str, Sequence[str]]):
        self.fields = {key: list(messages) for key, messages in fields.items()}
        summary = "; ".join(f"{key}: {', '.join(msgs)}" for key, msgs in self.fields.items())
        super().__init__(f"Contract violation: {summary}")


class _Errors:
    """Collects field errors so a caller sees all problems at once."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.fields: dict[str, list[str]] = {}

    def add(self, key: str, message: str) -> None:
        path = f"{self.prefix}{key}" if key else self.prefix.rstrip(".") or "non_field_errors"
        self.fields.setdefault(path, []).append(message)

    def merge(self, error: ContractValidationError, prefix: str) -> None:
        for key, messages in error.fields.items():
            for message in messages:
                self.add(f"{prefix}{key}" if key != "non_field_errors" else prefix.rstrip("."), message)

    def raise_if_any(self) -> None:
        if self.fields:
            raise ContractValidationError(self.fields)


def _check_id(errors: _Errors, key: str, value: str) -> None:
    if not ID_PATTERN.fullmatch(value):
        errors.add(key, "Must be a lowercase slug such as 'berlin' or 'frankfurt-am-main'.")


def _check_aware(errors: _Errors, key: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        errors.add(key, "Must include a UTC offset, e.g. '2026-12-15T08:00:00+01:00'.")


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _format_local(value: datetime) -> str:
    return value.isoformat()


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- parsing helpers for from_dict(); they record an error and return None --- #


def _require_mapping(data: Any, errors: _Errors) -> Mapping[str, Any] | None:
    if not isinstance(data, Mapping):
        errors.add("", "Must be a JSON object.")
        return None
    return data


def _get_str(data: Mapping[str, Any], key: str, errors: _Errors, *, nullable: bool = False) -> str | None:
    if key not in data:
        if nullable:
            return None
        errors.add(key, "This field is required.")
        return None
    value = data[key]
    if value is None:
        if not nullable:
            errors.add(key, "This field may not be null.")
        return None
    if not isinstance(value, str) or not value.strip():
        errors.add(key, "Must be a non-empty string.")
        return None
    return value.strip()


def _get_int(data: Mapping[str, Any], key: str, errors: _Errors, default: int | None = None) -> int | None:
    if key not in data:
        if default is None:
            errors.add(key, "This field is required.")
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        errors.add(key, "Must be an integer.")
        return None
    return value


def _get_number(data: Mapping[str, Any], key: str, errors: _Errors) -> float | None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        errors.add(key, "Must be a number.")
        return None
    return float(value)


def _get_bool(data: Mapping[str, Any], key: str, errors: _Errors) -> bool | None:
    value = data.get(key)
    if not isinstance(value, bool):
        errors.add(key, "Must be true or false.")
        return None
    return value


def _get_datetime(data: Mapping[str, Any], key: str, errors: _Errors, *, nullable: bool = False) -> datetime | None:
    raw = _get_str(data, key, errors, nullable=nullable)
    if raw is None:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        errors.add(key, "Must be an ISO 8601 date-time with UTC offset.")
        return None
    if not _is_aware(value):
        errors.add(key, "Must include a UTC offset, e.g. '2026-12-15T08:00:00+01:00'.")
        return None
    return value


def _get_enum[E: StrEnum](data: Mapping[str, Any], key: str, enum: type[E], errors: _Errors) -> E | None:
    raw = _get_str(data, key, errors)
    if raw is None:
        return None
    try:
        return enum(raw)
    except ValueError:
        allowed = ", ".join(f"'{member.value}'" for member in enum)
        errors.add(key, f"Must be one of {allowed}.")
        return None


def _get_object[T](
    data: Mapping[str, Any],
    key: str,
    parse: Callable[[Any], T],
    errors: _Errors,
    *,
    nullable: bool = False,
) -> T | None:
    if key not in data:
        errors.add(key, "This field is required.")
        return None
    value = data[key]
    if value is None:
        if not nullable:
            errors.add(key, "This field may not be null.")
        return None
    try:
        return parse(value)
    except ContractValidationError as exc:
        errors.merge(exc, f"{key}.")
        return None


def _get_list[T](
    data: Mapping[str, Any],
    key: str,
    parse: Callable[[Any], T],
    errors: _Errors,
    *,
    nullable: bool = False,
) -> list[T] | None:
    if key not in data:
        errors.add(key, "This field is required.")
        return None
    value = data[key]
    if value is None:
        if not nullable:
            errors.add(key, "This field may not be null.")
        return None
    if not isinstance(value, list):
        errors.add(key, "Must be a list.")
        return None
    items: list[T] = []
    for index, item in enumerate(value):
        try:
            items.append(parse(item))
        except ContractValidationError as exc:
            errors.merge(exc, f"{key}.{index}.")
    return items


# --------------------------------------------------------------------------- #
# Request
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Coordinates:
    """WGS 84 point, e.g. a pickup address. Geocoding addresses is not part of DS1."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        errors = _Errors()
        if not -90 <= self.latitude <= 90:
            errors.add("latitude", "Must be between -90 and 90.")
        if not -180 <= self.longitude <= 180:
            errors.add("longitude", "Must be between -180 and 180.")
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        return {"latitude": self.latitude, "longitude": self.longitude}

    @classmethod
    def from_dict(cls, data: Any) -> Coordinates:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        latitude = _get_number(mapping, "latitude", errors)
        longitude = _get_number(mapping, "longitude", errors)
        errors.raise_if_any()
        return cls(latitude=latitude, longitude=longitude)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Passenger:
    """One traveller. ``age`` in years at the travel date; ``None`` = not given.

    Services use known ages for age-based fares (child, infant, senior) and
    treat an unknown age like an adult.
    """

    age: int | None = None

    def __post_init__(self) -> None:
        errors = _Errors()
        if self.age is not None and not 0 <= self.age <= MAX_AGE:
            errors.add("age", f"Must be between 0 and {MAX_AGE}.")
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        return {"age": self.age}

    @classmethod
    def from_dict(cls, data: Any) -> Passenger:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        age = mapping.get("age")
        if age is not None and (isinstance(age, bool) or not isinstance(age, int)):
            errors.add("age", "Must be an integer or null.")
        errors.raise_if_any()
        return cls(age=age)


@dataclass(frozen=True, slots=True)
class JourneySearchRequest:
    """What the Journey Planner asks a transport service for.

    Times are local times with the UTC offset of the origin. The service returns
    journeys departing in ``[departure_after, departure_before]``. Without
    ``departure_before`` the service decides how far ahead it looks (at least
    until the end of the local day of ``departure_after``).

    ``origin_coordinates`` / ``destination_coordinates`` optionally pin the exact
    start/end point (hotel, address). Door-to-door services such as taxis use
    them; others may ignore them. With both given, origin_id and destination_id
    may be the same city (a ride within Berlin).
    """

    origin_id: str
    destination_id: str
    departure_after: datetime
    passengers: tuple[Passenger, ...] = (Passenger(),)
    departure_before: datetime | None = None
    origin_coordinates: Coordinates | None = None
    destination_coordinates: Coordinates | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "passengers", tuple(self.passengers))
        errors = _Errors()
        _check_id(errors, "origin_id", self.origin_id)
        _check_id(errors, "destination_id", self.destination_id)
        _check_route(errors, self.origin_id, self.destination_id, self.origin_coordinates, self.destination_coordinates)
        _check_aware(errors, "departure_after", self.departure_after)
        if self.departure_before is not None:
            _check_aware(errors, "departure_before", self.departure_before)
            if (
                _is_aware(self.departure_after)
                and _is_aware(self.departure_before)
                and self.departure_before <= self.departure_after
            ):
                errors.add("departure_before", "Must be later than departure_after.")
        if not 1 <= len(self.passengers) <= MAX_PASSENGERS:
            errors.add("passengers", f"Between 1 and {MAX_PASSENGERS} passengers per search.")
        errors.raise_if_any()

    @property
    def passenger_count(self) -> int:
        return len(self.passengers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_id": self.origin_id,
            "destination_id": self.destination_id,
            "origin_coordinates": self.origin_coordinates.to_dict() if self.origin_coordinates else None,
            "destination_coordinates": self.destination_coordinates.to_dict() if self.destination_coordinates else None,
            "departure_after": _format_local(self.departure_after),
            "departure_before": _format_local(self.departure_before) if self.departure_before else None,
            "passengers": [passenger.to_dict() for passenger in self.passengers],
        }

    @classmethod
    def from_dict(cls, data: Any) -> JourneySearchRequest:
        """Parse request JSON. Unknown fields are ignored (API conventions §5)."""
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        origin_id = _get_str(mapping, "origin_id", errors)
        destination_id = _get_str(mapping, "destination_id", errors)
        departure_after = _get_datetime(mapping, "departure_after", errors)
        departure_before = _get_datetime(mapping, "departure_before", errors, nullable=True)
        origin_coordinates = (
            _get_object(mapping, "origin_coordinates", Coordinates.from_dict, errors, nullable=True)
            if "origin_coordinates" in mapping
            else None
        )
        destination_coordinates = (
            _get_object(mapping, "destination_coordinates", Coordinates.from_dict, errors, nullable=True)
            if "destination_coordinates" in mapping
            else None
        )
        passengers = (
            _get_list(mapping, "passengers", Passenger.from_dict, errors)
            if "passengers" in mapping
            else [Passenger()]
        )
        # Report format problems of parsed fields together with missing/mistyped ones.
        if origin_id is not None:
            _check_id(errors, "origin_id", origin_id)
        if destination_id is not None:
            _check_id(errors, "destination_id", destination_id)
            if origin_id is not None:
                _check_route(errors, origin_id, destination_id, origin_coordinates, destination_coordinates)
        raw_passengers = mapping.get("passengers", [None])
        if isinstance(raw_passengers, list) and not 1 <= len(raw_passengers) <= MAX_PASSENGERS:
            errors.add("passengers", f"Between 1 and {MAX_PASSENGERS} passengers per search.")
        errors.raise_if_any()
        return cls(
            origin_id=origin_id,  # type: ignore[arg-type]
            destination_id=destination_id,  # type: ignore[arg-type]
            departure_after=departure_after,  # type: ignore[arg-type]
            departure_before=departure_before,
            passengers=tuple(passengers),  # type: ignore[arg-type]
            origin_coordinates=origin_coordinates,
            destination_coordinates=destination_coordinates,
        )


def _check_route(
    errors: _Errors,
    origin_id: str,
    destination_id: str,
    origin_coordinates: Coordinates | None,
    destination_coordinates: Coordinates | None,
) -> None:
    if origin_id != destination_id:
        return
    if origin_coordinates is None or destination_coordinates is None:
        errors.add(
            "destination_id",
            "Must differ from origin_id unless origin_coordinates and destination_coordinates are given.",
        )
    elif origin_coordinates == destination_coordinates:
        errors.add("destination_coordinates", "Must differ from origin_coordinates.")


# --------------------------------------------------------------------------- #
# Response model: Journey -> Leg / Offer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Money:
    """Money as defined in docs/API_CONVENTIONS.md §7. Unknown price -> ``None``, never 0."""

    amount: Decimal
    currency: str
    basis: PriceBasis

    def __post_init__(self) -> None:
        errors = _Errors()
        if not self.amount.is_finite() or self.amount < 0:
            errors.add("amount", "Must be a non-negative number.")
        elif self.amount.as_tuple().exponent < -2:  # type: ignore[operator]
            errors.add("amount", "At most two decimal places.")
        if not CURRENCY_PATTERN.fullmatch(self.currency):
            errors.add("currency", "Must be an ISO 4217 code such as 'EUR'.")
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        amount: int | float = int(self.amount) if self.amount == self.amount.to_integral_value() else float(self.amount)
        return {"amount": amount, "currency": self.currency, "basis": self.basis.value}

    @classmethod
    def from_dict(cls, data: Any) -> Money:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        raw_amount = mapping.get("amount")
        amount: Decimal | None = None
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, int | float):
            errors.add("amount", "Must be a number.")
        else:
            try:
                amount = Decimal(str(raw_amount))
            except InvalidOperation:
                errors.add("amount", "Must be a number.")
        currency = _get_str(mapping, "currency", errors)
        basis = _get_enum(mapping, "basis", PriceBasis, errors)
        errors.raise_if_any()
        return cls(amount=amount, currency=currency, basis=basis)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Stop:
    """Where a leg starts or ends.

    ``location_id`` uses the same IDs as the request (city level). ``name`` and
    ``code`` describe the concrete station or airport, e.g. "Berlin Brandenburg"/"BER".
    ``coordinates`` is the exact point if known (always set for taxi pickups/drop-offs).
    """

    location_id: str
    name: str | None = None
    code: str | None = None
    coordinates: Coordinates | None = None

    def __post_init__(self) -> None:
        errors = _Errors()
        _check_id(errors, "location_id", self.location_id)
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "name": self.name,
            "code": self.code,
            "coordinates": self.coordinates.to_dict() if self.coordinates else None,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Stop:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        location_id = _get_str(mapping, "location_id", errors)
        name = _get_str(mapping, "name", errors, nullable=True)
        code = _get_str(mapping, "code", errors, nullable=True)
        coordinates = _get_object(mapping, "coordinates", Coordinates.from_dict, errors, nullable=True)
        errors.raise_if_any()
        return cls(location_id=location_id, name=name, code=code, coordinates=coordinates)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Leg:
    """One ride in one vehicle (a single flight, a single train, a single taxi ride).

    ``is_on_demand``: no timetable; the vehicle comes when booked (taxi, Uber).
    ``departure_at`` is then the earliest expected pickup and ``arrival_at`` an
    estimate from the expected driving time.
    """

    mode: TransportMode
    origin: Stop
    destination: Stop
    departure_at: datetime
    arrival_at: datetime
    operator: str | None = None
    service_number: str | None = None
    is_on_demand: bool = False

    def __post_init__(self) -> None:
        errors = _Errors()
        _check_aware(errors, "departure_at", self.departure_at)
        _check_aware(errors, "arrival_at", self.arrival_at)
        if _is_aware(self.departure_at) and _is_aware(self.arrival_at) and self.arrival_at < self.departure_at:
            errors.add("arrival_at", "Must not be earlier than departure_at.")
        errors.raise_if_any()

    @property
    def duration_minutes(self) -> int:
        return int((self.arrival_at - self.departure_at).total_seconds() // 60)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "origin": self.origin.to_dict(),
            "destination": self.destination.to_dict(),
            "departure_at": _format_local(self.departure_at),
            "arrival_at": _format_local(self.arrival_at),
            "operator": self.operator,
            "service_number": self.service_number,
            "is_on_demand": self.is_on_demand,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Leg:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        mode = _get_enum(mapping, "mode", TransportMode, errors)
        origin = _get_object(mapping, "origin", Stop.from_dict, errors)
        destination = _get_object(mapping, "destination", Stop.from_dict, errors)
        departure_at = _get_datetime(mapping, "departure_at", errors)
        arrival_at = _get_datetime(mapping, "arrival_at", errors)
        operator = _get_str(mapping, "operator", errors, nullable=True)
        service_number = _get_str(mapping, "service_number", errors, nullable=True)
        is_on_demand = _get_bool(mapping, "is_on_demand", errors)
        errors.raise_if_any()
        return cls(
            mode=mode,  # type: ignore[arg-type]
            origin=origin,  # type: ignore[arg-type]
            destination=destination,  # type: ignore[arg-type]
            departure_at=departure_at,  # type: ignore[arg-type]
            arrival_at=arrival_at,  # type: ignore[arg-type]
            operator=operator,
            service_number=service_number,
            is_on_demand=is_on_demand,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class Offer:
    """A price/fare for a whole journey from one provider.

    ``price is None``: price unknown. ``is_price_estimate``: price comes from
    timetable/fare tables or a fare estimate, not from a live, bookable quote
    (DS2: timetable data must not look like a confirmed booking offer).

    ``price_upper``: upper bound if the provider only gives a range (typical for
    taxi/ride-hailing estimates, "23-29 EUR"); ``price`` is then the lower bound.
    ``None`` = ``price`` is a single value.
    """

    id: str
    provider_id: str
    price: Money | None
    availability: Availability = Availability.UNKNOWN
    is_price_estimate: bool = False
    fare_name: str | None = None
    booking_url: str | None = None
    price_upper: Money | None = None

    def __post_init__(self) -> None:
        errors = _Errors()
        if not self.id:
            errors.add("id", "Must be a non-empty string.")
        _check_id(errors, "provider_id", self.provider_id)
        if self.price_upper is not None:
            if self.price is None:
                errors.add("price_upper", "Only allowed together with price.")
            elif (self.price_upper.currency, self.price_upper.basis) != (self.price.currency, self.price.basis):
                errors.add("price_upper", "Must use the same currency and basis as price.")
            elif self.price_upper.amount < self.price.amount:
                errors.add("price_upper", "Must not be lower than price.")
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "price": self.price.to_dict() if self.price else None,
            "price_upper": self.price_upper.to_dict() if self.price_upper else None,
            "availability": self.availability.value,
            "is_price_estimate": self.is_price_estimate,
            "fare_name": self.fare_name,
            "booking_url": self.booking_url,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Offer:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        offer_id = _get_str(mapping, "id", errors)
        provider_id = _get_str(mapping, "provider_id", errors)
        price = _get_object(mapping, "price", Money.from_dict, errors, nullable=True)
        price_upper = _get_object(mapping, "price_upper", Money.from_dict, errors, nullable=True)
        availability = _get_enum(mapping, "availability", Availability, errors)
        is_price_estimate = _get_bool(mapping, "is_price_estimate", errors)
        fare_name = _get_str(mapping, "fare_name", errors, nullable=True)
        booking_url = _get_str(mapping, "booking_url", errors, nullable=True)
        errors.raise_if_any()
        return cls(
            id=offer_id,  # type: ignore[arg-type]
            provider_id=provider_id,  # type: ignore[arg-type]
            price=price,
            price_upper=price_upper,
            availability=availability,  # type: ignore[arg-type]
            is_price_estimate=is_price_estimate,  # type: ignore[arg-type]
            fare_name=fare_name,
            booking_url=booking_url,
        )


@dataclass(frozen=True, slots=True)
class Journey:
    """A complete trip from origin to destination: one or more legs.

    ``offers``: ``None`` = the source has no price/fare information at all
    (e.g. timetable only); ``[]`` = known to have no offers; otherwise the offers.
    """

    id: str
    provider_id: str
    legs: tuple[Leg, ...]
    offers: tuple[Offer, ...] | None = None

    def __post_init__(self) -> None:
        errors = _Errors()
        if not self.id:
            errors.add("id", "Must be a non-empty string.")
        _check_id(errors, "provider_id", self.provider_id)
        if not self.legs:
            errors.add("legs", "A journey needs at least one leg.")
        for index in range(1, len(self.legs)):
            if self.legs[index].departure_at < self.legs[index - 1].arrival_at:
                errors.add(f"legs.{index}.departure_at", "Must not be earlier than the previous leg's arrival_at.")
        if self.offers is not None:
            ids = [offer.id for offer in self.offers]
            if len(ids) != len(set(ids)):
                errors.add("offers", "Offer IDs must be unique within a journey.")
        errors.raise_if_any()

    @property
    def origin(self) -> Stop:
        return self.legs[0].origin

    @property
    def destination(self) -> Stop:
        return self.legs[-1].destination

    @property
    def departure_at(self) -> datetime:
        return self.legs[0].departure_at

    @property
    def arrival_at(self) -> datetime:
        return self.legs[-1].arrival_at

    @property
    def duration_minutes(self) -> int:
        return int((self.arrival_at - self.departure_at).total_seconds() // 60)

    @property
    def transfer_count(self) -> int:
        return len(self.legs) - 1

    @property
    def modes(self) -> frozenset[TransportMode]:
        return frozenset(leg.mode for leg in self.legs)

    def cheapest_known_price(self) -> Money | None:
        """Lowest known price among offers that are not sold out (``None`` if unknown).

        Only compares prices with the same currency and basis as the first one found;
        currency conversion is not part of DS1.
        """
        prices = [
            offer.price
            for offer in self.offers or ()
            if offer.price is not None and offer.availability is not Availability.SOLD_OUT
        ]
        if not prices:
            return None
        first = prices[0]
        comparable = [p for p in prices if p.currency == first.currency and p.basis == first.basis]
        return min(comparable, key=lambda p: p.amount)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "legs": [leg.to_dict() for leg in self.legs],
            "offers": None if self.offers is None else [offer.to_dict() for offer in self.offers],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Journey:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        journey_id = _get_str(mapping, "id", errors)
        provider_id = _get_str(mapping, "provider_id", errors)
        legs = _get_list(mapping, "legs", Leg.from_dict, errors)
        offers = _get_list(mapping, "offers", Offer.from_dict, errors, nullable=True)
        errors.raise_if_any()
        return cls(
            id=journey_id,  # type: ignore[arg-type]
            provider_id=provider_id,  # type: ignore[arg-type]
            legs=tuple(legs),  # type: ignore[arg-type]
            offers=None if offers is None else tuple(offers),
        )


# --------------------------------------------------------------------------- #
# Result and errors
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ServiceError:
    """One problem reported by a transport service.

    ``provider_id``: which provider failed (``None`` if not provider-specific).
    ``field``: the request field concerned (only for ``validation_error``).
    """

    code: ErrorCode
    message: str
    provider_id: str | None = None
    field: str | None = None
    is_retryable: bool | None = None

    def __post_init__(self) -> None:
        # Default: derive retryability from the code.
        if self.is_retryable is None:
            object.__setattr__(self, "is_retryable", self.code in RETRYABLE_ERROR_CODES)
        errors = _Errors()
        if self.provider_id is not None:
            _check_id(errors, "provider_id", self.provider_id)
        if self.field is not None and self.code is not ErrorCode.VALIDATION_ERROR:
            errors.add("field", "Only allowed for validation_error.")
        errors.raise_if_any()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "provider_id": self.provider_id,
            "field": self.field,
            "is_retryable": self.is_retryable,
        }

    @classmethod
    def from_dict(cls, data: Any) -> ServiceError:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        code = _get_enum(mapping, "code", ErrorCode, errors)
        message = _get_str(mapping, "message", errors)
        provider_id = _get_str(mapping, "provider_id", errors, nullable=True)
        error_field = _get_str(mapping, "field", errors, nullable=True)
        is_retryable = _get_bool(mapping, "is_retryable", errors)
        errors.raise_if_any()
        return cls(
            code=code,  # type: ignore[arg-type]
            message=message,  # type: ignore[arg-type]
            provider_id=provider_id,
            field=error_field,
            is_retryable=is_retryable,
        )


@dataclass(frozen=True, slots=True)
class JourneySearchResult:
    """Answer of one transport service to one ``JourneySearchRequest``.

    Status invariants (checked on construction):

    ================  ==========  ======================================
    status            journeys    errors
    ================  ==========  ======================================
    success           >= 1        none
    no_results        none        none
    partial           any         >= 1 (provider errors, not validation)
    unavailable       none        >= 1 (provider errors, not validation)
    invalid_request   none        >= 1, all validation_error
    ================  ==========  ======================================
    """

    service_id: str
    status: SearchStatus
    journeys: tuple[Journey, ...] = ()
    errors: tuple[ServiceError, ...] = ()
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        errors = _Errors()
        _check_id(errors, "service_id", self.service_id)
        _check_aware(errors, "retrieved_at", self.retrieved_at)

        has_journeys = bool(self.journeys)
        has_errors = bool(self.errors)
        validation_only = has_errors and all(e.code is ErrorCode.VALIDATION_ERROR for e in self.errors)
        any_validation = any(e.code is ErrorCode.VALIDATION_ERROR for e in self.errors)
        match self.status:
            case SearchStatus.SUCCESS:
                if not has_journeys:
                    errors.add("journeys", "'success' needs at least one journey; use 'no_results'.")
                if has_errors:
                    errors.add("errors", "'success' must not carry errors; use 'partial'.")
            case SearchStatus.NO_RESULTS:
                if has_journeys:
                    errors.add("journeys", "'no_results' must not carry journeys.")
                if has_errors:
                    errors.add("errors", "'no_results' must not carry errors; use 'partial' or 'unavailable'.")
            case SearchStatus.PARTIAL | SearchStatus.UNAVAILABLE:
                if not has_errors:
                    errors.add("errors", f"'{self.status.value}' needs at least one error.")
                if any_validation:
                    errors.add("errors", f"'{self.status.value}' must not carry validation errors.")
                if self.status is SearchStatus.UNAVAILABLE and has_journeys:
                    errors.add("journeys", "'unavailable' must not carry journeys; use 'partial'.")
            case SearchStatus.INVALID_REQUEST:
                if has_journeys:
                    errors.add("journeys", "'invalid_request' must not carry journeys.")
                if not validation_only:
                    errors.add("errors", "'invalid_request' needs one or more validation_error entries only.")

        ids = [journey.id for journey in self.journeys]
        if len(ids) != len(set(ids)):
            errors.add("journeys", "Journey IDs must be unique within a result.")
        errors.raise_if_any()

    # --- convenience constructors for service implementations --------------- #

    @classmethod
    def from_journeys(
        cls,
        service_id: str,
        journeys: Sequence[Journey],
        provider_errors: Sequence[ServiceError] = (),
    ) -> JourneySearchResult:
        """Pick the right status from what the providers returned.

        Use this when at least one provider answered. If no provider answered,
        use ``unavailable()``.
        """
        if provider_errors:
            status = SearchStatus.PARTIAL
        elif journeys:
            status = SearchStatus.SUCCESS
        else:
            status = SearchStatus.NO_RESULTS
        return cls(service_id=service_id, status=status, journeys=tuple(journeys), errors=tuple(provider_errors))

    @classmethod
    def unavailable(cls, service_id: str, *errors: ServiceError) -> JourneySearchResult:
        return cls(service_id=service_id, status=SearchStatus.UNAVAILABLE, errors=errors)

    @classmethod
    def invalid_request(cls, service_id: str, fields: Mapping[str, Sequence[str]]) -> JourneySearchResult:
        errors = tuple(
            ServiceError(code=ErrorCode.VALIDATION_ERROR, message=message, field=None if key == "non_field_errors" else key)
            for key, messages in fields.items()
            for message in messages
        )
        return cls(service_id=service_id, status=SearchStatus.INVALID_REQUEST, errors=errors)

    # --- interpretation helpers for the Journey Planner --------------------- #

    @property
    def is_complete(self) -> bool:
        """All providers answered. Only then does an empty list mean "no connection"."""
        return self.status in (SearchStatus.SUCCESS, SearchStatus.NO_RESULTS)

    @property
    def is_retryable(self) -> bool:
        return any(error.is_retryable for error in self.errors)

    def validation_fields(self) -> dict[str, list[str]]:
        """Validation errors in the API-conventions ``fields`` shape."""
        fields: dict[str, list[str]] = {}
        for error in self.errors:
            if error.code is ErrorCode.VALIDATION_ERROR:
                fields.setdefault(error.field or "non_field_errors", []).append(error.message)
        return fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "service_id": self.service_id,
            "status": self.status.value,
            "journeys": [journey.to_dict() for journey in self.journeys],
            "errors": [error.to_dict() for error in self.errors],
            "retrieved_at": _format_utc(self.retrieved_at),
        }

    @classmethod
    def from_dict(cls, data: Any) -> JourneySearchResult:
        errors = _Errors()
        mapping = _require_mapping(data, errors)
        errors.raise_if_any()
        assert mapping is not None
        version = mapping.get("contract_version")
        if not isinstance(version, str) or version.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
            errors.add("contract_version", f"Unsupported contract version; expected {CONTRACT_VERSION}.")
        service_id = _get_str(mapping, "service_id", errors)
        status = _get_enum(mapping, "status", SearchStatus, errors)
        journeys = _get_list(mapping, "journeys", Journey.from_dict, errors)
        service_errors = _get_list(mapping, "errors", ServiceError.from_dict, errors)
        retrieved_at = _get_datetime(mapping, "retrieved_at", errors)
        errors.raise_if_any()
        return cls(
            service_id=service_id,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            journeys=tuple(journeys),  # type: ignore[arg-type]
            errors=tuple(service_errors),  # type: ignore[arg-type]
            retrieved_at=retrieved_at,  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# The interface every transport service implements
# --------------------------------------------------------------------------- #


@runtime_checkable
class TransportService(Protocol):
    """Contract every transport service fulfils towards the Journey Planner.

    Rules for implementations:

    * ``service_id`` is stable and unique, e.g. ``"flight"`` or ``"train"``.
    * ``search_journeys`` reports every expected failure (provider timeout,
      rate limit, outage, broken provider answer, unsupported request) as a
      ``JourneySearchResult`` with the matching status. It does not raise for them.
    * ``result.service_id`` equals ``service_id``.
    * Provider-specific IDs, codes and errors stay inside the service.

    The caller still guards against hangs and bugs: see ``gateway.search_one``.
    """

    @property
    def service_id(self) -> str: ...

    async def search_journeys(self, request: JourneySearchRequest) -> JourneySearchResult: ...
