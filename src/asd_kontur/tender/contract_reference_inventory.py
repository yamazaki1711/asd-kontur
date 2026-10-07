"""Bounded, source-located inventory context for contract cross-references."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session


def contract_reference_inventory(
    session: Session,
    *,
    organization_id: UUID,
    workspace_id: UUID,
    sources: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Expose names plus small first-page excerpts, never inferred document facts.

    Qwen decides whether an excerpt is a document title, merely a mention, or
    irrelevant. The same function is used by scheduling and the read model so
    accepted results cannot outlive their exact inventory context.
    """

    ordered = sorted(sources, key=lambda source: str(source["source_version_id"]))
    source_ids = [UUID(str(source["source_version_id"])) for source in ordered]
    if not source_ids:
        return []
    excerpt_budget = min(160, max(48, 6_000 // len(source_ids)))
    rows = session.execute(
        sa.text(
            "WITH latest AS (SELECT DISTINCT ON (source_version_id,source_locator_id) "
            "source_version_id,source_locator_id,page_number,reading_order,"
            "COALESCE(NULLIF(raw_text,''),normalized_text) AS source_text "
            "FROM workspace.native_layout_element_versions WHERE organization_id=:o "
            "AND workspace_id=:w AND source_version_id=ANY(:sources) "
            "ORDER BY source_version_id,source_locator_id,version DESC), "
            "ranked AS (SELECT *,row_number() OVER (PARTITION BY source_version_id "
            "ORDER BY page_number,reading_order,source_locator_id) AS position "
            "FROM latest WHERE source_text<>'') SELECT source_version_id,source_locator_id,"
            "source_text FROM ranked WHERE position<=12 ORDER BY source_version_id,position"
        ),
        {"o": organization_id, "w": workspace_id, "sources": source_ids},
    ).mappings()
    snippets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        text = " ".join(str(row["source_text"]).split())
        if len(text) >= 8:
            snippets[str(row["source_version_id"])].append((str(row["source_locator_id"]), text))
    inventory: list[dict[str, Any]] = []
    for source in ordered:
        source_id = str(source["source_version_id"])
        selected = snippets[source_id][:3]
        excerpt = " | ".join(text[:96] for _, text in selected)[:excerpt_budget]
        inventory.append(
            {
                "source_version_id": source_id,
                "safe_display_name": str(source["safe_display_name"]),
                "first_page_excerpt": excerpt,
                "excerpt_source_locator_ids": [locator for locator, _ in selected],
            }
        )
    return inventory
