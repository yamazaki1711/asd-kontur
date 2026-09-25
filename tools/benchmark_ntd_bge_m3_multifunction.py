#!/usr/bin/env python3
"""Benchmark real BGE-M3 dense, sparse and late-interaction retrieval locally."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import resource
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np  # type: ignore[import-not-found]
import torch  # type: ignore[import-not-found]
from torch.nn import functional as functional  # type: ignore[import-not-found]
from transformers import AutoModel, AutoTokenizer  # type: ignore[import-not-found]

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


@dataclass(frozen=True, slots=True)
class EncodedBatch:
    dense: np.ndarray[Any, Any]
    sparse: tuple[dict[int, float], ...]
    token_counts: tuple[int, ...]
    colbert: tuple[np.ndarray[Any, Any], ...] | None


class BgeM3Encoder:
    """Small, pinned inference adapter matching BGE-M3's published heads."""

    def __init__(self, model_path: Path, *, device: str, max_length: int) -> None:
        self.device = torch.device(device)
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        self.model = AutoModel.from_pretrained(str(model_path), local_files_only=True)
        hidden = int(self.model.config.hidden_size)
        self.sparse_head = torch.nn.Linear(hidden, 1)
        self.colbert_head = torch.nn.Linear(hidden, hidden)
        self.sparse_head.load_state_dict(
            torch.load(model_path / "sparse_linear.pt", map_location="cpu", weights_only=True)
        )
        self.colbert_head.load_state_dict(
            torch.load(model_path / "colbert_linear.pt", map_location="cpu", weights_only=True)
        )
        self.model.to(self.device).eval()
        self.sparse_head.to(self.device).eval()
        self.colbert_head.to(self.device).eval()
        self.special_ids = frozenset(
            value
            for value in (
                self.tokenizer.cls_token_id,
                self.tokenizer.eos_token_id,
                self.tokenizer.pad_token_id,
                self.tokenizer.unk_token_id,
            )
            if value is not None
        )

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        include_colbert: bool,
    ) -> EncodedBatch:
        dense_values: list[np.ndarray[Any, Any]] = []
        sparse_values: list[dict[int, float]] = []
        token_counts: list[int] = []
        colbert_values: list[np.ndarray[Any, Any]] = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer(
                texts[start : start + batch_size],
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.inference_mode():
                hidden = self.model(**encoded, return_dict=True).last_hidden_state
                dense = functional.normalize(hidden[:, 0], dim=-1)
                weights = torch.relu(self.sparse_head(hidden)).squeeze(-1)
                colbert = (
                    functional.normalize(self.colbert_head(hidden[:, 1:]), dim=-1)
                    if include_colbert
                    else None
                )
            ids = encoded["input_ids"].detach().cpu().numpy()
            mask = encoded["attention_mask"].detach().cpu().numpy()
            raw_weights = weights.detach().float().cpu().numpy()
            dense_values.append(dense.detach().float().cpu().numpy())
            raw_colbert = colbert.detach().float().cpu().numpy() if colbert is not None else None
            for row in range(ids.shape[0]):
                count = int(mask[row].sum())
                token_counts.append(count)
                lexical: dict[int, float] = {}
                for token_id, weight in zip(
                    ids[row, :count], raw_weights[row, :count], strict=True
                ):
                    key = int(token_id)
                    if key in self.special_ids:
                        continue
                    lexical[key] = max(lexical.get(key, 0.0), float(weight))
                sparse_values.append(lexical)
                if raw_colbert is not None:
                    colbert_values.append(raw_colbert[row, : max(0, count - 1)])
        return EncodedBatch(
            np.concatenate(dense_values),
            tuple(sparse_values),
            tuple(token_counts),
            tuple(colbert_values) if include_colbert else None,
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
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--colbert-candidate-limit", type=int, default=20)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 32 or not 256 <= args.max_length <= 2048:
        raise ValueError("ntd_bge_m3_profile_invalid")
    if not 10 <= args.colbert_candidate_limit <= 50:
        raise ValueError("ntd_bge_m3_colbert_candidate_limit_invalid")

    corpus_digest = _file_digest(args.corpus)
    documents = read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest)
    build = build_representation(documents, profile=CONTEXTUAL_PROFILE)
    gold = load_gold_benchmark(args.gold)
    model_path = args.model.resolve(strict=True)
    ready_started = perf_counter()
    encoder = BgeM3Encoder(model_path, device=args.device, max_length=args.max_length)
    model_ready_seconds = perf_counter() - ready_started
    query_encoding_started = perf_counter()
    query_values = encoder.encode(
        [case.query for case in gold],
        batch_size=args.batch_size,
        include_colbert=True,
    )
    query_encoding_seconds = perf_counter() - query_encoding_started
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_identity = hashlib.sha256(
        f"{args.model_id}:{args.model_revision}:{build.fingerprint}:{args.max_length}".encode()
    ).hexdigest()
    dense_cache = args.cache_dir / f"{cache_identity}.dense.npz"
    sparse_cache = args.cache_dir / f"{cache_identity}.sparse.json.gz"
    passage_started = perf_counter()
    if dense_cache.is_file() and sparse_cache.is_file():
        stored = np.load(dense_cache)
        passage_dense = stored["vectors"]
        token_counts = tuple(int(value) for value in stored["token_counts"])
        with gzip.open(sparse_cache, "rt", encoding="utf-8") as stream:
            sparse_payload = json.load(stream)
        passage_sparse = tuple(
            {int(key): float(value) for key, value in row.items()}
            for row in sparse_payload["weights"]
        )
        if list(stored["chunk_ids"]) != [str(chunk.chunk_id) for chunk in build.chunks]:
            raise ValueError("ntd_bge_m3_cache_identity_mismatch")
        cache_reused = True
    else:
        passage_values = encoder.encode(
            [chunk.retrieval_text for chunk in build.chunks],
            batch_size=args.batch_size,
            include_colbert=False,
        )
        passage_dense = passage_values.dense
        passage_sparse = passage_values.sparse
        token_counts = passage_values.token_counts
        np.savez_compressed(
            dense_cache,
            vectors=passage_dense,
            token_counts=np.array(token_counts, dtype=np.int32),
            chunk_ids=np.array([str(chunk.chunk_id) for chunk in build.chunks]),
        )
        with gzip.open(sparse_cache, "wt", encoding="utf-8") as stream:
            json.dump(
                {
                    "chunk_ids": [str(chunk.chunk_id) for chunk in build.chunks],
                    "weights": [
                        {str(key): value for key, value in row.items()} for row in passage_sparse
                    ],
                },
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        cache_reused = False
    passage_seconds = perf_counter() - passage_started
    dense_scores = np.matmul(query_values.dense, passage_dense.T)
    sparse_scores = _sparse_scores(query_values.sparse, passage_sparse)
    lexical = run_lexical_benchmark(build, gold)
    allowed = _allowed_documents(build, lexical)
    dense_runs, dense_rankings = _score_runs(build.chunks, gold, dense_scores, lexical, allowed)
    sparse_runs, sparse_rankings = _score_runs(build.chunks, gold, sparse_scores, lexical, allowed)
    dense_sparse_runs, dense_sparse_rankings = _rrf_runs(
        build.chunks,
        gold,
        dense_rankings,
        sparse_rankings,
        lexical,
        allowed,
    )
    colbert_started = perf_counter()
    colbert_runs, colbert_rankings, colbert_bytes = _colbert_rerank(
        encoder,
        build.chunks,
        gold,
        query_values,
        dense_sparse_rankings,
        lexical,
        candidate_limit=args.colbert_candidate_limit,
        batch_size=args.batch_size,
    )
    colbert_seconds = perf_counter() - colbert_started
    multifunction_runs, _ = _rrf_runs(
        build.chunks,
        gold,
        dense_sparse_rankings,
        colbert_rankings,
        lexical,
        allowed,
    )
    payload: dict[str, object] = {
        "profile": "ntd-bge-m3-multifunction-benchmark@1.0.0",
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "representation_profile": CONTEXTUAL_PROFILE,
        "representation_fingerprint": build.fingerprint,
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "model_digest": _tree_digest(model_path),
        "dtype": "float32",
        "device": args.device,
        "dimension": int(passage_dense.shape[1]),
        "max_length": args.max_length,
        "batch_size": args.batch_size,
        "model_ready_seconds": round(model_ready_seconds, 3),
        "query_encoding_seconds": round(query_encoding_seconds, 3),
        "passage_encoding_seconds": round(passage_seconds, 3),
        "passages_per_second": round(len(build.chunks) / passage_seconds, 3),
        "cache_reused": cache_reused,
        "dense_cache": str(dense_cache),
        "dense_cache_digest": _file_digest(dense_cache),
        "sparse_cache": str(sparse_cache),
        "sparse_cache_digest": _file_digest(sparse_cache),
        "dense_index_bytes": int(passage_dense.nbytes),
        "sparse_index_bytes": sparse_cache.stat().st_size,
        "token_count": sum(token_counts),
        "truncated_chunk_count": sum(value == args.max_length for value in token_counts),
        "colbert_candidate_limit": args.colbert_candidate_limit,
        "colbert_candidate_bytes_materialized": colbert_bytes,
        "colbert_full_projection_bytes": sum(token_counts) * int(passage_dense.shape[1]) * 4,
        "colbert_seconds": round(colbert_seconds, 3),
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "profiles": [
            {"pipeline": "bge_m3_dense", "metrics": evaluate_retrieval(gold, dense_runs).as_dict()},
            {
                "pipeline": "bge_m3_sparse",
                "metrics": evaluate_retrieval(gold, sparse_runs).as_dict(),
            },
            {
                "pipeline": "bge_m3_dense_sparse_rrf",
                "metrics": evaluate_retrieval(gold, dense_sparse_runs).as_dict(),
            },
            {
                "pipeline": "bge_m3_colbert_rerank",
                "metrics": evaluate_retrieval(gold, colbert_runs).as_dict(),
            },
            {
                "pipeline": "bge_m3_dense_sparse_colbert_rrf",
                "metrics": evaluate_retrieval(gold, multifunction_runs).as_dict(),
            },
        ],
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _sparse_scores(
    queries: tuple[dict[int, float], ...],
    passages: tuple[dict[int, float], ...],
) -> np.ndarray[Any, Any]:
    result = np.zeros((len(queries), len(passages)), dtype=np.float32)
    for query_index, query in enumerate(queries):
        for passage_index, passage in enumerate(passages):
            result[query_index, passage_index] = sum(
                query_weight * passage.get(token, 0.0) for token, query_weight in query.items()
            )
    return result


def _allowed_documents(build: Any, lexical: tuple[QueryRun, ...]) -> dict[str, str | None]:
    by_designation = {
        document.entry.designation: document.entry.digest for document in build.documents
    }
    return {
        run.case_id: (
            by_designation[run.resolved_designation]
            if run.resolved_designation is not None
            else None
        )
        for run in lexical
    }


def _score_runs(
    chunks: tuple[QualificationChunk, ...],
    gold: tuple[GoldQuery, ...],
    scores: np.ndarray[Any, Any],
    lexical: tuple[QueryRun, ...],
    allowed: dict[str, str | None],
) -> tuple[tuple[QueryRun, ...], dict[str, tuple[int, ...]]]:
    lexical_by_id = {run.case_id: run for run in lexical}
    runs: list[QueryRun] = []
    rankings: dict[str, tuple[int, ...]] = {}
    for query_index, case in enumerate(gold):
        started = perf_counter()
        values = [
            index
            for index in np.argsort(-scores[query_index])
            if allowed[case.case_id] is None
            or chunks[int(index)].document_digest == allowed[case.case_id]
        ]
        rankings[case.case_id] = tuple(int(value) for value in values[:50])
        runs.append(
            QueryRun(
                case.case_id,
                _items(chunks, rankings[case.case_id], scores[query_index], limit=10),
                (perf_counter() - started) * 1000,
                lexical_by_id[case.case_id].resolved_designation,
            )
        )
    return tuple(runs), rankings


def _rrf_runs(
    chunks: tuple[QualificationChunk, ...],
    gold: tuple[GoldQuery, ...],
    left: dict[str, tuple[int, ...]],
    right: dict[str, tuple[int, ...]],
    lexical: tuple[QueryRun, ...],
    allowed: dict[str, str | None],
) -> tuple[tuple[QueryRun, ...], dict[str, tuple[int, ...]]]:
    lexical_by_id = {run.case_id: run for run in lexical}
    runs: list[QueryRun] = []
    rankings: dict[str, tuple[int, ...]] = {}
    for case in gold:
        started = perf_counter()
        scores: dict[int, float] = {}
        for values in (left[case.case_id], right[case.case_id]):
            for rank, index in enumerate(values, 1):
                if allowed[case.case_id] is not None and (
                    chunks[index].document_digest != allowed[case.case_id]
                ):
                    continue
                scores[index] = scores.get(index, 0.0) + 1.0 / (60 + rank)
        order = tuple(sorted(scores, key=lambda value: (-scores[value], value)))
        rankings[case.case_id] = order
        score_row = np.array([scores.get(index, 0.0) for index in range(len(chunks))])
        runs.append(
            QueryRun(
                case.case_id,
                _items(chunks, order, score_row, limit=10),
                (perf_counter() - started) * 1000,
                lexical_by_id[case.case_id].resolved_designation,
            )
        )
    return tuple(runs), rankings


def _colbert_rerank(
    encoder: BgeM3Encoder,
    chunks: tuple[QualificationChunk, ...],
    gold: tuple[GoldQuery, ...],
    query_values: EncodedBatch,
    candidates: dict[str, tuple[int, ...]],
    lexical: tuple[QueryRun, ...],
    *,
    candidate_limit: int,
    batch_size: int,
) -> tuple[tuple[QueryRun, ...], dict[str, tuple[int, ...]], int]:
    if query_values.colbert is None:
        raise ValueError("ntd_bge_m3_query_colbert_absent")
    lexical_by_id = {run.case_id: run for run in lexical}
    runs: list[QueryRun] = []
    rankings: dict[str, tuple[int, ...]] = {}
    materialized_bytes = 0
    for query_index, case in enumerate(gold):
        started = perf_counter()
        indices = candidates[case.case_id][:candidate_limit]
        values = encoder.encode(
            [chunks[index].retrieval_text for index in indices],
            batch_size=batch_size,
            include_colbert=True,
        )
        if values.colbert is None:
            raise ValueError("ntd_bge_m3_passage_colbert_absent")
        scores: dict[int, float] = {}
        query = query_values.colbert[query_index]
        materialized_bytes += query.nbytes
        for index, passage in zip(indices, values.colbert, strict=True):
            materialized_bytes += passage.nbytes
            similarities = np.matmul(query, passage.T)
            scores[index] = float(similarities.max(axis=1).sum() / max(1, query.shape[0]))
        order = tuple(sorted(scores, key=lambda value: (-scores[value], value)))
        rankings[case.case_id] = order
        score_row = np.array([scores.get(index, 0.0) for index in range(len(chunks))])
        runs.append(
            QueryRun(
                case.case_id,
                _items(chunks, order, score_row, limit=10),
                (perf_counter() - started) * 1000,
                lexical_by_id[case.case_id].resolved_designation,
            )
        )
    return tuple(runs), rankings, materialized_bytes


def _items(
    chunks: tuple[QualificationChunk, ...],
    order: tuple[int, ...],
    scores: np.ndarray[Any, Any],
    *,
    limit: int,
) -> tuple[RetrievedItem, ...]:
    result: list[RetrievedItem] = []
    seen: set[tuple[str, int | None, str | None]] = set()
    for index in order:
        chunk = chunks[index]
        item = RetrievedItem(
            chunk.document_digest,
            chunk.pages[0] if chunk.pages else None,
            chunk.clause_labels[0] if chunk.clause_labels else None,
            float(scores[index]),
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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


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
