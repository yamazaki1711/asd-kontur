from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from asd_kontur.ntd.rules import (
    DeonticType,
    NormativeRuleCandidate,
    RuleActivationStatus,
    RuleQualificationStatus,
    SemanticEvidenceBinding,
    decide_rule_activation,
    qualify_rule_candidate,
)


def _candidate(*, edition_id: UUID | None = None) -> NormativeRuleCandidate:
    text = "10.8 Запрещается проводить ремонт оборудования, находящегося под давлением."
    return NormativeRuleCandidate.create(
        normative_document_id=UUID("10000000-0000-0000-0000-000000000001"),
        normative_edition_id=edition_id or UUID("20000000-0000-0000-0000-000000000001"),
        source_version_id=UUID("30000000-0000-0000-0000-000000000001"),
        normative_provision_id=UUID("40000000-0000-0000-0000-000000000001"),
        normative_provision_version=1,
        source_locator_id=UUID("50000000-0000-0000-0000-000000000001"),
        structural_path="10.8",
        verbatim_text=text,
        deontic_type=DeonticType.PROHIBITION,
        actor={"kind": "work_performer"},
        regulated_object={"kind": "pressurized_equipment"},
        required_action={"action": "repair", "prohibited": True},
        applicability_predicate={"field": "equipment.pressurized", "operator": "eq", "value": True},
        output_contract={"violation": "repair_under_pressure"},
        evidence_bindings=(
            SemanticEvidenceBinding("deontic_type", ("Запрещается",)),
            SemanticEvidenceBinding("actor", ("проводить ремонт",)),
            SemanticEvidenceBinding("regulated_object", ("оборудования",)),
            SemanticEvidenceBinding("required_action", ("ремонт",)),
            SemanticEvidenceBinding("applicability_predicate", ("под давлением",)),
        ),
        interpretation_profile_version="rule-candidate-manifest-v1",
    )


def _qualification(candidate: NormativeRuleCandidate):
    return qualify_rule_candidate(
        candidate,
        provision_verification_status="verified",
        evidence_edition_id=candidate.normative_edition_id,
        evidence_source_version_id=candidate.source_version_id,
        evidence_locator_id=candidate.source_locator_id,
        evidence_verbatim_text=candidate.verbatim_text,
        qualification_profile_version="normative-rule-qualification-v1",
        test_manifest_digest="sha256:" + "1" * 64,
    )


def test_rule_candidate_identity_is_deterministic_and_edition_pinned() -> None:
    first = _candidate()
    assert first == _candidate()
    other_edition = _candidate(edition_id=uuid4())
    assert other_edition.candidate_id != first.candidate_id
    assert other_edition.semantic_fingerprint != first.semantic_fingerprint


def test_rule_candidate_rejects_missing_locator_verbatim_and_field_evidence() -> None:
    candidate = _candidate()
    with pytest.raises(ValueError, match="locator and verbatim"):
        replace(candidate, structural_path="")
    with pytest.raises(ValueError, match="Essential rule semantics"):
        replace(candidate, evidence_bindings=candidate.evidence_bindings[:3])
    with pytest.raises(ValueError, match="absent from the verbatim"):
        replace(
            candidate,
            evidence_bindings=(
                *candidate.evidence_bindings,
                SemanticEvidenceBinding("conditions", ("invented condition",)),
            ),
        )


def test_qualification_is_reproducible_and_blocks_unproven_semantics() -> None:
    candidate = _candidate()
    first = _qualification(candidate)
    assert first == _qualification(candidate)
    assert first.status is RuleQualificationStatus.QUALIFIED

    failed = qualify_rule_candidate(
        candidate,
        provision_verification_status="verified",
        evidence_edition_id=uuid4(),
        evidence_source_version_id=candidate.source_version_id,
        evidence_locator_id=candidate.source_locator_id,
        evidence_verbatim_text=candidate.verbatim_text,
        qualification_profile_version="normative-rule-qualification-v1",
        test_manifest_digest="sha256:" + "1" * 64,
    )
    assert failed.status is RuleQualificationStatus.BLOCKED
    assert dict((name, passed) for name, passed, _ in failed.gate_results)["exact_edition"] is False


def test_activation_separates_qualification_edition_and_rule_lifecycle() -> None:
    candidate = _candidate()
    qualification = _qualification(candidate)
    warning = decide_rule_activation(
        candidate,
        qualification,
        edition_activation_status="not_activated",
        rule_lifecycle_status="approved",
    )
    assert warning.status is RuleActivationStatus.NOT_ACTIVATED
    assert warning.reason_code == "NORMATIVE_EDITION_NOT_ACTIVATED"

    pending_human = decide_rule_activation(
        candidate,
        qualification,
        edition_activation_status="active",
        rule_lifecycle_status="approved",
    )
    assert pending_human.status is RuleActivationStatus.NOT_ACTIVATED
    assert pending_human.reason_code == "RULE_HUMAN_APPROVAL_NOT_ACTIVE"

    active = decide_rule_activation(
        candidate,
        qualification,
        edition_activation_status="active",
        rule_lifecycle_status="active",
    )
    assert active.status is RuleActivationStatus.ACTIVE
    assert active.reason_code == "QUALIFIED_RULE_AND_EDITION_ACTIVE"


def test_unqualified_candidate_never_activates() -> None:
    candidate = _candidate()
    qualification = replace(_qualification(candidate), status=RuleQualificationStatus.BLOCKED)
    decision = decide_rule_activation(
        candidate,
        qualification,
        edition_activation_status="active",
        rule_lifecycle_status="active",
    )
    assert decision.status is RuleActivationStatus.BLOCKED
    assert decision.reason_code == "RULE_QUALIFICATION_NOT_PASSED"
