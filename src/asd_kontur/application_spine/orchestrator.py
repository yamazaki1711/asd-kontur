"""Supervised, durable project-processing reconciliation.

The orchestrator never interprets project content.  It repairs missing durable
work from persisted state and leaves execution to the existing document/Qwen
worker.
"""

from __future__ import annotations

import json
import signal
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from asd_kontur.domain import uuid7

from .postgres import SpinePersistenceError, SpinePostgresRepository


@dataclass(frozen=True, slots=True)
class OrchestrationSweep:
    observed_at: str
    scopes: int
    dependency_failures_marked: int
    dependency_replacements_queued: int
    transient_retries_queued: int
    superseded_reconciliations: int
    project_models_ensured: int
    work_batches_queued: int
    scope_failures: tuple[dict[str, str], ...]

    @property
    def changed(self) -> bool:
        return any(
            (
                self.dependency_failures_marked,
                self.dependency_replacements_queued,
                self.transient_retries_queued,
                self.superseded_reconciliations,
                self.work_batches_queued,
            )
        )


class ProjectOrchestrator:
    """Low-frequency safety net for all active project workspaces."""

    def __init__(
        self,
        repository: SpinePostgresRepository,
        *,
        interval_seconds: float = 30.0,
        scope_limit: int = 16,
    ) -> None:
        if interval_seconds < 1:
            raise ValueError("project orchestrator interval must be at least one second")
        if not 1 <= scope_limit <= 64:
            raise ValueError("project orchestrator scope limit is invalid")
        self._repository = repository
        self._interval_seconds = interval_seconds
        self._scope_limit = scope_limit
        self._stopping = False

    def request_stop(self) -> None:
        self._stopping = True

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())

    def run_once(self) -> OrchestrationSweep:
        dependency_failures = self._repository.reconcile_unclaimable_jobs()
        dependency_replacements = self._repository.recover_dependency_terminal_failures()
        scopes = self._repository.autonomous_project_processing_scopes(limit=self._scope_limit)
        retries = 0
        superseded = 0
        models = 0
        work_batches = 0
        failures: list[dict[str, str]] = []
        for organization_id, workspace_id, owner_identity_id, _last_progress_at in scopes:
            try:
                self._repository.reconcile_expired_exhausted_jobs(
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                )
                retries += len(
                    self._repository.schedule_autonomous_retry_replacements(
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                    )
                )
                superseded += self._repository.supersede_redundant_project_reconciliations(
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                )
                self._repository.start_project_understanding(
                    owner_identity_id=owner_identity_id,
                    workspace_id=workspace_id,
                    correlation_id=uuid7(),
                    _resolved_organization_id=organization_id,
                )
                models += 1
                work_batches += len(
                    self._repository.refill_workspace_project_work_reconciliation_if_idle(
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        correlation_id=uuid7(),
                    )
                )
            except SpinePersistenceError as exc:
                failures.append(
                    {
                        "workspace_id": str(workspace_id),
                        "failure_code": str(exc),
                    }
                )
        # Successful transient replacements may have appeared while this sweep
        # was running.  A second bounded recovery pass reconnects their direct
        # descendants without waiting for the next periodic interval.
        dependency_replacements += self._repository.recover_dependency_terminal_failures()
        return OrchestrationSweep(
            observed_at=datetime.now(UTC).isoformat(),
            scopes=len(scopes),
            dependency_failures_marked=dependency_failures,
            dependency_replacements_queued=dependency_replacements,
            transient_retries_queued=retries,
            superseded_reconciliations=superseded,
            project_models_ensured=models,
            work_batches_queued=work_batches,
            scope_failures=tuple(failures),
        )

    def run_forever(self) -> None:
        self.install_signal_handlers()
        while not self._stopping:
            try:
                result = self.run_once()
            except Exception as exc:  # keep the supervised safety loop alive
                print(
                    json.dumps(
                        {
                            "observed_at": datetime.now(UTC).isoformat(),
                            "event": "project_orchestrator_sweep_failed",
                            "exception_type": type(exc).__name__,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            else:
                if result.changed or result.scope_failures:
                    print(json.dumps(asdict(result), sort_keys=True), flush=True)
            deadline = time.monotonic() + self._interval_seconds
            while not self._stopping and time.monotonic() < deadline:
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
