"""Source-linked contract candidates for Support planning, without legal promotion."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from asd_kontur.application_spine.models import semantic_digest


def contract_obligation_handover(
    contract_view: dict[str, Any], *, workspace_id: UUID
) -> list[dict[str, Any]]:
    """Carry extracted duties into Support as review candidates only.

    A clause may impose duties on both parties.  The contract extractor's
    source locator is retained so the field team can inspect the original.
    Nothing here makes a candidate an accepted obligation or work prerequisite.
    """

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for clause in contract_view.get("clauses") or ():
        if not isinstance(clause, dict):
            continue
        source_version_id = str(clause.get("source_version_id") or "")
        source_locator_id = str(clause.get("source_locator_id") or "")
        clause_id = str(clause.get("clause_id") or "")
        if not source_version_id or not source_locator_id or not clause_id:
            continue
        for party, field in (
            ("customer", "customer_obligation"),
            ("contractor", "contractor_obligation"),
        ):
            obligation = str(clause.get(field) or "").strip()
            if not obligation:
                continue
            key = (clause_id, party, obligation)
            if key in seen:
                continue
            seen.add(key)
            candidate_id = str(uuid5(workspace_id, f"contract-obligation:{clause_id}:{party}"))
            candidate_digest = semantic_digest(
                {
                    "clause_id": clause_id,
                    "party": party,
                    "obligation": obligation,
                    "condition": str(clause.get("condition") or "").strip(),
                    "source_version_id": source_version_id,
                    "source_locator_id": source_locator_id,
                    "source_text": str(clause.get("source_text") or ""),
                }
            )
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_digest": candidate_digest,
                    "clause_id": clause_id,
                    "clause_key": str(clause.get("clause_key") or ""),
                    "party": party,
                    "obligation": obligation,
                    "condition": str(clause.get("condition") or "").strip() or None,
                    "source_version_id": source_version_id,
                    "source_locator_id": source_locator_id,
                    "source_name": clause.get("source_name"),
                    "source_page": clause.get("source_page"),
                    "authority": "qwen_extracted_candidate_requires_contract_review",
                }
            )
    return rows


def apply_contract_obligation_reviews(
    candidates: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Old decisions remain visible, but cannot authorize changed candidates."""

    latest = {str(item["candidate_id"]): item for item in decisions}
    reviewed: list[dict[str, Any]] = []
    for candidate in candidates:
        decision = latest.get(str(candidate["candidate_id"]))
        state = "unreviewed"
        if decision is not None:
            original = decision.get("original_value")
            if (
                isinstance(original, dict)
                and original.get("candidate_digest") == candidate["candidate_digest"]
            ):
                state = str(decision.get("action") or "unreviewed")
            else:
                state = "stale_requires_review"
        reviewed.append(
            {
                **candidate,
                "review_state": state,
                "reviewed_at": decision.get("decided_at") if decision else None,
            }
        )
    return reviewed
