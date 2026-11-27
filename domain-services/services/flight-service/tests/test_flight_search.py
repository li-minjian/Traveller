import asyncio
import json
import unittest

from adapters.base import ProviderRateLimited
from adapters.travelpayouts import HttpResponse, TravelpayoutsAdapter
from airport_finder import AirportFinder
from flight_request.request import RequestInvalid, parse_request
from flight_request.search import FlightSearch, SearchSettings, handle_search

from .helpers import CONTRACT, HAS_SCHEMA_TOOLS, assert_matches_openapi, fixture, request_body

TOKEN = "test-token-123456"
FINDER = AirportFinder.from_files()


class FakeTransport:
    """Answers Travelpayouts calls by airport pair; records the calls."""

    def __init__(self, answers=None, default=None):
        self.answers = answers or {}
        self.default = default or HttpResponse(200, b'{"success": true, "currency": "eur", "data": []}')
        self.calls = []

    async def __call__(self, url, params, headers, timeout):
        self.calls.append((url, dict(params), dict(headers)))
        return self.answers.get((params["origin"], params["destination"]), self.default)


def ber_lhr_transport(**options):
    return FakeTransport({("BER", "LHR"): HttpResponse(200, fixture("travelpayouts-ber-lhr-2026-12.json"))}, **options)


def flight_search(transport) -> FlightSearch:
    return FlightSearch(FINDER, [TravelpayoutsAdapter(TOKEN, transport=transport)], SearchSettings(adapter_timeout_seconds=0.5))


def run(search: FlightSearch, body: dict) -> tuple[int, dict]:
    return asyncio.run(handle_search(json.dumps(body).encode(), search))


class RequestTests(unittest.TestCase):
    def test_coordinates_are_required(self):
        body = request_body()
        del body["origin_coordinates"]
        with self.assertRaises(RequestInvalid) as ctx:
            parse_request(body)
        self.assertIn("origin_coordinates", ctx.exception.fields)

    def test_invalid_values_are_reported_together(self):
        body = request_body(
            origin_id="Berlin",
            destination_coordinates={"latitude": 200, "longitude": 0},
            departure_after="2026-12-15T06:00:00",
            passengers=[],
        )
        with self.assertRaises(RequestInvalid) as ctx:
            parse_request(body)
        self.assertEqual(
            set(ctx.exception.fields), {"origin_id", "destination_coordinates", "departure_after", "passengers"}
        )

    def test_window_and_defaults(self):
        request = parse_request(request_body(departure_before="2026-12-15T12:00:00+01:00"))
        self.assertEqual(request.passenger_ages, (None,))
        self.assertEqual(request.latest_departure.isoformat(), "2026-12-15T12:00:00+01:00")
        with self.assertRaises(RequestInvalid):
            parse_request(request_body(departure_before="2026-12-15T05:00:00+01:00"))


class TravelpayoutsSearchTests(unittest.TestCase):
    def setUp(self):
        self.transport = ber_lhr_transport()
        self.status, self.body = run(flight_search(self.transport), request_body())

    def test_every_airport_pair_is_queried_once_per_month(self):
        pairs = sorted((p["origin"], p["destination"]) for _, p, _ in self.transport.calls)
        self.assertEqual(pairs, [("BER", "LCY"), ("BER", "LHR")])
        params = self.transport.calls[0][1]
        self.assertEqual((params["departure_at"], params["direct"]), ("2026-12", "true"))

    def test_success_with_filtered_and_deduplicated_flights(self):
        self.assertEqual((self.status, self.body["status"], self.body["errors"]), (200, "success", []))
        numbers = [j["legs"][0]["service_number"] for j in self.body["journeys"]]
        # Outside the window (14th, 16th 07:00), with transfer (LH) and other airport (SEN) are dropped.
        self.assertEqual(numbers, ["BA 992", "XQ 2470"])

    def test_journey_fields(self):
        leg = self.body["journeys"][0]["legs"][0]
        self.assertEqual(leg["origin"]["code"], "BER")
        self.assertEqual(leg["origin"]["location_id"], "berlin")
        self.assertEqual(leg["destination"]["name"], "London Heathrow Airport")
        self.assertIsNotNone(leg["destination"]["coordinates"])
        self.assertEqual(leg["arrival_at"], "2026-12-15T10:50:00+00:00")  # local time in London
        self.assertEqual(leg["operator"], "British Airways")
        [offer] = self.body["journeys"][0]["offers"]
        self.assertEqual(offer["price"], {"amount": 119, "currency": "EUR", "basis": "per_person"})
        self.assertTrue(offer["is_price_estimate"])
        self.assertIsNone(self.body["journeys"][1]["offers"][0]["price"])  # 0 -> unknown

    def test_token_only_in_header(self):
        url, params, headers = self.transport.calls[0]
        self.assertEqual(headers["X-Access-Token"], TOKEN)
        self.assertNotIn(TOKEN, url + json.dumps(params))

    @unittest.skipUnless(HAS_SCHEMA_TOOLS, "jsonschema/pyyaml not installed")
    def test_answer_matches_openapi(self):
        assert_matches_openapi(self.body, "JourneySearchResult")


class StatusTests(unittest.TestCase):
    def test_no_flights_is_no_results(self):
        status, body = run(flight_search(FakeTransport()), request_body())
        self.assertEqual((status, body["status"]), (200, "no_results"))

    def test_one_failing_pair_is_partial(self):
        transport = ber_lhr_transport()
        transport.answers[("BER", "LCY")] = HttpResponse(429, b"")
        with self.assertLogs("flight_request.search", "WARNING") as logs:
            _, body = run(flight_search(transport), request_body())
        self.assertEqual(body["status"], "partial")
        self.assertTrue(body["journeys"])
        [error] = body["errors"]
        self.assertEqual((error["code"], error["provider_id"], error["is_retryable"]), ("rate_limited", "travelpayouts", True))
        self.assertIn("BER-LCY", error["message"])
        log = "\n".join(logs.output)
        for secret in (TOKEN, "52.52", "2026-12-15"):
            self.assertNotIn(secret, log)

    def test_all_pairs_failing_is_unavailable_with_distinct_codes(self):
        for http_status, code in ((401, "authentication_failed"), (429, "rate_limited"), (503, "provider_unavailable"), (200, "invalid_provider_response")):
            with self.subTest(http_status=http_status):
                body_bytes = b"<html>" if http_status == 200 else b""
                with self.assertLogs("flight_request.search", "WARNING"):
                    _, body = run(flight_search(FakeTransport(default=HttpResponse(http_status, body_bytes))), request_body())
                self.assertEqual(body["status"], "unavailable")
                self.assertEqual({e["code"] for e in body["errors"]}, {code})

    def test_slow_provider_times_out(self):
        class Slow:
            provider_id = "slow"

            async def search(self, origin, destination, request):
                await asyncio.sleep(1)

        search = FlightSearch(FINDER, [Slow()], SearchSettings(adapter_timeout_seconds=0.05))
        with self.assertLogs("flight_request.search", "WARNING"):
            _, body = run(search, request_body())
        self.assertEqual(body["status"], "unavailable")
        self.assertEqual(body["errors"][0]["code"], "timeout")

    def test_unexpected_adapter_errors_are_contained(self):
        class Broken:
            provider_id = "broken"

            async def search(self, origin, destination, request):
                raise RuntimeError("bug")

        class Limited:
            provider_id = "limited"

            async def search(self, origin, destination, request):
                raise ProviderRateLimited("slow down")

        search = FlightSearch(FINDER, [Broken(), Limited()])
        with self.assertLogs("flight_request.search", "WARNING"):
            _, body = run(search, request_body())
        self.assertEqual({e["code"] for e in body["errors"]}, {"internal_error", "rate_limited"})

    def test_same_airport_on_both_sides_has_no_results(self):
        status, body = run(flight_search(FakeTransport()), request_body(destination_id="berlin", destination_coordinates={"latitude": 52.5, "longitude": 13.4}))
        self.assertEqual((status, body["status"]), (200, "no_results"))


class HttpErrorTests(unittest.TestCase):
    def test_invalid_json_and_invalid_request_are_400(self):
        search = flight_search(FakeTransport())
        status, body = asyncio.run(handle_search(b"{not json", search))
        self.assertEqual((status, body["error"]["code"]), (400, "parse_error"))
        status, body = run(search, {"origin_id": "berlin"})
        self.assertEqual((status, body["error"]["code"]), (400, "validation_error"))
        self.assertIn("departure_after", body["error"]["fields"])

    @unittest.skipUnless(HAS_SCHEMA_TOOLS, "jsonschema/pyyaml not installed")
    def test_contract_example_request_needs_coordinates(self):
        # The generic example has no coordinates: the flight service rejects it in the contract's error format.
        example = json.loads((CONTRACT / "examples" / "request.json").read_text(encoding="utf-8"))
        status, body = run(flight_search(FakeTransport()), example)
        self.assertEqual(status, 400)
        assert_matches_openapi(body, "ErrorResponse")


class ConfigurationTests(unittest.TestCase):
    def test_token_is_required(self):
        with self.assertRaises(ValueError):
            TravelpayoutsAdapter("")
        self.assertNotIn(TOKEN, repr(TravelpayoutsAdapter(TOKEN)))
