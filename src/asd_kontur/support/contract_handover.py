"""Source-linked contract candidates for Support planning, without legal promotion."""

from __future__ import annotations

from typing import Any


def contract_obligation_handover(contract_view: dict[str, Any]) -> list[dict[str, Any]]:
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
            rows.append(
                {
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
