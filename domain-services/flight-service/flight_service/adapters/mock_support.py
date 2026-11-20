"""Helpers for the deterministic mock adapter of this service.

Mocks answer every origin/destination pair with direct connections, so the
Journey Planner can be developed without real APIs. Same input -> same output.
"""

from __future__ import annotations

import asyncio
import math
import zlib
from collections.abc import Iterator, Sequence
from datetime import datetime, time, timedelta

from ..contract import Coordinates, ErrorCode
from ..errors import ERROR_CLASSES

MAX_SEARCH_DAYS = 7
DEFAULT_WINDOW = timedelta(hours=24)
#: Distance used when a city has no known coordinates.
FALLBACK_DISTANCE_KM = 400.0

#: City centres of the cities the mocks know by name and position.
#: Unknown city IDs still work: they get a name derived from the ID.
CITIES: dict[str, tuple[str, Coordinates]] = {
    "berlin": ("Berlin", Coordinates(52.5200, 13.4050)),
    "hamburg": ("Hamburg", Coordinates(53.5511, 9.9937)),
    "munich": ("München", Coordinates(48.1374, 11.5755)),
    "cologne": ("Köln", Coordinates(50.9375, 6.9603)),
    "frankfurt-am-main": ("Frankfurt (Main)", Coordinates(50.1109, 8.6821)),
    "stuttgart": ("Stuttgart", Coordinates(48.7758, 9.1829)),
    "leipzig": ("Leipzig", Coordinates(51.3397, 12.3731)),
    "dresden": ("Dresden", Coordinates(51.0504, 13.7373)),
    "paris": ("Paris", Coordinates(48.8566, 2.3522)),
    "vienna": ("Wien", Coordinates(48.2082, 16.3738)),
    "zurich": ("Zürich", Coordinates(47.3769, 8.5417)),
    "amsterdam": ("Amsterdam", Coordinates(52.3676, 4.9041)),
}


def city_name(location_id: str) -> str:
    """Display name; for unknown IDs derived from the slug ("bad-homburg" -> "Bad Homburg")."""
    if location_id in CITIES:
        return CITIES[location_id][0]
    return " ".join(part.capitalize() for part in location_id.split("-"))


def distance_km(origin_id: str, destination_id: str) -> float:
    """Great-circle distance between city centres, or a fallback for unknown cities."""
    if origin_id not in CITIES or destination_id not in CITIES:
        return FALLBACK_DISTANCE_KM
    a, b = CITIES[origin_id][1], CITIES[destination_id][1]
    lat1, lon1, lat2, lon2 = map(math.radians, (a.latitude, a.longitude, b.latitude, b.longitude))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def stable_number(*parts: str) -> int:
    """Deterministic number for a route (same across runs, unlike ``hash``)."""
    return zlib.crc32("|".join(parts).encode())


def departures(earliest: datetime, latest: datetime | None, clock_times: Sequence[str]) -> Iterator[datetime]:
    """Daily departures at ``clock_times`` within ``[earliest, latest]``.

    Without ``latest`` the window is 24 hours, so there is always at least one
    departure. Times use the UTC offset of ``earliest``.
    """
    end = latest if latest is not None else earliest + DEFAULT_WINDOW
    tz = earliest.tzinfo
    day = earliest.date()
    for _ in range(MAX_SEARCH_DAYS + 1):
        for clock in clock_times:
            hours, minutes = map(int, clock.split(":"))
            candidate = datetime.combine(day, time(hours, minutes), tzinfo=tz)
            if earliest <= candidate <= end:
                yield candidate
        day += timedelta(days=1)
        if datetime.combine(day, time(0, 0), tzinfo=tz) > end:
            return


async def simulate(failure: ErrorCode | None, delay_seconds: float) -> None:
    """Let a mock adapter be slow or fail like a real provider would."""
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    if failure is not None:
        if failure not in ERROR_CLASSES:
            raise ValueError(f"Cannot simulate {failure!r}.")
        raise ERROR_CLASSES[failure](f"Simulated provider failure: {failure.value}.")
