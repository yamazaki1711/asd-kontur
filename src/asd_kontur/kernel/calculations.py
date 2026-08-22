"""Pure deterministic calculations shared by all mode overlays."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from uuid import UUID

from .errors import KernelError, KernelErrorCode
from .models import Applicability, CompletenessResult, CoverageItem, RequiredItem


def evaluate_completeness(
    required: Iterable[RequiredItem], coverage: Iterable[CoverageItem]
) -> CompletenessResult:
    coverage_by_id = {item.requirement_id: item for item in coverage}
    required_ids: list[UUID] = []
    covered_ids: list[UUID] = []
    missing_ids: list[UUID] = []
    indeterminate_ids: list[UUID] = []
    for item in sorted(required, key=lambda current: str(current.requirement_id)):
        if item.applicability is Applicability.NOT_APPLICABLE:
            continue
        if item.applicability is Applicability.INDETERMINATE:
            indeterminate_ids.append(item.requirement_id)
            continue
        required_ids.append(item.requirement_id)
        match = coverage_by_id.get(item.requirement_id)
        if match is None or not match.covered:
            missing_ids.append(item.requirement_id)
        elif match.unresolved or not match.evidence_refs:
            indeterminate_ids.append(item.requirement_id)
        else:
            covered_ids.append(item.requirement_id)
    status = "indeterminate" if indeterminate_ids else "incomplete" if missing_ids else "complete"
    return CompletenessResult(
        status,
        tuple(required_ids),
        tuple(covered_ids),
        tuple(missing_ids),
        tuple(indeterminate_ids),
    )


def deterministic_work_order(
    work_ids: Iterable[UUID], dependencies: Iterable[tuple[UUID, UUID]]
) -> tuple[UUID, ...]:
    nodes = set(work_ids)
    outgoing: dict[UUID, set[UUID]] = defaultdict(set)
    indegree = dict.fromkeys(nodes, 0)
    for prerequisite, successor in dependencies:
        if prerequisite not in nodes or successor not in nodes:
            raise KernelError(
                KernelErrorCode.SCOPE_VIOLATION,
                "A work dependency references an unknown work instance.",
            )
        if successor not in outgoing[prerequisite]:
            outgoing[prerequisite].add(successor)
            indegree[successor] += 1
    ready = deque(sorted((item for item, degree in indegree.items() if degree == 0), key=str))
    ordered: list[UUID] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for successor in sorted(outgoing[current], key=str):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    if len(ordered) != len(nodes):
        raise KernelError(KernelErrorCode.DEPENDENCY_CYCLE, "Work dependencies contain a cycle.")
    return tuple(ordered)
