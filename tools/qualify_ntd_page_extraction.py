#!/usr/bin/env python3
"""Create a source-grounded page extraction cache for the NTD benchmark corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from asd_kontur.document_understanding.native import inspect_pdf_path
from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.file_processing import render_normative_pdf_page
from asd_kontur.ntd.retrieval_qualification import (
    QUALIFICATION_OCR_EXTRACTION_PROFILE,
    QualificationCorpusEntry,
    QualificationDocument,
    load_qualification_entries,
    qualification_document_from_pages,
    write_extraction_cache,
)

OCR_PROFILE = "apple-vision-accurate-page-qualification@1.0.0"
_RU_IE = "\N{CYRILLIC SMALL LETTER IE}"
_RU_IO = "\N{CYRILLIC SMALL LETTER IO}"
_OCR_KINDS = frozenset(
    {
        "raster_only_scan",
        "damaged_or_unreadable_encoding",
        "mixed_text_raster",
        "drawing_or_scheme",
    }
)


@dataclass(frozen=True, slots=True)
class PageRoute:
    page_number: int
    page_kind: str
    native_text: str
    needs_ocr: bool


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--ocr-executable", required=True, type=Path)
    parser.add_argument("--cache-output", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("ntd_qualification_ocr_workers_invalid")
    executable = args.ocr_executable.resolve(strict=True)
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("ntd_qualification_ocr_executable_invalid")
    corpus_digest = _file_digest(args.corpus)
    entries = load_qualification_entries(corpus_manifest=args.corpus, audit_json=args.audit)
    documents: list[QualificationDocument] = []
    receipts: list[dict[str, object]] = []
    for entry in entries:
        started = perf_counter()
        if entry.source_path is None:
            documents.append(QualificationDocument(entry, (), ()))
            receipts.append(
                {
                    "designation": entry.designation,
                    "document_digest": entry.digest,
                    "page_denominator": entry.expected_pages,
                    "terminal_pages": 0,
                    "extracted_pages": 0,
                    "blocked_pages": entry.expected_pages,
                    "terminal_outcome": "blocked_bytes_unavailable",
                    "pages": [],
                    "elapsed_seconds": round(perf_counter() - started, 3),
                }
            )
            continue
        document, receipt = _extract_document(entry, executable, workers=args.workers)
        documents.append(document)
        receipts.append(
            {
                **receipt,
                "elapsed_seconds": round(perf_counter() - started, 3),
            }
        )
    cache_fingerprint = write_extraction_cache(
        args.cache_output,
        tuple(documents),
        corpus_digest=corpus_digest,
        extraction_profile=QUALIFICATION_OCR_EXTRACTION_PROFILE,
    )
    payload: dict[str, object] = {
        "profile": QUALIFICATION_OCR_EXTRACTION_PROFILE,
        "corpus_digest": corpus_digest,
        "audit_digest": _file_digest(args.audit),
        "ocr_profile": OCR_PROFILE,
        "ocr_executable_digest": _file_digest(executable),
        "cache_path": str(args.cache_output),
        "cache_fingerprint": cache_fingerprint,
        "document_denominator": len(entries),
        "documents": receipts,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _extract_document(
    entry: QualificationCorpusEntry,
    executable: Path,
    *,
    workers: int,
) -> tuple[QualificationDocument, dict[str, object]]:
    source_path = entry.source_path
    assert source_path is not None
    native = inspect_pdf_path(
        path=source_path,
        document_id=deterministic_uuid(f"ntd-qualification-document:{entry.digest}"),
        document_version=1,
        source_version_id=deterministic_uuid(f"ntd-qualification-source:{entry.digest}"),
    )
    if len(native.pages) != entry.expected_pages:
        raise ValueError("ntd_qualification_page_count_mismatch")
    routes = tuple(
        PageRoute(
            page.page_number,
            page.health.primary_kind.value,
            "\n".join(
                element.raw_text.strip()
                for element in sorted(page.elements, key=lambda value: value.reading_order)
                if element.raw_text.strip()
            ),
            page.health.primary_kind.value in _OCR_KINDS,
        )
        for page in native.pages
    )
    results: dict[int, tuple[str, dict[str, object]]] = {}

    def run(route: PageRoute) -> tuple[int, str, dict[str, object]]:
        if not route.needs_ocr:
            terminal = "native_complete" if route.native_text.strip() else "blank_verified"
            return (
                route.page_number,
                route.native_text,
                {
                    "page_number": route.page_number,
                    "page_kind": route.page_kind,
                    "route": "native",
                    "terminal_outcome": terminal,
                    "raw_text_digest": _digest(route.native_text.encode()),
                    "characters": len(route.native_text),
                },
            )
        return _ocr_page(source_path, route, executable)

    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="ntd-qualification-ocr"
    ) as pool:
        for page_number, text, receipt in pool.map(run, routes):
            results[page_number] = (text, receipt)
    ordered_pages = tuple(results[index][0] for index in range(1, entry.expected_pages + 1))
    page_receipts = [results[index][1] for index in range(1, entry.expected_pages + 1)]
    extracted = sum(bool(value.strip()) for value in ordered_pages)
    blocked = sum(str(value["terminal_outcome"]).startswith("blocked") for value in page_receipts)
    terminal = len(page_receipts)
    outcome = "complete" if blocked == 0 else "partial"
    return qualification_document_from_pages(entry, ordered_pages), {
        "designation": entry.designation,
        "document_digest": entry.digest,
        "page_denominator": entry.expected_pages,
        "terminal_pages": terminal,
        "extracted_pages": extracted,
        "blocked_pages": blocked,
        "terminal_outcome": outcome,
        "pages": page_receipts,
    }


def _ocr_page(
    path: Path,
    route: PageRoute,
    executable: Path,
) -> tuple[int, str, dict[str, object]]:
    rendered = render_normative_pdf_page(
        path,
        page_index=route.page_number,
        source_rotation_degrees=0,
    )
    request_digest = _semantic_digest(
        {"profile": OCR_PROFILE, "render_digest": rendered.render_digest}
    )
    with tempfile.NamedTemporaryFile(prefix="asd-ntd-qualification-", suffix=".png") as image:
        image.write(rendered.png_bytes)
        image.flush()
        completed = subprocess.run(
            [str(executable), image.name],
            capture_output=True,
            check=False,
            timeout=180,
        )
    response_digest = _digest(completed.stdout)
    observations: list[dict[str, object]] = []
    if completed.returncode == 0:
        try:
            raw = json.loads(completed.stdout)
            if isinstance(raw, dict) and isinstance(raw.get("observations"), list):
                observations = [value for value in raw["observations"] if isinstance(value, dict)]
        except json.JSONDecodeError:
            observations = []
    ocr_text = "\n".join(
        str(item.get("text", "")).strip()
        for item in observations
        if str(item.get("text", "")).strip()
    )
    text = (
        _merge_page_text(route.native_text, ocr_text)
        if route.page_kind == "mixed_text_raster"
        else ocr_text or route.native_text
    )
    terminal = "ocr_complete" if text.strip() else "blocked_ocr_empty"
    receipt: dict[str, object] = {
        "page_number": route.page_number,
        "page_kind": route.page_kind,
        "route": "native_plus_region_ocr" if route.native_text.strip() else "page_ocr",
        "terminal_outcome": terminal,
        "render_digest": rendered.render_digest,
        "request_digest": request_digest,
        "response_digest": response_digest,
        "observation_count": len(observations),
        "raw_text_digest": _digest(text.encode()),
        "characters": len(text),
    }
    return route.page_number, text, receipt


def _merge_page_text(native: str, ocr: str) -> str:
    lines = [line.strip() for line in native.splitlines() if line.strip()]
    normalized = {" ".join(line.casefold().replace(_RU_IO, _RU_IE).split()) for line in lines}
    for line in (value.strip() for value in ocr.splitlines() if value.strip()):
        key = " ".join(line.casefold().replace(_RU_IO, _RU_IE).split())
        if key not in normalized:
            lines.append(line)
            normalized.add(key)
    return "\n".join(lines)


def _file_digest(path: Path) -> str:
    return _digest(path.read_bytes())


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return _digest(encoded)


if __name__ == "__main__":
    raise SystemExit(main())
