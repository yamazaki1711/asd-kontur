"""Native-first format inventory, layout extraction and page-health analysis."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from asd_kontur.domain import deterministic_uuid

from .models import (
    PAGE_HEALTH_PROFILE_VERSION,
    ExactLocator,
    LayoutElement,
    OcrRoute,
    PageHealthAnalysis,
    PageHealthKind,
)

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CONTROL_OR_REPLACEMENT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")
SCRIPT_TOKEN = re.compile(r"[A-Za-z\u0410-\u044f\u0401\u0451|{}\\/]+")
TABLE_SIGNAL = re.compile(r"(?:\t|\s{3,}|[|;].*[|;])")
DRAWING_SIGNAL = re.compile(
    r"(?:масштаб\s*1:|экспликац|условн(?:ые|ое)\s+обознач|ось\s+[А-ЯA-Z0-9])",  # noqa: RUF001
    re.I,
)


class NativeExtractionFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class NativePage:
    page_number: int
    width_points: Decimal
    height_points: Decimal
    rotation_degrees: int
    image_count: int
    elements: tuple[LayoutElement, ...]
    health: PageHealthAnalysis
    parser_observations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NativeDocument:
    media_type: str
    format_kind: str
    parser_key: str
    parser_version: str
    pages: tuple[NativePage, ...]
    capability_gaps: tuple[str, ...]
    fingerprint: str


def inspect_and_extract(
    *,
    content: bytes,
    media_type: str,
    document_id: UUID,
    document_version: int,
    source_version_id: UUID,
) -> NativeDocument:
    """Extract supported native structures without filename-based semantics."""

    if media_type == "application/pdf":
        return _pdf_document(content, document_id, document_version, source_version_id)
    if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _docx_document(content, document_id, document_version, source_version_id)
    if media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return _xlsx_document(content, document_id, document_version, source_version_id)
    if media_type == "text/csv":
        return _csv_document(content, document_id, document_version, source_version_id)
    if media_type == "application/zip":
        return _archive_inventory(content, document_id, document_version, source_version_id)
    if media_type.startswith("image/"):
        page = _non_native_page(
            document_id=document_id,
            document_version=document_version,
            source_version_id=source_version_id,
            media_type=media_type,
        )
        return _document(media_type, "raster_image", "signature-inventory", "0.1.0", (page,), ())
    raise NativeExtractionFailure("document_format_not_supported")


def _archive_inventory(
    content: bytes, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    """Inventory an admitted ZIP container; member files are processed independently."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            member_count = sum(not item.is_dir() for item in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise NativeExtractionFailure("archive_structure_invalid") from exc
    page = _non_native_page(
        document_id=document_id,
        document_version=version,
        source_version_id=source_version_id,
        media_type="application/zip",
    )
    return _document(
        "application/zip",
        "archive_container",
        "zip-inventory",
        "1.0.0",
        (page,),
        (f"ARCHIVE_EXPANDED_MEMBERS:{member_count}",),
    )


def _pdf_document(
    content: bytes, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    reader = _open_pdf_reader(io.BytesIO(content))
    return _pdf_reader_document(reader, document_id, version, source_version_id)


def inspect_pdf_path(
    *,
    path: Path,
    document_id: UUID,
    document_version: int,
    source_version_id: UUID,
) -> NativeDocument:
    """Stream a trusted admitted PDF path through the shared native extractor."""

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise NativeExtractionFailure("pdf_path_invalid")
    with path.open("rb") as stream:
        reader = _open_pdf_reader(stream)
        return _pdf_reader_document(reader, document_id, document_version, source_version_id)


def _open_pdf_reader(stream: Any) -> PdfReader:
    try:
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except FileNotDecryptedError as exc:
                raise NativeExtractionFailure("pdf_password_or_encryption") from exc
            if unlocked == 0:
                raise NativeExtractionFailure("pdf_password_or_encryption")
    except (PdfReadError, ValueError) as exc:
        raise NativeExtractionFailure("pdf_structure_invalid") from exc
    return reader


def _pdf_reader_document(
    reader: PdfReader, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    pages: list[NativePage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        box = page.cropbox
        width = Decimal(str(float(box.right) - float(box.left)))
        height = Decimal(str(float(box.top) - float(box.bottom)))
        rotation = int(page.rotation or 0) % 360
        fragments: list[tuple[str, float, float, float, str | None]] = []
        extraction_observations: set[str] = set()
        warning_capture = _PypdfWarningCapture()
        pypdf_logger = logging.getLogger("pypdf")
        previous_propagate = pypdf_logger.propagate
        pypdf_logger.propagate = False
        pypdf_logger.addHandler(warning_capture)

        def visit_text(
            text: str,
            _cm: list[float],
            text_matrix: list[float],
            font: dict[str, Any] | None,
            font_size: float,
            _fragments: list[tuple[str, float, float, float, str | None]] = fragments,
        ) -> None:
            if not text:
                return
            _fragments.append(
                (
                    text,
                    float(text_matrix[4]),
                    float(text_matrix[5]),
                    max(
                        abs(float(text_matrix[0])),
                        abs(float(text_matrix[3])),
                        float(font_size or 0.0),
                        1.0,
                    ),
                    str(font.get("/BaseFont")) if font and font.get("/BaseFont") else None,
                )
            )

        try:
            try:
                page.extract_text(visitor_text=visit_text)
            except (KeyError, LookupError, TypeError, ValueError):
                fragments = []
                extraction_observations.add("native_text_encoding_unresolved")
            try:
                layout_lines = tuple(
                    normalize_text(value)
                    for value in (page.extract_text(extraction_mode="layout") or "").splitlines()
                    if value.strip()
                )
            except (KeyError, LookupError, TypeError, ValueError):
                layout_lines = ()
                extraction_observations.add("native_text_encoding_unresolved")
            image_count = _pdf_image_count(page)
        finally:
            pypdf_logger.removeHandler(warning_capture)
            pypdf_logger.propagate = previous_propagate
        parser_observations = tuple(
            sorted(set(warning_capture.codes).union(extraction_observations))
        )
        elements: list[LayoutElement] = []
        for order, line in enumerate(
            _group_pdf_lines(fragments, layout_lines=layout_lines), start=1
        ):
            raw, x0_points, y0_points, x1_points, y1_points, font_name, font_size = line
            normalized = normalize_text(raw)
            region = _non_empty_region(
                _bounded(x0_points / float(width)),
                _bounded(1 - (y1_points / float(height))),
                _bounded(x1_points / float(width)),
                _bounded(1 - (y0_points / float(height))),
            )
            elements.append(
                _element(
                    document_id,
                    version,
                    source_version_id,
                    page_number,
                    region,
                    order,
                    "line",
                    raw,
                    normalized,
                    font_name,
                    Decimal(str(font_size)),
                )
            )
        text = "\n".join(item.raw_text for item in elements)
        health = analyze_page_health(
            document_id=document_id,
            document_version=version,
            page_number=page_number,
            text=text,
            image_count=image_count,
            width_points=width,
            height_points=height,
            rotation_degrees=rotation,
            parser_observations=parser_observations,
        )
        pages.append(
            NativePage(
                page_number,
                width,
                height,
                rotation,
                image_count,
                tuple(elements),
                health,
                parser_observations,
            )
        )
    if not pages:
        raise NativeExtractionFailure("pdf_has_no_pages")
    return _document("application/pdf", "pdf", "pypdf-layout", "6.x", tuple(pages), ())


def _docx_document(
    content: bytes, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise NativeExtractionFailure("docx_structure_invalid") from exc
    root = ElementTree.fromstring(document_xml)
    elements: list[LayoutElement] = []
    order = 0
    table_rows: dict[int, tuple[int, int]] = {}
    for table_index, table in enumerate(root.iter(f"{W_NS}tbl"), start=1):
        for row_index, row in enumerate(table.findall(f"{W_NS}tr"), start=1):
            for column_index, cell in enumerate(row.findall(f"{W_NS}tc"), start=1):
                raw = " ".join(node.text or "" for node in cell.iter(f"{W_NS}t")).strip()
                if not raw:
                    continue
                order += 1
                region = _grid_region(row_index, column_index, 100, 20)
                value = _element(
                    document_id,
                    version,
                    source_version_id,
                    1,
                    region,
                    order,
                    "table_cell",
                    raw,
                    normalize_text(raw),
                    None,
                    None,
                    row_index,
                    column_index,
                )
                elements.append(value)
                table_rows[table_index] = (row_index, column_index)
    table_text = {item.raw_text for item in elements}
    for paragraph in root.iter(f"{W_NS}p"):
        raw = "".join(node.text or "" for node in paragraph.iter(f"{W_NS}t")).strip()
        if not raw or raw in table_text:
            continue
        order += 1
        elements.append(
            _element(
                document_id,
                version,
                source_version_id,
                1,
                _line_region(order, 500),
                order,
                "paragraph",
                raw,
                normalize_text(raw),
                None,
                None,
            )
        )
    return _textual_office_document(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
        "ooxml-word-native",
        elements,
        document_id,
        version,
    )


def _xlsx_document(
    content: bytes, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared = _xlsx_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                rel.attrib["Id"]: rel.attrib["Target"]
                for rel in relationships.findall(f"{PKG_REL_NS}Relationship")
            }
            elements: list[LayoutElement] = []
            order = 0
            for sheet_index, sheet in enumerate(
                workbook.findall(f"{S_NS}sheets/{S_NS}sheet"), start=1
            ):
                relation_id = sheet.attrib[f"{R_NS}id"]
                target = targets[relation_id].lstrip("/")
                if not target.startswith("xl/"):
                    target = f"xl/{target}"
                xml = ElementTree.fromstring(archive.read(target))
                for cell in xml.iter(f"{S_NS}c"):
                    ref = cell.attrib.get("r", "")
                    raw = _xlsx_cell_value(cell, shared)
                    if raw == "":
                        continue
                    row_index, column_index = _cell_coordinates(ref)
                    order += 1
                    elements.append(
                        _element(
                            document_id,
                            version,
                            source_version_id,
                            sheet_index,
                            _grid_region(row_index, column_index, 10000, 256),
                            order,
                            "table_cell",
                            raw,
                            normalize_text(raw),
                            None,
                            None,
                            row_index,
                            column_index,
                            cell=ref,
                        )
                    )
    except (KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise NativeExtractionFailure("xlsx_structure_invalid") from exc
    grouped: dict[int, list[LayoutElement]] = {}
    for item in elements:
        grouped.setdefault(item.locator.page_number, []).append(item)
    pages = tuple(
        _office_page(document_id, version, page, values, table_heavy=True)
        for page, values in sorted(grouped.items())
    )
    if not pages:
        pages = (_office_page(document_id, version, 1, [], table_heavy=True),)
    return _document(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
        "ooxml-spreadsheet-native",
        "0.1.0",
        pages,
        (),
    )


def _csv_document(
    content: bytes, document_id: UUID, version: int, source_version_id: UUID
) -> NativeDocument:
    try:
        raw_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NativeExtractionFailure("csv_encoding_unsupported") from exc
    sample = raw_text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    elements: list[LayoutElement] = []
    order = 0
    for row_index, row in enumerate(csv.reader(io.StringIO(raw_text), dialect), start=1):
        for column_index, raw in enumerate(row, start=1):
            if raw == "":
                continue
            order += 1
            ref = f"R{row_index}C{column_index}"
            elements.append(
                _element(
                    document_id,
                    version,
                    source_version_id,
                    1,
                    _grid_region(row_index, column_index, 10000, 256),
                    order,
                    "table_cell",
                    raw,
                    normalize_text(raw),
                    None,
                    None,
                    row_index,
                    column_index,
                    cell=ref,
                )
            )
    return _textual_office_document(
        "text/csv", "csv", "stdlib-csv-native", elements, document_id, version
    )


def analyze_page_health(
    *,
    document_id: UUID,
    document_version: int,
    page_number: int,
    text: str,
    image_count: int,
    width_points: Decimal,
    height_points: Decimal,
    rotation_degrees: int,
    table_heavy: bool = False,
    parser_observations: tuple[str, ...] = (),
) -> PageHealthAnalysis:
    stripped = text.strip()
    length = len(stripped)
    damaged = len(CONTROL_OR_REPLACEMENT.findall(text))
    replacement_ratio = Decimal(damaged) / Decimal(max(1, len(text)))
    mixed_script_ratio = _mixed_script_token_ratio(text)
    signals: list[str] = []
    blocking_parser_observations = tuple(
        value for value in parser_observations if value != "duplicate_dictionary_definition"
    )
    if blocking_parser_observations:
        primary = PageHealthKind.DAMAGED_ENCODING
        route = OcrRoute.APPLE_VISION
        signals.extend(f"native_parser:{value}" for value in blocking_parser_observations)
    elif replacement_ratio > Decimal("0.02") or mixed_script_ratio > Decimal("0.08"):
        primary = PageHealthKind.DAMAGED_ENCODING
        route = OcrRoute.APPLE_VISION
        signals.append(
            "mixed_script_ocr_garble_high"
            if mixed_script_ratio > Decimal("0.08")
            else "replacement_or_control_ratio_high"
        )
    elif not stripped and image_count:
        primary = PageHealthKind.RASTER_ONLY
        route = OcrRoute.APPLE_VISION
        signals.append("image_without_native_text")
    elif not stripped:
        primary = PageHealthKind.BLANK
        route = OcrRoute.NOT_REQUIRED
        signals.append("no_text_or_image")
    elif image_count and length < 80:
        primary = PageHealthKind.EXISTING_OCR
        route = OcrRoute.APPLE_VISION
        signals.append("suspiciously_sparse_text_over_image")
    elif image_count:
        primary = PageHealthKind.MIXED
        route = OcrRoute.NOT_REQUIRED
        signals.append("native_text_and_image_regions")
    elif table_heavy or TABLE_SIGNAL.search(text):
        primary = PageHealthKind.TABLE_HEAVY
        route = OcrRoute.NOT_REQUIRED
        signals.append("table_structure_detected")
    elif DRAWING_SIGNAL.search(text):
        primary = PageHealthKind.DRAWING
        route = OcrRoute.VLM_REQUIRED
        signals.append("drawing_semantics_require_future_drawing_intelligence")
    else:
        primary = PageHealthKind.BORN_DIGITAL
        route = OcrRoute.NOT_REQUIRED
        signals.append("native_text_quality_accepted")
    if "duplicate_dictionary_definition" in parser_observations:
        signals.append("native_parser_observation:duplicate_dictionary_definition")
    identity = deterministic_uuid(
        f"page-health:{document_id}:{document_version}:{page_number}:{PAGE_HEALTH_PROFILE_VERSION}"
    )
    return PageHealthAnalysis(
        identity,
        page_number,
        primary,
        tuple(signals),
        length,
        replacement_ratio.quantize(Decimal("0.000001")),
        image_count,
        rotation_degrees,
        width_points,
        height_points,
        route,
        PAGE_HEALTH_PROFILE_VERSION,
    )


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _mixed_script_token_ratio(value: str) -> Decimal:
    tokens = SCRIPT_TOKEN.findall(value)
    if not tokens:
        return Decimal("0")
    suspicious = 0
    for token in tokens:
        has_latin = re.search(r"[A-Za-z]", token) is not None
        has_cyrillic = re.search(r"[\u0410-\u044f\u0401\u0451]", token) is not None
        noisy_punctuation = re.search(r"[|{}\\]", token) is not None
        if (has_latin and has_cyrillic) or noisy_punctuation:
            suspicious += 1
    return Decimal(suspicious) / Decimal(len(tokens))


class _PypdfWarningCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self._codes: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "Rotated text discovered" in message and "incomplete" in message:
            self._codes.add("rotated_text_incomplete")
        elif "Multiple definitions in dictionary" in message:
            self._codes.add("duplicate_dictionary_definition")
        else:
            self._codes.add("parser_warning")

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._codes))


def _group_pdf_lines(
    fragments: list[tuple[str, float, float, float, str | None]],
    *,
    layout_lines: tuple[str, ...] = (),
) -> tuple[tuple[str, float, float, float, float, str | None, float], ...]:
    """Group positioned PDF text fragments into deterministic visual lines."""

    positioned_fragments = _position_unanchored_pdf_fragments(fragments)
    expanded: list[tuple[str, float, float, float, str | None]] = []
    for raw, x, y, font_size, font_name in positioned_fragments:
        parts = [part for part in raw.splitlines() if part.strip()]
        for offset, part in enumerate(parts):
            expanded.append((part, x, y - offset * max(font_size, 1.0), font_size, font_name))
    ordered = sorted(expanded, key=lambda item: (-item[2], item[1], item[0]))
    groups: list[list[tuple[str, float, float, float, str | None]]] = []
    baselines: list[float] = []
    for fragment in ordered:
        _, _, y, font_size, _ = fragment
        match_index = next(
            (
                index
                for index, baseline in enumerate(baselines)
                if abs(baseline - y) <= max(2.0, font_size * 0.4)
            ),
            None,
        )
        if match_index is None:
            groups.append([fragment])
            baselines.append(y)
        else:
            groups[match_index].append(fragment)
            baselines[match_index] = sum(item[2] for item in groups[match_index]) / len(
                groups[match_index]
            )
    lines: list[tuple[str, float, float, float, float, str | None, float]] = []
    for group in groups:
        positioned = sorted(group, key=lambda item: (item[1], item[0]))
        line_parts: list[str] = []
        previous_end: float | None = None
        for raw, x, _y, font_size, _font_name in positioned:
            estimated_width = max(font_size, len(raw) * font_size * 0.52)
            if previous_end is not None and x - previous_end > font_size * 0.35:
                line_parts.append(" ")
            line_parts.append(raw)
            previous_end = max(previous_end or x, x + estimated_width)
        text = normalize_text("".join(line_parts))
        if not text:
            continue
        x0 = min(item[1] for item in positioned)
        baseline = sum(item[2] for item in positioned) / len(positioned)
        maximum_font = max(item[3] for item in positioned)
        x1 = max(item[1] + max(item[3], len(item[0]) * item[3] * 0.52) for item in positioned)
        font_name = next((item[4] for item in positioned if item[4]), None)
        lines.append(
            (
                text,
                x0,
                baseline - maximum_font * 0.25,
                x1,
                baseline + maximum_font,
                font_name,
                maximum_font,
            )
        )
    if len(layout_lines) == len(lines):
        return tuple(
            (layout_text, *line[1:]) for layout_text, line in zip(layout_lines, lines, strict=True)
        )
    return tuple(lines)


def _position_unanchored_pdf_fragments(
    fragments: list[tuple[str, float, float, float, str | None]],
) -> tuple[tuple[str, float, float, float, str | None], ...]:
    """Recover pypdf fragments whose text matrix was reset to the identity matrix.

    Some PDFs emit continuation glyph runs at ``(0, 0)`` between two properly
    positioned runs.  Their order remains authoritative; attaching them to the
    immediately preceding visual run preserves the printed line without treating
    the PDF extraction quirk as a real page coordinate.
    """

    resolved: list[tuple[str, float, float, float, str | None]] = []
    for index, fragment in enumerate(fragments):
        raw, x, y, font_size, font_name = fragment
        if x != 0.0 or y != 0.0:
            resolved.append(fragment)
            continue
        previous = next(
            (value for value in reversed(resolved) if value[1] != 0.0 or value[2] != 0.0),
            None,
        )
        following = next(
            (value for value in fragments[index + 1 :] if value[1] != 0.0 or value[2] != 0.0),
            None,
        )
        if previous is None and following is None:
            continue
        anchor = previous or following
        assert anchor is not None
        effective_font = max(font_size, anchor[3], 1.0)
        if previous is not None:
            previous_width = max(previous[3], len(previous[0].strip()) * previous[3] * 0.52)
            resolved.append(
                (
                    raw,
                    previous[1] + previous_width,
                    previous[2],
                    effective_font,
                    font_name or previous[4],
                )
            )
        else:
            estimated_width = max(effective_font, len(raw.strip()) * effective_font * 0.52)
            resolved.append(
                (
                    raw,
                    max(0.0, anchor[1] - estimated_width),
                    anchor[2],
                    effective_font,
                    font_name or anchor[4],
                )
            )
    return tuple(resolved)


def _element(
    document_id: UUID,
    document_version: int,
    source_version_id: UUID,
    page_number: int,
    region: tuple[float, float, float, float],
    order: int,
    kind: str,
    raw: str,
    normalized: str,
    font_name: str | None,
    font_size: Decimal | None,
    row_index: int | None = None,
    column_index: int | None = None,
    *,
    cell: str | None = None,
) -> LayoutElement:
    evidence_digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    locator_id = deterministic_uuid(
        f"understanding-locator:{source_version_id}:{page_number}:{region}:{cell or order}"
    )
    locator = ExactLocator(
        source_version_id,
        locator_id,
        document_id,
        document_version,
        page_number,
        region,
        evidence_digest,
        cell,
    )
    element_id = deterministic_uuid(
        f"layout-element:{source_version_id}:{page_number}:{kind}:{order}:{evidence_digest}"
    )
    return LayoutElement(
        element_id,
        kind,
        raw,
        normalized,
        order,
        locator,
        font_name,
        font_size,
        0,
        row_index,
        column_index,
    )


def _document(
    media_type: str,
    kind: str,
    parser_key: str,
    parser_version: str,
    pages: tuple[NativePage, ...],
    gaps: tuple[str, ...],
) -> NativeDocument:
    payload = {
        "media_type": media_type,
        "kind": kind,
        "parser_key": parser_key,
        "parser_version": parser_version,
        "pages": [
            {
                "page": page.page_number,
                "health": page.health.fingerprint,
                "elements": [item.locator.evidence_digest for item in page.elements],
            }
            for page in pages
        ],
        "gaps": gaps,
    }
    import rfc8785

    return NativeDocument(
        media_type,
        kind,
        parser_key,
        parser_version,
        pages,
        gaps,
        "sha256:" + hashlib.sha256(rfc8785.dumps(payload)).hexdigest(),  # type: ignore[arg-type]
    )


def _textual_office_document(
    media_type: str,
    kind: str,
    parser_key: str,
    elements: list[LayoutElement],
    document_id: UUID,
    version: int,
) -> NativeDocument:
    page = _office_page(document_id, version, 1, elements, table_heavy=kind in {"xlsx", "csv"})
    return _document(media_type, kind, parser_key, "0.1.0", (page,), ())


def _office_page(
    document_id: UUID,
    version: int,
    page: int,
    elements: list[LayoutElement],
    *,
    table_heavy: bool,
) -> NativePage:
    text = "\n".join(item.raw_text for item in elements)
    health = analyze_page_health(
        document_id=document_id,
        document_version=version,
        page_number=page,
        text=text,
        image_count=0,
        width_points=Decimal("595"),
        height_points=Decimal("842"),
        rotation_degrees=0,
        table_heavy=table_heavy,
    )
    return NativePage(page, Decimal("595"), Decimal("842"), 0, 0, tuple(elements), health)


def _non_native_page(
    *, document_id: UUID, document_version: int, source_version_id: UUID, media_type: str
) -> NativePage:
    del source_version_id, media_type
    health = analyze_page_health(
        document_id=document_id,
        document_version=document_version,
        page_number=1,
        text="",
        image_count=1,
        width_points=Decimal("1"),
        height_points=Decimal("1"),
        rotation_degrees=0,
    )
    return NativePage(1, Decimal("1"), Decimal("1"), 0, 1, (), health)


def _pdf_image_count(page: Any) -> int:
    try:
        resources = page.get("/Resources")
        if resources is None:
            return 0
        resources = resources.get_object()
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return 0
        return sum(
            1
            for value in xobjects.get_object().values()
            if value.get_object().get("/Subtype") == "/Image"
        )
    except (AttributeError, KeyError, TypeError):
        return 0


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{S_NS}t")) for item in root]


def _xlsx_cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    inline = cell.find(f"{S_NS}is")
    if inline is not None:
        return "".join(node.text or "" for node in inline.iter(f"{S_NS}t"))
    value = cell.find(f"{S_NS}v")
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        index = int(value.text)
        if index < 0 or index >= len(shared):
            raise ValueError("xlsx_shared_string_index_invalid")
        return shared[index]
    return value.text


def _cell_coordinates(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", value)
    if match is None:
        raise ValueError("xlsx_cell_reference_invalid")
    column = 0
    for character in match.group(1):
        column = column * 26 + ord(character) - 64
    return int(match.group(2)), column


def _grid_region(
    row: int, column: int, max_rows: int, max_columns: int
) -> tuple[float, float, float, float]:
    x0 = min(0.999, (column - 1) / max_columns)
    x1 = min(1.0, max(x0 + 1 / max_columns, column / max_columns))
    y0 = min(0.999, (row - 1) / max_rows)
    y1 = min(1.0, max(y0 + 1 / max_rows, row / max_rows))
    return (x0, y0, x1, y1)


def _line_region(order: int, maximum: int) -> tuple[float, float, float, float]:
    y0 = min(0.98, (order - 1) / maximum)
    return (0.02, y0, 0.98, min(1.0, y0 + 1 / maximum))


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _non_empty_region(
    x0: float, y0: float, x1: float, y1: float
) -> tuple[float, float, float, float]:
    x0, x1 = sorted((_bounded(x0), _bounded(x1)))
    y0, y1 = sorted((_bounded(y0), _bounded(y1)))
    if x1 <= x0:
        x1 = min(1.0, x0 + 0.001)
        x0 = max(0.0, x1 - 0.001)
    if y1 <= y0:
        y1 = min(1.0, y0 + 0.001)
        y0 = max(0.0, y1 - 0.001)
    return (x0, y0, x1, y1)
