from __future__ import annotations

import importlib.util
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONTRACT = Path(__file__).resolve().parents[3] / "contract"

BERLIN = {"latitude": 52.5200, "longitude": 13.4050}
LONDON = {"latitude": 51.5072, "longitude": -0.1276}

HAS_SCHEMA_TOOLS = bool(importlib.util.find_spec("jsonschema") and importlib.util.find_spec("yaml"))


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def request_body(**overrides) -> dict:
    return {
        "origin_id": "berlin",
        "destination_id": "london",
        "origin_coordinates": BERLIN,
        "destination_coordinates": LONDON,
        "departure_after": "2026-12-15T06:00:00+01:00",
        **overrides,
    }


def assert_matches_openapi(instance: dict, schema_name: str) -> None:
    """Validates against domain-services/contract/openapi.yaml (needs jsonschema and pyyaml)."""
    import jsonschema
    import yaml

    spec = yaml.safe_load((CONTRACT / "openapi.yaml").read_text(encoding="utf-8"))
    schema = {"$ref": f"#/components/schemas/{schema_name}", "components": spec["components"]}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(json.loads(json.dumps(instance)))
