from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.search_corpus import (
    NTD_SEARCH_INDEX_PROFILE,
    NtdSearchBuildResult,
    _persist_document,
    designation_aliases,
)

PROCESSING_PROFILE_VERSION = "1.0.0"


def _materialize_qualified_retrieval_profile(
    connection: sa.Connection,
    qualification_receipt: Mapping[str, Any],
    reranker_model_revision: str,
) -> uuid.UUID:
    if (
        not isinstance(reranker_model_revision, str)
        or not reranker_model_revision
        or reranker_model_revision == "latest"
    ):
        raise ValueError("ntd_production_retrieval_reranker_revision_invalid")

    chunk_profile_id, embedding_profile_id = _load_qualified_base_profiles(
        connection, qualification_receipt
    )
    reranker_profile_id = _materialize_qualified_reranker(
        connection, qualification_receipt, reranker_model_revision
    )

    profile_key = "ntd-contextual-hybrid-hierarchical-graph-reranker"
    profile_version = "1.0.0"
    pipeline_kind = "hybrid_graph_reranker"

    negative_query_policy = qualification_receipt.get("negative_query_policy")
    if not isinstance(negative_query_policy, str) or not negative_query_policy:
        raise ValueError("ntd_production_retrieval_negative_policy_invalid")

    parameters = {
        "exact_designation_first": True,
        "lexical": "postgresql_russian_fts",
        "dense": "cosine_1024",
        "fusion": "rrf",
        "hierarchy": {"max_depth": 2},
        "graph": {"max_depth": 2},
        "reranker": {"top_n": 20},
        "final_top_n": 8,
        "min_relevance": 0.18,
        "negative_query_policy": negative_query_policy,
        "abstain_when_below_threshold": True,
    }

    receipt_payload = {
        "profile_key": profile_key,
        "profile_version": profile_version,
        "pipeline_kind": pipeline_kind,
        "chunk_profile_id": str(chunk_profile_id),
        "embedding_profile_id": str(embedding_profile_id),
        "reranker_profile_id": str(reranker_profile_id),
        "parameters": parameters,
        "qualification_receipt": dict(qualification_receipt),
    }

    fingerprint = semantic_digest(receipt_payload)
    profile_id = deterministic_uuid(f"ntd-retrieval:{fingerprint}")

    connection.execute(
        sa.text(
            """
            INSERT INTO platform.ntd_retrieval_profiles (
                retrieval_profile_id,
                profile_key,
                profile_version,
                chunk_profile_id,
                embedding_profile_id,
                reranker_profile_id,
                pipeline_kind,
                parameters,
                benchmark_receipt,
                status,
                profile_fingerprint
            ) VALUES (
                :id,
                :key,
                :version,
                :chunk_id,
                :embedding_id,
                :reranker_id,
                :pipeline_kind,
                CAST(:parameters AS jsonb),
                CAST(:receipt AS jsonb),
                'qualified_primary',
                :fingerprint
            )
            ON CONFLICT (profile_fingerprint) DO NOTHING
            """
        ),
        {
            "id": profile_id,
            "key": profile_key,
            "version": profile_version,
            "chunk_id": chunk_profile_id,
            "embedding_id": embedding_profile_id,
            "reranker_id": reranker_profile_id,
            "pipeline_kind": pipeline_kind,
            "parameters": json.dumps(parameters),
            "receipt": json.dumps(receipt_payload),
            "fingerprint": fingerprint,
        },
    )

    verify_sql = sa.text(
        """
        SELECT retrieval_profile_id
        FROM platform.ntd_retrieval_profiles
        WHERE retrieval_profile_id = :id
        """
    )
    row = connection.execute(verify_sql, {"id": profile_id}).mappings().first()
    if row is None:
        raise ValueError("ntd_production_retrieval_insert_verification_failed")

    return _uuid(row["retrieval_profile_id"])


def _materialize_qualified_reranker(
    connection: sa.Connection,
    qualification_receipt: Mapping[str, Any],
    reranker_model_revision: str,
) -> uuid.UUID:
    if (
        not isinstance(reranker_model_revision, str)
        or not reranker_model_revision
        or reranker_model_revision == "latest"
    ):
        raise ValueError("ntd_production_reranker_revision_invalid")

    selected_reranker_model = qualification_receipt.get("selected_reranker_model")
    if selected_reranker_model != "Qwen/Qwen3-Reranker-0.6B":
        raise ValueError("ntd_production_reranker_model_mismatch")

    selected_reranker_digest = qualification_receipt.get("selected_reranker_model_digest")
    if (
        not isinstance(selected_reranker_digest, str)
        or not selected_reranker_digest.startswith("sha256:")
        or len(selected_reranker_digest) != 71
        or not all(c in "0123456789abcdef" for c in selected_reranker_digest[7:])
    ):
        raise ValueError("ntd_production_reranker_digest_invalid")

    profile_key = "ntd-qwen3-reranker-0.6b"
    profile_version = "1.0.0"
    dtype = "float16"
    instruction = (
        "Given a query and a document, determine if the document is relevant to the query."
    )

    receipt_payload = {
        "profile_key": profile_key,
        "profile_version": profile_version,
        "model_id": selected_reranker_model,
        "model_revision": reranker_model_revision,
        "model_digest": selected_reranker_digest,
        "dtype": dtype,
        "instruction": instruction,
        "qualification_receipt": dict(qualification_receipt),
    }

    fingerprint = semantic_digest(receipt_payload)
    profile_id = deterministic_uuid(f"ntd-reranker:{fingerprint}")

    connection.execute(
        sa.text(
            """
            INSERT INTO platform.ntd_reranker_profiles (
                reranker_profile_id,
                profile_key,
                profile_version,
                model_id,
                model_revision,
                model_digest,
                dtype,
                instruction,
                qualification_receipt,
                status,
                profile_fingerprint
            ) VALUES (
                :id,
                :key,
                :version,
                :model_id,
                :revision,
                :digest,
                :dtype,
                :instruction,
                CAST(:receipt AS jsonb),
                'qualified',
                :fingerprint
            )
            ON CONFLICT (profile_fingerprint) DO NOTHING
            """
        ),
        {
            "id": profile_id,
            "key": profile_key,
            "version": profile_version,
            "model_id": selected_reranker_model,
            "revision": reranker_model_revision,
            "digest": selected_reranker_digest,
            "dtype": dtype,
            "instruction": instruction,
            "receipt": json.dumps(receipt_payload),
            "fingerprint": fingerprint,
        },
    )

    verify_sql = sa.text(
        """
        SELECT reranker_profile_id
        FROM platform.ntd_reranker_profiles
        WHERE reranker_profile_id = :id
        """
    )
    row = connection.execute(verify_sql, {"id": profile_id}).mappings().first()
    if row is None:
        raise ValueError("ntd_production_reranker_insert_verification_failed")

    return _uuid(row["reranker_profile_id"])


def _load_qualified_base_profiles(
    connection: sa.Connection, qualification_receipt: Mapping[str, Any]
) -> tuple[uuid.UUID, uuid.UUID]:
    if qualification_receipt.get("terminal_outcome") != "pass":
        raise ValueError("ntd_production_receipt_terminal_outcome_invalid")

    question_count = qualification_receipt.get("question_count")
    if not isinstance(question_count, int) or question_count < 100:
        raise ValueError("ntd_production_receipt_question_count_invalid")

    selected_chunk_profile = qualification_receipt.get("selected_chunk_profile")
    if selected_chunk_profile != "ntd-contextual-chunks@1.0.0":
        raise ValueError("ntd_production_receipt_chunk_profile_mismatch")

    selected_embedding_model = qualification_receipt.get("selected_embedding_model")
    if selected_embedding_model != "Qwen/Qwen3-Embedding-0.6B":
        raise ValueError("ntd_production_receipt_embedding_model_mismatch")

    selected_embedding_revision = qualification_receipt.get("selected_embedding_model_revision")
    if (
        not isinstance(selected_embedding_revision, str)
        or not selected_embedding_revision
        or selected_embedding_revision == "latest"
    ):
        raise ValueError("ntd_production_receipt_embedding_revision_invalid")

    selected_embedding_digest = qualification_receipt.get("selected_embedding_model_digest")
    if (
        not isinstance(selected_embedding_digest, str)
        or not selected_embedding_digest.startswith("sha256:")
        or len(selected_embedding_digest) != 71
        or not all(c in "0123456789abcdef" for c in selected_embedding_digest[7:])
    ):
        raise ValueError("ntd_production_receipt_embedding_digest_invalid")

    selected_retrieval_profile = qualification_receipt.get("selected_retrieval_profile")
    if selected_retrieval_profile != "ntd-contextual-hybrid-hierarchical-graph-reranker@1.0.0":
        raise ValueError("ntd_production_receipt_retrieval_profile_mismatch")

    chunk_sql = sa.text(
        """
        SELECT chunk_profile_id
        FROM platform.ntd_chunk_profiles
        WHERE profile_key = 'ntd-contextual-chunks@1.0.0'
          AND profile_version = '1.0.0'
          AND qualification_status = 'qualified_primary'
        """
    )
    chunk_rows = connection.execute(chunk_sql).mappings().all()
    if len(chunk_rows) != 1:
        raise ValueError("ntd_production_chunk_profile_cardinality_invalid")
    chunk_profile_id = _uuid(chunk_rows[0]["chunk_profile_id"])

    embedding_sql = sa.text(
        """
        SELECT embedding_profile_id
        FROM platform.ntd_embedding_profiles
        WHERE model_id = :model_id
          AND model_revision = :revision
          AND model_digest = :digest
          AND status = 'qualified'
        """
    )
    embedding_rows = (
        connection.execute(
            embedding_sql,
            {
                "model_id": selected_embedding_model,
                "revision": selected_embedding_revision,
                "digest": selected_embedding_digest,
            },
        )
        .mappings()
        .all()
    )
    if len(embedding_rows) != 1:
        raise ValueError("ntd_production_embedding_profile_cardinality_invalid")
    embedding_profile_id = _uuid(embedding_rows[0]["embedding_profile_id"])

    return chunk_profile_id, embedding_profile_id


@dataclass(frozen=True, slots=True)
class CanonicalSearchDocument:
    corpus_object_id: uuid.UUID
    authority_class: str
    designation: str
    aliases: tuple[str, ...]
    title: str
    printed_edition: str | None
    artifact_digest: str
    source_version_id: uuid.UUID | None
    normative_document_id: uuid.UUID | None
    normative_edition_id: uuid.UUID | None
    normative_artifact_id: uuid.UUID | None
    bytes_present: bool
    terminal_status: str
    blocker_code: str | None
    pages_total: int
    pages_extracted: int
    pages_blocked: int
    structural_units: int
    contextual_chunks: int
    embeddings: int
    fts_indexed: bool
    hnsw_indexed: bool
    graph_indexed: bool


@dataclass(frozen=True, slots=True)
class CanonicalSearchPage:
    page_number: int
    normalized_text: str
    raw_transcription: str
    source_locator_id: uuid.UUID
    extraction_method: str
    terminal_outcome: str


def _uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _optional_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    return _uuid(value)


def _load_documents(connection: sa.Connection) -> tuple[CanonicalSearchDocument, ...]:
    cardinality_sql = sa.text(
        """
        SELECT COUNT(*)
        FROM platform.ntd_corpus_objects c
        WHERE c.authority_class <> 'gesn_candidate'
          AND (
              SELECT COUNT(*)
              FROM platform.ntd_document_processing_outcomes o
              WHERE o.corpus_object_id = c.corpus_object_id
                AND o.processing_profile_version = :profile
          ) = 1
        """
    )

    total_sql = sa.text(
        """
        SELECT COUNT(*)
        FROM platform.ntd_corpus_objects
        WHERE authority_class <> 'gesn_candidate'
        """
    )

    total_count = connection.execute(total_sql).scalar_one()
    valid_count = connection.execute(
        cardinality_sql, {"profile": PROCESSING_PROFILE_VERSION}
    ).scalar_one()

    if total_count != valid_count:
        raise ValueError("ntd_production_processing_outcome_cardinality")

    select_sql = sa.text(
        """
        SELECT
            c.corpus_object_id,
            c.authority_class,
            c.stable_designation AS designation,
            c.alternative_designations AS aliases,
            c.title,
            c.printed_edition,
            c.artifact_digest,
            c.source_version_id,
            c.normative_document_id,
            c.normative_edition_id,
            c.normative_artifact_id,
            c.bytes_status,
            o.terminal_status,
            o.blocker_code,
            o.pages_total,
            o.pages_extracted,
            o.pages_blocked,
            o.structural_units_count AS structural_units,
            o.contextual_chunks_count AS contextual_chunks,
            o.embeddings_count AS embeddings,
            o.fts_indexed,
            o.hnsw_indexed,
            o.typed_graph_indexed AS graph_indexed
        FROM platform.ntd_corpus_objects c
        JOIN platform.ntd_document_processing_outcomes o
            ON c.corpus_object_id = o.corpus_object_id
        WHERE c.authority_class <> 'gesn_candidate'
          AND o.processing_profile_version = :profile
        ORDER BY c.corpus_object_id
        """
    )

    rows = connection.execute(select_sql, {"profile": PROCESSING_PROFILE_VERSION}).mappings().all()

    documents: list[CanonicalSearchDocument] = []
    for row in rows:
        aliases_raw = row["aliases"]
        if aliases_raw is None:
            aliases = ()
        else:
            aliases = tuple(aliases_raw)

        doc = CanonicalSearchDocument(
            corpus_object_id=_uuid(row["corpus_object_id"]),
            authority_class=row["authority_class"],
            designation=row["designation"],
            aliases=aliases,
            title=row["title"],
            printed_edition=row["printed_edition"],
            artifact_digest=row["artifact_digest"],
            source_version_id=_optional_uuid(row["source_version_id"]),
            normative_document_id=_optional_uuid(row["normative_document_id"]),
            normative_edition_id=_optional_uuid(row["normative_edition_id"]),
            normative_artifact_id=_optional_uuid(row["normative_artifact_id"]),
            bytes_present=(row["bytes_status"] == "present_verified"),
            terminal_status=row["terminal_status"],
            blocker_code=row["blocker_code"],
            pages_total=row["pages_total"],
            pages_extracted=row["pages_extracted"],
            pages_blocked=row["pages_blocked"],
            structural_units=row["structural_units"],
            contextual_chunks=row["contextual_chunks"],
            embeddings=row["embeddings"],
            fts_indexed=row["fts_indexed"],
            hnsw_indexed=row["hnsw_indexed"],
            graph_indexed=row["graph_indexed"],
        )
        documents.append(doc)

    return tuple(documents)


def _load_pages(
    connection: sa.Connection, corpus_object_id: uuid.UUID
) -> tuple[CanonicalSearchPage, ...]:
    sql = sa.text(
        """
        SELECT
            p.page_number,
            p.normalized_text,
            p.raw_transcription,
            p.source_locator_id,
            p.extraction_method,
            p.terminal_outcome
        FROM platform.ntd_corpus_pages p
        WHERE p.corpus_object_id = :corpus_object_id
          AND NOT EXISTS (
              SELECT 1
              FROM platform.ntd_corpus_pages newer
              WHERE newer.corpus_page_id = p.corpus_page_id
                AND newer.version > p.version
          )
        ORDER BY p.page_number
        """
    )

    rows = connection.execute(sql, {"corpus_object_id": corpus_object_id}).mappings().all()

    pages: list[CanonicalSearchPage] = []
    seen_page_numbers: set[int] = set()

    for row in rows:
        page_number = row["page_number"]
        if page_number in seen_page_numbers:
            raise ValueError(f"Duplicate page number: {page_number}")
        seen_page_numbers.add(page_number)

        pages.append(
            CanonicalSearchPage(
                page_number=page_number,
                normalized_text=row["normalized_text"],
                raw_transcription=row["raw_transcription"],
                source_locator_id=_uuid(row["source_locator_id"]),
                extraction_method=row["extraction_method"],
                terminal_outcome=row["terminal_outcome"],
            )
        )

    return tuple(pages)


def _persist_canonical_document(
    connection: sa.Connection,
    document: CanonicalSearchDocument,
    pages: tuple[CanonicalSearchPage, ...],
) -> dict[str, Any]:
    if document.pages_total > 0:
        expected_numbers = list(range(1, document.pages_total + 1))
        actual_numbers = [page.page_number for page in pages]
        if actual_numbers != expected_numbers:
            raise ValueError("ntd_production_page_order_invalid")

    if document.authority_class in ("official", "official_binding_recovered", "legacy_reference"):
        authority_class = document.authority_class
    else:
        raise ValueError("ntd_production_authority_invalid")

    native_chars = 0
    ocr_chars = 0
    ocr_pages = 0
    has_non_native = False

    page_texts: list[str] = []
    page_locator_ids: list[uuid.UUID | None] = []

    for page in pages:
        text = page.normalized_text if page.normalized_text else page.raw_transcription
        page_texts.append(text)
        page_locator_ids.append(page.source_locator_id)

        if page.extraction_method in ("native", "deterministic_native"):
            native_chars += len(text)
        else:
            ocr_chars += len(text)
            ocr_pages += 1
            has_non_native = True

    if document.authority_class == "legacy_reference":
        extraction_method = "recovered_legacy_native_pdf"
    else:
        extraction_method = (
            "admitted_native_plus_ocr_pdf" if has_non_native else "admitted_native_pdf"
        )

    source_metadata = {
        "terminal_status": document.terminal_status,
        "blocker_code": document.blocker_code,
        "processing_profile_version": PROCESSING_PROFILE_VERSION,
    }

    return _persist_document(
        connection,
        authority_class=authority_class,
        identity=f"canonical:{document.corpus_object_id}",
        normative_document_id=document.normative_document_id,
        normative_edition_id=document.normative_edition_id,
        normative_artifact_id=document.normative_artifact_id,
        source_version_id=document.source_version_id,
        designation=document.designation,
        aliases=designation_aliases(document.designation),
        title=document.title,
        edition_label=document.printed_edition,
        artifact_digest=document.artifact_digest,
        bytes_present=document.bytes_present,
        inventoried_page_count=document.pages_total,
        pages=page_texts,
        native_text_characters=native_chars,
        ocr_page_count=ocr_pages,
        ocr_text_characters=ocr_chars,
        structured=document.structural_units,
        verified=0,
        origin_manifest_digest=None,
        href=None,
        extraction_method=extraction_method,
        corpus_object_id=document.corpus_object_id,
        source_metadata=source_metadata,
        page_locator_ids=page_locator_ids,
    )


def materialize_canonical_search_corpus(
    engine: Engine,
    *,
    expected_denominator: int = 118,
) -> NtdSearchBuildResult:
    if expected_denominator <= 0:
        raise ValueError("ntd_production_expected_denominator_invalid")

    with engine.begin() as connection:
        documents = _load_documents(connection)
        if len(documents) != expected_denominator:
            raise ValueError("ntd_production_document_count_mismatch")

        results: list[dict[str, Any]] = []
        for doc in documents:
            pages = _load_pages(connection, doc.corpus_object_id)
            result = _persist_canonical_document(connection, doc, pages)
            results.append(result)

        counters = {
            "document_count": len(results),
            "searchable_document_count": sum(r["search_status"] == "searchable" for r in results),
            "partially_searchable_document_count": sum(
                r["search_status"] == "partially_searchable" for r in results
            ),
            "document_without_text_count": sum(
                r["search_status"] == "not_searchable" for r in results
            ),
            "page_count": sum(int(r["page_count"]) for r in results),
            "searchable_page_count": sum(int(r["searchable_page_count"]) for r in results),
        }

        official_count = sum(
            1 for d in documents if d.authority_class in ("official", "official_binding_recovered")
        )
        reference_count = sum(1 for d in documents if d.authority_class == "legacy_reference")

        corpus_ids = [str(d.corpus_object_id) for d in documents]
        artifact_digests = [d.artifact_digest for d in documents]

        source_manifest_digests = {
            "canonical_processing_profile": PROCESSING_PROFILE_VERSION,
            "corpus_object_ids": semantic_digest(corpus_ids),
            "artifact_digests": semantic_digest(artifact_digests),
        }

        receipt_payload = {
            "profile_version": NTD_SEARCH_INDEX_PROFILE,
            "official_denominator": official_count,
            "reference_denominator": reference_count,
            **counters,
            "source_manifest_digests": source_manifest_digests,
        }

        fingerprint = semantic_digest(receipt_payload)
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_search_index_build_receipts("
                "build_receipt_id,profile_version,official_denominator,reference_denominator,"
                "document_count,searchable_document_count,partially_searchable_document_count,"
                "document_without_text_count,page_count,searchable_page_count,"
                "source_manifest_digests,build_fingerprint) VALUES ("
                ":id,:profile,:official,:reference,:documents,:searchable,:partial,:without_text,"
                ":pages,:searchable_pages,CAST(:manifests AS jsonb),:fingerprint) "
                "ON CONFLICT (build_fingerprint) DO NOTHING"
            ),
            {
                "id": deterministic_uuid(f"ntd-search-build:{fingerprint}"),
                "profile": NTD_SEARCH_INDEX_PROFILE,
                "official": official_count,
                "reference": reference_count,
                "documents": counters["document_count"],
                "searchable": counters["searchable_document_count"],
                "partial": counters["partially_searchable_document_count"],
                "without_text": counters["document_without_text_count"],
                "pages": counters["page_count"],
                "searchable_pages": counters["searchable_page_count"],
                "manifests": json.dumps(source_manifest_digests),
                "fingerprint": fingerprint,
            },
        )

    return NtdSearchBuildResult(
        official_count,
        reference_count,
        counters["document_count"],
        counters["searchable_document_count"],
        counters["partially_searchable_document_count"],
        counters["document_without_text_count"],
        counters["page_count"],
        counters["searchable_page_count"],
        fingerprint,
    )
