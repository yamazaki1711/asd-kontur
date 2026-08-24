from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_practice_guidance_contract_is_additive_and_fixtures_validate(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v1.5"
    registry = _load(root / "registry.json")
    assert registry["registry_version"] == "1.5.0"
    assert registry["compatibility"]["kind"] == "additive"
    assert registry["compatibility"]["preserves"][-1] == "1.4.0"
    schema_path = root / registry["schemas"][0]["path"]
    schema_bytes = schema_path.read_bytes()
    assert registry["schemas"][0]["digest"] == "sha256:" + hashlib.sha256(schema_bytes).hexdigest()
    schema = json.loads(schema_bytes)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for path in registry["fixtures"]["valid"]:
        assert list(validator.iter_errors(_load(root / path))) == []
    for item in registry["fixtures"]["invalid"]:
        assert list(validator.iter_errors(_load(root / item["path"])))


def test_practice_guidance_contract_has_no_network_references(repository_root: Path) -> None:
    schema = _load(
        repository_root / "contracts" / "v1.5" / "schemas" / "practice-guidance.schema.json"
    )
    encoded = json.dumps(schema)
    assert "http://" not in encoded
    assert "workspace_id" not in encoded
    assert "methodological_guidance" in encoded
