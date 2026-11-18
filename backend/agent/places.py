"""The places the Journey Planner has flights for, and checks against them.

The list comes from the planner (GET /places) and is kept for a few minutes.
It is used in two places:

- GET /api/v1/places/ offers it to the form as suggestions.
- Before a place reaches the trip state, it is matched against the list:
  "lisbon" becomes "Lissabon"; a place without flight data is rejected with a
  reason the user is told, instead of ending in an empty search later.

If the planner cannot be reached, places are taken as they are.
"""

import logging
import time
import unicodedata

from agent.planner_client import PlannerUnavailable

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300
_cache: dict = {"at": 0.0, "places": None}

UNKNOWN_PLACE = (
    "There are no flights for this place yet. Flights exist between {count} European "
    "cities, for example {examples}."
)


def fold(text: str) -> str:
    """Lower case without accents: "Zürich" and "zurich" are the same."""
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def load(planner) -> list[dict] | None:
    """The place list, or None if the planner does not offer one or is down."""
    listing = getattr(planner, "places", None)
    if not callable(listing):
        return None
    if _cache["places"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["places"]
    try:
        places = listing()
    except PlannerUnavailable:
        return _cache["places"]
    _cache.update(at=time.monotonic(), places=places)
    return places


def clear_cache() -> None:
    _cache.update(at=0.0, places=None)


class Catalog:
    def __init__(self, places: list[dict]):
        self.places = places
        self._index = {}
        for place in places:
            for name in (place["name"], *place.get("aliases", [])):
                self._index.setdefault(fold(name), place["name"])

    def canonical(self, name: str) -> str | None:
        return self._index.get(fold(name))

    def check(self, changes: dict) -> dict[str, str]:
        """Replace origin/destination in `changes` by the canonical name.

        Unknown places are removed from `changes`; the result maps them to
        the reason.
        """
        rejected = {}
        for field in ("origin", "destination"):
            value = changes.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            canonical = self.canonical(value)
            if canonical is None:
                del changes[field]
                examples = ", ".join(place["name"] for place in self.places[:6])
                rejected[field] = UNKNOWN_PLACE.format(count=len(self.places), examples=examples)
            else:
                changes[field] = canonical
        return rejected


def catalog(planner) -> Catalog | None:
    places = load(planner)
    return Catalog(places) if places else None
