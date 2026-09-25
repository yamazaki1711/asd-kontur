#!/usr/bin/env python3
"""Benchmark real PostgreSQL FTS over the pinned NTD qualification corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from time import perf_counter
from typing import cast

import psycopg

from asd_kontur.ntd.retrieval_benchmark import (
    QueryRun,
    RetrievedItem,
    evaluate_retrieval,
    load_gold_benchmark,
)
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
    HIERARCHICAL_PROFILE,
    STRUCTURE_PROFILE,
    build_representation,
    read_extraction_cache,
)
from asd_kontur.ntd.search_corpus import designation_aliases, normalize_designation

SCHEMA = "ntd_retrieval_qualification"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--extraction-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus_digest = _file_digest(args.corpus)
    documents = read_extraction_cache(args.extraction_cache, corpus_digest=corpus_digest)
    gold = load_gold_benchmark(args.gold)
    payload_profiles: list[dict[str, object]] = []
    with psycopg.connect(args.database_url) as connection:
        database = str(connection.info.dbname)
        if not database.endswith("_qualification_01"):
            raise ValueError("ntd_fts_benchmark_requires_disposable_qualification_database")
        with connection.cursor() as cursor:
            cursor.execute("SELECT version(), current_setting('default_text_search_config')")
            postgres_version, default_fts = cast(tuple[str, str], cursor.fetchone())
        for profile in (STRUCTURE_PROFILE, CONTEXTUAL_PROFILE, HIERARCHICAL_PROFILE):
            build = build_representation(documents, profile=profile)
            build_started = perf_counter()
            _replace_projection(connection, build)
            build_seconds = perf_counter() - build_started
            runs = _run_queries(
                connection, build, gold, hierarchical=profile == HIERARCHICAL_PROFILE
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_total_relation_size(%s::regclass)",
                    (f"{SCHEMA}.chunks",),
                )
                relation_bytes = cast(int, cast(tuple[object], cursor.fetchone())[0])
            payload_profiles.append(
                {
                    "representation_profile": profile,
                    "representation_fingerprint": build.fingerprint,
                    "chunk_count": len(build.chunks),
                    "build_seconds": round(build_seconds, 3),
                    "relation_and_index_bytes": relation_bytes,
                    "metrics": evaluate_retrieval(gold, runs).as_dict(),
                }
            )
    payload: dict[str, object] = {
        "profile": "ntd-postgresql-fts-benchmark@1.0.0",
        "database": database,
        "postgres_version": postgres_version,
        "default_fts": default_fts,
        "fts_configuration": "russian",
        "corpus_digest": corpus_digest,
        "gold_digest": _file_digest(args.gold),
        "question_count": len(gold),
        "profiles": payload_profiles,
    }
    payload["receipt_fingerprint"] = _semantic_digest(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _replace_projection(connection: psycopg.Connection[tuple[object, ...]], build: object) -> None:
    from asd_kontur.ntd.retrieval_qualification import RepresentationBuild

    if not isinstance(build, RepresentationBuild):
        raise TypeError("ntd_fts_representation_invalid")
    with connection.cursor() as cursor:
        cursor.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cursor.execute(f"CREATE SCHEMA {SCHEMA}")
        cursor.execute(
            f"""
            CREATE TABLE {SCHEMA}.chunks (
                chunk_id uuid PRIMARY KEY,
                document_digest text NOT NULL,
                page_number integer,
                clause_label text,
                structural_path text NOT NULL,
                document_designation text NOT NULL,
                document_title text NOT NULL,
                content text NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', document_designation), 'A') ||
                    setweight(to_tsvector('russian', document_title), 'B') ||
                    setweight(to_tsvector('russian', content), 'C')
                ) STORED
            )
            """
        )
        by_digest = {document.entry.digest: document.entry for document in build.documents}
        cursor.executemany(
            f"""
            INSERT INTO {SCHEMA}.chunks (
                chunk_id, document_digest, page_number, clause_label,
                structural_path, document_designation, document_title, content
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.document_digest,
                    chunk.pages[0] if chunk.pages else None,
                    chunk.clause_labels[0] if chunk.clause_labels else None,
                    chunk.structural_path,
                    by_digest[chunk.document_digest].designation,
                    by_digest[chunk.document_digest].title,
                    chunk.retrieval_text,
                )
                for chunk in build.chunks
            ],
        )
        cursor.execute(
            f"CREATE INDEX chunks_search_gin ON {SCHEMA}.chunks USING gin (search_vector)"
        )
        cursor.execute(f"ANALYZE {SCHEMA}.chunks")
    connection.commit()


def _run_queries(
    connection: psycopg.Connection[tuple[object, ...]],
    build: object,
    gold: tuple[object, ...],
    *,
    hierarchical: bool,
) -> tuple[QueryRun, ...]:
    from asd_kontur.ntd.retrieval_benchmark import GoldQuery
    from asd_kontur.ntd.retrieval_qualification import RepresentationBuild

    if not isinstance(build, RepresentationBuild) or not all(
        isinstance(case, GoldQuery) for case in gold
    ):
        raise TypeError("ntd_fts_benchmark_input_invalid")
    aliases: dict[str, set[str]] = {}
    designation_by_digest = {
        document.entry.digest: document.entry.designation for document in build.documents
    }
    for document in build.documents:
        for alias in designation_aliases(document.entry.designation):
            aliases.setdefault(normalize_designation(alias), set()).add(document.entry.digest)
        for number in re.findall(r"\d+(?:[.\-]\d+)+|\d{4,}", document.entry.designation):
            aliases.setdefault(normalize_designation(number), set()).add(document.entry.digest)
            aliases.setdefault(normalize_designation(number.split("-", maxsplit=1)[0]), set()).add(
                document.entry.digest
            )
    unique_aliases = {
        alias: next(iter(digests))
        for alias, digests in aliases.items()
        if alias and len(digests) == 1
    }
    runs: list[QueryRun] = []
    for raw_case in gold:
        assert isinstance(raw_case, GoldQuery)
        started = perf_counter()
        normalized = normalize_designation(raw_case.query)
        resolved_digest = next(
            (
                digest
                for alias, digest in sorted(
                    unique_aliases.items(), key=lambda item: len(item[0]), reverse=True
                )
                if alias in normalized
            ),
            None,
        )
        with connection.cursor() as cursor:
            if resolved_digest is not None:
                cursor.execute(
                    f"""
                    SELECT document_digest, page_number, clause_label,
                           ts_rank_cd(search_vector, websearch_to_tsquery('russian', %s)) + 10
                    FROM {SCHEMA}.chunks
                    WHERE document_digest = %s
                    ORDER BY 4 DESC, page_number NULLS LAST, chunk_id
                    LIMIT 10
                    """,
                    (raw_case.query, resolved_digest),
                )
            else:
                document_limit = 5 if hierarchical else 10
                cursor.execute(
                    f"""
                    WITH ranked AS (
                        SELECT document_digest, page_number, clause_label,
                               ts_rank_cd(
                                   search_vector,
                                   websearch_to_tsquery('russian', %s)
                               ) AS score,
                               row_number() OVER (
                                   PARTITION BY document_digest ORDER BY
                                   ts_rank_cd(
                                       search_vector,
                                       websearch_to_tsquery('russian', %s)
                                   ) DESC,
                                   page_number NULLS LAST, chunk_id
                               ) AS within_document
                        FROM {SCHEMA}.chunks
                        WHERE search_vector @@ websearch_to_tsquery('russian', %s)
                    ), documents AS (
                        SELECT document_digest, max(score) AS document_score
                        FROM ranked GROUP BY document_digest ORDER BY document_score DESC
                        LIMIT %s
                    )
                    SELECT r.document_digest, r.page_number, r.clause_label, r.score
                    FROM ranked r JOIN documents d USING (document_digest)
                    WHERE r.within_document <= 3
                    ORDER BY d.document_score DESC, r.score DESC, r.page_number NULLS LAST
                    LIMIT 10
                    """,
                    (raw_case.query, raw_case.query, raw_case.query, document_limit),
                )
            rows = cast(
                list[tuple[str, int | None, str | None, float]],
                cursor.fetchall(),
            )
        items = tuple(
            RetrievedItem(
                str(row[0]),
                int(row[1]) if row[1] is not None else None,
                str(row[2]) if row[2] is not None else None,
                float(row[3]),
            )
            for row in rows
        )
        runs.append(
            QueryRun(
                raw_case.case_id,
                items,
                (perf_counter() - started) * 1000,
                designation_by_digest.get(resolved_digest) if resolved_digest else None,
            )
        )
    return tuple(runs)


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
