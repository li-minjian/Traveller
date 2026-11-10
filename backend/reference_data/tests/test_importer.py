"""Tests for importing reference cases with small self-made files."""

import gzip
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from planning.models import PlanningSession
from reference_data.importer import DEFAULT_MANIFEST, ImportFileError, import_manifest
from reference_data.models import BenchmarkCase, BenchmarkDataset
from reference_data.tests.helpers import DATASET, make_case, make_test_split_case, write_dataset


class ImporterTestCase(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def write(self, files, dataset=None) -> Path:
        return write_dataset(self.directory, files, dataset)


class ImportTests(ImporterTestCase):
    def test_imports_cases_and_dataset_metadata(self):
        plan = [{"days": 1, "current_city": "from Berlin to Leipzig"}]
        manifest = self.write({
            "train": [make_case(row=0, annotated_plan=plan), make_case(row=1, level="medium")],
            "test": [make_test_split_case(row=0)],
        })

        report = import_manifest(manifest)

        self.assertEqual((report.created, report.updated, report.unchanged), (3, 0, 0))
        self.assertEqual(report.rejected, [])
        self.assertEqual(report.per_split, {"train": 2, "test": 1})
        dataset = BenchmarkDataset.objects.get(slug="sample")
        self.assertEqual((dataset.version, dataset.license), ("test-1", "CC BY 4.0"))
        case = BenchmarkCase.objects.get(case_id="sample-train-0000")
        self.assertEqual(case.dataset, dataset)
        self.assertEqual(case.date, ["2022-03-16", "2022-03-17"])
        self.assertEqual(case.annotated_plan, plan)
        self.assertEqual(case.reference_information, make_case()["reference_information"])
        test_case = BenchmarkCase.objects.get(case_id="sample-test-0000")
        self.assertIsNone(test_case.budget)
        self.assertIsNone(test_case.people_number)

    def test_repeated_import_creates_no_duplicates(self):
        manifest = self.write({"train": [make_case(row=0), make_case(row=1)]})
        import_manifest(manifest)

        report = import_manifest(manifest)

        self.assertEqual((report.created, report.updated, report.unchanged), (0, 0, 2))
        self.assertEqual(BenchmarkCase.objects.count(), 2)
        self.assertEqual(BenchmarkDataset.objects.count(), 1)

    def test_changed_case_is_updated_in_place(self):
        import_manifest(self.write({"train": [make_case(row=0), make_case(row=1)]}))
        before = BenchmarkCase.objects.get(case_id="sample-train-0001")

        report = import_manifest(self.write({"train": [make_case(row=0), make_case(row=1, budget=900)]}))

        self.assertEqual((report.created, report.updated, report.unchanged), (0, 1, 1))
        after = BenchmarkCase.objects.get(case_id="sample-train-0001")
        self.assertEqual((after.pk, after.budget), (before.pk, 900))
        self.assertGreater(after.imported_at, before.imported_at)

    def test_import_leaves_planning_sessions_unchanged(self):
        session = PlanningSession.objects.create(title="Existing session")
        before = list(PlanningSession.objects.values_list("id", "title", "created_at"))

        import_manifest(self.write({"train": [make_case()]}))

        self.assertEqual(list(PlanningSession.objects.values_list("id", "title", "created_at")), before)
        self.assertEqual(PlanningSession.objects.get().pk, session.pk)

    def test_split_filter_and_dry_run(self):
        manifest = self.write({"train": [make_case()], "validation": [make_case("validation")]})

        dry = import_manifest(manifest, dry_run=True)
        self.assertEqual((dry.created, dry.imported), (2, 2))
        self.assertFalse(BenchmarkCase.objects.exists())
        self.assertFalse(BenchmarkDataset.objects.exists())

        only_validation = import_manifest(manifest, splits={"validation"})
        self.assertEqual(only_validation.per_split, {"validation": 1})
        self.assertEqual(list(BenchmarkCase.objects.values_list("split", flat=True)), ["validation"])


class InvalidRecordTests(ImporterTestCase):
    def test_rejects_invalid_cases_with_location_and_imports_the_valid_ones(self):
        missing_budget = make_case(row=1)
        del missing_budget["budget"]
        manifest = self.write({
            "train": [
                make_case(row=0),
                missing_budget,
                make_case(row=2, people_number=0),
                make_case(row=3, date=["2022-13-45", "2022-03-17"]),
                make_case(row=4, days=3),
                '{"id": "sample-train-0005", "split": ',
                make_case(row=6, extra="field"),
                make_case(row=7, split="validation"),
                make_case(row=0),
                "[1, 2]",
                make_case(row=10, level="extreme"),
            ]
        })

        report = import_manifest(manifest)

        self.assertEqual(report.created, 1)
        self.assertEqual(BenchmarkCase.objects.count(), 1)
        expected = [
            "train.jsonl.gz:2 (sample-train-0001): budget: This field is required.",
            "train.jsonl.gz:3 (sample-train-0002): people_number: Ensure this value is greater than or equal to 1.",
            "train.jsonl.gz:4 (sample-train-0003): date[0]: Date has wrong format.",
            "train.jsonl.gz:5 (sample-train-0004): date: Expected 3 dates for 3 days.",
            "train.jsonl.gz:6: invalid JSON",
            "train.jsonl.gz:7 (sample-train-0006): Unknown fields: extra.",
            "train.jsonl.gz:8 (sample-validation-0007): split is 'validation', but the file contains 'train'.",
            "train.jsonl.gz:9 (sample-train-0000): duplicate id within this import.",
            "train.jsonl.gz:10: a case must be a JSON object.",
            'train.jsonl.gz:11 (sample-train-0010): level: "extreme" is not a valid choice.',
        ]
        self.assertEqual(len(report.rejected), len(expected))
        for message, start in zip(report.rejected, expected, strict=True):
            self.assertTrue(message.startswith(start), f"{message!r} should start with {start!r}")

    def test_changed_data_file_aborts_before_writing(self):
        manifest = self.write({"train": [make_case()]})
        data_file = self.directory / "train.jsonl.gz"
        data_file.write_bytes(gzip.compress(b'{"tampered": true}\n'))

        with self.assertRaisesMessage(ImportFileError, "Checksum mismatch for train.jsonl.gz"):
            import_manifest(manifest)
        self.assertFalse(BenchmarkDataset.objects.exists())

    def test_unusable_manifests_are_reported(self):
        broken = self.directory / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        wrong_format = self.directory / "wrong.json"
        wrong_format.write_text(json.dumps({"format": "other/1", "dataset": {}, "files": []}), encoding="utf-8")
        bad_dataset = self.write({"train": [make_case()]}, dataset={**DATASET, "license_url": "not a url"})
        outside = self.directory / "outside.json"
        outside.write_text(
            json.dumps({**json.loads(bad_dataset.read_text()), "dataset": DATASET,
                        "files": [{"split": "train", "path": "../train.jsonl.gz", "sha256": "0"}]}),
            encoding="utf-8",
        )

        cases = {
            self.directory / "missing.json": "Manifest not found",
            broken: "Manifest is not valid JSON",
            wrong_format: "must declare format",
            bad_dataset: "Invalid dataset metadata: license_url:",
            outside: "Data file must be next to the manifest",
        }
        for path, message in cases.items():
            with self.subTest(path=path.name), self.assertRaisesMessage(ImportFileError, message):
                import_manifest(path)
        self.assertFalse(BenchmarkCase.objects.exists())


class ImportCommandTests(ImporterTestCase):
    def run_command(self, *args):
        stdout, stderr = StringIO(), StringIO()
        call_command("import_reference_cases", *args, stdout=stdout, stderr=stderr)
        return stdout.getvalue(), stderr.getvalue()

    def test_prints_counts(self):
        manifest = str(self.write({"train": [make_case(row=0), make_case(row=1)]}))

        first, _ = self.run_command(manifest)
        second, _ = self.run_command(manifest)

        self.assertIn("Imported 2 cases (2 new, 0 updated, 0 unchanged), rejected 0.", first)
        self.assertIn("Imported 2 cases (0 new, 0 updated, 2 unchanged), rejected 0.", second)

    def test_fails_after_importing_the_valid_cases_when_some_are_rejected(self):
        manifest = str(self.write({"train": [make_case(row=0), make_case(row=1, budget=-1)]}))
        stdout, stderr = StringIO(), StringIO()

        with self.assertRaisesMessage(CommandError, "1 invalid cases were rejected"):
            call_command("import_reference_cases", manifest, stdout=stdout, stderr=stderr)

        self.assertIn("Rejected train.jsonl.gz:2 (sample-train-0001): budget:", stderr.getvalue())
        self.assertIn("Imported 1 cases (1 new, 0 updated, 0 unchanged), rejected 1.", stdout.getvalue())
        self.assertEqual(BenchmarkCase.objects.count(), 1)

    def test_reports_unusable_files_as_command_error(self):
        with self.assertRaisesMessage(CommandError, "Manifest not found"):
            self.run_command(str(self.directory / "missing.json"))


class BundledDatasetTests(TestCase):
    def test_bundled_travelplanner_data_is_complete_and_valid(self):
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        expected = {entry["split"]: entry["cases"] for entry in manifest["files"]}

        report = import_manifest(DEFAULT_MANIFEST, dry_run=True)

        self.assertEqual(report.rejected, [])
        self.assertEqual(report.per_split, expected)
        self.assertEqual(report.created, 1225)
        self.assertEqual(manifest["dataset"]["license"], "CC BY 4.0")
