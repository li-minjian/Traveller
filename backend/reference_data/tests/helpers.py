"""Small, self-made test datasets in the import format (manifest + .jsonl.gz)."""

import gzip
import hashlib
import json
from pathlib import Path

from reference_data.importer import FORMAT

DATASET = {
    "slug": "sample",
    "name": "Sample benchmark",
    "version": "test-1",
    "source_url": "https://example.org/sample",
    "homepage_url": "",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "citation": "Test data written for the Traveller test suite.",
    "retrieved_on": "2026-11-10",
    "changes": "None.",
    "notice": "Historical benchmark data for tests.",
}


def make_case(split: str = "train", row: int = 0, **changes) -> dict:
    case = {
        "id": f"sample-{split}-{row:04d}",
        "split": split,
        "row": row,
        "org": "Berlin",
        "dest": "Leipzig",
        "days": 2,
        "visiting_city_number": 1,
        "date": ["2022-03-16", "2022-03-17"],
        "people_number": 1,
        "local_constraint": {"house rule": None, "cuisine": None, "room type": None, "transportation": None},
        "budget": 500,
        "query": "Please plan a 2-day trip from Berlin to Leipzig for one person with a budget of $500.",
        "level": "easy",
        "annotated_plan": None,
        "reference_information": [{"Description": "Attractions in Leipzig", "Content": "Name  Latitude\nZoo  51.35"}],
    }
    case.update(changes)
    return case


def make_test_split_case(row: int = 0, **changes) -> dict:
    """Like the original test split: parameters and plan are missing."""
    return make_case(
        "test",
        row,
        visiting_city_number=None,
        people_number=None,
        local_constraint=None,
        budget=None,
        **changes,
    )


def write_dataset(directory: Path, files: dict[str, list], dataset: dict | None = None) -> Path:
    """Write one .jsonl.gz per split plus manifest.json and return the manifest path.

    Records can be dicts (written as JSON) or raw strings (written as they are).
    """
    entries = []
    for split, records in files.items():
        lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
        payload = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)
        name = f"{split}.jsonl.gz"
        (directory / name).write_bytes(payload)
        entries.append(
            {"split": split, "path": name, "cases": len(records), "sha256": hashlib.sha256(payload).hexdigest()}
        )
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps({"format": FORMAT, "dataset": dataset or DATASET, "files": entries}), encoding="utf-8"
    )
    return manifest
