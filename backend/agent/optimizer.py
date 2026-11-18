"""Optimization Agent: looks over the planner's results and improves the search.

It does two things:

1. `review` checks every connection with plain code (are the times plausible,
   is there enough time to change) and marks the cheapest, the fastest and a
   recommendation. An LLM cannot verify data it has no second source for, so
   this part is deterministic.
2. `find_alternative` runs when a search found nothing. The LLM chooses which
   relaxation of the search fits best; the code allows only a fixed set of
   relaxations, never touches the budget and limits the number of new searches.
"""

import datetime
import logging

from agent import prompts
from agent.planner_client import PlannerUnavailable
from agent.texts import duration
from llm import LLMError, Message

logger = logging.getLogger(__name__)

MIN_TRANSFER_MINUTES = 45
LONG_TRANSFER_MINUTES = 5 * 60
FLEXIBLE_DAYS = 3
MAX_EXTRA_SEARCHES = 2
# One hour of travel time is weighed like this many units of the price.
VALUE_OF_AN_HOUR = 15

STRATEGIES = {
    "budget": ["flexible_dates", "more_stops"],
    "max_stops": ["more_stops", "flexible_dates"],
    "no_connection": ["flexible_dates"],
}


def review(journeys: list[dict]) -> dict:
    """Return {journey id: {"tags": [...], "warnings": [...]}} for all journeys."""
    notes = {journey["id"]: {"tags": [], "warnings": _all_warnings(journey)} for journey in journeys}
    priced = [journey for journey in journeys if _price(journey) is not None]
    if len(journeys) > 1:
        if priced:
            cheapest = min(priced, key=lambda j: (_price(j), _minutes(j)))
            notes[cheapest["id"]]["tags"].append("cheapest")
        fastest = min(journeys, key=_minutes)
        notes[fastest["id"]]["tags"].append("fastest")
    sound = [journey for journey in priced if not notes[journey["id"]]["warnings"]]
    if sound:
        best = min(sound, key=lambda j: _price(j) + _minutes(j) / 60 * VALUE_OF_AN_HOUR)
        notes[best["id"]]["tags"].append("recommended")
    return notes


def _price(journey: dict) -> float | None:
    """Price of the whole trip: both flights for a round trip."""
    price = journey.get("total_price") or journey["price"]
    return price["amount"] if price else None


def _minutes(journey: dict) -> int:
    inbound = journey.get("inbound")
    return journey["duration_minutes"] + (inbound["duration_minutes"] if inbound else 0)


def _all_warnings(journey: dict) -> list[str]:
    warnings = _warnings(journey)
    if journey.get("inbound"):
        warnings += [f"Rückflug: {warning}" for warning in _warnings(journey["inbound"])]
    return warnings


def _warnings(journey: dict) -> list[str]:
    warnings = []
    legs = journey["legs"]
    for leg in legs:
        if _time(leg["arrival"]) <= _time(leg["departure"]):
            warnings.append(
                f"Die Zeiten von {leg['origin']} nach {leg['destination']} sind nicht plausibel."
            )
    for arriving, leaving in zip(legs, legs[1:]):
        wait = round((_time(leaving["departure"]) - _time(arriving["arrival"])).total_seconds() / 60)
        place = arriving["destination"]
        if wait < 0:
            warnings.append(f"Der Anschluss in {place} startet vor der Ankunft.")
        elif wait < MIN_TRANSFER_MINUTES:
            warnings.append(f"Nur {wait} Minuten zum Umsteigen in {place}.")
        elif wait > LONG_TRANSFER_MINUTES:
            warnings.append(f"Lange Wartezeit in {place}: {duration(wait)}.")
    if journey["price"] is None:
        warnings.append("Für diese Verbindung ist kein Preis bekannt.")
    return warnings


def _time(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(iso)


def find_alternative(search_request: dict, details: dict, *, llm, planner, today) -> dict | None:
    """Search again with one relaxed criterion; None if that finds nothing either."""
    options = [
        name
        for name in STRATEGIES.get(details["reason"], [])
        if _relax(search_request, name, today) is not None
    ]
    if not options:
        return None
    first = _choose(options, search_request, details, llm)
    ordered = [first] + [name for name in options if name != first]
    for strategy in ordered[:MAX_EXTRA_SEARCHES]:
        relaxed = _relax(search_request, strategy, today)
        try:
            answer = planner.plan(relaxed)
        except PlannerUnavailable:
            return None
        if answer["status"] == "ok":
            return {
                "strategy": strategy,
                "description": _describe(strategy, relaxed),
                "request": relaxed,
                "journeys": answer["journeys"],
                "review": review(answer["journeys"]),
            }
    return None


def _choose(options: list[str], search_request: dict, details: dict, llm) -> str:
    if len(options) == 1:
        return options[0]
    try:
        answer = llm.structured(
            [
                Message(
                    "user",
                    prompts.strategy_instruction(
                        request=search_request,
                        reason=details["reason"],
                        closest=details["closest_journey"],
                    ),
                )
            ],
            schema=prompts.strategy_schema(options),
            system=prompts.OPTIMIZER_SYSTEM,
        )
    except LLMError:
        # The optimisation is an extra: without the LLM the fixed order applies.
        return options[0]
    return answer["strategy"] if answer.get("strategy") in options else options[0]


def _relax(search_request: dict, strategy: str, today: datetime.date) -> dict | None:
    """The changed search request, or None if the strategy changes nothing."""
    if strategy == "more_stops":
        if search_request["max_stops"] is None:
            return None
        return {**search_request, "max_stops": search_request["max_stops"] + 1}
    if strategy == "flexible_dates":
        days = datetime.timedelta(days=FLEXIBLE_DAYS)
        earliest = datetime.date.fromisoformat(search_request["departure"]["earliest"])
        latest = datetime.date.fromisoformat(search_request["departure"]["latest"])
        departure = {
            "earliest": max(earliest - days, today).isoformat(),
            "latest": (latest + days).isoformat(),
        }
        relaxed = {**search_request, "departure": departure}
        back = search_request.get("return")
        if back:
            first = datetime.date.fromisoformat(back["earliest"]) - days
            last = datetime.date.fromisoformat(back["latest"]) + days
            # The return window never starts before the earliest departure.
            first = max(first, datetime.date.fromisoformat(departure["earliest"]))
            relaxed["return"] = {"earliest": first.isoformat(), "latest": last.isoformat()}
        return relaxed
    return None


def _describe(strategy: str, relaxed: dict) -> str:
    if strategy == "more_stops":
        word = "Umstieg" if relaxed["max_stops"] == 1 else "Umstiegen"
        return f"Mit bis zu {relaxed['max_stops']} {word} habe ich aber etwas gefunden:"
    start = datetime.date.fromisoformat(relaxed["departure"]["earliest"]).strftime("%d.%m.%Y")
    end = datetime.date.fromisoformat(relaxed["departure"]["latest"]).strftime("%d.%m.%Y")
    text = f"Wenn du beim Datum flexibel bist, habe ich für den Abflug zwischen {start} und {end}"
    if relaxed.get("return"):
        back_start = datetime.date.fromisoformat(relaxed["return"]["earliest"]).strftime("%d.%m.%Y")
        back_end = datetime.date.fromisoformat(relaxed["return"]["latest"]).strftime("%d.%m.%Y")
        text += f" und den Rückflug zwischen {back_start} und {back_end}"
    return text + " aber etwas gefunden:"
