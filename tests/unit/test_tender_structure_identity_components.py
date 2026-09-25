from __future__ import annotations

from asd_kontur.tender.structure_identity_components import (
    build_structure_identity_components,
)


def _candidate(
    candidate_id: str,
    label: str,
    *members: str,
    kind: str = "facility",
) -> dict[str, object]:
    return {
        "identity_candidate_id": candidate_id,
        "identity_kind": kind,
        "canonical_label": label,
        "member_structure_node_ids": list(members),
        "source_locator_ids": [f"locator-{value}" for value in members],
        "confidence": "0.8",
        "reconciliation_profile_version": "identity-v1",
    }


def test_components_union_candidates_transitively_only_through_shared_members() -> None:
    components = build_structure_identity_components(
        (
            _candidate("candidate-a", "Pump station 4", "node-a", "node-anchor"),
            _candidate("candidate-b", "Pump-station 4", "node-anchor", "node-b"),
            _candidate("candidate-c", "Pump station 4", "node-b", "node-c"),
            _candidate("candidate-distinct", "Pump station 4", "node-distinct"),
        )
    )

    assert len(components) == 2
    merged = next(item for item in components if item["candidate_group_count"] == 3)
    assert merged["member_identity_candidate_ids"] == [
        "candidate-a",
        "candidate-b",
        "candidate-c",
    ]
    assert merged["member_structure_node_ids"] == [
        "node-a",
        "node-anchor",
        "node-b",
        "node-c",
    ]
    assert merged["candidate_labels"] == ["Pump station 4", "Pump-station 4"]
    assert merged["component_state"] == "overlap_reconciled_candidate"
    distinct = next(item for item in components if item["candidate_group_count"] == 1)
    assert distinct["member_identity_candidate_ids"] == ["candidate-distinct"]


def test_components_do_not_union_shared_member_across_conflicting_kinds() -> None:
    components = build_structure_identity_components(
        (
            _candidate("facility", "Facility", "node-a", kind="facility"),
            _candidate("pit", "Pit", "node-a", kind="excavation_pit"),
        )
    )

    assert len(components) == 2
    assert {item["identity_kind"] for item in components} == {"facility", "excavation_pit"}
