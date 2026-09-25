import uuid
from dataclasses import replace

import pytest

from asd_kontur.ntd.processing_outcomes import (
    PhysicalProcessingRow,
    _build_materialized_outcome,
    classify_processing_row,
)


def _complete_row() -> PhysicalProcessingRow:
    return PhysicalProcessingRow(
        corpus_object_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        admission_outcome="admitted",
        bytes_status="present_verified",
        source_blocker=None,
        pages_total=10,
        extracted_pages=10,
        blank_pages=0,
        blocked_pages=0,
        has_pdf_structure_invalid=False,
        page_blocker_codes=(),
        structural_units_total=5,
        contextual_chunks_total=20,
        embedded_chunks_total=20,
        graph_nodes_total=5,
        fts_index_available=True,
        hnsw_index_available=True,
    )


class TestClassifyProcessingRow:
    def test_complete_document(self) -> None:
        row = _complete_row()
        status, blocker = classify_processing_row(row)
        assert status == "indexed_complete"
        assert blocker is None

    def test_partial_blocked_page(self) -> None:
        row = replace(
            _complete_row(),
            extracted_pages=9,
            blocked_pages=1,
            page_blocker_codes=("page_error",),
        )
        status, blocker = classify_processing_row(row)
        assert status == "indexed_partial"
        assert blocker == "page_error;blocked_pages"

    def test_blocked_extraction_zero_chunks(self) -> None:
        row = replace(
            _complete_row(),
            contextual_chunks_total=0,
            embedded_chunks_total=0,
            structural_units_total=0,
            graph_nodes_total=0,
        )
        status, blocker = classify_processing_row(row)
        assert status == "blocked_extraction"
        assert blocker == "zero_chunks"

    def test_unsupported_pdf(self) -> None:
        row = replace(_complete_row(), has_pdf_structure_invalid=True)
        status, blocker = classify_processing_row(row)
        assert status == "unsupported_content"
        assert blocker == "pdf_structure_invalid"

    def test_blocked_source(self) -> None:
        row = replace(_complete_row(), admission_outcome="rejected")
        status, blocker = classify_processing_row(row)
        assert status == "blocked_source"
        assert blocker == "source_not_admitted_or_bytes_unavailable"

    def test_invalid_negative_metric(self) -> None:
        row = replace(_complete_row(), pages_total=-1)
        with pytest.raises(ValueError, match="ntd_processing_metrics_invalid"):
            classify_processing_row(row)

    def test_embeddings_greater_than_chunks(self) -> None:
        row = replace(
            _complete_row(),
            contextual_chunks_total=10,
            embedded_chunks_total=11,
        )
        with pytest.raises(ValueError, match="ntd_processing_metrics_invalid"):
            classify_processing_row(row)


class TestBuildMaterializedOutcome:
    def test_indexed_booleans_and_fingerprint(self) -> None:
        row = _complete_row()
        profile_id = uuid.UUID("87654321-4321-8765-4321-876543218765")
        outcome = _build_materialized_outcome(row, profile_id)

        assert outcome.status == "indexed_complete"
        assert outcome.blocker is None
        assert outcome.fts_indexed is True
        assert outcome.hnsw_indexed is True
        assert outcome.typed_graph_indexed is True
        assert outcome.gateway_registered is True

        outcome2 = _build_materialized_outcome(row, profile_id)
        assert outcome.fingerprint == outcome2.fingerprint
        assert outcome.outcome_id == outcome2.outcome_id

    def test_blocked_row_booleans(self) -> None:
        row = replace(
            _complete_row(),
            admission_outcome="rejected",
            contextual_chunks_total=0,
            embedded_chunks_total=0,
            structural_units_total=0,
            graph_nodes_total=0,
        )
        profile_id = uuid.UUID("87654321-4321-8765-4321-876543218765")
        outcome = _build_materialized_outcome(row, profile_id)

        assert outcome.status == "blocked_source"
        assert outcome.fts_indexed is False
        assert outcome.hnsw_indexed is False
        assert outcome.typed_graph_indexed is False
        assert outcome.gateway_registered is False

    def test_stable_uuid_for_same_corpus(self) -> None:
        corpus_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        row1 = replace(_complete_row(), corpus_object_id=corpus_id)
        row2 = replace(_complete_row(), corpus_object_id=corpus_id)
        profile_id = uuid.UUID("87654321-4321-8765-4321-876543218765")

        outcome1 = _build_materialized_outcome(row1, profile_id)
        outcome2 = _build_materialized_outcome(row2, profile_id)

        assert outcome1.outcome_id == outcome2.outcome_id
