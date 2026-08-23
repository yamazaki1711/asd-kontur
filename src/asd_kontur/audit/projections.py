"""Rebuildable Customer/PTO projection contracts; never a system of record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from asd_kontur.corpus import CorpusSnapshot
from asd_kontur.harness.models import digest_of

from .evaluation import document_readiness_counts, package_readiness_counts
from .models import ActionRequest, CausalReadinessDelta, DocumentDelta, PackageReadiness


@dataclass(frozen=True, slots=True)
class CustomerAuditProjection:
    corpus_fingerprint: str
    collection_counts: tuple[tuple[str, int], ...]
    processing_counts: tuple[tuple[str, int], ...]
    document_counts: tuple[tuple[str, int], ...]
    causal_blockers: tuple[str, ...]
    package_counts: tuple[tuple[str, int], ...]
    denominator_versions: tuple[str, ...]
    freshness_at: datetime

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class PtoAuditProjection:
    corpus_fingerprint: str
    unresolved_item_codes: tuple[str, ...]
    failed_or_unknown_pages: int
    action_request_states: tuple[tuple[str, int], ...]
    readiness_blockers: tuple[str, ...]
    freshness_at: datetime

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


def rebuild_customer_projection(
    snapshot: CorpusSnapshot,
    document_delta: DocumentDelta,
    causal_delta: CausalReadinessDelta,
    package_readiness: PackageReadiness,
    *,
    freshness_at: datetime,
) -> CustomerAuditProjection:
    document_counts = document_readiness_counts(document_delta)
    package_counts = package_readiness_counts(package_readiness)
    return CustomerAuditProjection(
        snapshot.fingerprint,
        (
            ("discovered_objects", snapshot.coverage.discovered_objects),
            ("admitted_objects", snapshot.coverage.admitted_objects),
        ),
        (
            ("expected_pages", snapshot.coverage.expected_pages),
            ("validated_pages", snapshot.coverage.validated_pages),
            ("unresolved_items", snapshot.coverage.unresolved_items),
        ),
        tuple((state.value, document_counts[state]) for state in document_counts),
        tuple(sorted({code for path in causal_delta.paths for code in path.gap_codes})),
        tuple((state.value, package_counts[state]) for state in package_counts),
        (
            snapshot.coverage.denominator_version,
            f"{document_delta.denominator.denominator_id}:{document_delta.denominator.version}",
            f"{causal_delta.denominator.denominator_id}:{causal_delta.denominator.version}",
            f"{package_readiness.denominator.denominator_id}:{package_readiness.denominator.version}",
        ),
        freshness_at,
    )


def rebuild_pto_projection(
    snapshot: CorpusSnapshot,
    action_requests: tuple[ActionRequest, ...],
    *,
    failed_or_unknown_pages: int,
    freshness_at: datetime,
) -> PtoAuditProjection:
    states: dict[str, int] = {}
    for request in action_requests:
        states[request.state.value] = states.get(request.state.value, 0) + 1
    return PtoAuditProjection(
        snapshot.fingerprint,
        tuple(sorted(item.reason_code for item in snapshot.unresolved_items)),
        failed_or_unknown_pages,
        tuple(sorted(states.items())),
        tuple(sorted(impact for request in action_requests for impact in request.blocking_impacts)),
        freshness_at,
    )
