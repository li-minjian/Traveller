"""Invented example flights, a stand-in until the Flight Service exists.

The data is deterministic: the same request always returns the same flights.
Four routes from Berlin are written out by hand (ROUTES). Every other pair of
the cities in PLACES gets flights that are generated from the distance and a
checksum of the city names: a few direct flights and a few with one or two
changes at a hub. Prices depend on the weekday so that searching nearby dates
can make a difference.
"""

import datetime
import math
import zlib
from functools import lru_cache
from zoneinfo import ZoneInfo

# key -> (display name, time zone, further names the search accepts)
PLACES = {
    "berlin": ("Berlin", "Europe/Berlin", ("ber",)),
    "hamburg": ("Hamburg", "Europe/Berlin", ("ham",)),
    "muenchen": ("München", "Europe/Berlin", ("munich", "munchen", "muc")),
    "frankfurt": ("Frankfurt", "Europe/Berlin", ("frankfurt am main", "fra")),
    "koeln": ("Köln", "Europe/Berlin", ("cologne", "koln", "cgn")),
    "duesseldorf": ("Düsseldorf", "Europe/Berlin", ("dusseldorf", "dus")),
    "stuttgart": ("Stuttgart", "Europe/Berlin", ("str",)),
    "wien": ("Wien", "Europe/Vienna", ("vienna", "vie")),
    "zuerich": ("Zürich", "Europe/Zurich", ("zurich", "zrh")),
    "amsterdam": ("Amsterdam", "Europe/Amsterdam", ("ams",)),
    "paris": ("Paris", "Europe/Paris", ("cdg",)),
    "london": ("London", "Europe/London", ("lon", "lhr")),
    "dublin": ("Dublin", "Europe/Dublin", ("dub",)),
    "madrid": ("Madrid", "Europe/Madrid", ("mad",)),
    "barcelona": ("Barcelona", "Europe/Madrid", ("bcn",)),
    "palma": ("Palma de Mallorca", "Europe/Madrid", ("palma", "mallorca", "pmi")),
    "malaga": ("Málaga", "Europe/Madrid", ("malaga", "agp")),
    "lissabon": ("Lissabon", "Europe/Lisbon", ("lisbon", "lisboa", "lis")),
    "porto": ("Porto", "Europe/Lisbon", ("opo",)),
    "rom": ("Rom", "Europe/Rome", ("rome", "roma", "fco")),
    "mailand": ("Mailand", "Europe/Rome", ("milan", "milano", "mxp")),
    "nizza": ("Nizza", "Europe/Paris", ("nice", "nce")),
    "athen": ("Athen", "Europe/Athens", ("athens", "ath")),
    "istanbul": ("Istanbul", "Europe/Istanbul", ("ist",)),
    "kopenhagen": ("Kopenhagen", "Europe/Copenhagen", ("copenhagen", "cph")),
    "stockholm": ("Stockholm", "Europe/Stockholm", ("arn",)),
    "oslo": ("Oslo", "Europe/Oslo", ("osl",)),
    "prag": ("Prag", "Europe/Prague", ("prague", "praha", "prg")),
    "budapest": ("Budapest", "Europe/Budapest", ("bud",)),
    "warschau": ("Warschau", "Europe/Warsaw", ("warsaw", "warszawa", "waw")),
}

COUNTRIES = {
    "berlin": "Deutschland", "hamburg": "Deutschland", "muenchen": "Deutschland",
    "frankfurt": "Deutschland", "koeln": "Deutschland", "duesseldorf": "Deutschland",
    "stuttgart": "Deutschland", "wien": "Österreich", "zuerich": "Schweiz",
    "amsterdam": "Niederlande", "paris": "Frankreich", "nizza": "Frankreich",
    "london": "Vereinigtes Königreich", "dublin": "Irland", "madrid": "Spanien",
    "barcelona": "Spanien", "palma": "Spanien", "malaga": "Spanien", "lissabon": "Portugal",
    "porto": "Portugal", "rom": "Italien", "mailand": "Italien", "athen": "Griechenland",
    "istanbul": "Türkei", "kopenhagen": "Dänemark", "stockholm": "Schweden",
    "oslo": "Norwegen", "prag": "Tschechien", "budapest": "Ungarn", "warschau": "Polen",
}

# Latitude and longitude, used for the flight time of generated routes.
COORDINATES = {
    "berlin": (52.52, 13.40), "hamburg": (53.55, 9.99), "muenchen": (48.14, 11.58),
    "frankfurt": (50.11, 8.68), "koeln": (50.94, 6.96), "duesseldorf": (51.23, 6.77),
    "stuttgart": (48.78, 9.18), "wien": (48.21, 16.37), "zuerich": (47.37, 8.54),
    "amsterdam": (52.37, 4.90), "paris": (48.86, 2.35), "london": (51.51, -0.13),
    "dublin": (53.35, -6.26), "madrid": (40.42, -3.70), "barcelona": (41.39, 2.17),
    "palma": (39.57, 2.65), "malaga": (36.72, -4.42), "lissabon": (38.72, -9.14),
    "porto": (41.15, -8.61), "rom": (41.90, 12.50), "mailand": (45.46, 9.19),
    "nizza": (43.70, 7.27), "athen": (37.98, 23.73), "istanbul": (41.01, 28.98),
    "kopenhagen": (55.68, 12.57), "stockholm": (59.33, 18.07), "oslo": (59.91, 10.75),
    "prag": (50.08, 14.44), "budapest": (47.50, 19.04), "warschau": (52.23, 21.01),
}

# Airports where generated connections change planes.
HUBS = ("frankfurt", "muenchen", "amsterdam", "paris", "madrid", "zuerich", "wien", "london")

_ALIASES = {
    alias: key
    for key, (name, _, aliases) in PLACES.items()
    for alias in (key, name.lower(), *aliases)
}

EVERY_DAY = frozenset(range(7))  # Monday is 0
ROME_DAYS = frozenset({0, 2, 4, 5})  # not daily, so a fixed date can find nothing

# (origin, destination) -> list of (suffix, weekdays, base price in EUR per person, legs)
# A leg is (from, to, departure, duration in minutes, flight number). The departure
# is a local time "HH:MM" or, for a connecting flight, the minutes to wait after
# the previous leg has landed.
ROUTES = {
    ("berlin", "lissabon"): [
        ("direct-early", EVERY_DAY, 189.0, [("berlin", "lissabon", "06:40", 235, "EX 1201")]),
        ("direct-late", EVERY_DAY, 229.0, [("berlin", "lissabon", "17:55", 240, "EX 1207")]),
        ("via-madrid", EVERY_DAY, 142.5, [
            ("berlin", "madrid", "10:15", 185, "EX 3310"),
            ("madrid", "lissabon", "14:50", 80, "EX 3344"),
        ]),
        # Deliberately implausible: only 25 minutes to change planes.
        ("via-frankfurt", EVERY_DAY, 119.0, [
            ("berlin", "frankfurt", "07:05", 70, "EX 2100"),
            ("frankfurt", "lissabon", "08:40", 185, "EX 2188"),
        ]),
        ("via-paris", EVERY_DAY, 164.0, [
            ("berlin", "paris", "12:30", 110, "EX 4012"),
            ("paris", "lissabon", "15:45", 150, "EX 4090"),
        ]),
        ("via-zuerich-madrid", EVERY_DAY, 98.0, [
            ("berlin", "zuerich", "06:00", 90, "EX 5001"),
            ("zuerich", "madrid", "08:40", 135, "EX 5044"),
            ("madrid", "lissabon", "13:00", 80, "EX 3340"),
        ]),
    ],
    ("berlin", "barcelona"): [
        ("direct-early", EVERY_DAY, 89.0, [("berlin", "barcelona", "07:20", 160, "EX 1401")]),
        ("direct-noon", EVERY_DAY, 119.0, [("berlin", "barcelona", "15:10", 160, "EX 1405")]),
        ("direct-late", EVERY_DAY, 74.0, [("berlin", "barcelona", "20:30", 165, "EX 1409")]),
        ("via-zuerich", EVERY_DAY, 69.0, [
            ("berlin", "zuerich", "09:00", 90, "EX 5003"),
            ("zuerich", "barcelona", "11:30", 105, "EX 5060"),
        ]),
        ("via-frankfurt", EVERY_DAY, 81.0, [
            ("berlin", "frankfurt", "06:15", 70, "EX 2098"),
            ("frankfurt", "barcelona", "09:10", 125, "EX 2150"),
        ]),
    ],
    ("berlin", "rom"): [
        ("direct-early", ROME_DAYS, 109.0, [("berlin", "rom", "08:05", 130, "EX 1601")]),
        ("direct-late", ROME_DAYS, 95.0, [("berlin", "rom", "18:40", 130, "EX 1607")]),
        ("via-muenchen", ROME_DAYS, 78.0, [
            ("berlin", "muenchen", "10:00", 70, "EX 2301"),
            ("muenchen", "rom", "12:20", 95, "EX 2370"),
        ]),
    ],
    ("berlin", "london"): [
        ("direct-early", EVERY_DAY, 59.0, [("berlin", "london", "07:00", 115, "EX 1801")]),
        ("direct-noon", EVERY_DAY, 85.0, [("berlin", "london", "13:25", 115, "EX 1805")]),
        ("direct-late", EVERY_DAY, 49.0, [("berlin", "london", "19:50", 120, "EX 1809")]),
        ("via-amsterdam", EVERY_DAY, 45.0, [
            ("berlin", "amsterdam", "09:10", 85, "EX 6001"),
            ("amsterdam", "london", "11:40", 75, "EX 6040"),
        ]),
    ],
}

# Friday and Sunday are expensive, Tuesday and Wednesday cheap.
_WEEKDAY_FACTOR = {1: 0.85, 2: 0.85, 4: 1.25, 6: 1.25}
_MAX_DAYS = 31


def resolve_place(name: str) -> str | None:
    return _ALIASES.get(name.strip().lower())


class DummyFlightProvider:
    mode = "flight"
    name = "dummy"

    def places(self) -> list[dict]:
        """The places this provider has flights for."""
        return [
            {
                "name": name,
                "country": COUNTRIES[key],
                "aliases": sorted({key, *aliases} - {name.lower()}),
            }
            for key, (name, _, aliases) in PLACES.items()
        ]

    def search(self, request: dict) -> list[dict]:
        origin = resolve_place(request["origin"])
        destination = resolve_place(request["destination"])
        templates = _templates(origin, destination)
        earliest = request["departure"]["earliest"]
        latest = request["departure"]["latest"]
        journeys = []
        day = earliest
        while day <= latest and (day - earliest).days < _MAX_DAYS:
            for suffix, weekdays, base_price, legs in templates:
                if day.weekday() in weekdays:
                    journeys.append(
                        self._journey(origin, destination, day, suffix, base_price, legs)
                    )
            day += datetime.timedelta(days=1)
        return journeys

    def _journey(self, origin, destination, day, suffix, base_price, leg_templates) -> dict:
        journey_id = f"dummy-{origin}-{destination}-{day.isoformat()}-{suffix}"
        price = round(base_price * _WEEKDAY_FACTOR.get(day.weekday(), 1.0), 2)
        legs = []
        landed = None
        for start, end, leaves, duration, number in leg_templates:
            if isinstance(leaves, int):
                departure = (landed + datetime.timedelta(minutes=leaves)).astimezone(
                    ZoneInfo(PLACES[start][1])
                )
            else:
                hour, minute = (int(part) for part in leaves.split(":"))
                departure = datetime.datetime.combine(
                    day, datetime.time(hour, minute), ZoneInfo(PLACES[start][1])
                )
            arrival = (departure + datetime.timedelta(minutes=duration)).astimezone(
                ZoneInfo(PLACES[end][1])
            )
            landed = arrival
            legs.append({
                "mode": "flight",
                "origin": PLACES[start][0],
                "destination": PLACES[end][0],
                "departure": departure.isoformat(),
                "arrival": arrival.isoformat(),
                "carrier": "Example Air",
                "number": number,
            })
        return {
            "id": journey_id,
            "legs": legs,
            "offers": [{
                "id": f"{journey_id}-a",
                "provider": self.name,
                "price": {"amount": price, "currency": "EUR", "basis": "per_person"},
            }],
        }


_DEPARTURES = ("06:10", "07:25", "08:50", "10:35", "12:15", "14:05", "15:50", "17:30", "19:20", "21:05")
_ALL_DAYS = tuple(range(7))


def _templates(origin: str | None, destination: str | None) -> list:
    """Hand-written route if there is one, otherwise generated flights."""
    if origin is None or destination is None or origin == destination:
        return []
    return ROUTES.get((origin, destination)) or _generated(origin, destination)


def _number(*parts) -> int:
    """Stable pseudo-random number from the given parts (the same on every run)."""
    return zlib.crc32("|".join(str(part) for part in parts).encode("utf-8"))


def _distance_km(start: str, end: str) -> float:
    lat1, lon1 = (math.radians(value) for value in COORDINATES[start])
    lat2, lon2 = (math.radians(value) for value in COORDINATES[end])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _flight_minutes(start: str, end: str) -> int:
    """Block time: taxiing, climb and descent plus cruising at about 780 km/h."""
    return int(round((40 + _distance_km(start, end) / 13) / 5) * 5)


def _clock(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _flight_number(*parts) -> str:
    return f"EX {1000 + _number(*parts) % 9000}"


@lru_cache(maxsize=None)
def _generated(origin: str, destination: str) -> list:
    direct = _distance_km(origin, destination)
    base = 28 + direct * 0.075
    templates = []

    # One to three direct flights; small airports are not served every day.
    count = 1 + _number(origin, destination, "direct") % 3
    slots = sorted({_number(origin, destination, "slot", index) % len(_DEPARTURES) for index in range(count)})
    for index, slot in enumerate(slots):
        seed = _number(origin, destination, "direct", index)
        # The first direct flight runs daily, so every listed place is reachable every day.
        if index == 0 or origin in HUBS or destination in HUBS:
            days = frozenset(_ALL_DAYS)
        else:
            days = frozenset(day for day in _ALL_DAYS if (seed >> day) & 1) or frozenset({4, 6})
        price = round(base * (1.0 + (seed % 45) / 100), 2)
        templates.append((
            f"direct-{index + 1}", days, price,
            [(origin, destination, _DEPARTURES[slot], _flight_minutes(origin, destination),
              _flight_number(origin, destination, index))],
        ))

    # Connections with one change at the hubs with the smallest detour.
    hubs = sorted(
        (hub for hub in HUBS if hub not in (origin, destination)),
        key=lambda hub: _distance_km(origin, hub) + _distance_km(hub, destination),
    )
    for index, hub in enumerate(hubs[:3]):
        seed = _number(origin, hub, destination)
        detour = (_distance_km(origin, hub) + _distance_km(hub, destination)) / max(direct, 1)
        if detour > 2.2:
            continue
        first = _flight_minutes(origin, hub)
        # Most transfers are comfortable; about one in twelve is too tight.
        wait = 30 if seed % 12 == 0 else 55 + seed % 24 * 5
        departure = 345 + (seed >> 4) % 720  # between 05:45 and 17:45
        departure -= departure % 5
        templates.append((
            f"via-{hub}", frozenset(_ALL_DAYS), round(base * (0.62 + (seed % 30) / 100) + 9, 2),
            [
                (origin, hub, _clock(departure), first, _flight_number(origin, hub, "leg")),
                (hub, destination, wait, _flight_minutes(hub, destination),
                 _flight_number(hub, destination, "leg")),
            ],
        ))

    # On longer routes one very cheap connection with two changes.
    if direct > 1100 and len(hubs) >= 2:
        one, two = sorted(hubs[:2], key=lambda hub: _distance_km(origin, hub))
        seed = _number(origin, one, two, destination)
        departure = 330 + seed % 120
        departure -= departure % 5
        templates.append((
            f"via-{one}-{two}", frozenset(_ALL_DAYS), round(base * 0.48 + 6, 2),
            [
                (origin, one, _clock(departure), _flight_minutes(origin, one),
                 _flight_number(origin, one, "leg")),
                (one, two, 70 + seed % 12 * 5, _flight_minutes(one, two),
                 _flight_number(one, two, "leg")),
                (two, destination, 80 + (seed >> 3) % 18 * 5, _flight_minutes(two, destination),
                 _flight_number(two, destination, "leg")),
            ],
        ))
    return templates
