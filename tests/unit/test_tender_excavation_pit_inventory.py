# ruff: noqa: RUF001 -- Russian construction terms are intentional.

from __future__ import annotations

from asd_kontur.tender.excavation_pit_inventory import build_excavation_pit_inventory


def _node(identity: str, name: str, locator: str) -> dict[str, object]:
    return {
        "structure_node_id": identity,
        "node_kind": "excavation_pit",
        "raw_name": name,
        "source_locator_id": locator,
    }


def test_explicit_facility_pits_are_grouped_without_claiming_a_project_total() -> None:
    result = build_excavation_pit_inventory(
        [
            _node("pit-a-1", "котлован для ЛОС -4", "locator-a"),
            _node("pit-a-2", "Котлован для ЛОС 4", "locator-b"),
            _node("pit-b", "котлован для КНС8 .1", "locator-c"),
            _node("generic", "котлован", "locator-d"),
            _node("borehole", "скв. 1043", "locator-e"),
            {
                "structure_node_id": "facility",
                "node_kind": "facility",
                "raw_name": "КНС-270/12С/3,0-9,1/4,82",
                "source_locator_id": "locator-f",
            },
        ]
    )

    assert [
        candidate["associated_facility_designation"] for candidate in result["candidate_pits"]
    ] == ["КНС 8.1", "ЛОС 4"]
    los = result["candidate_pits"][1]
    assert los["member_structure_node_ids"] == ["pit-a-1", "pit-a-2"]
    assert los["source_locator_ids"] == ["locator-a", "locator-b"]
    assert result["coverage"] == {
        "total_pit_observation_count": 5,
        "explicit_facility_association_observation_count": 3,
        "unresolved_observation_count": 2,
        "returned_unresolved_observation_count": 2,
        "candidate_pit_count": 2,
        "identity_candidate_count": 0,
        "identity_rejected_non_pit_count": 0,
        "identity_enriched_observation_count": 0,
        "semantic_candidate_observation_count": 0,
        "non_pit_observation_count": 1,
        "generic_observation_count": 1,
        "disposition_counts": {},
        "exact_total_supported": False,
        "count_meaning": "distinct_explicit_source_association_candidates_not_project_total",
        "candidate_authority": "candidate_only",
    }


def test_distinct_pit_qualifiers_for_one_facility_are_not_name_collapsed() -> None:
    result = build_excavation_pit_inventory(
        [
            _node("working", "рабочий котлован для КНС 4", "locator-a"),
            _node("receiving", "приёмный котлован для КНС4", "locator-b"),
        ]
    )

    assert len(result["candidate_pits"]) == 2
    assert {candidate["canonical_label"] for candidate in result["candidate_pits"]} == {
        "рабочий котлован для КНС 4",
        "приёмный котлован для КНС4",
    }


def test_unresolved_observation_sample_is_bounded_without_losing_denominator() -> None:
    result = build_excavation_pit_inventory(
        [_node(f"pit-{index}", "котлован", f"locator-{index}") for index in range(5)],
        unresolved_sample_limit=2,
    )

    assert len(result["unresolved_observations"]) == 2
    assert result["coverage"]["unresolved_observation_count"] == 5
    assert result["coverage"]["returned_unresolved_observation_count"] == 2


def test_identity_candidates_cannot_promote_boreholes_and_can_retain_explicit_scope() -> None:
    result = build_excavation_pit_inventory(
        [
            _node("pit", "котлован для ЛОС 4", "locator-a"),
            _node("borehole", "скв.897", "locator-b"),
        ],
        identity_candidates=[
            {
                "identity_candidate_id": "pit-candidate",
                "identity_kind": "excavation_pit",
                "canonical_label": "скв.897",
                "member_structure_node_ids": ["borehole"],
            },
            {
                "identity_candidate_id": "scoped-pit-candidate",
                "identity_kind": "excavation_pit",
                "canonical_label": "котлован для ЛОС 4",
                "member_structure_node_ids": ["pit"],
            },
        ],
    )

    assert len(result["candidate_pits"]) == 1
    assert result["coverage"]["identity_candidate_count"] == 2
    assert result["coverage"]["identity_rejected_non_pit_count"] == 1
    assert result["coverage"]["non_pit_observation_count"] == 1


def test_semantic_distinct_candidate_keeps_unscoped_identity_as_candidate() -> None:
    result = build_excavation_pit_inventory(
        [_node("pit", "котлован", "locator-a")],
        pit_observation_decisions=[
            {
                "node_id": "pit",
                "disposition": "distinct_instance_candidate",
                "canonical_label": "котлован В-1",
                "facility_label": "",
                "reason_code": "named_on_plan",
                "confidence": "0.82",
            }
        ],
    )

    assert len(result["candidate_pits"]) == 1
    assert result["candidate_pits"][0]["candidate_state"] == (
        "semantic_distinct_instance_candidate"
    )
    assert result["candidate_pits"][0]["associated_facility_designation"] == "Не установлено"
    assert result["coverage"]["semantic_candidate_observation_count"] == 1
    assert result["coverage"]["disposition_counts"] == {"distinct_instance_candidate": 1}
