from __future__ import annotations

import csv
from io import StringIO

from asd_kontur.restoration import build_recovery_plan, render_recovery_plan_csv


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
                    "generated_candidate_ids": ["candidate-a"],
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
    assert plan["recoverable_actions"][0]["generated_candidate_ids"] == ["candidate-a"]
    assert plan["recoverable_actions"][0]["fabrication_prohibited"] is True
    assert plan["blocked_actions"][0]["action"] == "collect_missing_source_evidence"
    assert "actual document" in plan["blocked_actions"][0]["required_input"]
    assert plan["blocked_actions"][0]["fabrication_prohibited"] is True


def test_recovery_plan_export_keeps_blocked_records_and_fabrication_boundary() -> None:
    content = render_recovery_plan_csv(
        {
            "status": "partial",
            "global_blockers": ["ID_PACKAGE_NOT_COMPLETE"],
            "recoverable_actions": [
                {
                    "item_key": "candidate-a",
                    "action": "review_candidate_against_available_evidence",
                    "generated_candidate_ids": ["candidate-a"],
                    "fabrication_prohibited": True,
                }
            ],
            "blocked_actions": [
                {
                    "item_key": "missing-a",
                    "action": "collect_missing_source_evidence",
                    "required_input": "actual test record",
                    "fabrication_prohibited": True,
                }
            ],
        }
    )

    rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert [(row["disposition"], row["item_key"]) for row in rows] == [
        ("recoverable", "candidate-a"),
        ("blocked", "missing-a"),
    ]
    assert rows[1]["required_input"] == "actual test record"
    assert rows[1]["fabrication_prohibited"] == "true"
    assert rows[1]["global_blockers"] == "ID_PACKAGE_NOT_COMPLETE"
    assert rows[0]["generated_candidate_ids"] == "candidate-a"
