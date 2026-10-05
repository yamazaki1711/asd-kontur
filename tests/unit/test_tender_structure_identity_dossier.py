# ruff: noqa: RUF001 -- Russian project labels are intentional test data.

from __future__ import annotations

from asd_kontur.tender.structure_identity_dossier import (
    build_structure_identity_dossiers,
)


def test_dossier_preserves_members_relationships_works_and_missing_nodes() -> None:
    dossiers = build_structure_identity_dossiers(
        (
            {
                "identity_candidate_id": "identity-kns-1",
                "identity_kind": "facility",
                "canonical_label": "КНС-1",
                "member_structure_node_ids": ["node-a", "node-b", "node-missing"],
                "source_locator_ids": ["locator-a", "locator-b"],
                "status": "candidate",
            },
        ),
        structure_nodes=(
            {
                "structure_node_id": "node-a",
                "node_kind": "facility",
                "raw_name": "КНС 1",
                "source_locator_id": "locator-a",
            },
            {
                "structure_node_id": "node-b",
                "node_kind": "facility",
                "raw_name": "КНС-1",
                "source_locator_id": "locator-b",
            },
            {
                "structure_node_id": "node-pit",
                "node_kind": "excavation_pit",
                "raw_name": "Котлован КНС-1",
                "source_locator_id": "locator-c",
            },
        ),
        relationships=(
            {
                "relationship_candidate_id": "relationship-1",
                "relationship_kind": "serves",
                "subject_structure_node_id": "node-pit",
                "object_structure_node_id": "node-a",
                "source_locator_id": "locator-c",
                "resolution_state": "resolved_same_evidence",
            },
            {
                "relationship_candidate_id": "relationship-2",
                "relationship_kind": "located_at",
                "subject_structure_node_id": "node-b",
                "object_structure_node_id": None,
                "source_locator_id": "locator-b",
                "resolution_state": "unresolved_source_scoped_identity",
            },
        ),
        facility_work_groups=(
            {
                "facility_work_candidate_id": "facility-work-1",
                "identity_candidate_id": "identity-kns-1",
                "work_type": {"raw": "Разработка грунта"},
                "source_locator_ids": ["locator-a"],
            },
        ),
    )

    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert dossier["candidate_state"] == "cross_source_identity_dossier_candidate"
    assert dossier["aliases"] == ["КНС 1", "КНС-1"]
    assert [item["structure_node_id"] for item in dossier["member_observations"]] == [
        "node-a",
        "node-b",
    ]
    assert dossier["missing_member_structure_node_ids"] == ["node-missing"]
    assert [item["structure_node_id"] for item in dossier["related_structure_observations"]] == [
        "node-pit"
    ]
    assert len(dossier["relationship_observations"]) == 2
    assert len(dossier["facility_work_candidate_groups"]) == 1
    assert dossier["source_locator_ids"] == ["locator-a", "locator-b", "locator-c"]
    assert dossier["coverage"] == {
        "expected_member_observation_count": 3,
        "available_member_observation_count": 2,
        "missing_member_observation_count": 1,
        "relationship_observation_count": 2,
        "unresolved_relationship_observation_count": 1,
        "related_structure_observation_count": 1,
        "facility_work_candidate_group_count": 1,
        "complete_for_persisted_candidate": False,
        "authority": "candidate_observations_not_confirmed_project_entities",
    }


def test_dossier_does_not_join_same_name_across_distinct_identity_candidates() -> None:
    dossiers = build_structure_identity_dossiers(
        (
            {
                "identity_candidate_id": "identity-a",
                "identity_kind": "facility",
                "canonical_label": "КНС",
                "member_structure_node_ids": ["node-a"],
            },
            {
                "identity_candidate_id": "identity-b",
                "identity_kind": "facility",
                "canonical_label": "КНС",
                "member_structure_node_ids": ["node-b"],
            },
        ),
        structure_nodes=(
            {"structure_node_id": "node-a", "raw_name": "КНС"},
            {"structure_node_id": "node-b", "raw_name": "КНС"},
        ),
        relationships=(),
    )

    assert [item["identity_candidate"]["identity_candidate_id"] for item in dossiers] == [
        "identity-a",
        "identity-b",
    ]
    assert [len(item["member_observations"]) for item in dossiers] == [1, 1]
