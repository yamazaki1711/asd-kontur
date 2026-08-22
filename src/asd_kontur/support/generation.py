"""Stateless synthetic DOCX/XLSX generation and structural qualification.

The adapters prove deterministic OOXML package mechanics only. They do not
claim official template authority, production renderer qualification, or
print readiness.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .errors import SupportError, SupportErrorCode
from .models import (
    FieldResolution,
    GeneratedDocumentCandidate,
    GenerationRequest,
    ResolutionState,
)

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_TOKEN = re.compile(r"\{\{[A-Za-z0-9_.-]+\}\}")


@dataclass(frozen=True, slots=True)
class PackageValidation:
    valid: bool
    checks: tuple[str, ...]
    blockers: tuple[str, ...]


class SyntheticOoxmlGenerationPipeline:
    """One fresh deterministic OOXML package per GenerationRun."""

    def generate(self, request: GenerationRequest) -> GeneratedDocumentCandidate:
        blockers = _field_blockers(request.fields)
        if blockers:
            raise SupportError(
                SupportErrorCode.GENERATION_BLOCKED,
                "Material fields are missing, conflicting, or not evidence-bound: "
                + ",".join(blockers),
            )
        values = {
            field.field_key: field.display_value or str(field.normalized_value)
            for field in request.fields
            if field.state is ResolutionState.CONFIRMED
        }
        if request.requested_format == "DOCX":
            payload = _build_docx(values)
            validation = validate_docx(payload, required_fields=tuple(values))
        elif request.requested_format == "XLSX":
            payload = _build_xlsx(values)
            validation = validate_xlsx(payload, required_fields=tuple(values))
        else:
            raise SupportError(
                SupportErrorCode.GENERATION_BLOCKED,
                "The synthetic qualification adapter supports DOCX and XLSX only.",
            )
        if not validation.valid:
            raise SupportError(
                SupportErrorCode.GENERATION_BLOCKED,
                "Generated OOXML package failed structural validation: "
                + ",".join(validation.blockers),
            )
        return GeneratedDocumentCandidate(
            request.generation_run_id,
            request.requested_format,
            request.input_fingerprint,
            f"sha256:{hashlib.sha256(payload).hexdigest()}",
            payload,
            validation.checks,
        )


def validate_docx(payload: bytes, *, required_fields: tuple[str, ...]) -> PackageValidation:
    required_members = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/styles.xml",
        "word/settings.xml",
    }
    blockers: list[str] = []
    checks: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            names = set(package.namelist())
            missing = sorted(required_members - names)
            if missing:
                blockers.append("DOCX_PACKAGE_MEMBER_MISSING")
            else:
                checks.append("DOCX_PACKAGE_COMPLETE")
            document = package.read("word/document.xml")
            ET.fromstring(document)
            text = document.decode("utf-8")
            if _TOKEN.search(text):
                blockers.append("DOCX_UNRESOLVED_TOKEN")
            else:
                checks.append("DOCX_NO_UNRESOLVED_TOKEN")
            for field_key in required_fields:
                if f'data-field-key="{field_key}"' not in text:
                    blockers.append("DOCX_REQUIRED_FIELD_MISSING")
                    break
            else:
                checks.append("DOCX_REQUIRED_FIELD_COVERAGE")
            if "w:sectPr" not in text or "w:pgSz" not in text or "w:pgMar" not in text:
                blockers.append("DOCX_PAGE_SETTINGS_MISSING")
            else:
                checks.append("DOCX_PAGE_SETTINGS_PRESENT")
            if any(name.endswith("vbaProject.bin") for name in names):
                blockers.append("DOCX_ACTIVE_CONTENT_FORBIDDEN")
            if any("externalLink" in name for name in names):
                blockers.append("DOCX_EXTERNAL_LINK_FORBIDDEN")
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        blockers.append("DOCX_PACKAGE_INVALID")
    return PackageValidation(not blockers, tuple(checks), tuple(sorted(set(blockers))))


def validate_xlsx(payload: bytes, *, required_fields: tuple[str, ...]) -> PackageValidation:
    required_members = {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/worksheets/sheet1.xml",
        "xl/styles.xml",
    }
    blockers: list[str] = []
    checks: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            names = set(package.namelist())
            if required_members - names:
                blockers.append("XLSX_PACKAGE_MEMBER_MISSING")
            else:
                checks.append("XLSX_PACKAGE_COMPLETE")
            workbook = package.read("xl/workbook.xml").decode("utf-8")
            sheet = package.read("xl/worksheets/sheet1.xml").decode("utf-8")
            ET.fromstring(workbook)
            ET.fromstring(sheet)
            if "_xlnm.Print_Area" not in workbook or "_xlnm.Print_Titles" not in workbook:
                blockers.append("XLSX_PRINT_DEFINITION_MISSING")
            else:
                checks.append("XLSX_PRINT_DEFINITIONS_PRESENT")
            required_fragments = ("<mergeCells", "<pageMargins", "<pageSetup", "<sheetProtection")
            if any(fragment not in sheet for fragment in required_fragments):
                blockers.append("XLSX_LAYOUT_CONTROL_MISSING")
            else:
                checks.append("XLSX_LAYOUT_CONTROLS_PRESENT")
            if "<f>SUM(B2:B" not in sheet:
                blockers.append("XLSX_TOTAL_FORMULA_MISSING")
            else:
                checks.append("XLSX_FORMULA_PRESENT")
            if '<sheet name="HiddenEvidence" sheetId="2" state="hidden"' not in workbook:
                blockers.append("XLSX_HIDDEN_SHEET_STATE_MISSING")
            else:
                checks.append("XLSX_HIDDEN_SHEET_STATE_PRESENT")
            for field_key in required_fields:
                if f"field:{_xml_escape(field_key)}" not in sheet:
                    blockers.append("XLSX_REQUIRED_FIELD_MISSING")
                    break
            else:
                checks.append("XLSX_REQUIRED_FIELD_COVERAGE")
            if any(name.endswith("vbaProject.bin") for name in names):
                blockers.append("XLSX_ACTIVE_CONTENT_FORBIDDEN")
            if any("externalLink" in name for name in names):
                blockers.append("XLSX_EXTERNAL_LINK_FORBIDDEN")
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        blockers.append("XLSX_PACKAGE_INVALID")
    return PackageValidation(not blockers, tuple(checks), tuple(sorted(set(blockers))))


def _field_blockers(fields: tuple[FieldResolution, ...]) -> tuple[str, ...]:
    blockers: list[str] = []
    for field in fields:
        if not field.material:
            continue
        if field.state not in {ResolutionState.CONFIRMED, ResolutionState.NOT_APPLICABLE}:
            blockers.append(f"{field.field_key}:{field.state}")
        elif field.state is ResolutionState.CONFIRMED and (
            not field.evidence_link_ids or not field.source_locator_ids
        ):
            blockers.append(f"{field.field_key}:evidence_missing")
    return tuple(sorted(blockers))


def _zip_bytes(files: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            package.writestr(info, files[name])
    return buffer.getvalue()


def _build_docx(values: Mapping[str, str]) -> bytes:
    paragraphs = "".join(
        f'<w:p><w:r><w:t data-field-key="{_xml_escape(key)}">{_xml_escape(value)}</w:t></w:r></w:p>'
        for key, value in sorted(values.items())
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Evidence-bound synthetic form</w:t></w:r>"
        "</w:p></w:tc></w:tr></w:tbl>"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>"
            ),
            "word/document.xml": _bytes(document),
            "word/styles.xml": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
                "</w:styles>"
            ),
            "word/settings.xml": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:compat/></w:settings>"
            ),
        }
    )


def _build_xlsx(values: Mapping[str, str]) -> bytes:
    rows: list[str] = []
    for index, (key, value) in enumerate(sorted(values.items()), start=2):
        rows.append(
            f'<row r="{index}"><c r="A{index}" t="inlineStr"><is><t>field:{_xml_escape(key)}</t></is></c>'
            f'<c r="B{index}" t="inlineStr"><is><t>{_xml_escape(value)}</t></is></c></row>'
        )
    total_row = len(rows) + 2
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Support ID synthetic form</t></is></c></row>{"".join(rows)}'
        f'<row r="{total_row}"><c r="A{total_row}" t="inlineStr"><is><t>Total</t></is></c>'
        f'<c r="B{total_row}"><f>SUM(B2:B{total_row - 1})</f><v>0</v></c></row></sheetData>'
        f'<mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells>'
        '<sheetProtection sheet="1" objects="1" scenarios="1"/>'
        '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="portrait" paperSize="9" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>"
    )
    hidden_sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Evidence manifest digest only</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="SupportForm" sheetId="1" r:id="rId1"/>'
        '<sheet name="HiddenEvidence" sheetId="2" state="hidden" r:id="rId2"/></sheets>'
        '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">SupportForm!$A$1:$B$99</definedName>'
        '<definedName name="_xlnm.Print_Titles" localSheetId="0">SupportForm!$1:$1</definedName></definedNames>'
        '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
    )
    return _zip_bytes(
        {
            "[Content_Types].xml": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
            "xl/workbook.xml": _bytes(workbook),
            "xl/_rels/workbook.xml.rels": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                "</Relationships>"
            ),
            "xl/worksheets/sheet1.xml": _bytes(sheet),
            "xl/worksheets/sheet2.xml": _bytes(hidden_sheet),
            "xl/styles.xml": _bytes(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<fonts count="1"><font><sz val="10"/><name val="Arial"/></font></fonts>'
                '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
                '<borders count="1"><border/></borders><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs>'
                "</styleSheet>"
            ),
        }
    )


def _bytes(value: str) -> bytes:
    return value.encode("utf-8")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
