from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from asd_kontur.integrity.models import ReadinessStatus, load_module_readiness_manifest


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_memory_integrity_contract_is_additive_and_fixtures_validate(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.2"
    registry = _load(root / "registry.json")
    assert registry["registry_version"] == "2.2.0"
    assert registry["compatibility"]["kind"] == "additive"
    assert registry["compatibility"]["preserves"][-1] == "2.1.0"
    schemas = {}
    for entry in registry["schemas"]:
        schema_path = root / entry["path"]
        schema_bytes = schema_path.read_bytes()
        assert entry["digest"] == "sha256:" + hashlib.sha256(schema_bytes).hexdigest()
        schema = json.loads(schema_bytes)
        Draft202012Validator.check_schema(schema)
        schemas[entry["schema_id"]] = schema
    validator = Draft202012Validator(
        schemas["urn:asd-kontur:contracts:v2.2:schema:memory-integrity"],
        format_checker=FormatChecker(),
    )
    for path in registry["fixtures"]["valid"][:1]:
        value = _load(root / path)
        assert list(validator.iter_errors(value)) == []
        counts = value["counts"]
        assert counts["practice_intelligence_version_row_count"] == (
            counts["active_release_intelligence_version_count"]
            + counts["historical_intelligence_version_count"]
        )
        assert counts["playbook_version_row_count"] == (
            counts["active_release_playbook_count"] + counts["historical_playbook_count"]
        )
        assert counts["logical_gap_identity_count"] == (
            counts["active_gap_identity_count"] + counts["closed_gap_identity_count"]
        )
    for item in registry["fixtures"]["invalid"]:
        invalid_validator = Draft202012Validator(
            schemas[item["schema_id"]], format_checker=FormatChecker()
        )
        assert list(invalid_validator.iter_errors(_load(root / item["path"])))
    for item in registry["fixtures"]["schema_specific"]:
        schema_validator = Draft202012Validator(
            schemas[item["schema_id"]], format_checker=FormatChecker()
        )
        assert list(schema_validator.iter_errors(_load(root / item["valid"]))) == []
        assert list(schema_validator.iter_errors(_load(root / item["invalid"])))


def test_readiness_and_empty_rule_registry_semantics_are_explicit(repository_root: Path) -> None:
    fixture = _load(
        repository_root / "contracts/v2.2/fixtures/valid/memory-integrity-counters.json"
    )
    assert fixture["module_participation_status"] == "READY_FOR_INTEGRITY_CYCLE"
    assert fixture["rule_registry"] == {
        "rule_version_count": 0,
        "infrastructure_ready": True,
        "operational_rule_coverage": False,
    }
    assert fixture["product_ready"] is False
    readiness = load_module_readiness_manifest(
        repository_root / "contracts/v2.2/fixtures/valid/module-readiness-manifest.json"
    )
    rule_registry = next(
        item for item in readiness.modules if item.module_id == "knowledge.rule-registry"
    )
    assert rule_registry.qualification_status is ReadinessStatus.READY_FOR_INTEGRITY_CYCLE
    assert "operational_rule_coverage=false" in rule_registry.implemented_status
    assert readiness.product_ready is False


def test_current_capability_ids_are_canonical_and_distribution_is_fixed(
    repository_root: Path,
) -> None:
    current = _load(repository_root / "contracts/v2.2/fixtures/valid/capability-current-state.json")
    base = _load(repository_root / "contracts/v2.0/fixtures/valid/product-capability-registry.json")
    schema = _load(repository_root / "contracts/v2.2/schemas/capability-current-state.schema.json")
    assert (
        list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(current))
        == []
    )
    stable_ids = {item["capability_id"] for item in base["capabilities"]}
    assert set(current["capability_ready_ids"]) <= stable_ids
    assert sum(current["distribution"].values()) == current["denominator"] == len(stable_ids)
    assert current["distribution"] == {
        "CAPABILITY_READY": 16,
        "PARTIAL": 10,
        "FOUNDATION_ONLY": 45,
        "CONTRACT_ONLY": 64,
        "NOT_IMPLEMENTED": 7,
    }
