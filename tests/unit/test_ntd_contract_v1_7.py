from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema


def test_ntd_contract_registry_and_fixtures(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.7"
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    assert registry["registry_version"] == "1.7.0"
    schema_entry = registry["schemas"][0]
    schema_bytes = (root / schema_entry["path"]).read_bytes()
    assert schema_entry["digest"] == f"sha256:{hashlib.sha256(schema_bytes).hexdigest()}"

    schema = json.loads(schema_bytes)
    manifest = json.loads((root / "fixtures/manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        document = json.loads((root / "fixtures" / fixture["path"]).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(
            {**schema, "$ref": f"#{fixture['schema_pointer']}"},
            format_checker=jsonschema.FormatChecker(),
        )
        errors = list(validator.iter_errors(document))
        assert (not errors) is (fixture["expected"] == "valid"), (fixture["path"], errors)
