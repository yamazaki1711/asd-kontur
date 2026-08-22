from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from asd_kontur.kernel import Applicability, Mode
from asd_kontur.tender import (
    AuthorityLayer,
    ClauseProvenance,
    ContractClause,
    CorpusItem,
    LegalAuthority,
    RiskSubject,
    Severity,
    SourceClass,
    TenderDeliverableKind,
    TenderError,
    TenderFinalizationDecision,
    TenderIssue,
    TenderIssueKind,
    TenderScope,
    TenderTerminalOutcome,
    TenderValidationCode,
    TenderValidationInput,
    TypedTenderDeliverable,
    assess_corpus,
    product_ready,
    terminal_outcome_for,
    validate_tender,
)

DIGEST = "sha256:" + "a" * 64


def _clause() -> ContractClause:
    return ContractClause(
        uuid4(),
        1,
        "clause.synthetic.4.2",
        DIGEST,
        AuthorityLayer.CONTRACT,
        ClauseProvenance(uuid4(), uuid4(), uuid4(), uuid4(), 1),
    )


def _issue(**overrides: object) -> TenderIssue:
    values: dict[str, object] = {
        "issue_id": uuid4(),
        "issue_version": 1,
        "kind": TenderIssueKind.CONTRACT_RISK,
        "subject": RiskSubject.PAYMENT,
        "severity": Severity.HIGH,
        "applicability": Applicability.APPLICABLE,
        "clause": _clause(),
        "requirement_id": uuid4(),
        "rule_set_version_id": uuid4(),
        "rule_trace_id": uuid4(),
        "evidence_refs": (uuid4(),),
        "uncertainty_code": None,
        "recommended_change": "Synthetic proposed wording.",
        "consequence_code": "PAYMENT_TERM_RISK",
    }
    values.update(overrides)
    return TenderIssue(**values)  # type: ignore[arg-type]


def test_tender_scope_is_one_mode_and_pins_versions() -> None:
    scope = TenderScope(uuid4(), uuid4(), uuid4(), "1.0.0", uuid4(), "1.0.0", ("1.0.0",), "1.2.0")
    assert scope.mode is Mode.TENDER
    with pytest.raises(TenderError):
        TenderScope(uuid4(), uuid4(), uuid4(), "latest", uuid4(), "1.0.0", ("1.0.0",), "1.2.0")


def test_corpus_gap_is_explicit_and_never_no_risk() -> None:
    source = uuid4()
    locator = uuid4()
    evidence = uuid4()
    assessment = assess_corpus(
        (CorpusItem(SourceClass.TENDER_DOCUMENTATION, source, locator, evidence, True),)
    )
    assert assessment.status == "blocked"
    assert assessment.missing_classes == (SourceClass.DRAFT_CONTRACT,)
    assert assessment.fingerprint.startswith("sha256:")


def test_material_finding_requires_clause_evidence_and_rule_trace() -> None:
    with pytest.raises(TenderError):
        _issue(clause=None, evidence_refs=())
    first = _issue()
    second = replace(first)
    assert first.fingerprint == second.fingerprint


def test_indeterminate_clause_creates_uncertainty_and_blocks_terminal_success() -> None:
    issue = _issue(
        kind=TenderIssueKind.CONFLICT,
        applicability=Applicability.INDETERMINATE,
        uncertainty_code="NTD_EDITION_AMBIGUOUS",
    )
    assert terminal_outcome_for((issue,)) == "blocked_unresolved_conflict"
    with pytest.raises(TenderError):
        _issue(applicability=Applicability.INDETERMINATE, uncertainty_code=None)


def test_unknown_cost_or_volume_is_uncertainty_not_zero() -> None:
    issue = _issue(
        kind=TenderIssueKind.UNCERTAINTY,
        subject=RiskSubject.VOLUME,
        applicability=Applicability.INDETERMINATE,
        clause=None,
        evidence_refs=(),
        uncertainty_code="VOLUME_NOT_PROVIDED",
        recommended_change=None,
    )
    assert terminal_outcome_for((issue,)) == "blocked_material_uncertainty"


def test_model_identity_cannot_review_or_finalize() -> None:
    with pytest.raises(TenderError):
        LegalAuthority(
            "model:draft-provider", uuid4(), 1, "tender.legal.review", "qualification:test", True
        )


def test_independent_human_authorities_are_required() -> None:
    reviewer = LegalAuthority(
        "human:reviewer", uuid4(), 1, "tender.legal.review", "qualification:legal", True
    )
    same_human = LegalAuthority(
        "human:reviewer", uuid4(), 1, "tender.legal.finalize", "qualification:legal", True
    )
    with pytest.raises(TenderError):
        TenderFinalizationDecision(
            uuid4(),
            reviewer,
            same_human,
            tuple(uuid4() for _ in range(5)),
            TenderTerminalOutcome.SUCCESS,
            (),
        )


def test_typed_outputs_are_distinct_and_finalized_output_has_no_blockers() -> None:
    kinds = set(TenderDeliverableKind)
    assert len(kinds) == 5
    with pytest.raises(TenderError):
        TypedTenderDeliverable(
            uuid4(),
            1,
            TenderDeliverableKind.REVISED_CONTRACT,
            (uuid4(),),
            DIGEST,
            DIGEST,
            uuid4(),
            "finalized",
            (uuid4(),),
            (),
        )


def test_tender_success_does_not_make_product_ready() -> None:
    assert not product_ready(
        tender_ready=True, support_ready=False, audit_ready=False, restoration_ready=False
    )
    assert product_ready(
        tender_ready=True, support_ready=True, audit_ready=True, restoration_ready=True
    )


def test_deterministic_tender_validators_fail_closed_for_missing_and_conflicting_inputs() -> None:
    failures = validate_tender(
        TenderValidationInput(
            "1.0.0",
            ("subject", "price", "acceptance"),
            ("subject",),
            contradictory_clause_pairs=(("clause.a", "clause.b"),),
            ambiguous_terms=("reasonable period",),
            normative_reference_present=True,
            normative_edition_resolved=False,
            customer_regulation_conflicts_ntd=True,
            responsibility_allocated=False,
            deadline_defined=False,
            acceptance_basis_defined=False,
            payment_basis_defined=False,
            volume_confirmed=False,
            cost_confirmed=False,
            omitted_work_ids=("work.synthetic.1",),
            omitted_material_ids=("material.synthetic.1",),
            geometry_relevant=True,
            geometry_source_confirmed=False,
            crs_known=False,
            units_known=False,
        )
    )
    codes = {failure.code for failure in failures}
    assert {
        TenderValidationCode.REQUIRED_SECTION_MISSING,
        TenderValidationCode.CLAUSE_CONFLICT,
        TenderValidationCode.NTD_EDITION_AMBIGUOUS,
        TenderValidationCode.CUSTOMER_REGULATION_NTD_CONFLICT,
        TenderValidationCode.VOLUME_UNCONFIRMED,
        TenderValidationCode.COST_UNCONFIRMED,
        TenderValidationCode.WORK_OMITTED,
        TenderValidationCode.MATERIAL_OMITTED,
        TenderValidationCode.GEOMETRY_INSUFFICIENT,
    } <= codes
    geometry = next(
        failure
        for failure in failures
        if failure.code is TenderValidationCode.GEOMETRY_INSUFFICIENT
    )
    assert geometry.blocker
    assert geometry.required_inputs == ("confirmed_geometry_source", "crs", "units")


def test_validator_fingerprint_is_repeatable_and_customer_regulation_does_not_override_ntd() -> (
    None
):
    value = TenderValidationInput(
        "1.0.0",
        ("subject",),
        ("subject",),
        customer_regulation_conflicts_ntd=True,
    )
    first = validate_tender(value)
    second = validate_tender(value)
    assert first == second
    assert first[0].code is TenderValidationCode.CUSTOMER_REGULATION_NTD_CONFLICT
    assert first[0].applicability is Applicability.INDETERMINATE
