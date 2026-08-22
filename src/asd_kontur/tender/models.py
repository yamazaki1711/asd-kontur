"""Typed, object-independent values for the Tender implementation slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of
from asd_kontur.kernel import Applicability, Mode

from .errors import TenderError, TenderErrorCode


class TenderStep(StrEnum):
    ASSESS_CORPUS = "assess_tender_corpus"
    DETERMINE_REQUIREMENTS = "determine_tender_requirements"
    ANALYZE_CONTRACT_RISK = "analyze_contract_risk"
    DRAFT_DISAGREEMENT_PROTOCOL = "draft_disagreement_protocol"
    DRAFT_REVISED_CONTRACT = "draft_revised_contract"
    FINALIZE = "finalize_tender_deliverable"


class TenderState(StrEnum):
    REQUESTED = "requested"
    CORPUS_ASSESSED = "corpus_assessed"
    REQUIREMENTS_DETERMINED = "requirements_determined"
    ANALYZED = "analyzed"
    DRAFTED = "drafted"
    WAITING_FOR_AUTHORITY = "waiting_for_authority"
    BLOCKED = "blocked"
    FINALIZED = "finalized"


class SourceClass(StrEnum):
    TENDER_DOCUMENTATION = "tender_documentation"
    DRAFT_CONTRACT = "draft_contract"
    CONTRACT_APPENDIX = "contract_appendix"
    PD = "project_documentation"
    RD = "working_documentation"
    VOLUME_SHEET = "volume_sheet"
    SPECIFICATION = "specification"
    ESTIMATE = "estimate"
    CUSTOMER_REGULATION = "customer_regulation"


class AuthorityLayer(StrEnum):
    NTD = "ntd"
    LEGISLATION = "legislation"
    CONTRACT = "contract"
    CUSTOMER_REGULATION = "customer_regulation"
    JUDICIAL_PRACTICE = "judicial_practice"
    EXPERT_OPINION = "expert_opinion"


class TenderIssueKind(StrEnum):
    CONTRACT_RISK = "contract_risk"
    CONFLICT = "conflict"
    GAP = "gap"
    UNCERTAINTY = "uncertainty"
    BLOCKER = "blocker"
    MISSING_WORK = "missing_work"
    MISSING_MATERIAL = "missing_material"
    GEOMETRY_BLOCKER = "geometry_blocker"


class RiskSubject(StrEnum):
    RESPONSIBILITY = "responsibility"
    DEADLINE = "deadline"
    ACCEPTANCE = "acceptance"
    PAYMENT = "payment"
    PRICE = "price"
    VOLUME = "volume"
    MATERIAL = "material"
    TECHNICAL_REQUIREMENT = "technical_requirement"
    AUTHORITY = "authority"
    TERMINATION = "termination"
    GEOMETRY = "geometry"
    SOURCE_COMPLETENESS = "source_completeness"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


class TenderDeliverableKind(StrEnum):
    DISAGREEMENT_PROTOCOL = "disagreement_protocol"
    REVISED_CONTRACT = "revised_contract"
    RISK_REGISTER = "tender_risk_register"
    GAP_REGISTER = "tender_gap_register"
    PDRD_ANALYSIS = "tender_pd_rd_analysis"


class TenderTerminalOutcome(StrEnum):
    SUCCESS = "successful"
    BLOCKED_INCOMPLETE_CORPUS = "blocked_incomplete_corpus"
    BLOCKED_UNRESOLVED_CONFLICT = "blocked_unresolved_conflict"
    BLOCKED_MATERIAL_UNCERTAINTY = "blocked_material_uncertainty"
    BLOCKED_AUTHORITY = "blocked_authority"


@dataclass(frozen=True, slots=True)
class TenderScope:
    organization_id: UUID
    workspace_id: UUID
    mode_execution_id: UUID
    analysis_scope_version: str
    rule_set_version_id: UUID
    authority_profile_version: str
    policy_versions: tuple[str, ...]
    contract_registry_version: str

    def __post_init__(self) -> None:
        versions = (
            self.analysis_scope_version,
            self.authority_profile_version,
            self.contract_registry_version,
            *self.policy_versions,
        )
        if any(not value or value.lower() == "latest" for value in versions):
            raise TenderError(
                TenderErrorCode.INVALID_SCOPE,
                "Tender scope must pin every policy and contract version exactly.",
            )

    @property
    def mode(self) -> Mode:
        return Mode.TENDER


@dataclass(frozen=True, slots=True)
class ClauseProvenance:
    source_version_id: UUID
    source_locator_id: UUID
    evidence_link_id: UUID
    fact_id: UUID
    fact_version: int

    def __post_init__(self) -> None:
        if self.fact_version < 1:
            raise TenderError(
                TenderErrorCode.PROVENANCE_INCOMPLETE,
                "Clause provenance must reference a confirmed Fact version.",
            )


@dataclass(frozen=True, slots=True)
class ContractClause:
    clause_id: UUID
    clause_version: int
    locator_label: str
    text_digest: str
    authority_layer: AuthorityLayer
    provenance: ClauseProvenance
    effective_edition_ref: str | None = None

    def __post_init__(self) -> None:
        if self.clause_version < 1 or not self.locator_label:
            raise TenderError(
                TenderErrorCode.PROVENANCE_INCOMPLETE,
                "A contract clause requires an immutable version and exact locator.",
            )
        if not self.text_digest.startswith("sha256:"):
            raise TenderError(
                TenderErrorCode.PROVENANCE_INCOMPLETE,
                "Clause content must be represented by a SHA-256 integrity digest.",
            )


@dataclass(frozen=True, slots=True)
class CorpusItem:
    source_class: SourceClass
    source_version_id: UUID
    source_locator_id: UUID
    evidence_link_id: UUID
    accepted: bool


@dataclass(frozen=True, slots=True)
class CorpusAssessment:
    required_classes: tuple[SourceClass, ...]
    available_classes: tuple[SourceClass, ...]
    missing_classes: tuple[SourceClass, ...]
    optional_absent_classes: tuple[SourceClass, ...]
    status: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "required_classes": self.required_classes,
            "available_classes": self.available_classes,
            "missing_classes": self.missing_classes,
            "optional_absent_classes": self.optional_absent_classes,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class TenderRequirement:
    requirement_id: UUID
    requirement_version: int
    requirement_key: str
    subject: RiskSubject
    applicability: Applicability
    rule_set_version_id: UUID
    rule_trace_id: UUID
    evidence_refs: tuple[UUID, ...]
    required_source_classes: tuple[SourceClass, ...] = ()


@dataclass(frozen=True, slots=True)
class TenderIssue:
    issue_id: UUID
    issue_version: int
    kind: TenderIssueKind
    subject: RiskSubject
    severity: Severity
    applicability: Applicability
    clause: ContractClause | None
    requirement_id: UUID | None
    rule_set_version_id: UUID
    rule_trace_id: UUID | None
    evidence_refs: tuple[UUID, ...]
    uncertainty_code: str | None
    recommended_change: str | None
    consequence_code: str
    kernel_finding_id: UUID | None = None
    kernel_finding_version: int | None = None
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.issue_version < 1:
            raise ValueError("issue version must be positive")
        material_source = self.clause is not None or (
            self.kernel_finding_id is not None and self.kernel_finding_version is not None
        )
        if self.kind not in (TenderIssueKind.GAP, TenderIssueKind.UNCERTAINTY) and (
            not material_source or not self.evidence_refs
        ):
            raise TenderError(
                TenderErrorCode.PROVENANCE_INCOMPLETE,
                "A material Tender finding requires clause-level evidence.",
            )
        if self.applicability is Applicability.INDETERMINATE and not self.uncertainty_code:
            raise TenderError(
                TenderErrorCode.APPLICABILITY_INDETERMINATE,
                "Indeterminate applicability requires an explicit uncertainty.",
            )
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_version": self.issue_version,
            "kind": self.kind,
            "subject": self.subject,
            "severity": self.severity,
            "applicability": self.applicability,
            "clause_id": self.clause.clause_id if self.clause else None,
            "clause_version": self.clause.clause_version if self.clause else None,
            "requirement_id": self.requirement_id,
            "rule_set_version_id": self.rule_set_version_id,
            "rule_trace_id": self.rule_trace_id,
            "evidence_refs": self.evidence_refs,
            "uncertainty_code": self.uncertainty_code,
            "recommended_change": self.recommended_change,
            "consequence_code": self.consequence_code,
            "kernel_finding_id": self.kernel_finding_id,
            "kernel_finding_version": self.kernel_finding_version,
        }


@dataclass(frozen=True, slots=True)
class DisagreementItem:
    item_id: UUID
    ordinal: int
    clause: ContractClause
    issue_id: UUID
    issue_version: int
    proposed_clause_text: str
    consequence_code: str
    evidence_refs: tuple[UUID, ...]
    rule_trace_id: UUID
    finding_decision_id: UUID
    uncertainty_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not self.proposed_clause_text or not self.evidence_refs:
            raise TenderError(
                TenderErrorCode.OUTPUT_INCOMPLETE,
                "Every disagreement item requires lineage, evidence, and a proposed clause.",
            )


@dataclass(frozen=True, slots=True)
class RevisedClause:
    revised_clause_id: UUID
    ordinal: int
    source_clause: ContractClause
    issue_id: UUID
    issue_version: int
    disagreement_item_id: UUID
    decision_id: UUID
    revised_text: str


@dataclass(frozen=True, slots=True)
class TypedTenderDeliverable:
    deliverable_id: UUID
    deliverable_version: int
    kind: TenderDeliverableKind
    item_ids: tuple[UUID, ...]
    source_manifest_digest: str
    evidence_manifest_digest: str
    rule_set_version_id: UUID
    state: str
    blocker_ids: tuple[UUID, ...]
    uncertainty_ids: tuple[UUID, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.deliverable_version < 1 or not self.item_ids:
            raise TenderError(
                TenderErrorCode.OUTPUT_INCOMPLETE,
                "A Tender deliverable must contain typed items.",
            )
        if self.state == "finalized" and self.blocker_ids:
            raise TenderError(
                TenderErrorCode.MATERIAL_BLOCKER,
                "A deliverable with material blockers cannot be finalized.",
            )
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "deliverable_version": self.deliverable_version,
            "kind": self.kind,
            "item_ids": self.item_ids,
            "source_manifest_digest": self.source_manifest_digest,
            "evidence_manifest_digest": self.evidence_manifest_digest,
            "rule_set_version_id": self.rule_set_version_id,
            "state": self.state,
            "blocker_ids": self.blocker_ids,
            "uncertainty_ids": self.uncertainty_ids,
        }


@dataclass(frozen=True, slots=True)
class LegalAuthority:
    human_identity_id: str
    grant_id: UUID
    grant_version: int
    capability: str
    professional_qualification_ref: str
    active: bool

    def __post_init__(self) -> None:
        if self.human_identity_id.startswith(("model:", "service:", "integration:")):
            raise TenderError(
                TenderErrorCode.AUTHORITY_DENIED,
                "Model and service identities cannot carry Tender legal authority.",
            )


@dataclass(frozen=True, slots=True)
class TenderFinalizationDecision:
    decision_id: UUID
    reviewer: LegalAuthority
    finalizer: LegalAuthority
    deliverable_ids: tuple[UUID, ...]
    outcome: TenderTerminalOutcome
    limitation_codes: tuple[str, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.reviewer.human_identity_id == self.finalizer.human_identity_id:
            raise TenderError(
                TenderErrorCode.AUTHORITY_DENIED,
                "Independent legal review and finalization require different humans.",
            )
        if not (self.reviewer.active and self.finalizer.active):
            raise TenderError(TenderErrorCode.AUTHORITY_DENIED, "Authority is inactive.")
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "reviewer": self.reviewer.human_identity_id,
            "reviewer_grant": self.reviewer.grant_id,
            "finalizer": self.finalizer.human_identity_id,
            "finalizer_grant": self.finalizer.grant_id,
            "deliverable_ids": self.deliverable_ids,
            "outcome": self.outcome,
            "limitation_codes": self.limitation_codes,
        }
