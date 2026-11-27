"""Tests for the generic caller (``search_one`` / ``search_all``) with the DS1 mock services.

Run from journey-planner/:  python3 -m unittest
No network, no credentials, standard library only.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path

from journey_planner import (
    ErrorCode,
    JourneySearchRequest,
    JourneySearchResult,
    PriceBasis,
    SearchStatus,
    TransportMode,
    TransportService,
    search_all,
    search_one,
)
from journey_planner.mocks import mock_flight_service, mock_taxi_service, mock_train_service

EXAMPLES = Path(__file__).resolve().parents[2] / "domain-services" / "contract" / "examples"


def load_example(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def make_request(**overrides) -> JourneySearchRequest:
    data = {
        "origin_id": "berlin",
        "destination_id": "munich",
        "departure_after": "2026-12-15T06:00:00+01:00",
        **overrides,
    }
    return JourneySearchRequest.from_dict(data)


# --------------------------------------------------------------------------- #
# Mocks + generic caller: the DS1 Definition of Done
# --------------------------------------------------------------------------- #


class RaisingService:
    service_id = "bus"

    async def search_journeys(self, request):
        raise RuntimeError("bug")


class WrongAnswerService:
    def __init__(self, answer):
        self.service_id = "bus"
        self.answer = answer

    async def search_journeys(self, request):
        return self.answer


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_mocks_implement_the_protocol(self):
        for service in (mock_flight_service(), mock_train_service(), mock_taxi_service()):
            self.assertIsInstance(service, TransportService)

    async def test_one_generic_caller_uses_all_services(self):
        """Same code path for flight, train and taxi; no service-specific logic."""
        request = make_request(passengers=[{}, {}])
        results = await search_all([mock_flight_service(), mock_train_service(), mock_taxi_service()], request)

        self.assertEqual([r.service_id for r in results], ["flight", "train", "taxi"])
        # Berlin -> Munich is too far for the taxi mock: a complete search without results.
        self.assertEqual([r.status for r in results], [SearchStatus.SUCCESS, SearchStatus.SUCCESS, SearchStatus.NO_RESULTS])
        for result in results:
            with self.subTest(result.service_id):
                self.assertTrue(result.is_complete)
                for journey in result.journeys:
                    self.assertEqual(journey.origin.location_id, "berlin")
                    self.assertEqual(journey.destination.location_id, "munich")
                    self.assertGreaterEqual(journey.departure_at, request.departure_after)
                    for offer in journey.offers or ():
                        self.assertEqual(offer.provider_id, journey.provider_id)
                        if offer.price is not None:
                            self.assertIs(offer.price.basis, PriceBasis.TRIP_TOTAL)
        self.assertEqual({TransportMode.FLIGHT, TransportMode.TRAIN}, {m for r in results for j in r.journeys for m in j.modes})

    async def test_mock_data_covers_contract_edge_cases(self):
        flights = await search_one(mock_flight_service(), make_request())
        trains = await search_one(mock_train_service(), make_request(destination_id="paris"))
        timetable_only = await search_one(mock_train_service(), make_request(departure_after="2026-12-15T13:00:00+01:00"))

        self.assertTrue(any(o.price is None for j in flights.journeys for o in j.offers or ()))
        self.assertEqual(trains.journeys[0].transfer_count, 1)
        self.assertEqual(trains.journeys[0].offers, ())
        self.assertIsNone(timetable_only.journeys[0].offers)

    async def test_ages_change_age_based_fares(self):
        async def cheapest_train_fare(passengers):
            result = await search_one(mock_train_service(), make_request(passengers=passengers))
            return result.journeys[0].cheapest_known_price().amount

        self.assertEqual(await cheapest_train_fare([{"age": 40}]), Decimal("29.99"))
        self.assertEqual(await cheapest_train_fare([{"age": 40}, {"age": None}]), Decimal("59.98"))  # unknown = adult
        self.assertEqual(await cheapest_train_fare([{"age": 40}, {"age": 8}]), Decimal("44.99"))  # child half
        self.assertEqual(await cheapest_train_fare([{"age": 40}, {"age": 3}]), Decimal("29.99"))  # infant free

    async def test_taxi_ride_door_to_door(self):
        result = await search_one(mock_taxi_service(), JourneySearchRequest.from_dict(load_example("request-taxi.json")))
        self.assertIs(result.status, SearchStatus.SUCCESS)
        self.assertEqual({j.provider_id for j in result.journeys}, {"mock-taxi", "mock-ride"})
        for journey in result.journeys:
            leg = journey.legs[0]
            self.assertIs(leg.mode, TransportMode.TAXI)
            self.assertTrue(leg.is_on_demand)
            self.assertIsNotNone(leg.origin.coordinates)
            self.assertTrue(all(offer.is_price_estimate for offer in journey.offers))
        ride = next(j for j in result.journeys if j.provider_id == "mock-ride")
        self.assertTrue(all(o.price_upper is not None for o in ride.offers))

    async def test_taxi_offers_depend_on_group_size(self):
        async def fares(count):
            result = await search_one(mock_taxi_service(), make_request(destination_id="potsdam", passengers=[{}] * count))
            return {o.fare_name for j in result.journeys for o in j.offers}

        self.assertEqual(await fares(2), {"Taxi", "Großraumtaxi", "Standard", "XL"})
        self.assertEqual(await fares(6), {"Großraumtaxi", "XL"})
        self.assertEqual(await fares(9), set())  # known: no vehicle fits -> offers []

    async def test_taxi_outside_known_area_has_no_results(self):
        result = await search_one(mock_taxi_service(), make_request(destination_id="atlantis"))
        self.assertIs(result.status, SearchStatus.NO_RESULTS)

    async def test_unknown_route_is_a_successful_search_without_results(self):
        result = await search_one(mock_flight_service(), make_request(destination_id="atlantis"))
        self.assertIs(result.status, SearchStatus.NO_RESULTS)
        self.assertTrue(result.is_complete)

    async def test_time_window_is_respected(self):
        result = await search_one(
            mock_flight_service(),
            make_request(departure_after="2026-12-15T07:00:00+01:00", departure_before="2026-12-15T13:00:00+01:00"),
        )
        self.assertEqual([j.legs[0].service_number for j in result.journeys], ["MA 100", "MC 7"])

    async def test_provider_outage_is_partial_not_no_results(self):
        result = await search_one(mock_flight_service(unavailable_providers=["mock-airline"]), make_request(destination_id="paris"))
        self.assertIs(result.status, SearchStatus.PARTIAL)
        self.assertEqual(result.journeys, ())
        self.assertFalse(result.is_complete)
        self.assertEqual(result.errors[0].provider_id, "mock-airline")

    async def test_all_providers_down_is_unavailable(self):
        result = await search_one(mock_train_service(unavailable_providers=["mock-rail"]), make_request())
        self.assertIs(result.status, SearchStatus.UNAVAILABLE)
        self.assertTrue(result.is_retryable)

    async def test_timeout_becomes_unavailable(self):
        result = await search_one(mock_train_service(delay_seconds=1), make_request(), timeout_seconds=0.01)
        self.assertIs(result.status, SearchStatus.UNAVAILABLE)
        self.assertIs(result.errors[0].code, ErrorCode.TIMEOUT)

    async def test_contract_breaking_services_become_unavailable(self):
        services = [
            RaisingService(),
            WrongAnswerService({"status": "success"}),
            WrongAnswerService(JourneySearchResult.from_journeys("flight", [])),  # wrong service_id
        ]
        for service in services:
            with self.subTest(type(service).__name__), self.assertLogs("journey_planner.gateway", "ERROR"):
                result = await search_one(service, make_request())
            self.assertIs(result.status, SearchStatus.UNAVAILABLE)
            self.assertIs(result.errors[0].code, ErrorCode.INTERNAL_ERROR)
            self.assertFalse(result.is_retryable)

    async def test_one_failing_service_does_not_affect_the_other(self):
        with self.assertLogs("journey_planner.gateway", "ERROR"):
            results = await search_all(
                [RaisingService(), mock_flight_service(), mock_train_service(delay_seconds=1)],
                make_request(),
                timeout_seconds=0.2,
            )
        self.assertEqual([r.status for r in results], [SearchStatus.UNAVAILABLE, SearchStatus.SUCCESS, SearchStatus.UNAVAILABLE])

    async def test_results_are_deterministic(self):
        first = await search_one(mock_flight_service(), make_request())
        second = await search_one(mock_flight_service(), make_request())
        self.assertEqual(first.journeys, second.journeys)


if __name__ == "__main__":
    unittest.main()
