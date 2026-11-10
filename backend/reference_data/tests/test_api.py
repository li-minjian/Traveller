"""Tests for the read-only reference case API."""

import tempfile
from pathlib import Path

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from reference_data.importer import import_manifest
from reference_data.models import BenchmarkCase
from reference_data.tests.helpers import make_case, make_test_split_case, write_dataset

LIST_URL = "/api/v1/reference-cases/"


class ReferenceCaseApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_dataset(Path(directory), {
                "test": [make_test_split_case(row=0, days=3, date=["2022-03-01", "2022-03-02", "2022-03-03"])],
                "validation": [make_case("validation", 0, level="hard")],
                "train": [
                    make_case(row=0, annotated_plan=[{"days": 1}]),
                    make_case(row=1, level="medium"),
                ],
            })
            import_manifest(manifest)

    def setUp(self):
        self.client = APIClient()

    def test_lists_cases_in_split_order_with_page_shape(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"count", "next", "previous", "results"})
        self.assertEqual((body["count"], body["next"], body["previous"]), (4, None, None))
        self.assertEqual(
            [case["id"] for case in body["results"]],
            ["sample-train-0000", "sample-train-0001", "sample-validation-0000", "sample-test-0000"],
        )

    def test_list_items_are_marked_historical_and_omit_large_fields(self):
        first = self.client.get(LIST_URL).json()["results"][0]
        self.assertEqual(first["data_kind"], "historical_benchmark")
        self.assertEqual(first["dataset"]["slug"], "sample")
        self.assertEqual(first["dataset"]["notice"], "Historical benchmark data for tests.")
        self.assertEqual(first["budget"], {"amount": 500, "currency": "USD", "basis": "trip_total"})
        self.assertTrue(first["has_annotated_plan"])
        self.assertNotIn("reference_information", first)
        self.assertNotIn("annotated_plan", first)

    def test_filters_by_split_level_and_days(self):
        cases = {
            "split=train": ["sample-train-0000", "sample-train-0001"],
            "level=hard": ["sample-validation-0000"],
            "days=3": ["sample-test-0000"],
            "split=train&level=medium": ["sample-train-0001"],
            "split=validation&level=easy": [],
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                body = self.client.get(f"{LIST_URL}?{query}").json()
                self.assertEqual([case["id"] for case in body["results"]], expected)
                self.assertEqual(body["count"], len(expected))

    def test_rejects_invalid_filters_and_pages(self):
        for query, field in {"split=foo": "split", "level=extreme": "level", "days=0": "days"}.items():
            with self.subTest(query=query):
                response = self.client.get(f"{LIST_URL}?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["error"]["fields"])
        missing_page = self.client.get(f"{LIST_URL}?page=99")
        self.assertEqual(missing_page.status_code, 404)
        self.assertEqual(missing_page.json()["error"]["code"], "not_found")

    def test_paginates_with_twenty_cases_per_page(self):
        template = BenchmarkCase.objects.get(case_id="sample-train-0001")
        BenchmarkCase.objects.bulk_create(
            BenchmarkCase(
                case_id=f"sample-validation-{row:04d}", dataset=template.dataset, split="validation",
                source_row=row, level="easy", query="q", org="A", dest="B", days=1, date=["2022-03-01"],
                reference_information=[], content_sha256="x", imported_at=timezone.now(),
            )
            for row in range(1, 22)
        )

        first = self.client.get(LIST_URL).json()
        second = self.client.get(first["next"]).json()

        self.assertEqual((first["count"], len(first["results"]), len(second["results"])), (25, 20, 5))
        self.assertIsNone(second["next"])
        self.assertIsNotNone(second["previous"])

    def test_detail_includes_reference_information_and_plan(self):
        train = self.client.get(f"{LIST_URL}sample-train-0000/")
        self.assertEqual(train.status_code, 200)
        self.assertEqual(train.json()["annotated_plan"], [{"days": 1}])
        self.assertEqual(train.json()["reference_information"], make_case()["reference_information"])

        test = self.client.get(f"{LIST_URL}sample-test-0000/").json()
        self.assertIsNone(test["budget"])
        self.assertIsNone(test["annotated_plan"])
        self.assertFalse(test["has_annotated_plan"])

    def test_unknown_case_returns_404(self):
        response = self.client.get(f"{LIST_URL}does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_write_methods_are_not_offered(self):
        before = BenchmarkCase.objects.count()
        for method, url in [
            ("post", LIST_URL),
            ("put", f"{LIST_URL}sample-train-0000/"),
            ("patch", f"{LIST_URL}sample-train-0000/"),
            ("delete", f"{LIST_URL}sample-train-0000/"),
        ]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, {}, format="json")
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.json()["error"]["code"], "method_not_allowed")
        self.assertEqual(BenchmarkCase.objects.count(), before)
