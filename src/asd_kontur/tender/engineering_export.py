"""Editable project-first Tender outputs from the shared engineering model."""

# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape

from .findings_report import _docx_package


def render_engineering_work_schedule_csv(model: Mapping[str, Any]) -> bytes:
    """Render the professional work/quantity/material schedule."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "Сооружение / место",
            "Семейство работ",
            "Работа",
            "Формулировка проекта",
            "Документ",
            "Объём",
            "Единица",
            "Материалы",
            "Статус",
            "Источники",
            "work_package_id",
            "candidate_status",
            "source_references",
        ),
    )
    writer.writeheader()
    for work in model.get("works") or ():
        row = dict(work)
        quantities = dict(row.get("quantities_by_document") or {})
        materials = dict(row.get("materials_by_document") or {})
        roles = sorted({*quantities, *materials}) or ["Проектный документ"]
        for role in roles:
            quantity_values = [dict(value) for value in quantities.get(role) or ()]
            material_values = [dict(value) for value in materials.get(role) or ()]
            if not quantity_values:
                quantity_values = [{}]
            for quantity in quantity_values:
                writer.writerow(
                    {
                        "Сооружение / место": row.get("facility") or "Требует уточнения",
                        "Семейство работ": row.get("work_family") or "",
                        "Работа": row.get("work_name") or "",
                        "Формулировка проекта": "; ".join(
                            str(value) for value in row.get("project_wording") or ()
                        ),
                        "Документ": role,
                        "Объём": quantity.get("value") or "не найдено",
                        "Единица": quantity.get("unit") or "",
                        "Материалы": "; ".join(
                            str(value.get("name") or "") for value in material_values
                        ),
                        "Статус": row.get("status") or "",
                        "Источники": _source_labels(row),
                        "work_package_id": row.get("work_package_id") or "",
                        "candidate_status": "candidate",
                        "source_references": "; ".join(
                            str(value) for value in row.get("source_locator_ids") or ()
                        ),
                    }
                )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def render_engineering_findings_csv(model: Mapping[str, Any]) -> bytes:
    """Render only professional issues, risks and contractor actions."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "№",
            "Вид вопроса",
            "Место",
            "Предмет",
            "Вывод",
            "Практическое последствие",
            "Действие / вопрос Заказчику",
            "Статус",
            "Источники / source_references",
        ),
    )
    writer.writeheader()
    issues = [
        *[dict(value) for value in model.get("issues") or () if isinstance(value, Mapping)],
        *_contract_finding_rows(model),
    ]
    for ordinal, row in enumerate(issues, start=1):
        writer.writerow(
            {
                "№": ordinal,
                "Вид вопроса": row.get("kind") or "Инженерный вопрос",
                "Место": row.get("location") or "Требует уточнения",
                "Предмет": row.get("subject") or "",
                "Вывод": row.get("description") or "",
                "Практическое последствие": row.get("practical_consequence") or "",
                "Действие / вопрос Заказчику": row.get("recommended_action") or "",
                "Статус": row.get("status") or "",
                "Источники / source_references": _source_labels(row),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def render_engineering_tender_report_docx(model: Mapping[str, Any]) -> bytes:
    """Render an adaptive editable Tender report in construction language."""

    project = dict(model.get("project") or {})
    name = dict(project.get("name") or {}).get("value") or "Наименование уточняется"
    purpose = dict(project.get("purpose") or {}).get("value") or "Назначение уточняется"
    description = dict(project.get("description") or {}).get("value")
    location = dict(project.get("location") or {}).get("value")
    foundation = dict(project.get("foundation") or {}).get("value")
    pits = dict(model.get("pits") or {})
    pit_answer = (
        pits.get("professional_answer")
        if pits.get("established_count") != 0 or pits.get("unresolved_group_count") != 0
        else None
    )
    body: list[str] = [
        _heading("Первичный анализ проекта", level=1),
        _paragraph(str(name)),
        _heading("1. Общая характеристика проекта"),
        _paragraph(str(description or purpose)),
        *([_paragraph(f"Место строительства: {location}")] if location else []),
        *([_paragraph(f"Конструктивная схема: {foundation}")] if foundation else []),
        *([_paragraph(str(pit_answer))] if pit_answer else []),
        _heading("Состав исходных документов"),
        _paragraph(
            str(
                dict(model.get("document_composition") or {}).get("professional_summary")
                or "Состав исходных документов требует уточнения."
            )
        ),
    ]
    section = 2

    def add_section(title: str, content: list[str]) -> None:
        nonlocal section
        body.append(_heading(f"{section}. {title}"))
        body.extend(content)
        section += 1

    def add_context_section(model_key: str, title: str) -> None:
        values = [dict(value) for value in model.get(model_key) or ()]
        if values:
            add_section(
                title,
                [
                    _simple_table(
                        ("Показатель", "Значение"),
                        [
                            (
                                str(value.get("label") or ""),
                                str(value.get("value") or ""),
                            )
                            for value in values
                        ],
                    )
                ],
            )

    add_context_section("participants", "Участники проекта")
    add_context_section("commercial_conditions", "Коммерческие условия / цена")
    add_context_section("time_requirements", "Сроки")
    add_context_section("procurement_requirements", "Требования закупки")
    add_context_section("contract_conditions", "Договорные условия и гарантии")

    primary_findings = _primary_tender_conclusions(model)
    if primary_findings:
        add_section(
            "Ключевые выводы для участия в тендере",
            [_bullet_list(primary_findings, empty="")],
        )

    facilities = list(model.get("facilities") or ())
    if facilities:
        add_section(
            "Состав объекта",
            [
                _simple_table(
                    ("Сооружение / участок", "Тип", "Статус"),
                    [
                        (
                            str(row.get("name") or ""),
                            str(row.get("kind") or ""),
                            str(row.get("status") or ""),
                        )
                        for row in facilities
                    ],
                )
            ],
        )
    facility_cards = list(model.get("facility_cards") or ())
    if facility_cards:
        add_section(
            "Сооружения",
            [
                _simple_table(
                    (
                        "Сооружение",
                        "Основные характеристики",
                        "Котлованы",
                        "Конструкции и подключения",
                        "Основные работы",
                        "Нерешённые вопросы",
                    ),
                    [
                        (
                            str(dict(row.get("facility") or {}).get("name") or ""),
                            "; ".join(
                                f"{value.get('label')}: {value.get('value')}"
                                for value in row.get("characteristics") or ()
                            )
                            or "не установлены",
                            ", ".join(
                                str(value.get("name") or "") for value in row.get("pits") or ()
                            )
                            or "не установлен / не предусмотрен",
                            ", ".join(
                                str(value.get("name") or "")
                                for value in [
                                    *(row.get("structures") or ()),
                                    *(row.get("connections") or ()),
                                ]
                            )
                            or "требуют привязки",
                            ", ".join(
                                str(value.get("work_name") or "")
                                for value in row.get("works") or ()
                            )
                            or "требуют привязки",
                            "; ".join(str(value) for value in row.get("missing_information") or ()),
                        )
                        for row in facility_cards
                    ],
                )
            ],
        )
    works = list(model.get("works") or ())
    if works:
        add_section(
            "Основные виды работ",
            [
                _simple_table(
                    ("Место", "Работа", "Объёмы по документам", "Материалы"),
                    [
                        (
                            str(row.get("facility") or "Требует уточнения"),
                            str(row.get("work_name") or ""),
                            _role_values(row.get("quantities_by_document")),
                            _role_materials(row.get("materials_by_document")),
                        )
                        for row in works
                    ],
                )
            ],
        )
    quantity_rows = [
        (
            str(work.get("facility") or "Требует привязки"),
            str(work.get("work_name") or ""),
            str(role),
            " ".join(
                str(part)
                for part in (quantity.get("value"), quantity.get("unit"))
                if part not in (None, "")
            ),
        )
        for work in works
        for role, quantities in dict(work.get("quantities_by_document") or {}).items()
        for quantity in quantities or ()
    ]
    if quantity_rows:
        add_section(
            "Основные объёмы",
            [_simple_table(("Место", "Работа", "Документ", "Объём"), quantity_rows)],
        )
    sheet_pile_schedule = list(model.get("sheet_pile_schedule") or ())
    if sheet_pile_schedule:
        add_section(
            "Шпунтовые работы",
            [
                _simple_table(
                    (
                        "Сооружение / котлован",
                        "Операция",
                        "Объёмы по документам",
                        "Ограничение",
                    ),
                    [
                        (
                            " — ".join(
                                value
                                for value in (
                                    str(row.get("facility") or "Требует привязки"),
                                    str(row.get("pit") or ""),
                                )
                                if value
                            ),
                            str(row.get("operation") or ""),
                            _role_values(row.get("quantities_by_document")),
                            str(row.get("uncertainty") or ""),
                        )
                        for row in sheet_pile_schedule
                    ],
                )
            ],
        )
    materials = list(model.get("materials") or ())
    if materials:
        add_section(
            "Материалы",
            [
                _simple_table(
                    ("Место", "Работа", "Документ", "Материал"),
                    [
                        (
                            str(row.get("facility") or "Требует уточнения"),
                            str(row.get("work") or ""),
                            str(row.get("document_role") or ""),
                            " ".join(
                                str(value)
                                for value in (row.get("name"), row.get("quantity"), row.get("unit"))
                                if value not in (None, "")
                            ),
                        )
                        for row in materials
                    ],
                    empty="Материалы по установленным работам не найдены.",
                )
            ],
        )
    comparison_rows = _engineering_comparison_rows(model)
    if comparison_rows:
        add_section(
            "Расхождения проектных и коммерческих документов",
            [_simple_table(("Место", "Работа", "Сравнение", "Вывод"), comparison_rows)],
        )
    scope_comparisons = list(model.get("scope_comparisons") or ())
    if scope_comparisons:
        add_section(
            "Возможные неучтённые работы",
            [
                _simple_table(
                    ("Место", "Работа", "Результат сопоставления", "Вывод"),
                    [
                        (
                            str(row.get("facility") or "Требует уточнения"),
                            str(row.get("work") or ""),
                            str(row.get("professional_status") or ""),
                            str(row.get("conclusion") or ""),
                        )
                        for row in scope_comparisons
                        if row.get("classification")
                        in {"WORK_MISSING_IN_COMMERCIAL", "COMMERCIAL_ONLY_WORK"}
                    ],
                    empty=(
                        "В установленном объёме доказанные неучтённые работы не выявлены; "
                        "незавершённые сопоставления перечислены в неопределённостях."
                    ),
                )
            ],
        )
    issues = list(model.get("issues") or ())
    if issues:
        add_section("Технические противоречия", [_issue_table(issues)])
    contract = dict(model.get("contract_analysis") or {})
    contract_issues = _contract_issue_rows(contract)
    if contract_issues:
        add_section(
            "Договорные риски Подрядчика",
            [
                _simple_table(
                    (
                        "Пункт договора",
                        "Редакция Заказчика",
                        "Риск Подрядчика",
                        "Практическое последствие",
                        "Рекомендуемое действие",
                    ),
                    [
                        (
                            row["clause_label"],
                            row["source_text"],
                            row["description"],
                            row["practical_consequence"],
                            row["recommended_action"],
                        )
                        for row in contract_issues
                    ],
                )
            ],
        )
    proposed_changes = _contract_proposed_change_rows(contract)
    if proposed_changes:
        add_section(
            "Предлагаемые изменения договора",
            [
                _simple_table(
                    (
                        "Пункт договора",
                        "Редакция Заказчика",
                        "Редакция Подрядчика",
                        "Практическая причина",
                    ),
                    [
                        (
                            row["clause_label"],
                            row["source_text"],
                            row["proposed_text"],
                            row["reason"],
                        )
                        for row in proposed_changes
                    ],
                )
            ],
        )
    requirements = dict(model.get("requirements") or {})
    if requirements.get("professional_summary") or requirements.get("unresolved"):
        add_section(
            "Нормативные вопросы",
            [
                _paragraph(str(requirements.get("professional_summary") or "")),
                _bullet_list(
                    [str(value) for value in requirements.get("unresolved") or ()],
                    empty="Нормативные вопросы не установлены.",
                ),
            ],
        )
    questions = [str(row.get("question") or "") for row in model.get("customer_questions") or ()]
    if any(questions):
        add_section("Вопросы Заказчику", [_bullet_list(questions, empty="")])
    risks = [str(row.get("risk") or "") for row in model.get("risks") or ()]
    if any(risks):
        add_section("Риски Подрядчика", [_bullet_list(risks, empty="")])
    uncertainties = (
        [
            str(value.get("reason") or value.get("description") or "")
            for value in pits.get("requires_clarification") or ()
        ]
        + [str(value) for value in project.get("missing_information") or ()]
        + [
            str(value.get("reason") or "")
            for value in dict(model.get("unresolved") or {}).get("participants") or ()
        ]
        + _quantity_relationship_uncertainties(
            dict(model.get("unresolved") or {}).get("quantities")
        )
        + _scope_comparison_uncertainties(scope_comparisons)
    )
    if any(uncertainties):
        add_section(
            "Неопределённости / недостающие данные",
            [_bullet_list(uncertainties, empty="")],
        )
    documents = list(model.get("documents") or ())
    if documents:
        body.extend(
            [
                _heading("Список исходных документов"),
                _bullet_list(
                    [
                        f"{row.get('name')} (версия {row.get('version')}; "
                        f"{row.get('document_role')})"
                        for row in documents
                    ],
                    empty="",
                ),
            ]
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return _docx_package(document.encode())


def _primary_tender_conclusions(model: Mapping[str, Any]) -> list[str]:
    """Return a bounded professional synopsis before the detailed schedules."""

    rows: list[str] = []
    seen: set[str] = set()

    def add(row: str) -> None:
        key = " ".join(row.casefold().split())
        if key and key not in seen:
            seen.add(key)
            rows.append(row)

    for raw in model.get("issues") or ():
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind") or "Технический вопрос").strip()
        location = str(raw.get("location") or "").strip()
        description = str(raw.get("description") or "").strip()
        action = str(raw.get("recommended_action") or "").strip()
        if not description:
            continue
        prefix = f"{kind} ({location})" if location else kind
        add(f"{prefix}: {description}" + (f" Действие: {action}" if action else ""))
    contract = dict(model.get("contract_analysis") or {})
    for row in _contract_issue_rows(contract):
        clause = str(row.get("clause_label") or "").strip()
        description = str(row.get("description") or "").strip()
        action = str(row.get("recommended_action") or "").strip()
        if not description:
            continue
        prefix = f"Договор, пункт {clause}" if clause else "Договорный риск"
        add(f"{prefix}: {description}" + (f" Действие: {action}" if action else ""))
    return rows[:10]


def _engineering_comparison_rows(model: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
    rows = [
        (
            str(row.get("facility") or ""),
            str(row.get("work") or ""),
            f"{_operand(row.get('left'))}; {_operand(row.get('right'))}",
            str(row.get("conclusion") or ""),
        )
        for row in model.get("quantity_comparisons") or ()
    ]
    rows.extend(
        (
            str(row.get("facility") or ""),
            str(row.get("work") or ""),
            str(row.get("material") or "Материал"),
            str(row.get("description") or ""),
        )
        for row in model.get("material_comparisons") or ()
    )
    return rows


def _contract_issue_rows(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    clauses = {
        str(row.get("clause_id")): dict(row)
        for value in contract.get("clauses") or ()
        if isinstance(value, Mapping)
        for row in (dict(value),)
    }
    rows: list[dict[str, Any]] = []
    for value in contract.get("issues") or ():
        if not isinstance(value, Mapping):
            continue
        issue = dict(value)
        clause = clauses.get(str(issue.get("clause_id")), {})
        rows.append(
            {
                "clause_label": str(
                    clause.get("clause_key") or clause.get("locator_label") or "Пункт не указан"
                ),
                "source_text": str(clause.get("source_text") or "Исходная редакция не извлечена"),
                "description": str(issue.get("description") or issue.get("subject") or ""),
                "practical_consequence": str(issue.get("consequence_code") or ""),
                "recommended_action": str(issue.get("recommendation_text") or ""),
                "severity": str(issue.get("severity") or ""),
                "uncertainty": str(issue.get("uncertainty_code") or ""),
                "source_version_id": str(clause.get("source_version_id") or ""),
                "source_locator_ids": [
                    str(item) for item in clause.get("source_locator_ids") or ()
                ],
            }
        )
    return rows


def _contract_proposed_change_rows(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    clauses = {
        str(row.get("clause_id")): dict(row)
        for value in contract.get("clauses") or ()
        if isinstance(value, Mapping)
        for row in (dict(value),)
    }
    issues = {
        str(row.get("issue_id")): dict(row)
        for value in contract.get("issues") or ()
        if isinstance(value, Mapping)
        for row in (dict(value),)
    }
    rows: list[dict[str, str]] = []
    for value in contract.get("disagreement_items") or ():
        if not isinstance(value, Mapping):
            continue
        item = dict(value)
        clause = clauses.get(str(item.get("clause_id")), {})
        issue = issues.get(str(item.get("issue_id")), {})
        rows.append(
            {
                "clause_label": str(
                    clause.get("clause_key") or clause.get("locator_label") or "Пункт не указан"
                ),
                "source_text": str(clause.get("source_text") or "Исходная редакция не извлечена"),
                "proposed_text": str(item.get("proposed_clause_text") or ""),
                "reason": str(
                    issue.get("description")
                    or item.get("consequence_code")
                    or "Требуется согласование условий"
                ),
            }
        )
    return rows


def _contract_finding_rows(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "Договорный риск",
            "location": row["clause_label"],
            "subject": row["source_text"],
            "description": row["description"],
            "practical_consequence": row["practical_consequence"],
            "recommended_action": row["recommended_action"],
            "status": "Кандидат для проверки",
            "source_locator_ids": row["source_locator_ids"],
        }
        for row in _contract_issue_rows(dict(model.get("contract_analysis") or {}))
    ]


def render_engineering_disagreement_protocol_docx(model: Mapping[str, Any]) -> bytes:
    """Render an editable contractor disagreement protocol from real findings."""

    project = dict(model.get("project") or {})
    name = dict(project.get("name") or {}).get("value") or "Наименование уточняется"
    issues = [dict(value) for value in model.get("issues") or () if isinstance(value, Mapping)]
    body = [
        _heading("Протокол разногласий к исходным данным Тендера", level=1),
        _paragraph(str(name)),
        _paragraph(
            "Рабочий редактируемый документ. Позиции сформированы из установленных "
            "инженерных вопросов проекта; графа Заказчика оставлена для согласования."
        ),
        _simple_table(
            (
                "№",
                "Место / сооружение",
                "Предмет разногласия",
                "Выявленное расхождение или неопределённость",
                "Последствие для Подрядчика",
                "Предложение / запрос Подрядчика",
                "Позиция Заказчика",
                "Источники",
            ),
            [
                (
                    str(index),
                    str(row.get("location") or "Требует уточнения"),
                    str(row.get("subject") or row.get("kind") or ""),
                    str(row.get("description") or ""),
                    str(row.get("practical_consequence") or ""),
                    str(row.get("recommended_action") or ""),
                    "",
                    _source_labels(row),
                )
                for index, row in enumerate(issues, start=1)
            ],
            empty="Инженерные разногласия пока не установлены.",
        ),
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" '
        'w:orient="landscape"/><w:pgMar w:top="850" w:right="850" w:bottom="850" '
        'w:left="850" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return _docx_package(document.encode())


def _scope_comparison_uncertainties(rows: object) -> list[str]:
    counts: dict[str, int] = {}
    for raw in rows if isinstance(rows, (list, tuple)) else ():
        if not isinstance(raw, Mapping) or raw.get("classification") != "UNRESOLVED_SCOPE_MATCH":
            continue
        status = str(raw.get("professional_status") or "Сопоставление объёма требует уточнения")
        counts[status] = counts.get(status, 0) + 1
    return [f"{status}: {count} поз." for status, count in sorted(counts.items())]


def _quantity_relationship_uncertainties(rows: object) -> list[str]:
    """Show unchecked totals without promoting them to Tender discrepancies."""

    values: list[str] = []
    seen: set[str] = set()
    for raw in rows if isinstance(rows, (list, tuple)) else ():
        if (
            not isinstance(raw, Mapping)
            or raw.get("unresolved_kind") != "component_total_relationship"
        ):
            continue
        candidate_id = str(raw.get("quantity_candidate_id") or "")
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        location = str(raw.get("facility") or "Место выполнения требует уточнения")
        work = str(raw.get("work") or "Работа требует уточнения")
        role = str(raw.get("document_role") or "Документ")
        raw_value = raw.get("value")
        value = str(raw_value) if raw_value not in (None, "") else "значение не установлено"
        unit = str(raw.get("unit") or "").strip()
        reason = str(raw.get("reason") or "Связь с составляющими требует уточнения.")
        values.append(f"{location}: {work} — {role} {value} {unit}. {reason}".replace("  ", " "))
    limit = 20
    if len(values) > limit:
        return [*values[:limit], f"Ещё {len(values) - limit} общих объёмов требуют уточнения."]
    return values


def _heading(value: str, *, level: int = 2) -> str:
    size = "30" if level == 1 else "24"
    return (
        f'<w:p><w:r><w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr>'
        f"<w:t>{escape(value)}</w:t></w:r></w:p>"
    )


def _paragraph(value: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p>'


def _simple_table(
    headers: tuple[str, ...], rows: Sequence[tuple[str, ...]], *, empty: str = "Нет данных."
) -> str:
    values = [headers, *rows] if rows else [headers, (empty, *("" for _ in headers[1:]))]
    column_width = max(9000 // len(headers), 900)
    rendered = []
    for row_index, row in enumerate(values):
        cells = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="{column_width}" w:type="dxa"/></w:tcPr>'
            f"<w:p><w:r>{'<w:rPr><w:b/></w:rPr>' if row_index == 0 else ''}"
            f'<w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p></w:tc>'
            for value in row
        )
        row_properties = "<w:trPr><w:tblHeader/></w:trPr>" if row_index == 0 else ""
        rendered.append(f"<w:tr>{row_properties}{cells}</w:tr>")
    grid = (
        "<w:tblGrid>"
        + "".join(f'<w:gridCol w:w="{column_width}"/>' for _ in headers)
        + "</w:tblGrid>"
    )
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="B7B7B7"/>'
        '<w:left w:val="single" w:sz="4" w:color="B7B7B7"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="B7B7B7"/>'
        '<w:right w:val="single" w:sz="4" w:color="B7B7B7"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="D9D9D9"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D9D9D9"/></w:tblBorders>'
        '<w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/>'
        "</w:tblCellMar></w:tblPr>" + grid + "".join(rendered) + "</w:tbl>"
    )


def _role_values(value: object) -> str:
    roles = value if isinstance(value, Mapping) else {}
    return (
        "; ".join(
            f"{role}: "
            + ", ".join(f"{item.get('value')} {item.get('unit') or ''}" for item in items or ())
            for role, items in roles.items()
        )
        or "не найдено"
    )


def _role_materials(value: object) -> str:
    roles = value if isinstance(value, Mapping) else {}
    return (
        "; ".join(
            f"{role}: " + ", ".join(str(item.get("name") or "") for item in items or ())
            for role, items in roles.items()
        )
        or "не найдено"
    )


def _operand(value: object) -> str:
    row = dict(value) if isinstance(value, Mapping) else {}
    return f"{row.get('document_role')}: {row.get('value')} {row.get('unit') or ''}"


def _issue_table(values: object) -> str:
    items = values if isinstance(values, Sequence) and not isinstance(values, (str, bytes)) else ()
    rows = [
        (
            str(row.get("location") or "Требует уточнения"),
            str(row.get("kind") or "Инженерный вопрос"),
            str(row.get("description") or ""),
            str(row.get("recommended_action") or ""),
            _source_labels(row),
        )
        for value in items
        if isinstance(value, Mapping)
        for row in (dict(value),)
    ]
    return _simple_table(
        ("Место", "Вопрос", "Вывод", "Действие", "Источники"),
        rows,
        empty="Не установлены.",
    )


def _source_labels(row: Mapping[str, Any]) -> str:
    labels: list[str] = []
    for raw in row.get("sources") or ():
        if not isinstance(raw, Mapping):
            continue
        document = str(raw.get("document") or "Документ")
        version = raw.get("version")
        page = raw.get("page")
        label = document
        if version not in (None, ""):
            label += f", версия {version}"
        if page not in (None, ""):
            label += f", стр./лист {page}"
        labels.append(label)
    if labels:
        return "; ".join(dict.fromkeys(labels))
    return "; ".join(str(value) for value in row.get("source_locator_ids") or ())


def _bullet_list(values: list[str], *, empty: str) -> str:
    return "".join(_paragraph(f"• {value}") for value in values if value) or _paragraph(empty)
