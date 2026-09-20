"""Editable export of the canonical Tender contract-analysis read model."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

_FIELDS = (
    "row_kind",
    "process_id",
    "process_revision",
    "process_state",
    "item_id",
    "item_version",
    "item_kind",
    "subject",
    "severity",
    "applicability",
    "clause_id",
    "clause_version",
    "clause_key",
    "source_version_id",
    "source_locator_id",
    "evidence_link_ids",
    "authority_layer",
    "proposed_clause_text",
    "revised_clause_text",
    "recommendation",
    "consequence",
    "uncertainty_codes",
    "state",
    "blockers",
    "missing_source_classes",
    "gaps",
    "authority_boundary",
)


def render_tender_contract_analysis_csv(view: Mapping[str, Any]) -> bytes:
    """Render exact canonical records without promoting them to a legal decision."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    process = _mapping(view.get("process"))
    common = {
        "process_id": process.get("tender_process_id", ""),
        "process_revision": process.get("revision", ""),
        "process_state": process.get("state", view.get("status", "")),
        "gaps": _joined(view.get("gaps")),
        "authority_boundary": view.get("authority_boundary", ""),
    }
    writer.writerow(_row(common, row_kind="process", state=view.get("status", "")))

    assessment = _mapping(view.get("assessment"))
    if assessment:
        writer.writerow(
            _row(
                common,
                row_kind="corpus_assessment",
                state=assessment.get("status", ""),
                missing_source_classes=_joined(assessment.get("missing_source_classes")),
            )
        )

    clauses = tuple(_records(view.get("clauses")))
    clause_by_identity = {
        (str(item.get("clause_id", "")), str(item.get("clause_version", ""))): item
        for item in clauses
    }
    for item in clauses:
        writer.writerow(
            _row(
                common,
                row_kind="source_clause",
                item_id=item.get("clause_id", ""),
                item_version=item.get("clause_version", ""),
                item_kind="contract_clause",
                clause_id=item.get("clause_id", ""),
                clause_version=item.get("clause_version", ""),
                clause_key=item.get("clause_key", ""),
                source_version_id=item.get("source_version_id", ""),
                source_locator_id=item.get("source_locator_id", ""),
                evidence_link_ids=item.get("evidence_link_id", ""),
                authority_layer=item.get("authority_layer", ""),
            )
        )

    for item in _records(view.get("issues")):
        clause = clause_by_identity.get(
            (str(item.get("clause_id", "")), str(item.get("clause_version", ""))), {}
        )
        writer.writerow(
            _row(
                common,
                row_kind="issue",
                item_id=item.get("issue_id", ""),
                item_version=item.get("issue_version", ""),
                item_kind=item.get("issue_kind", ""),
                subject=item.get("subject", ""),
                severity=item.get("severity", ""),
                applicability=item.get("applicability", ""),
                clause_id=item.get("clause_id", ""),
                clause_version=item.get("clause_version", ""),
                clause_key=clause.get("clause_key", ""),
                source_version_id=clause.get("source_version_id", ""),
                source_locator_id=clause.get("source_locator_id", ""),
                evidence_link_ids=clause.get("evidence_link_id", ""),
                authority_layer=clause.get("authority_layer", ""),
                recommendation=item.get("recommendation_text", ""),
                consequence=item.get("consequence_code", ""),
                uncertainty_codes=item.get("uncertainty_code", ""),
            )
        )

    for item in _records(view.get("disagreement_items")):
        clause = clause_by_identity.get(
            (str(item.get("clause_id", "")), str(item.get("clause_version", ""))), {}
        )
        writer.writerow(
            _row(
                common,
                row_kind="disagreement_item",
                item_id=item.get("item_id", ""),
                item_version=item.get("protocol_version", ""),
                item_kind="proposed_contract_change",
                clause_id=item.get("clause_id", ""),
                clause_version=item.get("clause_version", ""),
                clause_key=clause.get("clause_key", ""),
                source_version_id=clause.get("source_version_id", ""),
                source_locator_id=clause.get("source_locator_id", ""),
                evidence_link_ids=_joined(item.get("evidence_link_ids")),
                authority_layer=clause.get("authority_layer", ""),
                proposed_clause_text=item.get("proposed_clause_text", ""),
                consequence=item.get("consequence_code", ""),
                uncertainty_codes=_joined(item.get("uncertainty_issue_ids")),
            )
        )

    for item in _records(view.get("revised_clauses")):
        clause = clause_by_identity.get(
            (
                str(item.get("source_clause_id", "")),
                str(item.get("source_clause_version", "")),
            ),
            {},
        )
        writer.writerow(
            _row(
                common,
                row_kind="revised_clause",
                item_id=item.get("revised_clause_id", ""),
                item_version=item.get("revised_contract_version", ""),
                item_kind="revised_contract_clause",
                clause_id=item.get("source_clause_id", ""),
                clause_version=item.get("source_clause_version", ""),
                clause_key=clause.get("clause_key", ""),
                source_version_id=clause.get("source_version_id", ""),
                source_locator_id=clause.get("source_locator_id", ""),
                evidence_link_ids=clause.get("evidence_link_id", ""),
                authority_layer=clause.get("authority_layer", ""),
                revised_clause_text=item.get("revised_text", ""),
            )
        )

    for item in _records(view.get("deliverables")):
        writer.writerow(
            _row(
                common,
                row_kind="deliverable",
                item_id=item.get("deliverable_id", ""),
                item_version=item.get("deliverable_version", ""),
                item_kind=item.get("deliverable_kind", ""),
                state=item.get("state", ""),
                blockers=_joined(item.get("blocker_issue_ids")),
                uncertainty_codes=_joined(item.get("uncertainty_issue_ids")),
            )
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _row(common: Mapping[str, Any], **values: Any) -> dict[str, str]:
    merged = {**common, **values}
    return {field: _safe_cell(merged.get(field, "")) for field in _FIELDS}


def _safe_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _joined(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(item) for item in value)
    return "" if value is None else str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return ()
    return (item for item in value if isinstance(item, Mapping))
