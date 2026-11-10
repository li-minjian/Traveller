"""Tests for the planning session API."""

import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from planning.models import PlanningSession

LIST_URL = "/api/v1/planning-sessions/"


def detail_url(session_id) -> str:
    return f"/api/v1/planning-sessions/{session_id}/"


class CreatePlanningSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_creates_a_session_and_returns_201(self):
        response = self.client.post(LIST_URL, {"title": "Weekend in Leipzig"}, format="json")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), {"id", "title", "created_at"})
        self.assertEqual(body["title"], "Weekend in Leipzig")
        uuid.UUID(body["id"])
        self.assertTrue(body["created_at"].endswith("Z"), "timestamps are UTC")
        self.assertTrue(PlanningSession.objects.filter(id=body["id"]).exists())

    def test_ignores_client_supplied_id_and_timestamp(self):
        chosen = "00000000-0000-0000-0000-000000000001"
        response = self.client.post(
            LIST_URL,
            {"title": "Trip", "id": chosen, "created_at": "2000-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()["id"], chosen)
        self.assertFalse(response.json()["created_at"].startswith("2000"))

    def test_rejects_invalid_titles_with_field_errors(self):
        cases = {
            "missing": {},
            "blank": {"title": "   "},
            "too long": {"title": "x" * 201},
            "wrong type": {"title": {"nested": True}},
            "null": {"title": None},
        }
        for name, payload in cases.items():
            with self.subTest(name):
                response = self.client.post(LIST_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)
                error = response.json()["error"]
                self.assertEqual(error["code"], "validation_error")
                self.assertIn("title", error["fields"])
        self.assertEqual(PlanningSession.objects.count(), 0)

    def test_rejects_malformed_and_non_json_bodies(self):
        malformed = self.client.post(LIST_URL, '{"title":', content_type="application/json")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"]["code"], "parse_error")

        not_json = self.client.post(LIST_URL, "title=x", content_type="text/plain")
        self.assertEqual(not_json.status_code, 415)
        self.assertEqual(not_json.json()["error"]["code"], "unsupported_media_type")

        a_list = self.client.post(LIST_URL, [1, 2], format="json")
        self.assertEqual(a_list.status_code, 400)
        self.assertIn("non_field_errors", a_list.json()["error"]["fields"])

    def test_listing_sessions_is_not_offered(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")


class RetrievePlanningSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_an_existing_session(self):
        session = PlanningSession.objects.create(title="Business trip")
        response = self.client.get(detail_url(session.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(session.id))
        self.assertEqual(response.json()["title"], "Business trip")

    def test_created_session_can_be_retrieved_again(self):
        created = self.client.post(LIST_URL, {"title": "Round trip"}, format="json").json()
        response = self.client.get(detail_url(created["id"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created)

    def test_unknown_or_invalid_ids_return_404(self):
        for session_id in [uuid.uuid4(), "not-a-uuid"]:
            with self.subTest(session_id=session_id):
                response = self.client.get(detail_url(session_id))
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.json(),
                    {"error": {"code": "not_found", "message": "The requested resource was not found."}},
                )
