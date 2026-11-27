"""Incoming search request (``JourneySearchRequest`` in domain-services/contract/openapi.yaml).

Flight-service rule on top of the contract: ``origin_coordinates`` and
``destination_coordinates`` are required, because the Airport-Finder searches
around these points. Without them the request is rejected (``invalid_request``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_WINDOW = timedelta(hours=24)
MAX_PASSENGERS = 9


class RequestInvalid(Exception):
    """All problems of a request, by field. Answered with HTTP 400."""

    def __init__(self, fields: dict[str, list[str]]):
        super().__init__("The input is invalid.")
        self.fields = fields


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SearchRequest:
    origin_id: str
    destination_id: str
    origin: Point
    destination: Point
    departure_after: datetime
    departure_before: datetime | None
    passenger_ages: tuple[int | None, ...]

    @property
    def latest_departure(self) -> datetime:
        """End of the search window; without departure_before 24 hours after departure_after."""
        return self.departure_before or self.departure_after + DEFAULT_WINDOW


def parse_request(body: Any) -> SearchRequest:
    if not isinstance(body, dict):
        raise RequestInvalid({"non_field_errors": ["Expected a JSON object."]})
    errors: dict[str, list[str]] = {}

    def fail(field: str, message: str) -> None:
        errors.setdefault(field, []).append(message)

    ids = {}
    for field in ("origin_id", "destination_id"):
        value = body.get(field)
        if value is None:
            fail(field, "This field is required.")
        elif not isinstance(value, str) or not SLUG.fullmatch(value):
            fail(field, "Must be a lowercase location slug such as 'berlin'.")
        else:
            ids[field] = value

    points = {}
    for field in ("origin_coordinates", "destination_coordinates"):
        value = body.get(field)
        if value is None:
            fail(field, "Required by the flight service: airports are searched around this point.")
            continue
        point = _point(value)
        if point is None:
            fail(field, "Must be an object with latitude (-90..90) and longitude (-180..180).")
        else:
            points[field] = point

    after = _datetime(body.get("departure_after"), "departure_after", fail, required=True)
    before = _datetime(body.get("departure_before"), "departure_before", fail, required=False)
    if after and before and before <= after:
        fail("departure_before", "Must be later than departure_after.")

    ages = _passengers(body.get("passengers"), fail)

    if errors:
        raise RequestInvalid(errors)
    return SearchRequest(
        origin_id=ids["origin_id"],
        destination_id=ids["destination_id"],
        origin=points["origin_coordinates"],
        destination=points["destination_coordinates"],
        departure_after=after,  # type: ignore[arg-type]
        departure_before=before,
        passenger_ages=ages,
    )


def _point(value: Any) -> Point | None:
    if not isinstance(value, dict):
        return None
    lat, lon = value.get("latitude"), value.get("longitude")
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in (lat, lon)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return Point(float(lat), float(lon))


def _datetime(value: Any, field: str, fail, *, required: bool) -> datetime | None:  # noqa: ANN001
    if value is None:
        if required:
            fail(field, "This field is required.")
        return None
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None:
        fail(field, "Must be an ISO 8601 date-time.")
        return None
    if parsed.utcoffset() is None:
        fail(field, "Must include a UTC offset, e.g. 2026-12-15T06:00:00+01:00.")
        return None
    return parsed


def _passengers(value: Any, fail) -> tuple[int | None, ...]:  # noqa: ANN001
    if value is None:
        return (None,)
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_PASSENGERS:
        fail("passengers", f"Must be a list with 1 to {MAX_PASSENGERS} entries.")
        return ()
    ages: list[int | None] = []
    for passenger in value:
        age = passenger.get("age") if isinstance(passenger, dict) else "invalid"
        if age is None:
            ages.append(None)
        elif isinstance(age, int) and not isinstance(age, bool) and 0 <= age <= 120:
            ages.append(age)
        else:
            fail("passengers", "Each entry must be an object with an optional age between 0 and 120.")
            return ()
    return tuple(ages)
