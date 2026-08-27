from asd_kontur.ntd.processing_jobs import terminal_state_for_failure


def test_outcome_unknown_external_failures_require_reconciliation() -> None:
    assert terminal_state_for_failure("POLZA_TIMEOUT") == "reconciliation_required"
    assert terminal_state_for_failure("POLZA_CONNECTION_ERROR") == "reconciliation_required"
    assert terminal_state_for_failure("POLZA_REGION_INVALID") == "failed"
