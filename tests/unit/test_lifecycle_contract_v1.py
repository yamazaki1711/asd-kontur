from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_lifecycle_attestation_v1_registry_digest_and_fixtures(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v1.0"
    registry = load_json(root / "registry.json")
    contract = registry["contracts"][0]
    schema_path = root / contract["schema_path"]
    schema = load_json(schema_path)
    assert registry["registry_version"] == "1.0.0"
    assert contract["contract_key"] == "lifecycle.destruction-attestation"
    assert contract["supersedes"] == "lifecycle.destruction-attestation@0.1.0"
    assert schema["$id"] == contract["schema_id"]
    assert contract["schema_digest"] == (
        "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = load_json(root / registry["fixtures"]["valid"][0])
    invalid = load_json(root / registry["fixtures"]["invalid"][0]["path"])
    assert not tuple(validator.iter_errors(valid))
    errors = tuple(validator.iter_errors(invalid))
    assert errors
    assert any("Additional properties are not allowed" in error.message for error in errors)


def test_verified_attestation_requires_zero_residue(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.0"
    registry = load_json(root / "registry.json")
    contract = registry["contracts"][0]
    schema = load_json(root / contract["schema_path"])
    payload = load_json(root / registry["fixtures"]["valid"][0])
    payload["aggregate_residue_count"] = 1
    errors = tuple(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )
    assert errors
