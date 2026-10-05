"""Authority-preserving typed graph projection for canonical NTD structure."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid


def rebuild_ntd_typed_graph(engine: Engine) -> dict[str, int | str]:
    """Materialize only explicit containment relations as canonical edges."""

    with engine.connect() as connection:
        objects = (
            connection.execute(
                sa.text(
                    "SELECT corpus_object_id,normative_document_id,stable_designation,title,"
                    "authority_class FROM platform.ntd_corpus_objects "
                    "WHERE terminal_outcome='admitted' AND authority_class <> 'gesn_candidate' "
                    "ORDER BY artifact_digest"
                )
            )
            .mappings()
            .all()
        )
        units = (
            connection.execute(
                sa.text(
                    "SELECT structural_unit_id,corpus_object_id,parent_structural_unit_id,"
                    "unit_kind,"
                    "label,heading,structural_path,source_locator_ids "
                    "FROM platform.ntd_structural_units WHERE version=1 AND "
                    "derivation_method='qualified_structure_reconstruction@1.0.0' "
                    "ORDER BY corpus_object_id,ordinal"
                )
            )
            .mappings()
            .all()
        )

    document_nodes: dict[UUID, dict[str, Any]] = {}
    authority_by_object: dict[UUID, str] = {}
    for corpus_object in objects:
        corpus_object_id = corpus_object["corpus_object_id"]
        canonical_id = corpus_object["normative_document_id"] or corpus_object_id
        node_id = deterministic_uuid(f"ntd-graph-document:{canonical_id}")
        label = f"{corpus_object['stable_designation']} — {corpus_object['title']}".strip(" —")
        authority = str(corpus_object["authority_class"])
        document_nodes[corpus_object_id] = {
            "id": node_id,
            "kind": "normative_document",
            "canonical": canonical_id,
            "label": label,
            "authority": authority,
            "locators": [],
            "fingerprint": semantic_digest(
                {
                    "profile": "ntd-typed-graph@1.0.0",
                    "kind": "normative_document",
                    "canonical": str(canonical_id),
                    "label": label,
                    "authority": authority,
                }
            ),
        }
        authority_by_object[corpus_object_id] = authority

    unit_nodes: dict[UUID, dict[str, Any]] = {}
    blocked = 0
    for unit in units:
        corpus_object_id = unit["corpus_object_id"]
        if corpus_object_id not in document_nodes:
            blocked += 1
            continue
        structural_unit_id = unit["structural_unit_id"]
        node_id = deterministic_uuid(f"ntd-graph-unit:{structural_unit_id}")
        label = str(unit["heading"] or unit["label"] or unit["structural_path"])
        kind = _node_kind(str(unit["unit_kind"]))
        locators = list(unit["source_locator_ids"])
        unit_nodes[structural_unit_id] = {
            "id": node_id,
            "kind": kind,
            "canonical": structural_unit_id,
            "label": label,
            "authority": authority_by_object[corpus_object_id],
            "locators": locators,
            "fingerprint": semantic_digest(
                {
                    "profile": "ntd-typed-graph@1.0.0",
                    "kind": kind,
                    "canonical": str(structural_unit_id),
                    "label": label,
                    "authority": authority_by_object[corpus_object_id],
                    "locators": [str(value) for value in locators],
                }
            ),
        }

    edges: list[dict[str, Any]] = []
    for unit in units:
        target = unit_nodes.get(unit["structural_unit_id"])
        if target is None:
            continue
        parent_id = unit["parent_structural_unit_id"]
        source = unit_nodes.get(parent_id) if parent_id is not None else None
        if source is None:
            source = document_nodes.get(unit["corpus_object_id"])
        if source is None:
            blocked += 1
            continue
        locators = list(unit["source_locator_ids"])
        edge_id = deterministic_uuid(f"ntd-graph-edge:{source['id']}:{target['id']}:contains")
        edges.append(
            {
                "id": edge_id,
                "source": source["id"],
                "target": target["id"],
                "locators": locators,
                "fingerprint": semantic_digest(
                    {
                        "profile": "ntd-typed-graph@1.0.0",
                        "source": str(source["id"]),
                        "target": str(target["id"]),
                        "relation": "contains",
                        "authority_method": "explicit_structure",
                        "locators": [str(value) for value in locators],
                    }
                ),
            }
        )

    with engine.begin() as connection:
        for node in (*document_nodes.values(), *unit_nodes.values()):
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_graph_nodes(graph_node_id,version,node_kind,"
                    "canonical_entity_id,label,authority_status,source_locator_ids,"
                    "node_fingerprint) "
                    "VALUES (:id,1,:kind,:canonical,:label,:authority,:locators,:fingerprint) "
                    "ON CONFLICT (node_fingerprint) DO NOTHING"
                ),
                node,
            )
        for edge in edges:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_graph_edges(graph_edge_id,source_graph_node_id,"
                    "target_graph_node_id,relation_kind,authority_method,source_locator_ids,"
                    "edge_fingerprint) VALUES (:id,:source,:target,'contains',"
                    "'explicit_structure',:locators,:fingerprint) "
                    "ON CONFLICT (edge_fingerprint) DO NOTHING"
                ),
                edge,
            )

    node_ids = sorted(str(node["id"]) for node in (*document_nodes.values(), *unit_nodes.values()))
    edge_ids = sorted(str(edge["id"]) for edge in edges)
    return {
        "documents": len(document_nodes),
        "nodes": len(node_ids),
        "edges": len(edge_ids),
        "blocked": blocked,
        "fingerprint": semantic_digest(
            {"profile": "ntd-typed-graph@1.0.0", "nodes": node_ids, "edges": edge_ids}
        ),
    }


def _node_kind(value: str) -> str:
    return {
        "clause": "provision",
        "subclause": "provision",
        "definition": "definition",
        "table": "table",
        "table_row": "table",
        "appendix": "appendix",
    }.get(value, "section")
