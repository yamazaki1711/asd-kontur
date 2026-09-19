"""Reusable expected-versus-package preflight for the Audit user workflow.

This projection deliberately does *not* write the canonical Audit ledger.  The
ledger is owned by the separately-scoped ``asd_audit_service`` role, whereas
the Product Spine runs as the workspace application role.  The preflight gives
an authorised workspace owner a truthful, useful comparison before an Audit
process is started: a generated or finalised Support document is evidence of a
package member, not proof that the document passed an independent audit.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def build_expected_actual_preflight(
    requirements: Iterable[Mapping[str, Any]],
    *,
    matrix: Mapping[str, Any] | None,
    package: Mapping[str, Any] | None,
    memberships: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare exact matrix requirement versions to the formed ID package.

    Comparison is intentionally by immutable requirement identity *and*
    version.  Human-readable role names are neither keys nor a fallback: two
    locations may legitimately require documents with the same title.

    A membership has no independent source-document inspection or Audit
    authority decision, so this routine never returns ``satisfied``.  It keeps
    the user-visible distinction between a missing package position, a
    generated candidate, and a document that still awaits formal audit.
    """

    requirement_rows = tuple(dict(value) for value in requirements)
    membership_rows = tuple(dict(value) for value in memberships)
    by_requirement: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for member in membership_rows:
        requirement_id = member.get("document_requirement_id")
        requirement_version = member.get("document_requirement_version")
        if requirement_id is None or requirement_version is None:
            continue
        by_requirement[(str(requirement_id), int(requirement_version))].append(member)

    items: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    global_gaps: set[str] = set()
    if matrix is None:
        global_gaps.add("WORK_REQUIREMENT_MATRIX_UNAVAILABLE")
    if package is None:
        global_gaps.add("ID_PACKAGE_NOT_FORMED")

    for requirement in requirement_rows:
        requirement_id = str(requirement.get("document_requirement_id", ""))
        requirement_version = int(requirement.get("document_requirement_version", 1))
        key = (requirement_id, requirement_version)
        linked = tuple(
            sorted(
                by_requirement.get(key, ()),
                key=lambda item: (int(item.get("ordinal", 0)), str(item.get("membership_id", ""))),
            )
        )
        state, gaps = _item_state(requirement, linked, package_available=package is not None)
        counts[state] += 1
        global_gaps.update(gaps)
        item_key = (
            f"{requirement.get('work_package_id', '')}:{requirement_id}:v{requirement_version}"
        )
        items.append(
            {
                "item_key": item_key,
                "work_package_id": str(requirement.get("work_package_id", "")),
                "document_requirement_id": requirement_id,
                "document_requirement_version": requirement_version,
                "document_type": str(requirement.get("document_type", "")),
                "required_stage": str(requirement.get("required_stage", "")),
                "requirement_state": str(requirement.get("requirement_state", "unresolved")),
                "authority_status": str(requirement.get("authority_status", "normative_gap")),
                "expected_copies": int(requirement.get("minimum_copies", 1)),
                "preflight_state": state,
                "membership_count": len(linked),
                "membership_states": sorted({str(member.get("state", "")) for member in linked}),
                "membership_ids": [str(member.get("membership_id", "")) for member in linked],
                "generated_candidate_ids": sorted(
                    str(member["generated_candidate_id"])
                    for member in linked
                    if member.get("generated_candidate_id") is not None
                ),
                "finalized_document_ids": sorted(
                    str(member["finalized_document_id"])
                    for member in linked
                    if member.get("finalized_document_id") is not None
                ),
                "evidence_refs": _evidence_refs(requirement, linked),
                "gaps": sorted(gaps),
                "audit_boundary": "independent_audit_evidence_and_authority_required",
            }
        )

    status = "not_started" if matrix is None else "partial"
    return {
        "assessment_kind": "expected_vs_package_preflight",
        "status": status,
        "matrix": dict(matrix) if matrix is not None else None,
        "package": _package_reference(package),
        "items": items,
        "counts": dict(sorted(counts.items())),
        "gaps": sorted(global_gaps),
        "authority_layers": {
            "package_membership": "workspace_candidate_or_finalized_document",
            "audit_conclusion": "requires_independent_audit_process",
            "not_claimed": "no_preflight_item_is_audit_satisfied",
        },
    }


def _item_state(
    requirement: Mapping[str, Any],
    members: tuple[Mapping[str, Any], ...],
    *,
    package_available: bool,
) -> tuple[str, set[str]]:
    gaps = {str(value) for value in requirement.get("blockers", ())}
    if str(requirement.get("requirement_state", "unresolved")) != "required":
        gaps.add("REQUIREMENT_AUTHORITY_UNRESOLVED")
        return "unresolved_requirement", gaps
    if not package_available:
        gaps.add("ID_PACKAGE_NOT_FORMED")
        return "not_formed", gaps
    if not members:
        gaps.add("REQUIRED_DOCUMENT_NOT_IN_PACKAGE")
        return "missing", gaps
    states = {str(member.get("state", "")) for member in members}
    for member in members:
        gaps.update(str(value) for value in member.get("blocker_codes", ()))
    if "blocked" in states:
        return "blocked", gaps
    if "conflict" in states:
        return "conflict", gaps
    if "missing" in states:
        return "missing", gaps
    if "generated_candidate" in states:
        gaps.add("GENERATED_CANDIDATE_REQUIRES_AUDIT")
        return "generated_candidate", gaps
    if "finalized" in states or any(member.get("finalized_document_id") for member in members):
        gaps.add("FINALIZED_DOCUMENT_REQUIRES_AUDIT")
        return "awaiting_audit", gaps
    gaps.add("PACKAGE_MEMBERSHIP_EVIDENCE_INDETERMINATE")
    return "indeterminate", gaps


def _evidence_refs(
    requirement: Mapping[str, Any], members: tuple[Mapping[str, Any], ...]
) -> list[str]:
    refs = [str(value) for value in requirement.get("basis_refs", ())]
    refs.extend(str(value) for member in members for value in member.get("evidence_refs", ()))
    return list(dict.fromkeys(refs))


def _package_reference(package: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if package is None:
        return None
    return {
        "id_package_id": str(package.get("id_package_id", "")),
        "version": int(package.get("version", 0)),
        "status": str(package.get("status", "")),
        "work_package_id": str(package.get("work_package_id", "")),
    }
