"""Incoming inspection remains a guarded preflight, not material admission."""

from __future__ import annotations

import pytest

from asd_kontur.support.incoming_inspection import (
    INCOMING_CHECKS,
    evaluate_incoming_inspection,
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
        "quality_documents", "visual_condition",
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
    assert evaluate_incoming_inspection(checks)["fingerprint"] == (
        evaluate_incoming_inspection(list(reversed(checks)))["fingerprint"]
    )
