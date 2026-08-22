from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


def test_tender_contract_extension_is_additive_exact_and_offline(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v1.2"
    registry_document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    assert registry_document["registry_version"] == "1.2.0"
    assert registry_document["compatibility"]["kind"] == "additive"
    assert registry_document["compatibility"]["preserves"] == ["0.1.0", "1.0.0", "1.1.0"]
    schema_path = root / registry_document["schemas"][0]["path"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert (
        "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
        == registry_document["schemas"][0]["digest"]
    )
    common = json.loads(
        (repository_root / "contracts/v0.1/schemas/common.schema.json").read_text(encoding="utf-8")
    )
    resources = Registry().with_resources(
        (
            (common["$id"], Resource.from_contents(common)),
            (schema["$id"], Resource.from_contents(schema)),
        )
    )
    manifest = json.loads((root / "fixtures/manifest.json").read_text(encoding="utf-8"))
    for item in manifest["valid"]:
        payload = json.loads((root / "fixtures" / item["path"]).read_text(encoding="utf-8"))
        assert not list(_validator(schema, item["schema_pointer"], resources).iter_errors(payload))
    for item in manifest["invalid"]:
        payload = json.loads((root / "fixtures" / item["path"]).read_text(encoding="utf-8"))
        assert list(_validator(schema, item["schema_pointer"], resources).iter_errors(payload)), (
            item["expected"]
        )
    assert all(
        ref.startswith("#") or ref.startswith("urn:asd-kontur:contracts:") for ref in _refs(schema)
    )


def _validator(
    schema: dict[str, Any], pointer: str, resources: Registry[Any]
) -> Draft202012Validator:
    fragment: Any = schema
    for token in pointer.removeprefix("#/").split("/"):
        fragment = fragment[token]
    return Draft202012Validator(schema, registry=resources, format_checker=FormatChecker()).evolve(
        schema=fragment
    )


def _refs(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("$ref"), str):
            result.append(value["$ref"])
        for child in value.values():
            result.extend(_refs(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_refs(child))
    return result
