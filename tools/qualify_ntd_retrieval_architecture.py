#!/usr/bin/env python3
"""Measure representation/retrieval profiles on the pinned NTD gold corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from asd_kontur.ntd.retrieval_benchmark import evaluate_retrieval, load_gold_benchmark
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
    FIXED_PROFILE,
    HIERARCHICAL_PROFILE,
    STRUCTURE_PROFILE,
    QualificationDocument,
    build_representation,
    extract_native_document,
    load_qualification_entries,
    read_extraction_cache,
    run_lexical_benchmark,
    write_extraction_cache,
)
from asd_kontur.ntd.typed_kag import build_qualification_kag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extraction-cache", type=Path, required=True)
    args = parser.parse_args()

    corpus_digest = _file_digest(args.corpus)
    extraction: list[dict[str, object]] = []
    if args.extraction_cache.is_file():
        documents = list(read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest))
        for document in documents:
            extraction.append(_extraction_row(document, elapsed_ms=0.0, cached=True))
    else:
        entries = load_qualification_entries(corpus_manifest=args.corpus, audit_json=args.audit)
        documents = []
        for entry in entries:
            started = perf_counter()
            document = (
                QualificationDocument(entry, (), ())
                if entry.source_path is None
                else extract_native_document(entry)
            )
            documents.append(document)
            extraction.append(
                _extraction_row(
                    document,
                    elapsed_ms=(perf_counter() - started) * 1000,
                    cached=False,
                )
            )
        write_extraction_cache(
            args.extraction_cache,
            tuple(documents),
            corpus_digest=corpus_digest,
        )
    gold = load_gold_benchmark(args.gold)
    typed_kag = build_qualification_kag(tuple(documents))
    profiles: list[dict[str, object]] = []
    for profile in (FIXED_PROFILE, STRUCTURE_PROFILE, CONTEXTUAL_PROFILE, HIERARCHICAL_PROFILE):
        build_started = perf_counter()
        build = build_representation(tuple(documents), profile=profile)
        build_ms = (perf_counter() - build_started) * 1000
        runs = run_lexical_benchmark(
            build,
            gold,
            hierarchical=profile == HIERARCHICAL_PROFILE,
        )
        profiles.append(
            {
                "representation_profile": profile,
                "retrieval_pipeline": (
                    "exact+lexical+hierarchical"
                    if profile == HIERARCHICAL_PROFILE
                    else "exact+lexical"
                ),
                "chunk_count": len(build.chunks),
                "hierarchy_edge_count": len(build.hierarchy),
                "representation_fingerprint": build.fingerprint,
                "build_ms": round(build_ms, 3),
                "metrics": evaluate_retrieval(gold, runs).as_dict(),
            }
        )
    payload = {
        "profile": "ntd-retrieval-qualification-run@1.0.0",
        "audit_digest": _file_digest(args.audit),
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "question_count": len(gold),
        "extraction": extraction,
        "typed_kag": {
            "profile": typed_kag.profile,
            "nodes": len(typed_kag.nodes),
            "canonical_edges": len(typed_kag.edges),
            "edge_candidates": len(typed_kag.candidates),
            "relations": sorted({edge.relation for edge in typed_kag.edges}),
            "fingerprint": typed_kag.fingerprint,
        },
        "profiles": profiles,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _extraction_row(
    document: QualificationDocument,
    *,
    elapsed_ms: float,
    cached: bool,
) -> dict[str, object]:
    if document.entry.source_path is None:
        outcome = "blocked_bytes_unavailable"
    else:
        outcome = "text_available" if any(document.page_text) else "text_absent"
    return {
        "designation": document.entry.designation,
        "document_digest": document.entry.digest,
        "terminal_outcome": outcome,
        "page_denominator": document.entry.expected_pages,
        "pages_with_native_text": sum(bool(value.strip()) for value in document.page_text),
        "structural_units": len(document.units),
        "elapsed_ms": round(elapsed_ms, 3),
        "cache_reused": cached,
    }


if __name__ == "__main__":
    raise SystemExit(main())
