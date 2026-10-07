"""Bounded, project-independent contexts for contract revision consistency review."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

CONTRACT_COHERENCE_PROFILE = "qwen-contract-coherence-v1"
_MAX_REVISIONS = 16
_MAX_RELATED_CLAUSES = 12
_MAX_CONTEXT_CHARS = 10_000
_MAX_SOURCE_CHARS = 3_500
_MAX_RELATED_CHARS = 1_800
_CLAUSE_NUMBER = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){0,4})(?!\d)")


def contract_coherence_tasks(view: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Select exact, bounded source passages; never conclude semantic coherence here.

    The selection favours same-category passages, nearby pages and explicit
    clause-number references. Anything omitted is counted in the task's
    coverage, so an empty Qwen conflict list cannot certify the whole contract.
    """

    clauses = [item for item in view.get("clauses") or () if isinstance(item, dict)]
    revisions = [item for item in view.get("revised_clauses") or () if isinstance(item, dict)]
    by_identity = {
        (str(item.get("clause_id") or ""), str(item.get("clause_version") or "")): item
        for item in clauses
    }
    tasks: list[dict[str, Any]] = []
    for revision in sorted(revisions, key=lambda item: str(item.get("revised_clause_id") or ""))[
        :_MAX_REVISIONS
    ]:
        source = by_identity.get(
            (
                str(revision.get("source_clause_id") or ""),
                str(revision.get("source_clause_version") or ""),
            )
        )
        if source is None:
            continue
        source_text = str(source.get("source_text") or "").strip()
        proposed_text = str(revision.get("revised_text") or "").strip()
        revision_id = str(revision.get("revised_clause_id") or "")
        source_id = str(source.get("source_version_id") or "")
        if (
            not revision_id
            or not source_id
            or not source.get("source_locator_id")
            or not source_text
            or not proposed_text
            or len(source_text) > _MAX_SOURCE_CHARS
            or len(proposed_text) > _MAX_SOURCE_CHARS
        ):
            continue
        referenced_numbers = set(_CLAUSE_NUMBER.findall(proposed_text))
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for other in clauses:
            other_id = str(other.get("clause_id") or "")
            other_text = str(other.get("source_text") or "").strip()
            if (
                not other_id
                or other_id == str(source.get("clause_id"))
                or not other.get("source_locator_id")
                or not other_text
                or len(other_text) > _MAX_RELATED_CHARS
            ):
                continue
            same_category = bool(
                source.get("category")
                and other.get("category") == source.get("category")
                and source.get("category") != "other"
            )
            same_source = other.get("source_version_id") == source_id
            source_page = source.get("source_page")
            other_page = other.get("source_page")
            nearby = bool(
                same_source
                and isinstance(source_page, int)
                and isinstance(other_page, int)
                and abs(source_page - other_page) <= 2
            )
            number = str(other.get("display_clause_ref") or "")
            explicit_reference = number in referenced_numbers
            score = 5 * explicit_reference + 3 * same_category + 2 * nearby + same_source
            if score:
                scored.append((score, other_id, other))
        scored.sort(key=lambda row: (-row[0], row[1]))
        selected: list[dict[str, Any]] = []
        chars = len(source_text) + len(proposed_text)
        for _score, _id, other in scored:
            if len(selected) >= _MAX_RELATED_CLAUSES:
                break
            text = str(other["source_text"]).strip()
            if chars + len(text) > _MAX_CONTEXT_CHARS:
                continue
            selected.append(_clause_context(other))
            chars += len(text)
        if not selected:
            continue
        revision_digest = semantic_digest(
            {
                "revision_id": revision_id,
                "source_clause_id": str(source.get("clause_id")),
                "source_text": source_text,
                "proposed_text": proposed_text,
            }
        )
        context = {
            "profile": CONTRACT_COHERENCE_PROFILE,
            "revision_id": revision_id,
            "revision_digest": revision_digest,
            "source_clause": _clause_context(source),
            "proposed_text": proposed_text,
            "related_clauses": selected,
            "coverage": {
                "total_other_clauses": len(clauses) - 1,
                "selected_other_clauses": len(selected),
                "omitted_other_clauses": max(0, len(clauses) - 1 - len(selected)),
                "total_revisions": len(revisions),
                "scheduled_revision_limit": _MAX_REVISIONS,
            },
        }
        context["context_digest"] = semantic_digest(context)
        tasks.append(context)
    return tuple(tasks)


def _clause_context(clause: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "clause_id": str(clause.get("clause_id") or ""),
        "clause_version": str(clause.get("clause_version") or ""),
        "source_version_id": str(clause.get("source_version_id") or ""),
        "source_locator_id": str(clause.get("source_locator_id") or ""),
        "source_page": clause.get("source_page"),
        "display_clause_ref": str(clause.get("display_clause_ref") or ""),
        "category": str(clause.get("category") or ""),
        "source_text": str(clause.get("source_text") or "").strip(),
    }


def current_coherence_digests(view: Mapping[str, Any]) -> set[str]:
    """Only results for the current exact source/proposal context may be shown."""

    return {str(task["context_digest"]) for task in contract_coherence_tasks(view)}
