from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import Connection

from asd_kontur.ntd.production_embedding import EmbeddingProfile


@dataclass(frozen=True, slots=True)
class ProductionRetrievalHit:
    corpus_object_id: uuid.UUID
    contextual_chunk_id: uuid.UUID
    designation: str
    title: str
    authority_class: str
    page_start: int
    page_end: int
    structural_path: str
    text: str
    source_locator_ids: tuple[uuid.UUID, ...]
    lexical_rank: int | None
    lexical_score: float | None
    dense_rank: int | None
    dense_similarity: float | None
    final_score: float
    ranking_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Profile:
    retrieval_profile_id: uuid.UUID
    embedding_profile_id: uuid.UUID
    embedding: EmbeddingProfile
    chunk_profile_id: uuid.UUID
    min_relevance: float


def _load_profile(connection: Connection) -> _Profile:
    query = sa.text(
        """
        SELECT
            rp.retrieval_profile_id,
            rp.embedding_profile_id,
            rp.chunk_profile_id,
            ep.profile_key,
            ep.profile_version,
            ep.dimension,
            rp.parameters
        FROM platform.ntd_retrieval_profiles rp
        JOIN platform.ntd_embedding_profiles ep
            ON rp.embedding_profile_id = ep.embedding_profile_id
        WHERE rp.status = 'qualified_primary'
          AND ep.status = 'qualified'
        """
    )
    result = connection.execute(query).mappings().all()
    if len(result) != 1:
        raise ValueError("ntd_production_retrieval_profile_cardinality_invalid")

    row = result[0]

    try:
        retrieval_profile_id = uuid.UUID(str(row["retrieval_profile_id"]))
    except (ValueError, TypeError) as e:
        raise ValueError("ntd_production_retrieval_invalid_retrieval_profile_id") from e

    try:
        embedding_profile_id = uuid.UUID(str(row["embedding_profile_id"]))
    except (ValueError, TypeError) as e:
        raise ValueError("ntd_production_retrieval_invalid_embedding_profile_id") from e

    try:
        chunk_profile_id = uuid.UUID(str(row["chunk_profile_id"]))
    except (ValueError, TypeError) as e:
        raise ValueError("ntd_production_retrieval_invalid_chunk_profile_id") from e

    profile_key = row["profile_key"]
    if not isinstance(profile_key, str) or not profile_key:
        raise ValueError("ntd_production_retrieval_invalid_profile_key")

    profile_version = row["profile_version"]
    if not isinstance(profile_version, str) or not profile_version:
        raise ValueError("ntd_production_retrieval_invalid_profile_version")

    dimension = row["dimension"]
    if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension <= 0:
        raise ValueError("ntd_production_retrieval_invalid_dimension")

    parameters = row["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("ntd_production_retrieval_invalid_parameters")

    min_relevance = parameters.get("min_relevance")
    if not isinstance(min_relevance, (int, float)) or isinstance(min_relevance, bool):
        raise ValueError("ntd_production_retrieval_invalid_min_relevance_type")
    if not (0 <= min_relevance <= 1):
        raise ValueError("ntd_production_retrieval_invalid_min_relevance_range")

    embedding = EmbeddingProfile(
        key=profile_key,
        version=profile_version,
        dimension=dimension,
    )

    return _Profile(
        retrieval_profile_id=retrieval_profile_id,
        embedding_profile_id=embedding_profile_id,
        embedding=embedding,
        chunk_profile_id=chunk_profile_id,
        min_relevance=float(min_relevance),
    )


def _normalized_relevance(lexical_score: float | None, dense_similarity: float | None) -> float:
    if lexical_score is not None and dense_similarity is not None:
        return (lexical_score + dense_similarity) / 2.0
    if lexical_score is not None:
        return lexical_score
    if dense_similarity is not None:
        return dense_similarity
    return 0.0


def _vector_literal(vector: tuple[float, ...]) -> str:
    return json.dumps(list(vector), separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class _FusedCandidate:
    corpus_object_id: uuid.UUID
    lexical_rank: int | None
    dense_rank: int | None
    fused_score: float
    ranking_reasons: tuple[str, ...]


def _validate_query(query: str, limit: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("ntd_production_query_invalid_query")
    if len(query) > 1000:
        raise ValueError("ntd_production_query_too_long")
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("ntd_production_query_invalid_limit_type")
    if not (1 <= limit <= 50):
        raise ValueError("ntd_production_query_invalid_limit_range")


def _reciprocal_rank_fusion(
    lexical: tuple[uuid.UUID, ...],
    dense: tuple[uuid.UUID, ...],
    k: int,
) -> tuple[_FusedCandidate, ...]:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("ntd_production_rrf_invalid_k")
    scores: dict[uuid.UUID, float] = {}
    ranks: dict[uuid.UUID, tuple[int | None, int | None]] = {}
    for uid in lexical:
        ranks[uid] = (ranks.get(uid, (None, None))[0], None)
    for rank, uid in enumerate(lexical, start=1):
        scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank)
        ranks[uid] = (rank, ranks.get(uid, (None, None))[1])
    for rank, uid in enumerate(dense, start=1):
        scores[uid] = scores.get(uid, 0.0) + 1.0 / (k + rank)
        ranks[uid] = (ranks.get(uid, (None, None))[0], rank)
    sorted_items = sorted(scores.items(), key=lambda x: (-x[1], str(x[0])))
    return tuple(
        _FusedCandidate(
            corpus_object_id=uid,
            lexical_rank=ranks[uid][0],
            dense_rank=ranks[uid][1],
            fused_score=score,
            ranking_reasons=("rrf",),
        )
        for uid, score in sorted_items
    )


def _should_abstain(
    candidates: tuple[_FusedCandidate, ...],
    min_relevance: float,
) -> bool:
    if not isinstance(min_relevance, (int, float)) or isinstance(min_relevance, bool):
        raise ValueError("ntd_production_abstain_invalid_min_relevance_type")
    if not (0 <= min_relevance <= 1):
        raise ValueError("ntd_production_abstain_invalid_min_relevance_range")
    if not candidates:
        return True
    return all(c.fused_score < min_relevance for c in candidates)


@dataclass(frozen=True, slots=True)
class _LexicalCandidate:
    corpus_object_id: uuid.UUID
    contextual_chunk_id: uuid.UUID
    lexical_score: float
    rank: int


def _load_lexical_candidates(
    connection: Connection,
    profile: _Profile,
    query: str,
    candidate_limit: int,
) -> tuple[_LexicalCandidate, ...]:
    if not isinstance(candidate_limit, int) or isinstance(candidate_limit, bool):
        raise ValueError("ntd_production_lexical_invalid_candidate_limit_type")
    if not (1 <= candidate_limit <= 200):
        raise ValueError("ntd_production_lexical_invalid_candidate_limit_range")

    sql = sa.text(
        """
        SELECT
            c.corpus_object_id,
            cc.contextual_chunk_id,
            ts_rank_cd(cc.lexical_vector, websearch_to_tsquery('russian', :query)) AS lexical_score,
            ROW_NUMBER() OVER (
                ORDER BY
                    ts_rank_cd(cc.lexical_vector, websearch_to_tsquery('russian', :query)) DESC,
                    cc.contextual_chunk_id ASC
            ) AS rank
        FROM platform.ntd_contextual_chunks cc
        JOIN platform.ntd_chunks c ON cc.chunk_id = c.chunk_id AND cc.chunk_version = c.version
        WHERE cc.chunk_profile_id = :chunk_profile_id
          AND cc.lexical_vector @@ websearch_to_tsquery('russian', :query)
        ORDER BY rank ASC
        LIMIT :limit
        """
    )

    rows = (
        connection.execute(
            sql,
            {
                "query": query,
                "chunk_profile_id": profile.chunk_profile_id,
                "limit": candidate_limit,
            },
        )
        .mappings()
        .all()
    )

    return tuple(
        _LexicalCandidate(
            corpus_object_id=uuid.UUID(str(row["corpus_object_id"])),
            contextual_chunk_id=uuid.UUID(str(row["contextual_chunk_id"])),
            lexical_score=float(row["lexical_score"]),
            rank=int(row["rank"]),
        )
        for row in rows
    )


@dataclass(frozen=True, slots=True)
class _DenseCandidate:
    corpus_object_id: uuid.UUID
    contextual_chunk_id: uuid.UUID
    similarity: float
    rank: int


def _load_dense_candidates(
    connection: Connection,
    profile: _Profile,
    query_vector: tuple[float, ...],
    candidate_limit: int,
) -> tuple[_DenseCandidate, ...]:
    if not isinstance(candidate_limit, int) or isinstance(candidate_limit, bool):
        raise ValueError("ntd_production_dense_invalid_candidate_limit_type")
    if not (1 <= candidate_limit <= 200):
        raise ValueError("ntd_production_dense_invalid_candidate_limit_range")
    if len(query_vector) != profile.embedding.dimension:
        raise ValueError("ntd_production_dense_invalid_query_vector_dimension")

    vector_literal = _vector_literal(query_vector)

    sql = sa.text(
        """
        SELECT
            c.corpus_object_id,
            cc.contextual_chunk_id,
            1 - (e.embedding <=> CAST(:query_vector AS vector)) AS similarity,
            ROW_NUMBER() OVER (
                ORDER BY
                    e.embedding <=> CAST(:query_vector AS vector) ASC,
                    cc.contextual_chunk_id ASC
            ) AS rank
        FROM platform.ntd_chunk_embeddings e
        JOIN platform.ntd_contextual_chunks cc
            ON e.contextual_chunk_id = cc.contextual_chunk_id
            AND e.contextual_chunk_version = cc.version
        JOIN platform.ntd_chunks c ON cc.chunk_id = c.chunk_id AND cc.chunk_version = c.version
        WHERE e.embedding_profile_id = :embedding_profile_id
          AND cc.chunk_profile_id = :chunk_profile_id
        ORDER BY rank ASC
        LIMIT :limit
        """
    )

    rows = (
        connection.execute(
            sql,
            {
                "query_vector": vector_literal,
                "embedding_profile_id": profile.embedding_profile_id,
                "chunk_profile_id": profile.chunk_profile_id,
                "limit": candidate_limit,
            },
        )
        .mappings()
        .all()
    )

    return tuple(
        _DenseCandidate(
            corpus_object_id=uuid.UUID(str(row["corpus_object_id"])),
            contextual_chunk_id=uuid.UUID(str(row["contextual_chunk_id"])),
            similarity=float(row["similarity"]),
            rank=int(row["rank"]),
        )
        for row in rows
    )
