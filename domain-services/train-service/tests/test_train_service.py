"""Tests for the train service (DS2 #23).

Run from domain-services/train-service/:  python3 -m unittest
No network, no credentials, standard library only. Independent of every other service.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from unittest import mock

from train_service import TrainService, create_train_service
from train_service.adapters import mock_rail
from train_service.contract import (
    Availability,
    ErrorCode,
    Journey,
    JourneySearchRequest,
    Leg,
    PriceBasis,
    SearchStatus,
    Stop,
    TransportMode,
    TransportService,
)
from train_service.errors import InvalidProviderResponse

from domain_services.gateway import search_one  # the Journey Planner's generic caller (DS1)

LOGGER = "train_service.service"


def make_request(**overrides) -> JourneySearchRequest:
    return JourneySearchRequest.from_dict(
        {"origin_id": "berlin", "destination_id": "munich", "departure_after": "2026-12-15T06:00:00+01:00", **overrides}
    )


def search(request: JourneySearchRequest, service: TrainService | None = None):
    return asyncio.run((service or create_train_service()).search_journeys(request))


def cheapest(result) -> Decimal:
    return min(o.price.amount for j in result.journeys for o in j.offers if o.price is not None)


class DirectConnectionTests(unittest.TestCase):
    ROUTES = [
        ("berlin", "munich"),
        ("hamburg", "vienna"),
        ("paris", "amsterdam"),
        ("berlin", "bad-homburg"),  # unknown city: still served
        ("atlantis", "el-dorado"),  # two unknown cities
    ]

    def test_implements_ds1(self):
        service = create_train_service()
        self.assertIsInstance(service, TransportService)
        self.assertEqual(service.service_id, "train")

    def test_always_a_direct_connection_to_the_destination(self):
        for origin, destination in self.ROUTES:
            # Late evening: without departure_before the window is 24 h, so there is always a departure.
            request = make_request(origin_id=origin, destination_id=destination, departure_after="2026-12-15T22:30:00+01:00")
            with self.subTest(f"{origin}->{destination}"):
                result = search(request)
                self.assertIs(result.status, SearchStatus.SUCCESS)
                for journey in result.journeys:
                    self.assertEqual(journey.transfer_count, 0)
                    self.assertEqual(journey.modes, {TransportMode.TRAIN})
                    self.assertEqual(journey.provider_id, "mock-rail")
                    self.assertEqual((journey.origin.location_id, journey.destination.location_id), (origin, destination))
                    self.assertGreaterEqual(journey.departure_at, request.departure_after)
                    self.assertLessEqual(journey.departure_at, request.departure_after + timedelta(hours=24))
                    self.assertGreater(journey.arrival_at, journey.departure_at)
                    for offer in journey.offers:
                        self.assertEqual(offer.provider_id, "mock-rail")
                        self.assertEqual((offer.price.currency, offer.price.basis), ("EUR", PriceBasis.TRIP_TOTAL))

    def test_time_window_and_empty_result(self):
        two_days = make_request(departure_before="2026-12-16T23:59:00+01:00")
        self.assertEqual(len(search(two_days).journeys), 2 * len(mock_rail.CLOCK_TIMES))

        gap = make_request(departure_after="2026-12-15T23:00:00+01:00", departure_before="2026-12-15T23:30:00+01:00")
        result = search(gap)
        self.assertIs(result.status, SearchStatus.NO_RESULTS)
        self.assertTrue(result.is_complete)

    def test_ride_within_one_city_has_no_results(self):
        request = make_request(
            destination_id="berlin",
            origin_coordinates={"latitude": 52.52, "longitude": 13.40},
            destination_coordinates={"latitude": 52.37, "longitude": 13.50},
        )
        self.assertIs(search(request).status, SearchStatus.NO_RESULTS)

    def test_times_are_local_with_the_request_offset(self):
        request = make_request(departure_after="2026-07-01T05:00:00+02:00", departure_before="2026-07-01T23:00:00+02:00")
        journeys = search(request).journeys
        self.assertEqual([j.departure_at.strftime("%H:%M") for j in journeys], list(mock_rail.CLOCK_TIMES))
        self.assertTrue(all(j.departure_at.utcoffset() == timedelta(hours=2) for j in journeys))

    def test_deterministic_and_independent_of_the_window(self):
        narrow = search(make_request(departure_after="2026-12-15T12:00:00+01:00"))
        self.assertEqual(narrow.journeys, search(make_request(departure_after="2026-12-15T12:00:00+01:00")).journeys)
        wide = {j.id: j for j in search(make_request(departure_after="2026-12-15T00:00:00+01:00")).journeys}
        for journey in narrow.journeys:
            if journey.id in wide:
                self.assertEqual(journey, wide[journey.id])


class FareTests(unittest.TestCase):
    def test_fares_by_age(self):
        adult = cheapest(search(make_request(passengers=[{"age": 40}])))
        half = (adult * Decimal("1.5")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.assertEqual(cheapest(search(make_request(passengers=[{"age": 40}, {"age": None}]))), 2 * adult)
        self.assertEqual(cheapest(search(make_request(passengers=[{"age": 40}, {"age": 10}]))), half)
        self.assertEqual(cheapest(search(make_request(passengers=[{"age": 40}, {"age": 4}]))), adult)

    def test_sold_out_fares_are_marked(self):
        result = search(make_request(departure_before="2026-12-21T23:00:00+01:00"))
        self.assertEqual({o.availability for j in result.journeys for o in j.offers}, {Availability.AVAILABLE, Availability.SOLD_OUT})


class JourneyPlannerIntegrationTests(unittest.TestCase):
    def test_journey_planner_can_query_the_service(self):
        result = asyncio.run(search_one(create_train_service(), make_request()))
        self.assertIs(result.status, SearchStatus.SUCCESS)


class ProviderErrorTests(unittest.TestCase):
    def test_provider_failures_are_reported_with_code_and_provider(self):
        cases = {
            ErrorCode.TIMEOUT: True,
            ErrorCode.RATE_LIMITED: True,
            ErrorCode.PROVIDER_UNAVAILABLE: True,
            ErrorCode.AUTHENTICATION_FAILED: False,
            ErrorCode.INVALID_PROVIDER_RESPONSE: False,
        }
        for code, retryable in cases.items():
            with self.subTest(code.value), self.assertLogs(LOGGER, "WARNING"):
                result = search(make_request(), create_train_service(adapter_options={"mock-rail": {"failure": code}}))
            self.assertIs(result.status, SearchStatus.UNAVAILABLE)
            self.assertFalse(result.is_complete)  # never "no connection"
            error = result.errors[0]
            self.assertEqual((error.code, error.provider_id, error.is_retryable), (code, "mock-rail", retryable))

    def test_slow_provider_times_out(self):
        service = create_train_service(adapter_options={"mock-rail": {"delay_seconds": 1}}, adapter_timeout_seconds=0.01)
        with self.assertLogs(LOGGER, "WARNING"):
            result = search(make_request(), service)
        self.assertIs(result.errors[0].code, ErrorCode.TIMEOUT)

    def test_one_of_two_providers_failing_is_partial(self):
        class OtherRail(mock_rail.MockRailAdapter):
            provider_id = "other-rail"

        service = TrainService([mock_rail.MockRailAdapter(), OtherRail(failure=ErrorCode.RATE_LIMITED)])
        with self.assertLogs(LOGGER, "WARNING"):
            result = search(make_request(), service)
        self.assertIs(result.status, SearchStatus.PARTIAL)
        self.assertTrue(result.journeys)
        self.assertEqual(result.errors[0].provider_id, "other-rail")

    def test_adapters_breaking_the_rules_are_contained(self):
        def journey(mode: TransportMode, provider_id: str) -> Journey:
            t = datetime.fromisoformat("2026-12-15T08:00:00+01:00")
            leg = Leg(mode, Stop("berlin"), Stop("munich"), t, t + timedelta(hours=4))
            return Journey(id="j", provider_id=provider_id, legs=(leg,))

        class Raising:
            provider_id = "mock-rail"

            async def search(self, request):
                raise RuntimeError("bug")

        class WrongMode:
            provider_id = "mock-rail"

            async def search(self, request):
                return [journey(TransportMode.BUS, "mock-rail")]

        class WrongProvider:
            provider_id = "mock-rail"

            async def search(self, request):
                return [journey(TransportMode.TRAIN, "someone-else")]

        cases = [(Raising(), ErrorCode.INTERNAL_ERROR), (WrongMode(), ErrorCode.INVALID_PROVIDER_RESPONSE), (WrongProvider(), ErrorCode.INVALID_PROVIDER_RESPONSE)]
        for adapter, code in cases:
            with self.subTest(type(adapter).__name__), self.assertLogs(LOGGER, "WARNING"):
                result = search(make_request(), TrainService([adapter]))
            self.assertIs(result.status, SearchStatus.UNAVAILABLE)
            self.assertIs(result.errors[0].code, code)


class RailAdapterTests(unittest.TestCase):
    request = make_request(passengers=[{"age": 34}, {}])

    def raw(self, **fare):
        return {
            "connections": [
                {
                    "trainNumber": "ICE 501",
                    "from": "mr:berlin",
                    "to": "mr:munich",
                    "departureUtc": "2026-12-15T07:00:00Z",
                    "arrivalUtc": "2026-12-15T11:04:00Z",
                    "fares": [{"product": "SUPERSPAR", "currency": "EUR", **fare}],
                }
            ]
        }

    def test_query_uses_provider_codes(self):
        query = mock_rail.build_query(self.request)
        self.assertEqual((query["fromStation"], query["toStation"]), ("mr:berlin", "mr:munich"))
        self.assertEqual(query["travellers"], [{"age": 34}, {"age": None}])

    def test_normalizes_times_prices_and_names(self):
        journey = mock_rail.parse_response(self.raw(totalCents=5998, binding=True, bookable=True), self.request)[0]
        leg, offer = journey.legs[0], journey.offers[0]
        self.assertEqual(leg.departure_at.isoformat(), "2026-12-15T08:00:00+01:00")
        self.assertEqual((leg.origin.name, leg.destination.name), ("Berlin Hbf", "München Hbf"))
        self.assertEqual(offer.price.amount, Decimal("59.98"))
        self.assertEqual((offer.fare_name, offer.availability, offer.is_price_estimate), ("Superspar", Availability.AVAILABLE, False))

    def test_missing_values_stay_unknown(self):
        offer = mock_rail.parse_response(self.raw(totalCents=None), self.request)[0].offers[0]
        self.assertIsNone(offer.price)
        self.assertIs(offer.availability, Availability.UNKNOWN)
        self.assertTrue(offer.is_price_estimate)  # not confirmed as binding

    def test_malformed_answers_raise(self):
        for raw in [{}, {"connections": [{}]}, {"connections": None}, self.raw(totalCents="x"), self.raw(totalCents=-1)]:
            with self.subTest(raw=str(raw)[:40]), self.assertRaises(InvalidProviderResponse):
                mock_rail.parse_response(raw, self.request)


class ConfigurationTests(unittest.TestCase):
    def test_providers_from_argument_env_or_default(self):
        self.assertEqual(create_train_service().provider_ids, ("mock-rail",))
        with mock.patch.dict(os.environ, {"TRAIN_SERVICE_PROVIDERS": " mock-rail , "}):
            self.assertEqual(create_train_service().provider_ids, ("mock-rail",))

    def test_invalid_configuration_fails_at_start(self):
        with self.assertRaises(ValueError):
            create_train_service(["real-rail"])
        with mock.patch.dict(os.environ, {"TRAIN_SERVICE_PROVIDERS": "mock-air"}), self.assertRaises(ValueError):
            create_train_service()
        with self.assertRaises(ValueError):
            create_train_service(["mock-rail", "mock-rail"])
        with self.assertRaises(ValueError):
            TrainService([])


if __name__ == "__main__":
    unittest.main()
