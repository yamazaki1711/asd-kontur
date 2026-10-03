#!/usr/bin/env python3
"""Rebuild qualification structure from pinned page transcriptions without OCR."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from asd_kontur.ntd.retrieval_qualification import (
    QUALIFICATION_OCR_STRUCTURAL_PROFILE,
    QualificationDocument,
    qualification_document_from_pages,
    read_extraction_cache,
    write_extraction_cache,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--input-corpus-digest", required=True)
    parser.add_argument("--input-cache", required=True, type=Path)
    parser.add_argument("--output-cache", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    args = parser.parse_args()
    if (
        not args.input_corpus_digest.startswith("sha256:")
        or len(args.input_corpus_digest) != 71
        or any(character not in "0123456789abcdef" for character in args.input_corpus_digest[7:])
    ):
        raise ValueError("ntd_qualification_input_corpus_digest_invalid")
    corpus_digest = _file_digest(args.corpus)
    source = read_extraction_cache(
        args.input_cache,
        corpus_digest=args.input_corpus_digest,
    )
    corpus = json.loads(args.corpus.read_bytes())
    selected_digests = {str(item["sha256"]) for item in corpus["documents"]}
    filtered = tuple(document for document in source if document.entry.digest in selected_digests)
    if (
        len(filtered) != len(selected_digests)
        or {document.entry.digest for document in filtered} != selected_digests
    ):
        raise ValueError("ntd_qualification_cache_selection_mismatch")
    excluded_digests = sorted(
        document.entry.digest
        for document in source
        if document.entry.digest not in selected_digests
    )
    source = filtered
    rebuilt_documents: list[QualificationDocument] = []
    blocked_documents: list[QualificationDocument] = []
    for document in source:
        entry = document.entry
        blocked = (
            entry.expected_pages > 0
            and entry.source_path is None
            and not document.page_text
            and not document.units
        )
        if blocked:
            rebuilt_documents.append(document)
            blocked_documents.append(document)
            continue
        rebuilt_documents.append(qualification_document_from_pages(entry, document.page_text))
    rebuilt = tuple(rebuilt_documents)
    fingerprint = write_extraction_cache(
        args.output_cache,
        rebuilt,
        corpus_digest=corpus_digest,
        extraction_profile=QUALIFICATION_OCR_STRUCTURAL_PROFILE,
    )
    receipt: dict[str, object] = {
        "profile": QUALIFICATION_OCR_STRUCTURAL_PROFILE,
        "corpus_digest": corpus_digest,
        "input_corpus_digest": args.input_corpus_digest,
        "input_cache_digest": _file_digest(args.input_cache),
        "output_cache": str(args.output_cache),
        "output_cache_digest": _file_digest(args.output_cache),
        "output_cache_fingerprint": fingerprint,
        "document_count": len(rebuilt),
        "selected_document_count": len(selected_digests),
        "excluded_document_digests": excluded_digests,
        "page_count": sum(len(document.page_text) for document in rebuilt),
        "page_denominator": sum(document.entry.expected_pages for document in rebuilt),
        "page_extracted": sum(len(document.page_text) for document in rebuilt),
        "page_blocked": sum(document.entry.expected_pages for document in blocked_documents),
        "blocked_document_count": len(blocked_documents),
        "blocked_document_identities": [
            {
                "designation": document.entry.designation,
                "digest": document.entry.digest,
            }
            for document in blocked_documents
        ],
        "structural_unit_count": sum(len(document.units) for document in rebuilt),
        "table_of_contents_unit_count": sum(
            unit.kind == "table_of_contents" for document in rebuilt for unit in document.units
        ),
        "source_text_changed": False,
    }
    receipt["receipt_fingerprint"] = _semantic_digest(receipt)
    args.output_receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
