"""Version-bound selection of proposed revisions for an editable contract draft."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from asd_kontur.application_spine.models import semantic_digest

from .revised_contract_candidate import RevisedContractCandidateError


def contract_revision_fingerprint(view: dict[str, Any]) -> str:
    """Bind a reviewer selection to exact current text and source clauses."""

    clauses = {
        (str(item.get("clause_id")), str(item.get("clause_version"))): item
        for item in view.get("clauses") or ()
        if isinstance(item, dict)
    }
    revisions: list[dict[str, str]] = []
    for item in view.get("revised_clauses") or ():
        if not isinstance(item, dict):
            continue
        clause = clauses.get(
            (str(item.get("source_clause_id")), str(item.get("source_clause_version")))
        )
        revisions.append(
            {
                "revision_id": str(item.get("revised_clause_id") or ""),
                "revised_text": str(item.get("revised_text") or ""),
                "replacement_source_text": str(item.get("replacement_source_text") or ""),
                "source_version_id": str(clause.get("source_version_id") or "") if clause else "",
                "source_text": str(clause.get("source_text") or "") if clause else "",
            }
        )
    return semantic_digest(sorted(revisions, key=lambda item: item["revision_id"]))


def select_contract_revisions(
    view: dict[str, Any],
    *,
    revision_ids: list[str] | None,
    fingerprint: str | None,
) -> dict[str, Any]:
    """Return only exact current proposals; never accept client-authored wording."""

    if revision_ids is None and fingerprint is None:
        return view
    if not revision_ids or not fingerprint or len(revision_ids) > 100:
        raise RevisedContractCandidateError("revised_contract_selection_invalid")
    if fingerprint != contract_revision_fingerprint(view):
        raise RevisedContractCandidateError("revised_contract_selection_stale")
    try:
        selected_ids = [str(UUID(value)) for value in revision_ids]
    except ValueError as exc:
        raise RevisedContractCandidateError("revised_contract_selection_invalid") from exc
    if len(selected_ids) != len(set(selected_ids)):
        raise RevisedContractCandidateError("revised_contract_selection_invalid")
    current = {
        str(item.get("revised_clause_id")): item
        for item in view.get("revised_clauses") or ()
        if isinstance(item, dict)
    }
    if not set(selected_ids).issubset(current):
        raise RevisedContractCandidateError("revised_contract_selection_stale")
    return {**view, "revised_clauses": [current[identity] for identity in selected_ids]}
