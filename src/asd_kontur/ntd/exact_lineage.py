"""Rebind accepted native NTD chunks to exact official source lineage.

This bridge is deliberately narrow.  It accepts a historical chunk only when
the artifact digest is byte-identical to a currently registered normative
artifact and every page covered by the chunk was extracted natively.  OCR or
model-derived text is not copied, and the operation never promotes extracted
text to normative authority or an executable rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid

EXACT_NATIVE_LINEAGE_PROFILE = "ntd-exact-native-lineage@1.0.0"


@dataclass(frozen=True, slots=True)
class ExactNativeLineageResult:
    exact_artifacts: int
    matched_historical_objects: int
    inserted_corpus_objects: int
    inserted_locators: int
    eligible_native_chunks: int
    inserted_chunks: int
    excluded_non_native_chunks: int


def reconcile_exact_native_lineage(
    historical_engine: Engine,
    target_engine: Engine,
    *,
    document_limit: int = 15,
    observed_at: datetime | None = None,
) -> ExactNativeLineageResult:
    """Append byte-exact, native-only historical chunks to the current corpus.

    The two databases must be trusted local ASD-KONTUR stores.  Matching is by
    SHA-256 content digest only.  Titles and designations are retained solely
    as display metadata and never participate in identity resolution.
    """

    if document_limit < 1:
        raise ValueError("ntd_exact_lineage_document_limit_invalid")
    now = observed_at or datetime.now(UTC)
    with target_engine.connect() as connection:
        artifacts = list(
            connection.execute(
                sa.text(
                    "SELECT artifact.normative_artifact_id,artifact.content_digest,"
                    "artifact.size_bytes,artifact.media_type,artifact.source_version_id,"
                    "source.source_artifact_id,artifact.normative_edition_id,"
                    "edition.normative_document_id,document.designation,document.title "
                    "FROM platform.normative_artifacts artifact JOIN platform.source_versions "
                    "source ON source.source_version_id=artifact.source_version_id JOIN "
                    "platform.normative_editions edition ON edition.normative_edition_id="
                    "artifact.normative_edition_id JOIN platform.normative_documents document "
                    "ON document.normative_document_id=edition.normative_document_id "
                    "ORDER BY artifact.registered_at,artifact.normative_artifact_id LIMIT :limit"
                ),
                {"limit": document_limit},
            ).mappings()
        )
    if not artifacts:
        return ExactNativeLineageResult(0, 0, 0, 0, 0, 0, 0)

    digests = [str(row["content_digest"]) for row in artifacts]
    with historical_engine.connect() as connection:
        historical_objects = {
            str(row["artifact_digest"]): row
            for row in connection.execute(
                sa.text(
                    "SELECT corpus_object_id,artifact_digest,logical_document_key,"
                    "stable_designation,alternative_designations,title,printed_edition,"
                    "original_paths,recovered_paths,provenance,corpus_profile_version,"
                    "corpus_fingerprint FROM platform.ntd_corpus_objects WHERE "
                    "artifact_digest=ANY(:digests) AND terminal_outcome='admitted'"
                ),
                {"digests": digests},
            ).mappings()
        }

    matched = [row for row in artifacts if str(row["content_digest"]) in historical_objects]
    inserted_objects = 0
    inserted_locators = 0
    eligible_chunks = 0
    inserted_chunks = 0
    excluded_chunks = 0
    for target in matched:
        historical = historical_objects[str(target["content_digest"])]
        corpus_id = deterministic_uuid(f"ntd-corpus-object:{target['content_digest']}")
        provenance = {
            "profile": EXACT_NATIVE_LINEAGE_PROFILE,
            "identity_basis": "exact_sha256_content_digest",
            "historical_corpus_object_id": str(historical["corpus_object_id"]),
            "historical_corpus_fingerprint": str(historical["corpus_fingerprint"]),
            "historical_profile": str(historical["corpus_profile_version"]),
            "content_scope": "native_complete_pages_only",
            "authority_effect": "none",
            "observed_at": now.isoformat(),
        }
        corpus_fingerprint = semantic_digest(
            {
                "profile": EXACT_NATIVE_LINEAGE_PROFILE,
                "artifact_digest": target["content_digest"],
                "source_version_id": str(target["source_version_id"]),
                "normative_artifact_id": str(target["normative_artifact_id"]),
                "historical_corpus_fingerprint": historical["corpus_fingerprint"],
            }
        )
        with target_engine.begin() as connection:
            result = connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_corpus_objects(corpus_object_id,artifact_digest,"
                    "size_bytes,media_type,authority_class,logical_document_key,"
                    "stable_designation,alternative_designations,title,printed_edition,"
                    "source_artifact_id,source_version_id,normative_document_id,"
                    "normative_edition_id,normative_artifact_id,original_paths,recovered_paths,"
                    "duplicate_representation_digests,provenance,bytes_status,"
                    "edition_currency_status,terminal_outcome,blocker_code,"
                    "corpus_profile_version,corpus_fingerprint,recorded_at) VALUES "
                    "(:id,:digest,:size,:media,'official_binding_recovered',:logical,"
                    ":designation,:aliases,:title,:edition,:source_artifact,:source_version,"
                    ":document,:normative_edition,:normative_artifact,CAST(:original AS jsonb),"
                    "CAST(:recovered AS jsonb),'[]'::jsonb,CAST(:provenance AS jsonb),"
                    "'present_verified','not_checked','admitted',NULL,:profile,:fingerprint,:now) "
                    "ON CONFLICT (artifact_digest) DO NOTHING"
                ),
                {
                    "id": corpus_id,
                    "digest": target["content_digest"],
                    "size": target["size_bytes"],
                    "media": target["media_type"],
                    "logical": str(target["normative_document_id"]),
                    "designation": target["designation"],
                    "aliases": list(historical["alternative_designations"] or []),
                    "title": target["title"],
                    "edition": historical["printed_edition"],
                    "source_artifact": target["source_artifact_id"],
                    "source_version": target["source_version_id"],
                    "document": target["normative_document_id"],
                    "normative_edition": target["normative_edition_id"],
                    "normative_artifact": target["normative_artifact_id"],
                    "original": json.dumps([], ensure_ascii=False),
                    "recovered": json.dumps([], ensure_ascii=False),
                    "provenance": json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                    "profile": EXACT_NATIVE_LINEAGE_PROFILE,
                    "fingerprint": corpus_fingerprint,
                    "now": now,
                },
            )
            inserted_objects += int(getattr(result, "rowcount", 0) or 0)

        with historical_engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "WITH latest_pages AS (SELECT DISTINCT ON (page_number) page_number,"
                        "terminal_outcome FROM platform.ntd_corpus_pages WHERE corpus_object_id="
                        ":corpus ORDER BY page_number,version DESC), eligible AS (SELECT chunk.* "
                        "FROM platform.ntd_chunks chunk WHERE chunk.corpus_object_id=:corpus AND "
                        "NOT EXISTS (SELECT 1 FROM generate_series(chunk.page_start,"
                        "chunk.page_end) "
                        "page LEFT JOIN latest_pages state ON state.page_number=page WHERE "
                        "state.terminal_outcome IS DISTINCT FROM 'native_complete')) SELECT "
                        "eligible.*,ARRAY(SELECT locator.locator_key FROM unnest("
                        "eligible.source_locator_ids) WITH ORDINALITY ids(id,ordinality) JOIN "
                        "platform.source_locators locator ON locator.source_locator_id=ids.id "
                        "ORDER BY ids.ordinality) locator_keys FROM eligible ORDER BY "
                        "ordinal,version"
                    ),
                    {"corpus": historical["corpus_object_id"]},
                ).mappings()
            )
            all_count = int(
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM platform.ntd_chunks WHERE corpus_object_id=:corpus"
                    ),
                    {"corpus": historical["corpus_object_id"]},
                )
                or 0
            )
        eligible_chunks += len(rows)
        excluded_chunks += all_count - len(rows)
        previous_by_path: dict[str, UUID] = {}
        for row in rows:
            locator_ids: list[UUID] = []
            for key in row["locator_keys"]:
                locator_id = deterministic_uuid(
                    f"ntd-corpus-page-locator:{target['source_version_id']}:{str(key).split(':')[-1]}"
                )
                with target_engine.begin() as connection:
                    locator_result = connection.execute(
                        sa.text(
                            "INSERT INTO platform.source_locators(source_locator_id,"
                            "source_version_id,locator_kind,locator_key,locator_value,"
                            "fragment_digest) "
                            "VALUES (:id,:source,'normative_corpus_page',:key,"
                            "CAST(:value AS jsonb),NULL) ON CONFLICT "
                            "(source_version_id,locator_kind,locator_key) DO NOTHING"
                        ),
                        {
                            "id": locator_id,
                            "source": target["source_version_id"],
                            "key": key,
                            "value": json.dumps({"page_number": int(str(key).split(":")[-1])}),
                        },
                    )
                inserted_locators += int(getattr(locator_result, "rowcount", 0) or 0)
                locator_ids.append(locator_id)
            chunk_id = deterministic_uuid(
                f"ntd-chunk:{target['source_version_id']}:{row['ordinal']}:"
                f"{row['normalized_text_digest']}:{row['chunking_profile_version']}"
            )
            fingerprint = semantic_digest(
                {
                    "chunk_id": str(chunk_id),
                    "source": str(target["source_version_id"]),
                    "pages": [int(row["page_start"]), int(row["page_end"])],
                    "path": row["structural_path"],
                    "raw": row["raw_text_digest"],
                    "normalized": row["normalized_text_digest"],
                    "profile": row["chunking_profile_version"],
                }
            )
            continuation = previous_by_path.get(str(row["structural_path"]))
            with target_engine.begin() as connection:
                chunk_result = connection.execute(
                    sa.text(
                        "INSERT INTO platform.ntd_chunks(chunk_id,version,corpus_object_id,"
                        "source_version_id,normative_document_id,normative_edition_id,"
                        "authority_class,ordinal,page_start,page_end,structural_path,"
                        "source_locator_ids,raw_text,normalized_text,raw_text_digest,"
                        "normalized_text_digest,chunking_profile_version,parent_chunk_id,"
                        "continuation_of_chunk_id,chunk_fingerprint,recorded_at,"
                        "supersedes_version) "
                        "VALUES (:id,:version,:corpus,:source,:document,:edition,"
                        "'official_binding_recovered',:ordinal,:start,:end,:path,:locators,:raw,"
                        ":normalized,:raw_digest,:normalized_digest,:profile,NULL,:continuation,"
                        ":fingerprint,:now,NULL) ON CONFLICT (chunk_fingerprint) DO NOTHING"
                    ),
                    {
                        "id": chunk_id,
                        "version": row["version"],
                        "corpus": corpus_id,
                        "source": target["source_version_id"],
                        "document": target["normative_document_id"],
                        "edition": target["normative_edition_id"],
                        "ordinal": row["ordinal"],
                        "start": row["page_start"],
                        "end": row["page_end"],
                        "path": row["structural_path"],
                        "locators": locator_ids,
                        "raw": row["raw_text"],
                        "normalized": row["normalized_text"],
                        "raw_digest": row["raw_text_digest"],
                        "normalized_digest": row["normalized_text_digest"],
                        "profile": row["chunking_profile_version"],
                        "continuation": continuation,
                        "fingerprint": fingerprint,
                        "now": now,
                    },
                )
            inserted_chunks += int(getattr(chunk_result, "rowcount", 0) or 0)
            previous_by_path[str(row["structural_path"])] = chunk_id

    return ExactNativeLineageResult(
        len(artifacts),
        len(matched),
        inserted_objects,
        inserted_locators,
        eligible_chunks,
        inserted_chunks,
        excluded_chunks,
    )
