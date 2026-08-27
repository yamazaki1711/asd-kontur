from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_field_android_client_is_additive_not_implemented_product_blocker(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.3"
    schema = _load(root / "schemas" / "capability-registry-extension.schema.json")
    fixture = _load(root / "fixtures" / "valid" / "capability-registry-extension.json")
    Draft202012Validator(schema).validate(fixture)
    assert fixture["base_denominator"] == 142
    assert fixture["denominator"] == 143
    assert sum(fixture["readiness_distribution"].values()) == fixture["denominator"]
    capability = fixture["additions"][0]
    assert capability["capability_id"] == "field.secure-android-client"
    assert capability["current_readiness"] == "NOT_IMPLEMENTED"
    assert capability["legacy_decision"] == "USE_AS_REFERENCE_ONLY"
    assert capability["target_implementation"] == "REIMPLEMENT_FROM_SEMANTICS"
    assert capability["authentication_architecture"] == "UNDECIDED"
    assert capability["architecture_security_adr_required"] is True
    assert capability["product_modes"] == ["Support", "Audit", "Restoration"]
    assert capability["issue_url"].endswith("/issues/24")
    assert capability["required_for_product"] is True

    record = (repository_root / "docs/implementation/FIELD_ANDROID_CLIENT_01.md").read_text(
        encoding="utf-8"
    )
    legacy_matrix = (
        repository_root / "docs/architecture/LEGACY_COMPONENT_DECISION_MATRIX_v1.md"
    ).read_text(encoding="utf-8")
    assert "authentication_architecture = UNDECIDED" in record
    assert "OperatorAssignmentVersion" in record
    assert "PWA offline ledger first" not in legacy_matrix
    assert "target `REIMPLEMENT_FROM_SEMANTICS`" in legacy_matrix
