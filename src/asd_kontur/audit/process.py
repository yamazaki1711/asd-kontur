"""Typed command/state semantics for shared corpus intake and Audit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from asd_kontur.harness.models import digest_of


class AuditCommandType(StrEnum):
    START_COLLECTION = "StartCollectionMission"
    RECORD_INSPECTION = "RecordPhysicalObjectInspection"
    APPROVE_PROCESSING_PLAN = "ApproveProcessingPlan"
    RECONCILE_CORPUS = "ReconcileCorpus"
    PUBLISH_CORPUS_SNAPSHOT = "PublishCorpusSnapshot"
    START_AUDIT = "StartAudit"
    EVALUATE_DOCUMENT_DELTA = "EvaluateDocumentDelta"
    EVALUATE_CAUSAL_DELTA = "EvaluateCausalReadinessDelta"
    EVALUATE_PACKAGE_READINESS = "EvaluatePackageReadiness"
    ISSUE_ACTION_REQUEST = "IssueActionRequest"
    RECLASSIFY_DOCUMENT = "ReclassifyDocument"
    FINALIZE_AUDIT_REPORT = "FinalizeAuditReport"


class ProcessState(StrEnum):
    REQUESTED = "requested"
    COLLECTING = "collecting"
    RECONCILING = "reconciling"
    SNAPSHOTTED = "snapshotted"
    EVALUATING = "evaluating"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class AuditCommand:
    command_id: UUID
    command_type: AuditCommandType
    aggregate_id: UUID
    expected_revision: int
    idempotency_key: str
    actor_identity_id: str
    capability: str
    correlation_id: UUID
    causation_id: UUID
    payload_digest: str

    @property
    def semantic_digest(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    accepted: bool
    revision: int
    state: ProcessState
    outcome_code: str
    event_name: str | None


_TRANSITIONS: dict[tuple[ProcessState, AuditCommandType], tuple[ProcessState, str]] = {
    (ProcessState.REQUESTED, AuditCommandType.START_COLLECTION): (
        ProcessState.COLLECTING,
        "CollectionMissionStarted",
    ),
    (ProcessState.COLLECTING, AuditCommandType.RECORD_INSPECTION): (
        ProcessState.COLLECTING,
        "PhysicalObjectInspected",
    ),
    (ProcessState.COLLECTING, AuditCommandType.APPROVE_PROCESSING_PLAN): (
        ProcessState.COLLECTING,
        "ProcessingPlanApproved",
    ),
    (ProcessState.COLLECTING, AuditCommandType.RECONCILE_CORPUS): (
        ProcessState.RECONCILING,
        "CorpusReconciliationStarted",
    ),
    (ProcessState.RECONCILING, AuditCommandType.PUBLISH_CORPUS_SNAPSHOT): (
        ProcessState.SNAPSHOTTED,
        "CorpusSnapshotPublished",
    ),
    (ProcessState.SNAPSHOTTED, AuditCommandType.START_AUDIT): (
        ProcessState.EVALUATING,
        "AuditStarted",
    ),
    (ProcessState.EVALUATING, AuditCommandType.EVALUATE_DOCUMENT_DELTA): (
        ProcessState.EVALUATING,
        "DocumentDeltaEvaluated",
    ),
    (ProcessState.EVALUATING, AuditCommandType.EVALUATE_CAUSAL_DELTA): (
        ProcessState.EVALUATING,
        "CausalReadinessDeltaEvaluated",
    ),
    (ProcessState.EVALUATING, AuditCommandType.EVALUATE_PACKAGE_READINESS): (
        ProcessState.EVALUATING,
        "PackageReadinessEvaluated",
    ),
    (ProcessState.EVALUATING, AuditCommandType.ISSUE_ACTION_REQUEST): (
        ProcessState.BLOCKED,
        "AuditActionRequested",
    ),
    (ProcessState.BLOCKED, AuditCommandType.RECLASSIFY_DOCUMENT): (
        ProcessState.EVALUATING,
        "DocumentReclassified",
    ),
    (ProcessState.EVALUATING, AuditCommandType.FINALIZE_AUDIT_REPORT): (
        ProcessState.COMPLETED,
        "AuditReportFinalized",
    ),
}


class AuditStateMachine:
    def apply(self, state: ProcessState, revision: int, command: AuditCommand) -> CommandOutcome:
        if command.expected_revision != revision:
            return CommandOutcome(False, revision, state, "CONCURRENCY_CONFLICT", None)
        transition = _TRANSITIONS.get((state, command.command_type))
        if transition is None:
            return CommandOutcome(False, revision, state, "TRANSITION_DENIED", None)
        next_state, event = transition
        return CommandOutcome(True, revision + 1, next_state, "OK", event)
