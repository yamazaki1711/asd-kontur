"""Official form qualification and deterministic PDF-overlay rendering.

The renderer is form-independent.  Exact page selection, field positions and
font bytes belong to a versioned TemplateVersion/BindingPlan and are supplied
as data.  An official source PDF is never modified in place.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from asd_kontur.harness.models import digest_of

from .models import FieldResolution, ResolutionState
from .production import TemplateRenderResult


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class PdfOverlayBinding:
    """One field target in PDF user-space coordinates (bottom-left origin)."""

    field_key: str
    page_index: int
    x: float
    y: float
    width: float
    height: float
    font_size: float = 8.0
    line_height: float = 9.5
    alignment: str = "left"
    material: bool = True
    required: bool = True

    def __post_init__(self) -> None:
        if not self.field_key or self.page_index < 1:
            raise ValueError("pdf binding requires field key and positive page index")
        if min(self.x, self.y, self.width, self.height, self.font_size, self.line_height) <= 0:
            raise ValueError("pdf binding coordinates and typography must be positive")
        if self.alignment not in {"left", "center", "right"}:
            raise ValueError("pdf binding alignment is invalid")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class OfficialPdfFormProfile:
    profile_version: str
    source_digest: str
    source_version_ref: str
    normative_edition_ref: str
    official_url: str
    page_numbers: tuple[int, ...]
    expected_markers: tuple[str, ...]
    bindings: tuple[PdfOverlayBinding, ...]
    renderer_profile_version: str
    validator_profile_version: str

    def __post_init__(self) -> None:
        if not self.source_digest.startswith("sha256:"):
            raise ValueError("official form profile requires source SHA-256")
        if not self.source_version_ref or not self.normative_edition_ref:
            raise ValueError("official form profile requires exact source and edition")
        if not self.official_url.startswith("https://"):
            raise ValueError("official form profile requires an HTTPS source URL")
        if not self.page_numbers or tuple(sorted(set(self.page_numbers))) != self.page_numbers:
            raise ValueError("official form pages must be unique and ordered")
        if not self.expected_markers or not self.bindings:
            raise ValueError("official form profile requires markers and a binding plan")
        if any(value.lower() == "latest" for value in self._versions()):
            raise ValueError("official form profile must pin exact versions")

    def _versions(self) -> tuple[str, ...]:
        return (
            self.profile_version,
            self.source_version_ref,
            self.normative_edition_ref,
            self.renderer_profile_version,
            self.validator_profile_version,
        )

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class TemplateQualificationReceipt:
    profile_fingerprint: str
    source_digest: str
    template_digest: str
    source_version_ref: str
    normative_edition_ref: str
    official_url: str
    source_page_count: int
    selected_pages: tuple[int, ...]
    selected_page_geometry: tuple[tuple[float, float], ...]
    check_codes: tuple[str, ...]
    result: str
    blocker_codes: tuple[str, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.result == "qualified" and self.blocker_codes:
            raise ValueError("qualified template receipt cannot contain blockers")
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "profile_fingerprint": self.profile_fingerprint,
            "source_digest": self.source_digest,
            "template_digest": self.template_digest,
            "source_version_ref": self.source_version_ref,
            "normative_edition_ref": self.normative_edition_ref,
            "official_url": self.official_url,
            "source_page_count": self.source_page_count,
            "selected_pages": self.selected_pages,
            "selected_page_geometry": self.selected_page_geometry,
            "check_codes": self.check_codes,
            "result": self.result,
            "blocker_codes": self.blocker_codes,
        }


@dataclass(frozen=True, slots=True)
class PdfPrintValidationReceipt:
    candidate_digest: str
    template_digest: str
    renderer_profile_version: str
    validator_profile_version: str
    font_digest: str
    page_geometry: tuple[tuple[float, float], ...]
    check_codes: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    result: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.result == "print_ready" and self.blocker_codes:
            raise ValueError("print-ready validation cannot contain blockers")
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "candidate_digest": self.candidate_digest,
            "template_digest": self.template_digest,
            "renderer_profile_version": self.renderer_profile_version,
            "validator_profile_version": self.validator_profile_version,
            "font_digest": self.font_digest,
            "page_geometry": self.page_geometry,
            "check_codes": self.check_codes,
            "blocker_codes": self.blocker_codes,
            "result": self.result,
        }


def qualify_official_pdf_form(
    *, source_bytes: bytes, profile: OfficialPdfFormProfile
) -> tuple[bytes, TemplateQualificationReceipt]:
    """Extract an immutable official page subset and qualify its structure."""

    observed = _sha256(source_bytes)
    if observed != profile.source_digest:
        raise ValueError("official_template_source_digest_mismatch")
    reader = PdfReader(io.BytesIO(source_bytes))
    if reader.is_encrypted:
        raise ValueError("official_template_source_encrypted")
    _assert_passive_pdf(reader)
    if max(profile.page_numbers) > len(reader.pages):
        raise ValueError("official_template_page_out_of_range")
    selected = [reader.pages[number - 1] for number in profile.page_numbers]
    extracted = "\n".join((page.extract_text() or "") for page in selected).casefold()
    missing_markers = [
        marker for marker in profile.expected_markers if marker.casefold() not in extracted
    ]
    if missing_markers:
        raise ValueError("official_template_identity_marker_missing:" + ",".join(missing_markers))
    geometry = tuple(
        (round(float(page.mediabox.width), 3), round(float(page.mediabox.height), 3))
        for page in selected
    )
    if any(not (580 <= width <= 610 and 830 <= height <= 860) for width, height in geometry):
        raise ValueError("official_template_page_geometry_not_a4")
    if any(binding.page_index > len(selected) for binding in profile.bindings):
        raise ValueError("official_template_binding_page_out_of_range")
    for binding in profile.bindings:
        page = selected[binding.page_index - 1]
        if (
            binding.x + binding.width > float(page.mediabox.width) + 0.001
            or binding.y + binding.height > float(page.mediabox.height) + 0.001
        ):
            raise ValueError("official_template_binding_box_out_of_page")
    for index, left in enumerate(profile.bindings):
        for right in profile.bindings[index + 1 :]:
            if left.page_index == right.page_index and _boxes_overlap(left, right):
                raise ValueError(
                    f"official_template_binding_boxes_overlap:{left.field_key}:{right.field_key}"
                )
    writer = PdfWriter()
    for page in selected:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "ASD-KONTUR qualified official form source",
            "/Producer": "asd-kontur.official-pdf-form-qualifier@1.0.0",
            "/CreationDate": "D:19800101000000Z",
            "/ModDate": "D:19800101000000Z",
        }
    )
    target = io.BytesIO()
    writer.write(target)
    template_bytes = target.getvalue()
    receipt = TemplateQualificationReceipt(
        profile.fingerprint,
        observed,
        _sha256(template_bytes),
        profile.source_version_ref,
        profile.normative_edition_ref,
        profile.official_url,
        len(reader.pages),
        profile.page_numbers,
        geometry,
        (
            "OFFICIAL_SOURCE_DIGEST_VERIFIED",
            "EXACT_SOURCE_VERSION_PINNED",
            "EXACT_NORMATIVE_EDITION_PINNED",
            "OFFICIAL_FORM_MARKERS_VERIFIED",
            "PAGE_SUBSET_IDENTITY_VERIFIED",
            "A4_GEOMETRY_VERIFIED",
            "PASSIVE_PDF_VERIFIED",
            "BINDING_PLAN_BOUNDED",
            "BINDING_BOXES_NON_OVERLAPPING",
        ),
        "qualified",
        (),
    )
    return template_bytes, receipt


class PdfOverlayRenderer:
    """Stateless renderer for any qualified fixed-page PDF binding plan."""

    def render(
        self,
        *,
        template_bytes: bytes,
        template_digest: str,
        fields: tuple[FieldResolution, ...],
        bindings: tuple[PdfOverlayBinding, ...],
        font_bytes: bytes,
        font_digest: str,
        renderer_profile_version: str,
        validator_profile_version: str,
        semantic_input: dict[str, Any],
    ) -> tuple[TemplateRenderResult, PdfPrintValidationReceipt]:
        if _sha256(template_bytes) != template_digest:
            raise ValueError("template_bytes_digest_mismatch")
        if _sha256(font_bytes) != font_digest:
            raise ValueError("renderer_font_digest_mismatch")
        blocked = sorted(
            item.field_key
            for item in fields
            if item.material
            and item.state not in {ResolutionState.CONFIRMED, ResolutionState.NOT_APPLICABLE}
        )
        if blocked:
            raise ValueError("generation_material_fields_unresolved:" + ",".join(blocked))
        values = {
            item.field_key: (item.display_value or str(item.normalized_value or ""))
            for item in fields
            if item.state is ResolutionState.CONFIRMED
        }
        unresolved_tokens = sorted(
            key for key, value in values.items() if _contains_placeholder(value)
        )
        if unresolved_tokens:
            raise ValueError("template_unresolved_placeholder:" + ",".join(unresolved_tokens))
        binding_keys = {item.field_key for item in bindings}
        unbound = sorted(set(values) - binding_keys)
        required_without_value = sorted(
            binding.field_key
            for binding in bindings
            if binding.required and binding.field_key not in values
        )
        if unbound or required_without_value:
            errors = [
                *(f"binding_missing:{key}" for key in unbound),
                *(f"field_unresolved:{key}" for key in required_without_value),
            ]
            raise ValueError("template_binding_validation_failed:" + ",".join(errors))
        reader = PdfReader(io.BytesIO(template_bytes))
        _assert_passive_pdf(reader)
        font_name = "ASDKonturFont" + font_digest[7:19]
        renderer_font = TTFont(font_name, io.BytesIO(font_bytes))
        pdfmetrics.registerFont(renderer_font)
        overlays: list[bytes] = []
        overflow: list[str] = []
        for page_index, page in enumerate(reader.pages, start=1):
            page_buffer = io.BytesIO()
            page_canvas = canvas.Canvas(
                page_buffer,
                pagesize=(float(page.mediabox.width), float(page.mediabox.height)),
                invariant=1,
                pageCompression=1,
            )
            for binding in (item for item in bindings if item.page_index == page_index):
                if binding.field_key not in values:
                    continue
                lines = _wrap_text(
                    values[binding.field_key], font_name, binding.font_size, binding.width
                )
                if len(lines) * binding.line_height > binding.height + 0.001:
                    overflow.append(binding.field_key)
                    continue
                page_canvas.setFont(font_name, binding.font_size)
                baseline = binding.y + binding.height - binding.font_size
                for line in lines:
                    x = _aligned_x(
                        binding.x,
                        binding.width,
                        line,
                        font_name,
                        binding.font_size,
                        binding.alignment,
                    )
                    page_canvas.drawString(x, baseline, line)
                    baseline -= binding.line_height
            page_canvas.showPage()
            page_canvas.save()
            overlays.append(page_buffer.getvalue())
        if overflow:
            raise ValueError("template_field_overflow:" + ",".join(sorted(overflow)))
        writer = PdfWriter()
        for page, overlay_bytes in zip(reader.pages, overlays, strict=True):
            overlay = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
            writer.add_page(page)
            writer.pages[-1].merge_page(overlay, over=True)
        writer.add_metadata(
            {
                "/Title": "ASD-KONTUR generated document candidate",
                "/Producer": renderer_profile_version,
                "/CreationDate": "D:19800101000000Z",
                "/ModDate": "D:19800101000000Z",
            }
        )
        result_buffer = io.BytesIO()
        writer.write(result_buffer)
        result_bytes = result_buffer.getvalue()
        result_digest = _sha256(result_bytes)
        result_reader = PdfReader(io.BytesIO(result_bytes))
        _assert_passive_pdf(result_reader)
        if len(result_reader.pages) != len(reader.pages):
            raise ValueError("print_validation_page_sequence_changed")
        geometry = tuple(
            (round(float(page.mediabox.width), 3), round(float(page.mediabox.height), 3))
            for page in result_reader.pages
        )
        if geometry != tuple(
            (round(float(page.mediabox.width), 3), round(float(page.mediabox.height), 3))
            for page in reader.pages
        ):
            raise ValueError("print_validation_page_geometry_changed")
        for page_index, (template_page, result_page) in enumerate(
            zip(reader.pages, result_reader.pages, strict=True), start=1
        ):
            template_text = _normalized_pdf_text(template_page.extract_text() or "")
            result_text = _normalized_pdf_text(result_page.extract_text() or "")
            if template_text and template_text not in result_text:
                raise ValueError("print_validation_template_text_changed")
            for binding in (item for item in bindings if item.page_index == page_index):
                value = values.get(binding.field_key)
                if value is None:
                    continue
                for line in _wrap_text(value, font_name, binding.font_size, binding.width):
                    if _normalized_pdf_text(line) not in result_text:
                        raise ValueError(
                            "print_validation_rendered_value_missing:" + binding.field_key
                        )
        expected_font_base = renderer_font.face.name.decode("ascii")
        if not _embedded_renderer_font_present(result_reader, expected_font_base):
            raise ValueError("print_validation_renderer_font_not_embedded")
        checks = (
            "TEMPLATE_DIGEST_VERIFIED",
            "FONT_DIGEST_VERIFIED",
            "FIELD_BINDINGS_COMPLETE",
            "MATERIAL_FIELDS_CONFIRMED",
            "PAGE_GEOMETRY_PRESERVED",
            "PAGE_SEQUENCE_PRESERVED",
            "TEMPLATE_TEXT_PRESERVED",
            "RENDERED_VALUES_TEXT_EXTRACTABLE",
            "RENDERER_FONT_EMBEDDED",
            "UNRESOLVED_PLACEHOLDERS_ABSENT",
            "MULTILINE_LAYOUT_BOUNDED",
            "CLIPPING_OVERFLOW_ABSENT",
            "ACTIVE_CONTENT_ABSENT",
            "EXTERNAL_LINKS_ABSENT",
            "FRESH_DOCUMENT_INSTANCE",
        )
        semantic_fingerprint = digest_of(
            {
                "template_digest": template_digest,
                "renderer_profile": renderer_profile_version,
                "validator_profile": validator_profile_version,
                "font_digest": font_digest,
                "bindings": bindings,
                "fields": fields,
                "semantic_input": semantic_input,
            }
        )
        rendered = TemplateRenderResult(result_bytes, result_digest, semantic_fingerprint, checks)
        validation = PdfPrintValidationReceipt(
            result_digest,
            template_digest,
            renderer_profile_version,
            validator_profile_version,
            font_digest,
            geometry,
            checks,
            (),
            "print_ready",
        )
        return rendered, validation


def load_official_pdf_form_profile(path: Path) -> OfficialPdfFormProfile:
    """Load a versioned data-only profile; renderer code remains form-independent."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return OfficialPdfFormProfile(
        profile_version=str(payload["profile_version"]),
        source_digest=str(payload["source_digest"]),
        source_version_ref=str(payload["source_version_ref"]),
        normative_edition_ref=str(payload["normative_edition_ref"]),
        official_url=str(payload["official_url"]),
        page_numbers=tuple(int(value) for value in payload["page_numbers"]),
        expected_markers=tuple(str(value) for value in payload["expected_markers"]),
        bindings=tuple(PdfOverlayBinding(**value) for value in payload["bindings"]),
        renderer_profile_version=str(payload["renderer_profile_version"]),
        validator_profile_version=str(payload["validator_profile_version"]),
    )


def _assert_passive_pdf(reader: PdfReader) -> None:
    root = reader.root_object
    if "/OpenAction" in root or "/AA" in root:
        raise ValueError("pdf_active_content_forbidden")
    names = root.get("/Names")
    if isinstance(names, DictionaryObject) and any(
        key in names for key in ("/JavaScript", "/EmbeddedFiles")
    ):
        raise ValueError("pdf_active_or_embedded_content_forbidden")
    for page in reader.pages:
        annotations = page.get("/Annots", ArrayObject())
        for annotation_ref in annotations:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A") if isinstance(annotation, DictionaryObject) else None
            if isinstance(action, DictionaryObject) and action.get("/S") == "/URI":
                raise ValueError("pdf_external_link_forbidden")


def _wrap_text(value: str, font_name: str, font_size: float, width: float) -> list[str]:
    result: list[str] = []
    for paragraph in value.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= width:
                current = candidate
            else:
                result.append(current)
                current = word
        result.append(current)
    return result


def _aligned_x(
    x: float,
    width: float,
    line: str,
    font_name: str,
    font_size: float,
    alignment: str,
) -> float:
    if alignment == "left":
        return x
    line_width = float(pdfmetrics.stringWidth(line, font_name, font_size))
    if alignment == "center":
        return x + max(0.0, (width - line_width) / 2)
    return x + max(0.0, width - line_width)


def _boxes_overlap(left: PdfOverlayBinding, right: PdfOverlayBinding) -> bool:
    return not (
        left.x + left.width <= right.x
        or right.x + right.width <= left.x
        or left.y + left.height <= right.y
        or right.y + right.height <= left.y
    )


def _contains_placeholder(value: str) -> bool:
    return bool(re.search(r"\$\{[^}]+\}|\{\{[^}]+\}\}|<<[^>]+>>", value))


def _normalized_pdf_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _embedded_renderer_font_present(reader: PdfReader, expected_base_name: str) -> bool:
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get_object().get("/Font")
        if fonts is None:
            continue
        for font_ref in fonts.get_object().values():
            font = font_ref.get_object()
            base_font = str(font.get("/BaseFont", "")).lstrip("/").split("+", 1)[-1]
            descriptor_ref = font.get("/FontDescriptor")
            if expected_base_name != base_font or descriptor_ref is None:
                continue
            descriptor = descriptor_ref.get_object()
            if any(name in descriptor for name in ("/FontFile", "/FontFile2", "/FontFile3")):
                return True
    return False
