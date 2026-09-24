# ruff: noqa: E501, RUF001
"""Qualified editable AOSR form derived from the exact 344/pr form semantics.

The DOCX is an editable representation, not a claim that the Ministry published
DOCX bytes.  Qualification pins the official PDF source/profile and verifies
that all semantic bindings remain editable text in a four-page A4 document.
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from asd_kontur.harness.models import digest_of

EDITABLE_AOSR_PROFILE_VERSION = "support.aosr.344pr-2023.editable@1.0.0"
EDITABLE_AOSR_RENDERER_VERSION = "support.editable-docx-renderer@1.0.0"
EDITABLE_AOSR_VALIDATOR_VERSION = "support.editable-docx-print-validator@1.0.0"
EDITABLE_AOSR_PAGE_COUNT = 4
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_FIELDS = (
    "object_name",
    "developer_identity",
    "builder_identity",
    "designer_identity",
    "act_number",
    "act_date",
    "customer_representative",
    "builder_representative",
    "construction_control_representative",
    "designer_representative",
    "work_performer_representative",
    "inspection_participants",
    "hidden_work_description",
    "project_document_reference",
    "materials_and_quality_documents",
    "control_evidence_documents",
    "work_start_date",
    "work_end_date",
    "compliance_basis",
    "next_works",
    "additional_information",
    "paper_copy_count",
    "appendices",
    "customer_signatory_name",
    "builder_signatory_name",
    "construction_control_signatory_name",
    "designer_signatory_name",
    "work_performer_signatory_name",
)


@dataclass(frozen=True, slots=True)
class EditableAosrQualificationReceipt:
    official_profile_fingerprint: str
    official_source_digest: str
    template_digest: str
    profile_version: str
    renderer_profile_version: str
    validator_profile_version: str
    page_count: int
    field_keys: tuple[str, ...]
    check_codes: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class EditableAosrPrintReceipt:
    document_digest: str
    rendered_pdf_digest: str
    page_count: int
    check_codes: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


def build_editable_aosr_template() -> bytes:
    """Build the bounded Russian AOSR form as editable WordprocessingML."""

    pages = (
        (
            _center("Приложение № 3 к составу исполнительной документации"),
            _center("Рекомендуемый образец"),
            _field("Объект капитального строительства", "object_name"),
            _hint("Наименование и адрес объекта по проектной документации"),
            _field(
                "Застройщик, технический заказчик или иное ответственное лицо",
                "developer_identity",
            ),
            _hint("Наименование, ОГРН, ИНН, адрес, контактные данные и СРО — при наличии"),
            _field(
                "Лицо, осуществляющее строительство, реконструкцию, капитальный ремонт",
                "builder_identity",
            ),
            _hint("Наименование, ОГРН, ИНН, адрес, контактные данные и СРО — при наличии"),
            _field(
                "Лицо, осуществляющее подготовку проектной документации",
                "designer_identity",
            ),
            _hint("Наименование, ОГРН, ИНН, адрес, контактные данные и СРО — при наличии"),
        ),
        (
            _center("АКТ ОСВИДЕТЕЛЬСТВОВАНИЯ СКРЫТЫХ РАБОТ", bold=True),
            _two_fields("№", "act_number", "Дата составления", "act_date"),
            _field(
                "Представитель застройщика (технического заказчика) по вопросам строительного контроля",
                "customer_representative",
            ),
            _hint("Должность, Ф.И.О., НРС и документ о полномочиях — когда применимо"),
            _field(
                "Представитель лица, осуществляющего строительство",
                "builder_representative",
            ),
            _hint("Должность, Ф.И.О. и документ о полномочиях"),
            _field(
                "Представитель лица, осуществляющего строительство, по вопросам строительного контроля",
                "construction_control_representative",
            ),
            _hint("Должность, Ф.И.О., НРС и документ о полномочиях — когда применимо"),
            _field(
                "Представитель лица, осуществляющего подготовку проектной документации",
                "designer_representative",
            ),
            _hint("Должность, Ф.И.О. и документ о полномочиях"),
        ),
        (
            _field(
                "Представитель лица, выполнившего работы, подлежащие освидетельствованию",
                "work_performer_representative",
            ),
            _field("Участники осмотра", "inspection_participants"),
            _text("произвели осмотр работ и составили настоящий акт о нижеследующем:"),
            _field("1. К освидетельствованию предъявлены работы", "hidden_work_description"),
            _field("2. Работы выполнены по проектной документации", "project_document_reference"),
            _field(
                "3. При выполнении работ применены материалы (изделия) и документы о качестве",
                "materials_and_quality_documents",
            ),
            _field(
                "4. Предъявлены документы, подтверждающие соответствие работ требованиям",
                "control_evidence_documents",
            ),
            _two_fields(
                "5. Дата начала работ", "work_start_date", "Дата окончания", "work_end_date"
            ),
            _field("6. Работы выполнены в соответствии с", "compliance_basis"),
        ),
        (
            _field("7. Разрешается производство последующих работ", "next_works"),
            _field("Дополнительные сведения", "additional_information"),
            _field("Акт составлен в количестве экземпляров", "paper_copy_count"),
            _field("Приложения", "appendices"),
            _signature(
                "Представитель застройщика (технического заказчика) по вопросам строительного контроля",
                "customer_signatory_name",
            ),
            _signature(
                "Представитель лица, осуществляющего строительство", "builder_signatory_name"
            ),
            _signature(
                "Представитель лица, осуществляющего строительство, по вопросам строительного контроля",
                "construction_control_signatory_name",
            ),
            _signature(
                "Представитель лица, осуществляющего подготовку проектной документации",
                "designer_signatory_name",
            ),
            _signature(
                "Представитель лица, выполнившего освидетельствуемые работы",
                "work_performer_signatory_name",
            ),
        ),
    )
    body: list[str] = []
    for page_number, page in enumerate(pages, start=1):
        body.extend(page)
        if page_number < len(pages):
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="680" w:right="850" w:bottom="680" w:left="850" '
        'w:header="360" w:footer="360" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    files = {
        "[Content_Types].xml": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            '<Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        ),
        "docProps/core.xml": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:title>Акт освидетельствования скрытых работ</dc:title>"
            "<dc:creator>ASD-KONTUR</dc:creator><cp:revision>1</cp:revision>"
            '<dcterms:created xsi:type="dcterms:W3CDTF">1980-01-01T00:00:00Z</dcterms:created>'
            '<dcterms:modified xsi:type="dcterms:W3CDTF">1980-01-01T00:00:00Z</dcterms:modified>'
            "</cp:coreProperties>"
        ),
        "docProps/app.xml": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Template>Normal.dotm</Template><Application>ASD-KONTUR</Application>"
            "<Pages>4</Pages><AppVersion>1.0</AppVersion></Properties>"
        ),
        "word/document.xml": _xml_bytes(document),
        "word/_rels/document.xml.rels": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>'
            "</Relationships>"
        ),
        "word/fontTable.xml": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:font w:name="Times New Roman"><w:family w:val="roman"/>'
            '<w:pitch w:val="variable"/></w:font></w:fonts>'
        ),
        "word/styles.xml": _xml_bytes(_styles()),
        "word/settings.xml": _xml_bytes(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:compat/><w:doNotTrackMoves/><w:doNotTrackFormatting/>"
            "</w:settings>"
        ),
    }
    return _zip_bytes(files)


def qualify_editable_aosr_template(
    *,
    template_bytes: bytes,
    official_profile_fingerprint: str,
    official_source_digest: str,
    converter_path: Path,
) -> EditableAosrQualificationReceipt:
    checks = list(validate_editable_aosr_template(template_bytes))
    rendered = _convert_to_pdf(template_bytes, converter_path)
    reader = PdfReader(io.BytesIO(rendered))
    if len(reader.pages) != EDITABLE_AOSR_PAGE_COUNT:
        raise ValueError("editable_aosr_page_count_mismatch")
    text = " ".join((page.extract_text() or "") for page in reader.pages)
    for marker in (
        "АКТ ОСВИДЕТЕЛЬСТВОВАНИЯ СКРЫТЫХ РАБОТ",
        "К освидетельствованию предъявлены работы",
        "Разрешается производство последующих работ",
    ):
        if _normalize(marker) not in _normalize(text):
            raise ValueError("editable_aosr_rendered_marker_missing")
    checks.extend(("FOUR_A4_PAGES_RENDERED", "FORM_MARKERS_RENDERED"))
    return EditableAosrQualificationReceipt(
        official_profile_fingerprint,
        official_source_digest,
        _sha256(template_bytes),
        EDITABLE_AOSR_PROFILE_VERSION,
        EDITABLE_AOSR_RENDERER_VERSION,
        EDITABLE_AOSR_VALIDATOR_VERSION,
        len(reader.pages),
        _FIELDS,
        tuple(checks),
    )


def validate_generated_editable_aosr(
    *,
    document_bytes: bytes,
    expected_values: Mapping[str, str],
    converter_path: Path,
) -> EditableAosrPrintReceipt:
    checks = list(validate_editable_aosr_template(document_bytes, tokens_expected=False))
    rendered = _convert_to_pdf(document_bytes, converter_path)
    reader = PdfReader(io.BytesIO(rendered))
    if len(reader.pages) != EDITABLE_AOSR_PAGE_COUNT:
        raise ValueError("editable_aosr_generated_page_count_mismatch")
    rendered_text = _normalize(" ".join((page.extract_text() or "") for page in reader.pages))
    for key, value in expected_values.items():
        normalized = _normalize(value)
        if normalized and normalized not in rendered_text:
            raise ValueError(f"editable_aosr_rendered_value_missing:{key}")
    checks.extend(("FOUR_A4_PAGES_RENDERED", "CONFIRMED_VALUES_RENDERED"))
    return EditableAosrPrintReceipt(
        _sha256(document_bytes),
        _sha256(rendered),
        len(reader.pages),
        tuple(checks),
    )


def validate_editable_aosr_template(
    payload: bytes, *, tokens_expected: bool = True
) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            names = set(package.namelist())
            required = {
                "[Content_Types].xml",
                "_rels/.rels",
                "word/document.xml",
                "word/styles.xml",
                "word/settings.xml",
            }
            if required - names:
                raise ValueError("editable_aosr_package_member_missing")
            if any(name.endswith("vbaProject.bin") or "externalLink" in name for name in names):
                raise ValueError("editable_aosr_active_content_forbidden")
            document = package.read("word/document.xml")
            ET.fromstring(document)
            text = document.decode("utf-8")
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise ValueError("editable_aosr_package_invalid") from exc
    if text.count('w:type="page"') != EDITABLE_AOSR_PAGE_COUNT - 1:
        raise ValueError("editable_aosr_page_break_count_mismatch")
    for field_key in _FIELDS:
        count = text.count("{{" + field_key + "}}")
        if tokens_expected and count != 1:
            raise ValueError(f"editable_aosr_field_binding_invalid:{field_key}")
        if not tokens_expected and count:
            raise ValueError(f"editable_aosr_unresolved_field:{field_key}")
    return (
        "DOCX_PACKAGE_COMPLETE",
        "ACTIVE_CONTENT_ABSENT",
        "A4_PAGE_SETTINGS_PRESENT",
        "EDITABLE_TEXT_BINDINGS_COMPLETE" if tokens_expected else "FIELD_BINDINGS_RESOLVED",
    )


def field_keys() -> tuple[str, ...]:
    return _FIELDS


def _convert_to_pdf(document_bytes: bytes, converter_path: Path) -> bytes:
    if not converter_path.is_absolute() or not converter_path.is_file():
        raise ValueError("editable_aosr_converter_unavailable")
    with tempfile.TemporaryDirectory(prefix="asd-aosr-") as directory:
        root = Path(directory)
        source = root / "input.docx"
        target = root / "output.pdf"
        source.write_bytes(document_bytes)
        completed = subprocess.run(
            [str(converter_path), str(source), str(target)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
            check=False,
        )
        if completed.returncode != 0 or not target.is_file():
            raise ValueError("editable_aosr_conversion_failed")
        return target.read_bytes()


def _field(label: str, key: str) -> str:
    return _text(label, bold=True, after=40) + _token(key)


def _signature(label: str, key: str) -> str:
    return _text(label, bold=True, after=20) + _token(
        key, suffix="                         (подпись)"
    )


def _two_fields(left_label: str, left_key: str, right_label: str, right_key: str) -> str:
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="10200" w:type="dxa"/>'
        '<w:tblBorders><w:bottom w:val="nil"/></w:tblBorders></w:tblPr><w:tblGrid>'
        '<w:gridCol w:w="5100"/><w:gridCol w:w="5100"/></w:tblGrid><w:tr>'
        + _cell(left_label, left_key)
        + _cell(right_label, right_key)
        + "</w:tr></w:tbl>"
    )


def _cell(label: str, key: str) -> str:
    return (
        '<w:tc><w:tcPr><w:tcW w:w="5100" w:type="dxa"/></w:tcPr>' + _field(label, key) + "</w:tc>"
    )


def _token(key: str, *, suffix: str = "") -> str:
    return (
        '<w:p><w:pPr><w:spacing w:after="70"/><w:keepNext/></w:pPr>'
        '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t xml:space="preserve">'
        + _escape("{{" + key + "}}" + suffix)
        + "</w:t></w:r></w:p>"
    )


def _text(value: str, *, bold: bool = False, after: int = 20) -> str:
    run = "<w:b/>" if bold else ""
    return (
        f'<w:p><w:pPr><w:spacing w:after="{after}"/><w:keepNext/></w:pPr>'
        f"<w:r><w:rPr>{run}</w:rPr><w:t>{_escape(value)}</w:t></w:r></w:p>"
    )


def _center(value: str, *, bold: bool = False) -> str:
    run = "<w:b/>" if bold else ""
    return (
        '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="100"/></w:pPr>'
        f"<w:r><w:rPr>{run}</w:rPr><w:t>{_escape(value)}</w:t></w:r></w:p>"
    )


def _hint(value: str) -> str:
    return (
        '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="35"/></w:pPr>'
        '<w:r><w:rPr><w:i/><w:sz w:val="14"/></w:rPr>'
        f"<w:t>{_escape(value)}</w:t></w:r></w:p>"
    )


def _styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" '
        'w:hAnsi="Times New Roman" w:eastAsia="Times New Roman"/><w:sz w:val="18"/>'
        '<w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
        '<w:spacing w:line="220" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>'
    )


def _zip_bytes(files: Mapping[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as package:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            package.writestr(info, files[name])
    return target.getvalue()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _xml_bytes(value: str) -> bytes:
    return value.encode("utf-8")


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
