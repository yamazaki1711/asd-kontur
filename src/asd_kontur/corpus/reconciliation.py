"""Exact receipt and logical-document reconciliation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from uuid import UUID

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of

from .models import (
    BoundaryCandidate,
    BoundaryDisposition,
    BoundaryValidation,
    CorpusOutcome,
    CorpusReconciliation,
    ProcessingPlan,
    ProcessingReceipt,
    ReceiptStatus,
)


def validate_boundary(
    candidate: BoundaryCandidate,
    *,
    page_count: int,
    validator_version: str,
    authority_decision_ref: str | None = None,
) -> BoundaryValidation:
    failures: list[str] = []
    if candidate.start_page < 1 or candidate.end_page > page_count:
        failures.append("BOUNDARY_OUT_OF_RANGE")
    if candidate.start_page > candidate.end_page:
        failures.append("BOUNDARY_REVERSED")
    if not candidate.evidence_receipt_ids:
        failures.append("BOUNDARY_EVIDENCE_MISSING")
    if failures:
        return BoundaryValidation(
            candidate.boundary_candidate_id,
            BoundaryDisposition.REJECTED,
            validator_version,
            tuple(failures),
            None,
        )
    if authority_decision_ref is None:
        return BoundaryValidation(
            candidate.boundary_candidate_id,
            BoundaryDisposition.UNRESOLVED,
            validator_version,
            ("BOUNDARY_AUTHORITY_MISSING",),
            None,
        )
    return BoundaryValidation(
        candidate.boundary_candidate_id,
        BoundaryDisposition.ACCEPTED,
        validator_version,
        (),
        authority_decision_ref,
    )


def validate_boundary_set(
    candidates: Iterable[BoundaryCandidate], *, page_count: int
) -> tuple[str, ...]:
    """Detect gaps and semantic overlaps; processing overlap is handled before this step."""
    ordered = sorted(candidates, key=lambda candidate: (candidate.start_page, candidate.end_page))
    failures: list[str] = []
    previous_end = 0
    for candidate in ordered:
        if candidate.start_page < 1 or candidate.end_page > page_count:
            failures.append("BOUNDARY_OUT_OF_RANGE")
        if candidate.start_page > previous_end + 1:
            failures.append("BOUNDARY_GAP")
        if candidate.start_page <= previous_end:
            failures.append("BOUNDARY_OVERLAP")
        previous_end = max(previous_end, candidate.end_page)
    if ordered and previous_end < page_count:
        failures.append("BOUNDARY_GAP")
    return tuple(sorted(set(failures)))


def reconcile_processing(
    plan: ProcessingPlan,
    receipts: Iterable[ProcessingReceipt],
    *,
    unresolved_segments: tuple[tuple[int, int], ...] = (),
    accepted_occurrence_ids: tuple[UUID, ...] = (),
) -> CorpusReconciliation:
    exact_receipts = tuple(receipts)
    expected = tuple(page.page_number for page in plan.page_plans)
    logical_receipts = tuple(receipt for receipt in exact_receipts if not receipt.context_only)
    validated_counts = Counter(
        receipt.page_number
        for receipt in logical_receipts
        if receipt.status is ReceiptStatus.VALIDATED
    )
    duplicate = tuple(sorted(page for page, count in validated_counts.items() if count > 1))
    by_page: dict[int, list[ProcessingReceipt]] = defaultdict(list)
    for receipt in exact_receipts:
        if receipt.plan_id != plan.processing_plan_id or receipt.plan_version != plan.version:
            raise ValueError("Receipt belongs to a different immutable processing plan")
        if receipt.context_only:
            continue
        by_page[receipt.page_number].append(receipt)
    validated = tuple(
        page
        for page in expected
        if any(receipt.status is ReceiptStatus.VALIDATED for receipt in by_page.get(page, ()))
    )
    failed = tuple(
        page
        for page in expected
        if by_page.get(page)
        and not any(receipt.status is ReceiptStatus.VALIDATED for receipt in by_page[page])
        and any(receipt.status is ReceiptStatus.FAILED for receipt in by_page[page])
    )
    unknown = tuple(
        page
        for page in expected
        if not any(receipt.status is ReceiptStatus.VALIDATED for receipt in by_page.get(page, ()))
        and (
            not by_page.get(page)
            or any(receipt.status is ReceiptStatus.UNKNOWN for receipt in by_page[page])
        )
    )
    if duplicate:
        outcome = CorpusOutcome.RECOVERY_REQUIRED
    elif not expected:
        outcome = CorpusOutcome.UNRESOLVED
    elif len(validated) == len(expected) and not unresolved_segments:
        outcome = CorpusOutcome.COMPLETE
    elif failed and not validated:
        outcome = CorpusOutcome.PROVIDER_FAILED
    elif unknown or unresolved_segments:
        outcome = CorpusOutcome.UNRESOLVED
    elif failed:
        outcome = CorpusOutcome.PARTIAL
    else:
        outcome = CorpusOutcome.PARTIAL
    return CorpusReconciliation(
        plan.scope,
        uuid7(),
        plan.processing_plan_id,
        plan.version,
        expected,
        validated,
        failed,
        unknown,
        duplicate,
        unresolved_segments,
        accepted_occurrence_ids,
        outcome,
        digest_of(exact_receipts),
    )
