# ruff: noqa: E501, RUF001
"""Editable contractor-facing report for canonical Tender contract analysis."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def render_tender_contract_analysis_docx(view: Mapping[str, Any]) -> bytes:
    """Render canonical clauses and proposals without creating a legal decision."""

    clauses = tuple(_records(view.get("clauses")))
    clause_by_identity = {
        (str(item.get("clause_id", "")), str(item.get("clause_version", ""))): item
        for item in clauses
    }
    revised_by_item = {
        str(item.get("disagreement_item_id", "")): item
        for item in _records(view.get("revised_clauses"))
    }
    disagreement_rows: list[tuple[str, str, str, str, str, str]] = []
    for ordinal, item in enumerate(_records(view.get("disagreement_items")), start=1):
        clause = clause_by_identity.get(
            (str(item.get("clause_id", "")), str(item.get("clause_version", ""))), {}
        )
        revised = revised_by_item.get(str(item.get("item_id", "")), {})
        disagreement_rows.append(
            (
                str(ordinal),
                str(clause.get("clause_key") or "Не указано"),
                _source_reference(clause),
                str(revised.get("revised_text") or item.get("proposed_clause_text") or ""),
                str(item.get("consequence_code") or "Не указано"),
                _joined(item.get("uncertainty_issue_ids")) or "Нет зарегистрированных кодов",
            )
        )

    issue_rows = [
        (
            str(ordinal),
            str(item.get("issue_kind") or "Не указано"),
            str(item.get("subject") or "Не указано"),
            str(item.get("applicability") or "Не указано"),
            str(item.get("recommendation_text") or "Требуется уточнение"),
            str(item.get("consequence_code") or "Не указано"),
        )
        for ordinal, item in enumerate(_records(view.get("issues")), start=1)
    ]
    deliverable_rows = [
        (
            str(ordinal),
            str(item.get("deliverable_kind") or "Не указано"),
            str(item.get("state") or "Не указано"),
            _joined(item.get("blocker_issue_ids")) or "Нет",
            _joined(item.get("uncertainty_issue_ids")) or "Нет",
        )
        for ordinal, item in enumerate(_records(view.get("deliverables")), start=1)
    ]
    process = _mapping(view.get("process"))
    gaps = _joined(view.get("gaps")) or "Нет зарегистрированных пробелов"
    body = [
        _heading("Протокол разногласий и предложения по переработке договора", "Title"),
        _paragraph(f"Состояние Tender-процесса: {view.get('status', 'не указано')}"),
        _paragraph(
            "Граница полномочий: документ является редактируемой проекцией канонических "
            "записей и не заменяет юридическое заключение, согласование или подписание."
        ),
        _paragraph(f"Пробелы и ограничения: {gaps}"),
    ]
    if process:
        body.append(
            _paragraph(
                "Идентификатор процесса: "
                f"{process.get('tender_process_id', '')}; ревизия: {process.get('revision', '')}."
            )
        )
    else:
        body.append(
            _paragraph(
                "Договорный Tender-процесс не сформирован. Это не означает, что договор "
                "проверен или риски отсутствуют."
            )
        )

    body.extend(
        (
            _heading("Предложения для протокола разногласий", "Heading1"),
            _table(
                (
                    "№",
                    "Исходное положение",
                    "Точный источник",
                    "Предлагаемая редакция",
                    "Практическое последствие",
                    "Неопределённость",
                ),
                disagreement_rows,
                "Подтверждённые предложения ещё не подготовлены.",
            ),
            _heading("Вопросы и риски", "Heading1"),
            _table(
                (
                    "№",
                    "Вид",
                    "Предмет",
                    "Применимость",
                    "Рекомендация",
                    "Последствие",
                ),
                issue_rows,
                "Канонические вопросы и риски ещё не зарегистрированы.",
            ),
            _heading("Подготовленные результаты", "Heading1"),
            _table(
                ("№", "Результат", "Состояние", "Блокеры", "Неопределённость"),
                deliverable_rows,
                "Результаты договорного анализа ещё не зарегистрированы.",
            ),
        )
    )
    return _docx_package(_document_xml(body))


def _source_reference(clause: Mapping[str, Any]) -> str:
    values = (
        ("Версия источника", clause.get("source_version_id")),
        ("Локатор", clause.get("source_locator_id")),
        ("Доказательство", clause.get("evidence_link_id")),
        ("Уровень полномочий", clause.get("authority_layer")),
    )
    return "; ".join(f"{label}: {value}" for label, value in values if value) or "Не привязан"


def _document_xml(body: Iterable[str]) -> bytes:
    content = "".join(body)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{content}"
        '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
        '<w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return document.encode("utf-8")


def _heading(text: str, style: str) -> str:
    return (
        f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{escape(text)}</w:t></w:r></w:p>'
    )


def _paragraph(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def _table(headers: tuple[str, ...], rows: Sequence[Sequence[str]], empty_text: str) -> str:
    if not rows:
        return _paragraph(empty_text)
    width = max(900, 15100 // len(headers))
    values = (headers, *rows)
    return "<w:tbl>" + "".join(_row(row, width) for row in values) + "</w:tbl>"


def _row(values: Sequence[str], width: int) -> str:
    cells = "".join(
        "<w:tc><w:tcPr>"
        f'<w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
        f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p></w:tc>'
        for value in values
    )
    return f"<w:tr>{cells}</w:tr>"


def _docx_package(document: bytes) -> bytes:
    files = {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            b'<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b"</Relationships>"
        ),
        "word/document.xml": document,
        "word/styles.xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            b'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
            b'<w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
            b'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
            b'<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>'
            b'<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style></w:styles>'
        ),
        "word/settings.xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:compat/></w:settings>'
        ),
        "word/_rels/document.xml.rels": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
            b"</Relationships>"
        ),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in files.items():
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return output.getvalue()


def _joined(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return ()
    return (item for item in value if isinstance(item, Mapping))
