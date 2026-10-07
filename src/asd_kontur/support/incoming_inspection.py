"""Pre-admission incoming inspection of a construction material batch.

This checklist is a workspace-scoped professional preparation, never a
material-admission decision or a substitute for a physical observation.
"""

from __future__ import annotations

import csv
import io
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
_STATE_LABELS = {
    "passed": "Соответствует",
    "failed": "Несоответствие",
    "pending": "Ожидает проверки",
    "not_applicable": "Неприменимо",
}
_KIND_LABELS = {
    "document": "Проверка документов",
    "physical": "Фактический осмотр",
    "document_and_physical": "Документы и фактический осмотр",
    "record": "Учётная запись",
}
_OUTCOME_LABELS = {
    "nonconforming": "Несоответствие — партию изолировать",
    "incomplete": "Проверка не завершена",
    "ready_for_authorized_admission_review": "Подготовлено к решению ответственного лица",
}
_ACTION_LABELS = {
    "isolate_batch_and_resolve_nonconformity": "Изолировать партию и устранить несоответствие",
    "perform_or_obtain_check": "Выполнить проверку или получить документ",
    "record_evidence_or_applicability_basis": "Указать подтверждение или основание неприменимости",
}


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


def render_incoming_inspection_register(records: Sequence[Mapping[str, Any]]) -> bytes:
    """Export every recorded check without presenting a preflight as admission."""

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        (
            "Дата записи",
            "Материал",
            "Партия / накладная",
            "Проверка",
            "Вид проверки",
            "Результат",
            "Основание / замечание",
            "Итог по партии",
            "Допуск к применению",
            "Необходимое действие",
        )
    )
    for record in records:
        result = record.get("result")
        if not isinstance(result, Mapping) or result.get("hold_for_use") is not True:
            raise ValueError("incoming_inspection_register_result_invalid")
        checks = result.get("checks")
        if not isinstance(checks, list) or len(checks) != len(INCOMING_CHECKS):
            raise ValueError("incoming_inspection_register_checks_invalid")
        expected = {key: (label, kind) for key, label, kind in INCOMING_CHECKS}
        actions = result.get("actions")
        if not isinstance(actions, list):
            raise ValueError("incoming_inspection_register_actions_invalid")
        actions_by_check: dict[str, list[str]] = {}
        for action in actions:
            if not isinstance(action, Mapping):
                raise ValueError("incoming_inspection_register_actions_invalid")
            key = str(action.get("check_key") or "")
            action_code = str(action.get("action") or "")
            if key not in expected or action_code not in _ACTION_LABELS:
                raise ValueError("incoming_inspection_register_actions_invalid")
            actions_by_check.setdefault(key, []).append(_ACTION_LABELS[action_code])
        outcome = str(result.get("outcome") or "")
        if outcome not in _OUTCOME_LABELS:
            raise ValueError("incoming_inspection_register_result_invalid")
        submitted_at = record.get("submitted_at")
        submitted = (
            submitted_at.isoformat()
            if hasattr(submitted_at, "isoformat")
            else str(submitted_at or "")
        )
        seen: set[str] = set()
        for check in checks:
            if not isinstance(check, Mapping):
                raise ValueError("incoming_inspection_register_checks_invalid")
            key = str(check.get("key") or "")
            state = str(check.get("state") or "")
            if (
                key not in expected
                or key in seen
                or (check.get("label"), check.get("kind")) != expected[key]
                or state not in _STATE_LABELS
            ):
                raise ValueError("incoming_inspection_register_checks_invalid")
            seen.add(key)
            writer.writerow(
                (
                    _csv_cell(submitted),
                    _csv_cell(record.get("material_name")),
                    _csv_cell(record.get("batch_reference")),
                    _csv_cell(check.get("label")),
                    _KIND_LABELS[str(check["kind"])],
                    _STATE_LABELS[state],
                    _csv_cell(check.get("basis")),
                    _OUTCOME_LABELS[outcome],
                    "Материал не допущен — требуется решение ответственного лица",
                    "; ".join(actions_by_check.get(key, ())),
                )
            )
        if seen != expected.keys():
            raise ValueError("incoming_inspection_register_checks_invalid")
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _csv_cell(value: object) -> str:
    text = str(value or "")
    # Spreadsheet applications must not execute formulas from user-entered text.
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
