from __future__ import annotations

from asd_kontur.restoration import build_recovery_plan


def test_recovery_plan_keeps_missing_evidence_blocked_and_candidates_reviewable() -> None:
    plan = build_recovery_plan(
        {
            "assessment_kind": "expected_vs_package_preflight",
            "matrix": {"matrix_id": "matrix", "version": 1},
            "package": {"id_package_id": "package", "version": 2},
            "gaps": ["ID_PACKAGE_NOT_COMPLETE"],
            "items": [
                {
                    "item_key": "scope-a:requirement-a:v1",
                    "work_package_id": "scope-a",
                    "document_requirement_id": "requirement-a",
                    "document_requirement_version": 1,
                    "document_type": "support.aosr",
                    "preflight_state": "generated_candidate",
                    "evidence_refs": ["project:source-a"],
                    "gaps": ["GENERATED_CANDIDATE_REQUIRES_AUDIT"],
                },
                {
                    "item_key": "scope-b:requirement-b:v1",
                    "work_package_id": "scope-b",
                    "document_requirement_id": "requirement-b",
                    "document_requirement_version": 1,
                    "document_type": "support.aosr",
                    "preflight_state": "missing",
                    "evidence_refs": ["rule:requirement-b"],
                    "gaps": ["REQUIRED_DOCUMENT_NOT_IN_PACKAGE"],
                },
            ],
        }
    )

    assert plan["status"] == "partial"
    assert plan["recoverable_actions"][0]["action"] == "review_candidate_against_available_evidence"
    assert plan["recoverable_actions"][0]["fabrication_prohibited"] is True
    assert plan["blocked_actions"][0]["action"] == "collect_missing_source_evidence"
    assert "actual document" in plan["blocked_actions"][0]["required_input"]
    assert plan["blocked_actions"][0]["fabrication_prohibited"] is True
