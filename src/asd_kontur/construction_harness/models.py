"""Typed, provider-independent values for the unified construction harness."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of
from asd_kontur.kernel.models import Mode


class HarnessErrorCode(StrEnum):
    CONTEXT_REQUIRED = "construction_harness_context_required"
    SCOPE_VIOLATION = "workspace_scope_violation"
    REGULATORY_WEAKENING = "customer_regulation_regulatory_weakening"
    UNVERIFIED_CANDIDATE = "unverified_project_characteristic"
    KNOWLEDGE_DEFECT = "knowledge_consistency_defect"
    EVIDENCE_REQUIRED = "exact_evidence_required"


class HarnessError(RuntimeError):
    def __init__(self, code: HarnessErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class VerificationStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_EVIDENCE = "needs_evidence"


class NormativeReferenceStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    OBSOLETE = "obsolete"
    EDITION_AMBIGUOUS = "edition_ambiguous"


class DocumentAssessment(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    WRONG_EDITION_OR_FORM = "wrong_edition_or_form"
    UNSUPPORTED = "unsupported"
    DUPLICATE = "duplicate"
    EVIDENCE_GAP = "evidence_gap"


class Recoverability(StrEnum):
    RECOVERABLE = "recoverable"
    NON_RECOVERABLE = "non_recoverable"
    INDETERMINATE = "indeterminate"


class RequirementAuthority(StrEnum):
    NORMATIVE_VERIFIED = "normative_verified"
    QUALIFIED_RULE = "qualified_rule"
    CONTRACTUAL = "contractual"
    METHODOLOGICAL_ADVISORY = "methodological_advisory"
    NORMATIVE_GAP = "normative_gap"


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    source_version_id: UUID
    locator: str
    content_digest: str
    evidence_link_id: UUID

    def __post_init__(self) -> None:
        if not self.locator or not self.content_digest.startswith("sha256:"):
            raise HarnessError(
                HarnessErrorCode.EVIDENCE_REQUIRED,
                "Exact source evidence is required",
            )


@dataclass(frozen=True, slots=True)
class ProjectCharacteristicCandidate:
    candidate_id: UUID
    version: int
    characteristic_key: str
    value: str
    extraction_profile_version: str
    evidence: SourceEvidence
    status: VerificationStatus = VerificationStatus.CANDIDATE

    def __post_init__(self) -> None:
        if self.version < 1 or self.extraction_profile_version.lower() == "latest":
            raise ValueError("candidate requires an immutable version and extraction profile")


@dataclass(frozen=True, slots=True)
class VerifiedProjectCharacteristic:
    characteristic_id: UUID
    version: int
    candidate_id: UUID
    candidate_version: int
    characteristic_key: str
    value: str
    validation_profile_version: str
    validation_receipt_digest: str
    evidence: SourceEvidence

    @classmethod
    def from_candidate(
        cls,
        *,
        characteristic_id: UUID,
        candidate: ProjectCharacteristicCandidate,
        validation_profile_version: str,
        validation_receipt_digest: str,
        deterministic_validation_passed: bool,
    ) -> VerifiedProjectCharacteristic:
        if not deterministic_validation_passed:
            raise HarnessError(
                HarnessErrorCode.UNVERIFIED_CANDIDATE,
                "A model Candidate cannot become a verified project fact without validation",
            )
        if validation_profile_version.lower() == "latest":
            raise ValueError("validation profile must be pinned")
        return cls(
            characteristic_id=characteristic_id,
            version=1,
            candidate_id=candidate.candidate_id,
            candidate_version=candidate.version,
            characteristic_key=candidate.characteristic_key,
            value=candidate.value,
            validation_profile_version=validation_profile_version,
            validation_receipt_digest=validation_receipt_digest,
            evidence=candidate.evidence,
        )


@dataclass(frozen=True, slots=True)
class WorkQuantity:
    quantity_id: UUID
    value: Decimal
    unit_code: str
    evidence: SourceEvidence

    def __post_init__(self) -> None:
        if self.value < 0 or not self.unit_code:
            raise ValueError("work quantity requires a non-negative value and explicit unit")


@dataclass(frozen=True, slots=True)
class MaterialRequirement:
    material_requirement_id: UUID
    material_key: str
    quantity: Decimal
    unit_code: str
    evidence: SourceEvidence


@dataclass(frozen=True, slots=True)
class ProjectNormativeReference:
    reference_id: UUID
    printed_identifier: str
    normalized_identifier: str
    status: NormativeReferenceStatus
    evidence: SourceEvidence
    normative_document_id: UUID | None = None
    normative_edition_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.status is NormativeReferenceStatus.RESOLVED and self.normative_edition_id is None:
            raise ValueError("resolved reference requires an exact NormativeEdition")


@dataclass(frozen=True, slots=True)
class WorkPackageCandidate:
    candidate_id: UUID
    version: int
    workspace_id: UUID
    work_type_key: str
    work_type_version: str
    title: str
    quantity_candidates: tuple[WorkQuantity, ...]
    material_candidates: tuple[MaterialRequirement, ...]
    normative_reference_candidates: tuple[ProjectNormativeReference, ...]
    predecessor_ids: tuple[UUID, ...]
    extraction_profile_version: str
    evidence: tuple[SourceEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.version < 1
            or self.extraction_profile_version.lower() == "latest"
            or self.work_type_version.lower() == "latest"
        ):
            raise ValueError("WorkPackageCandidate requires exact immutable extraction lineage")


@dataclass(frozen=True, slots=True)
class ConstructionWorkPackage:
    work_package_id: UUID
    version: int
    workspace_id: UUID
    work_type_key: str
    work_type_version: str
    title: str
    quantities: tuple[WorkQuantity, ...]
    materials: tuple[MaterialRequirement, ...]
    normative_references: tuple[ProjectNormativeReference, ...]
    predecessor_ids: tuple[UUID, ...]
    evidence: tuple[SourceEvidence, ...]

    @classmethod
    def from_candidate(
        cls,
        *,
        work_package_id: UUID,
        candidate: WorkPackageCandidate,
        deterministic_validation_passed: bool,
    ) -> ConstructionWorkPackage:
        if not deterministic_validation_passed:
            raise HarnessError(
                HarnessErrorCode.UNVERIFIED_CANDIDATE,
                "WorkPackageCandidate cannot become a canonical work package without validation",
            )
        if not candidate.evidence:
            raise HarnessError(HarnessErrorCode.EVIDENCE_REQUIRED, "Work package evidence is empty")
        return cls(
            work_package_id,
            1,
            candidate.workspace_id,
            candidate.work_type_key,
            candidate.work_type_version,
            candidate.title,
            candidate.quantity_candidates,
            candidate.material_candidates,
            candidate.normative_reference_candidates,
            candidate.predecessor_ids,
            candidate.evidence,
        )


@dataclass(frozen=True, slots=True)
class ProjectDefinition:
    project_definition_id: UUID
    version: int
    organization_id: UUID
    workspace_id: UUID
    purpose: str
    object_class: str
    characteristics: tuple[VerifiedProjectCharacteristic, ...]
    work_packages: tuple[ConstructionWorkPackage, ...]
    source_version_ids: tuple[UUID, ...]
    created_at: datetime
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.work_packages or any(
            item.workspace_id != self.workspace_id for item in self.work_packages
        ):
            raise HarnessError(
                HarnessErrorCode.SCOPE_VIOLATION,
                "Project work packages must belong to the exact workspace",
            )
        object.__setattr__(self, "fingerprint", _fingerprint_without(self, "fingerprint"))


@dataclass(frozen=True, slots=True)
class WorkControlRequirement:
    control_requirement_id: UUID
    control_kind: str
    basis_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequiredEvidence:
    evidence_requirement_id: UUID
    evidence_kind: str
    source_fact_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequiredIDDocument:
    document_requirement_id: UUID
    document_type: str
    minimum_copies: int
    form_edition: str | None
    basis_refs: tuple[str, ...]
    authority_status: RequirementAuthority

    def __post_init__(self) -> None:
        if self.minimum_copies < 1:
            raise ValueError("required ID document minimum must be positive")


@dataclass(frozen=True, slots=True)
class CustomerRegulationAddition:
    addition_id: UUID
    version: int
    organization_id: UUID
    workspace_id: UUID
    document_requirement_id: UUID
    additional_copies: int
    additional_evidence_kinds: tuple[str, ...]
    source: SourceEvidence

    def __post_init__(self) -> None:
        if self.additional_copies < 0:
            raise HarnessError(
                HarnessErrorCode.REGULATORY_WEAKENING,
                "Customer regulation cannot reduce a normative minimum",
            )
        if self.additional_copies == 0 and not self.additional_evidence_kinds:
            raise ValueError("customer overlay must add copies or evidence")


@dataclass(frozen=True, slots=True)
class WorkRequirementRow:
    work_package_id: UUID
    controls: tuple[WorkControlRequirement, ...]
    evidence: tuple[RequiredEvidence, ...]
    documents: tuple[RequiredIDDocument, ...]
    normative_gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkRequirementMatrix:
    matrix_id: UUID
    version: int
    organization_id: UUID
    workspace_id: UUID
    project_definition_id: UUID
    project_definition_version: int
    rows: tuple[WorkRequirementRow, ...]
    customer_addition_ids: tuple[UUID, ...]
    rule_set_version_id: UUID | None
    created_at: datetime
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("WorkRequirementMatrix cannot be empty")
        object.__setattr__(self, "fingerprint", _fingerprint_without(self, "fingerprint"))


@dataclass(frozen=True, slots=True)
class KnowledgeConsistencyDefect:
    defect_id: UUID
    code: str
    affected_reference: str
    evidence_refs: tuple[str, ...]
    blocking_rule_version_ids: tuple[UUID, ...]
    detected_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessMemorySnapshot:
    practice_guide_edition_refs: tuple[str, ...]
    practice_intelligence_refs: tuple[str, ...]
    practice_playbook_refs: tuple[str, ...]
    normative_edition_refs: tuple[str, ...]
    normative_provision_refs: tuple[str, ...]
    active_rule_version_refs: tuple[str, ...]
    gaps: tuple[dict[str, Any], ...]
    defects: tuple[KnowledgeConsistencyDefect, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstructionHarnessContextPack:
    context_pack_id: UUID
    contract_version: str
    organization_id: UUID
    workspace_id: UUID
    project_definition_ref: tuple[UUID, int]
    matrix_ref: tuple[UUID, int]
    matrix_fingerprint: str
    workspace_fact_refs: tuple[str, ...]
    practice_intelligence_refs: tuple[str, ...]
    practice_playbook_refs: tuple[str, ...]
    normative_edition_refs: tuple[str, ...]
    normative_provision_refs: tuple[str, ...]
    active_rule_version_refs: tuple[str, ...]
    customer_addition_refs: tuple[str, ...]
    source_evidence: tuple[SourceEvidence, ...]
    knowledge_gaps: tuple[dict[str, Any], ...]
    consistency_defect_ids: tuple[UUID, ...]
    assembled_at: datetime
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.contract_version.lower() == "latest" or not self.source_evidence:
            raise HarnessError(
                HarnessErrorCode.EVIDENCE_REQUIRED,
                "A Harness ContextPack requires pinned contracts and exact source evidence",
            )
        object.__setattr__(self, "fingerprint", _fingerprint_without(self, "fingerprint"))


@dataclass(frozen=True, slots=True)
class EstimateQuantity:
    work_package_id: UUID
    work_type_key: str
    value: Decimal
    unit_code: str
    material_keys: tuple[str, ...]
    evidence: SourceEvidence


@dataclass(frozen=True, slots=True)
class TenderView:
    mode: Mode
    matrix_ref: tuple[UUID, int]
    matrix_fingerprint: str
    quantity_deltas: tuple[dict[str, str], ...]
    missing_materials: tuple[dict[str, str], ...]
    unresolved_ntd_references: tuple[str, ...]
    conclusion: str | None
    normative_confirmed: bool


@dataclass(frozen=True, slots=True)
class SupportView:
    mode: Mode
    matrix_ref: tuple[UUID, int]
    matrix_fingerprint: str
    control_requirement_ids: tuple[UUID, ...]
    evidence_requirement_ids: tuple[UUID, ...]
    document_requirement_ids: tuple[UUID, ...]
    presentation_blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentedIDDocument:
    document_id: UUID
    document_type: str
    form_edition: str | None
    copy_count: int
    complete: bool
    valid: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditView:
    mode: Mode
    matrix_ref: tuple[UUID, int]
    matrix_fingerprint: str
    document_assessments: tuple[tuple[UUID, DocumentAssessment], ...]


@dataclass(frozen=True, slots=True)
class RestorationView:
    mode: Mode
    matrix_ref: tuple[UUID, int]
    matrix_fingerprint: str
    document_recoverability: tuple[tuple[UUID, Recoverability, tuple[str, ...]], ...]
    ordered_document_ids: tuple[UUID, ...]
    fabrication_prohibited: bool = True


@dataclass(frozen=True, slots=True)
class DrawingIntelligenceReference:
    """Reserved integration contract; no CAD/VLM drawing analysis is implemented here."""

    source_version_id: UUID
    locator: str
    status: str = "technical_debt_not_implemented"


@dataclass(frozen=True, slots=True)
class HarnessBackupManifest:
    manifest_id: UUID
    version: int
    project_definition_fingerprint: str
    matrix_fingerprint: str
    context_pack_fingerprint: str
    platform_memory_fingerprints: tuple[str, ...]
    projection_profile_version: str
    created_on: date
    semantic_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_fingerprint",
            _fingerprint_without(self, "semantic_fingerprint"),
        )


def _fingerprint_without(value: Any, excluded: str) -> str:
    return digest_of(
        {item.name: getattr(value, item.name) for item in fields(value) if item.name != excluded}
    )
