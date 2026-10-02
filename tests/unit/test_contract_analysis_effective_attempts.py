from asd_kontur.tender.contract_analysis_view import (
    _effective_profile_jobs,
    _latest_job_attempts,
    _preferred_contract_results,
)


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


def test_current_contract_profile_switches_atomically_across_changed_batch_boundaries() -> None:
    results = [
        {
            "job_id": "old-batch-1",
            "source_version_id": "source-a",
            "batch_ordinal": 1,
            "profile_version": "qwen-contract-analysis-v7",
        },
        {
            "job_id": "old-batch-2",
            "source_version_id": "source-a",
            "batch_ordinal": 2,
            "profile_version": "qwen-contract-analysis-v7",
        },
        {
            "job_id": "new-batch-1",
            "source_version_id": "source-a",
            "batch_ordinal": 1,
            "profile_version": "qwen-contract-analysis-v8",
        },
    ]

    while_incomplete = _preferred_contract_results(results, current_run_complete=False)
    after_completion = _preferred_contract_results(results, current_run_complete=True)

    assert {(item["batch_ordinal"], item["job_id"]) for item in while_incomplete} == {
        (1, "old-batch-1"),
        (2, "old-batch-2"),
    }
    assert [(item["batch_ordinal"], item["job_id"]) for item in after_completion] == [
        (1, "new-batch-1")
    ]


def test_new_contract_without_prior_profile_remains_progressive() -> None:
    current = [
        {
            "job_id": "new-batch-1",
            "source_version_id": "source-a",
            "batch_ordinal": 1,
            "profile_version": "qwen-contract-analysis-v8",
        }
    ]

    assert _preferred_contract_results(current, current_run_complete=False) == current


def test_contract_transition_retains_prior_progress_until_current_run_starts() -> None:
    prior = [
        {
            "job_id": "old-running",
            "input_digest": "sha256:old",
            "state": "running",
            "profile_version": "qwen-contract-analysis-v7",
        }
    ]
    current = {
        "job_id": "new-queued",
        "input_digest": "sha256:new",
        "state": "queued",
        "profile_version": "qwen-contract-analysis-v8",
    }

    assert [job["job_id"] for job in _effective_profile_jobs(prior)] == ["old-running"]
    assert [job["job_id"] for job in _effective_profile_jobs([current, *prior])] == ["new-queued"]
