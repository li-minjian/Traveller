"""Tests for the health endpoint, the uniform error format and the settings helpers."""

import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from config.settings import env, env_bool, env_list


class HealthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_reports_backend_and_database_as_ok(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_reports_503_without_details_when_the_database_is_down(self):
        with (
            patch("config.views.connection") as connection,
            self.assertLogs("config.views", level="WARNING"),
            self.assertLogs("django.request", level="ERROR"),
        ):
            connection.cursor.side_effect = OperationalError(
                'connection to server at "db" failed: password=secret'
            )
            response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"error": {"code": "service_unavailable", "message": "The database is not reachable."}},
        )
        self.assertNotIn(b"secret", response.content)


class ErrorFormatTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_unknown_api_path_answers_with_json_404(self):
        for path in ["/api/v1/does-not-exist/", "/api/v1/health"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_unexpected_error_is_generic_even_with_debug(self):
        with (
            self.settings(DEBUG=True),
            patch(
                "planning.views.PlanningSessionDetailView.retrieve",
                side_effect=RuntimeError("secret password=hunter2"),
            ),
            self.assertLogs("config.exceptions", level="ERROR"),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = self.client.get(
                "/api/v1/planning-sessions/00000000-0000-0000-0000-000000000000/"
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
        )
        self.assertNotIn(b"hunter2", response.content)

    def test_database_error_inside_a_view_becomes_503(self):
        with (
            patch(
                "planning.views.PlanningSessionCreateView.create",
                side_effect=OperationalError("could not connect to db:5432"),
            ),
            self.assertLogs("config.exceptions", level="WARNING"),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = self.client.post(
                "/api/v1/planning-sessions/", {"title": "x"}, format="json"
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "service_unavailable")
        self.assertNotIn(b"5432", response.content)


class SettingsHelperTests(SimpleTestCase):
    def test_env_returns_value_or_default_and_treats_empty_as_unset(self):
        with patch.dict(os.environ, {"T_SET": " value ", "T_EMPTY": ""}):
            self.assertEqual(env("T_SET"), " value ")
            self.assertEqual(env("T_EMPTY", "fallback"), "fallback")
            self.assertEqual(env("T_MISSING", "fallback"), "fallback")

    def test_env_fails_clearly_for_a_missing_required_variable(self):
        with patch.dict(os.environ, {"T_EMPTY": "  "}):
            for name in ["T_MISSING", "T_EMPTY"]:
                with self.subTest(name=name), self.assertRaisesMessage(
                    ImproperlyConfigured, f"Environment variable {name} is not set."
                ):
                    env(name)

    def test_env_bool_accepts_common_spellings_only(self):
        cases = {"true": True, "1": True, "YES": True, "off": False, "0": False, "": None}
        for raw, expected in cases.items():
            with self.subTest(raw=raw), patch.dict(os.environ, {"T_BOOL": raw}):
                self.assertEqual(env_bool("T_BOOL", default=None), expected)
        with patch.dict(os.environ, {"T_BOOL": "maybe"}), self.assertRaises(ImproperlyConfigured):
            env_bool("T_BOOL", default=False)

    def test_env_list_splits_and_trims(self):
        with patch.dict(os.environ, {"T_LIST": " backend, localhost ,,"}):
            self.assertEqual(env_list("T_LIST", "x"), ["backend", "localhost"])
