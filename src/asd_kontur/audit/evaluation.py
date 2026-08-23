"""Deterministic independent Audit delta evaluation and report assembly."""

from __future__ import annotations

from datetime import UTC, datetime

from asd_kontur.corpus import CorpusOutcome, CorpusSnapshot
from asd_kontur.domain import uuid7

from .models import (
    ActionRequest,
    AuditReport,
    AuditScope,
    AuditTerminalOutcome,
    CausalReadinessDelta,
    DeltaState,
    DocumentDelta,
    EvidenceRatedItem,
    PackageReadiness,
)


def document_readiness_counts(delta: DocumentDelta) -> dict[DeltaState, int]:
    """Expose causal counts; unknown and unsigned records never inflate readiness."""
    return {state: sum(item.state is state for item in delta.items) for state in DeltaState}


def package_readiness_counts(delta: PackageReadiness) -> dict[DeltaState, int]:
    counts = {state: 0 for state in DeltaState}
    for package in delta.packages:
        states = (
            package.professional_review_state,
            package.signer_authority_state,
            package.signature_state,
            package.handover_state,
            package.acceptance_state,
        )
        counts[DeltaState.SATISFIED] += int(all(state is DeltaState.SATISFIED for state in states))
        for state in states:
            if state is not DeltaState.SATISFIED:
                counts[state] += 1
    return counts


def evaluate_document_items(
    required_keys: tuple[str, ...], actual: tuple[EvidenceRatedItem, ...]
) -> tuple[EvidenceRatedItem, ...]:
    by_key = {item.item_key: item for item in actual}
    return tuple(
        by_key.get(
            key,
            EvidenceRatedItem(
                key,
                DeltaState.MISSING,
                (),
                (),
                (),
                (),
                ("DOCUMENT_NOT_EVIDENCED",),
                ("DOCUMENT_DELTA_OPEN",),
                ("ID_READINESS_UNPROVEN",),
            ),
        )
        for key in required_keys
    )


def assemble_audit_report(
    snapshot: CorpusSnapshot,
    scope: AuditScope,
    document_delta: DocumentDelta,
    causal_delta: CausalReadinessDelta,
    package_readiness: PackageReadiness,
    action_requests: tuple[ActionRequest, ...],
) -> AuditReport:
    """Assemble three separately fingerprinted deltas; no aggregate percentage exists."""
    if (
        scope.corpus_snapshot_id != snapshot.corpus_snapshot_id
        or scope.corpus_snapshot_version != snapshot.version
    ):
        raise ValueError("Audit scope must use the exact reconciled CorpusSnapshot")
    if not snapshot.reconciliation_ids:
        raise ValueError("Audit cannot run before exact corpus reconciliation")
    states = [item.state for item in document_delta.items]
    states.extend(path.state for path in causal_delta.paths)
    for package in package_readiness.packages:
        states.extend(
            (
                package.professional_review_state,
                package.signer_authority_state,
                package.signature_state,
                package.handover_state,
                package.acceptance_state,
            )
        )
    unresolved = sorted(
        {
            code
            for item in document_delta.items
            for code in (*item.uncertainty_codes, *item.blocker_codes)
        }
        | {code for path in causal_delta.paths for code in path.gap_codes}
        | {code for package in package_readiness.packages for code in package.blocker_codes}
    )
    if snapshot.outcome in {CorpusOutcome.QUARANTINED, CorpusOutcome.RECOVERY_REQUIRED}:
        outcome = AuditTerminalOutcome.BLOCKED
    elif any(state in {DeltaState.BLOCKED, DeltaState.CONFLICT} for state in states):
        outcome = AuditTerminalOutcome.BLOCKED
    elif any(state in {DeltaState.MISSING, DeltaState.INDETERMINATE} for state in states):
        outcome = AuditTerminalOutcome.PARTIAL
    elif snapshot.outcome is not CorpusOutcome.COMPLETE:
        outcome = AuditTerminalOutcome.UNRESOLVED
    else:
        outcome = AuditTerminalOutcome.COMPLETE
    return AuditReport(
        uuid7(),
        1,
        scope,
        snapshot.fingerprint,
        document_delta.document_delta_id,
        document_delta.fingerprint,
        causal_delta.causal_delta_id,
        causal_delta.fingerprint,
        package_readiness.package_readiness_id,
        package_readiness.fingerprint,
        tuple(request.action_request_id for request in action_requests),
        outcome,
        tuple(unresolved),
        datetime.now(UTC),
    )
