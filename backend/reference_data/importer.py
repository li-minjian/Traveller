"""Validate and import benchmark cases from a manifest with JSON Lines files.

A manifest (see data/travelplanner/manifest.json) describes the dataset and
lists one gzip-compressed JSON Lines file per split. Every line is one case.
Valid cases are created or updated by their stable ID, so repeated imports do
not create duplicates. Invalid cases are rejected with file, line and field.
The import only writes reference data tables; application data is untouched.
"""

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from reference_data.models import BenchmarkCase, BenchmarkDataset

FORMAT = "traveller-reference-cases/1"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "data" / "travelplanner" / "manifest.json"
BATCH_SIZE = 100


class ImportFileError(Exception):
    """The manifest or one of its files cannot be used at all."""


class DatasetRecordSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=50)
    name = serializers.CharField(max_length=100)
    version = serializers.CharField(max_length=100)
    source_url = serializers.URLField()
    homepage_url = serializers.URLField(required=False, allow_blank=True, default="")
    license = serializers.CharField(max_length=100)
    license_url = serializers.URLField()
    citation = serializers.CharField()
    retrieved_on = serializers.DateField()
    changes = serializers.CharField()
    notice = serializers.CharField()


class CaseRecordSerializer(serializers.Serializer):
    id = serializers.RegexField(r"^[a-z0-9][a-z0-9-]*$", max_length=100)
    split = serializers.ChoiceField(choices=BenchmarkCase.Split.choices)
    row = serializers.IntegerField(min_value=0)
    level = serializers.ChoiceField(choices=BenchmarkCase.Level.choices)
    query = serializers.CharField()
    org = serializers.CharField(max_length=200)
    dest = serializers.CharField(max_length=200)
    days = serializers.IntegerField(min_value=1, max_value=60)
    visiting_city_number = serializers.IntegerField(min_value=1, allow_null=True)
    date = serializers.ListField(child=serializers.DateField(), allow_empty=False)
    people_number = serializers.IntegerField(min_value=1, allow_null=True)
    local_constraint = serializers.DictField(allow_null=True)
    budget = serializers.IntegerField(min_value=0, allow_null=True)
    annotated_plan = serializers.ListField(allow_null=True)
    reference_information = serializers.ListField(allow_empty=False)

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(f"Unknown fields: {', '.join(unknown)}.")
        if len(attrs["date"]) != attrs["days"]:
            raise serializers.ValidationError(
                {"date": [f"Expected {attrs['days']} dates for {attrs['days']} days."]}
            )
        return attrs


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: list[str] = field(default_factory=list)
    per_split: dict[str, int] = field(default_factory=dict)

    @property
    def imported(self) -> int:
        return self.created + self.updated + self.unchanged


def import_manifest(
    manifest_path: Path, splits: set[str] | None = None, dry_run: bool = False
) -> ImportReport:
    manifest = _read_manifest(manifest_path)
    dataset_values = _validated_dataset(manifest["dataset"])
    report = ImportReport()
    seen_ids: set[str] = set()

    with transaction.atomic():
        dataset = None
        if not dry_run:
            dataset, _ = BenchmarkDataset.objects.update_or_create(
                slug=dataset_values.pop("slug"), defaults=dataset_values
            )
        for entry in manifest["files"]:
            if splits and entry.get("split") not in splits:
                continue
            path = _checked_file(manifest_path.parent, entry)
            accepted = 0
            batch: list[dict] = []
            for line_number, record in _read_records(path):
                location = f"{path.name}:{line_number}"
                values = _validated_case(record, entry["split"], location, seen_ids, report)
                if values is None:
                    continue
                accepted += 1
                batch.append(values)
                if len(batch) >= BATCH_SIZE:
                    _write(batch, dataset, report, dry_run)
                    batch = []
            _write(batch, dataset, report, dry_run)
            report.per_split[entry["split"]] = accepted
    return report


def _read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ImportFileError(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ImportFileError(f"Manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ImportFileError(f"Manifest {path} must declare format {FORMAT!r}.")
    if not isinstance(manifest.get("dataset"), dict) or not isinstance(manifest.get("files"), list):
        raise ImportFileError(f"Manifest {path} needs a 'dataset' object and a 'files' list.")
    return manifest


def _validated_dataset(data: dict) -> dict:
    serializer = DatasetRecordSerializer(data=data)
    if not serializer.is_valid():
        raise ImportFileError(f"Invalid dataset metadata: {_format_errors(serializer.errors)}")
    return dict(serializer.validated_data)


def _checked_file(directory: Path, entry: dict) -> Path:
    if not isinstance(entry, dict) or not {"split", "path", "sha256"} <= entry.keys():
        raise ImportFileError(f"Manifest file entry needs split, path and sha256: {entry!r}")
    path = (directory / entry["path"]).resolve()
    if directory.resolve() not in path.parents:
        raise ImportFileError(f"Data file must be next to the manifest: {entry['path']}")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise ImportFileError(f"Data file not found: {path}") from exc
    if digest != entry["sha256"]:
        raise ImportFileError(f"Checksum mismatch for {path.name}: the file was changed or is incomplete.")
    return path


def _read_records(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_number, exc


def _validated_case(record, split, location, seen_ids, report) -> dict | None:
    if isinstance(record, json.JSONDecodeError):
        report.rejected.append(f"{location}: invalid JSON: {record.msg}")
        return None
    if not isinstance(record, dict):
        report.rejected.append(f"{location}: a case must be a JSON object.")
        return None
    label = f"{location} ({record.get('id', 'no id')})"
    serializer = CaseRecordSerializer(data=record)
    if not serializer.is_valid():
        report.rejected.append(f"{label}: {_format_errors(serializer.errors)}")
        return None
    data = serializer.validated_data
    if data["split"] != split:
        report.rejected.append(f"{label}: split is {data['split']!r}, but the file contains {split!r}.")
        return None
    if data["id"] in seen_ids:
        report.rejected.append(f"{label}: duplicate id within this import.")
        return None
    seen_ids.add(data["id"])

    values = {
        "case_id": data["id"],
        "split": data["split"],
        "source_row": data["row"],
        "level": data["level"],
        "query": data["query"],
        "org": data["org"],
        "dest": data["dest"],
        "days": data["days"],
        "visiting_city_number": data["visiting_city_number"],
        "date": [day.isoformat() for day in data["date"]],
        "people_number": data["people_number"],
        "local_constraint": data["local_constraint"],
        "budget": data["budget"],
        "annotated_plan": data["annotated_plan"],
        "reference_information": data["reference_information"],
    }
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    values["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return values


def _write(batch: list[dict], dataset, report: ImportReport, dry_run: bool) -> None:
    if not batch:
        return
    existing = dict(
        BenchmarkCase.objects.filter(case_id__in=[c["case_id"] for c in batch]).values_list(
            "case_id", "content_sha256"
        )
    )
    new = [c for c in batch if c["case_id"] not in existing]
    changed = [
        c for c in batch if c["case_id"] in existing and existing[c["case_id"]] != c["content_sha256"]
    ]
    report.created += len(new)
    report.updated += len(changed)
    report.unchanged += len(batch) - len(new) - len(changed)
    if dry_run:
        return
    now = timezone.now()
    BenchmarkCase.objects.bulk_create(
        [BenchmarkCase(dataset=dataset, imported_at=now, **values) for values in new]
    )
    for values in changed:
        BenchmarkCase.objects.filter(case_id=values["case_id"]).update(
            dataset=dataset, imported_at=now, **values
        )


def _format_errors(errors, prefix: str = "") -> str:
    """Flatten DRF errors, e.g. {"date": {0: ["Wrong format."]}} -> "date[0]: Wrong format." """
    if isinstance(errors, dict):
        parts = []
        for name, value in errors.items():
            if name == "non_field_errors":
                parts.append(_format_errors(value, prefix))
            else:
                key = f"{prefix}[{name}]" if isinstance(name, int) else (f"{prefix}.{name}" if prefix else name)
                parts.append(_format_errors(value, key))
        return " ".join(parts)
    if isinstance(errors, list):
        messages = " ".join(str(message) for message in errors)
        return f"{prefix}: {messages}" if prefix else messages
    return f"{prefix}: {errors}" if prefix else str(errors)
