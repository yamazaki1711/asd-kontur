"""Qualification-only document representations for modern NTD retrieval.

The module compares representations over exact admitted bytes before a profile
is allowed into the resumable production builder.  It never changes normative
authority and never publishes a provision.
"""

# ruff: noqa: RUF001 -- exact Russian designations and morphology are intentional.

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.retrieval_benchmark import GoldQuery, QueryRun, RetrievedItem
from asd_kontur.ntd.search_corpus import designation_aliases, normalize_designation

QUALIFICATION_CORPUS_PROFILE = "ntd-retrieval-qualification-corpus@2.0.0"
QUALIFICATION_EXTRACTION_PROFILE = "poppler-layout-structural-qualification@1.0.0"
QUALIFICATION_OCR_EXTRACTION_PROFILE = "native-apple-vision-structural-qualification@1.0.0"
QUALIFICATION_STRUCTURAL_PROFILE = "ntd-structural-reconstruction@1.1.0"
QUALIFICATION_OCR_STRUCTURAL_PROFILE = "native-apple-vision-structural-qualification@1.1.0"
FIXED_PROFILE = "ntd-fixed-chunks@1.0.0"
STRUCTURE_PROFILE = "ntd-structure-aware-chunks@1.0.0"
CONTEXTUAL_PROFILE = "ntd-contextual-chunks@1.0.0"
HIERARCHICAL_PROFILE = "ntd-hierarchical-retrieval@1.0.0"
_TOKEN = re.compile(r"[0-9]+(?:[.\-][0-9]+)*|[a-zа-яё]+", re.IGNORECASE)
_CLAUSE = re.compile(r"^(\d+(?:\.\d+)+|приложение\s+[а-яa-z0-9]+|таблица\s+[а-яa-z0-9.\-]+)", re.I)
_STRUCTURAL_LINE = re.compile(
    r"^(?P<label>\d+(?:\.\d+){0,5})[.)]?\s+(?P<text>[А-ЯA-Zа-яё].{2,})$",
    re.IGNORECASE,
)
_APPENDIX_LINE = re.compile(r"^(?P<label>приложение\s+[А-ЯA-Z0-9]+)\b(?P<text>.*)$", re.I)
_TABLE_LINE = re.compile(r"^(?P<label>таблица\s+[А-ЯA-Z0-9.\-]+)\b(?P<text>.*)$", re.I)
_NOTE_LINE = re.compile(r"^(?P<label>примечани[ея])\b(?P<text>.*)$", re.I)
_TOC_LINE = re.compile(r"(?:\.{4,}|…{3,})\s*\d+\s*$")
_RUSSIAN_SUFFIXES = tuple(
    sorted(
        {
            "иями",
            "ями",
            "ами",
            "его",
            "ого",
            "ему",
            "ому",
            "ение",
            "ений",
            "ости",
            "овать",
            "ирован",
            "ая",
            "яя",
            "ий",
            "ый",
            "ой",
            "ам",
            "ям",
            "ах",
            "ях",
            "ов",
            "ев",
            "ы",
            "и",
            "а",
            "я",
            "у",
            "ю",
            "е",
        },
        key=len,
        reverse=True,
    )
)


@dataclass(frozen=True, slots=True)
class QualificationCorpusEntry:
    designation: str
    title: str
    digest: str
    authority_class: str
    expected_pages: int
    source_path: Path | None
    features: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualificationUnit:
    unit_id: UUID
    document_digest: str
    ordinal: int
    kind: str
    structural_path: str
    parent_path: str | None
    heading: str | None
    clause_label: str | None
    pages: tuple[int, ...]
    line_pages: tuple[int, ...]
    raw_text: str
    normalized_text: str


@dataclass(frozen=True, slots=True)
class QualificationChunk:
    chunk_id: UUID
    profile: str
    document_digest: str
    ordinal: int
    structural_path: str
    parent_path: str | None
    clause_labels: tuple[str, ...]
    pages: tuple[int, ...]
    raw_text: str
    derived_context: str
    retrieval_text: str


@dataclass(frozen=True, slots=True)
class QualificationDocument:
    entry: QualificationCorpusEntry
    units: tuple[QualificationUnit, ...]
    page_text: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepresentationBuild:
    profile: str
    documents: tuple[QualificationDocument, ...]
    chunks: tuple[QualificationChunk, ...]
    hierarchy: tuple[tuple[str, str], ...]
    fingerprint: str


def write_extraction_cache(
    path: Path,
    documents: tuple[QualificationDocument, ...],
    *,
    corpus_digest: str,
    extraction_profile: str = QUALIFICATION_EXTRACTION_PROFILE,
) -> str:
    """Persist qualification extraction outside Git with a semantic fingerprint."""

    payload: dict[str, Any] = {
        "profile": "ntd-qualification-extraction-cache@1.0.0",
        "extraction_profile": extraction_profile,
        "corpus_digest": corpus_digest,
        "documents": [
            {
                "entry": {
                    "designation": document.entry.designation,
                    "title": document.entry.title,
                    "digest": document.entry.digest,
                    "authority_class": document.entry.authority_class,
                    "expected_pages": document.entry.expected_pages,
                    "source_path": (
                        str(document.entry.source_path) if document.entry.source_path else None
                    ),
                    "features": document.entry.features,
                },
                "units": [
                    {
                        "unit_id": str(unit.unit_id),
                        "ordinal": unit.ordinal,
                        "kind": unit.kind,
                        "structural_path": unit.structural_path,
                        "parent_path": unit.parent_path,
                        "heading": unit.heading,
                        "clause_label": unit.clause_label,
                        "pages": unit.pages,
                        "line_pages": unit.line_pages,
                        "raw_text": unit.raw_text,
                        "normalized_text": unit.normalized_text,
                    }
                    for unit in document.units
                ],
                "page_text": document.page_text,
            }
            for document in documents
        ],
    }
    payload["fingerprint"] = _digest(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(filename=str(path), mode="wb", compresslevel=6, mtime=0) as stream:
        stream.write(encoded)
    return str(payload["fingerprint"])


def read_extraction_cache(
    path: Path,
    *,
    corpus_digest: str,
    expected_profile: str | None = None,
) -> tuple[QualificationDocument, ...]:
    with gzip.open(path, "rb") as stream:
        payload = json.loads(stream.read())
    fingerprint = payload.pop("fingerprint", None)
    calculated = _digest(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        fingerprint != calculated
        or payload.get("corpus_digest") != corpus_digest
        or payload.get("extraction_profile")
        not in {
            QUALIFICATION_EXTRACTION_PROFILE,
            QUALIFICATION_OCR_EXTRACTION_PROFILE,
            QUALIFICATION_OCR_STRUCTURAL_PROFILE,
        }
        or (expected_profile is not None and payload.get("extraction_profile") != expected_profile)
    ):
        raise ValueError("ntd_qualification_extraction_cache_mismatch")
    result: list[QualificationDocument] = []
    for raw_document in payload["documents"]:
        raw_entry = raw_document["entry"]
        raw_path = raw_entry.get("source_path")
        entry = QualificationCorpusEntry(
            str(raw_entry["designation"]),
            str(raw_entry["title"]),
            str(raw_entry["digest"]),
            str(raw_entry["authority_class"]),
            int(raw_entry["expected_pages"]),
            Path(str(raw_path)) if raw_path else None,
            tuple(str(value) for value in raw_entry["features"]),
        )
        units = tuple(
            QualificationUnit(
                UUID(str(unit["unit_id"])),
                entry.digest,
                int(unit["ordinal"]),
                str(unit["kind"]),
                str(unit["structural_path"]),
                str(unit["parent_path"]) if unit.get("parent_path") is not None else None,
                str(unit["heading"]) if unit.get("heading") is not None else None,
                str(unit["clause_label"]) if unit.get("clause_label") is not None else None,
                tuple(int(value) for value in unit["pages"]),
                tuple(int(value) for value in unit["line_pages"]),
                str(unit["raw_text"]),
                str(unit["normalized_text"]),
            )
            for unit in raw_document["units"]
        )
        result.append(
            QualificationDocument(
                entry,
                units,
                tuple(str(value) for value in raw_document["page_text"]),
            )
        )
    return tuple(result)


def load_qualification_entries(
    *,
    corpus_manifest: Path,
    audit_json: Path,
) -> tuple[QualificationCorpusEntry, ...]:
    """Resolve the selected digests only through the accepted immutable audit."""

    manifest = json.loads(corpus_manifest.read_bytes())
    audit = json.loads(audit_json.read_bytes())
    if manifest.get("profile") != QUALIFICATION_CORPUS_PROFILE:
        raise ValueError("ntd_qualification_corpus_profile_invalid")
    expected_audit = manifest["source_audit"]
    actual_digest = "sha256:" + hashlib.sha256(audit_json.read_bytes()).hexdigest()
    if expected_audit["sha256"] != actual_digest:
        raise ValueError("ntd_qualification_audit_digest_mismatch")
    if expected_audit["semantic_fingerprint"] != audit.get("semantic_fingerprint"):
        raise ValueError("ntd_qualification_audit_fingerprint_mismatch")
    by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audit["artifacts"]:
        if row.get("sha256"):
            by_digest[str(row["sha256"])].append(row)
    result: list[QualificationCorpusEntry] = []
    for selected in manifest["documents"]:
        digest = str(selected["sha256"])
        rows = by_digest.get(digest, [])
        if not rows:
            raise ValueError(f"ntd_qualification_digest_absent:{digest}")
        ordinal = int(selected["audit_ordinal"])
        row = next((item for item in rows if int(item["ordinal"]) == ordinal), None)
        if row is None:
            raise ValueError(f"ntd_qualification_ordinal_mismatch:{digest}")
        raw_path = row.get("object_plane_path") or row.get("source_path")
        source_path = Path(str(raw_path)) if raw_path and Path(str(raw_path)).is_file() else None
        result.append(
            QualificationCorpusEntry(
                str(selected["designation"]),
                str(selected["title"]),
                digest,
                str(selected["authority_class"]),
                int(selected["expected_pages"]),
                source_path,
                tuple(str(item) for item in selected["features"]),
            )
        )
    if len(result) != 9 or len({item.digest for item in result}) != 9:
        raise ValueError("ntd_qualification_corpus_denominator_invalid")
    return tuple(result)


def extract_native_document(entry: QualificationCorpusEntry) -> QualificationDocument:
    """Extract native structure for a single qualification object."""

    if entry.source_path is None:
        raise ValueError(f"ntd_qualification_bytes_unavailable:{entry.digest}")
    pages = _extract_poppler_layout(entry.source_path)
    if len(pages) != entry.expected_pages:
        raise ValueError(f"ntd_qualification_page_count_mismatch:{entry.digest}")
    return QualificationDocument(entry, _reconstruct_text_units(entry, pages), pages)


def qualification_document_from_pages(
    entry: QualificationCorpusEntry,
    pages: tuple[str, ...],
) -> QualificationDocument:
    """Rebuild deterministic structural units after a qualified page route."""

    if len(pages) != entry.expected_pages:
        raise ValueError("ntd_qualification_page_count_mismatch")
    return QualificationDocument(entry, _reconstruct_text_units(entry, pages), pages)


def _extract_poppler_layout(path: Path) -> tuple[str, ...]:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise ValueError("ntd_qualification_pdftotext_unavailable")
    completed = subprocess.run(
        [executable, "-layout", str(path), "-"],
        check=False,
        capture_output=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise ValueError("ntd_qualification_pdftotext_failed")
    text = completed.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return tuple(page.replace("\r\n", "\n").replace("\r", "\n") for page in pages)


def _reconstruct_text_units(
    entry: QualificationCorpusEntry,
    pages: tuple[str, ...],
) -> tuple[QualificationUnit, ...]:
    recurring = _recurring_margin_lines(pages)
    table_of_contents_pages = _table_of_contents_pages(pages)
    builders: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section_stack: list[tuple[int, str]] = []
    path_occurrences: Counter[str] = Counter()
    preamble = 0
    for page_number, page in enumerate(pages, 1):
        if page_number in table_of_contents_pages:
            lines = [
                " ".join(raw_line.split())
                for raw_line in page.splitlines()
                if raw_line.strip() and " ".join(raw_line.split()) not in recurring
            ]
            if lines:
                builders.append(
                    {
                        "path": f"table-of-contents:{page_number}",
                        "parent": None,
                        "kind": "table_of_contents",
                        "heading": "Содержание",
                        "label": None,
                        "lines": lines,
                        "line_pages": [page_number] * len(lines),
                        "pages": {page_number},
                    }
                )
            current = None
            section_stack = []
            continue
        for raw_line in page.splitlines():
            line = " ".join(raw_line.split())
            if not line or line in recurring or _TOC_LINE.search(line):
                continue
            matched = _structural_match(line)
            if matched is None:
                if current is None:
                    preamble += 1
                    current = _new_unit_builder(
                        entry,
                        f"preamble:{preamble}",
                        None,
                        "document",
                        None,
                        None,
                        line,
                        page_number,
                    )
                    builders.append(current)
                else:
                    current["lines"].append(line)
                    current["line_pages"].append(page_number)
                    current["pages"].add(page_number)
                continue
            label, kind, heading = matched
            if kind in {"section", "clause", "subclause"}:
                depth = label.count(".") + 1
                section_stack = [item for item in section_stack if item[0] < depth]
                parent_path = section_stack[-1][1] if section_stack else None
                base_path = label
            elif kind == "appendix":
                parent_path = None
                section_stack = [(1, label)]
                base_path = label.casefold().replace(" ", ":", 1)
            else:
                parent_path = section_stack[-1][1] if section_stack else None
                base_path = f"{parent_path + '/' if parent_path else ''}{label.casefold()}"
            occurrence = path_occurrences[base_path]
            path_occurrences[base_path] += 1
            structural_path = (
                base_path if occurrence == 0 else f"{base_path}@occurrence:{occurrence + 1}"
            )
            if kind in {"section", "clause", "subclause"}:
                section_stack.append((depth, structural_path))
            current = _new_unit_builder(
                entry,
                structural_path,
                parent_path,
                kind,
                heading,
                label,
                line,
                page_number,
            )
            builders.append(current)
    result: list[QualificationUnit] = []
    for ordinal, builder in enumerate(builders, 1):
        raw_text = "\n".join(builder["lines"])
        pages_value = tuple(sorted(builder["pages"]))
        identity = deterministic_uuid(
            f"ntd-qualification-unit:{entry.digest}:{builder['path']}:{_digest(raw_text.encode())}"
        )
        result.append(
            QualificationUnit(
                identity,
                entry.digest,
                ordinal,
                str(builder["kind"]),
                str(builder["path"]),
                str(builder["parent"]) if builder["parent"] is not None else None,
                str(builder["heading"]) if builder["heading"] is not None else None,
                str(builder["label"]) if builder["label"] is not None else None,
                pages_value,
                tuple(int(value) for value in builder["line_pages"]),
                raw_text,
                " ".join(raw_text.casefold().replace("ё", "е").split()),
            )
        )
    return tuple(result)


def _table_of_contents_pages(pages: tuple[str, ...]) -> frozenset[int]:
    """Identify a contiguous contents block without promoting its labels to clauses."""

    starts = [
        page_number
        for page_number, page in enumerate(pages, 1)
        if any(
            re.fullmatch(r"(?:содержание|оглавление)", " ".join(line.split()), re.I)
            for line in page.splitlines()
        )
    ]
    if not starts:
        return frozenset()
    start = starts[0]
    body_start: int | None = None
    for page_number in range(start + 1, len(pages) + 1):
        normalized = "\n".join(
            " ".join(line.split()) for line in pages[page_number - 1].splitlines()
        )
        if re.search(r"\bДата\s+введения\b", normalized, re.I):
            body_start = page_number
            break
        if re.search(r"(?m)^1[.)]?\s+Область\s+применения\b", normalized, re.I) and any(
            len(line) >= 120 and not _TOC_LINE.search(line) for line in normalized.splitlines()
        ):
            body_start = page_number
            break
    if body_start is None:
        return frozenset({start})
    return frozenset(range(start, body_start))


def _structural_match(line: str) -> tuple[str, str, str | None] | None:
    for pattern, kind in (
        (_APPENDIX_LINE, "appendix"),
        (_TABLE_LINE, "table"),
        (_NOTE_LINE, "note"),
    ):
        match = pattern.match(line)
        if match is not None:
            label = match.group("label")
            heading = line if kind in {"appendix", "table"} else None
            return label, kind, heading
    match = _STRUCTURAL_LINE.match(line)
    if match is None:
        return None
    label = match.group("label")
    if len(label.replace(".", "")) > 10 or int(label.split(".")[0]) > 99:
        return None
    depth = label.count(".") + 1
    kind = "section" if depth == 1 else "clause" if depth == 2 else "subclause"
    heading = line if depth <= 2 and len(match.group("text")) <= 180 else None
    return label, kind, heading


def _new_unit_builder(
    entry: QualificationCorpusEntry,
    path: str,
    parent: str | None,
    kind: str,
    heading: str | None,
    label: str | None,
    line: str,
    page_number: int,
) -> dict[str, Any]:
    del entry
    return {
        "path": path,
        "parent": parent,
        "kind": kind,
        "heading": heading,
        "label": label,
        "lines": [line],
        "line_pages": [page_number],
        "pages": {page_number},
    }


def _recurring_margin_lines(pages: tuple[str, ...]) -> frozenset[str]:
    occurrences: dict[str, set[int]] = defaultdict(set)
    for page_number, page in enumerate(pages, 1):
        lines = [" ".join(value.split()) for value in page.splitlines() if value.strip()]
        for line in (*lines[:2], *lines[-2:]):
            if line and not line.isdigit():
                occurrences[line].add(page_number)
    threshold = max(3, len(pages) // 10)
    return frozenset(line for line, page_set in occurrences.items() if len(page_set) >= threshold)


def build_representation(
    documents: tuple[QualificationDocument, ...],
    *,
    profile: str,
) -> RepresentationBuild:
    if profile == FIXED_PROFILE:
        chunks = _fixed_chunks(documents)
    elif profile in {STRUCTURE_PROFILE, CONTEXTUAL_PROFILE, HIERARCHICAL_PROFILE}:
        chunks = _structural_chunks(documents, contextual=profile != STRUCTURE_PROFILE)
    else:
        raise ValueError("ntd_chunk_profile_unknown")
    hierarchy = tuple(
        sorted(
            {
                (f"{unit.document_digest}:{unit.parent_path}", str(unit.unit_id))
                for document in documents
                for unit in document.units
                if unit.parent_path is not None
            }
        )
    )
    payload = {
        "profile": profile,
        "documents": [item.entry.digest for item in documents],
        "chunks": [str(item.chunk_id) for item in chunks],
        "hierarchy": hierarchy,
    }
    fingerprint = _digest(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode())
    return RepresentationBuild(profile, documents, chunks, hierarchy, fingerprint)


def run_lexical_benchmark(
    build: RepresentationBuild,
    cases: tuple[GoldQuery, ...],
    *,
    hierarchical: bool = False,
    limit: int = 10,
) -> tuple[QueryRun, ...]:
    """Run an explainable exact + morphological lexical qualification baseline."""

    document_by_digest = {item.entry.digest: item for item in build.documents}
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    for document in build.documents:
        for alias in designation_aliases(document.entry.designation):
            alias_candidates[normalize_designation(alias)].add(document.entry.digest)
        for number in re.findall(r"\d+(?:[.\-]\d+)+|\d{4,}", document.entry.designation):
            alias_candidates[normalize_designation(number)].add(document.entry.digest)
            alias_candidates[normalize_designation(number.split("-", maxsplit=1)[0])].add(
                document.entry.digest
            )
    aliases = {
        alias: next(iter(digests))
        for alias, digests in alias_candidates.items()
        if alias and len(digests) == 1
    }
    tokenized = {chunk.chunk_id: _tokens(chunk.retrieval_text) for chunk in build.chunks}
    frequencies: Counter[str] = Counter()
    for tokens in tokenized.values():
        frequencies.update(set(tokens))
    count = max(1, len(build.chunks))
    chunks_by_document: dict[str, list[QualificationChunk]] = defaultdict(list)
    for chunk in build.chunks:
        chunks_by_document[chunk.document_digest].append(chunk)
    runs: list[QueryRun] = []
    for case in cases:
        started = perf_counter()
        normalized_query = normalize_designation(case.query)
        resolved_digest = next(
            (
                digest
                for alias, digest in sorted(
                    aliases.items(), key=lambda item: len(item[0]), reverse=True
                )
                if alias and alias in normalized_query
            ),
            None,
        )
        resolved_designation = (
            document_by_digest[resolved_digest].entry.designation if resolved_digest else None
        )
        query_tokens = _tokens(case.query)
        allowed_documents: set[str] | None = None
        if resolved_digest is not None:
            allowed_documents = {resolved_digest}
        elif hierarchical:
            ranked_documents = sorted(
                (
                    (
                        _lexical_score(
                            query_tokens,
                            _tokens(
                                f"{document.entry.designation} {document.entry.title} "
                                + " ".join(unit.heading or "" for unit in document.units)
                            ),
                            frequencies,
                            count,
                        ),
                        document.entry.digest,
                    )
                    for document in build.documents
                ),
                reverse=True,
            )
            allowed_documents = {digest for score, digest in ranked_documents[:5] if score > 0}
        scored: list[tuple[float, QualificationChunk]] = []
        for chunk in build.chunks:
            if allowed_documents is not None and chunk.document_digest not in allowed_documents:
                continue
            score = _lexical_score(query_tokens, tokenized[chunk.chunk_id], frequencies, count)
            if resolved_digest == chunk.document_digest:
                score += 12.0
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].ordinal, str(item[1].chunk_id)))
        items = tuple(
            RetrievedItem(
                chunk.document_digest,
                chunk.pages[0] if chunk.pages else None,
                chunk.clause_labels[0] if chunk.clause_labels else None,
                score,
            )
            for score, chunk in _diverse_top(scored, limit=limit)
        )
        runs.append(
            QueryRun(
                case.case_id,
                items,
                (perf_counter() - started) * 1000,
                resolved_designation=resolved_designation,
            )
        )
    return tuple(runs)


def _fixed_chunks(documents: tuple[QualificationDocument, ...]) -> tuple[QualificationChunk, ...]:
    result: list[QualificationChunk] = []
    for document in documents:
        ordinal = 0
        for page_number, page_text in enumerate(document.page_text, 1):
            normalized = " ".join(page_text.split())
            for start in range(0, len(normalized), 1000):
                raw = normalized[start : start + 1200]
                if not raw.strip():
                    continue
                ordinal += 1
                chunk_id = deterministic_uuid(
                    f"{FIXED_PROFILE}:{document.entry.digest}:{page_number}:{start}:{_digest(raw.encode())}"
                )
                result.append(
                    QualificationChunk(
                        chunk_id,
                        FIXED_PROFILE,
                        document.entry.digest,
                        ordinal,
                        f"page:{page_number}/offset:{start}",
                        None,
                        (),
                        (page_number,),
                        raw,
                        "",
                        raw,
                    )
                )
    return tuple(result)


def _structural_chunks(
    documents: tuple[QualificationDocument, ...],
    *,
    contextual: bool,
) -> tuple[QualificationChunk, ...]:
    result: list[QualificationChunk] = []
    profile = CONTEXTUAL_PROFILE if contextual else STRUCTURE_PROFILE
    for document in documents:
        headings = {
            unit.structural_path: unit.heading
            for unit in document.units
            if unit.heading is not None
        }
        chunk_ordinal = 0
        for unit in document.units:
            parent_heading = headings.get(unit.parent_path or "", "") or ""
            for part_number, (raw_text, part_pages) in enumerate(_unit_parts(unit), 1):
                chunk_ordinal += 1
                path = (
                    unit.structural_path
                    if part_number == 1
                    else f"{unit.structural_path}@continuation:{part_number}"
                )
                context = ""
                if contextual:
                    context = "\n".join(
                        value
                        for value in (
                            f"Документ: {document.entry.designation}",
                            f"Название: {document.entry.title}",
                            f"Раздел: {unit.heading or unit.structural_path}",
                            f"Родительский раздел: {parent_heading}" if parent_heading else "",
                            f"Область: {_scope_context(document.entry)}",
                            f"Регулируемая работа: {_work_context(document.entry)}",
                            (
                                f"Страницы: {min(part_pages)}-{max(part_pages)}"
                                if part_pages
                                else ""
                            ),
                        )
                        if value
                    )
                retrieval = f"{context}\n{raw_text}" if context else raw_text
                chunk_id = deterministic_uuid(
                    f"{profile}:{unit.unit_id}:{part_number}:{_digest(retrieval.encode())}"
                )
                result.append(
                    QualificationChunk(
                        chunk_id,
                        profile,
                        document.entry.digest,
                        chunk_ordinal,
                        path,
                        unit.parent_path,
                        (unit.clause_label,) if unit.clause_label else (),
                        part_pages,
                        raw_text,
                        context,
                        retrieval,
                    )
                )
    return tuple(result)


def _unit_parts(
    unit: QualificationUnit,
    *,
    max_characters: int = 1800,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    lines = unit.raw_text.splitlines()
    if len(lines) != len(unit.line_pages):
        raise ValueError("ntd_qualification_unit_line_page_mismatch")
    result: list[tuple[str, tuple[int, ...]]] = []
    current_lines: list[str] = []
    current_pages: list[int] = []
    current_size = 0
    for line, page_number in zip(lines, unit.line_pages, strict=True):
        if current_lines and current_size + len(line) + 1 > max_characters:
            result.append(("\n".join(current_lines), tuple(dict.fromkeys(current_pages))))
            current_lines = []
            current_pages = []
            current_size = 0
        if len(line) <= max_characters:
            current_lines.append(line)
            current_pages.append(page_number)
            current_size += len(line) + 1
            continue
        for start in range(0, len(line), max_characters):
            if current_lines:
                result.append(("\n".join(current_lines), tuple(dict.fromkeys(current_pages))))
                current_lines = []
                current_pages = []
                current_size = 0
            result.append((line[start : start + max_characters], (page_number,)))
    if current_lines:
        result.append(("\n".join(current_lines), tuple(dict.fromkeys(current_pages))))
    return tuple(result)


def _scope_context(entry: QualificationCorpusEntry) -> str:
    values = {
        "СП 70.13330.2012": "возведение несущих и ограждающих конструкций",
        "СП 543.1325800.2024": "строительный контроль",
        "СП 45.13330.2017": "земляные сооружения, основания и фундаменты",
        "СП 392.1325800.2018": "исполнительная документация магистральных трубопроводов",
        "СП 48.13330.2019": "организация строительства",
        "ГОСТ 10180-2012": "испытание прочности бетона по контрольным образцам",
        "ГОСТ 18105-2018": "контроль и оценка прочности бетона",
        "ГОСТ Р 51872-2024": "геодезическая исполнительная документация",
        "И 1.13-07": "приемо-сдаточная документация электромонтажных работ",
        "ГЭСН 81-02-06-2022": "сметные нормы на монолитные бетонные конструкции",
    }
    return values.get(entry.designation, f"{entry.title}; область применения требует уточнения")


def _work_context(entry: QualificationCorpusEntry) -> str:
    values = {
        "СП 70.13330.2012": (
            "бетонные, железобетонные, стальные, каменные и ограждающие конструкции"
        ),
        "СП 543.1325800.2024": "контроль строительно-монтажных работ",
        "СП 45.13330.2017": "разработка грунта и устройство оснований",
        "СП 392.1325800.2018": "строительство трубопроводов",
        "СП 48.13330.2019": "организация строительного производства",
        "ГОСТ 10180-2012": "изготовление и испытание образцов бетона",
        "ГОСТ 18105-2018": "оценка прочности бетона",
        "ГОСТ Р 51872-2024": "исполнительные геодезические работы",
        "И 1.13-07": "электромонтажные работы",
        "ГЭСН 81-02-06-2022": "монолитные бетонные и железобетонные конструкции",
    }
    return values.get(
        entry.designation,
        f"работы и конструкции, регулируемые документом {entry.designation}",
    )


def _tokens(text: str) -> Counter[str]:
    values: list[str] = []
    for raw in _TOKEN.findall(text.casefold().replace("ё", "е")):
        values.append(raw)
        if raw.isalpha() and len(raw) > 4:
            stem = raw
            for suffix in _RUSSIAN_SUFFIXES:
                if stem.endswith(suffix) and len(stem) - len(suffix) >= 4:
                    stem = stem[: -len(suffix)]
                    break
            values.append(stem)
    return Counter(values)


def _lexical_score(
    query: Counter[str],
    document: Counter[str],
    frequencies: Counter[str],
    corpus_size: int,
) -> float:
    score = 0.0
    length = max(1, sum(document.values()))
    for token, query_count in query.items():
        term_frequency = document.get(token, 0)
        if not term_frequency:
            continue
        inverse = math.log(1 + corpus_size / (1 + frequencies[token]))
        score += query_count * inverse * (term_frequency / (term_frequency + 0.8 + length / 1200))
    return score


def _diverse_top(
    values: list[tuple[float, QualificationChunk]],
    *,
    limit: int,
) -> tuple[tuple[float, QualificationChunk], ...]:
    result: list[tuple[float, QualificationChunk]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        key = (item[1].document_digest, item[1].structural_path)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) == limit:
            break
    return tuple(result)


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
