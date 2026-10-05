import uuid
from dataclasses import replace

import pytest
import sqlalchemy as sa

import asd_kontur.ntd.processing_outcomes as outcomes
from asd_kontur.ntd.processing_outcomes import PhysicalProcessingRow

from .conftest import PostgreSQLEnvironment


@pytest.mark.postgres
def test_ntd_processing_outcome_materialization(
    postgres_environment: PostgreSQLEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = postgres_environment.owner_engine
    corpus_object_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
    profile_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO platform.ntd_corpus_objects (
                    corpus_object_id, artifact_digest, size_bytes, media_type,
                    authority_class, logical_document_key, stable_designation,
                    alternative_designations, title, original_paths,
                    recovered_paths, duplicate_representation_digests,
                    provenance, bytes_status, edition_currency_status,
                    terminal_outcome, blocker_code, corpus_profile_version,
                    corpus_fingerprint
                ) VALUES (
                    :id, :digest, 1024, 'application/pdf', 'legacy_reference',
                    'doc-key', 'stable', ARRAY[]::text[], 'Title',
                    CAST('[]' AS jsonb), CAST('[]' AS jsonb),
                    CAST('[]' AS jsonb), CAST(:prov AS jsonb),
                    'not_locally_available', 'not_checked',
                    'blocked_bytes_unavailable', 'SOURCE_MISSING',
                    'test-processing@1.0.0', :fingerprint
                )
                """
            ),
            {
                "id": corpus_object_id,
                "digest": "sha256:" + "a" * 64,
                "prov": "{}",
                "fingerprint": "sha256:" + "b" * 64,
            },
        )

    physical_row = PhysicalProcessingRow(
        corpus_object_id=corpus_object_id,
        admission_outcome="blocked",
        bytes_status="not_locally_available",
        source_blocker="SOURCE_MISSING",
        pages_total=0,
        extracted_pages=0,
        blank_pages=0,
        blocked_pages=0,
        has_pdf_structure_invalid=False,
        page_blocker_codes=(),
        structural_units_total=0,
        contextual_chunks_total=0,
        embedded_chunks_total=0,
        graph_nodes_total=0,
        fts_index_available=False,
        hnsw_index_available=False,
    )

    def mock_load(
        engine_arg: sa.Engine, profile_arg: uuid.UUID
    ) -> tuple[PhysicalProcessingRow, ...]:
        assert engine_arg is engine
        assert profile_arg == profile_id
        return (physical_row,)

    monkeypatch.setattr(outcomes, "load_physical_outcome_rows", mock_load)

    summary1 = outcomes.materialize_processing_outcomes(engine, profile_id)
    summary2 = outcomes.materialize_processing_outcomes(engine, profile_id)

    assert summary1 == summary2
    assert summary1.total == 1
    assert summary1.blocked_source == 1

    with engine.connect() as conn:
        result = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM platform.ntd_document_processing_outcomes "
                "WHERE corpus_object_id = :id"
            ),
            {"id": corpus_object_id},
        )
        count = result.scalar_one()
        assert count == 1

    changed_row = replace(physical_row, source_blocker="DIFFERENT_BLOCKER")

    def mock_load_conflict(
        engine_arg: sa.Engine, profile_arg: uuid.UUID
    ) -> tuple[PhysicalProcessingRow, ...]:
        assert engine_arg is engine
        assert profile_arg == profile_id
        return (changed_row,)

    monkeypatch.setattr(outcomes, "load_physical_outcome_rows", mock_load_conflict)

    with pytest.raises(ValueError, match="ntd_processing_outcome_conflict"):
        outcomes.materialize_processing_outcomes(engine, profile_id)

    with pytest.raises(sa.exc.DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE platform.ntd_document_processing_outcomes "
                    "SET blocker_code = 'X' WHERE corpus_object_id = :id"
                ),
                {"id": corpus_object_id},
            )

    with engine.connect() as conn:
        select_priv = conn.execute(
            sa.text(
                "SELECT has_table_privilege('public', "
                "'platform.ntd_document_processing_outcomes', 'SELECT')"
            )
        ).scalar_one()
        assert select_priv is False

        insert_priv = conn.execute(
            sa.text(
                "SELECT has_table_privilege('public', "
                "'platform.ntd_document_processing_outcomes', 'INSERT')"
            )
        ).scalar_one()
        assert insert_priv is False
