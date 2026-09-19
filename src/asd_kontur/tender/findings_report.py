# ruff: noqa: E501, RUF001
"""Editable Tender findings report built from the current evidence-bound model."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Mapping
from typing import Any
from xml.sax.saxutils import escape

from .findings_schedule import (
    _work_packages_by_observation,
    finding_presentation,
    finding_work_context,
    source_reference,
)

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

_RUSSIAN_TITLES = {
    "estimate_comparison_input_unavailable": "Сопоставление со сметой не выполнено",
    "project_work_missing_in_estimate": "Проектная работа требует сопоставления со сметой",
    "quantity_mismatch": "Требуется сверка объёма по источникам",
    "project_material_missing_in_estimate": "Материал требует сопоставления со сметой",
    "estimate_position_unsupported_by_project": "Сметная позиция не подтверждена проектом",
    "incompatible_units": "Единицы измерения требуют проверки",
    "ambiguous_source_match": "Связь исходных сведений неоднозначна",
}


def render_tender_findings_docx(
    defects: Iterable[Mapping[str, Any]],
    *,
    materialization_state: str,
    coverage_gaps: Iterable[str],
    evidence_index: Mapping[str, Mapping[str, Any]] | None = None,
    work_packages: Iterable[Mapping[str, Any]] = (),
) -> bytes:
    """Render an editable Russian report without promoting candidate findings.

    The report is a presentation projection of the same findings schedule. It
    preserves source references and missing inputs, and it never turns an
    empty partial result into a conclusion that no discrepancies exist.
    """

    normalized = sorted(
        (dict(item) for item in defects),
        key=lambda item: (str(item.get("defect_id", "")), str(item)),
    )
    gaps = tuple(sorted(str(item) for item in coverage_gaps))
    packages_by_observation = _work_packages_by_observation(work_packages)
    rows = [("№", "Наблюдение", "Объект", "Нужные данные", "Последствие", "Источники")]
    for ordinal, defect in enumerate(normalized, start=1):
        kind = str(defect.get("defect_kind", "unknown"))
        _, required_input, consequence = finding_presentation(kind)
        parameters = defect.get("parameters")
        if isinstance(parameters, Mapping):
            required_input = str(parameters.get("missing_input") or required_input)
            consequence = str(parameters.get("consequence") or consequence)
        locator_ids = tuple(str(item) for item in defect.get("source_locator_ids", []))
        evidence = evidence_index or {}
        rows.append(
            (
                str(ordinal),
                _RUSSIAN_TITLES.get(kind, "Требуется инженерская сверка"),
                _subject(defect, finding_work_context(defect, packages_by_observation)),
                required_input,
                consequence,
                "; ".join(
                    source_reference(locator_id, evidence.get(locator_id))
                    for locator_id in locator_ids
                )
                or "Источник не указан",
            )
        )
    content = _document_xml(
        rows=rows,
        materialization_state=materialization_state,
        coverage_gaps=gaps,
        no_findings=not normalized,
    )
    return _docx_package(content)


def _subject(defect: Mapping[str, Any], work_context: Mapping[str, str]) -> str:
    work_name = work_context.get("work_name")
    scope = work_context.get("scope")
    if work_name:
        return f"{work_name}; область: {scope or 'не указана'}"
    subject = str(defect.get("subject_identity") or "Не указан")
    related = defect.get("related_identity")
    return subject if related is None else f"{subject}; связано с: {related}"


def _document_xml(
    *,
    rows: list[tuple[str, str, str, str, str, str]],
    materialization_state: str,
    coverage_gaps: tuple[str, ...],
    no_findings: bool,
) -> bytes:
    table = "<w:tbl>" + "".join(_row(row) for row in rows) + "</w:tbl>"
    coverage = "; ".join(coverage_gaps) if coverage_gaps else "не указаны"
    conclusion = (
        "В сформированной модели открытые расхождения не зарегистрированы."
        if materialization_state == "complete"
        else "Анализ расхождений ещё не завершён; отсутствие записей не означает отсутствие расхождений."
    )
    finding_notice = (
        conclusion
        if no_findings
        else "Наблюдения ниже являются кандидатами, а не подтверждёнными нарушениями."
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>'
        "Предварительный Tender-отчёт: расхождения и вопросы</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>Состояние формирования модели: {escape(materialization_state)}</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>Пробелы покрытия: {escape(coverage)}</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{escape(finding_notice)}</w:t></w:r></w:p>"
        f"{table}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )
    return document.encode()


def _row(values: tuple[str, str, str, str, str, str]) -> str:
    cells = "".join(
        '<w:tc><w:tcPr><w:tcW w:w="1600" w:type="dxa"/></w:tcPr>'
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
            b'<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            b'<w:name w:val="Normal"/></w:style>'
            b'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
            b'<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'
            b"</w:style></w:styles>"
        ),
        "word/settings.xml": (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:compat/></w:settings>"
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
