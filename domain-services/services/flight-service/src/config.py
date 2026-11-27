"""Configuration from environment variables (in Docker e.g. via --env-file ../../../.env).

Only TRAVELPAYOUTS_API_TOKEN is required. Every other variable has a default;
an empty value counts as not set.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from flight_request.search import SearchSettings

T = TypeVar("T")


def _env(name: str, default: T, parse: Callable[[str], T]) -> T:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return parse(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} has an invalid value: {value!r}.") from exc


@dataclass(frozen=True)
class Settings:
    travelpayouts_token: str
    travelpayouts_currency: str
    travelpayouts_marker: str | None
    search: SearchSettings

    @classmethod
    def from_env(cls) -> Settings:
        token = _env("TRAVELPAYOUTS_API_TOKEN", "", str)
        if not token:
            raise RuntimeError("TRAVELPAYOUTS_API_TOKEN is not set.")
        defaults = SearchSettings()
        return cls(
            travelpayouts_token=token,
            travelpayouts_currency=_env("TRAVELPAYOUTS_CURRENCY", "EUR", str),
            travelpayouts_marker=_env("TRAVELPAYOUTS_MARKER", None, str),
            search=SearchSettings(
                radius_km=_env("FLIGHT_SEARCH_RADIUS_KM", defaults.radius_km, float),
                radius_step_km=_env("FLIGHT_SEARCH_RADIUS_STEP_KM", defaults.radius_step_km, float),
                max_airports=_env("FLIGHT_MAX_AIRPORTS", defaults.max_airports, int),
            ),
        )
