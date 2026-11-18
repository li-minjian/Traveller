"""Tests for the Journey Planner. They use the shared contract examples in
docs/contracts/search-v1/ so that agent and planner agree on the format."""

import copy
import datetime
import json
from pathlib import Path

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from planner.contract import SearchRequestSerializer
from planner.providers import ProviderError
from planner.providers.dummy_flights import PLACES, ROUTES, DummyFlightProvider
from planner.service import plan

# In the repository: <repo>/docs/…; in the container the folder is mounted at /docs/….
EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "search-v1"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def validated(**changes) -> dict:
    serializer = SearchRequestSerializer(data={**example("request.json"), **changes})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def eur(amount, basis="per_person") -> dict:
    return {"amount": amount, "currency": "EUR", "basis": basis}


class FailingProvider:
    mode = "flight"
    name = "failing"

    def search(self, request):
        raise ProviderError("timeout")


class FixedProvider:
    mode = "flight"
    name = "fixed"

    def __init__(self, journeys):
        self.journeys = journeys

    def search(self, request):
        return copy.deepcopy(self.journeys)


class PlanEndpointTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def post(self, body):
        return self.client.post("/plan", body, format="json")

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_example_request_returns_the_example_response(self):
        response = self.post(example("request.json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), example("response_ok.json"))

    def test_example_for_no_results(self):
        response = self.post({**example("request.json"), "max_price": eur(50)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), example("response_no_results.json"))

    def test_invalid_requests_return_400_with_field_errors(self):
        valid = example("request.json")
        cases = {
            "origin": {**valid, "origin": ""},
            "destination": {k: v for k, v in valid.items() if k != "destination"},
            "departure": {**valid, "departure": {"earliest": "2027-05-21", "latest": "2027-05-20"}},
            "travelers": {**valid, "travelers": 0},
            "max_price": {**valid, "max_price": eur(-5)},
            "max_stops": {**valid, "max_stops": -1},
            "modes": {**valid, "modes": ["train"]},
        }
        for field, body in cases.items():
            with self.subTest(field):
                response = self.post(body)
                self.assertEqual(response.status_code, 400)
                error = response.json()["error"]
                self.assertEqual(error["code"], "validation_error")
                self.assertIn(field, error["fields"])

    def test_optional_limits_must_be_sent_but_may_be_null(self):
        valid = example("request.json")
        missing = self.post({k: v for k, v in valid.items() if k != "max_stops"})
        self.assertEqual(missing.status_code, 400)
        self.assertIn("max_stops", missing.json()["error"]["fields"])
        self.assertEqual(self.post({**valid, "max_price": None}).status_code, 200)

    def test_unknown_paths_and_methods_use_the_error_format(self):
        self.assertEqual(self.client.get("/nope").json()["error"]["code"], "not_found")
        response = self.client.get("/plan")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")


class FilterAndRankingTests(SimpleTestCase):
    """2027-05-20 is a Thursday; the dummy has six Berlin–Lisbon flights that day."""

    def plan(self, **changes):
        return plan(validated(**changes), [DummyFlightProvider()])

    def test_returns_at_most_five_sorted_by_price_then_duration(self):
        result = self.plan(max_price=None)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["journeys"]), 5)
        prices = [journey["price"]["amount"] for journey in result["journeys"]]
        self.assertEqual(prices, [98.0, 119.0, 142.5, 164.0, 189.0])
        self.assertIsNone(result["no_results"])
        self.assertIsNone(result["error"])

    def test_equal_prices_are_sorted_by_duration(self):
        def journey(name, minutes):
            start = datetime.datetime(2027, 5, 20, 8, 0, tzinfo=datetime.timezone.utc)
            return {
                "id": name,
                "legs": [{
                    "mode": "flight", "origin": "A", "destination": "B",
                    "departure": start.isoformat(),
                    "arrival": (start + datetime.timedelta(minutes=minutes)).isoformat(),
                    "carrier": None, "number": None,
                }],
                "offers": [{"id": f"{name}-a", "provider": "fixed", "price": eur(100.0)}],
            }

        provider = FixedProvider([journey("slow", 300), journey("fast", 120), journey("mid", 200)])
        result = plan(validated(), [provider])
        self.assertEqual([j["id"] for j in result["journeys"]], ["fast", "mid", "slow"])

    def test_derives_duration_stops_and_price(self):
        cheapest = self.plan(max_price=None)["journeys"][0]
        self.assertEqual(cheapest["stops"], 2)
        self.assertEqual(len(cheapest["legs"]), 3)
        # 06:00 in Berlin (+02:00) to 13:20 in Lisbon (+01:00).
        self.assertEqual(cheapest["duration_minutes"], 500)
        self.assertEqual(cheapest["price"], cheapest["offers"][0]["price"])

    def test_max_price_per_person(self):
        result = self.plan(max_price=eur(120))
        self.assertEqual([j["price"]["amount"] for j in result["journeys"]], [98.0, 119.0])

    def test_max_price_for_the_whole_trip_counts_all_travellers(self):
        # Two travellers: 98 € per person is 196 € in total.
        self.assertEqual(self.plan(max_price=eur(200, "trip_total"))["journeys"][0]["price"]["amount"], 98.0)
        self.assertEqual(len(self.plan(max_price=eur(200, "trip_total"))["journeys"]), 1)
        self.assertEqual(self.plan(max_price=eur(190, "trip_total"))["status"], "no_results")

    def test_a_limit_in_another_currency_matches_nothing(self):
        result = self.plan(max_price={"amount": 500, "currency": "USD", "basis": "per_person"})
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["no_results"]["reason"], "budget")

    def test_max_stops(self):
        direct = self.plan(max_price=None, max_stops=0)
        self.assertEqual([j["stops"] for j in direct["journeys"]], [0, 0])
        one_stop = self.plan(max_price=None, max_stops=1)
        self.assertTrue(all(j["stops"] <= 1 for j in one_stop["journeys"]))
        self.assertEqual(one_stop["journeys"][0]["price"]["amount"], 119.0)

    def test_date_window(self):
        single = self.plan(max_price=None)
        self.assertTrue(all("2027-05-20" in j["id"] for j in single["journeys"]))
        window = self.plan(
            max_price=None, departure={"earliest": "2027-05-18", "latest": "2027-05-20"}
        )
        # Tuesday and Wednesday are cheaper than Thursday.
        self.assertEqual(window["journeys"][0]["price"]["amount"], 83.3)
        days = {j["legs"][0]["departure"][:10] for j in window["journeys"]}
        self.assertLessEqual(days, {"2027-05-18", "2027-05-19", "2027-05-20"})

    def test_journeys_outside_the_window_are_dropped(self):
        outside = DummyFlightProvider().search(
            validated(departure={"earliest": "2027-05-22", "latest": "2027-05-22"})
        )
        result = plan(validated(), [FixedProvider(outside)])
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["no_results"]["reason"], "no_connection")

    def test_no_results_because_of_budget_names_the_cheapest(self):
        result = self.plan(max_price=eur(50))
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["journeys"], [])
        self.assertEqual(result["no_results"]["reason"], "budget")
        self.assertEqual(result["no_results"]["closest_journey"]["price"]["amount"], 98.0)

    def test_budget_reason_respects_max_stops(self):
        result = self.plan(max_price=eur(50), max_stops=0)
        self.assertEqual(result["no_results"]["reason"], "budget")
        self.assertEqual(result["no_results"]["closest_journey"]["stops"], 0)
        self.assertEqual(result["no_results"]["closest_journey"]["price"]["amount"], 189.0)

    def test_no_results_because_of_stops_names_the_one_with_fewest_stops(self):
        with_stops = [
            j for j in DummyFlightProvider().search(validated()) if len(j["legs"]) > 1
        ]
        result = plan(validated(max_stops=0), [FixedProvider(with_stops)])
        self.assertEqual(result["no_results"]["reason"], "max_stops")
        self.assertEqual(result["no_results"]["closest_journey"]["stops"], 1)
        self.assertEqual(result["no_results"]["closest_journey"]["price"]["amount"], 119.0)

    def test_unknown_route_is_a_successful_search_without_results(self):
        result = self.plan(destination="Atlantis")
        self.assertEqual(
            result,
            {
                "status": "no_results",
                "journeys": [],
                "no_results": {
                    "reason": "no_connection", "direction": None, "closest_journey": None,
                },
                "error": None,
            },
        )

    def test_no_connection_on_a_day_without_flights(self):
        # Rome is served on Monday, Wednesday, Friday and Saturday only.
        thursday = {"earliest": "2027-05-20", "latest": "2027-05-20"}
        self.assertEqual(
            self.plan(destination="Rom", departure=thursday)["no_results"]["reason"],
            "no_connection",
        )
        friday = {"earliest": "2027-05-21", "latest": "2027-05-21"}
        self.assertEqual(self.plan(destination="Rome", departure=friday)["status"], "ok")

    def test_same_input_gives_the_same_output(self):
        self.assertEqual(self.plan(), self.plan())

    def test_place_names_are_matched_loosely(self):
        self.assertEqual(self.plan(origin=" berlin ", destination="LISBON")["status"], "ok")


class RoundTripTests(SimpleTestCase):
    """A request with a return window is answered with pairs of flights."""

    BACK = {"earliest": "2027-05-27", "latest": "2027-05-27"}

    def plan(self, **changes):
        request = {**example("request_round_trip.json"), **changes}
        serializer = SearchRequestSerializer(data=request)
        serializer.is_valid(raise_exception=True)
        return plan(serializer.validated_data, [DummyFlightProvider()])

    def test_example_request_returns_the_example_response(self):
        response = APIClient().post("/plan", example("request_round_trip.json"), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), example("response_round_trip.json"))

    def test_every_option_is_an_outbound_with_a_return_flight(self):
        result = self.plan(max_price=None)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["journeys"]), 5)
        for journey in result["journeys"]:
            inbound = journey["inbound"]
            self.assertEqual(journey["legs"][0]["origin"], "Berlin")
            self.assertEqual(journey["legs"][-1]["destination"], "Lissabon")
            self.assertEqual(inbound["legs"][0]["origin"], "Lissabon")
            self.assertEqual(inbound["legs"][-1]["destination"], "Berlin")
            self.assertEqual(inbound["legs"][0]["departure"][:10], "2027-05-27")
            self.assertEqual(journey["id"], f"{journey['id'].split('+')[0]}+{inbound['id']}")
            self.assertAlmostEqual(
                journey["total_price"]["amount"],
                journey["price"]["amount"] + inbound["price"]["amount"],
                places=2,
            )

    def test_sorted_by_the_price_of_both_flights(self):
        totals = [j["total_price"]["amount"] for j in self.plan(max_price=None)["journeys"]]
        self.assertEqual(totals, sorted(totals))

    def test_no_flight_is_repeated_more_than_twice(self):
        journeys = self.plan(max_price=None)["journeys"]
        for part in ("out", "back"):
            ids = [j["id"].split("+")[0] if part == "out" else j["inbound"]["id"] for j in journeys]
            self.assertLessEqual(max(ids.count(i) for i in ids), 2, part)

    def test_the_budget_applies_to_both_flights_together(self):
        cheapest = self.plan(max_price=None)["journeys"][0]["total_price"]["amount"]
        self.assertEqual(self.plan(max_price=eur(cheapest))["status"], "ok")
        result = self.plan(max_price=eur(cheapest - 0.01))
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["no_results"]["reason"], "budget")
        self.assertIsNone(result["no_results"]["direction"])
        closest = result["no_results"]["closest_journey"]
        self.assertEqual(closest["total_price"]["amount"], cheapest)
        self.assertIsNotNone(closest["inbound"])

    def test_max_stops_applies_to_each_direction(self):
        result = self.plan(max_price=None, max_stops=0)
        self.assertEqual(result["status"], "ok")
        for journey in result["journeys"]:
            self.assertEqual(journey["stops"], 0)
            self.assertEqual(journey["inbound"]["stops"], 0)

    def test_the_return_flight_leaves_after_the_outbound_has_landed(self):
        same_day = {"earliest": "2027-05-20", "latest": "2027-05-20"}
        result = self.plan(max_price=None, **{"return": same_day})
        parse = datetime.datetime.fromisoformat
        self.assertEqual(result["status"], "ok")
        for journey in result["journeys"]:
            self.assertGreater(
                parse(journey["inbound"]["legs"][0]["departure"]), parse(journey["legs"][-1]["arrival"])
            )

    def test_no_return_flight_names_the_direction(self):
        # Rome is served on Monday, Wednesday, Friday and Saturday only; the way back daily.
        result = self.plan(
            destination="Rom",
            departure={"earliest": "2027-05-20", "latest": "2027-05-20"},  # a Thursday
        )
        self.assertEqual(result["no_results"]["reason"], "no_connection")
        self.assertEqual(result["no_results"]["direction"], "outbound")
        unknown = self.plan(origin="Berlin", destination="Atlantis")
        self.assertEqual(unknown["no_results"]["direction"], "outbound")

    def test_return_before_departure_is_rejected(self):
        request = {**example("request_round_trip.json"), "return": {"earliest": "2027-05-01", "latest": "2027-05-10"}}
        response = APIClient().post("/plan", request, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("return", response.json()["error"]["fields"])

    def test_return_must_be_sent_but_may_be_null(self):
        request = {k: v for k, v in example("request.json").items() if k != "return"}
        response = APIClient().post("/plan", request, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("return", response.json()["error"]["fields"])

    def test_a_failed_provider_on_the_way_back_is_an_error(self):
        class OutboundOnly(DummyFlightProvider):
            def search(self, request):
                if request["origin"] == "Lissabon":
                    raise ProviderError("down")
                return super().search(request)

        serializer = SearchRequestSerializer(data=example("request_round_trip.json"))
        serializer.is_valid(raise_exception=True)
        with self.assertLogs("planner.service", level="WARNING"):
            result = plan(serializer.validated_data, [OutboundOnly()])
        self.assertEqual(result["status"], "error")


class OneWayShapeTests(SimpleTestCase):
    def test_one_way_results_have_no_inbound_and_the_same_total(self):
        result = plan(validated(), [DummyFlightProvider()])
        for journey in result["journeys"]:
            self.assertIsNone(journey["inbound"])
            self.assertEqual(journey["total_price"], journey["price"])


class ProviderFailureTests(SimpleTestCase):
    def test_a_failed_provider_is_an_error_not_no_results(self):
        with self.assertLogs("planner.service", level="WARNING"):
            result = plan(validated(), [FailingProvider()])
        self.assertEqual(result, example("response_error.json"))

    def test_results_of_working_providers_survive_a_failed_one(self):
        with self.assertLogs("planner.service", level="WARNING"):
            result = plan(validated(), [FailingProvider(), DummyFlightProvider()])
        self.assertEqual(result["status"], "ok")

    def test_providers_of_other_modes_are_not_asked(self):
        train = FailingProvider()
        train.mode = "train"
        self.assertEqual(plan(validated(), [train, DummyFlightProvider()])["status"], "ok")


class GeneratedFlightsTests(SimpleTestCase):
    """Every pair of cities without a hand-written route gets generated flights."""

    def search(self, origin, destination, day="2027-05-20"):
        return DummyFlightProvider().search(
            validated(
                origin=origin, destination=destination,
                departure={"earliest": day, "latest": day},
            )
        )

    def test_routes_between_other_cities_exist(self):
        result = plan(
            validated(origin="Köln", destination="Lisbon", max_price=None),
            [DummyFlightProvider()],
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["journeys"]), 5)
        self.assertEqual(result["journeys"][0]["legs"][0]["origin"], "Köln")
        self.assertEqual(result["journeys"][0]["legs"][-1]["destination"], "Lissabon")
        stops = {journey["stops"] for journey in result["journeys"]}
        self.assertTrue({0, 1} <= stops)

    def test_generated_flights_are_the_same_on_every_call(self):
        self.assertEqual(self.search("Hamburg", "Wien"), self.search("Hamburg", "Wien"))

    def test_same_origin_and_destination_has_no_flights(self):
        self.assertEqual(self.search("Hamburg", "hamburg"), [])

    def test_all_generated_connections_are_consistent(self):
        parse = datetime.datetime.fromisoformat
        # A summer day, a winter day and the day the clocks change.
        for day in ("2027-05-20", "2027-01-12", "2027-03-28"):
            for origin in PLACES:
                for destination in PLACES:
                    if origin == destination or (origin, destination) in ROUTES:
                        continue
                    for journey in self.search(origin, destination, day):
                        legs = journey["legs"]
                        self.assertEqual(legs[0]["departure"][:10], day, journey["id"])
                        self.assertGreater(journey["offers"][0]["price"]["amount"], 0)
                        for leg in legs:
                            self.assertGreater(parse(leg["arrival"]), parse(leg["departure"]))
                        for landing, leaving in zip(legs, legs[1:]):
                            self.assertEqual(landing["destination"], leaving["origin"])
                            wait = parse(leaving["departure"]) - parse(landing["arrival"])
                            self.assertGreaterEqual(wait, datetime.timedelta(minutes=30), journey["id"])
                            self.assertLessEqual(wait, datetime.timedelta(hours=4), journey["id"])


class PlacesTests(SimpleTestCase):
    def test_lists_every_place_with_country_and_aliases(self):
        response = APIClient().get("/places")
        self.assertEqual(response.status_code, 200)
        places = response.json()["places"]
        self.assertEqual(len(places), 30)
        lisbon = next(place for place in places if place["name"] == "Lissabon")
        self.assertEqual(lisbon["country"], "Portugal")
        self.assertIn("lisbon", lisbon["aliases"])
        self.assertEqual(places, sorted(places, key=lambda p: (p["country"], p["name"])))

    def test_every_listed_place_has_flights(self):
        provider = DummyFlightProvider()
        names = [place["name"] for place in provider.places()]
        for name in names:
            other = "Berlin" if name != "Berlin" else "Wien"
            with self.subTest(name):
                self.assertTrue(provider.search(validated(origin=name, destination=other)))

    def test_only_get_is_allowed(self):
        self.assertEqual(APIClient().post("/places", {}, format="json").status_code, 405)
