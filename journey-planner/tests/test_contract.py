"""Tests for the Journey Planner's implementation of the DS1 contract (openapi.yaml):
models, status rules, example files, OpenAPI schema and HTTP binding.

Run from journey-planner/:  python3 -m unittest
No network, no credentials, standard library only.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from journey_planner import (
    Availability,
    ContractValidationError,
    Coordinates,
    ErrorCode,
    Journey,
    JourneySearchRequest,
    JourneySearchResult,
    Leg,
    Money,
    Offer,
    Passenger,
    PriceBasis,
    SearchStatus,
    ServiceError,
    Stop,
    TransportMode,
    TransportService,
)
from journey_planner.http_binding import result_from_http, result_to_http
from journey_planner.mocks import mock_flight_service, mock_taxi_service, mock_train_service

CONTRACT = Path(__file__).resolve().parents[2] / "domain-services" / "contract"
EXAMPLES = CONTRACT / "examples"
CET = timezone(timedelta(hours=1))


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


def make_leg(dep_hour: int, arr_hour: int, origin: str = "berlin", destination: str = "munich") -> Leg:
    return Leg(
        mode=TransportMode.TRAIN,
        origin=Stop(origin),
        destination=Stop(destination),
        departure_at=datetime(2026, 12, 15, dep_hour, tzinfo=CET),
        arrival_at=datetime(2026, 12, 15, arr_hour, tzinfo=CET),
    )


def make_journey(journey_id: str = "j1", **overrides) -> Journey:
    return Journey(**{"id": journey_id, "provider_id": "mock-rail", "legs": (make_leg(8, 12),), **overrides})


# --------------------------------------------------------------------------- #
# Request
# --------------------------------------------------------------------------- #


class RequestTests(unittest.TestCase):
    def test_minimal_request_uses_defaults(self):
        request = make_request()
        self.assertEqual(request.passengers, (Passenger(age=None),))
        self.assertIsNone(request.departure_before)
        self.assertIsNone(request.origin_coordinates)

    def test_round_trip_keeps_local_offset(self):
        for name in ["request.json", "request-taxi.json"]:
            with self.subTest(name):
                data = load_example(name)
                request = JourneySearchRequest.from_dict(data)
                self.assertEqual(request.departure_after.utcoffset(), timedelta(hours=1))
                self.assertEqual(request.to_dict(), data)

    def test_ages_are_optional_per_passenger(self):
        request = make_request(passengers=[{"age": 34}, {"age": 0}, {"age": None}, {}])
        self.assertEqual([p.age for p in request.passengers], [34, 0, None, None])
        self.assertEqual(request.passenger_count, 4)

    def test_ride_within_one_city_needs_coordinates(self):
        a = {"latitude": 52.5251, "longitude": 13.3694}
        b = {"latitude": 52.3667, "longitude": 13.5033}
        request = make_request(destination_id="berlin", origin_coordinates=a, destination_coordinates=b)
        self.assertEqual(request.destination_coordinates, Coordinates(52.3667, 13.5033))
        with self.assertRaises(ContractValidationError) as ctx:
            make_request(destination_id="berlin", origin_coordinates=a)
        self.assertIn("destination_id", ctx.exception.fields)
        with self.assertRaises(ContractValidationError) as ctx:
            make_request(destination_id="berlin", origin_coordinates=a, destination_coordinates=a)
        self.assertIn("destination_coordinates", ctx.exception.fields)

    def test_unknown_fields_are_ignored(self):
        self.assertEqual(make_request(max_price=100), make_request())

    def test_reports_all_field_errors_at_once(self):
        with self.assertRaises(ContractValidationError) as ctx:
            JourneySearchRequest.from_dict({"origin_id": "Berlin Hbf", "departure_after": "tomorrow"})
        self.assertEqual(set(ctx.exception.fields), {"origin_id", "destination_id", "departure_after"})

    def test_rejects_invalid_values(self):
        cases = {
            "departure_after": {"departure_after": "2026-12-15T06:00:00"},  # no offset
            "destination_id": {"destination_id": "berlin"},  # same as origin
            "departure_before": {"departure_before": "2026-12-15T05:00:00+01:00"},  # before after
            "passengers.0.age": {"passengers": [{"age": True}]},  # bool is not an int
            "passengers.1.age": {"passengers": [{}, {"age": 121}]},
            "passengers": {"passengers": [{}] * 10},  # > 9 passengers
            "origin_coordinates.latitude": {"origin_coordinates": {"latitude": 91, "longitude": 0}},
        }
        for expected_field, override in cases.items():
            with self.subTest(expected_field), self.assertRaises(ContractValidationError) as ctx:
                make_request(**override)
            self.assertIn(expected_field, ctx.exception.fields)

    def test_rejects_empty_and_old_passenger_format(self):
        for passengers in ([], {"adults": 2, "children": 1}):
            with self.subTest(passengers=passengers), self.assertRaises(ContractValidationError) as ctx:
                make_request(passengers=passengers)
            self.assertEqual(list(ctx.exception.fields), ["passengers"])

    def test_rejects_non_object(self):
        with self.assertRaises(ContractValidationError):
            JourneySearchRequest.from_dict(["berlin", "munich"])

    def test_direct_construction_is_validated_too(self):
        with self.assertRaises(ContractValidationError):
            JourneySearchRequest("berlin", "munich", datetime(2026, 12, 15, 8))  # naive datetime


# --------------------------------------------------------------------------- #
# Journey / Leg / Offer model
# --------------------------------------------------------------------------- #


class ModelTests(unittest.TestCase):
    def test_journey_with_several_legs(self):
        journey = make_journey(legs=(make_leg(6, 9, "berlin", "cologne"), make_leg(10, 13, "cologne", "paris")))
        self.assertEqual(journey.transfer_count, 1)
        self.assertEqual(journey.duration_minutes, 7 * 60)
        self.assertEqual(journey.origin.location_id, "berlin")
        self.assertEqual(journey.destination.location_id, "paris")

    def test_legs_must_be_in_travel_order(self):
        with self.assertRaises(ContractValidationError) as ctx:
            make_journey(legs=(make_leg(6, 9), make_leg(8, 13)))
        self.assertIn("legs.1.departure_at", ctx.exception.fields)

    def test_journey_needs_a_leg(self):
        with self.assertRaises(ContractValidationError):
            make_journey(legs=())

    def test_unknown_offers_and_empty_offers_are_different(self):
        unknown = make_journey(offers=None)
        none_available = make_journey(offers=())
        self.assertIsNone(unknown.to_dict()["offers"])
        self.assertEqual(none_available.to_dict()["offers"], [])
        self.assertEqual(Journey.from_dict(unknown.to_dict()), unknown)
        self.assertEqual(Journey.from_dict(none_available.to_dict()), none_available)

    def test_unknown_price_is_null_not_zero(self):
        offer = Offer(id="o1", provider_id="mock-rail", price=None)
        self.assertIsNone(offer.to_dict()["price"])
        self.assertIsNone(make_journey(offers=(offer,)).cheapest_known_price())

    def test_cheapest_price_ignores_sold_out_and_unknown(self):
        eur = lambda amount: Money(Decimal(amount), "EUR", PriceBasis.TRIP_TOTAL)  # noqa: E731
        journey = make_journey(
            offers=(
                Offer("a", "mock-rail", eur("19"), availability=Availability.SOLD_OUT),
                Offer("b", "mock-rail", None),
                Offer("c", "mock-rail", eur("49.90")),
                Offer("d", "mock-rail", eur("29")),
            )
        )
        self.assertEqual(journey.cheapest_known_price(), eur("29"))

    def test_price_range(self):
        eur = lambda amount: Money(Decimal(amount), "EUR", PriceBasis.TRIP_TOTAL)  # noqa: E731
        offer = Offer("o", "mock-ride", eur("23"), price_upper=eur("29"), is_price_estimate=True)
        self.assertEqual(Offer.from_dict(offer.to_dict()), offer)
        invalid = [
            dict(price=None, price_upper=eur("29")),
            dict(price=eur("23"), price_upper=eur("20")),
            dict(price=eur("23"), price_upper=Money(Decimal(29), "USD", PriceBasis.TRIP_TOTAL)),
        ]
        for kwargs in invalid:
            with self.subTest(kwargs), self.assertRaises(ContractValidationError) as ctx:
                Offer("o", "mock-ride", **kwargs)
            self.assertIn("price_upper", ctx.exception.fields)

    def test_money_format(self):
        self.assertEqual(Money(Decimal("1700"), "USD", PriceBasis.TRIP_TOTAL).to_dict()["amount"], 1700)
        self.assertEqual(Money(Decimal("251.50"), "EUR", PriceBasis.TRIP_TOTAL).to_dict()["amount"], 251.5)
        for amount, currency in [("1.999", "EUR"), ("-1", "EUR"), ("10", "eur")]:
            with self.subTest(amount=amount, currency=currency), self.assertRaises(ContractValidationError):
                Money(Decimal(amount), currency, PriceBasis.TRIP_TOTAL)

    def test_parse_errors_carry_nested_paths(self):
        data = make_journey().to_dict()
        data["legs"][0]["mode"] = "rocket"
        with self.assertRaises(ContractValidationError) as ctx:
            Journey.from_dict(data)
        self.assertIn("legs.0.mode", ctx.exception.fields)


# --------------------------------------------------------------------------- #
# Result status invariants
# --------------------------------------------------------------------------- #


class ResultStatusTests(unittest.TestCase):
    timeout = ServiceError(ErrorCode.TIMEOUT, "slow", provider_id="mock-rail")

    def test_from_journeys_picks_status(self):
        self.assertIs(JourneySearchResult.from_journeys("train", [make_journey()]).status, SearchStatus.SUCCESS)
        self.assertIs(JourneySearchResult.from_journeys("train", []).status, SearchStatus.NO_RESULTS)
        self.assertIs(JourneySearchResult.from_journeys("train", [], [self.timeout]).status, SearchStatus.PARTIAL)

    def test_only_no_results_means_no_connection(self):
        partial_empty = JourneySearchResult.from_journeys("train", [], [self.timeout])
        self.assertFalse(partial_empty.is_complete)
        self.assertTrue(JourneySearchResult.from_journeys("train", []).is_complete)

    def test_invalid_combinations_are_rejected(self):
        validation = ServiceError(ErrorCode.VALIDATION_ERROR, "bad", field="origin_id")
        invalid = [
            dict(status=SearchStatus.SUCCESS),  # success without journeys
            dict(status=SearchStatus.SUCCESS, journeys=(make_journey(),), errors=(self.timeout,)),
            dict(status=SearchStatus.NO_RESULTS, errors=(self.timeout,)),
            dict(status=SearchStatus.NO_RESULTS, journeys=(make_journey(),)),
            dict(status=SearchStatus.PARTIAL, journeys=(make_journey(),)),  # partial without error
            dict(status=SearchStatus.UNAVAILABLE),
            dict(status=SearchStatus.UNAVAILABLE, journeys=(make_journey(),), errors=(self.timeout,)),
            dict(status=SearchStatus.UNAVAILABLE, errors=(validation,)),
            dict(status=SearchStatus.INVALID_REQUEST, errors=(self.timeout,)),
            dict(status=SearchStatus.SUCCESS, journeys=(make_journey("x"), make_journey("x"))),
        ]
        for kwargs in invalid:
            with self.subTest(kwargs), self.assertRaises(ContractValidationError):
                JourneySearchResult(service_id="train", **kwargs)

    def test_retryable_defaults_follow_error_code(self):
        self.assertTrue(ServiceError(ErrorCode.RATE_LIMITED, "x").is_retryable)
        self.assertFalse(ServiceError(ErrorCode.AUTHENTICATION_FAILED, "x").is_retryable)

    def test_field_only_for_validation_errors(self):
        with self.assertRaises(ContractValidationError):
            ServiceError(ErrorCode.TIMEOUT, "x", field="origin_id")


# --------------------------------------------------------------------------- #
# Example files (shared with docs and other teams' tests)
# --------------------------------------------------------------------------- #


class ExampleFileTests(unittest.TestCase):
    def test_result_examples_parse_and_round_trip(self):
        expected_status = {
            "result-success.json": SearchStatus.SUCCESS,
            "result-success-multi-leg.json": SearchStatus.SUCCESS,
            "result-success-taxi.json": SearchStatus.SUCCESS,
            "result-no-results.json": SearchStatus.NO_RESULTS,
            "result-partial.json": SearchStatus.PARTIAL,
            "result-unavailable.json": SearchStatus.UNAVAILABLE,
        }
        for name, status in expected_status.items():
            with self.subTest(name):
                data = load_example(name)
                result = JourneySearchResult.from_dict(data)
                self.assertIs(result.status, status)
                self.assertEqual(result.to_dict(), data)

    def test_validation_example_maps_to_invalid_request(self):
        result = result_from_http("flight", 400, load_example("error-validation-400.json"))
        self.assertIs(result.status, SearchStatus.INVALID_REQUEST)
        self.assertIn("destination_id", result.validation_fields())

    def test_examples_match_mock_output(self):
        """The examples are real mock output, so docs and code cannot drift apart."""
        request = JourneySearchRequest.from_dict(load_example("request.json"))
        result = asyncio.run(mock_flight_service().search_journeys(request))
        expected = load_example("result-success.json")
        actual = result.to_dict()
        actual["retrieved_at"] = expected["retrieved_at"]
        self.assertEqual(actual, expected)


@unittest.skipUnless(
    __import__("importlib").util.find_spec("jsonschema") and __import__("importlib").util.find_spec("yaml"),
    "jsonschema/pyyaml not installed (optional check)",
)
class OpenApiSchemaTests(unittest.TestCase):
    """Optional: the examples also satisfy openapi.yaml."""

    def validate(self, schema_name: str, instance) -> None:
        import jsonschema
        import yaml

        spec = yaml.safe_load((CONTRACT / "openapi.yaml").read_text(encoding="utf-8"))
        schema = {"$ref": f"#/components/schemas/{schema_name}", "components": spec["components"]}
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(instance)

    def test_examples_match_schema(self):
        self.validate("JourneySearchRequest", load_example("request.json"))
        self.validate("ErrorResponse", load_example("error-validation-400.json"))
        for path in sorted(EXAMPLES.glob("result-*.json")):
            with self.subTest(path.name):
                self.validate("JourneySearchResult", load_example(path.name))


# --------------------------------------------------------------------------- #
# HTTP binding
# --------------------------------------------------------------------------- #


class HttpBindingTests(unittest.TestCase):
    def test_handled_searches_are_200_and_round_trip(self):
        for name in ["result-success.json", "result-partial.json", "result-unavailable.json", "result-no-results.json"]:
            with self.subTest(name):
                result = JourneySearchResult.from_dict(load_example(name))
                status_code, body = result_to_http(result)
                self.assertEqual(status_code, 200)
                self.assertEqual(result_from_http(result.service_id, status_code, json.loads(json.dumps(body))), result)

    def test_invalid_request_is_400_in_api_error_format(self):
        result = JourneySearchResult.invalid_request("flight", {"origin_id": ["Unknown location."]})
        status_code, body = result_to_http(result)
        self.assertEqual(status_code, 400)
        self.assertEqual(body["error"]["code"], "validation_error")
        self.assertEqual(result_from_http("flight", status_code, body).validation_fields(), {"origin_id": ["Unknown location."]})

    def test_parse_error_without_fields(self):
        result = result_from_http("flight", 400, {"error": {"code": "parse_error", "message": "Malformed JSON."}})
        self.assertIs(result.status, SearchStatus.INVALID_REQUEST)
        self.assertEqual(result.validation_fields(), {"non_field_errors": ["Malformed JSON."]})

    def test_transport_failures_become_unavailable(self):
        cases = {
            None: ErrorCode.PROVIDER_UNAVAILABLE,
            429: ErrorCode.RATE_LIMITED,
            503: ErrorCode.PROVIDER_UNAVAILABLE,
            500: ErrorCode.INTERNAL_ERROR,
            404: ErrorCode.INTERNAL_ERROR,
        }
        for status_code, code in cases.items():
            with self.subTest(status_code):
                result = result_from_http("flight", status_code, None)
                self.assertIs(result.status, SearchStatus.UNAVAILABLE)
                self.assertIs(result.errors[0].code, code)

    def test_broken_200_body_becomes_unavailable(self):
        for body in [None, {}, {"status": "success"}, load_example("result-success.json") | {"contract_version": "2.0"}]:
            with self.subTest(body=str(body)[:40]):
                self.assertIs(result_from_http("flight", 200, body).status, SearchStatus.UNAVAILABLE)

    def test_200_from_other_service_is_rejected(self):
        self.assertIs(result_from_http("train", 200, load_example("result-success.json")).status, SearchStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
