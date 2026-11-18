"""Planning: query providers, filter by the hard criteria, rank. No LLM.

A one-way search returns single flights. A round-trip search (the request has
a `return` window) returns pairs: an outbound flight with a matching return
flight. The budget then applies to both flights together.
"""

import datetime
import logging

from planner.providers.base import ProviderError

logger = logging.getLogger(__name__)

MAX_JOURNEYS = 5
# The same flight appears in at most this many of the returned round trips,
# so that the list does not show one outbound flight with five return flights.
MAX_REUSE = 2


def plan(request: dict, providers: list) -> dict:
    """Answer a validated search request in the format of docs/SEARCH_CONTRACT.md."""
    outbound, failed = _search(request, providers)
    if not outbound:
        return _nothing(failed, "no_connection", "outbound" if request["return"] else None)

    max_stops = request["max_stops"]
    out_ok = [j for j in outbound if max_stops is None or j["stops"] <= max_stops]

    if request["return"] is None:
        if not out_ok:
            closest = min(outbound, key=lambda j: (j["stops"], *_rank(j)))
            return _no_results("max_stops", None, _one_way(closest))
        options = [_one_way(journey) for journey in out_ok]
    else:
        way_back = {
            **request,
            "origin": request["destination"],
            "destination": request["origin"],
            "departure": request["return"],
            # For the provider this is a plain one-way search in the other direction.
            "return": None,
        }
        inbound, inbound_failed = _search(way_back, providers)
        failed = failed or inbound_failed
        if not inbound:
            return _nothing(failed, "no_connection", "inbound")
        in_ok = [j for j in inbound if max_stops is None or j["stops"] <= max_stops]
        if not out_ok or not in_ok:
            # Show the pair with the fewest stops as the closest option.
            pairs = _pairs(out_ok or outbound, in_ok or inbound)
            closest = min(pairs, key=lambda j: (j["stops"] + j["inbound"]["stops"], *_rank(j)), default=None)
            return _no_results("max_stops", "inbound" if out_ok else "outbound", closest)
        options = _pairs(out_ok, in_ok)
        if not options:
            # Flights exist in both directions, but no return leaves after an arrival.
            return _no_results("no_connection", "inbound", None)

    affordable = [option for option in options if _within_budget(option, request)]
    if not affordable:
        return _no_results("budget", None, min(options, key=_rank))
    return _response("ok", journeys=_pick(sorted(affordable, key=_rank)))


def _search(request: dict, providers: list) -> tuple[list[dict], bool]:
    """All flights of the providers inside the departure window, and whether one failed."""
    found, failed = [], False
    for provider in providers:
        if provider.mode not in request["modes"]:
            continue
        try:
            found.extend(_complete(journey) for journey in provider.search(request))
        except ProviderError as error:
            failed = True
            logger.warning("Provider %s failed: %s", provider.name, type(error).__name__)
    earliest, latest = request["departure"]["earliest"], request["departure"]["latest"]
    return [j for j in found if earliest <= _start(j).date() <= latest], failed


def _nothing(failed: bool, reason: str, direction: str | None) -> dict:
    # A failed provider must never look like "nothing found".
    if failed:
        return _response(
            "error",
            error={
                "code": "provider_unavailable",
                "message": "A transport service could not be reached.",
            },
        )
    return _no_results(reason, direction, None)


def _no_results(reason: str, direction: str | None, closest: dict | None) -> dict:
    return _response(
        "no_results",
        no_results={"reason": reason, "direction": direction, "closest_journey": closest},
    )


def _response(status, *, journeys=(), no_results=None, error=None) -> dict:
    return {"status": status, "journeys": list(journeys), "no_results": no_results, "error": error}


def _complete(journey: dict) -> dict:
    """Add the fields derived from legs and offers."""
    legs = journey["legs"]
    start = datetime.datetime.fromisoformat(legs[0]["departure"])
    end = datetime.datetime.fromisoformat(legs[-1]["arrival"])
    prices = [offer["price"] for offer in journey["offers"] if offer.get("price")]
    return {
        **journey,
        "duration_minutes": round((end - start).total_seconds() / 60),
        "stops": len(legs) - 1,
        "price": min(prices, key=lambda price: price["amount"]) if prices else None,
    }


def _one_way(journey: dict) -> dict:
    return {**journey, "inbound": None, "total_price": journey["price"]}


def _pairs(outbound: list[dict], inbound: list[dict]) -> list[dict]:
    """Every outbound flight with every return flight that leaves after it has landed."""
    pairs = []
    for out in outbound:
        landed = _end(out)
        for back in inbound:
            if _start(back) > landed:
                pairs.append({
                    **out,
                    "id": f"{out['id']}+{back['id']}",
                    "inbound": back,
                    "total_price": _sum(out["price"], back["price"]),
                })
    return pairs


def _sum(first: dict | None, second: dict | None) -> dict | None:
    """Price of both flights; unknown if one is unknown or they cannot be added."""
    if not first or not second:
        return None
    if (first["currency"], first["basis"]) != (second["currency"], second["basis"]):
        return None
    return {**first, "amount": round(first["amount"] + second["amount"], 2)}


def _pick(ranked: list[dict]) -> list[dict]:
    """The best options; for round trips no flight is repeated too often."""
    picked, used = [], {}
    for option in ranked:
        parts = [option["id"].split("+")[0]]
        if option["inbound"]:
            parts.append(option["inbound"]["id"])
        if any(used.get(part, 0) >= MAX_REUSE for part in parts):
            continue
        for part in parts:
            used[part] = used.get(part, 0) + 1
        picked.append(option)
        if len(picked) == MAX_JOURNEYS:
            break
    return picked


def _start(journey: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(journey["legs"][0]["departure"])


def _end(journey: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(journey["legs"][-1]["arrival"])


def _minutes(option: dict) -> int:
    inbound = option.get("inbound")
    return option["duration_minutes"] + (inbound["duration_minutes"] if inbound else 0)


def _rank(option: dict) -> tuple:
    """Cheapest first, then shortest; the ID makes the order deterministic."""
    total = option.get("total_price", option["price"])
    price = total["amount"] if total else float("inf")
    return (price, _minutes(option), option["id"])


def _within_budget(option: dict, request: dict) -> bool:
    limit = request["max_price"]
    if limit is None:
        return True
    price = option["total_price"]
    # Without a price, or in another currency, the limit cannot be checked.
    if price is None or price["currency"] != limit["currency"]:
        return False
    amount = price["amount"]
    if price["basis"] != limit["basis"]:
        travelers = request["travelers"]
        amount = amount * travelers if limit["basis"] == "trip_total" else amount / travelers
    return amount <= limit["amount"]
