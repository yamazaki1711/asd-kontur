"""Editable schedule for evidence-bound cross-document structure identities.

The schedule exposes model-proposed facility/structure identity groups without
turning them into canonical project entities.  Each row is one original
structure observation, so equal names, aliases, and distinct source revisions
remain inspectable before any later engineering reconciliation.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

from .findings_schedule import source_reference


def render_tender_structure_identity_schedule_csv(
    identity_candidates: Iterable[Mapping[str, Any]],
    *,
    structure_nodes: Iterable[Mapping[str, Any]],
    materialization_state: str,
    coverage_gaps: Iterable[str],
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> bytes:
    """Render one source observation per cross-document identity candidate.

    Missing member rows are surfaced as an internal consistency gap rather
    than dropped.  The accepted persistence contract prevents that condition,
    but the export must remain truthful if an old or partial projection is
    read during recovery.
    """

    nodes_by_id = {
        str(node.get("structure_node_id")): dict(node)
        for node in structure_nodes
        if node.get("structure_node_id") is not None
    }
    evidence = evidence_index or {}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "identity_candidate_id",
            "identity_kind",
            "candidate_label",
            "candidate_status",
            "confidence",
            "automatic_merge",
            "member_structure_node_id",
            "member_kind",
            "member_raw_name",
            "source_reference",
            "source_locator_id",
            "member_state",
            "materialization_state",
            "coverage_gaps",
        ),
    )
    writer.writeheader()
    gaps = ";".join(sorted(str(value) for value in coverage_gaps))
    candidates = sorted(
        (dict(item) for item in identity_candidates),
        key=lambda item: (
            str(item.get("canonical_label") or ""),
            str(item.get("identity_candidate_id") or ""),
        ),
    )
    for candidate in candidates:
        member_ids = sorted(
            str(value) for value in candidate.get("member_structure_node_ids") or ()
        )
        if not member_ids:
            member_ids = [""]
        for member_id in member_ids:
            node = nodes_by_id.get(member_id)
            locator_id = str(node.get("source_locator_id") or "") if node else ""
            writer.writerow(
                {
                    "identity_candidate_id": str(candidate.get("identity_candidate_id") or ""),
                    "identity_kind": str(candidate.get("identity_kind") or ""),
                    "candidate_label": str(candidate.get("canonical_label") or ""),
                    "candidate_status": str(candidate.get("status") or "candidate"),
                    "confidence": str(candidate.get("confidence") or ""),
                    "automatic_merge": "false",
                    "member_structure_node_id": member_id,
                    "member_kind": str(node.get("node_kind") or "") if node else "",
                    "member_raw_name": str(node.get("raw_name") or "") if node else "",
                    "source_reference": source_reference(locator_id, evidence.get(locator_id))
                    if locator_id
                    else "",
                    "source_locator_id": locator_id,
                    "member_state": "source_observation" if node else "member_unavailable",
                    "materialization_state": materialization_state,
                    "coverage_gaps": gaps,
                }
            )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
