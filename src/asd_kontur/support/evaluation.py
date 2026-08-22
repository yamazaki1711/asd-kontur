"""Deterministic Support evaluations over confirmed WP-11 inputs."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from asd_kontur.kernel.models import Applicability

from .models import (
    CommercialReadiness,
    CommercialReadinessInput,
    CompletenessDelta,
    ControlEvidence,
    ControlOutcome,
    ControlResult,
    DocumentCoverageEvidence,
    DocumentRequirementEvidence,
    MaterialAdmission,
    MaterialAdmissionResult,
    MaterialBatchEvidence,
    WorkReadiness,
    WorkReadinessInput,
    WorkReadinessResult,
)


def evaluate_work_readiness(value: WorkReadinessInput) -> WorkReadinessResult:
    reasons: list[str] = []
    if not value.planned:
        reasons.append("WORK_NOT_PLANNED")
    if value.performed_fact_id is None or value.performed_fact_version is None:
        reasons.append("PERFORMED_FACT_MISSING")
    if any(state not in {"performed", "accepted"} for state in value.predecessor_states):
        reasons.append("PREDECESSOR_NOT_COMPLETE")
    if any(state != "passed" for state in value.prestart_control_states):
        reasons.append("PRESTART_CONTROL_NOT_PASSED")
    if any(state is not MaterialAdmission.ADMITTED for state in value.material_states):
        reasons.append("MATERIAL_NOT_ADMITTED")
    if any(state != "satisfied" for state in value.evidence_checkpoint_states):
        reasons.append("EVIDENCE_CHECKPOINT_MISSING")
    if value.hidden_work:
        if value.checkpoint_due_at is None or value.evidence_recorded_at is None:
            reasons.append("HIDDEN_WORK_TIMELY_EVIDENCE_MISSING")
        elif value.evidence_recorded_at > value.checkpoint_due_at:
            reasons.append("HIDDEN_WORK_EVIDENCE_LATE")
    if value.blocking_issue_ids:
        reasons.append("MATERIAL_BLOCKER_OPEN")
    if reasons:
        outcome = (
            WorkReadiness.INDETERMINATE
            if set(reasons) <= {"PERFORMED_FACT_MISSING", "EVIDENCE_CHECKPOINT_MISSING"}
            else WorkReadiness.BLOCKED
        )
        return WorkReadinessResult(outcome, tuple(sorted(reasons)), value.rule_trace_id)
    return WorkReadinessResult(WorkReadiness.READY, (), value.rule_trace_id)


def evaluate_material_admission(value: MaterialBatchEvidence) -> MaterialAdmissionResult:
    reasons: list[str] = []
    if not value.material_class_ref or not value.batch_reference:
        reasons.append("MATERIAL_IDENTITY_MISSING")
    if not value.manufacturer_ref or not value.supplier_ref:
        reasons.append("MATERIAL_ORIGIN_MISSING")
    if not value.certificate_evidence_ids or not value.passport_evidence_ids:
        reasons.append("QUALITY_DOCUMENT_MISSING")
    if value.incoming_control_id is None:
        reasons.append("INCOMING_CONTROL_MISSING")
    if not value.custody_chain_complete:
        reasons.append("CUSTODY_GAP")
    if not value.applicable_to_work:
        reasons.append("MATERIAL_NOT_APPLICABLE_TO_WORK")
    if value.conflict_ids:
        reasons.append("MATERIAL_CONFLICT")
    reasons.extend(value.gap_codes)
    if "MATERIAL_CONFLICT" in reasons:
        outcome = MaterialAdmission.QUARANTINED
    elif reasons:
        outcome = MaterialAdmission.WAITING_FOR_DOCUMENTS
    else:
        outcome = MaterialAdmission.ADMITTED
    return MaterialAdmissionResult(outcome, tuple(sorted(set(reasons))))


def evaluate_control(value: ControlEvidence) -> ControlResult:
    reasons: list[str] = []
    if value.method_version.lower() == "latest":
        reasons.append("CONTROL_METHOD_VERSION_MUTABLE")
    if value.calibration_required:
        if value.calibration is None:
            reasons.append("CALIBRATION_MISSING")
        elif not value.calibration.valid_at(value.performed_at):
            reasons.append("CALIBRATION_EXPIRED")
    if value.observed_value is None or value.tolerance is None or value.unit_code is None:
        reasons.append("CONTROL_INPUT_INCOMPLETE")
    if reasons:
        return ControlResult(ControlOutcome.INDETERMINATE, tuple(sorted(reasons)))
    assert value.observed_value is not None
    assert value.tolerance is not None
    if abs(value.observed_value) > value.tolerance:
        return ControlResult(ControlOutcome.FAILED, ("TOLERANCE_EXCEEDED",))
    return ControlResult(ControlOutcome.PASSED, ())


def evaluate_id_completeness(
    requirements: tuple[DocumentRequirementEvidence, ...],
    coverages: tuple[DocumentCoverageEvidence, ...],
) -> CompletenessDelta:
    coverage_by_key = {(item.requirement_id, item.requirement_version): item for item in coverages}
    required: list[UUID] = []
    covered: list[UUID] = []
    missing: list[UUID] = []
    indeterminate: list[UUID] = []
    blocked: list[UUID] = []
    for requirement in sorted(requirements, key=lambda item: str(item.requirement_id)):
        required.append(requirement.requirement_id)
        if requirement.applicability is Applicability.INDETERMINATE:
            indeterminate.append(requirement.requirement_id)
            continue
        if requirement.applicability is Applicability.NOT_APPLICABLE:
            covered.append(requirement.requirement_id)
            continue
        coverage = coverage_by_key.get(
            (requirement.requirement_id, requirement.requirement_version)
        )
        if coverage is None:
            missing.append(requirement.requirement_id)
        elif coverage.status == "covered" and coverage.authority_verified:
            covered.append(requirement.requirement_id)
        elif coverage.status in {"conflict", "rejected"} or not coverage.authority_verified:
            blocked.append(requirement.requirement_id)
        else:
            missing.append(requirement.requirement_id)
    return CompletenessDelta(
        tuple(required),
        tuple(covered),
        tuple(missing),
        tuple(indeterminate),
        tuple(blocked),
    )


def evaluate_commercial_readiness(value: CommercialReadinessInput) -> CommercialReadiness:
    blockers: list[str] = []
    same_units = (
        value.work_volume.unit_code
        == value.presented_volume.unit_code
        == value.ks_quantity.unit_code
    )
    if not same_units:
        blockers.append("VOLUME_UNIT_MISMATCH")
    if value.presented_volume.value > value.work_volume.value:
        blockers.append("PRESENTED_VOLUME_EXCEEDS_CONFIRMED")
    if value.ks_quantity.value != value.presented_volume.value:
        blockers.append("KS_VOLUME_MISMATCH")
    calculated_amount = value.ks_quantity.value * value.ks_rate
    if calculated_amount != value.ks_amount:
        blockers.append("KS_TOTAL_MISMATCH")
    if not value.id_complete:
        blockers.append("ID_PACKAGE_INCOMPLETE")
    if not value.evidence_complete:
        blockers.append("VOLUME_EVIDENCE_INCOMPLETE")
    if not value.contract_conditions_satisfied:
        blockers.append("CONTRACT_CONDITION_BLOCKED")
    blockers = sorted(set(blockers))
    presented_eligible = not any(
        code
        in {
            "VOLUME_UNIT_MISMATCH",
            "PRESENTED_VOLUME_EXCEEDS_CONFIRMED",
            "ID_PACKAGE_INCOMPLETE",
            "VOLUME_EVIDENCE_INCOMPLETE",
        }
        for code in blockers
    )
    ks_consistent = not any(code.startswith("KS_") for code in blockers)
    payment_ready = presented_eligible and ks_consistent and not blockers
    # A PaymentRecord is an observation only and deliberately does not change entitlement.
    return CommercialReadiness(
        presented_eligible,
        ks_consistent,
        payment_ready,
        tuple(blockers),
        calculated_amount.quantize(Decimal("0.01")),
    )
