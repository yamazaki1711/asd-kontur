from __future__ import annotations

import io
from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID

import pytest

from asd_kontur.application_spine.models import ClaimedJob, JobKind
from asd_kontur.application_spine.orchestrator import ProjectOrchestrator
from asd_kontur.application_spine.worker import (
    DeterministicJobFailure,
    DocumentWorker,
    RetryableJobFailure,
)
from asd_kontur.document_understanding.pipeline import UnderstandingStageFailure

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000001801")
WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000001802")


class _UnderstandingFailure:
    def __init__(self, code: str) -> None:
        self.code = code

    def execute(self, *_args: object) -> dict[str, object]:
        raise UnderstandingStageFailure(self.code)


def _semantic_job() -> ClaimedJob:
    return ClaimedJob(
        ORGANIZATION_ID,
        WORKSPACE_ID,
        UUID("018f5c3e-7b00-7000-8000-000000001803"),
        JobKind.WORK_QUANTITY_MATERIAL_EXTRACTION,
        {},
        "sha256:" + "1" * 64,
        1,
        1,
        "none",
    )


def test_local_model_outage_is_retryable_at_durable_job_boundary() -> None:
    worker = object.__new__(DocumentWorker)
    worker._understanding = _UnderstandingFailure("qwen_semantic_runtime_unavailable")
    worker._open_source = lambda _claimed: nullcontext(io.BytesIO())  # type: ignore[method-assign]

    with pytest.raises(RetryableJobFailure, match="qwen_semantic_runtime_unavailable"):
        worker._execute(_semantic_job())


def test_invalid_model_content_remains_a_bounded_terminal_failure() -> None:
    worker = object.__new__(DocumentWorker)
    worker._understanding = _UnderstandingFailure("qwen_semantic_response_invalid_locator")
    worker._open_source = lambda _claimed: nullcontext(io.BytesIO())  # type: ignore[method-assign]

    with pytest.raises(DeterministicJobFailure, match="qwen_semantic_response_invalid_locator"):
        worker._execute(_semantic_job())


def test_orchestrator_repairs_dependencies_and_ensures_successors() -> None:
    class Repository:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def reconcile_unclaimable_jobs(self) -> int:
            self.calls.append("mark_blocked")
            return 120

        def recover_dependency_terminal_failures(self) -> int:
            self.calls.append("recover_dependencies")
            return 2 if self.calls.count("recover_dependencies") == 1 else 1

        def autonomous_project_processing_scopes(self, **_kwargs: object):
            return ((ORGANIZATION_ID, WORKSPACE_ID, "owner", datetime.now(UTC)),)

        def reconcile_expired_exhausted_jobs(self, **_kwargs: object) -> int:
            self.calls.append("recover_leases")
            return 0

        def schedule_autonomous_retry_replacements(self, **_kwargs: object):
            self.calls.append("retry_transient")
            return (UUID("018f5c3e-7b00-7000-8000-000000001804"),)

        def supersede_redundant_project_reconciliations(self, **_kwargs: object) -> int:
            self.calls.append("supersede_reconciliations")
            return 7

        def start_project_understanding(self, **kwargs: object) -> object:
            assert kwargs["_resolved_organization_id"] == ORGANIZATION_ID
            self.calls.append("ensure_project_model")
            return object()

        def refill_workspace_project_work_reconciliation_if_idle(self, **_kwargs: object):
            self.calls.append("refill_work")
            return (object(), object())

    repository = Repository()
    result = ProjectOrchestrator(repository, interval_seconds=30).run_once()  # type: ignore[arg-type]

    assert result.dependency_failures_marked == 120
    assert result.dependency_replacements_queued == 3
    assert result.transient_retries_queued == 1
    assert result.superseded_reconciliations == 7
    assert result.work_batches_queued == 2
    assert repository.calls == [
        "mark_blocked",
        "recover_dependencies",
        "recover_leases",
        "retry_transient",
        "supersede_reconciliations",
        "ensure_project_model",
        "refill_work",
        "recover_dependencies",
    ]
