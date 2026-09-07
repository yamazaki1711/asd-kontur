from __future__ import annotations

import uuid

import pytest

from asd_kontur.ntd.production_query import (
    _DenseCandidate,
    _extract_ntd_designation,
    _FusedCandidate,
    _LexicalCandidate,
    _reciprocal_rank_fusion,
    _should_abstain,
    _validate_query,
)

UUID_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
UUID_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
UUID_C = uuid.UUID("33333333-3333-3333-3333-333333333333")


@pytest.mark.parametrize(
    "query, limit, expected_error",
    [
        ("valid query", 10, None),
        ("", 10, "ntd_production_query_invalid_query"),
        ("a" * 1001, 10, "ntd_production_query_too_long"),
        ("valid query", 0, "ntd_production_query_invalid_limit_range"),
        ("valid query", 51, "ntd_production_query_invalid_limit_range"),
        ("valid query", True, "ntd_production_query_invalid_limit_type"),
    ],
)
def test_validate_query(query: str, limit: int, expected_error: str | None) -> None:
    if expected_error is None:
        _validate_query(query, limit)
    else:
        with pytest.raises(ValueError, match=expected_error):
            _validate_query(query, limit)


def test_extract_ntd_designation() -> None:
    expected_prefix = chr(0x0441) + chr(0x043F)
    assert _extract_ntd_designation("SP70") == expected_prefix + "70"
    assert _extract_ntd_designation("GOST R 51872-2024") is not None
    assert _extract_ntd_designation("ordinary concrete works") is None


def test_rrf_fusion_same_corpus() -> None:
    lexical = (
        _LexicalCandidate(
            corpus_object_id=UUID_A,
            contextual_chunk_id=UUID_B,
            lexical_score=0.9,
            rank=1,
        ),
        _LexicalCandidate(
            corpus_object_id=UUID_A,
            contextual_chunk_id=UUID_C,
            lexical_score=0.8,
            rank=2,
        ),
    )
    dense = (
        _DenseCandidate(
            corpus_object_id=UUID_A,
            contextual_chunk_id=UUID_B,
            similarity=0.95,
            rank=2,
        ),
    )
    results = _reciprocal_rank_fusion(lexical, dense, 60)
    assert len(results) == 2
    first = results[0]
    assert first.contextual_chunk_id == UUID_B
    assert first.lexical_rank == 1
    assert first.dense_rank == 2
    assert first.lexical_score == 0.9
    assert first.dense_similarity == 0.95
    assert first.fused_score == pytest.approx(1 / 61 + 1 / 62)
    assert first.ranking_reasons == ("lexical_rank:1", "dense_rank:2")
    second = results[1]
    assert second.contextual_chunk_id == UUID_C
    assert second.dense_rank is None
    assert second.dense_similarity is None


@pytest.mark.parametrize(
    "candidates, min_relevance, expected",
    [
        ((), 0.5, True),
        (
            (
                _FusedCandidate(
                    corpus_object_id=UUID_A,
                    contextual_chunk_id=UUID_B,
                    lexical_rank=1,
                    lexical_score=0.7,
                    dense_rank=1,
                    dense_similarity=0.8,
                    fused_score=0.1,
                    ranking_reasons=("rrf",),
                ),
            ),
            0.5,
            True,
        ),
        (
            (
                _FusedCandidate(
                    corpus_object_id=UUID_A,
                    contextual_chunk_id=UUID_B,
                    lexical_rank=1,
                    lexical_score=0.7,
                    dense_rank=1,
                    dense_similarity=0.8,
                    fused_score=0.6,
                    ranking_reasons=("rrf",),
                ),
            ),
            0.5,
            False,
        ),
    ],
)
def test_should_abstain(
    candidates: tuple[_FusedCandidate, ...],
    min_relevance: float,
    expected: bool,
) -> None:
    assert _should_abstain(candidates, min_relevance) is expected


def test_invalid_parameters() -> None:
    lexical_candidate = _LexicalCandidate(
        corpus_object_id=UUID_A,
        contextual_chunk_id=UUID_B,
        lexical_score=0.9,
        rank=1,
    )
    dense_candidate = _DenseCandidate(
        corpus_object_id=UUID_A,
        contextual_chunk_id=UUID_B,
        similarity=0.9,
        rank=1,
    )
    with pytest.raises(ValueError, match="ntd_production_rrf_invalid_k"):
        _reciprocal_rank_fusion((lexical_candidate,), (dense_candidate,), 0)

    for invalid_min_relevance in (-0.1, 1.1):
        with pytest.raises(ValueError, match="ntd_production_abstain_invalid_min_relevance_range"):
            _should_abstain((), invalid_min_relevance)
