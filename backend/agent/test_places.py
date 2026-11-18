"""Tests for the place list: matching names, rejecting unknown places, the endpoint."""

import datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from agent import places
from agent.main_agent import read_message
from agent.planner_client import PlannerUnavailable
from llm import FakeLLM
from planning.models import PlanningSession
from planning.trip_state import TripState

PLACES = [
    {"name": "Lissabon", "country": "Portugal", "aliases": ["lisbon", "lisboa", "lis"]},
    {"name": "München", "country": "Deutschland", "aliases": ["munich", "muenchen"]},
    {"name": "Zürich", "country": "Schweiz", "aliases": ["zrh"]},
    {"name": "Berlin", "country": "Deutschland", "aliases": ["ber"]},
]
TODAY = datetime.date(2026, 11, 15)


class PlacePlanner:
    """A planner that offers the place list."""

    def __init__(self, listing=PLACES, fail=False):
        self.listing, self.fail, self.calls = listing, fail, 0

    def places(self):
        self.calls += 1
        if self.fail:
            raise PlannerUnavailable("down")
        return self.listing


def extraction(**values):
    empty = dict.fromkeys((
        "origin", "destination", "departure_earliest", "departure_latest", "return_earliest",
        "return_latest", "one_way", "travelers", "budget_amount", "budget_basis", "max_stops",
    ))
    return {**empty, "inferred": [], "confirmed": [], "cleared": [], "intent": "trip_info",
            "note": None, **values}


class CatalogTests(SimpleTestCase):
    def setUp(self):
        places.clear_cache()
        self.catalog = places.Catalog(PLACES)

    def test_names_and_aliases_are_matched_without_case_and_accents(self):
        for typed, expected in [
            ("Lissabon", "Lissabon"), ("lisbon", "Lissabon"), (" LISBOA ", "Lissabon"),
            ("munchen", "München"), ("Muenchen", "München"), ("zurich", "Zürich"),
        ]:
            with self.subTest(typed):
                self.assertEqual(self.catalog.canonical(typed), expected)
        self.assertIsNone(self.catalog.canonical("Atlantis"))

    def test_check_replaces_known_places_and_rejects_unknown_ones(self):
        changes = {"origin": "munich", "destination": "Atlantis", "travelers": 2}
        rejected = self.catalog.check(changes)
        self.assertEqual(changes, {"origin": "München", "travelers": 2})
        self.assertEqual(list(rejected), ["destination"])
        self.assertIn("no flights for this place", rejected["destination"])
        self.assertIn("Lissabon", rejected["destination"])

    def test_the_list_is_cached_and_survives_a_planner_outage(self):
        planner = PlacePlanner()
        self.assertEqual(places.load(planner), PLACES)
        self.assertEqual(places.load(planner), PLACES)
        self.assertEqual(planner.calls, 1)
        places.clear_cache()
        self.assertIsNone(places.load(PlacePlanner(fail=True)))
        self.assertIsNone(places.load(object()))


class ReadingWithPlacesTests(SimpleTestCase):
    def read(self, state, data, catalog):
        with patch("llm.base.logger"):
            return read_message(
                state, "…", history=[], llm=FakeLLM([data]), today=TODAY, catalog=catalog
            )

    def test_an_alias_is_stored_under_its_canonical_name(self):
        state = TripState()
        reading = self.read(state, extraction(destination="lisbon"), places.Catalog(PLACES))
        self.assertEqual(state.value("destination"), "Lissabon")
        self.assertEqual(reading.rejected, {})
        self.assertEqual(reading.dropped, [])

    def test_an_unknown_place_is_rejected_with_the_reason_and_not_dropped(self):
        state = TripState()
        reading = self.read(
            state, extraction(origin="Berlin", destination="Atlantis"), places.Catalog(PLACES)
        )
        self.assertEqual(state.value("origin"), "Berlin")
        self.assertIsNone(state.value("destination"))
        self.assertEqual(list(reading.rejected), ["destination"])
        self.assertEqual(reading.dropped, [])

    def test_without_a_list_places_are_taken_as_they_are(self):
        state = TripState()
        reading = self.read(state, extraction(destination="Atlantis"), None)
        self.assertEqual(state.value("destination"), "Atlantis")
        self.assertEqual(reading.dropped, [])


@override_settings(LLM_PROVIDER="offline")
class PlaceEndpointTests(TestCase):
    def setUp(self):
        places.clear_cache()
        self.addCleanup(places.clear_cache)
        self.client = APIClient()

    def test_lists_the_places_of_the_planner(self):
        with patch("planning.views.PlannerClient", return_value=PlacePlanner()):
            response = self.client.get("/api/v1/places/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"count": 4, "next": None, "previous": None, "results": PLACES}
        )

    def test_planner_down_returns_503(self):
        with (
            patch("planning.views.PlannerClient", return_value=PlacePlanner(fail=True)),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = self.client.get("/api/v1/places/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "service_unavailable")

    def test_form_places_are_matched_and_unknown_ones_rejected(self):
        session = PlanningSession.objects.create(title="t")
        url = f"/api/v1/planning-sessions/{session.id}/messages/"
        with patch("planning.views.PlannerClient", return_value=PlacePlanner()):
            ok = self.client.post(url, {"fields": {"origin": "munich"}}, format="json")
            bad = self.client.post(url, {"fields": {"destination": "Atlantis"}}, format="json")
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.json()["trip_state"]["origin"]["value"], "München")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("destination", bad.json()["error"]["fields"]["fields"])
