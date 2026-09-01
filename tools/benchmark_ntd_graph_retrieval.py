#!/usr/bin/env python3
"""Benchmark bounded typed-graph expansion over pinned hybrid NTD candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from asd_kontur.ntd.retrieval_benchmark import (
    GoldQuery,
    QueryRun,
    RetrievedItem,
    evaluate_retrieval,
    load_gold_benchmark,
)
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
    QualificationChunk,
    build_representation,
    read_extraction_cache,
    run_lexical_benchmark,
)
from asd_kontur.ntd.typed_kag import KagNode, TypedKag, build_qualification_kag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--extraction-cache", required=True, type=Path)
    parser.add_argument("--dense-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.max_depth <= 4 or not 10 <= args.max_nodes <= 100:
        raise ValueError("ntd_graph_benchmark_bounds_invalid")

    corpus_digest = _file_digest(args.corpus)
    documents = read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest)
    build = build_representation(documents, profile=CONTEXTUAL_PROFILE)
    gold = load_gold_benchmark(args.gold)
    receipt = json.loads(args.dense_receipt.read_bytes())
    if receipt.get("corpus_digest") != corpus_digest:
        raise ValueError("ntd_graph_dense_corpus_mismatch")
    dense_profile = next(
        (
            value
            for value in receipt["profiles"]
            if value["representation_profile"] == CONTEXTUAL_PROFILE
        ),
        None,
    )
    if dense_profile is None or dense_profile["representation_fingerprint"] != build.fingerprint:
        raise ValueError("ntd_graph_dense_representation_mismatch")

    graph = build_qualification_kag(documents)
    lexical = {run.case_id: run for run in run_lexical_benchmark(build, gold)}
    dense = {str(row["case_id"]): row for row in dense_profile["dense_candidate_runs"]}
    runs, traces = _graph_runs(
        build,
        graph,
        gold,
        lexical,
        dense,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
    )
    payload: dict[str, object] = {
        "profile": "ntd-typed-graph-retrieval-benchmark@1.0.0",
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "dense_receipt_digest": _file_digest(args.dense_receipt),
        "dense_model_id": receipt["model_id"],
        "representation_profile": CONTEXTUAL_PROFILE,
        "representation_fingerprint": build.fingerprint,
        "typed_kag_profile": graph.profile,
        "typed_kag_fingerprint": graph.fingerprint,
        "max_depth": args.max_depth,
        "max_nodes": args.max_nodes,
        "metrics": evaluate_retrieval(gold, runs).as_dict(),
        "retrieval_traces": traces,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _graph_runs(
    build: Any,
    graph: TypedKag,
    gold: tuple[GoldQuery, ...],
    lexical: dict[str, QueryRun],
    dense: dict[str, dict[str, object]],
    *,
    max_depth: int,
    max_nodes: int,
) -> tuple[tuple[QueryRun, ...], list[dict[str, object]]]:
    chunks = {chunk.chunk_id: chunk for chunk in build.chunks}
    by_locator = _chunks_by_locator(tuple(chunks.values()))
    node_by_id = {node.node_id: node for node in graph.nodes}
    unit_node_by_path: dict[tuple[str, str], KagNode] = {}
    root_by_document: dict[str, KagNode] = {}
    for node in graph.nodes:
        if node.kind == "normative_document":
            root_by_document[node.document_digest] = node
        else:
            unit_node_by_path[(node.document_digest, node.canonical_identity)] = node
    unit_identity_by_path = {
        (document.entry.digest, unit.structural_path): str(unit.unit_id)
        for document in build.documents
        for unit in document.units
    }
    adjacency = _adjacency(graph)
    runs: list[QueryRun] = []
    traces: list[dict[str, object]] = []
    for case in gold:
        started = perf_counter()
        seed_scores: dict[UUID, float] = defaultdict(float)
        for rank, raw in enumerate(
            cast(list[dict[str, object]], dense[case.case_id]["candidates"]), 1
        ):
            seed_scores[UUID(str(raw["chunk_id"]))] += 1.0 / (60 + rank)
        for rank, item in enumerate(lexical[case.case_id].items, 1):
            chunk_id = by_locator.get((item.document_digest, item.page_number, item.clause_label))
            if chunk_id is not None:
                seed_scores[chunk_id] += 1.0 / (60 + rank)
        ordered_seeds = sorted(seed_scores, key=lambda value: (-seed_scores[value], str(value)))[
            :10
        ]
        expanded_scores = dict(seed_scores)
        paths: list[dict[str, object]] = []
        for rank, chunk_id in enumerate(ordered_seeds, 1):
            chunk = chunks[chunk_id]
            base_path = chunk.structural_path.split("@continuation:", maxsplit=1)[0]
            unit_identity = unit_identity_by_path.get((chunk.document_digest, base_path))
            seed_node: KagNode | None = (
                unit_node_by_path.get((chunk.document_digest, unit_identity))
                if unit_identity is not None
                else root_by_document.get(chunk.document_digest)
            )
            if seed_node is None:
                continue
            for adjacent_id, depth, relations in _expand_with_trace(
                seed_node.node_id,
                adjacency,
                max_depth=max_depth,
                max_nodes=max_nodes,
            ):
                adjacent = node_by_id[adjacent_id]
                if adjacent.kind == "normative_document":
                    continue
                adjacent_chunks = _chunks_for_node(
                    tuple(chunks.values()), adjacent, unit_identity_by_path
                )
                for adjacent_chunk in adjacent_chunks:
                    expanded_scores[adjacent_chunk.chunk_id] = expanded_scores.get(
                        adjacent_chunk.chunk_id, 0.0
                    ) + (1.0 / (60 + rank)) * (0.35**depth)
                if adjacent_chunks and len(paths) < 100:
                    paths.append(
                        {
                            "seed_chunk_id": str(chunk_id),
                            "target_node_id": str(adjacent_id),
                            "depth": depth,
                            "relations": relations,
                        }
                    )
        ordered = sorted(
            expanded_scores,
            key=lambda value: (
                -expanded_scores[value],
                chunks[value].ordinal,
                str(value),
            ),
        )
        items = _items(ordered, expanded_scores, chunks, limit=10)
        runs.append(
            QueryRun(
                case.case_id,
                items,
                (perf_counter() - started) * 1000,
                resolved_designation=lexical[case.case_id].resolved_designation,
            )
        )
        traces.append(
            {
                "case_id": case.case_id,
                "seed_chunk_ids": [str(value) for value in ordered_seeds],
                "expanded_chunk_count": len(expanded_scores),
                "paths": paths,
            }
        )
    return tuple(runs), traces


def _chunks_by_locator(
    chunks: tuple[QualificationChunk, ...],
) -> dict[tuple[str, int | None, str | None], UUID]:
    values: dict[tuple[str, int | None, str | None], UUID] = {}
    for chunk in chunks:
        key = (
            chunk.document_digest,
            chunk.pages[0] if chunk.pages else None,
            chunk.clause_labels[0] if chunk.clause_labels else None,
        )
        values.setdefault(key, chunk.chunk_id)
    return values


def _chunks_for_node(
    chunks: tuple[QualificationChunk, ...],
    node: KagNode,
    unit_identity_by_path: dict[tuple[str, str], str],
) -> tuple[QualificationChunk, ...]:
    return tuple(
        chunk
        for chunk in chunks
        if chunk.document_digest == node.document_digest
        and unit_identity_by_path.get(
            (
                chunk.document_digest,
                chunk.structural_path.split("@continuation:", maxsplit=1)[0],
            )
        )
        == node.canonical_identity
    )


def _adjacency(
    graph: TypedKag,
) -> dict[UUID, tuple[tuple[UUID, str], ...]]:
    mutable: dict[UUID, list[tuple[UUID, str]]] = defaultdict(list)
    for edge in graph.edges:
        mutable[edge.source_node_id].append((edge.target_node_id, edge.relation))
        mutable[edge.target_node_id].append((edge.source_node_id, edge.relation))
    return {
        node_id: tuple(sorted(values, key=lambda item: (str(item[0]), item[1])))
        for node_id, values in mutable.items()
    }


def _expand_with_trace(
    start: UUID,
    adjacency: dict[UUID, tuple[tuple[UUID, str], ...]],
    *,
    max_depth: int,
    max_nodes: int,
) -> tuple[tuple[UUID, int, tuple[str, ...]], ...]:
    queue: deque[tuple[UUID, int, tuple[str, ...]]] = deque([(start, 0, ())])
    seen = {start}
    values: list[tuple[UUID, int, tuple[str, ...]]] = []
    while queue and len(values) < max_nodes:
        node_id, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for target, relation in adjacency.get(node_id, ()):
            if target in seen:
                continue
            seen.add(target)
            target_path = (*path, relation)
            values.append((target, depth + 1, target_path))
            queue.append((target, depth + 1, target_path))
            if len(values) == max_nodes:
                break
    return tuple(values)


def _items(
    ordered: list[UUID],
    scores: dict[UUID, float],
    chunks: dict[UUID, QualificationChunk],
    *,
    limit: int,
) -> tuple[RetrievedItem, ...]:
    values: list[RetrievedItem] = []
    seen: set[tuple[str, int | None, str | None]] = set()
    for chunk_id in ordered:
        chunk = chunks[chunk_id]
        item = RetrievedItem(
            chunk.document_digest,
            chunk.pages[0] if chunk.pages else None,
            chunk.clause_labels[0] if chunk.clause_labels else None,
            scores[chunk_id],
        )
        key = (item.document_digest, item.page_number, item.clause_label)
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
        if len(values) == limit:
            break
    return tuple(values)


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
