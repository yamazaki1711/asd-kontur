from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_support_contract_registry_schema_and_fixtures(repository_root: Path) -> None:
    common_root = repository_root / "contracts" / "v0.1" / "schemas"
    support_root = repository_root / "contracts" / "v1.3"
    registry_data = load_json(support_root / "registry.json")
    assert isinstance(registry_data, dict)
    assert registry_data["registry_version"] == "1.3.0"
    assert registry_data["compatibility"]["preserves"] == [
        "0.1.0",
        "1.0.0",
        "1.1.0",
        "1.2.0",
    ]
    schema_path = support_root / "schemas" / "support.schema.json"
    schema = load_json(schema_path)
    assert isinstance(schema, dict)
    Draft202012Validator.check_schema(schema)
    digest = "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert registry_data["schemas"][0]["digest"] == digest

    schema_store: dict[str, dict[str, object]] = {}
    for path in (*common_root.glob("*.json"), schema_path):
        value = load_json(path)
        assert isinstance(value, dict)
        schema_id = value.get("$id")
        assert isinstance(schema_id, str)
        assert schema_id not in schema_store
        schema_store[schema_id] = value
    local_registry = Registry()
    for schema_id, value in schema_store.items():
        local_registry = local_registry.with_resource(schema_id, Resource.from_contents(value))
    validator = Draft202012Validator(schema, registry=local_registry)
    manifest = load_json(support_root / "fixtures" / "manifest.json")
    assert isinstance(manifest, dict)
    for fixture_name in manifest["valid"]:
        validator.validate(load_json(support_root / "fixtures" / fixture_name))
    for entry in manifest["invalid"]:
        with pytest.raises(ValidationError):
            validator.validate(load_json(support_root / "fixtures" / entry["path"]))


def test_support_contract_has_local_refs_and_exact_versions(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.3"
    serialized = (root / "schemas" / "support.schema.json").read_text(encoding="utf-8")
    assert '"latest"' in serialized  # only explicit negative guards
    schema = load_json(root / "schemas" / "support.schema.json")
    assert isinstance(schema, dict)

    def refs(value: object) -> list[str]:
        if isinstance(value, dict):
            return [
                *([value["$ref"]] if isinstance(value.get("$ref"), str) else []),
                *(ref for child in value.values() for ref in refs(child)),
            ]
        if isinstance(value, list):
            return [ref for child in value for ref in refs(child)]
        return []

    assert all(ref.startswith(("#", "urn:asd-kontur:")) for ref in refs(schema))
