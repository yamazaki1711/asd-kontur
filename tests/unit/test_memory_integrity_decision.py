from pathlib import Path

from asd_kontur.integrity.decisions import load_integrity_decision


def test_superseding_decision_withdraws_semantic_pass_without_rewriting_series() -> None:
    decision = load_integrity_decision(
        Path("docs/verification/MEMORY_INTEGRITY_SUPERSEDING_DECISION_01.json")
    )
    assert decision["prior_series_id"] == "SIC01-20260825-R1"
    assert decision["effective_system_integrity_status"] == "PARTIAL / DATA_DEFECT"
    assert decision["historical_series_preserved"] is True
    assert decision["requires_fresh_three_cycle_series"] is True
    assert decision["product_ready"] is False
