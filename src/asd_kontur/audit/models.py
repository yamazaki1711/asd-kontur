"""Typed evidence-rated values for the WP-14 Audit slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from asd_kontur.corpus import CorpusSnapshot
from asd_kontur.harness.models import digest_of


class DeltaState(StrEnum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    CONFLICT = "conflict"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class AuditTerminalOutcome(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"


class ActionRequestState(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    EVIDENCE_SUBMITTED = "evidence_submitted"
    VERIFIED_CLOSED = "verified_closed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AuditScope:
    organization_id: UUID
    workspace_id: UUID
    mode_execution_id: UUID
    audit_process_id: UUID
    corpus_snapshot_id: UUID
    corpus_snapshot_version: int
    rule_set_version_id: UUID
    conflict_policy_version: str
    authority_profile_version: str
    contract_registry_version: str
    purpose: str = "construction_evidence_audit"

    def __post_init__(self) -> None:
        versions = (
            self.conflict_policy_version,
            self.authority_profile_version,
            self.contract_registry_version,
        )
        if self.corpus_snapshot_version < 1 or any(
            version.lower() == "latest" for version in versions
        ):
            raise ValueError("Audit must pin exact snapshot and policy versions")


@dataclass(frozen=True, slots=True)
class EvidenceRatedItem:
    item_key: str
    state: DeltaState
    source_version_ids: tuple[UUID, ...]
    source_locator_ids: tuple[UUID, ...]
    rule_trace_ids: tuple[UUID, ...]
    authority_decision_refs: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    downstream_impacts: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state is DeltaState.SATISFIED and (
            not self.source_locator_ids or not self.authority_decision_refs
        ):
            raise ValueError("Satisfied material item requires locator and authority evidence")


@dataclass(frozen=True, slots=True)
class DeltaDenominator:
    denominator_id: UUID
    version: int
    exact_scope: tuple[str, ...]
    required_item_keys: tuple[str, ...]
    rule_set_version_id: UUID
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version < 1 or not self.exact_scope:
            raise ValueError("Delta denominator must have exact versioned scope")


@dataclass(frozen=True, slots=True)
class DocumentDelta:
    document_delta_id: UUID
    version: int
    audit_scope: AuditScope
    denominator: DeltaDenominator
    items: tuple[EvidenceRatedItem, ...]
    dimensions: tuple[str, ...] = (
        "required",
        "found",
        "recognized",
        "classified",
        "versioned",
        "evidence_bound",
        "applicable",
    )

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class CausalImpactPath:
    path_id: UUID
    material_batch_ref: str
    incoming_control_ref: str | None
    admission_ref: str | None
    work_ref: str | None
    evidence_ref: str | None
    id_package_ref: str | None
    presented_volume_ref: str | None
    ks_ref: str | None
    payment_claim_ref: str | None
    state: DeltaState
    rule_trace_ids: tuple[UUID, ...]
    gap_codes: tuple[str, ...]
    downstream_impacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CausalReadinessDelta:
    causal_delta_id: UUID
    version: int
    audit_scope: AuditScope
    denominator: DeltaDenominator
    paths: tuple[CausalImpactPath, ...]

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class PackageMembership:
    occurrence_id: UUID
    ordinal: int
    required_copies: int
    actual_copies: int
    register_level: int | None


@dataclass(frozen=True, slots=True)
class PackageAssessment:
    package_id: UUID
    package_version: int
    volume_or_book_id: UUID | None
    section_ref: str | None
    memberships: tuple[PackageMembership, ...]
    professional_review_state: DeltaState
    signer_authority_state: DeltaState
    signature_state: DeltaState
    handover_state: DeltaState
    acceptance_state: DeltaState
    blocker_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        ordinals = tuple(item.ordinal for item in self.memberships)
        if len(set(ordinals)) != len(ordinals):
            raise ValueError("Package membership ordering must be unique")


@dataclass(frozen=True, slots=True)
class PackageReadiness:
    package_readiness_id: UUID
    version: int
    audit_scope: AuditScope
    denominator: DeltaDenominator
    packages: tuple[PackageAssessment, ...]

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class ActionRequest:
    action_request_id: UUID
    version: int
    audit_scope: AuditScope
    action_code: str
    addressee_identity_id: str
    affected_object_ref: str
    evidence_refs: tuple[str, ...]
    deadline: datetime | None
    blocking_impacts: tuple[str, ...]
    initiator_identity_id: str
    verifier_identity_id: str
    state: ActionRequestState
    supersedes_version: int | None = None
    executor_identity_id: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("ActionRequest version must be positive")
        if self.initiator_identity_id == self.verifier_identity_id:
            raise ValueError("ActionRequest initiator and verifier must be independent")
        if self.state is ActionRequestState.VERIFIED_CLOSED and not self.evidence_refs:
            raise ValueError("ActionRequest closure requires evidence")
        if self.state is ActionRequestState.VERIFIED_CLOSED and self.executor_identity_id is None:
            raise ValueError("ActionRequest closure requires an identified executor")
        if self.executor_identity_id == self.verifier_identity_id:
            raise ValueError("ActionRequest executor cannot verify its own remediation")


@dataclass(frozen=True, slots=True)
class ClassificationVersion:
    classification_id: UUID
    version: int
    occurrence_id: UUID
    document_type: str
    type_specific_attributes: tuple[tuple[str, str], ...]
    validator_version: str
    validation_failure_codes: tuple[str, ...]
    authority_decision_ref: str | None
    supersedes_version: int | None

    @property
    def ready(self) -> bool:
        return not self.validation_failure_codes and self.authority_decision_ref is not None


@dataclass(frozen=True, slots=True)
class AuditReport:
    audit_report_id: UUID
    version: int
    audit_scope: AuditScope
    corpus_snapshot_fingerprint: str
    document_delta_id: UUID
    document_delta_fingerprint: str
    causal_delta_id: UUID
    causal_delta_fingerprint: str
    package_readiness_id: UUID
    package_readiness_fingerprint: str
    action_request_ids: tuple[UUID, ...]
    outcome: AuditTerminalOutcome
    unresolved_codes: tuple[str, ...]
    created_at: datetime
    product_ready: bool = False

    def __post_init__(self) -> None:
        if self.product_ready:
            raise ValueError("WP-14 Audit slice cannot assert ProductReady")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


def scope_from_snapshot(
    snapshot: CorpusSnapshot,
    *,
    mode_execution_id: UUID,
    audit_process_id: UUID,
    conflict_policy_version: str,
    authority_profile_version: str,
    contract_registry_version: str,
) -> AuditScope:
    return AuditScope(
        snapshot.scope.organization_id,
        snapshot.scope.workspace_id,
        mode_execution_id,
        audit_process_id,
        snapshot.corpus_snapshot_id,
        snapshot.version,
        snapshot.rule_set_version_id,
        conflict_policy_version,
        authority_profile_version,
        contract_registry_version,
    )
