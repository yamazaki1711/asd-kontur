"""Build permanent NTD text/chunk/vector memory from an audited byte denominator.

The builder is intentionally source-first and idempotent.  Search text from a
legacy/reference artifact remains reference material; this module never
publishes a provision or activates a normative rule.
"""

# ruff: noqa: E501, RUF001 -- exact Russian designations and SQL stay readable.

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import sqlalchemy as sa
from PIL import Image, ImageStat
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.models import PageHealthKind
from asd_kontur.document_understanding.native import (
    NativeExtractionFailure,
    analyze_page_health,
    inspect_pdf_path,
)
from asd_kontur.domain import deterministic_uuid
from asd_kontur.knowledge.object_store import LocalFilesystemObjectStore
from asd_kontur.knowledge.source_ledger import (
    PERMANENT_PLATFORM_CORE,
    PlatformSourceAdmission,
    PlatformSourceLedger,
)
from asd_kontur.ntd.file_processing import render_normative_pdf_page
from asd_kontur.ntd.graph_projection import rebuild_ntd_typed_graph
from asd_kontur.ntd.search_corpus import normalize_designation
from asd_kontur.ntd.structural_projection import (
    rebuild_ntd_qualified_contextual_projection,
    rebuild_ntd_structural_units,
)

NTD_CANONICAL_MEMORY_PROFILE = "ntd-canonical-memory@1.0.0"
NTD_PAGE_EXTRACTION_PROFILE = "ntd-page-native-ocr@1.0.0"
NTD_CHUNKING_PROFILE = "ntd-structural-chunks@1.0.0"
NTD_AUDIT_DIGEST = "sha256:6a0e38c9d4b69ad07b5b407e3bb4911f599041873dab133f2d1bce925cd8c09a"
NTD_DENOMINATOR = 118
GESN_DEFERRED_REFERENCE_COUNT = 12

_TRUSTED_QUALIFICATION_METADATA: dict[str, tuple[str, str]] = {
    "sha256:47ed8e3302560ab2e85cc1fb07e8dbfa73ac4e7197e7e2c2d6877309fb4233a5": (
        "СП 70.13330.2012",
        "Несущие и ограждающие конструкции",
    ),
    "sha256:1143c97a803c597556fd02f1924496b342d4c3d1b77aaa24a65fe4936767c267": (
        "СП 543.1325800.2024",
        "Строительный контроль при строительстве, реконструкции, капитальном ремонте объектов капитального строительства",
    ),
    "sha256:2d1803ad939d4168993fe3e147fea9fe9c9227dac21c7034dfb1bf75409768a0": (
        "СП 45.13330.2017",
        "Земляные сооружения, основания и фундаменты",
    ),
    "sha256:18808b6b4f8f4c5c53c76fcc8f105e23bdf1b89f83773faef555b1995db29a6e": (
        "СП 392.1325800.2018",
        "Трубопроводы магистральные и промысловые для нефти и газа. Исполнительная документация при строительстве",
    ),
    "sha256:0cbfe59b5395ac0ed3f90d60e459cb2478cc12e08c0ece5677cbca4d66f1d4ac": (
        "СП 48.13330.2019",
        "Организация строительства",
    ),
    "sha256:265c997e90f859dd3f031bcce3f1e5b17d0049bb3c5d2c524f7540ef09589a45": (
        "ГОСТ 10180-2012",
        "Бетоны. Методы определения прочности по контрольным образцам",
    ),
    "sha256:64bd1509394dc752dc7f98818423a5201294163b8cb76b66da7e0eb62065e25f": (
        "ГОСТ 18105-2018",
        "Бетоны. Правила контроля и оценки прочности",
    ),
    "sha256:639b851f7ecdbe3fe568e0435b5892a8e138e1ddbb53acca35cd71b61957e8bd": (
        "ГОСТ Р 51872-2024",
        "Документация исполнительная геодезическая. Правила выполнения",
    ),
    "sha256:400115a99fa3ec311395162f9bc5a7839062aad544ac1da484f0432a76057d16": (
        "И 1.13-07",
        "Инструкция по оформлению приемо-сдаточной документации по электромонтажным работам",
    ),
}


class EmbeddingPort(Protocol):
    profile_key: str
    profile_version: str
    model_id: str
    model_revision: str
    model_digest: str
    dimension: int
    normalization: str
    input_construction: str
    qualification_receipt: dict[str, Any]

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class NtdMemoryBuildResult:
    denominator_ntd: int
    deferred_estimate_references: int
    admitted_objects: int
    blocked_objects: int
    terminal_documents: int
    pages: int
    pages_terminal: int
    pages_extracted: int
    pages_blocked: int
    chunks: int
    embeddings: int
    chunks_without_embeddings: int
    orphan_embeddings: int
    searchable_documents: int
    build_fingerprint: str
    terminal_outcome: str


@dataclass(frozen=True, slots=True)
class _CorpusInput:
    artifact_digest: str
    size_bytes: int
    media_type: str
    authority_class: str
    logical_document_key: str
    designation: str
    title: str
    printed_edition: str | None
    source_path: Path | None
    original_paths: tuple[str, ...]
    recovered_paths: tuple[str, ...]
    source_artifact_id: UUID | None
    source_version_id: UUID | None
    normative_document_id: UUID | None
    normative_edition_id: UUID | None
    normative_artifact_id: UUID | None
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Page:
    page_number: int
    kind: str
    width_points: str
    height_points: str
    rotation_degrees: int
    render_digest: str | None
    raw_text: str
    normalized_text: str
    extraction_method: str
    model_profile: str | None
    request_digest: str | None
    response_digest: str | None
    terminal_outcome: str
    blocker_code: str | None
    critical_token_status: str
    structural_path: str


@dataclass(frozen=True, slots=True)
class _Chunk:
    ordinal: int
    page_start: int
    page_end: int
    structural_path: str
    locator_ids: tuple[UUID, ...]
    raw_text: str
    normalized_text: str
    parent_chunk_id: UUID | None
    continuation_of_chunk_id: UUID | None


class HttpEmbeddingClient:
    """Pinned client for the separately supervised local embedding worker."""

    def __init__(
        self,
        *,
        endpoint: str,
        profile: dict[str, Any],
        timeout_seconds: float = 120.0,
    ) -> None:
        if not endpoint.startswith("http://127.0.0.1:"):
            raise ValueError("embedding_endpoint_must_be_local")
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout_seconds
        self.profile_key = str(profile["profile_key"])
        self.profile_version = str(profile["profile_version"])
        self.model_id = str(profile["model_id"])
        self.model_revision = str(profile["model_revision"])
        self.model_digest = str(profile["model_digest"])
        self.dimension = int(profile["dimension"])
        self.normalization = str(profile["normalization"])
        self.input_construction = str(profile["input_construction"])
        self.qualification_receipt = dict(profile["qualification_receipt"])

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        import urllib.request

        payload = json.dumps(
            {"profile": self.profile_key, "texts": list(texts)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        request = urllib.request.Request(
            f"{self._endpoint}/v1/embeddings",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=self._timeout) as response:
            value = json.loads(response.read())
        if value.get("profile_key") != self.profile_key or value.get("dimension") != self.dimension:
            raise ValueError("embedding_profile_response_mismatch")
        vectors = value.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("embedding_response_cardinality_mismatch")
        result = [[float(item) for item in vector] for vector in vectors]
        if any(len(vector) != self.dimension for vector in result):
            raise ValueError("embedding_response_dimension_mismatch")
        return result


def build_canonical_ntd_memory(
    engine: Engine,
    *,
    audit_json: Path,
    object_store_root: Path,
    actor_identity_id: str,
    embedding: EmbeddingPort,
    retrieval_qualification_receipt: Path,
    ocr_executable: Path | None = None,
    canary_designation: str | None = None,
    embedding_batch_size: int = 32,
) -> NtdMemoryBuildResult:
    """Run an idempotent build over the accepted immutable audit denominator."""

    _validate_inputs(audit_json, object_store_root, embedding, embedding_batch_size)
    retrieval_qualification = _validate_retrieval_qualification(
        retrieval_qualification_receipt, embedding
    )
    inputs = load_audited_corpus(audit_json)
    if canary_designation is not None:
        normalized = normalize_designation(canary_designation)
        inputs = tuple(
            item
            for item in inputs
            if normalize_designation(item.designation).startswith(normalized)
        )
        if len(inputs) != 1:
            raise ValueError("ntd_canary_designation_not_unique")
    ledger = PlatformSourceLedger(engine, LocalFilesystemObjectStore(object_store_root))
    chunk_profile_id = _register_chunk_profile(engine, retrieval_qualification)
    profile_id = _register_embedding_profile(engine, embedding)
    for item in inputs:
        _build_one(
            engine,
            ledger,
            item,
            actor_identity_id=actor_identity_id,
            ocr_executable=ocr_executable,
            chunk_profile_id=chunk_profile_id,
        )
    rebuild_ntd_structural_units(engine)
    rebuild_ntd_typed_graph(engine)
    rebuild_ntd_qualified_contextual_projection(engine, retrieval_qualification)
    _embed_pending(engine, embedding, profile_id, batch_size=embedding_batch_size)
    result = _reconcile(engine, profile_id, canary=canary_designation is not None)
    return result


def load_audited_corpus(audit_json: Path) -> tuple[_CorpusInput, ...]:
    if not audit_json.is_absolute() or not audit_json.is_file() or audit_json.is_symlink():
        raise ValueError("ntd_audit_path_invalid")
    if _file_digest(audit_json) != NTD_AUDIT_DIGEST:
        raise ValueError("ntd_audit_digest_mismatch")
    audit = json.loads(audit_json.read_bytes())
    if (
        audit.get("semantic_fingerprint")
        != "sha256:a8c56c87401e8c7cf45c5e8415b201a30824bd0f33ea4f67cc50f31f3a20a1ac"
    ):
        raise ValueError("ntd_audit_semantic_fingerprint_mismatch")
    selected: dict[str, dict[str, Any]] = {}
    priority = {
        "official": 4,
        "official + legacy representation": 4,
        "legacy/reference": 2,
        "GESN": 1,
    }
    for row in audit["artifacts"]:
        classification = str(row.get("classification"))
        digest = row.get("sha256")
        if classification not in priority or not digest:
            continue
        previous = selected.get(str(digest))
        if previous is None or priority[classification] > priority[str(previous["classification"])]:
            selected[str(digest)] = row
    return _validated_processing_inputs(tuple(row for _, row in sorted(selected.items())))


def _validated_processing_inputs(
    rows: Sequence[dict[str, Any]],
) -> tuple[_CorpusInput, ...]:
    """Validate the accepted audit denominator and exclude deferred GESN bytes."""

    values = tuple(_audit_input(row) for row in rows)
    ntd = sum(item.authority_class != "gesn_candidate" for item in values)
    gesn = sum(item.authority_class == "gesn_candidate" for item in values)
    if ntd != NTD_DENOMINATOR or gesn != GESN_DEFERRED_REFERENCE_COUNT:
        raise ValueError(f"ntd_audit_denominator_mismatch:{ntd}:{gesn}")
    return tuple(item for item in values if item.authority_class != "gesn_candidate")


def _audit_input(row: dict[str, Any]) -> _CorpusInput:
    classification = str(row["classification"])
    if classification == "GESN":
        authority = "gesn_candidate"
    elif classification == "official + legacy representation":
        authority = "official_binding_recovered"
    elif classification == "official":
        authority = "official"
    else:
        authority = "legacy_reference"
    source_paths = tuple(filter(None, [str(row.get("source_path") or "")]))
    object_path_value = str(row.get("object_plane_path") or "")
    source_path = Path(object_path_value) if object_path_value else None
    if source_path is None or not source_path.is_file():
        source_path = next((Path(value) for value in source_paths if Path(value).is_file()), None)
    artifact_digest = str(row["sha256"])
    trusted_metadata = _TRUSTED_QUALIFICATION_METADATA.get(artifact_digest)
    designation = (
        trusted_metadata[0]
        if trusted_metadata is not None
        else str(row.get("designation") or row.get("title") or artifact_digest)
    )
    title = (
        trusted_metadata[1]
        if trusted_metadata is not None
        else str(row.get("title") or designation)
    )
    logical = str(row.get("logical_document_identity") or normalize_designation(designation))
    return _CorpusInput(
        artifact_digest,
        int(row.get("size_bytes") or 0),
        str(row.get("mime") or "application/octet-stream"),
        authority,
        logical,
        designation,
        title,
        str(row.get("edition")) if row.get("edition") else None,
        source_path,
        source_paths,
        tuple(filter(None, [object_path_value])),
        _uuid_or_none(row.get("source_artifact_id")),
        _uuid_or_none(row.get("source_version_id")),
        _uuid_or_none(row.get("normative_document_id")),
        _uuid_or_none(row.get("normative_edition_id")),
        _uuid_or_none(row.get("normative_artifact_id")),
        {
            "audit_ordinal": row.get("ordinal"),
            "classification": classification,
            "source_provenance": row.get("source_provenance"),
            "audit_terminal_status": row.get("terminal_processing_status"),
        },
    )


def _resolve_local_audit_references(
    engine: Engine,
    source_artifact_id: UUID | None,
    source_version_id: UUID | None,
    normative_document_id: UUID | None,
    normative_edition_id: UUID | None,
    normative_artifact_id: UUID | None,
) -> tuple[UUID | None, UUID | None, UUID | None, UUID | None, UUID | None]:
    values = (
        source_artifact_id,
        source_version_id,
        normative_document_id,
        normative_edition_id,
        normative_artifact_id,
    )
    statements = (
        "SELECT EXISTS(SELECT 1 FROM platform.source_artifacts WHERE source_artifact_id=:id)",
        "SELECT EXISTS(SELECT 1 FROM platform.source_versions WHERE source_version_id=:id)",
        "SELECT EXISTS(SELECT 1 FROM platform.normative_documents WHERE normative_document_id=:id)",
        "SELECT EXISTS(SELECT 1 FROM platform.normative_editions WHERE normative_edition_id=:id)",
        "SELECT EXISTS(SELECT 1 FROM platform.normative_artifacts WHERE normative_artifact_id=:id)",
    )
    with engine.connect() as connection:
        resolved = tuple(
            value
            if value is not None and bool(connection.scalar(sa.text(statement), {"id": value}))
            else None
            for value, statement in zip(values, statements, strict=True)
        )
    return (
        resolved[0] if resolved[1] is not None else None,
        resolved[1],
        resolved[2],
        resolved[3],
        resolved[4],
    )


def _build_one(
    engine: Engine,
    ledger: PlatformSourceLedger,
    item: _CorpusInput,
    *,
    actor_identity_id: str,
    ocr_executable: Path | None,
    chunk_profile_id: UUID,
) -> None:
    corpus_id = deterministic_uuid(f"ntd-corpus-object:{item.artifact_digest}")
    with engine.connect() as connection:
        existing = connection.execute(
            sa.text(
                "SELECT terminal_outcome FROM platform.ntd_corpus_objects WHERE corpus_object_id=:id"
            ),
            {"id": corpus_id},
        ).scalar_one_or_none()
    if existing == "admitted":
        _extract_and_chunk_if_needed(
            engine, corpus_id, item.source_path, ocr_executable, chunk_profile_id
        )
        return
    source_artifact_id = item.source_artifact_id
    source_version_id = item.source_version_id
    (
        source_artifact_id,
        source_version_id,
        normative_document_id,
        normative_edition_id,
        normative_artifact_id,
    ) = _resolve_local_audit_references(
        engine,
        source_artifact_id,
        source_version_id,
        item.normative_document_id,
        item.normative_edition_id,
        item.normative_artifact_id,
    )
    path = item.source_path
    bytes_ok = path is not None and path.is_file() and not path.is_symlink()
    if (
        path is not None
        and bytes_ok
        and (path.stat().st_size != item.size_bytes or _file_digest(path) != item.artifact_digest)
    ):
        bytes_ok = False
        terminal = "blocked_digest_mismatch"
        bytes_status = "digest_mismatch"
        blocker = "NTD_CORPUS_DIGEST_MISMATCH"
    elif not bytes_ok:
        terminal = "blocked_bytes_unavailable"
        bytes_status = "not_locally_available"
        blocker = "NTD_CORPUS_BYTES_NOT_LOCALLY_AVAILABLE"
    elif item.media_type != "application/pdf":
        terminal = "blocked_unsupported_format"
        bytes_status = "unsupported"
        blocker = "NTD_CORPUS_FORMAT_NOT_SUPPORTED"
    else:
        terminal = "admitted"
        bytes_status = "present_verified"
        blocker = None
        if source_version_id is None:
            assert path is not None
            admission = ledger.admit_file(
                PlatformSourceAdmission(
                    source_family_key=None,
                    stable_designation=f"ntd-corpus:{normalize_designation(item.designation)}:{item.artifact_digest[-12:]}",
                    title=item.title,
                    issuer="recovered-corpus",
                    jurisdiction="RU",
                    external_version_label=item.printed_edition or item.artifact_digest[7:19],
                    source_kind="normative_document"
                    if item.authority_class != "gesn_candidate"
                    else "official_reference",
                    locator=str(path),
                    acquisition_method="audited_existing_bytes_v1",
                    semantic_metadata=json.dumps(
                        item.provenance, ensure_ascii=False, sort_keys=True
                    ),
                    media_type=item.media_type,
                    classification=item.authority_class,
                    retention_class=PERMANENT_PLATFORM_CORE,
                    actor_identity_id=actor_identity_id,
                    correlation_id=deterministic_uuid(
                        f"ntd-corpus-admission:{item.artifact_digest}"
                    ),
                ),
                path,
            )
            source_artifact_id = admission.source_artifact_id
            source_version_id = admission.source_version_id
    payload = {
        "profile": NTD_CANONICAL_MEMORY_PROFILE,
        "digest": item.artifact_digest,
        "authority": item.authority_class,
        "logical": item.logical_document_key,
        "designation": item.designation,
        "source_version": str(source_version_id) if source_version_id else None,
        "terminal": terminal,
    }
    fingerprint = semantic_digest(payload)
    aliases = _designation_aliases(item.designation)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_corpus_objects(corpus_object_id,artifact_digest,size_bytes,media_type,authority_class,"
                "logical_document_key,stable_designation,alternative_designations,title,printed_edition,source_artifact_id,"
                "source_version_id,normative_document_id,normative_edition_id,normative_artifact_id,original_paths,recovered_paths,"
                "provenance,bytes_status,edition_currency_status,terminal_outcome,blocker_code,corpus_profile_version,corpus_fingerprint) "
                "VALUES (:id,:digest,:size,:mime,:authority,:logical,:designation,:aliases,:title,:edition,:source_artifact,"
                ":source_version,:document,:normative_edition,:normative_artifact,CAST(:original AS jsonb),CAST(:recovered AS jsonb),"
                "CAST(:provenance AS jsonb),:bytes,'not_checked',:terminal,:blocker,:profile,:fingerprint) "
                "ON CONFLICT (artifact_digest) DO NOTHING"
            ),
            {
                "id": corpus_id,
                "digest": item.artifact_digest,
                "size": item.size_bytes,
                "mime": item.media_type,
                "authority": item.authority_class,
                "logical": item.logical_document_key,
                "designation": item.designation,
                "aliases": aliases,
                "title": item.title,
                "edition": item.printed_edition,
                "source_artifact": source_artifact_id,
                "source_version": source_version_id,
                "document": normative_document_id,
                "normative_edition": normative_edition_id,
                "normative_artifact": normative_artifact_id,
                "original": json.dumps(item.original_paths, ensure_ascii=False),
                "recovered": json.dumps(item.recovered_paths, ensure_ascii=False),
                "provenance": json.dumps(item.provenance, ensure_ascii=False),
                "bytes": bytes_status,
                "terminal": terminal,
                "blocker": blocker,
                "profile": NTD_CANONICAL_MEMORY_PROFILE,
                "fingerprint": fingerprint,
            },
        )
    if terminal == "admitted":
        assert source_version_id is not None
        _extract_and_chunk_if_needed(engine, corpus_id, path, ocr_executable, chunk_profile_id)


def _extract_and_chunk_if_needed(
    engine: Engine,
    corpus_id: UUID,
    path: Path | None,
    ocr_executable: Path | None,
    chunk_profile_id: UUID,
) -> None:
    with engine.connect() as connection:
        existing = int(
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM platform.ntd_corpus_pages WHERE corpus_object_id=:id"
                ),
                {"id": corpus_id},
            ).scalar_one()
        )
        source = (
            connection.execute(
                sa.text(
                    "SELECT source_version_id,normative_document_id,normative_edition_id,authority_class,"
                    "stable_designation,title FROM platform.ntd_corpus_objects WHERE corpus_object_id=:id"
                ),
                {"id": corpus_id},
            )
            .mappings()
            .one()
        )
    if existing:
        return
    if path is None or not path.is_file():
        return
    source_version_id = UUID(str(source["source_version_id"]))
    try:
        native = inspect_pdf_path(
            path=path,
            document_id=corpus_id,
            document_version=1,
            source_version_id=source_version_id,
        )
    except NativeExtractionFailure as error:
        _record_failed_document_page(engine, corpus_id, source_version_id, error.code)
        return
    poppler_pages = _extract_poppler_layout_pages(path, len(native.pages))
    pages: list[_Page] = []
    for page in native.pages:
        if poppler_pages is not None:
            raw = poppler_pages[page.page_number - 1]
            method = "poppler-layout@1.0.0"
        else:
            raw = "\n".join(
                element.raw_text.strip()
                for element in sorted(page.elements, key=lambda value: value.reading_order)
                if element.raw_text.strip()
            )
            method = "pypdf-layout@6.x"
        normalized = _normalize_text(raw)
        model_profile = None
        request_digest = None
        response_digest = None
        terminal = "native_complete" if raw else "blank_verified"
        blocker = None
        if page.health.primary_kind is PageHealthKind.DAMAGED_ENCODING or (
            not raw and page.health.primary_kind is not PageHealthKind.BLANK
        ):
            if ocr_executable is None:
                terminal = "blocked_extraction"
                blocker = "NTD_OCR_PROFILE_NOT_CONFIGURED"
            else:
                raw, request_digest, response_digest, deterministic_blank = _ocr_page(
                    path, page.page_number, page.rotation_degrees, ocr_executable
                )
                normalized = _normalize_text(raw)
                method = "apple-vision-accurate@1.0.0"
                model_profile = "apple-vision-accurate"
                if raw:
                    ocr_health = analyze_page_health(
                        document_id=corpus_id,
                        document_version=1,
                        page_number=page.page_number,
                        text=raw,
                        image_count=0,
                        width_points=page.width_points,
                        height_points=page.height_points,
                        rotation_degrees=page.rotation_degrees,
                    )
                    if ocr_health.primary_kind is PageHealthKind.DAMAGED_ENCODING:
                        terminal = "blocked_extraction"
                        blocker = "NTD_OCR_OUTPUT_UNREADABLE"
                    else:
                        terminal = "ocr_complete"
                        blocker = None
                elif deterministic_blank:
                    terminal = "blank_verified"
                    blocker = None
                else:
                    terminal = "blocked_extraction"
                    blocker = "NTD_OCR_EMPTY_RESULT"
        render_digest = None
        try:
            render_digest = render_normative_pdf_page(
                path,
                page_index=page.page_number,
                source_rotation_degrees=page.rotation_degrees,
            ).render_digest
        except ValueError:
            if terminal not in {"blank_verified", "blocked_extraction"}:
                terminal = "blocked_extraction"
                blocker = "NTD_PAGE_RENDER_FAILED"
        pages.append(
            _Page(
                page.page_number,
                _page_kind(page.health.primary_kind),
                str(page.width_points),
                str(page.height_points),
                page.rotation_degrees,
                render_digest,
                raw,
                normalized,
                method,
                model_profile,
                request_digest,
                response_digest,
                terminal,
                blocker,
                "requires_review"
                if page.health.primary_kind is PageHealthKind.DAMAGED_ENCODING
                else "not_applicable",
                _page_structural_path(page.elements),
            )
        )
    locator_ids = _persist_pages(engine, corpus_id, source_version_id, pages)
    chunks = _chunk_pages(corpus_id, pages, locator_ids)
    chunk_ids = _persist_chunks(
        engine,
        corpus_id,
        source_version_id,
        source["normative_document_id"],
        source["normative_edition_id"],
        str(source["authority_class"]),
        chunks,
    )
    if len(chunk_ids) != len(chunks):
        raise ValueError("ntd_chunk_identity_cardinality_mismatch")
    del chunk_profile_id


def _record_failed_document_page(
    engine: Engine, corpus_id: UUID, source_version_id: UUID, blocker: str
) -> None:
    locator_id = _ensure_page_locator(engine, source_version_id, 1, _digest(b""))
    fingerprint = semantic_digest({"corpus": str(corpus_id), "page": 1, "blocker": blocker})
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_corpus_pages(corpus_page_id,version,corpus_object_id,source_version_id,page_number,page_kind,"
                "width_points,height_points,rotation_degrees,raw_transcription,normalized_text,raw_text_digest,normalized_text_digest,"
                "source_locator_id,extraction_method,extraction_profile_version,critical_token_status,terminal_outcome,blocker_code,page_fingerprint) "
                "VALUES (:id,1,:corpus,:source,1,'unsupported_corrupt',1,1,0,'','',:digest,:digest,:locator,'pypdf-layout@6.x',"
                ":profile,'requires_review','blocked_corrupt',:blocker,:fingerprint)"
            ),
            {
                "id": deterministic_uuid(f"ntd-page:{corpus_id}:1"),
                "corpus": corpus_id,
                "source": source_version_id,
                "digest": _digest(b""),
                "locator": locator_id,
                "profile": NTD_PAGE_EXTRACTION_PROFILE,
                "blocker": blocker,
                "fingerprint": fingerprint,
            },
        )


def _persist_pages(
    engine: Engine, corpus_id: UUID, source_version_id: UUID, pages: Sequence[_Page]
) -> dict[int, UUID]:
    locators: dict[int, UUID] = {}
    for page in pages:
        raw_digest = _digest(page.raw_text.encode())
        normalized_digest = _digest(page.normalized_text.encode())
        locator = _ensure_page_locator(engine, source_version_id, page.page_number, raw_digest)
        locators[page.page_number] = locator
        fingerprint = semantic_digest(
            {
                "profile": NTD_PAGE_EXTRACTION_PROFILE,
                "corpus": str(corpus_id),
                "page": page.page_number,
                "raw": raw_digest,
                "render": page.render_digest,
                "terminal": page.terminal_outcome,
            }
        )
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_corpus_pages(corpus_page_id,version,corpus_object_id,source_version_id,page_number,page_kind,"
                    "width_points,height_points,rotation_degrees,render_digest,raw_transcription,normalized_text,raw_text_digest,"
                    "normalized_text_digest,source_locator_id,extraction_method,extraction_profile_version,model_profile,request_digest,"
                    "response_digest,critical_token_status,terminal_outcome,blocker_code,page_fingerprint) VALUES ("
                    ":id,1,:corpus,:source,:page,:kind,:width,:height,:rotation,:render,:raw,:normalized,:raw_digest,:normalized_digest,"
                    ":locator,:method,:profile,:model,:request,:response,:critical,:terminal,:blocker,:fingerprint) "
                    "ON CONFLICT (page_fingerprint) DO NOTHING"
                ),
                {
                    "id": deterministic_uuid(f"ntd-page:{corpus_id}:{page.page_number}"),
                    "corpus": corpus_id,
                    "source": source_version_id,
                    "page": page.page_number,
                    "kind": page.kind,
                    "width": page.width_points,
                    "height": page.height_points,
                    "rotation": page.rotation_degrees,
                    "render": page.render_digest,
                    "raw": page.raw_text,
                    "normalized": page.normalized_text,
                    "raw_digest": raw_digest,
                    "normalized_digest": normalized_digest,
                    "locator": locator,
                    "method": page.extraction_method,
                    "profile": NTD_PAGE_EXTRACTION_PROFILE,
                    "model": page.model_profile,
                    "request": page.request_digest,
                    "response": page.response_digest,
                    "critical": page.critical_token_status,
                    "terminal": page.terminal_outcome,
                    "blocker": page.blocker_code,
                    "fingerprint": fingerprint,
                },
            )
    return locators


def _chunk_pages(
    corpus_id: UUID, pages: Sequence[_Page], locator_ids: dict[int, UUID]
) -> tuple[_Chunk, ...]:
    chunks: list[_Chunk] = []
    current_text: list[str] = []
    current_pages: list[int] = []
    current_path = "document"
    target = 1800
    hard_max = 2600

    def flush() -> None:
        nonlocal current_text, current_pages, current_path
        raw = "\n".join(current_text).strip()
        if not raw:
            current_text = []
            current_pages = []
            return
        ordinal = len(chunks) + 1
        continuation = chunks[-1] if chunks and chunks[-1].structural_path == current_path else None
        chunks.append(
            _Chunk(
                ordinal,
                min(current_pages),
                max(current_pages),
                current_path,
                tuple(locator_ids[p] for p in sorted(set(current_pages))),
                raw,
                _normalize_text(raw),
                None,
                deterministic_uuid(f"ntd-chunk-continuation:{corpus_id}:{continuation.ordinal}")
                if continuation
                else None,
            )
        )
        current_text = []
        current_pages = []

    for page in pages:
        if not page.raw_text.strip() or page.terminal_outcome.startswith("blocked"):
            flush()
            continue
        paragraphs = [
            value.strip() for value in re.split(r"\n{2,}|(?<=\.)\n", page.raw_text) if value.strip()
        ]
        if not paragraphs:
            paragraphs = [page.raw_text.strip()]
        for paragraph in paragraphs:
            heading = _heading(paragraph)
            if heading and current_text:
                flush()
            if heading:
                current_path = heading
            projected = sum(len(value) for value in current_text) + len(paragraph)
            if current_text and projected > hard_max:
                flush()
            current_text.append(paragraph)
            current_pages.append(page.page_number)
            if sum(len(value) for value in current_text) >= target and not heading:
                flush()
        if page.kind == "table_heavy":
            flush()
    flush()
    return tuple(chunks)


def _persist_chunks(
    engine: Engine,
    corpus_id: UUID,
    source_version_id: UUID,
    normative_document_id: Any,
    normative_edition_id: Any,
    authority_class: str,
    chunks: Sequence[_Chunk],
) -> dict[int, UUID]:
    chunk_ids = {
        chunk.ordinal: deterministic_uuid(
            f"ntd-chunk:{source_version_id}:{chunk.ordinal}:{_digest(chunk.normalized_text.encode())}:{NTD_CHUNKING_PROFILE}"
        )
        for chunk in chunks
    }
    previous_by_path: dict[str, UUID] = {}
    with engine.begin() as connection:
        for chunk in chunks:
            raw_digest = _digest(chunk.raw_text.encode())
            normalized_digest = _digest(chunk.normalized_text.encode())
            chunk_id = chunk_ids[chunk.ordinal]
            continuation_id = previous_by_path.get(chunk.structural_path)
            fingerprint = semantic_digest(
                {
                    "chunk_id": str(chunk_id),
                    "source": str(source_version_id),
                    "pages": [chunk.page_start, chunk.page_end],
                    "path": chunk.structural_path,
                    "raw": raw_digest,
                    "normalized": normalized_digest,
                    "profile": NTD_CHUNKING_PROFILE,
                }
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_chunks(chunk_id,version,corpus_object_id,source_version_id,normative_document_id,"
                    "normative_edition_id,authority_class,ordinal,page_start,page_end,structural_path,source_locator_ids,raw_text,"
                    "normalized_text,raw_text_digest,normalized_text_digest,chunking_profile_version,parent_chunk_id,"
                    "continuation_of_chunk_id,chunk_fingerprint) VALUES (:id,1,:corpus,:source,:document,:edition,:authority,:ordinal,"
                    ":start,:end,:path,:locators,:raw,:normalized,:raw_digest,:normalized_digest,:profile,:parent,:continuation,:fingerprint) "
                    "ON CONFLICT (chunk_fingerprint) DO NOTHING"
                ),
                {
                    "id": chunk_id,
                    "corpus": corpus_id,
                    "source": source_version_id,
                    "document": normative_document_id,
                    "edition": normative_edition_id,
                    "authority": authority_class,
                    "ordinal": chunk.ordinal,
                    "start": chunk.page_start,
                    "end": chunk.page_end,
                    "path": chunk.structural_path,
                    "locators": list(chunk.locator_ids),
                    "raw": chunk.raw_text,
                    "normalized": chunk.normalized_text,
                    "raw_digest": raw_digest,
                    "normalized_digest": normalized_digest,
                    "profile": NTD_CHUNKING_PROFILE,
                    "parent": chunk.parent_chunk_id,
                    "continuation": continuation_id,
                    "fingerprint": fingerprint,
                },
            )
            previous_by_path[chunk.structural_path] = chunk_id
    return chunk_ids


def _register_chunk_profile(engine: Engine, receipt: dict[str, Any]) -> UUID:
    payload = {
        "profile_key": NTD_CHUNKING_PROFILE,
        "profile_version": "1.0.0",
        "strategy": "structure_aware",
        "parameters": {"target_characters": 1800, "hard_max_characters": 2600},
        "qualification_receipt": receipt,
    }
    fingerprint = semantic_digest(payload)
    profile_id = deterministic_uuid(f"ntd-chunk-profile:{fingerprint}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_chunk_profiles(chunk_profile_id,profile_key,profile_version,strategy,parameters,"
                "qualification_status,benchmark_receipt,profile_fingerprint) VALUES (:id,:key,:version,'structure_aware',"
                "CAST(:parameters AS jsonb),'candidate',CAST(:receipt AS jsonb),:fingerprint) "
                "ON CONFLICT (profile_fingerprint) DO NOTHING"
            ),
            {
                "id": profile_id,
                "key": NTD_CHUNKING_PROFILE,
                "version": "1.0.0",
                "parameters": json.dumps(payload["parameters"], sort_keys=True),
                "receipt": json.dumps(receipt, ensure_ascii=False, sort_keys=True),
                "fingerprint": fingerprint,
            },
        )
    return profile_id


def _persist_contextual_chunks(
    engine: Engine,
    corpus_id: UUID,
    source_version_id: UUID,
    designation: str,
    title: str,
    chunks: Sequence[_Chunk],
    chunk_ids: dict[int, UUID],
    chunk_profile_id: UUID,
) -> tuple[UUID, ...]:
    contextual_ids: list[UUID] = []
    with engine.begin() as connection:
        for chunk in chunks:
            chunk_id = chunk_ids[chunk.ordinal]
            unit_kind = _structural_unit_kind(chunk.structural_path)
            unit_id = deterministic_uuid(
                f"ntd-structural-unit:{source_version_id}:{chunk.ordinal}:"
                f"{_digest(chunk.normalized_text.encode())}:{NTD_CHUNKING_PROFILE}"
            )
            unit_fingerprint = semantic_digest(
                {
                    "unit": str(unit_id),
                    "source": str(source_version_id),
                    "path": chunk.structural_path,
                    "pages": [chunk.page_start, chunk.page_end],
                    "text": _digest(chunk.normalized_text.encode()),
                }
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_structural_units(structural_unit_id,version,corpus_object_id,source_version_id,"
                    "unit_kind,ordinal,heading,page_start,page_end,structural_path,source_locator_ids,raw_text,normalized_text,"
                    "raw_text_digest,normalized_text_digest,derivation_method,confidence_status,unit_fingerprint) VALUES "
                    "(:id,1,:corpus,:source,:kind,:ordinal,:heading,:start,:end,:path,:locators,:raw,:normalized,:raw_digest,"
                    ":normalized_digest,'deterministic_structural_chunk@1.0.0','deterministic',:fingerprint) "
                    "ON CONFLICT (unit_fingerprint) DO NOTHING"
                ),
                {
                    "id": unit_id,
                    "corpus": corpus_id,
                    "source": source_version_id,
                    "kind": unit_kind,
                    "ordinal": chunk.ordinal,
                    "heading": chunk.structural_path[:500],
                    "start": chunk.page_start,
                    "end": chunk.page_end,
                    "path": chunk.structural_path,
                    "locators": list(chunk.locator_ids),
                    "raw": chunk.raw_text,
                    "normalized": chunk.normalized_text,
                    "raw_digest": _digest(chunk.raw_text.encode()),
                    "normalized_digest": _digest(chunk.normalized_text.encode()),
                    "fingerprint": unit_fingerprint,
                },
            )
            page_context = f"Страницы {chunk.page_start}–{chunk.page_end}"
            derived_context = (
                f"{designation}. {title}. Раздел: {chunk.structural_path}. {page_context}."
            )
            input_text = f"{derived_context}\n{chunk.normalized_text}"
            context_digest = _digest(derived_context.encode())
            input_digest = _digest(input_text.encode())
            contextual_id = deterministic_uuid(
                f"ntd-contextual-chunk:{chunk_profile_id}:{chunk_id}:1:{input_digest}"
            )
            contextual_fingerprint = semantic_digest(
                {
                    "contextual_chunk": str(contextual_id),
                    "chunk": str(chunk_id),
                    "profile": str(chunk_profile_id),
                    "input": input_digest,
                }
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_contextual_chunks(contextual_chunk_id,version,chunk_id,chunk_version,chunk_profile_id,"
                    "structural_unit_ids,designation_context,title_context,section_context,parent_heading_context,scope_context,"
                    "regulated_work_context,page_range_context,derived_context,context_digest,input_text,input_digest,"
                    "contextual_fingerprint) VALUES (:id,1,:chunk,1,:profile,:units,:designation,:title,:section,'','','',"
                    ":pages,:context,:context_digest,:input,:input_digest,:fingerprint) "
                    "ON CONFLICT (contextual_fingerprint) DO NOTHING"
                ),
                {
                    "id": contextual_id,
                    "chunk": chunk_id,
                    "profile": chunk_profile_id,
                    "units": [unit_id],
                    "designation": designation,
                    "title": title,
                    "section": chunk.structural_path,
                    "pages": page_context,
                    "context": derived_context,
                    "context_digest": context_digest,
                    "input": input_text,
                    "input_digest": input_digest,
                    "fingerprint": contextual_fingerprint,
                },
            )
            contextual_ids.append(contextual_id)
    if len(contextual_ids) != len(chunks):
        raise ValueError("ntd_contextual_chunk_identity_cardinality_mismatch")
    return tuple(contextual_ids)


def _structural_unit_kind(path: str) -> str:
    normalized = path.casefold().strip()
    if normalized.startswith("таблица"):
        return "table"
    if normalized.startswith("приложение"):
        return "appendix"
    if re.match(r"^\d+(?:\.\d+){2,}", normalized):
        return "subclause"
    if re.match(r"^\d+\.\d+", normalized):
        return "clause"
    return "section"


def _register_embedding_profile(engine: Engine, embedding: EmbeddingPort) -> UUID:
    if embedding.dimension != 1024:
        raise ValueError("ntd_embedding_profile_requires_1024_dimensions")
    payload = {
        "key": embedding.profile_key,
        "version": embedding.profile_version,
        "model": embedding.model_id,
        "revision": embedding.model_revision,
        "digest": embedding.model_digest,
        "dimension": embedding.dimension,
        "normalization": embedding.normalization,
        "input": embedding.input_construction,
        "qualification": embedding.qualification_receipt,
    }
    fingerprint = semantic_digest(payload)
    profile_id = deterministic_uuid(f"ntd-embedding-profile:{fingerprint}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_embedding_profiles(embedding_profile_id,profile_key,profile_version,model_id,"
                "model_revision,model_digest,dimension,normalization,input_construction,qualification_receipt,status,profile_fingerprint) "
                "VALUES (:id,:key,:version,:model,:revision,:digest,:dimension,:normalization,:input,CAST(:qualification AS jsonb),'qualified',:fingerprint) "
                "ON CONFLICT (profile_fingerprint) DO NOTHING"
            ),
            {
                "id": profile_id,
                "key": embedding.profile_key,
                "version": embedding.profile_version,
                "model": embedding.model_id,
                "revision": embedding.model_revision,
                "digest": embedding.model_digest,
                "dimension": embedding.dimension,
                "normalization": embedding.normalization,
                "input": embedding.input_construction,
                "qualification": json.dumps(embedding.qualification_receipt, ensure_ascii=False),
                "fingerprint": fingerprint,
            },
        )
    return profile_id


def _embed_pending(
    engine: Engine, embedding: EmbeddingPort, profile_id: UUID, *, batch_size: int
) -> None:
    while True:
        with engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT cc.contextual_chunk_id,cc.version,cc.input_text,cc.input_digest "
                        "FROM platform.ntd_contextual_chunks cc "
                        "JOIN platform.ntd_chunk_profiles cp ON cp.chunk_profile_id=cc.chunk_profile_id "
                        "LEFT JOIN platform.ntd_chunk_embeddings e ON e.embedding_profile_id=:profile "
                        "AND e.contextual_chunk_id=cc.contextual_chunk_id "
                        "AND e.contextual_chunk_version=cc.version "
                        "WHERE cp.qualification_status='qualified_primary' "
                        "AND e.contextual_chunk_id IS NULL "
                        "ORDER BY cc.contextual_chunk_id LIMIT :limit"
                    ),
                    {"profile": profile_id, "limit": batch_size},
                ).mappings()
            )
        if not rows:
            return
        texts = [str(row["input_text"]) for row in rows]
        vectors = embedding.encode(texts)
        with engine.begin() as connection:
            for row, text, vector in zip(rows, texts, vectors, strict=True):
                input_digest = _digest(text.encode())
                if input_digest != row["input_digest"]:
                    raise ValueError("ntd_contextual_chunk_input_digest_mismatch")
                embedding_digest = _vector_digest(vector)
                connection.execute(
                    sa.text(
                        "INSERT INTO platform.ntd_chunk_embeddings(embedding_profile_id,contextual_chunk_id,contextual_chunk_version,dimension,"
                        "embedding,embedding_digest,input_digest) VALUES (:profile,:chunk,:version,:dimension,CAST(:embedding AS vector),:digest,:input) "
                        "ON CONFLICT (embedding_profile_id,contextual_chunk_id,contextual_chunk_version) DO NOTHING"
                    ),
                    {
                        "profile": profile_id,
                        "chunk": row["contextual_chunk_id"],
                        "version": row["version"],
                        "dimension": embedding.dimension,
                        "embedding": vector,
                        "digest": embedding_digest,
                        "input": input_digest,
                    },
                )


def _reconcile(engine: Engine, profile_id: UUID, *, canary: bool) -> NtdMemoryBuildResult:
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT count(*) objects,count(*) filter(where terminal_outcome='admitted') admitted,"
                    "count(*) filter(where terminal_outcome<>'admitted') blocked FROM platform.ntd_corpus_objects"
                )
            )
            .mappings()
            .one()
        )
        page = (
            connection.execute(
                sa.text(
                    "SELECT count(*) pages,count(*) terminal,"
                    "count(*) filter(where terminal_outcome in ('native_complete', 'ocr_complete', 'mixed_complete', 'table_complete') and length(normalized_text)>0) extracted,count(*) filter(where terminal_outcome like 'blocked%') blocked "
                    "FROM platform.ntd_corpus_pages"
                )
            )
            .mappings()
            .one()
        )
        chunk_count = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.ntd_contextual_chunks c "
                    "JOIN platform.ntd_chunk_profiles p ON p.chunk_profile_id = c.chunk_profile_id "
                    "WHERE p.qualification_status = 'qualified_primary'"
                )
            )
            or 0
        )
        embedding_count = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) "
                    "FROM platform.ntd_chunk_embeddings e "
                    "JOIN platform.ntd_contextual_chunks c ON e.contextual_chunk_id = c.contextual_chunk_id AND e.contextual_chunk_version = c.version "
                    "JOIN platform.ntd_chunk_profiles p ON c.chunk_profile_id = p.chunk_profile_id "
                    "WHERE e.embedding_profile_id=:id AND p.qualification_status='qualified_primary'"
                ),
                {"id": profile_id},
            )
            or 0
        )
        without = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.ntd_contextual_chunks c "
                    "JOIN platform.ntd_chunk_profiles p ON c.chunk_profile_id = p.chunk_profile_id "
                    "LEFT JOIN platform.ntd_chunk_embeddings e ON "
                    "e.embedding_profile_id=:id AND e.contextual_chunk_id=c.contextual_chunk_id "
                    "AND e.contextual_chunk_version=c.version "
                    "WHERE p.qualification_status = 'qualified_primary' AND e.contextual_chunk_id IS NULL"
                ),
                {"id": profile_id},
            )
            or 0
        )
        orphan = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.ntd_chunk_embeddings e LEFT JOIN platform.ntd_contextual_chunks c ON "
                    "c.contextual_chunk_id=e.contextual_chunk_id AND c.version=e.contextual_chunk_version "
                    "WHERE e.embedding_profile_id=:id AND c.contextual_chunk_id IS NULL"
                ),
                {"id": profile_id},
            )
            or 0
        )
        searchable = int(
            connection.scalar(
                sa.text(
                    """
                    SELECT count(DISTINCT ch.corpus_object_id)
                    FROM platform.ntd_chunks ch
                    JOIN platform.ntd_contextual_chunks c
                      ON c.chunk_id = ch.chunk_id
                     AND c.chunk_version = ch.version
                    JOIN platform.ntd_chunk_profiles p
                      ON p.chunk_profile_id = c.chunk_profile_id
                    WHERE p.qualification_status = 'qualified_primary'
                    """
                )
            )
            or 0
        )
    terminal_documents = int(row["objects"])
    expected = 1 if canary else NTD_DENOMINATOR
    outcome = (
        "complete"
        if terminal_documents == expected
        and without == 0
        and orphan == 0
        and int(page["blocked"]) == 0
        else "partial"
    )
    counters = {
        "objects": terminal_documents,
        "admitted": int(row["admitted"]),
        "blocked_objects": int(row["blocked"]),
        "pages": int(page["pages"]),
        "pages_terminal": int(page["terminal"]),
        "pages_extracted": int(page["extracted"]),
        "pages_blocked": int(page["blocked"]),
        "chunks": chunk_count,
        "embeddings": embedding_count,
        "chunks_without_embeddings": without,
        "orphan_embeddings": orphan,
        "searchable_documents": searchable,
    }
    fingerprint = semantic_digest(
        {
            "profile": NTD_CANONICAL_MEMORY_PROFILE,
            "embedding_profile": str(profile_id),
            "canary": canary,
            "counters": counters,
        }
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_memory_build_receipts(build_receipt_id,profile_version,denominator_ntd,"
                "deferred_estimate_references,counters,source_audit_digest,embedding_profile_id,projection_fingerprint,build_fingerprint,terminal_outcome) "
                "VALUES (:id,:profile,118,12,CAST(:counters AS jsonb),:audit,:embedding,:projection,:fingerprint,:outcome) "
                "ON CONFLICT (build_fingerprint) DO NOTHING"
            ),
            {
                "id": deterministic_uuid(f"ntd-memory-receipt:{fingerprint}"),
                "profile": NTD_CANONICAL_MEMORY_PROFILE,
                "counters": json.dumps(counters, sort_keys=True),
                "audit": NTD_AUDIT_DIGEST,
                "embedding": profile_id,
                "projection": semantic_digest(
                    {"fts_chunks": chunk_count, "vector_entries": embedding_count}
                ),
                "fingerprint": fingerprint,
                "outcome": outcome,
            },
        )
    return NtdMemoryBuildResult(
        NTD_DENOMINATOR,
        GESN_DEFERRED_REFERENCE_COUNT,
        int(row["admitted"]),
        int(row["blocked"]),
        terminal_documents,
        int(page["pages"]),
        int(page["terminal"]),
        int(page["extracted"]),
        int(page["blocked"]),
        chunk_count,
        embedding_count,
        without,
        orphan,
        searchable,
        fingerprint,
        outcome,
    )


def _ensure_page_locator(engine: Engine, source_version_id: UUID, page: int, digest: str) -> UUID:
    locator_id = deterministic_uuid(f"ntd-corpus-page-locator:{source_version_id}:{page}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.source_locators(source_locator_id,source_version_id,locator_kind,locator_key,"
                "locator_value,fragment_digest) VALUES (:id,:source,'normative_corpus_page',:key,CAST(:value AS jsonb),:digest) "
                "ON CONFLICT (source_version_id,locator_kind,locator_key) DO NOTHING"
            ),
            {
                "id": locator_id,
                "source": source_version_id,
                "key": f"page:{page}",
                "value": json.dumps({"page_number": page}),
                "digest": digest,
            },
        )
    return locator_id


def _extract_poppler_layout_pages(path: Path, expected_pages: int) -> tuple[str, ...] | None:
    pdftotext_bin = shutil.which("pdftotext")
    if pdftotext_bin is None:
        return None
    try:
        result = subprocess.run(
            [pdftotext_bin, "-layout", str(path), "-"],
            check=False,
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pages = text.split("\f")
    if pages and pages[-1].strip() == "":
        pages.pop()
    if len(pages) != expected_pages:
        return None
    return tuple(pages)


def _ocr_page(path: Path, page: int, rotation: int, executable: Path) -> tuple[str, str, str, bool]:
    rendered = render_normative_pdf_page(path, page_index=page, source_rotation_degrees=rotation)
    deterministic_blank = _is_deterministic_blank_png(rendered.png_bytes)
    request_digest = semantic_digest(
        {"profile": "apple-vision-accurate@1.0.0", "render": rendered.render_digest}
    )
    with tempfile.NamedTemporaryFile(prefix="asd-ntd-ocr-", suffix=".png") as image:
        image.write(rendered.png_bytes)
        image.flush()
        completed = subprocess.run(
            [str(executable), image.name], capture_output=True, check=False, timeout=180
        )
    response_digest = _digest(completed.stdout)
    if completed.returncode != 0:
        return "", request_digest, response_digest, deterministic_blank
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return "", request_digest, response_digest, deterministic_blank
    observations = payload.get("observations", []) if isinstance(payload, dict) else []
    text = "\n".join(
        str(item.get("text", "")).strip()
        for item in observations
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    )
    return text, request_digest, response_digest, deterministic_blank


def _is_deterministic_blank_png(png_bytes: bytes) -> bool:
    """Classify only near-uniform white renders as deterministic blank pages."""

    try:
        with Image.open(BytesIO(png_bytes)) as source:
            grayscale = source.convert("L")
        pixel_count = grayscale.width * grayscale.height
        if pixel_count == 0:
            return False
        standard_deviation = float(ImageStat.Stat(grayscale).stddev[0])
        dark_pixel_fraction = sum(grayscale.histogram()[:245]) / pixel_count
    except (OSError, ValueError):
        return False
    return standard_deviation < 1.5 and dark_pixel_fraction < 0.001


def _page_kind(value: PageHealthKind) -> str:
    return {
        PageHealthKind.BORN_DIGITAL: "native",
        PageHealthKind.EXISTING_OCR: "native",
        PageHealthKind.RASTER_ONLY: "raster",
        PageHealthKind.MIXED: "mixed",
        PageHealthKind.TABLE_HEAVY: "table_heavy",
        PageHealthKind.DAMAGED_ENCODING: "damaged_native",
        PageHealthKind.BLANK: "blank",
        PageHealthKind.RENDER_FAILURE: "unsupported_corrupt",
        PageHealthKind.PASSWORD_PROTECTED: "unsupported_corrupt",
        PageHealthKind.DRAWING: "mixed",
    }[value]


def _page_structural_path(elements: Sequence[Any]) -> str:
    for element in elements:
        value = element.raw_text.strip()
        if _heading(value):
            return _heading(value) or "document"
    return "document"


def _heading(value: str) -> str | None:
    line = value.splitlines()[0].strip()[:180]
    if re.match(r"^(?:раздел|глава|приложение|таблица)\s+[А-ЯA-Z0-9.\-]+", line, re.I):
        return line
    if re.match(r"^\d+(?:\.\d+){1,5}(?:[.)]|\s)", line):
        return line
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00ad", "").replace("ё", "е")).strip()


def _designation_aliases(value: str) -> list[str]:
    aliases = {value, re.sub(r"\s+", "", value)}
    match = re.search(
        r"\b(СП|ГОСТ(?:\s+Р)?|ГЭСНм?|GESN[m]?)\s*([0-9]+(?:[.\-][0-9]+)*)", value, re.I
    )
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        aliases.update(
            {f"{prefix} {number}", f"{prefix}{number}", f"{prefix} {number.split('.')[0]}"}
        )
    return sorted(aliases)


def _vector_digest(vector: Sequence[float]) -> str:
    payload = ",".join(format(value, ".9g") for value in vector).encode()
    return _digest(payload)


def _validate_inputs(audit: Path, root: Path, embedding: EmbeddingPort, batch: int) -> None:
    if not audit.is_absolute() or not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError("ntd_memory_build_path_invalid")
    if embedding.profile_version.lower() == "latest" or not embedding.model_digest.startswith(
        "sha256:"
    ):
        raise ValueError("ntd_embedding_profile_unpinned")
    if not 1 <= batch <= 128:
        raise ValueError("ntd_embedding_batch_size_invalid")


def _validate_retrieval_qualification(
    receipt_path: Path, embedding: EmbeddingPort
) -> dict[str, Any]:
    if not receipt_path.is_absolute() or not receipt_path.is_file() or receipt_path.is_symlink():
        raise ValueError("ntd_retrieval_qualification_receipt_invalid")
    receipt = json.loads(receipt_path.read_bytes())
    if (
        receipt.get("terminal_outcome") != "pass"
        or int(receipt.get("question_count", 0)) < 100
        or receipt.get("selected_embedding_model_digest") != embedding.model_digest
        or not str(receipt.get("selected_retrieval_profile", "")).startswith("ntd-")
    ):
        raise ValueError("ntd_retrieval_profile_not_qualified")
    return dict(receipt)


def _uuid_or_none(value: Any) -> UUID | None:
    return UUID(str(value)) if value else None


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()
