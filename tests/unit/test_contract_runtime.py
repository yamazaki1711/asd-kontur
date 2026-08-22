from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from asd_kontur.contracts import (
    ContractErrorCode,
    ContractRegistry,
    ContractValidationError,
    validate_semantic,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _contract_key_for_schema(registry: ContractRegistry, schema_id: str) -> str:
    for group in registry.document["contract_groups"]:
        if group["schema_id"] == schema_id:
            return str(group["contract_keys"][0])
    raise AssertionError(f"no contract group for {schema_id}")


def test_registry_loads_exact_release_with_unique_ids(
    contract_registry: ContractRegistry,
) -> None:
    assert contract_registry.document["registry_version"] == "0.1.0"
    assert len(contract_registry.schemas) == 13
    assert len(set(contract_registry.schemas)) == 13
    assert all(
        schema_id.startswith("urn:asd-kontur:contracts:v0.1:")
        for schema_id in contract_registry.schemas
    )


def test_registry_rejects_fingerprint_tampering(contract_root: Path, tmp_path: Path) -> None:
    copied = tmp_path / "v0.1"
    shutil.copytree(contract_root, copied)
    schema_path = copied / "schemas" / "common.schema.json"
    schema_path.write_text(schema_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ContractValidationError) as captured:
        ContractRegistry.load(copied)

    assert captured.value.issue.code is ContractErrorCode.INVALID_SCHEMA
    assert "fingerprint" in captured.value.issue.message


def test_registry_rejects_network_reference(contract_root: Path, tmp_path: Path) -> None:
    copied = tmp_path / "v0.1"
    shutil.copytree(contract_root, copied)
    schema_path = copied / "schemas" / "common.schema.json"
    schema = _load(schema_path)
    schema["$defs"]["networkProbe"] = {"$ref": "https://example.invalid/schema.json"}
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    registry_path = copied / "registry.json"
    registry = _load(registry_path)
    digest = "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    for item in registry["schemas"]:
        if item["schema_id"] == schema["$id"]:
            item["digest"] = digest
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractValidationError) as captured:
        ContractRegistry.load(copied)

    assert "network or foreign" in captured.value.issue.message


def test_all_schema_fixtures_have_expected_result(
    contract_registry: ContractRegistry,
    contract_root: Path,
) -> None:
    manifest = _load(contract_root / "fixtures" / "manifest.json")
    schema_fixtures = [item for item in manifest["fixtures"] if item["layer"] == "schema"]
    assert sum(item["expected"] == "valid" for item in schema_fixtures) == 17
    assert sum(item["expected"] == "invalid" for item in schema_fixtures) == 2

    for item in schema_fixtures:
        payload = _load(contract_root / "fixtures" / item["path"])
        result = contract_registry.validate(
            contract_key=_contract_key_for_schema(contract_registry, item["schema_id"]),
            contract_version="0.1.0",
            schema_id=item["schema_id"],
            schema_pointer=item["schema_pointer"],
            payload=payload,
        )
        assert result.valid is (item["expected"] == "valid"), item["path"]
        if not result.valid:
            assert {issue.code.value for issue in result.issues} == {item["expected_error_code"]}
            assert {issue.validation_layer for issue in result.issues} == {"schema"}


def test_all_semantic_invalid_fixtures_are_rejected(
    contract_root: Path,
) -> None:
    manifest = _load(contract_root / "fixtures" / "manifest.json")
    semantic_fixtures = [item for item in manifest["fixtures"] if item["layer"] == "semantic"]
    assert len(semantic_fixtures) == 8

    for item in semantic_fixtures:
        payload = _load(contract_root / "fixtures" / item["path"])
        issue = validate_semantic(item["invariant"], payload)
        assert issue is not None, item["path"]
        assert issue.code.value == item["expected_error_code"]
        assert issue.invariant == item["invariant"]
        assert issue.validation_layer == "semantic"


def test_mutable_latest_is_rejected(contract_registry: ContractRegistry) -> None:
    with pytest.raises(ContractValidationError) as captured:
        contract_registry.contract_family("command.envelope", "latest")

    assert captured.value.issue.code is ContractErrorCode.INCOMPATIBLE_VERSION


def test_rfc_8785_canonicalization_and_sha256(contract_registry: ContractRegistry) -> None:
    payload = {"b": 1, "a": "x", "digest": "sha256:" + "0" * 64}

    assert contract_registry.canonicalize(payload) == b'{"a":"x","b":1}'
    assert contract_registry.digest(payload) == (
        "sha256:cdab067e9f3beb32d1252cfd63e492592fecbf591b0d08cadb24bb17f3864246"
    )


def test_contract_selection_failure_is_typed(contract_registry: ContractRegistry) -> None:
    with pytest.raises(ContractValidationError) as captured:
        contract_registry.contract_family("unknown.contract", "0.1.0")

    assert captured.value.issue.code is ContractErrorCode.UNKNOWN_VERSION
