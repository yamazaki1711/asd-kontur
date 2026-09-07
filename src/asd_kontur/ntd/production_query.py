from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import Connection

from asd_kontur.ntd.production_embedding import EmbeddingProfile, embed_query


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
    contextual_chunk_id: uuid.UUID
    lexical_rank: int | None
    lexical_score: float | None
    dense_rank: int | None
    dense_similarity: float | None
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
    lexical: tuple[_LexicalCandidate, ...],
    dense: tuple[_DenseCandidate, ...],
    k: int,
) -> tuple[_FusedCandidate, ...]:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("ntd_production_rrf_invalid_k")

    lexical_map: dict[uuid.UUID, _LexicalCandidate] = {}
    for lexical_item in lexical:
        lexical_map[lexical_item.contextual_chunk_id] = lexical_item

    dense_map: dict[uuid.UUID, _DenseCandidate] = {}
    for dense_item in dense:
        dense_map[dense_item.contextual_chunk_id] = dense_item

    all_chunk_ids: set[uuid.UUID] = set(lexical_map.keys()) | set(dense_map.keys())

    fused_candidates: list[_FusedCandidate] = []
    for chunk_id in all_chunk_ids:
        lexical_candidate = lexical_map.get(chunk_id)
        dense_candidate = dense_map.get(chunk_id)

        if lexical_candidate is None and dense_candidate is None:
            raise ValueError("ntd_production_rrf_missing_candidates")

        if lexical_candidate is not None and dense_candidate is not None:
            if lexical_candidate.corpus_object_id != dense_candidate.corpus_object_id:
                raise ValueError("ntd_production_rrf_corpus_object_mismatch")
            corpus_object_id = lexical_candidate.corpus_object_id
        elif lexical_candidate is not None:
            corpus_object_id = lexical_candidate.corpus_object_id
        else:
            if dense_candidate is None:
                raise ValueError("ntd_production_rrf_missing_candidates")
            corpus_object_id = dense_candidate.corpus_object_id

        fused_score = 0.0
        reasons: list[str] = []

        if lexical_candidate is not None:
            fused_score += 1.0 / (k + lexical_candidate.rank)
            reasons.append(f"lexical_rank:{lexical_candidate.rank}")
        if dense_candidate is not None:
            fused_score += 1.0 / (k + dense_candidate.rank)
            reasons.append(f"dense_rank:{dense_candidate.rank}")

        fused_candidates.append(
            _FusedCandidate(
                corpus_object_id=corpus_object_id,
                contextual_chunk_id=chunk_id,
                lexical_rank=lexical_candidate.rank if lexical_candidate is not None else None,
                lexical_score=(
                    lexical_candidate.lexical_score if lexical_candidate is not None else None
                ),
                dense_rank=dense_candidate.rank if dense_candidate is not None else None,
                dense_similarity=(
                    dense_candidate.similarity if dense_candidate is not None else None
                ),
                fused_score=fused_score,
                ranking_reasons=tuple(reasons),
            )
        )

    fused_candidates.sort(key=lambda c: (-c.fused_score, str(c.contextual_chunk_id)))
    return tuple(fused_candidates)


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


def query_production_candidates(
    connection: Connection,
    query: str,
    query_vector: tuple[float, ...],
    limit: int = 8,
) -> tuple[_FusedCandidate, ...]:
    _validate_query(query, limit)
    profile = _load_profile(connection)
    candidate_limit = min(200, max(limit * 5, limit))
    lexical = _load_lexical_candidates(connection, profile, query, candidate_limit)
    dense = _load_dense_candidates(connection, profile, query_vector, candidate_limit)
    fused = _reciprocal_rank_fusion(lexical, dense, 60)
    filtered = tuple(
        c
        for c in fused
        if _normalized_relevance(c.lexical_score, c.dense_similarity) >= profile.min_relevance
    )

    groups: dict[uuid.UUID, list[_FusedCandidate]] = {}
    for candidate in filtered:
        groups.setdefault(candidate.corpus_object_id, []).append(candidate)

    for candidates in groups.values():
        candidates.sort(key=lambda c: (-c.fused_score, str(c.contextual_chunk_id)))

    def _doc_sort_key(item: tuple[uuid.UUID, list[_FusedCandidate]]) -> tuple[float, str]:
        _, candidates = item
        top_two_scores = [c.fused_score for c in candidates[:2]]
        return (-sum(top_two_scores), str(item[0]))

    sorted_groups = sorted(groups.items(), key=_doc_sort_key)

    result: list[_FusedCandidate] = []
    while len(result) < limit and any(groups.values()):
        for _corpus_id, candidates in sorted_groups:
            if not candidates:
                continue
            result.append(candidates.pop(0))
            if len(result) >= limit:
                break

    return tuple(result)


def _load_production_hits(
    connection: Connection,
    candidates: tuple[_FusedCandidate, ...],
) -> tuple[ProductionRetrievalHit, ...]:
    if not candidates:
        return ()

    contextual_chunk_ids = tuple(c.contextual_chunk_id for c in candidates)
    sql = """
        SELECT
            c.corpus_object_id,
            cc.contextual_chunk_id,
            o.stable_designation AS designation,
            o.title,
            o.authority_class,
            c.page_start,
            c.page_end,
            c.structural_path,
            cc.input_text AS text,
            c.source_locator_ids
        FROM platform.ntd_contextual_chunks cc
        JOIN platform.ntd_chunks c ON c.chunk_id=cc.chunk_id AND c.version=cc.chunk_version
        JOIN platform.ntd_corpus_objects o ON o.corpus_object_id=c.corpus_object_id
        WHERE cc.contextual_chunk_id = ANY(CAST(:contextual_chunk_ids AS uuid[]))
    """
    rows = (
        connection.execute(sa.text(sql), {"contextual_chunk_ids": contextual_chunk_ids})
        .mappings()
        .all()
    )
    row_map = {uuid.UUID(str(row["contextual_chunk_id"])): row for row in rows}

    hits: list[ProductionRetrievalHit] = []
    for candidate in candidates:
        row = row_map.get(candidate.contextual_chunk_id)
        if row is None:
            raise ValueError("ntd_production_hit_missing_contextual_chunk")

        source_locator_ids = tuple(uuid.UUID(str(x)) for x in row["source_locator_ids"])
        hits.append(
            ProductionRetrievalHit(
                corpus_object_id=uuid.UUID(str(row["corpus_object_id"])),
                contextual_chunk_id=uuid.UUID(str(row["contextual_chunk_id"])),
                designation=str(row["designation"]),
                title=str(row["title"]),
                authority_class=str(row["authority_class"]),
                page_start=int(row["page_start"]),
                page_end=int(row["page_end"]),
                structural_path=str(row["structural_path"]),
                text=str(row["text"]),
                source_locator_ids=source_locator_ids,
                lexical_rank=candidate.lexical_rank,
                lexical_score=candidate.lexical_score,
                dense_rank=candidate.dense_rank,
                dense_similarity=candidate.dense_similarity,
                final_score=candidate.fused_score,
                ranking_reasons=candidate.ranking_reasons,
            )
        )

    return tuple(hits)


def query_production_ntd(
    connection: Connection,
    embedding_endpoint: str,
    query: str,
    limit: int = 8,
) -> tuple[ProductionRetrievalHit, ...]:
    _validate_query(query, limit)
    profile = _load_profile(connection)
    query_vector = embed_query(embedding_endpoint, profile.embedding, query)
    candidates = query_production_candidates(connection, query, query_vector, limit)
    return _load_production_hits(connection, candidates)
