from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_professional_assistant_contract_pack_is_exact_and_valid(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.7"
    registry = _load(root / "registry.json")
    for schema_entry in registry["schemas"]:
        schema_path = root / schema_entry["path"]
        assert (
            "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
            == schema_entry["digest"]
        )
        Draft202012Validator.check_schema(_load(schema_path))
    schema_entry = registry["schemas"][0]
    schema_path = root / schema_entry["path"]
    schema = _load(schema_path)
    fixture = _load(root / "fixtures" / "valid" / "professional-assistant-delta.json")
    Draft202012Validator(schema).validate(fixture)
    assert fixture["assistant"]["implementation_count"] == 1
    assert fixture["assistant"]["modes"] == ["Tender", "Support", "Audit", "Restoration"]
    assert fixture["memory"]["practice_units"] == 21_105
    assert fixture["memory"]["verified_normative_provisions"] == 1_294
    assert fixture["external_acceptance"] == "pending"
    assistant_context = _load(
        root / "schemas" / "professional-assistant-context.schema.json"
    )
    Draft202012Validator(assistant_context).validate(
        {"query": "Какие документы нужны?", "mode": "Support"}
    )
