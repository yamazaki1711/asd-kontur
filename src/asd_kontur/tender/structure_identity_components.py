"""Deterministic transitive components for overlapping identity candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest


def build_structure_identity_components(
    identity_candidates: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse only candidates connected by an exact shared member observation.

    Canonical-label equality is deliberately ignored: distinct facilities may
    share a name. A shared immutable structure-node observation is sufficient
    for transitive union because each accepted candidate already asserts that
    all of its members refer to one identity.
    """

    candidates = [
        dict(value)
        for value in identity_candidates
        if value.get("identity_candidate_id") is not None
    ]
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    by_member: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, candidate in enumerate(candidates):
        kind = str(candidate.get("identity_kind") or "")
        for member_id in candidate.get("member_structure_node_ids") or ():
            by_member[(kind, str(member_id))].append(index)
    for indexes in by_member.values():
        for index in indexes[1:]:
            union(indexes[0], index)

    component_indexes: dict[int, list[int]] = defaultdict(list)
    for index in range(len(candidates)):
        component_indexes[find(index)].append(index)

    components: list[dict[str, Any]] = []
    for indexes in component_indexes.values():
        members = [candidates[index] for index in indexes]
        candidate_ids = sorted(str(item["identity_candidate_id"]) for item in members)
        identity_kind = str(members[0].get("identity_kind") or "")
        labels = sorted(
            {
                str(item.get("canonical_label") or "").strip()
                for item in members
                if str(item.get("canonical_label") or "").strip()
            }
        )
        member_node_ids = sorted(
            {
                str(value)
                for item in members
                for value in item.get("member_structure_node_ids") or ()
            }
        )
        locator_ids = sorted(
            {str(value) for item in members for value in item.get("source_locator_ids") or ()}
        )
        payload = {
            "identity_kind": identity_kind,
            "member_identity_candidate_ids": candidate_ids,
            "member_structure_node_ids": member_node_ids,
        }
        components.append(
            {
                "identity_candidate_id": semantic_digest(payload),
                "identity_kind": identity_kind,
                "canonical_label": labels[0] if len(labels) == 1 else " / ".join(labels),
                "candidate_labels": labels,
                "member_identity_candidate_ids": candidate_ids,
                "member_structure_node_ids": member_node_ids,
                "source_locator_ids": locator_ids,
                "candidate_group_count": len(candidate_ids),
                "component_state": (
                    "overlap_reconciled_candidate" if len(candidate_ids) > 1 else "single_candidate"
                ),
                "status": "candidate",
                "confidence": None,
                "member_confidences": [
                    item.get("confidence") for item in members if item.get("confidence") is not None
                ],
                "reconciliation_profile_versions": sorted(
                    {
                        str(item.get("reconciliation_profile_version"))
                        for item in members
                        if item.get("reconciliation_profile_version") is not None
                    }
                ),
                "candidate_state": "cross_source_identity_component_candidate",
                "authority": "candidate_only_exact_member_overlap_union",
            }
        )
    return sorted(
        components,
        key=lambda item: (
            str(item.get("identity_kind") or ""),
            str(item.get("canonical_label") or ""),
            str(item.get("identity_candidate_id") or ""),
        ),
    )
