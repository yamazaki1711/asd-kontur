"""Turn an expected-versus-package preflight into a non-fabricating plan."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def build_recovery_plan(preflight: Mapping[str, Any]) -> dict[str, Any]:
    """Build ordered recovery actions without inventing project or field facts.

    The plan retains the exact requirement identity and evidence references from
    the preflight.  A missing document is never represented as eligible for
    generation: that would make a document-shaped artefact look like evidence
    of work, signatures, measurements, or tests that are not present.
    """

    recoverable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in _items(preflight.get("items", ())):
        state = str(item.get("preflight_state", "indeterminate"))
        action = _action_for(state)
        record = {
            "item_key": str(item.get("item_key", "")),
            "work_package_id": str(item.get("work_package_id", "")),
            "document_requirement_id": str(item.get("document_requirement_id", "")),
            "document_requirement_version": int(item.get("document_requirement_version", 1)),
            "document_type": str(item.get("document_type", "")),
            "preflight_state": state,
            "action": action[0],
            "required_input": action[1],
            "evidence_refs": [str(value) for value in item.get("evidence_refs", ())],
            "blocker_codes": [str(value) for value in item.get("gaps", ())],
            "fabrication_prohibited": True,
        }
        (recoverable if action[2] else blocked).append(record)

    return {
        "plan_kind": "id_package_recovery_plan",
        "status": "partial" if recoverable else "blocked",
        "basis": {
            "assessment_kind": str(preflight.get("assessment_kind", "")),
            "matrix": preflight.get("matrix"),
            "package": preflight.get("package"),
        },
        "recoverable_actions": recoverable,
        "blocked_actions": blocked,
        "global_blockers": [str(value) for value in preflight.get("gaps", ())],
        "authority_boundary": (
            "candidate_documents_and_recovery_plans_do_not_confirm_execution, "
            "measurements, tests, dates, signatures, or acceptance"
        ),
    }


def _action_for(state: str) -> tuple[str, str, bool]:
    if state == "generated_candidate":
        return (
            "review_candidate_against_available_evidence",
            "authorised review decision and any missing required field evidence",
            True,
        )
    if state == "awaiting_audit":
        return (
            "start_independent_document_audit",
            "source-document inspection, authority decision, and audit evidence",
            True,
        )
    if state in {"missing", "not_formed"}:
        return (
            "collect_missing_source_evidence",
            "actual document, field fact, test record, measurement, date, "
            "or signature as applicable",
            False,
        )
    if state == "unresolved_requirement":
        return (
            "resolve_requirement_authority",
            "applicable project, customer, contract, or verified normative basis",
            False,
        )
    return (
        "resolve_evidence_or_relationship",
        "exact evidence and scope relationship for the requirement",
        False,
    )


def _items(values: Iterable[object]) -> Iterable[Mapping[str, Any]]:
    return (value for value in values if isinstance(value, Mapping))
