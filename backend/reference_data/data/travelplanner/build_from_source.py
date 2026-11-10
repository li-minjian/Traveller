"""Build the bundled TravelPlanner files from the original Hugging Face CSVs.

Only needed to recreate or update the data in this directory; the import
command reads the generated files. Uses the standard library only.

    python build_from_source.py <directory with train.csv, validation.csv, test.csv>

Source: https://huggingface.co/datasets/osunlp/TravelPlanner (revision below).
The CSVs store lists and dicts as Python literals. They are converted to JSON
and numbers in text form to integers; all values stay unchanged otherwise.
"""

import ast
import csv
import gzip
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

REVISION = "8736504ecfc31b7f8b7e40122873c337e83fff7c"
SPLITS = ["train", "validation", "test"]
LITERAL_FIELDS = {"date", "local_constraint", "annotated_plan", "reference_information"}
INTEGER_FIELDS = {"days", "visiting_city_number", "people_number", "budget"}
# Fixed key order of a case; fields missing in a split (test) become null.
FIELDS = [
    "org", "dest", "days", "visiting_city_number", "date", "people_number",
    "local_constraint", "budget", "query", "level", "annotated_plan",
    "reference_information",
]

DATASET = {
    "slug": "travelplanner",
    "name": "TravelPlanner",
    "version": REVISION,
    "source_url": "https://huggingface.co/datasets/osunlp/TravelPlanner",
    "homepage_url": "https://osu-nlp-group.github.io/TravelPlanner/",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "citation": (
        "Jian Xie, Kai Zhang, Jiangjie Chen, Tinghui Zhu, Renze Lou, Yuandong Tian, "
        "Yanghua Xiao, Yu Su (2024): TravelPlanner: A Benchmark for Real-World "
        "Planning with Language Agents. arXiv:2402.01622"
    ),
    "retrieved_on": date.today().isoformat(),
    "changes": (
        "Converted from CSV with Python-literal fields to gzip-compressed JSON Lines; "
        "numbers in text form became integers. Stable case IDs were added from split "
        "and row number. All other values are unchanged."
    ),
    "notice": (
        "Historical benchmark data: trips in 2022 with offers and prices from the "
        "benchmark's sandbox database. Not current travel offers."
    ),
}


def convert(split: str, row_number: int, row: dict) -> dict:
    case = {"id": f"travelplanner-{split}-{row_number:04d}", "split": split, "row": row_number}
    for field in FIELDS:
        value = row.get(field)
        if value is None or value == "":
            case[field] = None
        elif field in LITERAL_FIELDS:
            case[field] = ast.literal_eval(value)
        elif field in INTEGER_FIELDS:
            case[field] = int(value)
        else:
            case[field] = value
    return case


def main(source: Path, target: Path) -> None:
    csv.field_size_limit(sys.maxsize)
    files = []
    for split in SPLITS:
        with (source / f"{split}.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        lines = [
            json.dumps(convert(split, number, row), ensure_ascii=False, separators=(",", ":"))
            for number, row in enumerate(rows)
        ]
        payload = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), compresslevel=9, mtime=0)
        path = target / f"{split}.jsonl.gz"
        path.write_bytes(payload)
        files.append({
            "split": split,
            "path": path.name,
            "cases": len(rows),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        print(f"{split}: {len(rows)} cases -> {path.name} ({len(payload) / 1e6:.2f} MB)")

    manifest = {"format": "traveller-reference-cases/1", "dataset": DATASET, "files": files}
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(__file__).resolve().parent)
