from asd_kontur.tender.contract_analysis_view import (
    _effective_profile_jobs,
    _is_docx_source,
    _latest_job_attempts,
    _preferred_contract_results,
    _stable_source_page,
    _uncovered_contract_sources,
)


def test_docx_native_locator_is_not_reported_as_a_printed_page() -> None:
    docx = {
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "safe_display_name": "Contract.docx",
    }
    fallback_docx = {
        "media_type": "application/octet-stream",
        "safe_display_name": "Contract.DOCX",
    }
    pdf = {"media_type": "application/pdf", "safe_display_name": "Contract.pdf"}

    assert _stable_source_page(_is_docx_source(docx), 1) is None
    assert _stable_source_page(_is_docx_source(fallback_docx), 7) is None
    assert _stable_source_page(_is_docx_source(pdf), 7) == 7


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
            "profile_version": "qwen-contract-analysis-v9",
        },
        {
            "job_id": "old-batch-2",
            "source_version_id": "source-a",
            "batch_ordinal": 2,
            "profile_version": "qwen-contract-analysis-v9",
        },
        {
            "job_id": "new-batch-1",
            "source_version_id": "source-a",
            "batch_ordinal": 1,
            "profile_version": "qwen-contract-analysis-v10",
        },
    ]

    while_incomplete = _preferred_contract_results(results, current_run_terminal=False)
    after_terminal = _preferred_contract_results(results, current_run_terminal=True)

    assert {(item["batch_ordinal"], item["job_id"]) for item in while_incomplete} == {
        (1, "old-batch-1"),
        (2, "old-batch-2"),
    }
    assert [(item["batch_ordinal"], item["job_id"]) for item in after_terminal] == [
        (1, "new-batch-1")
    ]


def test_new_contract_without_prior_profile_remains_progressive() -> None:
    current = [
        {
            "job_id": "new-batch-1",
            "source_version_id": "source-a",
            "batch_ordinal": 1,
            "profile_version": "qwen-contract-analysis-v10",
        }
    ]

    assert _preferred_contract_results(current, current_run_terminal=False) == current


def test_contract_transition_retains_prior_progress_until_current_run_starts() -> None:
    prior = [
        {
            "job_id": "old-running",
            "input_digest": "sha256:old",
            "state": "running",
            "profile_version": "qwen-contract-analysis-v9",
        }
    ]
    current = {
        "job_id": "new-queued",
        "input_digest": "sha256:new",
        "state": "queued",
        "profile_version": "qwen-contract-analysis-v10",
    }

    assert [job["job_id"] for job in _effective_profile_jobs(prior)] == ["old-running"]
    assert [job["job_id"] for job in _effective_profile_jobs([current, *prior])] == ["new-queued"]


def test_contract_completion_requires_all_readable_source_segments() -> None:
    sources = {"source-a": "Contract", "source-b": "Attachment"}
    elements = [
        {"source_version_id": "source-a", "source_locator_id": "a-1", "text_length": 10},
        {"source_version_id": "source-a", "source_locator_id": "a-2", "text_length": 4},
        {"source_version_id": "source-b", "source_locator_id": "b-1", "text_length": 3},
    ]
    accepted = [
        {
            "source_version_id": "source-a",
            "input_manifest": {
                "source_segments": [
                    {"source_locator_id": "a-1", "start": 0, "end": 5},
                    {"source_locator_id": "a-2", "start": 0, "end": 4},
                ]
            },
        }
    ]
    assert _uncovered_contract_sources(sources, readable_elements=elements, results=accepted) == [
        "source-a",
        "source-b",
    ]

    accepted.extend(
        [
            {
                "source_version_id": "source-a",
                "input_manifest": {
                    "source_segments": [{"source_locator_id": "a-1", "start": 5, "end": 10}]
                },
            },
            {
                "source_version_id": "source-b",
                "input_manifest": {
                    "source_segments": [{"source_locator_id": "b-1", "start": 0, "end": 3}]
                },
            },
        ]
    )
    assert _uncovered_contract_sources(sources, readable_elements=elements, results=accepted) == []


def test_contract_completion_rejects_unknown_or_unversioned_segment_coverage() -> None:
    sources = {"source-a": "Contract"}
    elements = [{"source_version_id": "source-a", "source_locator_id": "a-1", "text_length": 8}]
    results = [
        {"source_version_id": "source-a", "input_manifest": {"source_locator_ids": ["a-1"]}},
        {
            "source_version_id": "source-a",
            "input_manifest": {
                "source_segments": [{"source_locator_id": "a-1", "start": 0, "end": 6}]
            },
        },
    ]
    assert _uncovered_contract_sources(sources, readable_elements=elements, results=results) == [
        "source-a"
    ]
