"""HTTP client for the Journey Planner (docs/SEARCH_CONTRACT.md)."""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_STATUSES = {"ok", "no_results", "error"}


class PlannerUnavailable(Exception):
    """The planner did not answer, or not in the agreed format."""


class PlannerClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None):
        self._base = (base_url or settings.JOURNEY_PLANNER_URL).rstrip("/")
        self._url = self._base + "/plan"
        self._timeout = timeout_seconds or settings.JOURNEY_PLANNER_TIMEOUT_SECONDS

    def places(self) -> list[dict]:
        """GET /places: the places the planner has flights for."""
        request = urllib.request.Request(
            self._base + "/places", headers={"Accept": "application/json"}, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                answer = json.loads(response.read())
        except (OSError, ValueError) as error:
            logger.warning("Journey Planner places unavailable: %s", type(error).__name__)
            raise PlannerUnavailable("Planner places could not be loaded.") from None
        places = answer.get("places") if isinstance(answer, dict) else None
        if not isinstance(places, list) or not all(
            isinstance(place, dict) and isinstance(place.get("name"), str) for place in places
        ):
            raise PlannerUnavailable("Planner places do not follow the contract.")
        return [
            {
                "name": place["name"],
                "country": place.get("country") or "",
                "aliases": [alias for alias in place.get("aliases", []) if isinstance(alias, str)],
            }
            for place in places
        ]

    def plan(self, search_request: dict) -> dict:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(search_request).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                answer = json.loads(response.read())
        except urllib.error.HTTPError as error:
            # 400 here means the agent built an invalid request: a bug, not user input.
            logger.error("Journey Planner rejected the search request with %s", error.code)
            raise PlannerUnavailable(f"Planner answered with {error.code}.") from None
        except (OSError, ValueError) as error:
            # URLError, timeouts and connection errors are OSErrors; bad JSON is a ValueError.
            logger.warning("Journey Planner unreachable: %s", type(error).__name__)
            raise PlannerUnavailable("Planner could not be reached.") from None
        if (
            not isinstance(answer, dict)
            or answer.get("status") not in _STATUSES
            or not isinstance(answer.get("journeys"), list)
        ):
            logger.error("Journey Planner sent an answer outside the contract")
            raise PlannerUnavailable("Planner answer does not follow the contract.")
        return answer
