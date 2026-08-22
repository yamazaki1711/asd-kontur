"""Rebuildable lexical, vector, and typed-graph projection operations."""

# ruff: noqa: E501 -- SQL fragments retain readable clause boundaries.

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from pgvector.psycopg import register_vector
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .errors import KnowledgeError, KnowledgeErrorCode


class ProjectionState(StrEnum):
    BUILDING = "building"
    READY = "ready"
    EMPTY = "empty"
    STALE = "stale"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    lexical_index_version_id: UUID
    embedding_index_version_id: UUID
    graph_projection_version_id: UUID
    canonical_snapshot_digest: str
    entry_digest: str
    state: ProjectionState


class ProjectionBuilder:
    """Projection-writer service; canonical rows are read but never mutated."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        event.listen(self._engine, "connect", self._register_vector)

    @staticmethod
    def _register_vector(dbapi_connection: object, _record: object) -> None:
        register_vector(dbapi_connection)  # type: ignore[arg-type]

    def rebuild(
        self,
        *,
        canonical_snapshot_digest: str,
        embedding_profile_version: str,
        entries: tuple[tuple[UUID, str, tuple[float, float, float]], ...],
        edges: tuple[tuple[UUID, UUID, str], ...],
    ) -> ProjectionSnapshot:
        lexical_id, embedding_id, graph_id = uuid7(), uuid7(), uuid7()
        entry_digest = self._entry_digest(entries, edges)
        state = ProjectionState.READY if entries else ProjectionState.EMPTY
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO projection.lexical_index_versions "
                    "(lexical_index_version_id,profile_key,profile_version,canonical_snapshot_digest,status,built_at) "
                    "VALUES (:id,'lexical.synthetic','1.0.0',:snapshot,:state,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": lexical_id,
                    "snapshot": canonical_snapshot_digest,
                    "state": state,
                    "count": len(entries),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO projection.embedding_index_versions "
                    "(embedding_index_version_id,profile_key,profile_version,model_id,model_revision,"
                    "dimension,dtype,metric,index_profile,chunker_version,instruction_version,"
                    "canonical_snapshot_digest,status,built_at) "
                    "VALUES (:id,'embedding.synthetic',:profile,'synthetic-vector','1',3,'float32',"
                    "'cosine','hnsw-v0.1','1.0.0','1.0.0',:snapshot,:state,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": embedding_id,
                    "snapshot": canonical_snapshot_digest,
                    "profile": embedding_profile_version,
                    "state": state,
                    "count": len(entries),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO projection.graph_projection_versions "
                    "(graph_projection_version_id,profile_key,profile_version,canonical_snapshot_digest,status,built_at) "
                    "VALUES (:id,'graph.synthetic','1.0.0',:snapshot,:state,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": graph_id,
                    "snapshot": canonical_snapshot_digest,
                    "state": state,
                    "count": len(edges),
                },
            )
            for structural_unit_id, text_value, vector in entries:
                unit = (
                    session.execute(
                        sa.text(
                            "SELECT normative_edition_id,structural_path FROM platform.structural_units "
                            "WHERE structural_unit_id=:id"
                        ),
                        {"id": structural_unit_id},
                    )
                    .mappings()
                    .one()
                )
                session.execute(
                    sa.text(
                        "INSERT INTO projection.lexical_entries "
                        "(lexical_index_version_id,structural_unit_id,normative_edition_id,structural_path,normalized_text) "
                        "VALUES (:version,:unit,:edition,:path,:text)"
                    ),
                    {
                        "version": lexical_id,
                        "unit": structural_unit_id,
                        "edition": unit["normative_edition_id"],
                        "path": unit["structural_path"],
                        "text": text_value,
                    },
                )
                session.execute(
                    sa.text(
                        "INSERT INTO projection.embedding_entries "
                        "(embedding_index_version_id,structural_unit_id,dimension,embedding,vector_digest) "
                        "VALUES (:version,:unit,3,:embedding,:digest)"
                    ),
                    {
                        "version": embedding_id,
                        "unit": structural_unit_id,
                        "embedding": list(vector),
                        "digest": "sha256:" + hashlib.sha256(repr(vector).encode()).hexdigest(),
                    },
                )
            for source_id, target_id, edge_type in edges:
                session.execute(
                    sa.text(
                        "INSERT INTO projection.typed_edges "
                        "(graph_projection_version_id,typed_edge_id,source_structural_unit_id,target_structural_unit_id,"
                        "edge_type,derivation_profile_version) "
                        "VALUES (:version,:edge,:source,:target,:type,'1.0.0')"
                    ),
                    {
                        "version": graph_id,
                        "edge": uuid7(),
                        "source": source_id,
                        "target": target_id,
                        "type": edge_type,
                    },
                )
        return ProjectionSnapshot(
            lexical_id, embedding_id, graph_id, canonical_snapshot_digest, entry_digest, state
        )

    def exact_fts(self, version_id: UUID, query: str) -> tuple[UUID, ...]:
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT status FROM projection.lexical_index_versions "
                    "WHERE lexical_index_version_id=:id"
                ),
                {"id": version_id},
            ).scalar_one_or_none()
            if state not in {ProjectionState.READY, ProjectionState.EMPTY}:
                raise KnowledgeError(
                    KnowledgeErrorCode.INDEX_UNAVAILABLE,
                    "Lexical index is absent, stale, building, failed, or deleted.",
                )
            return tuple(
                UUID(str(value))
                for value in session.execute(
                    sa.text(
                        "SELECT structural_unit_id FROM projection.lexical_entries "
                        "WHERE lexical_index_version_id=:id "
                        "AND search_vector @@ plainto_tsquery('russian', :query) "
                        "ORDER BY structural_unit_id"
                    ),
                    {"id": version_id, "query": query},
                ).scalars()
            )

    def vector_search(
        self, version_id: UUID, vector: tuple[float, float, float], limit: int = 10
    ) -> tuple[UUID, ...]:
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT status FROM projection.embedding_index_versions "
                    "WHERE embedding_index_version_id=:id"
                ),
                {"id": version_id},
            ).scalar_one_or_none()
            if state != ProjectionState.READY:
                raise KnowledgeError(
                    KnowledgeErrorCode.INDEX_UNAVAILABLE,
                    "Vector index is empty, stale, failed, building, deleted, or absent.",
                )
            rows = session.execute(
                sa.text(
                    "SELECT structural_unit_id FROM projection.embedding_entries "
                    "WHERE embedding_index_version_id=:id "
                    "ORDER BY embedding <=> CAST(:vector AS vector) LIMIT :limit"
                ),
                {"id": version_id, "vector": list(vector), "limit": limit},
            ).scalars()
            return tuple(UUID(str(value)) for value in rows)

    def graph_neighbors(self, version_id: UUID, assertion_id: UUID) -> tuple[UUID, ...]:
        with Session(self._engine) as session:
            state = session.execute(
                sa.text(
                    "SELECT status FROM projection.graph_projection_versions "
                    "WHERE graph_projection_version_id=:id"
                ),
                {"id": version_id},
            ).scalar_one_or_none()
            if state != ProjectionState.READY:
                raise KnowledgeError(
                    KnowledgeErrorCode.INDEX_UNAVAILABLE,
                    "Graph projection is not ready.",
                )
            values = session.execute(
                sa.text(
                    "SELECT target_structural_unit_id FROM projection.typed_edges "
                    "WHERE graph_projection_version_id=:version AND source_structural_unit_id=:source "
                    "ORDER BY target_structural_unit_id"
                ),
                {"version": version_id, "source": assertion_id},
            ).scalars()
            return tuple(UUID(str(value)) for value in values)

    def delete(self, snapshot: ProjectionSnapshot) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "DELETE FROM projection.lexical_index_versions WHERE lexical_index_version_id=:id"
                ),
                {"id": snapshot.lexical_index_version_id},
            )
            session.execute(
                sa.text(
                    "DELETE FROM projection.embedding_index_versions WHERE embedding_index_version_id=:id"
                ),
                {"id": snapshot.embedding_index_version_id},
            )
            session.execute(
                sa.text(
                    "DELETE FROM projection.graph_projection_versions WHERE graph_projection_version_id=:id"
                ),
                {"id": snapshot.graph_projection_version_id},
            )

    @staticmethod
    def _entry_digest(
        entries: tuple[tuple[UUID, str, tuple[float, float, float]], ...],
        edges: tuple[tuple[UUID, UUID, str], ...],
    ) -> str:
        representation = repr(
            (sorted((str(i), t, v) for i, t, v in entries), sorted(map(str, edges)))
        ).encode()
        return f"sha256:{hashlib.sha256(representation).hexdigest()}"
