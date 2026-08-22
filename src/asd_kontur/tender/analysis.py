"""Deterministic Tender checks over confirmed, evidence-bound inputs."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from asd_kontur.kernel import Applicability

from .models import (
    CorpusAssessment,
    CorpusItem,
    RiskSubject,
    SourceClass,
    TenderIssue,
    TenderIssueKind,
)

MANDATORY_TENDER_SOURCE_CLASSES = (
    SourceClass.TENDER_DOCUMENTATION,
    SourceClass.DRAFT_CONTRACT,
)


def assess_corpus(
    items: Iterable[CorpusItem],
    *,
    required: tuple[SourceClass, ...] = MANDATORY_TENDER_SOURCE_CLASSES,
) -> CorpusAssessment:
    accepted = tuple(sorted({item.source_class for item in items if item.accepted}, key=str))
    missing = tuple(item for item in required if item not in accepted)
    optional_absent = tuple(
        item for item in SourceClass if item not in required and item not in accepted
    )
    return CorpusAssessment(
        required,
        accepted,
        missing,
        optional_absent,
        "blocked" if missing else "assessed_with_explicit_limits",
    )


def terminal_outcome_for(
    issues: Iterable[TenderIssue], *, confirmed_issue_ids: frozenset[UUID] = frozenset()
) -> str:
    material = tuple(issues)
    if any(
        issue.kind is TenderIssueKind.GAP and issue.severity.value == "blocking"
        for issue in material
    ):
        return "blocked_incomplete_corpus"
    if any(
        issue.kind is TenderIssueKind.CONFLICT
        and issue.applicability is Applicability.INDETERMINATE
        for issue in material
    ):
        return "blocked_unresolved_conflict"
    if any(
        issue.subject in (RiskSubject.VOLUME, RiskSubject.PRICE, RiskSubject.GEOMETRY)
        and issue.applicability is Applicability.INDETERMINATE
        for issue in material
    ):
        return "blocked_material_uncertainty"
    if any(
        issue.severity.value == "blocking" and issue.issue_id not in confirmed_issue_ids
        for issue in material
    ):
        return "blocked_authority"
    return "successful"


def product_ready(
    *, tender_ready: bool, support_ready: bool, audit_ready: bool, restoration_ready: bool
) -> bool:
    """The product gate is conjunctive; a Tender success can never bypass it."""

    return tender_ready and support_ready and audit_ready and restoration_ready
