"""Explicit command/event state machine for the Support overlay."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from asd_kontur.harness.models import digest_of

from .errors import SupportError, SupportErrorCode
from .models import ProfessionalAuthority, SupportState


class SupportCommandType(StrEnum):
    CONFIGURE_SUPPORT_SCOPE = "ConfigureSupportScope"
    CREATE_PLANNED_WORK = "CreatePlannedWork"
    EVALUATE_WORK_READINESS = "EvaluateWorkReadiness"
    CONFIRM_WORK_FACT = "ConfirmWorkFact"
    REGISTER_MATERIAL_BATCH = "RegisterMaterialBatch"
    APPLY_MATERIAL_BATCH = "ApplyMaterialBatch"
    RECORD_CONTROL_EVENT = "RecordControlEvent"
    ATTACH_EVIDENCE = "AttachEvidence"
    EVALUATE_ID_COMPLETENESS = "EvaluateIdCompleteness"
    START_GENERATION_RUN = "StartGenerationRun"
    FORM_ID_PACKAGE = "FormIdPackage"
    EVALUATE_VOLUME_READINESS = "EvaluateVolumeReadiness"
    FORM_EXECUTIVE_SCHEME = "FormExecutiveScheme"
    TRACE_PRESENTED_VOLUME = "TracePresentedVolume"
    EVALUATE_PAYMENT_READINESS = "EvaluatePaymentReadiness"
    FINALIZE_SUPPORT_DELIVERABLE = "FinalizeSupportDeliverable"


EVENT_BY_COMMAND = {
    SupportCommandType.CONFIGURE_SUPPORT_SCOPE: "SupportScopeConfigured",
    SupportCommandType.CREATE_PLANNED_WORK: "PlannedWorkCreated",
    SupportCommandType.EVALUATE_WORK_READINESS: "WorkReadinessEvaluated",
    SupportCommandType.CONFIRM_WORK_FACT: "WorkFactConfirmed",
    SupportCommandType.REGISTER_MATERIAL_BATCH: "MaterialBatchAccepted",
    SupportCommandType.APPLY_MATERIAL_BATCH: "MaterialBatchApplied",
    SupportCommandType.RECORD_CONTROL_EVENT: "ControlEventRecorded",
    SupportCommandType.ATTACH_EVIDENCE: "EvidenceVerified",
    SupportCommandType.EVALUATE_ID_COMPLETENESS: "IdCompletenessEvaluated",
    SupportCommandType.START_GENERATION_RUN: "GenerationRunStarted",
    SupportCommandType.FORM_ID_PACKAGE: "IdPackageFormed",
    SupportCommandType.EVALUATE_VOLUME_READINESS: "VolumeReadinessEvaluated",
    SupportCommandType.FORM_EXECUTIVE_SCHEME: "ExecutiveSchemeFinalized",
    SupportCommandType.TRACE_PRESENTED_VOLUME: "PresentedVolumeTraced",
    SupportCommandType.EVALUATE_PAYMENT_READINESS: "PaymentReadinessEvaluated",
    SupportCommandType.FINALIZE_SUPPORT_DELIVERABLE: "SupportDeliverableFinalized",
}


CAPABILITY_BY_COMMAND = {
    SupportCommandType.CONFIGURE_SUPPORT_SCOPE: "support.scope.configure",
    SupportCommandType.CREATE_PLANNED_WORK: "support.work.plan",
    SupportCommandType.EVALUATE_WORK_READINESS: "support.work.evaluate",
    SupportCommandType.CONFIRM_WORK_FACT: "support.engineering.confirm",
    SupportCommandType.REGISTER_MATERIAL_BATCH: "support.material.admit",
    SupportCommandType.APPLY_MATERIAL_BATCH: "support.material.apply",
    SupportCommandType.RECORD_CONTROL_EVENT: "support.control.confirm",
    SupportCommandType.ATTACH_EVIDENCE: "support.evidence.verify",
    SupportCommandType.EVALUATE_ID_COMPLETENESS: "support.id.evaluate",
    SupportCommandType.START_GENERATION_RUN: "support.document.generate",
    SupportCommandType.FORM_ID_PACKAGE: "support.id.form-package",
    SupportCommandType.EVALUATE_VOLUME_READINESS: "support.volume.review",
    SupportCommandType.FORM_EXECUTIVE_SCHEME: "support.geometry.finalize",
    SupportCommandType.TRACE_PRESENTED_VOLUME: "support.ks.trace",
    SupportCommandType.EVALUATE_PAYMENT_READINESS: "support.payment.review",
    SupportCommandType.FINALIZE_SUPPORT_DELIVERABLE: "support.deliverable.finalize",
}


@dataclass(frozen=True, slots=True)
class SupportCommand:
    command_id: UUID
    command_type: SupportCommandType
    support_process_id: UUID
    expected_revision: int
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID
    semantic_payload: dict[str, object]
    authority: ProfessionalAuthority

    @property
    def semantic_digest(self) -> str:
        return digest_of(
            {
                "command_type": self.command_type,
                "support_process_id": self.support_process_id,
                "expected_revision": self.expected_revision,
                "semantic_payload": self.semantic_payload,
                "authority_identity": self.authority.identity_id,
                "authority_grant": self.authority.grant_id,
                "authority_grant_version": self.authority.grant_version,
            }
        )


@dataclass(frozen=True, slots=True)
class SupportEvent:
    event_type: str
    support_process_id: UUID
    aggregate_revision: int
    correlation_id: UUID
    causation_id: UUID
    payload_fingerprint: str


@dataclass(frozen=True, slots=True)
class SupportCommandOutcome:
    outcome: str
    revision: int
    state: SupportState
    event: SupportEvent | None
    reason_code: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "revision": self.revision,
            "state": self.state,
            "event": self.event,
            "reason_code": self.reason_code,
        }


class SupportProcessStateMachine:
    """Fail-closed state machine; rejected commands never create an event."""

    def execute(
        self,
        *,
        current_state: SupportState,
        current_revision: int,
        command: SupportCommand,
        blockers: tuple[str, ...] = (),
    ) -> SupportCommandOutcome:
        if command.expected_revision != current_revision:
            raise SupportError(
                SupportErrorCode.CONCURRENCY_CONFLICT,
                "The Support process revision changed before command execution.",
            )
        expected_capability = CAPABILITY_BY_COMMAND[command.command_type]
        if command.authority.capability != expected_capability:
            raise SupportError(
                SupportErrorCode.AUTHORITY_DENIED,
                "The professional grant does not authorize this Support command.",
            )
        if current_state in {SupportState.BLOCKED, SupportState.FINALIZED}:
            raise SupportError(
                SupportErrorCode.INVALID_STATE,
                "The Support process cannot accept this command in its current state.",
            )
        if blockers and command.command_type is SupportCommandType.FINALIZE_SUPPORT_DELIVERABLE:
            return SupportCommandOutcome(
                "rejected",
                current_revision,
                current_state,
                None,
                "MATERIAL_BLOCKER_OPEN",
            )
        next_state = self._next_state(current_state, command.command_type)
        revision = current_revision + 1
        event = SupportEvent(
            EVENT_BY_COMMAND[command.command_type],
            command.support_process_id,
            revision,
            command.correlation_id,
            command.command_id,
            command.semantic_digest,
        )
        return SupportCommandOutcome("accepted_completed", revision, next_state, event, "OK")

    @staticmethod
    def _next_state(state: SupportState, command_type: SupportCommandType) -> SupportState:
        if command_type is SupportCommandType.CONFIGURE_SUPPORT_SCOPE:
            if state is not SupportState.REQUESTED:
                raise SupportError(
                    SupportErrorCode.INVALID_STATE,
                    "Support scope can only be configured from requested state.",
                )
            return SupportState.SCOPE_CONFIGURED
        if state is SupportState.REQUESTED:
            raise SupportError(
                SupportErrorCode.INVALID_STATE,
                "Support scope must be configured before domain work.",
            )
        if command_type is SupportCommandType.FINALIZE_SUPPORT_DELIVERABLE:
            if state not in {
                SupportState.READY_FOR_DELIVERABLE,
                SupportState.WAITING_FOR_AUTHORITY,
            }:
                raise SupportError(
                    SupportErrorCode.INVALID_STATE,
                    "Support deliverable is not ready for finalization.",
                )
            return SupportState.FINALIZED
        if command_type in {
            SupportCommandType.FORM_ID_PACKAGE,
            SupportCommandType.EVALUATE_VOLUME_READINESS,
            SupportCommandType.TRACE_PRESENTED_VOLUME,
            SupportCommandType.EVALUATE_PAYMENT_READINESS,
        }:
            return SupportState.READY_FOR_DELIVERABLE
        return SupportState.EXECUTING
