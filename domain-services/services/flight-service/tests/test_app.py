"""HTTP layer (FastAPI). Skipped if FastAPI is not installed (pip install -r requirements.txt httpx)."""

import importlib.util
import unittest

from .helpers import request_body

HAS_FASTAPI = bool(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"))


@unittest.skipUnless(HAS_FASTAPI, "fastapi/httpx not installed")
class AppTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from adapters.travelpayouts import TravelpayoutsAdapter
        from airport_finder import AirportFinder
        from flight_request.search import FlightSearch
        from main import create_app

        from .test_flight_search import ber_lhr_transport

        search = FlightSearch(AirportFinder.from_files(), [TravelpayoutsAdapter("token", transport=ber_lhr_transport())])
        self.client = TestClient(create_app(search))

    def test_health(self):
        body = self.client.get("/health").json()
        self.assertEqual((body["status"], body["providers"]), ("ok", ["travelpayouts"]))

    def test_search_endpoint(self):
        response = self.client.post("/api/v1/journey-searches/", json=request_body())
        self.assertEqual((response.status_code, response.json()["status"]), (200, "success"))
        response = self.client.post("/api/v1/journey-searches/", json={})
        self.assertEqual(response.status_code, 400)
