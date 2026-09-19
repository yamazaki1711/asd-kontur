"""Deterministic DOCX/PDF/ZIP exports for reviewed pilot results."""

from __future__ import annotations

import hashlib
import io
import json
import os
import textwrap
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .models import PilotExportFormat, PilotExportKind

_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def render_export(
    *,
    result: dict[str, Any],
    kind: PilotExportKind,
    output_format: PilotExportFormat,
    additional_files: Iterable[tuple[str, bytes]] = (),
) -> bytes:
    result = _export_snapshot(result)
    title = _export_title(kind)
    lines = _document_lines(result, title)
    if output_format is PilotExportFormat.PDF:
        return _render_pdf(title, lines)
    if output_format is PilotExportFormat.DOCX:
        return _render_docx(title, lines)
    return _render_zip(result, title, lines, additional_files)


def render_workspace_archive(
    *, results: Iterable[dict[str, Any]], additional_files: Iterable[tuple[str, bytes]] = ()
) -> bytes:
    """Package every formed mode result without changing its canonical version."""

    files: list[tuple[str, bytes]] = []
    manifest: list[dict[str, Any]] = []
    snapshots = (_export_snapshot(result) for result in results)
    for result in sorted(snapshots, key=lambda value: str(value["mode"])):
        mode = str(result["mode"]).lower()
        title = f"Результат режима «{result['mode']}»"
        lines = _document_lines(result, title)
        files.extend(
            [
                (
                    f"{mode}/result.json",
                    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode(
                        "utf-8"
                    ),
                ),
                (f"{mode}/result.docx", _render_docx(title, lines)),
                (f"{mode}/result.pdf", _render_pdf(title, lines)),
            ]
        )
        manifest.append(
            {
                "mode": result["mode"],
                "result_id": result["result_id"],
                "version": result["version"],
                "fingerprint": result["fingerprint"],
                "status": result["status"],
            }
        )
    files.append(
        (
            "manifest.json",
            json.dumps(
                {"format": "asd-kontur-pilot-results@1.0.0", "results": manifest},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ).encode("utf-8"),
        )
    )
    files.extend(additional_files)
    return _zip_bytes(files)


def _export_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Remove delivery projections that would make an export depend on itself."""

    return {key: value for key, value in result.items() if key != "exports"}


def _document_lines(result: dict[str, Any], title: str) -> list[str]:
    lines = [
        str(result["workspace_name"]),
        title,
        f"Версия результата: {result['version']}",
        f"Статус: {_status_label(str(result['status']))}",
    ]
    if result.get("formed_at"):
        lines.append(f"Дата формирования: {result['formed_at']}")
    lines.extend(["", "Результаты"])
    included = [
        dict(value)
        for value in result.get("items") or []
        if value.get("effective_resolution_status") != "excluded"
    ]
    for ordinal, item in enumerate(included, start=1):
        lines.extend(
            [
                f"{ordinal}. {item.get('title', 'Результат')}",
                f"Состояние: {_status_label(str(item.get('effective_status') or item.get('status')))}",
                str(item.get("effective_description") or item.get("description") or ""),
                f"Последствия: {item.get('consequence') or 'Требуется проверка.'}",
                f"Действие: {item.get('recommended_action') or 'Рассмотреть специалисту.'}",
            ]
        )
        source_references = [str(value) for value in item.get("source_references") or []]
        if source_references:
            lines.append("Источники вывода: " + "; ".join(source_references))
        lines.append("")
    lines.extend(["Использованные источники"])
    for source in result.get("source_manifest") or []:
        lines.append(
            f"• {source['name']}, версия {source['version']}, контрольная сумма {source['digest']}"
        )
    lines.extend(["", "Нерешённые вопросы"])
    unresolved = result.get("unresolved_questions") or []
    lines.extend(f"• {_status_label(str(value))}" for value in unresolved)
    if not unresolved:
        lines.append("• Не зарегистрированы")
    notice = result.get("normative_notice")
    if notice:
        lines.extend(["", str(notice)])
    return lines


def _render_pdf(title: str, lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    font_name = _register_font()
    page = canvas.Canvas(buffer, pagesize=A4, pageCompression=1, invariant=1)
    _, height = A4
    margin = 48
    y = height - margin
    page.setTitle(title)
    page.setAuthor("ООО «АСД-КОНТУР»")
    page.setCreator("АСД-КОНТУР")
    for index, line in enumerate(lines):
        size = 14 if index == 1 else 10
        if line in {"Результаты", "Использованные источники", "Нерешённые вопросы"}:
            size = 12
        wrapped = _wrap(line, 104 if size == 10 else 76)
        for segment in wrapped or [""]:
            if y < margin + 24:
                page.showPage()
                y = height - margin
            page.setFont(font_name, size)
            page.drawString(margin, y, segment)
            y -= size + 4
        if not line:
            y -= 4
    page.save()
    return buffer.getvalue()


def _render_docx(title: str, lines: list[str]) -> bytes:
    paragraphs = []
    for index, line in enumerate(lines):
        style = "Title" if index == 1 else "Normal"
        if line in {"Результаты", "Использованные источники", "Нерешённые вопросы"}:
            style = "Heading1"
        paragraphs.append(
            '<w:p><w:pPr><w:pStyle w:val="'
            + style
            + '"/></w:pPr><w:r><w:t xml:space="preserve">'
            + escape(line)
            + "</w:t></w:r></w:p>"
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" '
        'w:right="1134" w:bottom="1134" w:left="1134" w:header="708" '
        'w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'
    ).encode("utf-8")
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Обычный"/>'
        '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="20"/>'
        "</w:rPr></w:style>"
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Заголовок"/>'
        '<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Заголовок 1"/>'
        '<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        "</w:styles>"
    ).encode()
    content_types = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        b"</Types>"
    )
    root_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        b"</Relationships>"
    )
    document_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        b"</Relationships>"
    )
    return _zip_bytes(
        (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", root_rels),
            ("word/document.xml", document),
            ("word/styles.xml", styles),
            ("word/_rels/document.xml.rels", document_rels),
        )
    )


def _render_zip(
    result: dict[str, Any],
    title: str,
    lines: list[str],
    additional_files: Iterable[tuple[str, bytes]],
) -> bytes:
    manifest = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    files: list[tuple[str, bytes]] = [
        ("manifest.json", manifest),
        ("result.docx", _render_docx(title, lines)),
        ("result.pdf", _render_pdf(title, lines)),
    ]
    files.extend(additional_files)
    return _zip_bytes(tuple(files))


def _zip_bytes(files: Iterable[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files):
            info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def _register_font() -> str:
    name = "PilotSans"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    candidates = [
        os.environ.get("ASD_RENDERER_FONT_PATH", ""),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for raw in candidates:
        if raw and Path(raw).is_file():
            pdfmetrics.registerFont(TTFont(name, raw))
            return name
    raise RuntimeError("pilot_export_cyrillic_font_unavailable")


def _wrap(value: str, width: int) -> list[str]:
    return textwrap.wrap(value, width=width, break_long_words=True, break_on_hyphens=False)


def _export_title(kind: PilotExportKind) -> str:
    return {
        PilotExportKind.DISAGREEMENT_PROTOCOL: "Проект протокола разногласий",
        PilotExportKind.CONTRACT_CHANGES: "Предлагаемые изменения к договору",
        PilotExportKind.REQUIREMENT_MATRIX: "Матрица работ и требований",
        PilotExportKind.ID_PACKAGE: "Комплект исполнительной документации",
        PilotExportKind.REGISTER: "Реестр документов комплекта",
        PilotExportKind.AUDIT_REPORT: "Отчёт аудита строительной документации",
        PilotExportKind.RECOVERY_PLAN: "План восстановления исполнительной документации",
        PilotExportKind.RECOVERED_DRAFTS: "Проекты восстанавливаемых документов",
        PilotExportKind.WORKSPACE_RESULTS: "Архив результатов объекта строительства",
    }[kind]


def _status_label(value: str) -> str:
    return {
        "draft_with_open_questions": "Проект, имеются нерешённые вопросы",
        "reviewed_draft": "Проект рассмотрен",
        "requires_clarification": "Требуется уточнение",
        "missing": "Отсутствует",
        "conflict": "Обнаружено расхождение",
        "cannot_prepare": "Невозможно подготовить по имеющимся данным",
        "conforms": "Соответствует",
        "required": "Требуется",
        "conditional": "Требуется при указанных условиях",
        "original_or_finalized": "Финализированный документ",
        "recoverable_draft": "Можно подготовить проект",
    }.get(value, value.replace("_", " "))


def content_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
