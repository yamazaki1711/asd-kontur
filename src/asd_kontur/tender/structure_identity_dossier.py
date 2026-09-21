"""Evidence-preserving dossier projection for cross-document identity candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def build_structure_identity_dossiers(
    identity_candidates: Iterable[Mapping[str, Any]],
    *,
    structure_nodes: Iterable[Mapping[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
    facility_work_groups: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Build candidate dossiers without promoting identities or relationships."""

    nodes_by_id = {
        str(node.get("structure_node_id")): dict(node)
        for node in structure_nodes
        if node.get("structure_node_id") is not None
    }
    relationship_rows = [dict(item) for item in relationships]
    work_groups_by_identity: dict[str, list[dict[str, Any]]] = {}
    for group in facility_work_groups:
        identity_id = str(group.get("identity_candidate_id") or "")
        if identity_id:
            work_groups_by_identity.setdefault(identity_id, []).append(dict(group))

    dossiers: list[dict[str, Any]] = []
    for candidate_value in identity_candidates:
        candidate = dict(candidate_value)
        identity_id = str(candidate.get("identity_candidate_id") or "")
        if not identity_id:
            continue
        member_ids = tuple(
            dict.fromkeys(str(value) for value in candidate.get("member_structure_node_ids") or ())
        )
        member_id_set = set(member_ids)
        members = [nodes_by_id[node_id] for node_id in member_ids if node_id in nodes_by_id]
        missing_member_ids = [node_id for node_id in member_ids if node_id not in nodes_by_id]
        linked_relationships = [
            row
            for row in relationship_rows
            if str(row.get("subject_structure_node_id") or "") in member_id_set
            or str(row.get("object_structure_node_id") or "") in member_id_set
        ]
        related_node_ids = {
            str(value)
            for row in linked_relationships
            for value in (
                row.get("subject_structure_node_id"),
                row.get("object_structure_node_id"),
            )
            if value is not None and str(value) not in member_id_set
        }
        related_nodes = [
            nodes_by_id[node_id] for node_id in sorted(related_node_ids) if node_id in nodes_by_id
        ]
        work_groups = sorted(
            work_groups_by_identity.get(identity_id, []),
            key=lambda item: str(item.get("facility_work_candidate_id") or ""),
        )
        source_locator_ids = sorted(
            {
                *(str(value) for value in candidate.get("source_locator_ids") or ()),
                *(
                    str(node["source_locator_id"])
                    for node in (*members, *related_nodes)
                    if node.get("source_locator_id") is not None
                ),
                *(
                    str(row["source_locator_id"])
                    for row in linked_relationships
                    if row.get("source_locator_id") is not None
                ),
                *(
                    str(value)
                    for group in work_groups
                    for value in group.get("source_locator_ids") or ()
                ),
            }
        )
        aliases = sorted(
            {
                str(node.get("raw_name") or "").strip()
                for node in members
                if str(node.get("raw_name") or "").strip()
            }
        )
        dossiers.append(
            {
                "candidate_state": "cross_source_identity_dossier_candidate",
                "identity_candidate": candidate,
                "aliases": aliases,
                "member_observations": members,
                "missing_member_structure_node_ids": missing_member_ids,
                "relationship_observations": linked_relationships,
                "related_structure_observations": related_nodes,
                "facility_work_candidate_groups": work_groups,
                "source_locator_ids": source_locator_ids,
                "coverage": {
                    "expected_member_observation_count": len(member_ids),
                    "available_member_observation_count": len(members),
                    "missing_member_observation_count": len(missing_member_ids),
                    "relationship_observation_count": len(linked_relationships),
                    "unresolved_relationship_observation_count": sum(
                        str(row.get("resolution_state") or "") != "resolved_same_evidence"
                        for row in linked_relationships
                    ),
                    "related_structure_observation_count": len(related_nodes),
                    "facility_work_candidate_group_count": len(work_groups),
                    "complete_for_persisted_candidate": not missing_member_ids,
                    "authority": "candidate_observations_not_confirmed_project_entities",
                },
            }
        )
    return sorted(
        dossiers,
        key=lambda item: (
            str(item["identity_candidate"].get("identity_kind") or ""),
            str(item["identity_candidate"].get("canonical_label") or ""),
            str(item["identity_candidate"].get("identity_candidate_id") or ""),
        ),
    )
