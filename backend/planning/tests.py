"""Tests for the planning session API."""

import uuid

from django.test import Client, TestCase, modify_settings, override_settings
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

    def test_a_new_session_starts_with_one_assumed_traveller(self):
        body = self.client.post(LIST_URL, {"title": "Trip"}, format="json").json()
        state = self.client.get(f"{detail_url(body['id'])}trip-state/").json()
        self.assertEqual(state["trip_state"]["travelers"], {"value": 1, "provenance": "inferred"})
        self.assertNotIn("travelers", state["missing_fields"])

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


@modify_settings(MIDDLEWARE={"append": "django.contrib.sessions.middleware.SessionMiddleware"})
@override_settings(
    ISOLATE_PLANNING_SESSIONS=True,
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
    SESSION_COOKIE_NAME="__Host-traveller",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Strict",
)
class BrowserSessionIsolationTests(TestCase):
    def test_session_data_requires_the_creating_browser_cookie(self):
        response = self.client.post(LIST_URL, {"title": "Shared DEV trip"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.cookies["__Host-traveller"]["secure"])
        url = detail_url(response.json()["id"])
        other_browser = Client()
        for path in (url, url + "trip-state/", url + "messages/"):
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(other_browser.get(path).status_code, 404)
        self.assertEqual(
            other_browser.post(url + "messages/", {"text": "hello"}, content_type="application/json").status_code,
            404,
        )
