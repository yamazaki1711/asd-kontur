from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def test_unified_harness_contract_pack_fingerprints_and_fixtures() -> None:
    root = Path("contracts/v1.8")
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    assert registry["registry_version"] == "1.8.0"
    schema_path = root / registry["schemas"][0]["path"]
    assert (
        registry["schemas"][0]["digest"]
        == "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    manifest = json.loads((root / "fixtures/manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        payload = json.loads((root / "fixtures" / fixture["path"]).read_text(encoding="utf-8"))
        fragment = schema
        for part in fixture["schema_pointer"].strip("/").split("/"):
            fragment = fragment[part]
        valid = not tuple(validator.evolve(schema=fragment).iter_errors(payload))
        assert valid is (fixture["expected"] == "valid"), fixture["path"]
