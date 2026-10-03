"""Typed, authority-preserving KAG primitives for NTD retrieval.

Only explicit document structure and exact cross-references become canonical
edges automatically.  Semantic work/material relations stay candidates until a
deterministic mapping or professional confirmation exists.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.retrieval_qualification import QualificationDocument
from asd_kontur.ntd.search_corpus import designation_aliases, normalize_designation

TYPED_KAG_PROFILE = "ntd-typed-kag@1.0.0"
_REFERENCE = re.compile(
    r"\b(?:СП\s*\d+(?:\.\d+){1,3}|ГОСТ(?:\s+\N{CYRILLIC CAPITAL LETTER ER})?"
    r"\s*\d+(?:\.\d+)*(?:-\d{2,4})?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class KagNode:
    node_id: UUID
    kind: str
    canonical_identity: str
    label: str
    document_digest: str
    pages: tuple[int, ...]
    authority_status: str


@dataclass(frozen=True, slots=True)
class KagEdge:
    edge_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relation: str
    authority_method: str
    document_digest: str
    pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class KagEdgeCandidate:
    candidate_id: UUID
    source_node_id: UUID
    target_identity: str
    relation: str
    derivation_method: str
    document_digest: str
    pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TypedKag:
    profile: str
    nodes: tuple[KagNode, ...]
    edges: tuple[KagEdge, ...]
    candidates: tuple[KagEdgeCandidate, ...]
    fingerprint: str

    def expand(
        self,
        start_node_ids: tuple[UUID, ...],
        *,
        max_depth: int = 2,
        max_nodes: int = 24,
        relations: frozenset[str] = frozenset({"contains", "references"}),
    ) -> tuple[UUID, ...]:
        """Bounded path expansion; graph rank never changes canonical authority."""

        if not 0 <= max_depth <= 4 or not 1 <= max_nodes <= 100:
            raise ValueError("ntd_kag_expansion_bound_invalid")
        adjacency: dict[UUID, list[UUID]] = defaultdict(list)
        for edge in self.edges:
            if edge.relation not in relations:
                continue
            adjacency[edge.source_node_id].append(edge.target_node_id)
            adjacency[edge.target_node_id].append(edge.source_node_id)
        seen: set[UUID] = set(start_node_ids)
        queue = deque((node_id, 0) for node_id in start_node_ids)
        ordered: list[UUID] = list(start_node_ids)
        while queue and len(ordered) < max_nodes:
            node_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for adjacent in sorted(adjacency[node_id], key=str):
                if adjacent in seen:
                    continue
                seen.add(adjacent)
                ordered.append(adjacent)
                queue.append((adjacent, depth + 1))
                if len(ordered) == max_nodes:
                    break
        return tuple(ordered)


def build_qualification_kag(documents: tuple[QualificationDocument, ...]) -> TypedKag:
    roots: dict[str, KagNode] = {}
    aliases: dict[str, set[str]] = defaultdict(set)
    nodes: list[KagNode] = []
    edges: list[KagEdge] = []
    candidates: list[KagEdgeCandidate] = []
    unit_nodes: dict[tuple[str, str], KagNode] = {}
    for document in documents:
        root = KagNode(
            deterministic_uuid(f"ntd-kag-document:{document.entry.digest}"),
            "normative_document",
            document.entry.digest,
            f"{document.entry.designation} — {document.entry.title}",
            document.entry.digest,
            tuple(range(1, document.entry.expected_pages + 1)),
            document.entry.authority_class,
        )
        roots[document.entry.digest] = root
        nodes.append(root)
        for alias in designation_aliases(document.entry.designation):
            aliases[normalize_designation(alias)].add(document.entry.digest)
        for unit in document.units:
            node = KagNode(
                deterministic_uuid(f"ntd-kag-unit:{unit.unit_id}"),
                _unit_node_kind(unit.kind),
                str(unit.unit_id),
                unit.heading or unit.clause_label or unit.structural_path,
                unit.document_digest,
                unit.pages,
                document.entry.authority_class,
            )
            nodes.append(node)
            unit_nodes[(unit.document_digest, unit.structural_path)] = node
    for document in documents:
        root = roots[document.entry.digest]
        for unit in document.units:
            node = unit_nodes[(unit.document_digest, unit.structural_path)]
            parent = (
                unit_nodes.get((unit.document_digest, unit.parent_path))
                if unit.parent_path is not None
                else None
            )
            source = parent or root
            edges.append(
                _edge(
                    source,
                    node,
                    "contains",
                    "explicit_structure",
                    unit.document_digest,
                    unit.pages,
                )
            )
            for reference in _REFERENCE.findall(unit.raw_text):
                normalized = normalize_designation(reference)
                matches = {
                    digest
                    for alias, digests in aliases.items()
                    if alias == normalized or alias in normalized or normalized in alias
                    for digest in digests
                }
                if len(matches) == 1:
                    target = roots[next(iter(matches))]
                    if target.node_id != root.node_id:
                        edges.append(
                            _edge(
                                node,
                                target,
                                "references",
                                "exact_reference",
                                unit.document_digest,
                                unit.pages,
                            )
                        )
                elif len(matches) > 1:
                    candidates.append(
                        KagEdgeCandidate(
                            deterministic_uuid(
                                f"ntd-kag-candidate:{node.node_id}:references:{normalized}"
                            ),
                            node.node_id,
                            normalized,
                            "references",
                            "designation_ambiguous",
                            unit.document_digest,
                            unit.pages,
                        )
                    )
    unique_edges = {edge.edge_id: edge for edge in edges}
    payload = {
        "profile": TYPED_KAG_PROFILE,
        "nodes": [str(node.node_id) for node in nodes],
        "edges": [str(edge.edge_id) for edge in unique_edges.values()],
        "candidates": [str(candidate.candidate_id) for candidate in candidates],
    }
    return TypedKag(
        TYPED_KAG_PROFILE,
        tuple(nodes),
        tuple(unique_edges.values()),
        tuple(candidates),
        _digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()),
    )


def _edge(
    source: KagNode,
    target: KagNode,
    relation: str,
    authority_method: str,
    document_digest: str,
    pages: tuple[int, ...],
) -> KagEdge:
    identity = f"{source.node_id}:{target.node_id}:{relation}:{authority_method}"
    return KagEdge(
        deterministic_uuid(f"ntd-kag-edge:{identity}"),
        source.node_id,
        target.node_id,
        relation,
        authority_method,
        document_digest,
        pages,
    )


def _unit_node_kind(value: str) -> str:
    return {
        "section": "section",
        "clause": "provision",
        "subclause": "provision",
        "table": "table",
        "appendix": "appendix",
        "definition": "definition",
    }.get(value, "section")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
