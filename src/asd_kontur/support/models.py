"""Typed object-independent values for the WP-13 Support slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of
from asd_kontur.kernel.models import Applicability, Quantity


class SupportState(StrEnum):
    REQUESTED = "requested"
    SCOPE_CONFIGURED = "scope_configured"
    EXECUTING = "executing"
    WAITING_FOR_EVIDENCE = "waiting_for_evidence"
    READY_FOR_DELIVERABLE = "ready_for_deliverable"
    WAITING_FOR_AUTHORITY = "waiting_for_authority"
    BLOCKED = "blocked"
    FINALIZED = "finalized"


class WorkReadiness(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


class MaterialAdmission(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    WAITING_FOR_DOCUMENTS = "waiting_for_documents"


class ControlOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


class ResolutionState(StrEnum):
    CONFIRMED = "confirmed"
    CANDIDATE = "candidate"
    CONFLICT = "conflict"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class OfflineDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    QUARANTINED = "quarantined"


class GeometryOutcome(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class SupportScope:
    organization_id: UUID
    workspace_id: UUID
    mode_execution_id: UUID
    support_process_id: UUID
    rule_set_version_id: UUID
    process_definition_version: str
    authority_profile_version: str
    contract_registry_version: str
    policy_versions: tuple[str, ...]
    deliverable_scope: tuple[str, ...]
    classification: str
    purpose: str = "construction_support"

    def __post_init__(self) -> None:
        exact_versions = (
            self.process_definition_version,
            self.authority_profile_version,
            self.contract_registry_version,
            *self.policy_versions,
        )
        if any(version.lower() == "latest" for version in exact_versions):
            raise ValueError("Support scope must pin exact versions")
        if not self.deliverable_scope or not self.policy_versions:
            raise ValueError("Support scope and policy manifest cannot be empty")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class ProfessionalAuthority:
    identity_id: str
    grant_id: UUID
    grant_version: int
    capability: str
    qualification_ref: str
    active: bool = True

    def __post_init__(self) -> None:
        if self.identity_id.startswith(("model:", "service:", "integration:")):
            raise ValueError("Professional authority belongs only to a human identity")
        if not self.active or self.grant_version < 1:
            raise ValueError("An active exact professional grant is required")


def require_independent_authorities(
    first: ProfessionalAuthority,
    second: ProfessionalAuthority,
) -> None:
    if first.identity_id == second.identity_id or first.grant_id == second.grant_id:
        raise ValueError("Independent professional authorities are required")


@dataclass(frozen=True, slots=True)
class WorkReadinessInput:
    work_instance_id: UUID
    work_instance_version: int
    planned: bool
    performed_fact_id: UUID | None
    performed_fact_version: int | None
    predecessor_states: tuple[str, ...]
    prestart_control_states: tuple[str, ...]
    material_states: tuple[MaterialAdmission, ...]
    evidence_checkpoint_states: tuple[str, ...]
    blocking_issue_ids: tuple[UUID, ...]
    rule_trace_id: UUID
    hidden_work: bool = False
    checkpoint_due_at: datetime | None = None
    evidence_recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkReadinessResult:
    outcome: WorkReadiness
    reason_codes: tuple[str, ...]
    rule_trace_id: UUID
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason_codes": self.reason_codes,
            "rule_trace_id": self.rule_trace_id,
        }


@dataclass(frozen=True, slots=True)
class MaterialBatchEvidence:
    material_batch_id: UUID
    material_batch_version: int
    material_class_ref: str
    batch_reference: str
    manufacturer_ref: str
    supplier_ref: str
    quantity: Quantity
    certificate_evidence_ids: tuple[UUID, ...]
    passport_evidence_ids: tuple[UUID, ...]
    incoming_control_id: UUID | None
    custody_chain_complete: bool
    applicable_to_work: bool
    authority: ProfessionalAuthority
    conflict_ids: tuple[UUID, ...] = ()
    gap_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialAdmissionResult:
    outcome: MaterialAdmission
    reason_codes: tuple[str, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "reason_codes": self.reason_codes}


@dataclass(frozen=True, slots=True)
class CalibrationEvidence:
    calibration_id: UUID
    instrument_identity: str
    valid_from: datetime
    valid_until: datetime
    evidence_link_id: UUID

    def valid_at(self, observed_at: datetime) -> bool:
        return self.valid_from <= observed_at < self.valid_until


@dataclass(frozen=True, slots=True)
class ControlEvidence:
    control_operation_id: UUID
    control_operation_version: int
    method_version: str
    criterion: str
    observed_value: Decimal | None
    tolerance: Decimal | None
    unit_code: str | None
    performed_at: datetime
    performed_fact_id: UUID
    performed_fact_version: int
    evidence_link_id: UUID
    rule_trace_id: UUID
    authority: ProfessionalAuthority
    calibration: CalibrationEvidence | None
    calibration_required: bool
    supersedes_control_result_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ControlResult:
    outcome: ControlOutcome
    reason_codes: tuple[str, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "reason_codes": self.reason_codes}


@dataclass(frozen=True, slots=True)
class OfflineFactEnvelope:
    observation_id: UUID
    device_identity: str
    acquisition_method: str
    observed_at: datetime
    timestamp_authority_ref: str
    actor_identity: str
    fact_payload_digest: str
    evidence_link_id: UUID
    source_locator_id: UUID
    sync_lineage_id: UUID
    coordinate_frame_ref: str | None = None
    unit_code: str | None = None
    precision_scale: int | None = None
    calibration_id: UUID | None = None

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class OfflineReconciliation:
    disposition: OfflineDisposition
    canonical_fingerprint: str
    conflict_fingerprints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentRequirementEvidence:
    requirement_id: UUID
    requirement_version: int
    applicability: Applicability
    rule_version_ref: str
    rule_trace_id: UUID
    source_version_id: UUID
    source_locator_id: UUID
    required_stage: str
    required_authority_class: str


@dataclass(frozen=True, slots=True)
class DocumentCoverageEvidence:
    requirement_id: UUID
    requirement_version: int
    status: str
    evidence_link_ids: tuple[UUID, ...]
    authority_verified: bool


@dataclass(frozen=True, slots=True)
class CompletenessDelta:
    required: tuple[UUID, ...]
    covered: tuple[UUID, ...]
    missing: tuple[UUID, ...]
    indeterminate: tuple[UUID, ...]
    blocked: tuple[UUID, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    @property
    def complete(self) -> bool:
        return not self.missing and not self.indeterminate and not self.blocked

    def _payload(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "covered": self.covered,
            "missing": self.missing,
            "indeterminate": self.indeterminate,
            "blocked": self.blocked,
        }


@dataclass(frozen=True, slots=True)
class FieldResolution:
    field_key: str
    state: ResolutionState
    normalized_value: str | Decimal | None
    display_value: str | None
    fact_id: UUID | None
    fact_version: int | None
    evidence_link_ids: tuple[UUID, ...]
    source_locator_ids: tuple[UUID, ...]
    material: bool = True

    def __post_init__(self) -> None:
        if self.state is ResolutionState.CONFIRMED:
            if self.fact_id is None or self.fact_version is None or not self.evidence_link_ids:
                raise ValueError("Confirmed field requires FactVersion and evidence")
            if not self.source_locator_ids:
                raise ValueError("Confirmed material field requires a source locator")
        if self.state is not ResolutionState.CONFIRMED and self.material:
            if self.normalized_value not in (None, ""):
                raise ValueError("Unconfirmed material fields cannot carry a filled value")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    generation_request_id: UUID
    generation_run_id: UUID
    required_document_type_ref: str
    template_version_ref: str
    field_schema_version: str
    binding_plan_version: str
    renderer_profile_version: str
    validator_profile_version: str
    requested_format: str
    fields: tuple[FieldResolution, ...]
    rule_set_version_id: UUID
    policy_versions: tuple[str, ...]
    idempotency_key: str

    def __post_init__(self) -> None:
        exact_versions = (
            self.template_version_ref,
            self.field_schema_version,
            self.binding_plan_version,
            self.renderer_profile_version,
            self.validator_profile_version,
            *self.policy_versions,
        )
        if any(
            version.lower() == "latest" or version.lower().endswith(":latest")
            for version in exact_versions
        ):
            raise ValueError("Generation requires exact immutable versions; latest is forbidden")
        if self.requested_format not in {"DOCX", "XLSX"}:
            raise ValueError("The WP-13 qualification slice supports DOCX and XLSX only")

    @property
    def input_fingerprint(self) -> str:
        return digest_of(
            {
                "required_document_type_ref": self.required_document_type_ref,
                "template_version_ref": self.template_version_ref,
                "field_schema_version": self.field_schema_version,
                "binding_plan_version": self.binding_plan_version,
                "renderer_profile_version": self.renderer_profile_version,
                "validator_profile_version": self.validator_profile_version,
                "requested_format": self.requested_format,
                "fields": [
                    {
                        "field_key": item.field_key,
                        "state": item.state,
                        "normalized_value": (
                            str(item.normalized_value)
                            if isinstance(item.normalized_value, Decimal)
                            else item.normalized_value
                        ),
                        "display_value": item.display_value,
                        "fact_id": item.fact_id,
                        "fact_version": item.fact_version,
                        "evidence_link_ids": item.evidence_link_ids,
                        "source_locator_ids": item.source_locator_ids,
                        "material": item.material,
                    }
                    for item in self.fields
                ],
                "rule_set_version_id": self.rule_set_version_id,
                "policy_versions": self.policy_versions,
            }
        )


@dataclass(frozen=True, slots=True)
class GeneratedDocumentCandidate:
    generation_run_id: UUID
    format: str
    semantic_fingerprint: str
    bytes_digest: str
    package_bytes: bytes = field(repr=False, compare=False)
    structural_checks: tuple[str, ...] = ()
    print_validation_level: str = "synthetic_structural_only"


@dataclass(frozen=True, slots=True)
class GeometryInput:
    geometry_input_id: UUID
    geometry_kind: str
    fact_id: UUID
    fact_version: int
    source_version_id: UUID
    source_locator_id: UUID
    crs_ref: str | None
    reference_frame_ref: str | None
    unit_code: str | None
    precision_scale: int | None
    points: tuple[tuple[Decimal, Decimal], ...]
    confirmed: bool
    confirmation_identity_kind: str
    measurement_method_ref: str
    calibration_valid: bool


@dataclass(frozen=True, slots=True)
class ExecutiveSchemeResult:
    outcome: GeometryOutcome
    scheme_fingerprint: str | None
    tolerance_outcomes: tuple[str, ...]
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommercialReadinessInput:
    work_volume: Quantity
    presented_volume: Quantity
    id_complete: bool
    evidence_complete: bool
    contract_conditions_satisfied: bool
    ks_quantity: Quantity
    ks_rate: Decimal
    ks_amount: Decimal
    currency_code: str
    payment_recorded: bool = False


@dataclass(frozen=True, slots=True)
class CommercialReadiness:
    presented_eligible: bool
    ks_consistent: bool
    payment_ready: bool
    blocker_codes: tuple[str, ...]
    calculated_amount: Decimal
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "presented_eligible": self.presented_eligible,
            "ks_consistent": self.ks_consistent,
            "payment_ready": self.payment_ready,
            "blocker_codes": self.blocker_codes,
            "calculated_amount": str(self.calculated_amount),
        }


@dataclass(frozen=True, slots=True)
class SupportTerminalResult:
    outcome: str
    support_process_id: UUID
    deliverable_refs: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    archive_manifest_digest: str | None
    product_ready: bool = False
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.product_ready:
            raise ValueError("A Support slice cannot establish ProductReady")
        if self.outcome == "completed" and (
            self.blocker_codes or not self.deliverable_refs or self.archive_manifest_digest is None
        ):
            raise ValueError("Successful Support terminal result requires outputs and no blockers")
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "support_process_id": self.support_process_id,
            "deliverable_refs": self.deliverable_refs,
            "blocker_codes": self.blocker_codes,
            "uncertainty_codes": self.uncertainty_codes,
            "archive_manifest_digest": self.archive_manifest_digest,
            "product_ready": self.product_ready,
        }
