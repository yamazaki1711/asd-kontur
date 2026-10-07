"""Pre-admission incoming inspection of a construction material batch.

This checklist is a workspace-scoped professional preparation, never a
material-admission decision or a substitute for a physical observation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

INCOMING_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("quality_documents", "Паспорта и сертификаты", "document"),
    ("specified_standard", "Соответствие стандарту или техническим условиям", "document"),
    ("marking", "Маркировка партии", "physical"),
    ("visual_condition", "Визуальное состояние", "physical"),
    ("shelf_life", "Срок годности", "document_and_physical"),
    ("delivery_quantity", "Количество по накладной", "document_and_physical"),
    ("storage_conditions", "Условия хранения", "physical"),
    ("incoming_log", "Запись в журнале входного контроля", "record"),
)
_ALLOWED_STATES = frozenset({"passed", "failed", "pending", "not_applicable"})


def evaluate_incoming_inspection(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return exact checklist actions without asserting human or legal authority."""

    keyed: dict[str, Mapping[str, Any]] = {}
    for check in checks:
        key = str(check.get("key") or "")
        if key in keyed:
            raise ValueError("incoming_inspection_duplicate_check")
        keyed[key] = check
    if set(keyed) != {key for key, _label, _kind in INCOMING_CHECKS}:
        raise ValueError("incoming_inspection_check_set_invalid")

    rows: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []
    failed = False
    incomplete = False
    for key, label, kind in INCOMING_CHECKS:
        check = keyed[key]
        state = str(check.get("state") or "")
        basis = " ".join(str(check.get("basis") or "").split())
        if state not in _ALLOWED_STATES or len(basis) > 600:
            raise ValueError("incoming_inspection_check_invalid")
        rows.append({"key": key, "label": label, "kind": kind, "state": state, "basis": basis})
        if state == "failed":
            failed = True
            actions.append({"check_key": key, "action": "isolate_batch_and_resolve_nonconformity"})
        elif state == "pending":
            incomplete = True
            actions.append({"check_key": key, "action": "perform_or_obtain_check"})
        if state != "pending" and len(basis) < 3:
            incomplete = True
            actions.append({"check_key": key, "action": "record_evidence_or_applicability_basis"})

    outcome = (
        "nonconforming"
        if failed
        else "incomplete"
        if incomplete
        else "ready_for_authorized_admission_review"
    )
    result: dict[str, Any] = {
        "outcome": outcome,
        "hold_for_use": True,
        "checks": rows,
        "actions": actions,
        "checked_count": sum(row["state"] != "pending" for row in rows),
        "total_count": len(INCOMING_CHECKS),
        "authority_boundary": (
            "reported_preflight_only; physical_observations_and_material_admission_"
            "require_responsible_person_confirmation"
        ),
    }
    result["fingerprint"] = semantic_digest(result)
    return result
