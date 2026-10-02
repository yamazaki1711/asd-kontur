from asd_kontur.tender.contract_analysis_view import _latest_job_attempts


def test_latest_contract_attempt_replaces_historical_failure_without_hiding_other_input() -> None:
    jobs = [
        {"job_id": "replacement", "input_digest": "sha256:a", "state": "succeeded"},
        {"job_id": "other", "input_digest": "sha256:b", "state": "queued"},
        {
            "job_id": "historical-failure",
            "input_digest": "sha256:a",
            "state": "reconciliation_required",
        },
    ]

    effective = _latest_job_attempts(jobs)

    assert [job["job_id"] for job in effective] == ["replacement", "other"]
