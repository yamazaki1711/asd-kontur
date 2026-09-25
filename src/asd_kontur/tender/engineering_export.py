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
                        "Источники": "; ".join(
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
    for ordinal, issue in enumerate(model.get("issues") or (), start=1):
        row = dict(issue)
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
                "Источники / source_references": "; ".join(
                    str(value) for value in row.get("source_locator_ids") or ()
                ),
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def render_engineering_tender_report_docx(model: Mapping[str, Any]) -> bytes:
    """Render a readable editable Tender report in construction language."""

    project = dict(model.get("project") or {})
    name = dict(project.get("name") or {}).get("value") or "Наименование уточняется"
    purpose = dict(project.get("purpose") or {}).get("value") or "Назначение уточняется"
    pits = dict(model.get("pits") or {})
    body: list[str] = [
        _heading("Tender-анализ проекта", level=1),
        _paragraph(str(name)),
        _heading("1. Краткое описание объекта"),
        _paragraph(str(purpose)),
        _paragraph(
            str(pits.get("professional_answer") or "Инвентаризация котлованов не завершена.")
        ),
        _heading("2. Состав сооружений"),
        _simple_table(
            ("Сооружение / участок", "Тип", "Статус"),
            [
                (
                    str(row.get("name") or ""),
                    str(row.get("kind") or ""),
                    str(row.get("status") or ""),
                )
                for row in model.get("facilities") or ()
            ],
        ),
        _heading("3. Основные виды работ и объёмы"),
        _simple_table(
            ("Место", "Работа", "Объёмы по документам", "Материалы"),
            [
                (
                    str(row.get("facility") or "Требует уточнения"),
                    str(row.get("work_name") or ""),
                    _role_values(row.get("quantities_by_document")),
                    _role_materials(row.get("materials_by_document")),
                )
                for row in model.get("works") or ()
            ],
        ),
        _heading("4. Расхождения ПД/РД/ВОР/сметы"),
        _simple_table(
            ("Место", "Работа", "Сравнение", "Вывод"),
            [
                (
                    str(row.get("facility") or ""),
                    str(row.get("work") or ""),
                    f"{_operand(row.get('left'))}; {_operand(row.get('right'))}",
                    str(row.get("conclusion") or ""),
                )
                for row in model.get("quantity_comparisons") or ()
            ],
            empty="Сопоставимые значения по ролям документов пока не установлены.",
        ),
        _heading("5. Неучтённые или спорные работы"),
        _paragraph(
            f"Не удалось однозначно классифицировать: "
            f"{len(model.get('unclassified_works') or ())} описаний. "
            "Они сохранены для дальнейшего уточнения и не исключены из состава проекта."
        ),
        _heading("6. Технические противоречия"),
        _issue_table(model.get("issues") or ()),
        _heading("7. Вопросы Заказчику"),
        _bullet_list(
            [str(row.get("question") or "") for row in model.get("customer_questions") or ()],
            empty="Вопросы будут сформированы после установления инженерных расхождений.",
        ),
        _heading("8. Риски Подрядчика"),
        _bullet_list(
            [str(row.get("risk") or "") for row in model.get("risks") or ()],
            empty="Риски будут сформированы после установления инженерных расхождений.",
        ),
        _heading("9. Применимые требования"),
        _paragraph(str(dict(model.get("requirements") or {}).get("professional_summary") or "")),
        _heading("10. Список исходных документов"),
        _bullet_list(
            [
                f"{row.get('name')} (версия {row.get('version')}; {row.get('document_role')})"
                for row in model.get("documents") or ()
            ],
            empty="Исходные документы не перечислены.",
        ),
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return _docx_package(document.encode())


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
    rendered = []
    for row in values:
        cells = "".join(
            f'<w:tc><w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p></w:tc>'
            for value in row
        )
        rendered.append(f"<w:tr>{cells}</w:tr>")
    return "<w:tbl>" + "".join(rendered) + "</w:tbl>"


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
        )
        for value in items
        if isinstance(value, Mapping)
        for row in (dict(value),)
    ]
    return _simple_table(("Место", "Вопрос", "Вывод", "Действие"), rows, empty="Не установлены.")


def _bullet_list(values: list[str], *, empty: str) -> str:
    return "".join(_paragraph(f"• {value}") for value in values if value) or _paragraph(empty)
