#!/usr/bin/env python3
"""Rerank pinned hybrid NTD candidates with one local model at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

from asd_kontur.ntd.retrieval_benchmark import (
    QueryRun,
    RetrievedItem,
    evaluate_retrieval,
    load_gold_benchmark,
)
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
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
    parser.add_argument("--dense-receipt", required=True, type=Path)
    parser.add_argument("--dense-profile", default=CONTEXTUAL_PROFILE)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 32:
        raise ValueError("ntd_reranker_batch_size_invalid")
    corpus_digest = _file_digest(args.corpus)
    documents = read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest)
    build = build_representation(documents, profile=args.dense_profile)
    gold = load_gold_benchmark(args.gold)
    dense_receipt = json.loads(args.dense_receipt.read_bytes())
    if dense_receipt.get("corpus_digest") != corpus_digest:
        raise ValueError("ntd_reranker_dense_corpus_mismatch")
    raw_profile = next(
        (
            profile
            for profile in dense_receipt["profiles"]
            if profile["representation_profile"] == args.dense_profile
        ),
        None,
    )
    if raw_profile is None or raw_profile["representation_fingerprint"] != build.fingerprint:
        raise ValueError("ntd_reranker_representation_mismatch")
    candidates, resolved_designations, hybrid_ranks = _candidate_sets(build, gold, raw_profile)
    model_path = args.model.resolve(strict=True)
    started = perf_counter()
    model = CrossEncoder(
        str(model_path),
        device=args.device,
        prompts={"ntd": args.instruction},
        default_prompt_name="ntd",
        max_length=2048,
    )
    ready_seconds = perf_counter() - started
    by_chunk = {chunk.chunk_id: chunk for chunk in build.chunks}
    reranker_runs: list[QueryRun] = []
    fused_runs: list[QueryRun] = []
    candidate_receipts: list[dict[str, object]] = []
    total_pairs = 0
    prediction_seconds = 0.0
    for case in gold:
        chunk_ids = candidates[case.case_id]
        chunks = [by_chunk[chunk_id] for chunk_id in chunk_ids]
        pairs = [(case.query, chunk.retrieval_text) for chunk in chunks]
        predict_started = perf_counter()
        raw_scores = model.predict(
            pairs,
            batch_size=args.batch_size,
            show_progress_bar=False,
        )
        elapsed = perf_counter() - predict_started
        prediction_seconds += elapsed
        total_pairs += len(pairs)
        scored = sorted(
            zip((float(value) for value in raw_scores), chunks, strict=True),
            key=lambda item: (-item[0], item[1].ordinal, str(item[1].chunk_id)),
        )
        reranker_items = _items(scored, limit=10)
        reranker_runs.append(
            QueryRun(
                case.case_id,
                reranker_items,
                elapsed * 1000,
                resolved_designation=resolved_designations[case.case_id],
            )
        )
        reranker_rank = {chunk.chunk_id: rank for rank, (_, chunk) in enumerate(scored, 1)}
        fused_scored = sorted(
            (
                (
                    1.0 / (60 + hybrid_ranks[case.case_id][chunk.chunk_id])
                    + 2.0 / (60 + reranker_rank[chunk.chunk_id]),
                    chunk,
                )
                for _, chunk in scored
            ),
            key=lambda item: (-item[0], item[1].ordinal, str(item[1].chunk_id)),
        )
        fused_runs.append(
            QueryRun(
                case.case_id,
                _items(fused_scored, limit=10),
                elapsed * 1000,
                resolved_designation=resolved_designations[case.case_id],
            )
        )
        candidate_receipts.append(
            {
                "case_id": case.case_id,
                "candidates": [
                    {"chunk_id": str(chunk.chunk_id), "reranker_score": score}
                    for score, chunk in scored
                ],
            }
        )
    payload: dict[str, object] = {
        "profile": "ntd-reranker-benchmark@1.0.0",
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "dense_receipt_digest": _file_digest(args.dense_receipt),
        "representation_profile": args.dense_profile,
        "representation_fingerprint": build.fingerprint,
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "model_digest": _tree_digest(model_path),
        "dtype": "bfloat16",
        "instruction": args.instruction,
        "device": args.device,
        "batch_size": args.batch_size,
        "model_ready_seconds": round(ready_seconds, 3),
        "candidate_pairs": total_pairs,
        "prediction_seconds": round(prediction_seconds, 3),
        "pairs_per_second": round(total_pairs / prediction_seconds, 3),
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "profiles": [
            {
                "pipeline": "hybrid_candidates+reranker",
                "metrics": evaluate_retrieval(gold, tuple(reranker_runs)).as_dict(),
            },
            {
                "pipeline": "hybrid_candidates+hybrid_reranker_rrf",
                "fusion": {"hybrid_weight": 1.0, "reranker_weight": 2.0, "rrf_k": 60},
                "metrics": evaluate_retrieval(gold, tuple(fused_runs)).as_dict(),
            },
        ],
        "reranked_candidate_runs": candidate_receipts,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _candidate_sets(
    build: RepresentationBuild,
    gold: tuple[object, ...],
    profile: dict[str, Any],
) -> tuple[
    dict[str, tuple[UUID, ...]],
    dict[str, str | None],
    dict[str, dict[UUID, int]],
]:
    from asd_kontur.ntd.retrieval_benchmark import GoldQuery

    typed_gold = cast(tuple[GoldQuery, ...], gold)
    lexical = {run.case_id: run for run in run_lexical_benchmark(build, typed_gold)}
    chunk_by_key: dict[tuple[str, int | None, str | None], UUID] = {}
    for chunk in build.chunks:
        key = (
            chunk.document_digest,
            chunk.pages[0] if chunk.pages else None,
            chunk.clause_labels[0] if chunk.clause_labels else None,
        )
        chunk_by_key.setdefault(key, chunk.chunk_id)
    dense = {str(row["case_id"]): row for row in profile["dense_candidate_runs"]}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in build.chunks}
    designation_to_digest = {
        document.entry.designation: document.entry.digest for document in build.documents
    }
    result: dict[str, tuple[UUID, ...]] = {}
    hybrid_ranks: dict[str, dict[UUID, int]] = {}
    for case in typed_gold:
        scores: dict[UUID, float] = {}
        resolved_designation = lexical[case.case_id].resolved_designation
        resolved_digest = (
            designation_to_digest[resolved_designation]
            if resolved_designation is not None
            else None
        )
        for rank, raw_candidate in enumerate(
            cast(list[dict[str, object]], dense[case.case_id]["candidates"]), 1
        ):
            chunk_id = UUID(str(raw_candidate["chunk_id"]))
            chunk = chunks_by_id[chunk_id]
            if resolved_digest is not None and chunk.document_digest != resolved_digest:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (60 + rank)
        for rank, lexical_item in enumerate(lexical[case.case_id].items, 1):
            lexical_chunk_id = chunk_by_key.get(
                (
                    lexical_item.document_digest,
                    lexical_item.page_number,
                    lexical_item.clause_label,
                )
            )
            if lexical_chunk_id is not None:
                scores[lexical_chunk_id] = scores.get(lexical_chunk_id, 0.0) + 1.0 / (60 + rank)
        ordered = sorted(scores, key=lambda value: (-scores[value], str(value)))[:40]
        result[case.case_id] = tuple(ordered)
        hybrid_ranks[case.case_id] = {chunk_id: rank for rank, chunk_id in enumerate(ordered, 1)}
    return (
        result,
        {case_id: run.resolved_designation for case_id, run in lexical.items()},
        hybrid_ranks,
    )


def _items(
    values: list[tuple[float, QualificationChunk]],
    *,
    limit: int,
) -> tuple[RetrievedItem, ...]:
    result: list[RetrievedItem] = []
    seen: set[tuple[str, int | None, str | None]] = set()
    for score, chunk in values:
        item = RetrievedItem(
            chunk.document_digest,
            chunk.pages[0] if chunk.pages else None,
            chunk.clause_labels[0] if chunk.clause_labels else None,
            score,
        )
        key = (item.document_digest, item.page_number, item.clause_label)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) == limit:
            break
    return tuple(result)


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
