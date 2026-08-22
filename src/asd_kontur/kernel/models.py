"""Typed values for the object-independent common domain process kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of


class Mode(StrEnum):
    TENDER = "Tender"
    SUPPORT = "Support"
    AUDIT = "Audit"
    RESTORATION = "Restoration"


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"


class FactClass(StrEnum):
    OBSERVATION = "observation"
    CLASSIFICATION = "classification"
    LEGAL_EFFECT = "legal_effect"
    CONTRACTUAL_OBLIGATION = "contractual_obligation"
    GEOMETRY = "geometry"
    MEASUREMENT = "measurement"
    PAYABLE_VOLUME = "payable_volume"
    SIGNER_AUTHORITY = "signer_authority"
    MATERIAL_BLOCKER = "material_blocker"
    PROFESSIONAL_FINALIZATION = "professional_finalization"


class FactValueKind(StrEnum):
    TEXT = "text"
    BOOLEAN = "boolean"
    DECIMAL_QUANTITY = "decimal_quantity"
    DATE = "date"
    REFERENCE = "reference"
    MEASUREMENT = "measurement"


class AuthorityKind(StrEnum):
    QUALIFIED_HUMAN = "qualified_human"
    DETERMINISTIC_RULE = "deterministic_rule"


class DecisionOutcome(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEEDS_EVIDENCE = "needs_evidence"
    CONFLICT = "conflict"


class IssueKind(StrEnum):
    UNCERTAINTY = "uncertainty"
    CONFLICT = "conflict"
    BLOCKER = "blocker"


class FindingKind(StrEnum):
    MISSING_WORK = "missing_work"
    MISSING_MATERIAL = "missing_material"
    MISSING_EVIDENCE = "missing_evidence"
    CONSTRUCTIVE_CLASH = "constructive_clash"
    GEOMETRIC_CLASH = "geometric_clash"
    CONTRACT_RISK = "contract_risk"
    AUDIT_DELTA = "audit_delta"
    RESTORATION_GAP = "restoration_gap"
    PAYMENT_BLOCKER = "payment_blocker"


@dataclass(frozen=True, slots=True)
class KernelScope:
    organization_id: UUID
    workspace_id: UUID


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    source_version_id: UUID
    source_locator_id: UUID
    evidence_link_id: UUID


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit_code: str
    precision_scale: int
    rounding_policy_version: str

    def __post_init__(self) -> None:
        if not self.unit_code or self.precision_scale < 0:
            raise ValueError("quantity requires an explicit unit and non-negative precision")
        if self.rounding_policy_version.lower() == "latest":
            raise ValueError("quantity must pin an exact rounding policy version")


@dataclass(frozen=True, slots=True)
class HumanAuthority:
    identity_id: str
    grant_id: UUID
    grant_version: int
    capability: str
    qualified_fact_classes: frozenset[FactClass]
    active: bool = True
    professional_qualification_ref: str | None = None

    def __post_init__(self) -> None:
        if self.identity_id.startswith(("model:", "service:", "integration:")):
            raise ValueError("only a human principal may carry professional confirmation authority")


@dataclass(frozen=True, slots=True)
class DeterministicAuthority:
    service_identity_id: str
    rule_version_id: UUID
    rule_set_version_id: UUID
    rule_evaluation_id: UUID
    rule_trace_id: UUID
    rule_trace_fingerprint: str
    applicability: Applicability
    rule_outcome: str
    active_rule: bool
    member_of_pinned_rule_set: bool


@dataclass(frozen=True, slots=True)
class ConfirmationPolicy:
    policy_id: UUID
    version: str
    auto_confirm_fact_classes: frozenset[FactClass]
    professional_fact_classes: frozenset[FactClass]
    status: str

    def __post_init__(self) -> None:
        if self.version.lower() == "latest":
            raise ValueError("confirmation policy requires an exact version")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate_id: UUID
    candidate_version: int
    field_path: str
    status: str
    validation_run_id: UUID
    validation_passed: bool
    skipped_mandatory_validators: tuple[str, ...]
    source_confirmed: bool
    evidence: tuple[EvidenceBinding, ...]
    typed_value: Any = None
    conflict_ids: tuple[UUID, ...] = ()
    uncertainty_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    decision_id: UUID
    fact_id: UUID
    expected_fact_version: int
    fact_type: str
    fact_class: FactClass
    value_kind: FactValueKind
    candidate: CandidateAssessment
    policy: ConfirmationPolicy
    authority: HumanAuthority | DeterministicAuthority
    correlation_id: UUID
    causation_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    outcome: DecisionOutcome
    decision_id: UUID
    fact_id: UUID
    fact_version: int | None
    reason_code: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fingerprint",
            digest_of(
                {
                    "outcome": self.outcome,
                    "decision_id": self.decision_id,
                    "fact_id": self.fact_id,
                    "fact_version": self.fact_version,
                    "reason_code": self.reason_code,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class RequiredItem:
    requirement_id: UUID
    applicability: Applicability
    rule_trace_id: UUID


@dataclass(frozen=True, slots=True)
class CoverageItem:
    requirement_id: UUID
    covered: bool
    evidence_refs: tuple[UUID, ...]
    unresolved: bool = False


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    status: str
    required_ids: tuple[UUID, ...]
    covered_ids: tuple[UUID, ...]
    missing_ids: tuple[UUID, ...]
    indeterminate_ids: tuple[UUID, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "required_ids": self.required_ids,
            "covered_ids": self.covered_ids,
            "missing_ids": self.missing_ids,
            "indeterminate_ids": self.indeterminate_ids,
        }


@dataclass(frozen=True, slots=True)
class KernelChainSnapshot:
    structure_version_id: UUID
    work_version_ids: tuple[UUID, ...]
    volume_version_ids: tuple[UUID, ...]
    material_requirement_ids: tuple[UUID, ...]
    control_operation_ids: tuple[UUID, ...]
    evidence_requirement_ids: tuple[UUID, ...]
    document_requirement_ids: tuple[UUID, ...]
    id_package_id: UUID
    presented_volume_ids: tuple[UUID, ...]
    ks_line_ids: tuple[UUID, ...]
    payment_claim_ids: tuple[UUID, ...]
    issue_ids: tuple[UUID, ...]
    rule_set_version_id: UUID
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fingerprint",
            digest_of(
                {
                    name: getattr(self, name)
                    for name in self.__dataclass_fields__
                    if name != "fingerprint"
                }
            ),
        )
