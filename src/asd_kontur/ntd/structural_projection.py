"""Deterministic structure-aware projection over persisted NTD page text."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.retrieval_qualification import (
    CONTEXTUAL_PROFILE,
    QualificationCorpusEntry,
    _scope_context,
    _work_context,
    build_representation,
    qualification_document_from_pages,
)

_ORDINAL_OFFSET = 100_000


def rebuild_ntd_structural_units(engine: Engine) -> dict[str, int | str]:
    """Rebuild qualified units without changing the immutable page layer."""

    with engine.connect() as connection:
        objects = (
            connection.execute(
                sa.text(
                    "SELECT corpus_object_id,source_version_id,artifact_digest,stable_designation,"
                    "title,authority_class FROM platform.ntd_corpus_objects "
                    "WHERE terminal_outcome='admitted' AND authority_class <> 'gesn_candidate' "
                    "ORDER BY artifact_digest"
                )
            )
            .mappings()
            .all()
        )
        pages = (
            connection.execute(
                sa.text(
                    "SELECT corpus_object_id,page_number,raw_transcription,source_locator_id,"
                    "terminal_outcome FROM platform.ntd_corpus_pages WHERE version=1 "
                    "ORDER BY corpus_object_id,page_number"
                )
            )
            .mappings()
            .all()
        )

    pages_by_object: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        local_page = dict(page)
        if str(local_page.get("terminal_outcome", "")).startswith("blocked"):
            local_page["raw_transcription"] = ""
        pages_by_object[local_page["corpus_object_id"]].append(local_page)

    projected: list[dict[str, Any]] = []
    blocked: list[str] = []
    for corpus_object in objects:
        corpus_object_id = corpus_object["corpus_object_id"]
        object_pages = pages_by_object.get(corpus_object_id, [])
        page_numbers = [int(page["page_number"]) for page in object_pages]
        if (
            page_numbers != list(range(1, len(object_pages) + 1))
            or not object_pages
            or not any(str(page["raw_transcription"]).strip() for page in object_pages)
        ):
            blocked.append(str(corpus_object["artifact_digest"]))
            continue
        entry = QualificationCorpusEntry(
            str(corpus_object["stable_designation"]),
            str(corpus_object["title"]),
            str(corpus_object["artifact_digest"]),
            str(corpus_object["authority_class"]),
            len(object_pages),
            None,
            (),
        )
        document = qualification_document_from_pages(
            entry,
            tuple(str(page["raw_transcription"]) for page in object_pages),
        )
        locator_by_page = {
            int(page["page_number"]): page["source_locator_id"] for page in object_pages
        }
        unit_id_by_path = {
            unit.structural_path: deterministic_uuid(
                f"ntd-qualified-structural-unit:{unit.unit_id}"
            )
            for unit in document.units
        }
        for unit in document.units:
            unit_id = unit_id_by_path[unit.structural_path]
            locators = [locator_by_page[page] for page in unit.pages]
            raw_digest = _digest(unit.raw_text.encode())
            normalized_digest = _digest(unit.normalized_text.encode())
            fingerprint = semantic_digest(
                {
                    "profile": "ntd-qualified-structure@1.0.0",
                    "unit_id": str(unit_id),
                    "source_version_id": str(corpus_object["source_version_id"]),
                    "structural_path": unit.structural_path,
                    "locators": [str(value) for value in locators],
                    "raw_text_digest": raw_digest,
                    "normalized_text_digest": normalized_digest,
                }
            )
            projected.append(
                {
                    "id": unit_id,
                    "corpus": corpus_object_id,
                    "source": corpus_object["source_version_id"],
                    "parent": (
                        unit_id_by_path.get(unit.parent_path)
                        if unit.parent_path is not None
                        else None
                    ),
                    "kind": _unit_kind(unit.kind),
                    "ordinal": _ORDINAL_OFFSET + unit.ordinal,
                    "label": unit.clause_label,
                    "heading": unit.heading,
                    "start": min(unit.pages),
                    "end": max(unit.pages),
                    "path": unit.structural_path,
                    "locators": locators,
                    "raw": unit.raw_text,
                    "normalized": unit.normalized_text,
                    "raw_digest": raw_digest,
                    "normalized_digest": normalized_digest,
                    "fingerprint": fingerprint,
                }
            )

    with engine.begin() as connection:
        for projected_unit in projected:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_structural_units("
                    "structural_unit_id,version,corpus_object_id,source_version_id,"
                    "parent_structural_unit_id,unit_kind,ordinal,label,heading,page_start,page_end,"
                    "structural_path,source_locator_ids,raw_text,normalized_text,raw_text_digest,"
                    "normalized_text_digest,derivation_method,confidence_status,unit_fingerprint) "
                    "VALUES (:id,1,:corpus,:source,:parent,:kind,:ordinal,:label,:heading,"
                    ":start,:end,"
                    ":path,:locators,:raw,:normalized,:raw_digest,:normalized_digest,"
                    "'qualified_structure_reconstruction@1.0.0','deterministic',:fingerprint) "
                    "ON CONFLICT (unit_fingerprint) DO NOTHING"
                ),
                projected_unit,
            )

    return {
        "documents": len(objects) - len(blocked),
        "units": len(projected),
        "blocked": len(blocked),
        "fingerprint": semantic_digest(
            {
                "profile": "ntd-qualified-structure@1.0.0",
                "units": sorted(str(unit["id"]) for unit in projected),
                "blocked": sorted(blocked),
            }
        ),
    }


def rebuild_ntd_qualified_contextual_projection(
    engine: Engine, qualification_receipt: dict[str, Any]
) -> dict[str, int | str]:
    """Persist the benchmark-selected contextual projection over canonical pages."""

    profile_payload = {
        "profile_key": CONTEXTUAL_PROFILE,
        "profile_version": "1.0.0",
        "strategy": "contextual",
        "parameters": {"max_raw_characters": 1800, "structure_profile": "qualified"},
        "qualification_receipt": qualification_receipt,
    }
    profile_fingerprint = semantic_digest(profile_payload)
    profile_id = deterministic_uuid(f"ntd-chunk-profile:{profile_fingerprint}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_chunk_profiles("
                "chunk_profile_id,profile_key,profile_version,strategy,parameters,"
                "qualification_status,benchmark_receipt,profile_fingerprint) VALUES ("
                ":id,:key,:version,'contextual',CAST(:parameters AS jsonb),'qualified_primary',"
                "CAST(:receipt AS jsonb),:fingerprint) ON CONFLICT (profile_fingerprint) DO NOTHING"
            ),
            {
                "id": profile_id,
                "key": CONTEXTUAL_PROFILE,
                "version": "1.0.0",
                "parameters": json.dumps(profile_payload["parameters"], sort_keys=True),
                "receipt": json.dumps(qualification_receipt, ensure_ascii=False, sort_keys=True),
                "fingerprint": profile_fingerprint,
            },
        )

    with engine.connect() as connection:
        objects = (
            connection.execute(
                sa.text(
                    "SELECT corpus_object_id,source_version_id,normative_document_id,"
                    "normative_edition_id,artifact_digest,stable_designation,title,authority_class "
                    "FROM platform.ntd_corpus_objects WHERE terminal_outcome='admitted' "
                    "AND authority_class <> 'gesn_candidate' ORDER BY artifact_digest"
                )
            )
            .mappings()
            .all()
        )
        page_rows = (
            connection.execute(
                sa.text(
                    "SELECT corpus_object_id,page_number,raw_transcription,source_locator_id,"
                    "terminal_outcome "
                    "FROM platform.ntd_corpus_pages WHERE version=1 "
                    "ORDER BY corpus_object_id,page_number"
                )
            )
            .mappings()
            .all()
        )

    pages_by_object: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for page in page_rows:
        local_page = dict(page)
        if str(local_page.get("terminal_outcome", "")).startswith("blocked"):
            local_page["raw_transcription"] = ""
        pages_by_object[local_page["corpus_object_id"]].append(local_page)

    projected_chunks: list[dict[str, Any]] = []
    blocked: list[str] = []
    projected_documents = 0
    for corpus_object in objects:
        corpus_id = corpus_object["corpus_object_id"]
        pages = pages_by_object.get(corpus_id, [])
        page_numbers = [int(page["page_number"]) for page in pages]
        if (
            not pages
            or page_numbers != list(range(1, len(pages) + 1))
            or not any(str(page["raw_transcription"]).strip() for page in pages)
        ):
            blocked.append(str(corpus_object["artifact_digest"]))
            continue
        entry = QualificationCorpusEntry(
            str(corpus_object["stable_designation"]),
            str(corpus_object["title"]),
            str(corpus_object["artifact_digest"]),
            str(corpus_object["authority_class"]),
            len(pages),
            None,
            (),
        )
        document = qualification_document_from_pages(
            entry, tuple(str(page["raw_transcription"]) for page in pages)
        )
        representation = build_representation((document,), profile=CONTEXTUAL_PROFILE)
        locator_by_page = {int(page["page_number"]): page["source_locator_id"] for page in pages}
        unit_id_by_path = {
            unit.structural_path: deterministic_uuid(
                f"ntd-qualified-structural-unit:{unit.unit_id}"
            )
            for unit in document.units
        }
        unit_by_path = {unit.structural_path: unit for unit in document.units}
        chunk_id_by_path = {
            chunk.structural_path: chunk.chunk_id for chunk in representation.chunks
        }
        previous_by_base_path: dict[str, UUID] = {}
        for chunk in representation.chunks:
            base_path = chunk.structural_path.split("@continuation:", maxsplit=1)[0]
            unit_id = unit_id_by_path[base_path]
            unit = unit_by_path[base_path]
            locators = list(dict.fromkeys(locator_by_page[page] for page in chunk.pages))
            normalized = " ".join(chunk.raw_text.split())
            raw_digest = _digest(chunk.raw_text.encode())
            normalized_digest = _digest(normalized.encode())
            parent_chunk_id = (
                chunk_id_by_path.get(chunk.parent_path) if chunk.parent_path is not None else None
            )
            continuation_id = previous_by_base_path.get(base_path)
            chunk_fingerprint = semantic_digest(
                {
                    "profile": CONTEXTUAL_PROFILE,
                    "chunk": str(chunk.chunk_id),
                    "source": str(corpus_object["source_version_id"]),
                    "path": chunk.structural_path,
                    "locators": [str(value) for value in locators],
                    "raw": raw_digest,
                }
            )
            context_digest = _digest(chunk.derived_context.encode())
            input_digest = _digest(chunk.retrieval_text.encode())
            contextual_id = deterministic_uuid(
                f"ntd-contextual-chunk:{profile_id}:{chunk.chunk_id}:1:{input_digest}"
            )
            contextual_fingerprint = semantic_digest(
                {
                    "contextual_chunk": str(contextual_id),
                    "chunk": str(chunk.chunk_id),
                    "profile": str(profile_id),
                    "input": input_digest,
                }
            )
            parent_heading = ""
            if unit.parent_path is not None and unit.parent_path in unit_by_path:
                parent_heading = unit_by_path[unit.parent_path].heading or ""
            projected_chunks.append(
                {
                    "id": chunk.chunk_id,
                    "corpus": corpus_id,
                    "source": corpus_object["source_version_id"],
                    "document": corpus_object["normative_document_id"],
                    "edition": corpus_object["normative_edition_id"],
                    "authority": corpus_object["authority_class"],
                    "ordinal": 200_000 + chunk.ordinal,
                    "start": min(chunk.pages),
                    "end": max(chunk.pages),
                    "path": chunk.structural_path,
                    "locators": locators,
                    "raw": chunk.raw_text,
                    "normalized": normalized,
                    "raw_digest": raw_digest,
                    "normalized_digest": normalized_digest,
                    "parent": parent_chunk_id,
                    "continuation": continuation_id,
                    "chunk_fingerprint": chunk_fingerprint,
                    "contextual_id": contextual_id,
                    "profile": profile_id,
                    "units": [unit_id],
                    "designation": entry.designation,
                    "title": entry.title,
                    "section": unit.heading or chunk.structural_path,
                    "parent_heading": parent_heading,
                    "scope": _scope_context(entry),
                    "work": _work_context(entry),
                    "page_context": f"Страницы {min(chunk.pages)}-{max(chunk.pages)}",
                    "context": chunk.derived_context,
                    "context_digest": context_digest,
                    "input": chunk.retrieval_text,
                    "input_digest": input_digest,
                    "contextual_fingerprint": contextual_fingerprint,
                }
            )
            previous_by_base_path[base_path] = chunk.chunk_id
        projected_documents += 1

    with engine.begin() as connection:
        for record in projected_chunks:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_chunks(chunk_id,version,corpus_object_id,"
                    "source_version_id,normative_document_id,normative_edition_id,authority_class,"
                    "ordinal,page_start,page_end,structural_path,source_locator_ids,raw_text,"
                    "normalized_text,raw_text_digest,normalized_text_digest,chunking_profile_version,"
                    "parent_chunk_id,continuation_of_chunk_id,chunk_fingerprint) VALUES ("
                    ":id,1,:corpus,:source,:document,:edition,:authority,:ordinal,:start,:end,:path,"
                    ":locators,:raw,:normalized,:raw_digest,:normalized_digest,:profile_key,:parent,"
                    ":continuation,:chunk_fingerprint) ON CONFLICT (chunk_fingerprint) DO NOTHING"
                ),
                {**record, "profile_key": CONTEXTUAL_PROFILE},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.ntd_contextual_chunks(contextual_chunk_id,version,"
                    "chunk_id,chunk_version,chunk_profile_id,structural_unit_ids,designation_context,"
                    "title_context,section_context,parent_heading_context,scope_context,"
                    "regulated_work_context,page_range_context,derived_context,context_digest,"
                    "input_text,input_digest,contextual_fingerprint) VALUES ("
                    ":contextual_id,1,:id,1,:profile,:units,:designation,:title,:section,"
                    ":parent_heading,:scope,:work,:page_context,:context,:context_digest,:input,"
                    ":input_digest,:contextual_fingerprint) "
                    "ON CONFLICT (contextual_fingerprint) DO NOTHING"
                ),
                record,
            )

    fingerprint = semantic_digest(
        {
            "profile": CONTEXTUAL_PROFILE,
            "profile_id": str(profile_id),
            "chunks": sorted(str(chunk["id"]) for chunk in projected_chunks),
            "blocked": sorted(blocked),
        }
    )
    return {
        "documents": projected_documents,
        "chunks": len(projected_chunks),
        "blocked": len(blocked),
        "profile_id": str(profile_id),
        "fingerprint": fingerprint,
    }


def _unit_kind(value: str) -> str:
    if value in {"section", "clause", "subclause", "note", "table", "appendix"}:
        return value
    if value in {"document", "table_of_contents"}:
        return "document"
    if value == "definition":
        return "definition"
    return "page_region"


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
