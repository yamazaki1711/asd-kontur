from __future__ import annotations

import uuid

import pytest

from asd_kontur.ntd.production_query import (
    _FusedCandidate,
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


@pytest.mark.parametrize(
    "lexical, dense, k, expected_scores",
    [
        (
            (UUID_A, UUID_B),
            (UUID_B, UUID_C),
            60,
            {UUID_B: 1 / 62 + 1 / 61, UUID_A: 1 / 61, UUID_C: 1 / 62},
        ),
        (
            (UUID_A,),
            (UUID_A,),
            10,
            {UUID_A: 1 / 11 + 1 / 11},
        ),
    ],
)
def test_rrf_fusion(
    lexical: tuple[uuid.UUID, ...],
    dense: tuple[uuid.UUID, ...],
    k: int,
    expected_scores: dict[uuid.UUID, float],
) -> None:
    result = _reciprocal_rank_fusion(lexical, dense, k)
    assert len(result) == len(expected_scores)
    for candidate in result:
        assert candidate.fused_score == pytest.approx(expected_scores[candidate.corpus_object_id])
        assert candidate.ranking_reasons == ("rrf",)


@pytest.mark.parametrize(
    "candidates, min_relevance, expected",
    [
        ((), 0.5, True),
        (
            (_FusedCandidate(UUID_A, 1, 1, 0.1, ("rrf",)),),
            0.5,
            True,
        ),
        (
            (_FusedCandidate(UUID_A, 1, 1, 0.6, ("rrf",)),),
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
    with pytest.raises(ValueError, match="ntd_production_rrf_invalid_k"):
        _reciprocal_rank_fusion((UUID_A,), (UUID_A,), 0)

    for invalid_min_relevance in (-0.1, 1.1):
        with pytest.raises(ValueError, match="ntd_production_abstain_invalid_min_relevance_range"):
            _should_abstain((), invalid_min_relevance)
