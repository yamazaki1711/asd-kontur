"""Bounded, project-independent contexts for contract revision consistency review."""

# ruff: noqa: RUF001 -- Russian clause-reference forms are intentional.

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.tender.clause_reference import display_clause_reference

CONTRACT_COHERENCE_PROFILE = "qwen-contract-coherence-v2"
# A failed v2 result write under schema 0133 must not reserve the same durable
# scheduling identity after the compatible result constraint is installed.
CONTRACT_COHERENCE_RESULT_SCHEMA = "0134"
MAX_CONTRACT_COHERENCE_REVISIONS = 16
_MAX_RELATED_CLAUSES = 12
_MAX_REFERENCE_OVERFLOW_BATCHES = 8
_MAX_CONTEXT_CHARS = 10_000
_MAX_SOURCE_CHARS = 3_500
_MAX_RELATED_CHARS = 1_800
_EXPLICIT_CLAUSE_REFERENCE = re.compile(
    r"(?<!\w)(?:п\.|пункт(?:а|е|ом|у)?|clauses?|sections?)\s*"
    r"(?:№\s*)?(\d{1,3}(?:\.\d{1,3}){1,4})(?![\d.])",
    re.IGNORECASE,
)
_CLAUSE_NUMBER = re.compile(r"\d{1,3}(?:\.\d{1,3}){1,4}")


def contract_coherence_job_key(context_digest: str) -> str:
    return (
        f"contract-coherence:{CONTRACT_COHERENCE_PROFILE}:"
        f"schema-{CONTRACT_COHERENCE_RESULT_SCHEMA}:{context_digest}"
    )


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
        :MAX_CONTRACT_COHERENCE_REVISIONS
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
        referenced_numbers = set(_EXPLICIT_CLAUSE_REFERENCE.findall(proposed_text))
        source_number = display_clause_reference(source)
        if _CLAUSE_NUMBER.fullmatch(source_number) is None:
            source_number = ""
        scored: list[tuple[int, str, dict[str, Any]]] = []
        reverse_reference_ids: set[str] = set()
        for other in clauses:
            other_id = str(other.get("clause_id") or "")
            other_text = str(other.get("source_text") or "").strip()
            if (
                other_id
                and other_id != str(source.get("clause_id"))
                and other.get("source_locator_id")
                and source_number
                and source_number in _EXPLICIT_CLAUSE_REFERENCE.findall(other_text)
            ):
                reverse_reference_ids.add(other_id)
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
            number = display_clause_reference(other)
            forward_reference = number in referenced_numbers
            reverse_reference = other_id in reverse_reference_ids
            score = (
                7 * reverse_reference
                + 6 * forward_reference
                + 3 * same_category
                + 2 * nearby
                + same_source
            )
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
                "reverse_reference_clauses": len(reverse_reference_ids),
                "selected_reverse_reference_clauses": sum(
                    str(item["clause_id"]) in reverse_reference_ids for item in selected
                ),
                "total_revisions": len(revisions),
                "scheduled_revision_limit": MAX_CONTRACT_COHERENCE_REVISIONS,
            },
        }
        context["context_digest"] = semantic_digest(context)
        tasks.append(context)
        # Keep the original bounded context byte-for-byte stable: accepted
        # reviews remain reusable. Explicit cross-references that lost the
        # ranking/budget contest get separate bounded semantic reviews.
        selected_ids = {str(item["clause_id"]) for item in selected}
        overflow = [
            other
            for _score, other_id, other in scored
            if other_id not in selected_ids
            and (
                other_id in reverse_reference_ids
                or display_clause_reference(other) in referenced_numbers
            )
        ]
        overflow_batches: list[list[dict[str, Any]]] = []
        batch: list[dict[str, Any]] = []
        batch_chars = len(source_text) + len(proposed_text)
        for other in overflow:
            other_text = str(other["source_text"]).strip()
            if batch and (
                len(batch) >= _MAX_RELATED_CLAUSES
                or batch_chars + len(other_text) > _MAX_CONTEXT_CHARS
            ):
                overflow_batches.append(batch)
                batch = []
                batch_chars = len(source_text) + len(proposed_text)
            if batch_chars + len(other_text) > _MAX_CONTEXT_CHARS:
                continue
            batch.append(_clause_context(other))
            batch_chars += len(other_text)
        if batch:
            overflow_batches.append(batch)
        for index, related in enumerate(
            overflow_batches[:_MAX_REFERENCE_OVERFLOW_BATCHES], start=1
        ):
            overflow_context = {
                "profile": CONTRACT_COHERENCE_PROFILE,
                "revision_id": revision_id,
                "revision_digest": revision_digest,
                "source_clause": _clause_context(source),
                "proposed_text": proposed_text,
                "related_clauses": related,
                "coverage": {
                    "review_segment": "explicit_reference_overflow",
                    "segment_index": index,
                    "total_explicit_reference_overflow": len(overflow),
                    "scheduled_overflow_batch_limit": _MAX_REFERENCE_OVERFLOW_BATCHES,
                    "total_other_clauses": len(clauses) - 1,
                    "selected_other_clauses": len(related),
                    "omitted_other_clauses": max(0, len(clauses) - 1 - len(related)),
                    "total_revisions": len(revisions),
                    "scheduled_revision_limit": MAX_CONTRACT_COHERENCE_REVISIONS,
                },
            }
            overflow_context["context_digest"] = semantic_digest(overflow_context)
            tasks.append(overflow_context)
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


def unreviewed_explicit_reference_count(
    view: Mapping[str, Any], tasks: tuple[dict[str, Any], ...]
) -> int:
    """Count source-backed explicit clause links outside scheduled Qwen contexts.

    This is a coverage alarm, not a semantic-conflict finding. Long passages,
    budget caps and missing locators cannot quietly become legal clearance.
    """

    clauses = [item for item in view.get("clauses") or () if isinstance(item, dict)]
    revisions = [item for item in view.get("revised_clauses") or () if isinstance(item, dict)]
    by_identity = {
        (str(item.get("clause_id") or ""), str(item.get("clause_version") or "")): item
        for item in clauses
    }
    scheduled: dict[str, set[str]] = {}
    for task in tasks:
        scheduled.setdefault(str(task["revision_id"]), set()).update(
            str(item["clause_id"]) for item in task["related_clauses"]
        )
    unreviewed = 0
    for revision in revisions:
        revision_id = str(revision.get("revised_clause_id") or "")
        source = by_identity.get(
            (
                str(revision.get("source_clause_id") or ""),
                str(revision.get("source_clause_version") or ""),
            )
        )
        if source is None:
            continue
        source_number = display_clause_reference(source)
        if _CLAUSE_NUMBER.fullmatch(source_number) is None:
            source_number = ""
        forward_numbers = set(
            _EXPLICIT_CLAUSE_REFERENCE.findall(str(revision.get("revised_text") or ""))
        )
        selected = scheduled.get(revision_id, set())
        for other in clauses:
            other_id = str(other.get("clause_id") or "")
            if not other_id or other_id == str(source.get("clause_id")):
                continue
            other_number = display_clause_reference(other)
            reverse = bool(
                source_number
                and source_number
                in _EXPLICIT_CLAUSE_REFERENCE.findall(str(other.get("source_text") or ""))
            )
            if (reverse or other_number in forward_numbers) and other_id not in selected:
                unreviewed += 1
    return unreviewed
