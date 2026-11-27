"""Airport-Finder: nearby airports with scheduled flights for a geolocation.

Data (both in this folder, refreshed with ``update_data.py``):

* ``airports.csv``: OurAirports (public domain). Only ``large_airport`` and
  ``medium_airport`` with ``scheduled_service = yes`` and an IATA code are
  used; closed airports, small airfields, heliports etc. are ignored.
* ``timezones.json``: IATA code -> IANA time zone (from the Travelpayouts
  data API), only for airports Travelpayouts marks as flightable. Needed for
  local arrival times. Airports missing here are ignored, so the finder
  never picks an airport the flight API rejects (e.g. FCN Cuxhaven).

Search: all airports within ``radius_km`` (default 30 km). If there is none,
the radius grows in steps of ``step_km`` (default 10 km) until at least one
airport is found; ``max_radius_km`` is only a safety limit.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
AIRPORTS_CSV = DATA_DIR / "airports.csv"
TIMEZONES_JSON = DATA_DIR / "timezones.json"

USABLE_TYPES = {"large_airport", "medium_airport"}
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float
    time_zone: str
    is_large: bool


@dataclass(frozen=True)
class NearbyAirport:
    airport: Airport
    distance_km: float


@dataclass(frozen=True)
class SearchArea:
    """Result of one search: the radius that was finally used and the airports in it, nearest first."""

    radius_km: float
    airports: tuple[NearbyAirport, ...]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


class AirportFinder:
    def __init__(self, airports: list[Airport]):
        if not airports:
            raise ValueError("The airport finder needs at least one airport.")
        self._airports = airports

    @classmethod
    def from_files(cls, csv_path: Path = AIRPORTS_CSV, timezones_path: Path = TIMEZONES_JSON) -> AirportFinder:
        return cls(load_airports(csv_path, timezones_path))

    def __len__(self) -> int:
        return len(self._airports)

    def nearest(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_km: float = 30.0,
        step_km: float = 10.0,
        max_radius_km: float = 2000.0,
        max_airports: int = 3,
    ) -> SearchArea:
        """Airports around a point; widens the radius step by step until at least one is found."""
        if radius_km <= 0 or step_km <= 0 or max_radius_km < radius_km or max_airports < 1:
            raise ValueError("Invalid search area settings.")
        ranked = sorted(
            (NearbyAirport(a, distance_km(latitude, longitude, a.latitude, a.longitude)) for a in self._airports),
            key=lambda nearby: (nearby.distance_km, nearby.airport.iata),
        )
        radius = radius_km
        nearest = ranked[0].distance_km
        if nearest > radius:
            steps = math.ceil((nearest - radius_km) / step_km)
            radius = min(radius_km + steps * step_km, max_radius_km)
        inside = tuple(nearby for nearby in ranked if nearby.distance_km <= radius)
        return SearchArea(radius_km=radius, airports=inside[:max_airports])


@lru_cache(maxsize=4)
def load_airports(csv_path: Path = AIRPORTS_CSV, timezones_path: Path = TIMEZONES_JSON) -> list[Airport]:
    time_zones: dict[str, str] = json.loads(timezones_path.read_text(encoding="utf-8"))
    airports: dict[str, Airport] = {}
    with csv_path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            iata = (row.get("iata_code") or "").strip().upper()
            if (
                row.get("type") not in USABLE_TYPES
                or row.get("scheduled_service") != "yes"
                or len(iata) != 3
                or iata not in time_zones
            ):
                continue
            try:
                latitude, longitude = float(row["latitude_deg"]), float(row["longitude_deg"])
            except (KeyError, ValueError):
                continue
            airports[iata] = Airport(
                iata=iata,
                name=row["name"].strip(),
                city=(row.get("municipality") or "").strip(),
                country=(row.get("iso_country") or "").strip(),
                latitude=latitude,
                longitude=longitude,
                time_zone=time_zones[iata],
                is_large=row["type"] == "large_airport",
            )
    return list(airports.values())
