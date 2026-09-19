"""Deterministic professional-result assembly from the shared project model."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid5

from asd_kontur.application_spine.models import semantic_digest

from .models import MODE_EXPORTS, PilotMode

PILOT_NAMESPACE = UUID("0761c5eb-0253-45b7-b857-0350850655ce")


def build_pilot_result(
    *,
    workspace_id: UUID,
    workspace_name: str,
    mode: PilotMode,
    project: dict[str, Any],
    documents: Iterable[dict[str, Any]],
    support: dict[str, Any],
) -> dict[str, Any]:
    """Build one mode view without promoting candidates or inventing facts."""

    reconciliation = dict(project.get("reconciliation") or {})
    project_definition = dict(project.get("project_definition") or {})
    definition = dict(project_definition.get("definition") or {})
    fields = dict(definition.get("fields") or {})
    packages = [dict(item) for item in project.get("work_packages") or []]
    defects = [dict(item) for item in project.get("defects") or []]
    evidence_index = {
        str(key): dict(value) for key, value in dict(project.get("evidence_index") or {}).items()
    }
    document_rows = [dict(item) for item in documents]
    source_manifest = _source_manifest(document_rows)
    items = _mode_items(mode, packages, defects, document_rows, support, evidence_index)
    unresolved = sorted(
        {
            str(item["status"])
            for item in items
            if item["status"] in {"requires_clarification", "missing", "conflict", "cannot_prepare"}
        }
    )
    project_id = str(project_definition.get("project_definition_id") or "unavailable")
    project_version = int(project_definition.get("version") or 0)
    matrix = dict(project.get("matrix") or {})
    matrix_id = str(matrix.get("matrix_id") or "unavailable")
    matrix_version = int(matrix.get("version") or 0)
    result_id = uuid5(
        PILOT_NAMESPACE,
        f"pilot-result:{workspace_id}:{mode.value}:{project_id}:{project_version}:{matrix_id}:{matrix_version}",
    )
    payload: dict[str, Any] = {
        "result_id": str(result_id),
        "version": 1,
        "mode": mode.value,
        "workspace_id": str(workspace_id),
        "workspace_name": workspace_name,
        "project_definition_id": project_id,
        "project_definition_version": project_version,
        "matrix_id": matrix_id,
        "matrix_version": matrix_version,
        "project_status": str(reconciliation.get("terminal_status") or "not_formed"),
        "project_fields": fields,
        "summary": _summary(mode, items, packages, support),
        "items": items,
        "source_manifest": source_manifest,
        "unresolved_questions": unresolved,
        "available_exports": [item.value for item in MODE_EXPORTS[mode]],
        "normative_notice": "Актуальность редакций нормативных документов не проверена",
        "status": "draft_with_open_questions" if unresolved else "reviewed_draft",
    }
    payload["fingerprint"] = semantic_digest(payload)
    return payload


def _source_manifest(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": str(item["document_id"]),
            "version": int(item["version"]),
            "name": str(item["safe_display_name"]),
            "source_version_id": (
                str(item["source_version_id"]) if item.get("source_version_id") else None
            ),
            "digest": str(item["content_digest"]),
            "status": str(item["extraction_status"]),
        }
        for item in sorted(documents, key=lambda value: str(value["document_id"]))
    ]


def _mode_items(
    mode: PilotMode,
    packages: list[dict[str, Any]],
    defects: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    support: dict[str, Any],
    evidence_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if mode is PilotMode.TENDER:
        items = [_defect_item(mode, item, evidence_index) for item in defects]
        items.append(_contract_input_item(mode, documents))
        return items
    if mode is PilotMode.SUPPORT:
        requirements = [dict(item) for item in support.get("requirements") or []]
        items = [
            _item(
                mode,
                f"requirement:{item.get('document_requirement_id')}",
                _document_title(str(item.get("document_type") or "document")),
                "Документ включён в состав исполнительной документации для выбранной работы.",
                _support_status(item),
                tuple(str(value) for value in item.get("basis_refs") or []),
                _support_action(item),
            )
            for item in requirements
        ]
        return items or _package_items(mode, packages)
    if mode is PilotMode.AUDIT:
        items = [_defect_item(mode, item, evidence_index) for item in defects]
        items.extend(
            _item(
                mode,
                f"audit-input:{item['document_id']}",
                f"Исходный документ для аудита «{item['safe_display_name']}»",
                _audit_input_description(item),
                "requires_clarification",
                (),
                _audit_input_action(item),
            )
            for item in documents
        )
        return items
    memberships = [dict(item) for item in support.get("memberships") or []]
    items = [
        _item(
            mode,
            f"recovery:{item.get('membership_id')}",
            _document_title(str(item.get("role") or "document")),
            _recovery_description(item),
            _recovery_status(item),
            (),
            _recovery_action(item),
        )
        for item in memberships
        if str(item.get("role")) != "register"
    ]
    return items or _package_items(mode, packages)


def _package_items(mode: PilotMode, packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _item(
            mode,
            f"package:{item.get('work_package_id')}",
            str(dict(item.get("package") or {}).get("work_type", {}).get("normalized") or "Работа"),
            "Пакет работ сформирован из исходных документов.",
            "requires_clarification",
            tuple(
                str(value)
                for value in dict(item.get("package") or {}).get("source_locator_ids") or []
            ),
            "Уточнить состав восстанавливаемых документов.",
        )
        for item in packages
    ]


def _contract_input_item(mode: PilotMode, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose the contract-analysis boundary without inventing contract findings.

    A Tender result used to add a generic professional-review card regardless
    of whether a contract was admitted.  Document inventory is enough to say
    whether a contract source appears to be available, but it is not evidence
    for a clause-level conclusion.  Keep that distinction visible to the user.
    """

    contract_sources = [document for document in documents if _looks_like_contract_source(document)]
    if not contract_sources:
        return _item(
            mode,
            "contract_input_unavailable",
            "Договор не предоставлен для договорного анализа",
            "В составе принятых исходных документов не обнаружен договор или его проект. "
            "Анализ ПД и РД продолжается отдельно, но условия ответственности, сроков, "
            "приёмки и оплаты не сопоставлялись.",
            "requires_clarification",
            (),
            "Предоставить актуальную редакцию договора или проекта договора для отдельного "
            "сравнения и подготовки предложений по условиям.",
        )

    names = ", ".join(
        str(document.get("safe_display_name") or "документ") for document in contract_sources
    )
    return _item(
        mode,
        "contract_analysis_pending",
        "Договор предоставлен, но договорные условия ещё не извлечены",
        "В составе исходных документов обнаружены материалы, похожие на договор: "
        f"{names}. Их наличие не подтверждает проверку условий ответственности, сроков, "
        "приёмки и оплаты.",
        "requires_clarification",
        (),
        "Выполнить отдельное извлечение условий договора и сопоставить их с подтверждёнными "
        "проектными и сметными данными.",
    )


def _looks_like_contract_source(document: dict[str, Any]) -> bool:
    """Use only supplied document metadata to route, never to infer clauses."""

    reference = " ".join(
        str(document.get(key) or "") for key in ("safe_display_name", "relative_path")
    ).casefold()
    return any(token in reference for token in ("договор", "контракт", "contract"))


def _audit_input_description(document: dict[str, Any]) -> str:
    """Keep extraction/readiness evidence separate from an Audit conclusion."""

    if str(document.get("extraction_status")) == "complete":
        return (
            "Содержание документа доступно как вход для аудита. Проверки состава, формы, "
            "редакции, подписей, приложений и доказательств по этому документу ещё не выполнены."
        )
    return (
        "Содержание документа обработано не полностью; проверки состава, формы, редакции, "
        "подписей, приложений и доказательств пока невозможны."
    )


def _audit_input_action(document: dict[str, Any]) -> str:
    if str(document.get("extraction_status")) == "complete":
        return (
            "Запустить проверку ожидаемого и фактического состава; не считать извлечение "
            "результатом аудита."
        )
    return (
        "Восстановить обработку документа и затем выполнить проверку ожидаемого и "
        "фактического состава."
    )


def _defect_item(
    mode: PilotMode, defect: dict[str, Any], evidence_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    kind = str(defect.get("defect_kind") or "discrepancy")
    locators = tuple(str(value) for value in defect.get("source_locator_ids") or [])
    source_references = [
        _evidence_reference(value, evidence_index.get(value)) for value in locators
    ]
    description = _defect_description(kind)
    if source_references:
        description += " Источники: " + ", ".join(source_references) + "."
    item = _item(
        mode,
        f"defect:{defect.get('defect_id')}:{defect.get('version', 1)}",
        _defect_title(kind),
        description,
        "conflict" if "mismatch" in kind or "incompatible" in kind else "requires_clarification",
        locators,
        _defect_action(kind),
    )
    item["source_references"] = source_references
    return item


def _evidence_reference(locator_id: str, evidence: dict[str, Any] | None) -> str:
    """Render locator provenance for a user-facing result without losing identity."""

    if evidence is None:
        return f"неразрешённый фрагмент ({locator_id})"
    document = str(evidence.get("safe_display_name") or "исходный документ")
    version = evidence.get("document_version")
    location = str(
        evidence.get("locator_value") or evidence.get("locator_kind") or "место не указано"
    )
    suffix = f", версия {version}" if version is not None else ""
    return f"{document}{suffix}, {location}"


def _item(
    mode: PilotMode,
    key: str,
    title: str,
    description: str,
    status: str,
    source_locator_ids: tuple[str, ...],
    recommended_action: str,
) -> dict[str, Any]:
    identity = uuid5(PILOT_NAMESPACE, f"pilot-item:{mode.value}:{key}")
    return {
        "item_id": str(identity),
        "version": 1,
        "kind": key.split(":", 1)[0],
        "title": title,
        "description": description,
        "status": status,
        "source_locator_ids": list(source_locator_ids),
        "consequence": _consequence(status),
        "recommended_action": recommended_action,
        "responsible": "Не назначен",
        "resolution_status": "open",
    }


def _summary(
    mode: PilotMode,
    items: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    support: dict[str, Any],
) -> dict[str, Any]:
    open_count = sum(item["resolution_status"] == "open" for item in items)
    common = {"items": len(items), "open_questions": open_count, "work_packages": len(packages)}
    if mode is PilotMode.SUPPORT:
        readiness = dict(support.get("readiness") or {})
        common.update(
            {
                "required_documents": int(readiness.get("required_count") or 0),
                "finalized_documents": int(readiness.get("finalized_count") or 0),
                "missing_documents": int(readiness.get("missing_count") or 0),
                "blocked_documents": int(readiness.get("blocked_count") or 0),
            }
        )
    return common


def _support_status(item: dict[str, Any]) -> str:
    blockers = item.get("blockers") or []
    if blockers:
        return "missing" if "MISSING" in " ".join(map(str, blockers)) else "cannot_prepare"
    return str(item.get("requirement_state") or "requires_clarification")


def _support_action(item: dict[str, Any]) -> str:
    return (
        "Добавить отсутствующие исходные данные или документ."
        if item.get("blockers")
        else "Проверить состав документа и включить его в комплект."
    )


def _recovery_status(item: dict[str, Any]) -> str:
    if item.get("finalized_document_id"):
        return "original_or_finalized"
    if item.get("generated_candidate_id"):
        return "recoverable_draft"
    blockers = " ".join(str(value) for value in item.get("blocker_codes") or [])
    return "cannot_prepare" if blockers else "missing"


def _recovery_description(item: dict[str, Any]) -> str:
    status = _recovery_status(item)
    return {
        "original_or_finalized": "Финализированный документ найден в составе комплекта.",
        "recoverable_draft": "Проект документа сформирован, но ещё не финализирован.",
        "cannot_prepare": "Документ нельзя сформировать без отсутствующих исходных данных.",
        "missing": "Документ отсутствует; возможность восстановления требует проверки.",
    }[status]


def _recovery_action(item: dict[str, Any]) -> str:
    status = _recovery_status(item)
    if status == "original_or_finalized":
        return "Сохранить документ в восстанавливаемом комплекте."
    if status == "recoverable_draft":
        return "Проверить проект и выполнить предусмотренную финализацию."
    return "Получить недостающие подтверждённые сведения; не подставлять их предположением."


def _defect_title(kind: str) -> str:
    return {
        "quantity_mismatch": "Расхождение объёма между ВОР и сметой",
        "project_work_missing_in_estimate": "Работа проекта не учтена в смете",
        "project_material_missing_in_estimate": "Материал проекта не учтён в смете",
        "estimate_position_unsupported_by_project": "Позиция сметы не подтверждена проектом",
        "incompatible_units": "Несовместимые единицы измерения",
        "ambiguous_source_match": "Неоднозначное сопоставление источников",
        "drawing_intelligence_required": "Требуется проверка графической части",
        "normative_authority_unavailable": "Нормативное основание требует уточнения",
        "rule_coverage_unavailable": "Автоматическая проверка не поддержана",
    }.get(kind, "Требуется проверка исходных данных")


def _defect_description(kind: str) -> str:
    if kind == "quantity_mismatch":
        return "Для одной работы в исходных документах указаны разные объёмы."
    if "missing" in kind:
        return "Состав работ или материалов различается между исходными документами."
    return "Сведение нельзя принять без отдельного сопоставления исходных фрагментов."


def _defect_action(kind: str) -> str:
    if kind == "quantity_mismatch":
        return (
            "Сверить ВОР, смету и проект; зафиксировать согласованный объём новой версией сведения."
        )
    return "Открыть исходные фрагменты и принять решение специалиста."


def _consequence(status: str) -> str:
    return {
        "conflict": "Риск неверного объёма, стоимости или состава работ.",
        "missing": "Комплект или исходные данные остаются неполными.",
        "cannot_prepare": "Документ нельзя выпускать без недостающих фактов.",
        "requires_clarification": "Результат остаётся проектом до проверки специалистом.",
        "conforms": "Дополнительное действие не требуется.",
    }.get(status, "Требуется профессиональная проверка.")


def _document_title(role: str) -> str:
    return {
        "register": "Реестр документов комплекта",
        "support.aosr": "Акт освидетельствования скрытых работ",
        "aosr": "Акт освидетельствования скрытых работ",
        "executive_scheme": "Исполнительная схема",
        "quality_documents": "Документы о качестве материалов",
        "attachment": "Приложение к комплекту",
    }.get(role.lower(), role.replace("_", " ").capitalize())
