"""Travelpayouts / Aviasales Data API (``prices_for_dates``) as flight provider.

    GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates
    header X-Access-Token: <TRAVELPAYOUTS_API_TOKEN>

* One query per airport pair and departure month (``departure_at=YYYY-MM``),
  filtered to the search window afterwards. Daily queries are often empty
  because the API only knows prices other users searched recently.
* Only direct flights (``direct=true``): for flights with transfers the API
  names neither the transfer airport nor the times, so no legs can be built.
* Prices are cached prices per person: ``is_price_estimate: true``,
  ``availability: unknown``, ``basis: per_person``.
* The arrival is departure + ``duration_to``, in the destination's time zone.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from adapters.base import (
    InvalidProviderResponse,
    ProviderAuthenticationFailed,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from airport_finder import Airport
from flight_request import contract_json
from flight_request.request import SearchRequest

logger = logging.getLogger(__name__)

PROVIDER_ID = "travelpayouts"
API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
BOOKING_BASE_URL = "https://www.aviasales.com"
RESULT_LIMIT = 1000

AIRLINE_NAMES = {
    "LH": "Lufthansa", "EW": "Eurowings", "DE": "Condor", "FR": "Ryanair", "U2": "easyJet",
    "EC": "easyJet Europe", "W6": "Wizz Air", "AF": "Air France", "KL": "KLM", "LX": "SWISS",
    "OS": "Austrian", "BA": "British Airways", "IB": "Iberia", "VY": "Vueling", "AZ": "ITA Airways",
    "TP": "TAP Air Portugal", "SK": "SAS", "TK": "Turkish Airlines", "LO": "LOT", "SN": "Brussels Airlines",
}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


#: (url, params, headers, timeout_seconds) -> HttpResponse; replaced in tests.
Transport = Callable[[str, Mapping[str, str], Mapping[str, str], float], Awaitable[HttpResponse]]


async def urllib_transport(url: str, params: Mapping[str, str], headers: Mapping[str, str], timeout: float) -> HttpResponse:
    return await asyncio.to_thread(_get, url, params, headers, timeout)


def _get(url: str, params: Mapping[str, str], headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = Request(f"{url}?{urlencode(params)}", headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
            return HttpResponse(response.status, response.read(), dict(response.headers))
    except HTTPError as exc:
        return HttpResponse(exc.code, exc.read() or b"", dict(exc.headers or {}))
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderTimeout("Travelpayouts did not answer in time.") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError | socket.timeout):
            raise ProviderTimeout("Travelpayouts did not answer in time.") from exc
        raise ProviderUnavailable("Travelpayouts is not reachable.") from exc


class TravelpayoutsAdapter:
    provider_id = PROVIDER_ID

    def __init__(
        self,
        token: str,
        *,
        currency: str = "EUR",
        marker: str | None = None,
        transport: Transport | None = None,
        timeout_seconds: float = 6.0,
    ):
        if not token:
            raise ValueError("Travelpayouts needs an API token (TRAVELPAYOUTS_API_TOKEN).")
        self._token = token
        self._currency = currency.upper()
        self._marker = marker
        self._transport = transport or urllib_transport
        self._timeout = timeout_seconds

    def __repr__(self) -> str:  # never show the token
        return f"TravelpayoutsAdapter(currency={self._currency!r})"

    async def search(self, origin: Airport, destination: Airport, request: SearchRequest) -> list[dict[str, Any]]:
        months = departure_months(request, origin)
        answers = await asyncio.gather(*(self._fetch(origin.iata, destination.iata, month) for month in months))
        return parse_answers(answers, origin, destination, request, currency=self._currency, marker=self._marker)

    async def _fetch(self, origin: str, destination: str, month: str) -> Any:
        params = {
            "origin": origin,
            "destination": destination,
            "departure_at": month,
            "one_way": "true",
            "direct": "true",
            "unique": "false",
            "sorting": "price",
            "currency": self._currency.lower(),
            "limit": str(RESULT_LIMIT),
        }
        headers = {"X-Access-Token": self._token, "Accept": "application/json", "Accept-Encoding": "identity"}
        response = await self._transport(API_URL, params, headers, self._timeout)
        status = response.status
        if status in (401, 403):
            raise ProviderAuthenticationFailed("Travelpayouts rejected the API token.")
        if status == 429:
            raise ProviderRateLimited("Travelpayouts rate limit reached.")
        if status >= 500:
            raise ProviderUnavailable(f"Travelpayouts answered HTTP {status}.")
        if status != 200:
            raise InvalidProviderResponse(f"Travelpayouts answered HTTP {status}.")
        try:
            data = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidProviderResponse("Travelpayouts answered with invalid JSON.") from exc
        if not isinstance(data, dict) or data.get("success") is not True or not isinstance(data.get("data"), list):
            raise InvalidProviderResponse("Travelpayouts reported an unsuccessful request.")
        return data


def departure_months(request: SearchRequest, origin: Airport) -> list[str]:
    """Months (YYYY-MM, local time at the origin airport) touched by the search window."""
    tz = ZoneInfo(origin.time_zone)
    first = request.departure_after.astimezone(tz).date().replace(day=1)
    last = request.latest_departure.astimezone(tz).date().replace(day=1)
    months, current = [], first
    while current <= last and len(months) < 12:
        months.append(f"{current:%Y-%m}")
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def parse_answers(
    answers: list[Any],
    origin: Airport,
    destination: Airport,
    request: SearchRequest,
    *,
    currency: str,
    marker: str | None,
) -> list[dict[str, Any]]:
    journeys: dict[str, tuple[Decimal | None, dict[str, Any]]] = {}
    try:
        for answer in answers:
            answer_currency = str(answer.get("currency") or currency).upper()
            for ticket in answer["data"]:
                parsed = _ticket(ticket, origin, destination, request, answer_currency, marker)
                if parsed is None:
                    continue
                price, journey = parsed
                known = journeys.get(journey["id"])
                if known is None or (price is not None and (known[0] is None or price < known[0])):
                    journeys[journey["id"]] = (price, journey)  # same flight listed twice: keep the cheaper one
    except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as exc:
        raise InvalidProviderResponse(f"Malformed Travelpayouts answer: {type(exc).__name__}.") from exc
    return [journey for _, journey in journeys.values()]


def _ticket(
    ticket: dict[str, Any],
    origin: Airport,
    destination: Airport,
    request: SearchRequest,
    currency: str,
    marker: str | None,
) -> tuple[Decimal | None, dict[str, Any]] | None:
    if int(ticket.get("transfers") or 0) != 0:
        return None
    if ticket.get("origin_airport", origin.iata) != origin.iata or ticket.get("destination_airport", destination.iata) != destination.iata:
        return None
    departure = datetime.fromisoformat(ticket["departure_at"])
    if departure.utcoffset() is None:
        raise ValueError("departure_at without offset")
    if not request.departure_after <= departure <= request.latest_departure:
        return None
    minutes = int(ticket.get("duration_to") or ticket["duration"])
    if minutes <= 0:
        raise ValueError("non-positive duration")
    arrival = (departure + timedelta(minutes=minutes)).astimezone(ZoneInfo(destination.time_zone))

    airline = str(ticket["airline"]).strip().upper()
    number = str(ticket["flight_number"]).strip()
    journey_id = f"{PROVIDER_ID}-{airline}{number}-{departure:%Y%m%dT%H%M}".lower()
    price = _price(ticket.get("price"))

    leg = contract_json.flight_leg(
        _stop(request.origin_id, origin),
        _stop(request.destination_id, destination),
        departure,
        arrival,
        operator=AIRLINE_NAMES.get(airline, airline),
        service_number=f"{airline} {number}",
    )
    offer = contract_json.offer(
        f"{journey_id}-0",
        PROVIDER_ID,
        price=contract_json.money(price, currency, "per_person") if price is not None else None,
        is_price_estimate=True,
        booking_url=_booking_url(ticket.get("link"), marker),
    )
    return price, contract_json.journey(journey_id, PROVIDER_ID, [leg], [offer])


def _stop(location_id: str, airport: Airport) -> dict[str, Any]:
    return contract_json.stop(location_id, name=airport.name, code=airport.iata, latitude=airport.latitude, longitude=airport.longitude)


def _price(raw: Any) -> Decimal | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        amount = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("price is not a number") from exc
    return amount if amount > 0 else None  # unknown price is null, never 0


def _booking_url(link: Any, marker: str | None) -> str | None:
    if not isinstance(link, str) or not link.startswith("/"):
        return None
    url = BOOKING_BASE_URL + link
    if marker:
        url += ("&" if "?" in url else "?") + urlencode({"marker": marker})
    return url


__all__ = ["HttpResponse", "TravelpayoutsAdapter", "Transport"]
