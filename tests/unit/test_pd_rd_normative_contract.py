from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator

from asd_kontur.ntd.pd_rd import evaluate_pd_rd_requirements


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_pack_v2_3_schema_digests_are_exact(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v2.3"
    registry = _load(root / "registry.json")
    for entry in registry["schemas"]:
        digest = "sha256:" + hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest()
        assert digest == entry["digest"]


def test_pd_rd_normative_profile_contract_preserves_fail_closed_gap(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.3"
    schema = _load(root / "schemas" / "pd-rd-normative-profile.schema.json")
    fixture = _load(root / "fixtures" / "valid" / "pd-rd-normative-profile-gap.json")
    Draft202012Validator(schema).validate(fixture)
    assert fixture["completeness_status"] == "blocked"
    assert fixture["normative_edition_ids"] == []
    assert fixture["rule_version_ids"] == []
    assert {gap["code"] for gap in fixture["gaps"]} == {
        "VERIFIED_PD_RD_NTD_UNAVAILABLE",
        "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE",
        "NORMATIVE_APPLICABILITY_INPUT_MISSING",
    }


def test_pd_rd_profile_evaluator_is_order_independent_and_denominator_bound() -> None:
    def row(identity: int, section: str) -> dict[str, Any]:
        token = f"{identity:012d}"
        return {
            "rule_version_id": UUID(f"00000000-0000-7000-8000-{token}"),
            "output_contract": {
                "requirement_kind": "pd_section",
                "section": section,
                "required": True,
            },
            "normative_edition_id": UUID(f"10000000-0000-7000-8000-{token}"),
            "official_catalog_url": "https://protect.gost.ru/gost/details/"
            f"00000000-0000-0000-0000-{token}",
            "normative_provision_id": UUID(f"20000000-0000-7000-8000-{token}"),
            "provision_version": 1,
            "source_version_id": UUID(f"30000000-0000-7000-8000-{token}"),
            "structural_path": f"section/{section}",
            "content_digest": "sha256:" + f"{identity:064x}",
            "source_locator_id": UUID(f"40000000-0000-7000-8000-{token}"),
            "locator_value": f"page:1/section:{section}",
            "required_inputs": ["object_kind"],
            "predicate": {"object_kind": "non_linear"},
        }

    rows = (row(1, "1"), row(2, "2"))
    arguments = {
        "dimensions": {"object_kind": "non_linear"},
        "applicable_on": date(2026, 8, 26),
        "input_fingerprint": "sha256:" + "a" * 64,
        "corpus_denominator": {
            "spds_members": 109,
            "manifest_fingerprint": "sha256:" + "b" * 64,
        },
    }
    first = evaluate_pd_rd_requirements(rows=rows, **arguments)
    reordered = evaluate_pd_rd_requirements(rows=tuple(reversed(rows)), **arguments)
    assert first == reordered
    changed_denominator = evaluate_pd_rd_requirements(
        rows=rows,
        **{
            **arguments,
            "corpus_denominator": {
                "spds_members": 110,
                "manifest_fingerprint": "sha256:" + "c" * 64,
            },
        },
    )
    assert changed_denominator.semantic_fingerprint != first.semantic_fingerprint
