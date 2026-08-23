from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_audit_contract_registry_schema_and_fixtures(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.4"
    registry = load_json(root / "registry.json")
    assert registry["registry_version"] == "1.4.0"
    assert registry["compatibility"]["kind"] == "additive"
    assert registry["compatibility"]["preserves"] == [
        "0.1.0",
        "1.0.0",
        "1.1.0",
        "1.2.0",
        "1.3.0",
    ]
    schema_path = root / registry["schemas"][0]["path"]
    payload = schema_path.read_bytes()
    assert registry["schemas"][0]["digest"] == "sha256:" + hashlib.sha256(payload).hexdigest()
    schema = json.loads(payload)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for fixture in registry["fixtures"]["valid"]:
        assert list(validator.iter_errors(load_json(root / fixture))) == []
    for fixture in registry["fixtures"]["invalid"]:
        assert list(validator.iter_errors(load_json(root / fixture["path"])))


def test_audit_contract_references_are_local_and_exact(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.4"
    schema = load_json(root / "schemas" / "audit.schema.json")
    serialized = json.dumps(schema)
    assert "http://" not in serialized
    assert '"latest"' in serialized  # exactVersion explicitly rejects it
    assert schema["$id"] == "urn:asd-kontur:contracts:v1.4:schema:audit"
