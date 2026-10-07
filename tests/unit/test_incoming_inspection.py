"""Incoming inspection remains a guarded preflight, not material admission."""

from __future__ import annotations

import csv
import io

import pytest

from asd_kontur.support.incoming_inspection import (
    INCOMING_CHECKS,
    evaluate_incoming_inspection,
    render_incoming_inspection_register,
)


def _checks(state: str = "passed") -> list[dict[str, str]]:
    return [
        {"key": key, "state": state, "basis": f"Evidence for {key}"}
        for key, _label, _kind in INCOMING_CHECKS
    ]


def test_all_eight_checks_only_prepare_authorized_review() -> None:
    result = evaluate_incoming_inspection(_checks())
    assert result["outcome"] == "ready_for_authorized_admission_review"
    assert result["checked_count"] == result["total_count"] == 8
    assert result["hold_for_use"] is True
    assert [row["kind"] for row in result["checks"]].count("physical") == 3


def test_failed_and_pending_checks_produce_specific_actions() -> None:
    checks = _checks()
    checks[0]["state"] = "failed"
    checks[3]["state"] = "pending"
    result = evaluate_incoming_inspection(checks)
    assert result["outcome"] == "nonconforming"
    assert {action["check_key"] for action in result["actions"]} == {
        "quality_documents",
        "visual_condition",
    }


def test_missing_evidence_or_missing_check_cannot_pass() -> None:
    checks = _checks()
    checks[2]["basis"] = ""
    assert evaluate_incoming_inspection(checks)["outcome"] == "incomplete"
    with pytest.raises(ValueError, match="check_set_invalid"):
        evaluate_incoming_inspection(checks[:-1])
    with pytest.raises(ValueError, match="duplicate_check"):
        evaluate_incoming_inspection([*checks, checks[0]])


def test_result_is_order_independent_and_project_independent() -> None:
    checks = _checks()
    assert (
        evaluate_incoming_inspection(checks)["fingerprint"]
        == (evaluate_incoming_inspection(list(reversed(checks)))["fingerprint"])
    )


def test_register_exports_all_checks_without_admission_or_csv_formulas() -> None:
    result = evaluate_incoming_inspection(_checks())
    content = render_incoming_inspection_register(
        [
            {
                "submitted_at": "2026-10-07T10:00:00Z",
                "material_name": '=HYPERLINK("bad")',
                "batch_reference": "batch-17",
                "result": result,
            }
        ]
    )
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 9
    assert {row[8] for row in rows[1:]} == {
        "Материал не допущен — требуется решение ответственного лица"
    }
    assert all(row[1].startswith("'=HYPERLINK") for row in rows[1:])


def test_register_rejects_result_that_claims_admission() -> None:
    result = evaluate_incoming_inspection(_checks())
    result["hold_for_use"] = False
    with pytest.raises(ValueError, match="result_invalid"):
        render_incoming_inspection_register([{"result": result}])
