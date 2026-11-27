import os
import unittest
from unittest import mock

from config import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_without_variables(self):
        with mock.patch.dict(os.environ, {"TRAVELPAYOUTS_API_TOKEN": "t"}, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.search.radius_km, settings.search.radius_step_km, settings.search.max_airports), (30, 10, 3))
        self.assertEqual((settings.travelpayouts_currency, settings.travelpayouts_marker), ("EUR", None))

    def test_empty_values_count_as_not_set(self):
        env = {"TRAVELPAYOUTS_API_TOKEN": "t", "FLIGHT_SEARCH_RADIUS_KM": "", "FLIGHT_MAX_AIRPORTS": " ", "TRAVELPAYOUTS_CURRENCY": ""}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual((settings.search.radius_km, settings.search.max_airports, settings.travelpayouts_currency), (30, 3, "EUR"))

    def test_values_from_environment(self):
        env = {"TRAVELPAYOUTS_API_TOKEN": "t", "FLIGHT_SEARCH_RADIUS_KM": "50", "FLIGHT_SEARCH_RADIUS_STEP_KM": "25", "FLIGHT_MAX_AIRPORTS": "2"}
        with mock.patch.dict(os.environ, env, clear=True):
            search = Settings.from_env().search
        self.assertEqual((search.radius_km, search.radius_step_km, search.max_airports), (50, 25, 2))

    def test_token_required_and_invalid_numbers_are_reported(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            Settings.from_env()
        with mock.patch.dict(os.environ, {"TRAVELPAYOUTS_API_TOKEN": "t", "FLIGHT_MAX_AIRPORTS": "drei"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FLIGHT_MAX_AIRPORTS"):
                Settings.from_env()
