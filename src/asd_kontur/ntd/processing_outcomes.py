"""NTD processing outcomes module contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid

PROCESSING_PROFILE_VERSION = "1.0.0"

_PHYSICAL_OUTCOME_SQL = """
WITH page_stats AS (
    SELECT
        corpus_object_id,
        COUNT(*) AS pages_total,
        SUM(CASE WHEN terminal_outcome IN (
            'native_complete',
            'ocr_complete',
            'mixed_complete',
            'table_complete'
        )
                 AND LENGTH(normalized_text) > 0 THEN 1 ELSE 0 END) AS extracted_pages,
        SUM(CASE WHEN terminal_outcome = 'blank_verified' THEN 1 ELSE 0 END) AS blank_pages,
        SUM(CASE WHEN terminal_outcome LIKE 'blocked%' THEN 1 ELSE 0 END) AS blocked_pages,
        BOOL_OR(blocker_code = 'pdf_structure_invalid') AS has_pdf_structure_invalid,
        COALESCE(
            ARRAY_AGG(DISTINCT blocker_code ORDER BY blocker_code)
            FILTER (WHERE blocker_code IS NOT NULL),
            ARRAY[]::text[]
        ) AS page_blocker_codes
    FROM platform.ntd_corpus_pages
    GROUP BY corpus_object_id
),
unit_stats AS (
    SELECT
        corpus_object_id,
        COUNT(*) AS structural_units_total
    FROM platform.ntd_structural_units
    WHERE ordinal >= 100000
    GROUP BY corpus_object_id
),
chunk_stats AS (
    SELECT
        ch.corpus_object_id,
        COUNT(DISTINCT cc.contextual_chunk_id) AS contextual_chunks_total,
        COUNT(DISTINCT e.contextual_chunk_id) AS embedded_chunks_total
    FROM platform.ntd_chunks ch
    JOIN platform.ntd_contextual_chunks cc
        ON ch.chunk_id = cc.chunk_id AND ch.version = cc.chunk_version
    JOIN platform.ntd_chunk_profiles p
        ON cc.chunk_profile_id = p.chunk_profile_id AND p.qualification_status = 'qualified_primary'
    LEFT JOIN platform.ntd_chunk_embeddings e
        ON cc.contextual_chunk_id = e.contextual_chunk_id
        AND cc.version = e.contextual_chunk_version
        AND e.embedding_profile_id = :embedding_profile_id
    GROUP BY ch.corpus_object_id
),
graph_stats AS (
    SELECT
        u.corpus_object_id,
        COUNT(DISTINCT n.graph_node_id) AS graph_nodes_total
    FROM platform.ntd_structural_units u
    JOIN platform.ntd_graph_nodes n ON n.canonical_entity_id = u.structural_unit_id
    WHERE u.ordinal >= 100000
    GROUP BY u.corpus_object_id
)
SELECT
    co.corpus_object_id,
    co.terminal_outcome AS admission_outcome,
    co.bytes_status,
    co.blocker_code AS source_blocker,
    COALESCE(ps.pages_total, 0) AS pages_total,
    COALESCE(ps.extracted_pages, 0) AS extracted_pages,
    COALESCE(ps.blank_pages, 0) AS blank_pages,
    COALESCE(ps.blocked_pages, 0) AS blocked_pages,
    COALESCE(ps.has_pdf_structure_invalid, FALSE) AS has_pdf_structure_invalid,
    COALESCE(ps.page_blocker_codes, ARRAY[]::text[]) AS page_blocker_codes,
    COALESCE(us.structural_units_total, 0) AS structural_units_total,
    COALESCE(cs.contextual_chunks_total, 0) AS contextual_chunks_total,
    COALESCE(cs.embedded_chunks_total, 0) AS embedded_chunks_total,
    COALESCE(gs.graph_nodes_total, 0) AS graph_nodes_total
FROM platform.ntd_corpus_objects co
LEFT JOIN page_stats ps ON co.corpus_object_id = ps.corpus_object_id
LEFT JOIN unit_stats us ON co.corpus_object_id = us.corpus_object_id
LEFT JOIN chunk_stats cs ON co.corpus_object_id = cs.corpus_object_id
LEFT JOIN graph_stats gs ON co.corpus_object_id = gs.corpus_object_id
WHERE co.authority_class <> 'gesn_candidate'
ORDER BY co.corpus_object_id;
"""

ALLOWED_STATUSES: tuple[str, ...] = (
    "indexed_complete",
    "indexed_partial",
    "blocked_extraction",
    "blocked_source",
    "unsupported_content",
)


@dataclass(frozen=True, slots=True)
class PhysicalProcessingRow:
    """Read-only snapshot of physical NTD processing metrics."""

    corpus_object_id: UUID
    admission_outcome: str
    bytes_status: str
    source_blocker: str | None
    pages_total: int
    extracted_pages: int
    blank_pages: int
    blocked_pages: int
    has_pdf_structure_invalid: bool
    page_blocker_codes: tuple[str, ...]
    structural_units_total: int
    contextual_chunks_total: int
    embedded_chunks_total: int
    graph_nodes_total: int
    fts_index_available: bool
    hnsw_index_available: bool


def _check_indexes(engine: sa.Engine) -> tuple[bool, bool]:
    """Inspect pg_indexes for required physical indexes."""
    sql = """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'platform'
        AND indexname IN (
            'ntd_chunks_fts_gin',
            'ntd_contextual_chunks_fts_gin',
            'ntd_chunk_embeddings_hnsw'
        )
    """
    with engine.connect() as conn:
        result = conn.execute(sa.text(sql))
        indexes = {row["indexname"] for row in result.mappings()}

    fts_available = indexes.issuperset({"ntd_chunks_fts_gin", "ntd_contextual_chunks_fts_gin"})
    hnsw_available = "ntd_chunk_embeddings_hnsw" in indexes
    return fts_available, hnsw_available


@dataclass(frozen=True, slots=True)
class ProcessingOutcomeSummary:
    """Summary of NTD document processing outcomes.

    Attributes:
        profile: The processing profile version.
        total: Total number of documents processed.
        indexed_complete: Count of documents with 'indexed_complete' status.
        indexed_partial: Count of documents with 'indexed_partial' status.
        blocked_extraction: Count of documents with 'blocked_extraction' status.
        blocked_source: Count of documents with 'blocked_source' status.
        unsupported_content: Count of documents with 'unsupported_content' status.
        indexed_documents: Count of documents that are indexed (complete or partial).
        fingerprint: SHA256 fingerprint of the processing outcome.
    """

    profile: str
    total: int
    indexed_complete: int
    indexed_partial: int
    blocked_extraction: int
    blocked_source: int
    unsupported_content: int
    indexed_documents: int
    fingerprint: str


def load_physical_outcome_rows(
    engine: sa.Engine, embedding_profile_id: UUID
) -> tuple[PhysicalProcessingRow, ...]:
    """Load physical processing outcome rows for the given embedding profile."""
    fts_available, hnsw_available = _check_indexes(engine)

    if not fts_available:
        raise ValueError("missing_fts_indexes")
    if not hnsw_available:
        raise ValueError("missing_hnsw_index")

    with engine.connect() as conn:
        result = conn.execute(
            sa.text(_PHYSICAL_OUTCOME_SQL),
            {"embedding_profile_id": embedding_profile_id},
        )
        rows = result.mappings().all()

    processed_rows: list[PhysicalProcessingRow] = []
    for row in rows:
        raw_id = row["corpus_object_id"]
        corpus_object_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
        source_blocker_value = row["source_blocker"]
        source_blocker = str(source_blocker_value) if source_blocker_value is not None else None
        page_blocker_codes_value = row["page_blocker_codes"]
        if page_blocker_codes_value:
            page_blocker_codes = tuple(str(code) for code in page_blocker_codes_value)
        else:
            page_blocker_codes = ()
        processed_rows.append(
            PhysicalProcessingRow(
                corpus_object_id=corpus_object_id,
                admission_outcome=str(row["admission_outcome"]),
                bytes_status=str(row["bytes_status"]),
                source_blocker=source_blocker,
                pages_total=int(row["pages_total"]),
                extracted_pages=int(row["extracted_pages"]),
                blank_pages=int(row["blank_pages"]),
                blocked_pages=int(row["blocked_pages"]),
                has_pdf_structure_invalid=bool(row["has_pdf_structure_invalid"]),
                page_blocker_codes=page_blocker_codes,
                structural_units_total=int(row["structural_units_total"]),
                contextual_chunks_total=int(row["contextual_chunks_total"]),
                embedded_chunks_total=int(row["embedded_chunks_total"]),
                graph_nodes_total=int(row["graph_nodes_total"]),
                fts_index_available=fts_available,
                hnsw_index_available=hnsw_available,
            )
        )

    return tuple(processed_rows)


def _validate_metrics(row: PhysicalProcessingRow) -> None:
    """Validate non-negative metrics and consistency constraints."""
    metrics = (
        row.pages_total,
        row.extracted_pages,
        row.blank_pages,
        row.blocked_pages,
        row.structural_units_total,
        row.contextual_chunks_total,
        row.embedded_chunks_total,
        row.graph_nodes_total,
    )
    if any(value < 0 for value in metrics):
        raise ValueError("ntd_processing_metrics_invalid")

    if row.extracted_pages + row.blank_pages + row.blocked_pages > row.pages_total:
        raise ValueError("ntd_processing_metrics_invalid")

    if row.embedded_chunks_total > row.contextual_chunks_total:
        raise ValueError("ntd_processing_metrics_invalid")


def classify_processing_row(row: PhysicalProcessingRow) -> tuple[str, str | None]:
    """Classify a physical processing row into a status and blocker."""
    _validate_metrics(row)

    if row.admission_outcome != "admitted" or row.bytes_status != "present_verified":
        blocker_parts = list(row.page_blocker_codes)
        if row.source_blocker:
            blocker_parts.append(row.source_blocker)
        if not blocker_parts:
            return "blocked_source", "source_not_admitted_or_bytes_unavailable"
        return "blocked_source", ";".join(blocker_parts)

    if row.has_pdf_structure_invalid:
        blocker_parts = list(row.page_blocker_codes)
        if row.source_blocker:
            blocker_parts.append(row.source_blocker)
        if not blocker_parts:
            blocker_parts.append("pdf_structure_invalid")
        return "unsupported_content", ";".join(blocker_parts)

    if row.contextual_chunks_total == 0:
        blocker_parts = list(row.page_blocker_codes)
        if row.source_blocker:
            blocker_parts.append(row.source_blocker)
        if not blocker_parts:
            blocker_parts.append("zero_chunks")
        return "blocked_extraction", ";".join(blocker_parts)

    partial_blockers: list[str] = []

    if row.blocked_pages > 0:
        partial_blockers.append("blocked_pages")

    expected_extracted = row.pages_total - row.blank_pages - row.blocked_pages
    if row.extracted_pages != expected_extracted:
        partial_blockers.append("terminal_coverage_mismatch")

    if row.structural_units_total == 0 or row.graph_nodes_total == 0:
        partial_blockers.append("zero_units_or_graph")

    if row.embedded_chunks_total != row.contextual_chunks_total:
        partial_blockers.append("embedding_count_mismatch")

    if not row.fts_index_available or not row.hnsw_index_available:
        partial_blockers.append("missing_physical_index")

    if partial_blockers:
        blocker_parts = list(row.page_blocker_codes)
        if row.source_blocker:
            blocker_parts.append(row.source_blocker)
        blocker_parts.extend(partial_blockers)
        return "indexed_partial", ";".join(blocker_parts)

    return "indexed_complete", None


@dataclass(frozen=True, slots=True)
class _MaterializedOutcome:
    """Deterministic internal outcome record for NTD processing."""

    outcome_id: UUID
    corpus_object_id: UUID
    status: str
    blocker: str | None
    pages_total: int
    pages_extracted: int
    pages_blocked: int
    structural_units_count: int
    contextual_chunks_count: int
    embeddings_count: int
    fts_indexed: bool
    hnsw_indexed: bool
    typed_graph_indexed: bool
    gateway_registered: bool
    metrics: Mapping[str, object]
    fingerprint: str


def _build_materialized_outcome(
    row: PhysicalProcessingRow,
    embedding_profile_id: UUID,
) -> _MaterializedOutcome:
    """Build a deterministic materialized outcome from a physical processing row."""
    status, blocker = classify_processing_row(row)

    fts_indexed = row.contextual_chunks_total > 0 and row.fts_index_available
    hnsw_indexed = row.embedded_chunks_total > 0 and row.hnsw_index_available
    typed_graph_indexed = row.graph_nodes_total > 0
    gateway_registered = row.contextual_chunks_total > 0

    metrics: Mapping[str, object] = {
        "blank_pages": row.blank_pages,
        "page_blocker_codes": row.page_blocker_codes,
        "admission_outcome": row.admission_outcome,
        "bytes_status": row.bytes_status,
        "graph_nodes_total": row.graph_nodes_total,
        "embedding_profile_id": str(embedding_profile_id),
        "fts_indexed": fts_indexed,
        "hnsw_indexed": hnsw_indexed,
        "typed_graph_indexed": typed_graph_indexed,
        "gateway_registered": gateway_registered,
    }

    payload = (
        f"{row.corpus_object_id}:{status}:{blocker}:{embedding_profile_id}:"
        f"{row.pages_total}:{row.extracted_pages}:{row.blank_pages}:{row.blocked_pages}:"
        f"{row.structural_units_total}:{row.contextual_chunks_total}:{row.embedded_chunks_total}:"
        f"{row.graph_nodes_total}:{fts_indexed}:{hnsw_indexed}:{typed_graph_indexed}:{gateway_registered}"
    )
    fingerprint = semantic_digest(payload)
    outcome_id = deterministic_uuid(
        f"ntd-processing-outcome:{PROCESSING_PROFILE_VERSION}:{row.corpus_object_id}"
    )

    return _MaterializedOutcome(
        outcome_id=outcome_id,
        corpus_object_id=row.corpus_object_id,
        status=status,
        blocker=blocker,
        pages_total=row.pages_total,
        pages_extracted=row.extracted_pages,
        pages_blocked=row.blocked_pages,
        structural_units_count=row.structural_units_total,
        contextual_chunks_count=row.contextual_chunks_total,
        embeddings_count=row.embedded_chunks_total,
        fts_indexed=fts_indexed,
        hnsw_indexed=hnsw_indexed,
        typed_graph_indexed=typed_graph_indexed,
        gateway_registered=gateway_registered,
        metrics=metrics,
        fingerprint=fingerprint,
    )


def materialize_processing_outcomes(
    engine: sa.Engine, embedding_profile_id: UUID
) -> ProcessingOutcomeSummary:
    """Materialize NTD processing outcomes into the database."""
    physical_rows = load_physical_outcome_rows(engine, embedding_profile_id)
    outcomes = tuple(
        _build_materialized_outcome(row, embedding_profile_id) for row in physical_rows
    )

    insert_sql = sa.text(
        """
        INSERT INTO platform.ntd_document_processing_outcomes (
            processing_outcome_id,
            corpus_object_id,
            processing_profile_version,
            terminal_status,
            pages_total,
            pages_extracted,
            pages_blocked,
            structural_units_count,
            contextual_chunks_count,
            embeddings_count,
            fts_indexed,
            hnsw_indexed,
            typed_graph_indexed,
            gateway_registered,
            blocker_code,
            metrics,
            processing_fingerprint
        ) VALUES (
            :outcome_id,
            :corpus_object_id,
            :profile_version,
            :status,
            :pages_total,
            :pages_extracted,
            :pages_blocked,
            :structural_units_count,
            :contextual_chunks_count,
            :embeddings_count,
            :fts_indexed,
            :hnsw_indexed,
            :typed_graph_indexed,
            :gateway_registered,
            :blocker_code,
            CAST(:metrics AS jsonb),
            :fingerprint
        )
        ON CONFLICT (corpus_object_id, processing_profile_version) DO NOTHING
        """
    )

    with engine.begin() as conn:
        for outcome in outcomes:
            conn.execute(
                insert_sql,
                {
                    "outcome_id": outcome.outcome_id,
                    "corpus_object_id": outcome.corpus_object_id,
                    "profile_version": PROCESSING_PROFILE_VERSION,
                    "status": outcome.status,
                    "pages_total": outcome.pages_total,
                    "pages_extracted": outcome.pages_extracted,
                    "pages_blocked": outcome.pages_blocked,
                    "structural_units_count": outcome.structural_units_count,
                    "contextual_chunks_count": outcome.contextual_chunks_count,
                    "embeddings_count": outcome.embeddings_count,
                    "fts_indexed": outcome.fts_indexed,
                    "hnsw_indexed": outcome.hnsw_indexed,
                    "typed_graph_indexed": outcome.typed_graph_indexed,
                    "gateway_registered": outcome.gateway_registered,
                    "blocker_code": outcome.blocker,
                    "metrics": json.dumps(
                        dict(outcome.metrics),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "fingerprint": outcome.fingerprint,
                },
            )

        select_sql = sa.text(
            """
            SELECT corpus_object_id, terminal_status, processing_fingerprint
            FROM platform.ntd_document_processing_outcomes
            WHERE processing_profile_version = :profile_version
            """
        )
        result = conn.execute(select_sql, {"profile_version": PROCESSING_PROFILE_VERSION})
        db_rows = result.mappings().all()

    expected_map = {str(o.corpus_object_id): (o.status, o.fingerprint) for o in outcomes}
    actual_map = {
        str(r["corpus_object_id"]): (r["terminal_status"], r["processing_fingerprint"])
        for r in db_rows
    }

    if expected_map != actual_map:
        raise ValueError("ntd_processing_outcome_conflict")

    counts = {status: 0 for status in ALLOWED_STATUSES}
    for outcome in outcomes:
        counts[outcome.status] += 1

    indexed_documents = counts["indexed_complete"] + counts["indexed_partial"]

    ordered_tuples = sorted(
        (
            str(o.corpus_object_id),
            o.status,
            o.fingerprint,
        )
        for o in outcomes
    )
    aggregate_payload = "|".join(f"{cid}:{status}:{fp}" for cid, status, fp in ordered_tuples)
    fingerprint = semantic_digest(aggregate_payload)

    return ProcessingOutcomeSummary(
        profile=PROCESSING_PROFILE_VERSION,
        total=len(outcomes),
        indexed_complete=counts["indexed_complete"],
        indexed_partial=counts["indexed_partial"],
        blocked_extraction=counts["blocked_extraction"],
        blocked_source=counts["blocked_source"],
        unsupported_content=counts["unsupported_content"],
        indexed_documents=indexed_documents,
        fingerprint=fingerprint,
    )
