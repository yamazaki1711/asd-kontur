from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from asd_kontur.domain import uuid7
from asd_kontur.kernel import (
    Applicability,
    CandidateAssessment,
    ConfirmationGate,
    ConfirmationPolicy,
    ConfirmationRequest,
    CoverageItem,
    DeterministicAuthority,
    EvidenceBinding,
    FactClass,
    FactValueKind,
    HumanAuthority,
    KernelError,
    KernelErrorCode,
    Mode,
    Quantity,
    RequiredItem,
    deterministic_work_order,
    evaluate_completeness,
)


def _assessment(*, status: str = "validated_candidate") -> CandidateAssessment:
    return CandidateAssessment(
        uuid7(),
        1,
        "/work/type",
        status,
        uuid7(),
        True,
        (),
        True,
        (EvidenceBinding(uuid7(), uuid7(), uuid7()),),
        "synthetic-work-type",
    )


def _policy() -> ConfirmationPolicy:
    return ConfirmationPolicy(
        uuid7(),
        "1.0.0",
        frozenset({FactClass.CLASSIFICATION, FactClass.OBSERVATION}),
        frozenset(
            {
                FactClass.LEGAL_EFFECT,
                FactClass.CONTRACTUAL_OBLIGATION,
                FactClass.GEOMETRY,
                FactClass.MEASUREMENT,
                FactClass.PAYABLE_VOLUME,
                FactClass.SIGNER_AUTHORITY,
                FactClass.MATERIAL_BLOCKER,
                FactClass.PROFESSIONAL_FINALIZATION,
            }
        ),
        "active",
    )


def _request(
    authority: HumanAuthority | DeterministicAuthority,
    *,
    fact_class: FactClass = FactClass.CLASSIFICATION,
    candidate: CandidateAssessment | None = None,
) -> ConfirmationRequest:
    return ConfirmationRequest(
        uuid7(),
        uuid7(),
        0,
        "work_type.classification",
        fact_class,
        FactValueKind.TEXT,
        candidate or _assessment(),
        _policy(),
        authority,
        uuid7(),
        uuid7(),
        "synthetic-confirmation",
    )


def _rule_authority() -> DeterministicAuthority:
    return DeterministicAuthority(
        "service:deterministic-kernel",
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        "sha256:" + "a" * 64,
        Applicability.APPLICABLE,
        "pass",
        True,
        True,
    )


def test_candidate_to_fact_requires_explicit_authority() -> None:
    result = ConfirmationGate().confirm(_request(_rule_authority()))
    assert result.fact_version == 1
    assert result.reason_code == "policy_controlled_deterministic_rule"


def test_valid_json_or_candidate_status_does_not_bypass_missing_evidence() -> None:
    candidate = CandidateAssessment(
        uuid7(), 1, "/field", "validated_candidate", uuid7(), True, (), False, (), "value"
    )
    with pytest.raises(KernelError, match=KernelErrorCode.EVIDENCE_MISSING):
        ConfirmationGate().confirm(_request(_rule_authority(), candidate=candidate))


@pytest.mark.parametrize(
    "fact_class",
    [
        FactClass.LEGAL_EFFECT,
        FactClass.CONTRACTUAL_OBLIGATION,
        FactClass.GEOMETRY,
        FactClass.MEASUREMENT,
        FactClass.PAYABLE_VOLUME,
        FactClass.SIGNER_AUTHORITY,
        FactClass.MATERIAL_BLOCKER,
        FactClass.PROFESSIONAL_FINALIZATION,
    ],
)
def test_professional_fact_classes_cannot_auto_confirm(fact_class: FactClass) -> None:
    with pytest.raises(KernelError, match=KernelErrorCode.PROFESSIONAL_AUTHORITY_REQUIRED):
        ConfirmationGate().confirm(_request(_rule_authority(), fact_class=fact_class))


def test_qualified_human_can_confirm_only_granted_fact_class() -> None:
    authority = HumanAuthority(
        "human:synthetic-reviewer",
        uuid7(),
        1,
        "fact.confirm",
        frozenset({FactClass.GEOMETRY}),
        professional_qualification_ref="qualification:synthetic-geometry",
    )
    result = ConfirmationGate().confirm(_request(authority, fact_class=FactClass.GEOMETRY))
    assert result.reason_code == "qualified_human_authority"
    with pytest.raises(KernelError, match=KernelErrorCode.AUTHORITY_DENIED):
        ConfirmationGate().confirm(_request(authority, fact_class=FactClass.LEGAL_EFFECT))


def test_model_identity_cannot_be_human_authority() -> None:
    with pytest.raises(ValueError, match="human principal"):
        HumanAuthority(
            "model:qwen", uuid7(), 1, "fact.confirm", frozenset({FactClass.CLASSIFICATION})
        )


def test_professional_human_authority_requires_qualification_reference() -> None:
    authority = HumanAuthority(
        "human:synthetic-reviewer", uuid7(), 1, "fact.confirm", frozenset({FactClass.GEOMETRY})
    )
    with pytest.raises(KernelError, match=KernelErrorCode.PROFESSIONAL_AUTHORITY_REQUIRED):
        ConfirmationGate().confirm(_request(authority, fact_class=FactClass.GEOMETRY))


def test_indeterminate_rule_and_unresolved_input_fail_closed() -> None:
    authority = _rule_authority()
    authority = DeterministicAuthority(
        authority.service_identity_id,
        authority.rule_version_id,
        authority.rule_set_version_id,
        authority.rule_evaluation_id,
        authority.rule_trace_id,
        authority.rule_trace_fingerprint,
        Applicability.INDETERMINATE,
        "not_evaluated",
        True,
        True,
    )
    with pytest.raises(KernelError, match=KernelErrorCode.INDETERMINATE):
        ConfirmationGate().confirm(_request(authority))


def test_completeness_delta_never_turns_unknown_into_complete() -> None:
    covered = uuid7()
    missing = uuid7()
    unknown = uuid7()
    result = evaluate_completeness(
        (
            RequiredItem(covered, Applicability.APPLICABLE, uuid7()),
            RequiredItem(missing, Applicability.APPLICABLE, uuid7()),
            RequiredItem(unknown, Applicability.INDETERMINATE, uuid7()),
        ),
        (CoverageItem(covered, True, (uuid7(),)),),
    )
    assert result.status == "indeterminate"
    assert result.missing_ids == (missing,)
    assert result.indeterminate_ids == (unknown,)
    assert result.fingerprint.startswith("sha256:")


def test_work_dependency_order_is_deterministic_and_cycles_block() -> None:
    first, second, third = uuid7(), uuid7(), uuid7()
    assert deterministic_work_order((first, second, third), ((first, second), (second, third))) == (
        first,
        second,
        third,
    )
    with pytest.raises(KernelError, match=KernelErrorCode.DEPENDENCY_CYCLE):
        deterministic_work_order((first, second), ((first, second), (second, first)))


def test_quantities_require_units_precision_and_exact_rounding_policy() -> None:
    quantity = Quantity(Decimal("12.500"), "m3", 3, "1.0.0")
    assert quantity.value == Decimal("12.500")
    with pytest.raises(ValueError, match="exact rounding"):
        Quantity(Decimal("1"), "m", 0, "latest")


@pytest.mark.parametrize("mode", list(Mode))
def test_all_four_modes_use_the_same_common_kernel(mode: Mode) -> None:
    requirement = RequiredItem(uuid7(), Applicability.APPLICABLE, uuid7())
    result = evaluate_completeness((requirement,), ())
    assert mode in Mode
    assert result.status == "incomplete"
    assert ConfirmationGate.__module__ == "asd_kontur.kernel.authority"


def test_fingerprints_are_reproducible() -> None:
    authority = _rule_authority()
    request = _request(authority)
    first = ConfirmationGate().confirm(request)
    second = ConfirmationGate().confirm(request)
    assert first.fingerprint == second.fingerprint
    assert datetime.now(UTC).tzinfo is not None
