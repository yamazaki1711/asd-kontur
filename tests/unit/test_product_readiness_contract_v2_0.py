from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from asd_kontur.product_readiness import (
    CapabilityRegistryError,
    load_capability_registry,
    validate_capability_registry,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "v2.0"


def _requirements() -> tuple[frozenset[str], frozenset[str]]:
    document = json.loads(
        (CONTRACT_ROOT / "required-capabilities.json").read_text(encoding="utf-8")
    )
    return frozenset(document["required_capability_ids"]), frozenset(document["required_planes"])


def _validate(registry: dict[str, Any]) -> None:
    capability_ids, planes = _requirements()
    validate_capability_registry(
        registry,
        required_capability_ids=capability_ids,
        required_planes=planes,
    )


def _apply_mutation(registry: dict[str, Any], fixture: dict[str, str]) -> None:
    mutation = fixture["mutation"]
    if mutation == "remove_capability":
        registry["capabilities"] = [
            item
            for item in registry["capabilities"]
            if item["capability_id"] != fixture["capability_id"]
        ]
    elif mutation == "capability_ready_without_surface":
        capability = next(
            item
            for item in registry["capabilities"]
            if item["capability_id"] == fixture["capability_id"]
        )
        capability["current_readiness"] = "CAPABILITY_READY"
    elif mutation == "mode_ready_without_e2e":
        decision = registry["readiness_decisions"]["modes"][fixture["mode"]]
        decision.update(ready=True, decision_id="MODE-DECISION-invalid")
        decision["e2e_evidence"] = ["none"]
        decision["output_evidence"] = ["not_run"]
    elif mutation == "trial_ready":
        registry["readiness_decisions"]["trial"].update(
            ready=True,
            decision_id="TRIAL-DECISION-invalid",
            scale_qualification_evidence=["unproven"],
        )
    elif mutation == "product_ready":
        registry["readiness_decisions"]["product"].update(
            ready=True,
            decision_id="PRODUCT-DECISION-invalid",
            product_result_evidence=[True, True, True],
        )
    elif mutation == "pass_without_denominator":
        registry["claims"][0].update(outcome="PASS", denominator=0, evidence_refs=[])
    elif mutation == "real_oks_without_trial":
        registry["readiness_decisions"]["real_oks_admission"].update(proposed=True, allowed=True)
    else:  # pragma: no cover - fixture manifest is closed by this assertion
        raise AssertionError(f"unknown mutation {mutation}")


def test_complete_registry_is_valid_and_currently_not_product_ready() -> None:
    registry = load_capability_registry(CONTRACT_ROOT)
    result = validate_capability_registry(
        registry,
        required_capability_ids=_requirements()[0],
        required_planes=_requirements()[1],
    )

    assert result.capability_count == 142
    assert result.plane_count == 13
    assert result.readiness_counts == {
        "NOT_IMPLEMENTED": 21,
        "CONTRACT_ONLY": 70,
        "FOUNDATION_ONLY": 50,
        "PARTIAL": 1,
        "CAPABILITY_READY": 0,
        "MODE_READY": 0,
        "TRIAL_READY": 0,
        "PRODUCT_READY": 0,
    }
    decisions = registry["readiness_decisions"]
    assert decisions["trial"]["ready"] is False
    assert decisions["real_oks_admission"]["allowed"] is False
    assert decisions["oks_ready"] is False
    assert decisions["product"]["ready"] is False
    assert result.blocking_capability_ids


def test_contract_registry_pins_schema_and_all_fixtures_exist() -> None:
    registry = json.loads((CONTRACT_ROOT / "registry.json").read_text(encoding="utf-8"))
    schema_registration = registry["schemas"][0]
    schema_path = CONTRACT_ROOT / schema_registration["path"]
    assert schema_registration["digest"] == (
        "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    )
    fixture_manifest = json.loads(
        (CONTRACT_ROOT / registry["fixtures"]["manifest"]).read_text(encoding="utf-8")
    )
    registered = {item["path"] for item in registry["fixtures"]["invalid"]} | set(
        registry["fixtures"]["valid"]
    )
    manifested = {
        f"fixtures/{path}" for key in ("valid", "invalid") for path in fixture_manifest[key]
    }
    assert registered == manifested
    assert all((CONTRACT_ROOT / path).is_file() for path in registered)


@pytest.mark.parametrize(
    "path",
    sorted((CONTRACT_ROOT / "fixtures" / "invalid").glob("*.json")),
    ids=lambda path: path.stem,
)
def test_readiness_mutations_fail_closed(path: Path) -> None:
    registry = copy.deepcopy(load_capability_registry(CONTRACT_ROOT))
    fixture = json.loads(path.read_text(encoding="utf-8"))
    _apply_mutation(registry, fixture)

    with pytest.raises(CapabilityRegistryError, match=fixture["expected_error"]):
        _validate(registry)
