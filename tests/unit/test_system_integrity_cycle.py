from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from asd_kontur.integrity.models import (
    IntegrityFailure,
    canonical_digest,
    load_module_readiness_manifest,
    write_immutable_json,
)
from asd_kontur.integrity.qualification import execute_four_mode_fixture
from asd_kontur.integrity.qwen import SMOKE_CONTRACT, smoke_context, validate_response
from asd_kontur.integrity.runner import _import_production_packages


def test_integrity_contract_pack_fingerprint_and_fixtures() -> None:
    root = Path("contracts/v1.9")
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    schema_path = root / registry["schemas"][0]["path"]
    assert registry["schemas"][0]["digest"] == (
        "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifest = json.loads((root / "fixtures/manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        value = json.loads((root / "fixtures" / fixture["path"]).read_text(encoding="utf-8"))
        fragment = schema
        for part in fixture["schema_pointer"].strip("/").split("/"):
            fragment = fragment[part]
        valid = not tuple(validator.evolve(schema=fragment).iter_errors(value))
        assert valid is (fixture["expected"] == "valid"), fixture["path"]


def test_module_readiness_manifest_is_unique_executable_and_product_not_ready() -> None:
    manifest = load_module_readiness_manifest(
        Path("contracts/v1.9/fixtures/valid/module-readiness-manifest.json")
    )
    assert len(manifest.modules) >= 25
    assert not manifest.product_ready
    assert manifest.semantic_fingerprint.startswith("sha256:")
    assert {item.module_id for item in manifest.modules} >= {
        "knowledge.practice-intelligence",
        "knowledge.ntd-memory",
        "knowledge.rule-registry",
        "construction.unified-harness",
        "mode.tender",
        "mode.support",
        "mode.audit",
        "mode.restoration",
    }


def test_immutable_receipt_rejects_replacement(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    write_immutable_json(path, {"status": "pass"})
    with pytest.raises(FileExistsError):
        write_immutable_json(path, {"status": "rewritten"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "pass"}


def test_canonical_digest_accepts_domain_identifiers_without_repr_instability() -> None:
    identity = UUID("018ff001-0000-7000-8000-000000000001")
    assert canonical_digest({"identity": identity}) == canonical_digest({"identity": str(identity)})


def test_four_mode_qualification_fixture_is_deterministic() -> None:
    first = execute_four_mode_fixture()
    second = execute_four_mode_fixture()
    assert first == second
    assert first["automatic_rule_promotion"] is False
    assert set(first["knowledge_gap_codes"]) == {"official_ntd_subset_empty"}
    assert len(set(first["mode_output_fingerprints"].values())) == 4


def test_production_import_qualification_supplies_explicit_runtime_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = (
        "ASD_DATABASE_URL",
        "ASD_LIFECYCLE_DATABASE_URL",
        "ASD_WORKER_DATABASE_URL",
        "ASD_DESTRUCTION_DATABASE_URL",
        "ASD_OBJECT_STORE_ROOT",
        "ASD_ARCHIVE_STORE_ROOT",
        "ASD_AUTH_AUDIT_PEPPER",
    )
    for name in required:
        monkeypatch.delenv(name, raising=False)

    imported = _import_production_packages("postgresql+psycopg://localhost/postgres")

    assert "asd_kontur.web_app.runtime" in imported
    assert all(name not in __import__("os").environ for name in required)


def test_qwen_smoke_validator_accepts_exact_structure_and_rejects_repair() -> None:
    context = smoke_context()
    value = {
        "contract": SMOKE_CONTRACT,
        "context_pack_fingerprint": context["context_pack_fingerprint"],
        "matrix_fingerprint": context["matrix_fingerprint"],
        "referenced_identities": sorted(
            identity
            for identities in context["authority_layers"].values()
            for identity in identities
        ),
        "authority_layers": context["authority_layers"],
        "evidence_locators": context["evidence_locators"],
        "calculated_status": "knowledge_incomplete",
        "knowledge_gaps": ["official_ntd_subset_empty"],
        "fabrication_prohibited": True,
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert canonical_digest(validate_response(raw, context)) == canonical_digest(value)
    with pytest.raises(IntegrityFailure) as malformed:
        validate_response(f"```json\n{raw}\n```", context)
    assert malformed.value.code == "MODEL_RESPONSE_INTEGRITY_FAILED"
    value["authority_layers"]["normative_authority"] = ["invented-provision"]
    with pytest.raises(IntegrityFailure) as fabricated:
        validate_response(json.dumps(value, separators=(",", ":")), context)
    assert fabricated.value.code == "MODEL_STRUCTURAL_VALIDATION_FAILED"
