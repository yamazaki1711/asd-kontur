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
    issues = tuple(_records(view.get("issues")))
    issue_by_identity = {
        (str(item.get("issue_id", "")), str(item.get("issue_version", ""))): item for item in issues
    }
    disagreement_rows: list[tuple[str, str, str, str, str, str, str]] = []
    for ordinal, item in enumerate(_records(view.get("disagreement_items")), start=1):
        clause = clause_by_identity.get(
            (str(item.get("clause_id", "")), str(item.get("clause_version", ""))), {}
        )
        revised = revised_by_item.get(str(item.get("item_id", "")), {})
        issue = issue_by_identity.get(
            (str(item.get("issue_id", "")), str(item.get("issue_version", ""))), {}
        )
        disagreement_rows.append(
            (
                str(ordinal),
                str(clause.get("clause_key") or "Не указано"),
                str(clause.get("source_text") or "Текст исходного пункта не извлечён"),
                _source_reference(clause),
                str(revised.get("revised_text") or item.get("proposed_clause_text") or ""),
                _disagreement_basis(issue, item),
                _joined(item.get("uncertainty_issue_ids")) or "Нет зарегистрированных кодов",
            )
        )

    issue_rows = [
        (
            str(ordinal),
            str(item.get("issue_kind") or "Не указано"),
            str(item.get("subject") or "Не указано"),
            str(item.get("description") or "Не указано"),
            _risk_source_wording(item),
            str(item.get("applicability") or "Не указано"),
            str(item.get("recommendation_text") or "Требуется уточнение"),
            str(item.get("consequence_code") or "Не указано"),
        )
        for ordinal, item in enumerate(issues, start=1)
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
    project_context = _mapping(view.get("project_context"))
    key_condition_rows = [
        (
            str(ordinal),
            str(item.get("label") or item.get("field") or "Условие"),
            str(item.get("value") or "Требует уточнения"),
            _fact_source_reference(item),
        )
        for ordinal, item in enumerate(_contract_key_facts(project_context), start=1)
    ]
    project_finding_rows = [
        (
            str(ordinal),
            str(item.get("kind") or item.get("finding_kind") or "Вопрос"),
            str(item.get("subject") or "Объект в целом"),
            str(item.get("description") or "Требует уточнения"),
            str(item.get("practical_consequence") or "Не указано"),
            str(item.get("recommended_action") or "Получить письменное уточнение"),
            _finding_source_reference(item),
        )
        for ordinal, item in enumerate(
            _records(project_context.get("project_contract_findings")), start=1
        )
    ]
    reference_rows = [
        (
            str(ordinal),
            str(item.get("source_quote") or ""),
            str(item.get("target_description") or ""),
            (
                str(item.get("matched_source_name") or "")
                if str(item.get("match_decision")) == "matched"
                else "Соответствующий документ не установлен"
            ),
            ", ".join(
                part
                for part in (
                    str(item.get("source_name") or ""),
                    f"стр. {item['source_page']}" if item.get("source_page") is not None else "",
                )
                if part
            ),
        )
        for ordinal, item in enumerate(_records(view.get("attachment_references")), start=1)
    ]
    process = _mapping(view.get("process"))
    status = _status_label(view.get("status"))
    gaps = _gap_summary(view.get("gaps"))
    body = [
        _heading("Договорный анализ и предложения Подрядчика", "Title"),
        _paragraph(f"Состояние анализа: {status}."),
        _paragraph(
            "Рабочий документ Подрядчика. Требует профессиональной юридической проверки "
            "и согласования; не является подписанным соглашением сторон."
        ),
        _paragraph(f"Ограничения результата: {gaps}"),
    ]
    source_coverage = _mapping(_mapping(view.get("assessment")).get("source_coverage"))
    incomplete_sources = [
        str(name)
        for name in source_coverage.get("incomplete_source_names") or ()
        if str(name).strip()
    ]
    if incomplete_sources:
        body.append(
            _paragraph(
                "Анализ исходных договорных документов не завершён: "
                + ", ".join(incomplete_sources)
                + ". Выводы и предложения ниже относятся только к уже обработанному тексту."
            )
        )
    unavailable_checks = _unavailable_project_cross_checks(project_context)
    if unavailable_checks:
        body.append(
            _paragraph(
                "Сопоставление договора с проектом ограничено: по текущей модели не "
                "установлены исходные данные для проверки: "
                + ", ".join(unavailable_checks)
                + ". Это не означает отсутствия противоречий."
            )
        )
    if process:
        if process.get("revision"):
            body.append(_paragraph(f"Редакция анализа: {process.get('revision')}."))
    else:
        body.append(
            _paragraph(
                "Проект договора не найден среди загруженных документов. Договорные риски "
                "и предложения по изменению условий без исходного договора не подготовлены."
            )
        )

    if reference_rows:
        body.extend(
            (
                _heading("Документы, на которые ссылается договор", "Heading1"),
                _table(
                    ("№", "Точная ссылка", "Предмет ссылки", "Принятый документ", "Источник"),
                    reference_rows,
                    "",
                ),
                _paragraph(
                    "Неустановленная связь с загруженным документом требует проверки состава "
                    "перед согласованием; сама по себе она не доказывает отсутствие приложения."
                ),
            )
        )

    body.extend(
        (
            _heading("Ключевые условия договора и закупки", "Heading1"),
            _table(
                ("№", "Условие", "Значение", "Источник"),
                key_condition_rows,
                "Ключевые условия ещё извлекаются.",
            ),
            _heading("Связь договора с проектом", "Heading1"),
            _table(
                (
                    "№",
                    "Вопрос",
                    "Предмет",
                    "Расхождение или неопределённость",
                    "Последствие для Подрядчика",
                    "Рекомендуемое действие",
                    "Источники",
                ),
                project_finding_rows,
                "Проектно-договорные выводы пока не опубликованы; полнота "
                "сопоставления не подтверждена.",
            ),
            _heading("Предложения для протокола разногласий", "Heading1"),
            _table(
                (
                    "№",
                    "Пункт договора",
                    "Редакция Заказчика",
                    "Источник",
                    "Предлагаемая редакция",
                    "Обоснование / практическая причина",
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
                    "Риск для Подрядчика",
                    "Точная формулировка риска",
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


def _unavailable_project_cross_checks(project_context: Mapping[str, Any]) -> list[str]:
    labels = {
        "design_scope": "проектный объём ПД/РД",
        "commercial_scope": "объёмы ВОР/сметы",
        "schedule": "календарный график",
    }
    return [
        labels[check]
        for item in _records(project_context.get("cross_checks"))
        if (check := str(item.get("check") or "")) in labels
        and str(item.get("status") or "") == "input_not_established"
    ]


def render_tender_disagreement_protocol_docx(view: Mapping[str, Any]) -> bytes:
    """Render the contractor's editable disagreement protocol as a standalone artifact."""

    clauses = {
        (str(item.get("clause_id", "")), str(item.get("clause_version", ""))): item
        for item in _records(view.get("clauses"))
    }
    issues = {
        (str(item.get("issue_id", "")), str(item.get("issue_version", ""))): item
        for item in _records(view.get("issues"))
    }
    revisions = {
        str(item.get("disagreement_item_id", "")): item
        for item in _records(view.get("revised_clauses"))
    }
    rows: list[tuple[str, str, str, str, str, str]] = []
    for ordinal, item in enumerate(_records(view.get("disagreement_items")), start=1):
        clause = clauses.get(
            (str(item.get("clause_id", "")), str(item.get("clause_version", ""))), {}
        )
        issue = issues.get((str(item.get("issue_id", "")), str(item.get("issue_version", ""))), {})
        revision = revisions.get(str(item.get("item_id", "")), {})
        rows.append(
            (
                str(ordinal),
                str(clause.get("clause_key") or "Не указано"),
                str(clause.get("source_text") or "Текст исходного пункта не извлечён"),
                str(revision.get("revised_text") or item.get("proposed_clause_text") or ""),
                _disagreement_basis(issue, item),
                _source_reference(clause),
            )
        )

    assessment = _mapping(view.get("assessment"))
    source_names = _joined(assessment.get("source_names")) or "Источник договора не указан"
    project_context = _mapping(view.get("project_context"))
    participant_rows = [
        (
            str(ordinal),
            str(item.get("label") or item.get("field") or "Участник"),
            str(item.get("value") or "Требует уточнения"),
            _fact_source_reference(item),
        )
        for ordinal, item in enumerate(_records(project_context.get("participants")), start=1)
    ]
    body = [
        _heading("ПРОТОКОЛ РАЗНОГЛАСИЙ", "Title"),
        _paragraph(f"Исходные документы: {source_names}."),
        _paragraph(
            "Рабочая редакция Подрядчика. Документ подготовлен для профессиональной "
            "юридической проверки и согласования; он не является подписанным соглашением сторон."
        ),
        _heading("Объект и стороны", "Heading1"),
        _table(
            ("№", "Роль", "Наименование", "Источник"),
            participant_rows,
            "Сведения о сторонах требуют уточнения; отсутствующие реквизиты не подставлены.",
        ),
        _heading("Предлагаемые изменения", "Heading1"),
        _table(
            (
                "№",
                "Пункт договора",
                "Редакция Заказчика",
                "Редакция Подрядчика",
                "Обоснование / практическая причина",
                "Источник",
            ),
            rows,
            "Обоснованные предложения для протокола разногласий пока не подготовлены.",
        ),
    ]
    return _docx_package(_document_xml(body))


def _source_reference(clause: Mapping[str, Any]) -> str:
    """Return a professional source label without exposing internal identifiers."""

    values = (
        ("Документ", clause.get("source_name")),
        ("стр./лист", clause.get("source_page") or clause.get("page_number")),
    )
    return (
        "; ".join(f"{label}: {value}" for label, value in values if value)
        or "Источник доступен по ссылке результата"
    )


def _status_label(value: Any) -> str:
    labels = {
        "analysis_pending": "анализ ожидает запуска",
        "analyzing": "анализ договора выполняется",
        "drafted": "предварительный анализ подготовлен",
        "contract_clause_extraction_pending": "извлекаются условия договора",
        "contract_input_unavailable": "проект договора не найден",
    }
    return labels.get(str(value or ""), "состояние требует уточнения")


def _gap_summary(value: Any) -> str:
    labels = {
        "CONTRACT_ANALYSIS_IN_PROGRESS": "анализ продолжается; документ будет дополнен",
        "CONTRACT_ANALYSIS_BATCH_FAILURES": (
            "часть условий пока не удалось интерпретировать; доступные выводы сохранены"
        ),
        "CONTRACT_ANALYSIS_SOURCE_COVERAGE_INCOMPLETE": (
            "не весь исходный текст договора обработан"
        ),
        "CONTRACT_REFERENCE_REVIEW_IN_PROGRESS": (
            "ссылки на договорные документы ещё проверяются"
        ),
        "CONTRACT_REFERENCE_REVIEW_FAILED": (
            "часть ссылок на договорные документы не удалось проверить"
        ),
        "CONTRACT_REFERENCE_INVENTORY_LIMIT": (
            "состав загруженных документов слишком велик для текущей проверки ссылок"
        ),
        "CONTRACT_REFERENCED_DOCUMENT_UNRESOLVED": (
            "связь части договорных ссылок с загруженными документами не установлена"
        ),
        "CONTRACT_RISKS_NOT_IDENTIFIED_IN_COMPLETED_BATCHES": (
            "в обработанной части договора риски не установлены"
        ),
        "CONTRACT_SOURCE_CLASSIFICATION_IN_PROGRESS": "уточняется назначение документов",
        "CONTRACT_SOURCE_RECLASSIFICATION_PENDING": (
            "назначение ранее найденного проекта договора уточняется повторно"
        ),
        "DRAFT_CONTRACT_SOURCE_UNAVAILABLE": "проект договора не найден среди документов",
        "PROFESSIONAL_REVIEW_REQUIRED": "требуется профессиональная юридическая проверка",
    }
    raw = value if isinstance(value, (list, tuple, set)) else ()
    result = [
        labels.get(str(item), "есть ограничение обработки; подробности в диагностике")
        for item in raw
    ]
    return "; ".join(dict.fromkeys(result)) or "существенные ограничения не зарегистрированы"


def _contract_key_facts(project_context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for key in (
        "participants",
        "commercial_conditions",
        "time_requirements",
        "key_conditions",
        "procurement_requirements",
    ):
        result.extend(_records(project_context.get(key)))
    return result


def _fact_source_reference(item: Mapping[str, Any]) -> str:
    references = []
    for source in _records(item.get("sources")):
        name = str(source.get("document") or "Документ")
        page = source.get("page")
        references.append(f"{name}, стр./лист {page}" if page else name)
    return "; ".join(references) or "Источник указан во внутренней ссылке"


def _finding_source_reference(item: Mapping[str, Any]) -> str:
    references = []
    for source in _records(item.get("sources")):
        name = str(source.get("document") or "Документ")
        page = source.get("page")
        references.append(f"{name}, стр./лист {page}" if page else name)
    return "; ".join(references) or "Источники доступны по ссылкам результата"


def _risk_source_wording(issue: Mapping[str, Any]) -> str:
    values = (
        ("Условие", issue.get("trigger_text")),
        ("Последствие", issue.get("adverse_effect_text")),
    )
    return "; ".join(f"{label}: {value}" for label, value in values if value) or "Не указано"


def _disagreement_basis(issue: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    values = (
        ("Риск", issue.get("description")),
        ("Практическое последствие", issue.get("consequence_code") or item.get("consequence_code")),
        ("Рекомендуемое действие", issue.get("recommendation_text")),
    )
    return "; ".join(f"{label}: {value}" for label, value in values if value) or "Не указано"


def _document_xml(body: Iterable[str]) -> bytes:
    content = "".join(body)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{content}"
        '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
        '<w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
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
    total_width = 15100
    if len(headers) > 1 and headers[0] == "№":
        widths = (600,) + ((total_width - 600) // (len(headers) - 1),) * (len(headers) - 1)
    else:
        widths = (max(900, total_width // len(headers)),) * len(headers)
    values = (headers, *rows)
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    return (
        "<w:tbl>"
        f'<w:tblPr><w:tblW w:w="{total_width}" w:type="dxa"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="808080"/>'
        '<w:left w:val="single" w:sz="4" w:color="808080"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="808080"/>'
        '<w:right w:val="single" w:sz="4" w:color="808080"/>'
        '<w:insideH w:val="single" w:sz="3" w:color="B7B7B7"/>'
        '<w:insideV w:val="single" w:sz="3" w:color="B7B7B7"/></w:tblBorders>'
        '<w:tblLayout w:type="fixed"/>'
        '<w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
        '<w:bottom w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/>'
        "</w:tblCellMar></w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
        + "".join(_row(row, widths, header=index == 0) for index, row in enumerate(values))
        + "</w:tbl>"
    )


def _row(values: Sequence[str], widths: Sequence[int], *, header: bool) -> str:
    run_properties = (
        '<w:rPr><w:b/><w:sz w:val="16"/></w:rPr>'
        if header
        else ('<w:rPr><w:sz w:val="16"/></w:rPr>')
    )
    cell_shading = '<w:shd w:val="clear" w:color="auto" w:fill="E7EDF3"/>' if header else ""
    cells = "".join(
        "<w:tc><w:tcPr>"
        f'<w:tcW w:w="{width}" w:type="dxa"/>{cell_shading}</w:tcPr>'
        f'<w:p><w:r>{run_properties}<w:t xml:space="preserve">{escape(value)}</w:t>'
        "</w:r></w:p></w:tc>"
        for value, width in zip(values, widths, strict=True)
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
            b'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            b'<w:rPr><w:sz w:val="20"/></w:rPr></w:style>'
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
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
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
