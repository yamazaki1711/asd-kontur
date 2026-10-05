#!/usr/bin/env python3
"""Benchmark one local dense model sequentially over pinned NTD representations."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np  # type: ignore[import-not-found]
from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

from asd_kontur.ntd.retrieval_benchmark import (
    GoldQuery,
    QueryRun,
    RetrievedItem,
    evaluate_retrieval,
    load_gold_benchmark,
)
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
    FIXED_PROFILE,
    STRUCTURE_PROFILE,
    QualificationChunk,
    RepresentationBuild,
    build_representation,
    read_extraction_cache,
    run_lexical_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--extraction-cache", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--query-prefix", default="")
    parser.add_argument("--passage-prefix", default="")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vector-cache-dir", required=True, type=Path)
    parser.add_argument("--candidate-limit", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 128 or not 10 <= args.candidate_limit <= 100:
        raise ValueError("ntd_dense_batch_size_invalid")

    corpus_digest = _file_digest(args.corpus)
    documents = read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest)
    gold = load_gold_benchmark(args.gold)
    model_path = args.model.resolve(strict=True)
    started = perf_counter()
    model = SentenceTransformer(str(model_path), device=args.device)
    model_ready_seconds = perf_counter() - started
    dimension = int(model.get_embedding_dimension())
    query_texts = [args.query_prefix + case.query for case in gold]
    query_started = perf_counter()
    query_vectors = model.encode(
        query_texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=args.batch_size,
        show_progress_bar=False,
    )
    query_seconds = perf_counter() - query_started
    profiles: list[dict[str, Any]] = []
    args.vector_cache_dir.mkdir(parents=True, exist_ok=True)
    for representation_profile in (FIXED_PROFILE, STRUCTURE_PROFILE, CONTEXTUAL_PROFILE):
        build = build_representation(documents, profile=representation_profile)
        cache_identity = hashlib.sha256(
            f"{args.model_id}:{args.model_revision}:{build.fingerprint}:{args.passage_prefix}".encode()
        ).hexdigest()
        cache_path = args.vector_cache_dir / f"{cache_identity}.npz"
        passage_started = perf_counter()
        if cache_path.is_file():
            stored = np.load(cache_path)
            passage_vectors = stored["vectors"]
            if list(stored["chunk_ids"]) != [str(chunk.chunk_id) for chunk in build.chunks]:
                raise ValueError("ntd_dense_vector_cache_identity_mismatch")
            cache_reused = True
        else:
            passage_vectors = model.encode(
                [args.passage_prefix + chunk.retrieval_text for chunk in build.chunks],
                normalize_embeddings=True,
                convert_to_numpy=True,
                batch_size=args.batch_size,
                show_progress_bar=False,
            )
            np.savez_compressed(
                cache_path,
                vectors=passage_vectors,
                chunk_ids=np.array([str(chunk.chunk_id) for chunk in build.chunks]),
            )
            cache_reused = False
        passage_seconds = perf_counter() - passage_started
        if passage_vectors.shape != (len(build.chunks), dimension):
            raise ValueError("ntd_dense_vector_shape_mismatch")
        scores = np.matmul(query_vectors, passage_vectors.T)
        dense_runs = _runs_from_scores(build, gold, scores)
        lexical_runs = run_lexical_benchmark(build, gold)
        hybrid_runs = _rrf_runs(gold, lexical_runs, dense_runs)
        profiles.append(
            {
                "representation_profile": representation_profile,
                "representation_fingerprint": build.fingerprint,
                "chunk_count": len(build.chunks),
                "passage_encoding_seconds": round(passage_seconds, 3),
                "passages_per_second": round(
                    len(build.chunks) / passage_seconds if passage_seconds else 0.0,
                    3,
                ),
                "vector_cache": str(cache_path),
                "vector_cache_digest": _file_digest(cache_path),
                "vector_cache_reused": cache_reused,
                "vector_bytes": int(passage_vectors.nbytes),
                "dense_metrics": evaluate_retrieval(gold, dense_runs).as_dict(),
                "fts_dense_rrf_metrics": evaluate_retrieval(gold, hybrid_runs).as_dict(),
                "dense_candidate_runs": _candidate_rows(
                    build,
                    gold,
                    scores,
                    limit=args.candidate_limit,
                ),
            }
        )
    payload: dict[str, Any] = {
        "profile": "ntd-dense-retrieval-benchmark@1.0.0",
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "model_digest": _tree_digest(model_path),
        "dimension": dimension,
        "dtype": str(query_vectors.dtype),
        "device": args.device,
        "normalization": "l2",
        "query_prefix": args.query_prefix,
        "passage_prefix": args.passage_prefix,
        "batch_size": args.batch_size,
        "model_ready_seconds": round(model_ready_seconds, 3),
        "query_encoding_seconds": round(query_seconds, 3),
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "profiles": profiles,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _runs_from_scores(
    build: RepresentationBuild,
    gold: tuple[GoldQuery, ...],
    scores: np.ndarray[Any, Any],
) -> tuple[QueryRun, ...]:
    runs: list[QueryRun] = []
    for query_index, case in enumerate(gold):
        started = perf_counter()
        order = np.argsort(-scores[query_index])
        selected: list[RetrievedItem] = []
        seen: set[tuple[str, int | None, str | None]] = set()
        for raw_index in order:
            chunk = build.chunks[int(raw_index)]
            item = _item(chunk, float(scores[query_index, int(raw_index)]))
            key = (item.document_digest, item.page_number, item.clause_label)
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) == 10:
                break
        runs.append(
            QueryRun(
                case.case_id,
                tuple(selected),
                (perf_counter() - started) * 1000,
            )
        )
    return tuple(runs)


def _candidate_rows(
    build: RepresentationBuild,
    gold: tuple[GoldQuery, ...],
    scores: np.ndarray[Any, Any],
    *,
    limit: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for query_index, case in enumerate(gold):
        order = np.argsort(-scores[query_index])[:limit]
        rows.append(
            {
                "case_id": case.case_id,
                "candidates": [
                    {
                        "chunk_id": str(build.chunks[int(raw_index)].chunk_id),
                        "score": float(scores[query_index, int(raw_index)]),
                    }
                    for raw_index in order
                ],
            }
        )
    return rows


def _rrf_runs(
    gold: tuple[GoldQuery, ...],
    lexical: tuple[QueryRun, ...],
    dense: tuple[QueryRun, ...],
) -> tuple[QueryRun, ...]:
    lexical_by_id = {run.case_id: run for run in lexical}
    dense_by_id = {run.case_id: run for run in dense}
    runs: list[QueryRun] = []
    for case in gold:
        started = perf_counter()
        scores: dict[tuple[str, int | None, str | None], float] = {}
        items: dict[tuple[str, int | None, str | None], RetrievedItem] = {}
        for run in (lexical_by_id[case.case_id], dense_by_id[case.case_id]):
            for rank, item in enumerate(run.items, 1):
                key = (item.document_digest, item.page_number, item.clause_label)
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
                items[key] = item
        ordered = sorted(
            scores,
            key=lambda key: (
                -scores[key],
                key[0],
                key[1] if key[1] is not None else -1,
                key[2] or "",
            ),
        )[:10]
        runs.append(
            QueryRun(
                case.case_id,
                tuple(RetrievedItem(key[0], key[1], key[2], scores[key]) for key in ordered),
                (perf_counter() - started) * 1000,
                resolved_designation=lexical_by_id[case.case_id].resolved_designation,
            )
        )
    return tuple(runs)


def _item(chunk: QualificationChunk, score: float) -> RetrievedItem:
    return RetrievedItem(
        chunk.document_digest,
        chunk.pages[0] if chunk.pages else None,
        chunk.clause_labels[0] if chunk.clause_labels else None,
        score,
    )


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    return "sha256:" + digest.hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
