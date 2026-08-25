from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "contracts" / "v2.1"


def test_product_spine_contract_pack_registry_and_fixture() -> None:
    registry = json.loads((PACK / "registry.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (PACK / "schemas" / "spine-contract-fixture.schema.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (PACK / "fixtures" / "valid" / "product-spine-contract-fixture.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)
    assert len(registry["contract_keys"]) == len(set(registry["contract_keys"])) == 14
    assert fixture["knowledge_status"]["memory_data_defect"] is True
    assert fixture["knowledge_status"]["knowledge_ready"] is False
    assert fixture["capability_status"]["trial_ready"] is False
    assert fixture["capability_status"]["oks_ready"] is False
    assert fixture["capability_status"]["product_ready"] is False
    decisions = fixture["capability_readiness_delta"]
    assert len(decisions) == len({item["capability_id"] for item in decisions}) == 25
    assert all(item["current"] in {"PARTIAL", "CAPABILITY_READY"} for item in decisions)
    scale_results = fixture["scale_qualification_results"]
    assert {item["accepted"] for item in scale_results} == {1000, 5000, 10000}
    assert all(item["jobs"] == item["accepted"] * 5 for item in scale_results)
    assert all(item["lost_jobs"] == item["rejected"] == 0 for item in scale_results)
    assert all(item["threshold_status"] == "UNSET_MEASURED_ONLY" for item in scale_results)
    readiness = fixture["effective_registry_readiness"]
    assert (
        sum(value for key, value in readiness.items() if key != "denominator")
        == readiness["denominator"]
    )
    assert readiness["MODE_READY"] == readiness["TRIAL_READY"] == readiness["PRODUCT_READY"] == 0


def test_openapi_digest_and_required_resource_groups_are_pinned() -> None:
    registry = json.loads((PACK / "registry.json").read_text(encoding="utf-8"))
    path = PACK / registry["openapi"]["path"]
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == registry["openapi"]["digest"]
    specification = json.loads(path.read_text(encoding="utf-8"))
    paths = set(specification["paths"])
    for prefix in (
        "/api/v1/session",
        "/api/v1/capabilities",
        "/api/v1/workspaces",
        "/api/v1/platform/knowledge-status",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    ):
        assert any(item == prefix or item.startswith(f"{prefix}/") for item in paths)
