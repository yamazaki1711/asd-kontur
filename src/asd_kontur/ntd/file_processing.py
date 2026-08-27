"""Source-first processing of admitted official normative artifacts.

This module reuses the industrial Document Understanding native representation.
It does not own source bytes, publish knowledge, or call an external model.
"""

# ruff: noqa: RUF001 -- exact Russian normative tokens are intentional.

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from asd_kontur.document_understanding.models import LayoutElement, PageHealthKind
from asd_kontur.document_understanding.native import NativeDocument, inspect_pdf_path
from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

NTD_ARTIFACT_VALIDATION_VERSION = "ntd-artifact-validation-v0.2"
NTD_STRUCTURE_PROFILE_VERSION = "ntd-structural-reconstruction-v0.1"
NTD_PROVISION_PROFILE_VERSION = "ntd-provision-candidate-v0.1"
NTD_RENDER_PROFILE_VERSION = "poppler-pdftoppm-png-144dpi-v0.1"
NTD_REPRESENTATION_INVENTORY_VERSION = "ntd-representation-inventory-v0.3"

_STRUCTURAL_NUMBER = re.compile(
    r"^(?:(?:раздел|подраздел|пункт)\s+)?(?P<number>\d+(?:\.\d+)+|\d+)[.)]?(?:\s+(?P<text>.*))?$",
    re.IGNORECASE,
)
_APPENDIX = re.compile(r"^приложение\s+(?P<number>[А-ЯA-Z0-9]+)(?P<text>.*)$", re.IGNORECASE)
_TABLE = re.compile(r"^таблица\s+(?P<number>[А-ЯA-Z0-9.\-]+)(?P<text>.*)$", re.IGNORECASE)
_FORMULA = re.compile(r"(?:=|≤|≥|±|∑|√|\bгде\b)")
_TOC_LEADER = re.compile(r"(?:\.{5,}|…{3,})")
_EDITION_METADATA = re.compile(
    r"^\d+\s+(?:ИСПОЛНИТЕЛЬ|ВНЕСЕН|ПОДГОТОВЛЕН|УТВЕРЖДЕН|ЗАРЕГИСТРИРОВАН|ВВЕДЕН)\b"
)
_MODAL_OR_NEGATION_TOKEN = re.compile(
    r"\b(?:не\s+допускается|запрещается|запрещено|должен|должна|должно|должны|"
    r"следует|допускается|не)\b",
    re.IGNORECASE,
)
_NUMERIC_OR_SIGN_TOKEN = re.compile(r"(?<![\w])(?:[+\-]?\d+(?:[.,]\d+)*|≤|≥|±|%|‰)(?![\w])")
_UNIT_TOKEN = re.compile(r"(?<![\w])(?:м²|м³|мм|см|кг|м|т)(?![\w])", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ArtifactValidation:
    detected_media_type: str
    byte_length: int
    content_digest: str
    representation_version: str | None
    encryption_status: str
    signature_status: str
    page_count: int
    embedded_file_count: int
    active_content_status: str
    title_identity_status: str
    validation_status: str
    observations: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RepresentationPage:
    page_id: UUID
    page_index: int
    printed_page_label: str | None
    kind: str
    width_points: Decimal
    height_points: Decimal
    rotation_degrees: int
    native_text_character_count: int
    native_text_coverage: Decimal
    render_digest: str | None
    extraction_route: str
    terminal_outcome: str
    inventory_profile_version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class StructuralFragment:
    structural_id: UUID
    structural_path: str
    unit_type: str
    parent_path: str | None
    ordinal: int
    exact_heading: str | None
    exact_number: str | None
    raw_text: str
    normalized_search_text: str
    locators: tuple[LayoutElement, ...]
    extraction_method: str
    fragment_digest: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ProvisionSemantics:
    modality: str
    subject: dict[str, Any]
    predicate: dict[str, Any]
    object_value: dict[str, Any]
    conditions: tuple[str, ...]
    exclusions: tuple[str, ...]
    applicability: dict[str, Any]
    units_dimensions: tuple[str, ...]
    referenced_designations: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    critical_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderedNormativePage:
    page_index: int
    width_pixels: int
    height_pixels: int
    source_rotation_degrees: int
    source_to_render: tuple[Decimal, ...]
    render_to_source: tuple[Decimal, ...]
    render_digest: str
    renderer_profile_version: str
    png_bytes: bytes = dataclass_field(repr=False, compare=False)


def render_normative_pdf_page(
    path: Path, *, page_index: int, source_rotation_degrees: int
) -> RenderedNormativePage:
    """Render one admitted page with an explicit reversible coordinate transform."""

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("NTD_RENDER_SOURCE_PATH_INVALID")
    if page_index < 1 or source_rotation_degrees not in {0, 90, 180, 270}:
        raise ValueError("NTD_RENDER_PAGE_ARGUMENT_INVALID")
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise ValueError("NTD_RENDERER_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="asd-ntd-render-") as directory:
        prefix = Path(directory) / "page"
        completed = subprocess.run(
            [
                renderer,
                "-f",
                str(page_index),
                "-l",
                str(page_index),
                "-singlefile",
                "-png",
                "-r",
                "144",
                str(path),
                str(prefix),
            ],
            check=False,
            capture_output=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise ValueError("NTD_RENDER_FAILED")
        output = prefix.with_suffix(".png")
        if not output.is_file():
            raise ValueError("NTD_RENDER_OUTPUT_MISSING")
        png = output.read_bytes()
    width, height = _strict_png_dimensions(png)
    source_to_render, render_to_source = _rotation_transforms(source_rotation_degrees)
    return RenderedNormativePage(
        page_index,
        width,
        height,
        source_rotation_degrees,
        source_to_render,
        render_to_source,
        "sha256:" + hashlib.sha256(png).hexdigest(),
        NTD_RENDER_PROFILE_VERSION,
        png,
    )


def render_normative_pdf_region(
    path: Path,
    *,
    page_index: int,
    source_rotation_degrees: int,
    source_width_points: Decimal,
    source_height_points: Decimal,
    source_region: tuple[Decimal, Decimal, Decimal, Decimal],
) -> RenderedNormativePage:
    """Render one normalized region without promoting it to a full-page representation."""

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("NTD_RENDER_SOURCE_PATH_INVALID")
    if page_index < 1 or source_rotation_degrees not in {0, 90, 180, 270}:
        raise ValueError("NTD_RENDER_PAGE_ARGUMENT_INVALID")
    x0, y0, x1, y1 = source_region
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("NTD_RENDER_SOURCE_REGION_INVALID")
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise ValueError("NTD_RENDERER_UNAVAILABLE")
    scale = Decimal("2")
    if source_rotation_degrees in {90, 270}:
        render_width_points = source_height_points
        render_height_points = source_width_points
    else:
        render_width_points = source_width_points
        render_height_points = source_height_points
    full_width = max(1, int((render_width_points * scale).to_integral_value()))
    full_height = max(1, int((render_height_points * scale).to_integral_value()))
    left = max(0, int((Decimal(full_width) * x0).to_integral_value()))
    top = max(0, int((Decimal(full_height) * y0).to_integral_value()))
    right = min(full_width, int((Decimal(full_width) * x1).to_integral_value()))
    bottom = min(full_height, int((Decimal(full_height) * y1).to_integral_value()))
    width = right - left
    height = bottom - top
    if width < 2 or height < 2:
        raise ValueError("NTD_RENDER_SOURCE_REGION_TOO_SMALL")
    with tempfile.TemporaryDirectory(prefix="asd-ntd-region-render-") as directory:
        prefix = Path(directory) / "region"
        completed = subprocess.run(
            [
                renderer,
                "-f",
                str(page_index),
                "-l",
                str(page_index),
                "-singlefile",
                "-png",
                "-r",
                "144",
                "-x",
                str(left),
                "-y",
                str(top),
                "-W",
                str(width),
                "-H",
                str(height),
                str(path),
                str(prefix),
            ],
            check=False,
            capture_output=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise ValueError("NTD_REGION_RENDER_FAILED")
        output = prefix.with_suffix(".png")
        if not output.is_file():
            raise ValueError("NTD_REGION_RENDER_OUTPUT_MISSING")
        png = output.read_bytes()
    actual_width, actual_height = _strict_png_dimensions(png)
    source_to_page_render, page_render_to_source = _rotation_transforms(source_rotation_degrees)
    page_render_to_crop, crop_to_page_render = _region_transforms(source_region)
    source_to_render = _matrix_multiply(page_render_to_crop, source_to_page_render)
    render_to_source = _matrix_multiply(page_render_to_source, crop_to_page_render)
    return RenderedNormativePage(
        page_index,
        actual_width,
        actual_height,
        source_rotation_degrees,
        source_to_render,
        render_to_source,
        "sha256:" + hashlib.sha256(png).hexdigest(),
        "poppler-pdftoppm-png-144dpi-region-v0.1",
        png,
    )


def _region_transforms(
    source_region: tuple[Decimal, Decimal, Decimal, Decimal],
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    x0, y0, x1, y1 = source_region
    width = x1 - x0
    height = y1 - y0
    return (
        (
            Decimal(1) / width,
            Decimal(0),
            -x0 / width,
            Decimal(0),
            Decimal(1) / height,
            -y0 / height,
            Decimal(0),
            Decimal(0),
            Decimal(1),
        ),
        (
            width,
            Decimal(0),
            x0,
            Decimal(0),
            height,
            y0,
            Decimal(0),
            Decimal(0),
            Decimal(1),
        ),
    )


def _matrix_multiply(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    if len(left) != 9 or len(right) != 9:
        raise ValueError("NTD_RENDER_TRANSFORM_INVALID")
    return tuple(
        sum(
            (left[row * 3 + index] * right[index * 3 + column] for index in range(3)),
            Decimal(0),
        )
        for row in range(3)
        for column in range(3)
    )


def validate_official_pdf(path: Path, *, expected_designation: str) -> ArtifactValidation:
    """Validate exact PDF bytes without rewriting or repairing them."""

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("NTD_ARTIFACT_PATH_INVALID")
    digest = hashlib.sha256()
    byte_length = 0
    header = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if not header:
                header = chunk[:1024]
            digest.update(chunk)
            byte_length += len(chunk)
    if not header.startswith(b"%PDF-"):
        raise ValueError("NTD_ARTIFACT_PDF_SIGNATURE_INVALID")
    version_match = re.match(rb"%PDF-(\d+\.\d+)", header)
    representation_version = version_match.group(1).decode() if version_match else None
    observations: list[str] = []
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream, strict=True)
            encryption_status = "encrypted" if reader.is_encrypted else "not_encrypted"
            if reader.is_encrypted:
                try:
                    if reader.decrypt("") == 0:
                        return _blocked_validation(
                            byte_length,
                            digest.hexdigest(),
                            representation_version,
                            "encrypted_password_required",
                            "unknown",
                            "unknown",
                            "title_unverified",
                            ("PDF_PASSWORD_REQUIRED",),
                        )
                except FileNotDecryptedError:
                    return _blocked_validation(
                        byte_length,
                        digest.hexdigest(),
                        representation_version,
                        "encrypted_password_required",
                        "unknown",
                        "unknown",
                        "title_unverified",
                        ("PDF_PASSWORD_REQUIRED",),
                    )
            page_count = len(reader.pages)
            if page_count < 1 or page_count > 5_000:
                raise ValueError("NTD_ARTIFACT_PAGE_DENOMINATOR_INVALID")
            root = reader.trailer.get("/Root")
            root_object = root.get_object() if root is not None else {}
            active_keys = tuple(
                key for key in ("/OpenAction", "/AA", "/JavaScript") if key in root_object
            )
            names = _resolved_mapping(root_object.get("/Names"))
            embedded_file_count = _embedded_file_count(names)
            if "/JavaScript" in names:
                active_keys += ("/Names/JavaScript",)
            active_content_status = "absent" if not active_keys else "present_quarantined"
            signature_status = _signature_status(reader)
            title_zone_text = "\n".join(
                (reader.pages[index].extract_text() or "").strip()
                for index in range(min(8, page_count))
            )
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("NTD_ARTIFACT_PDF_STRUCTURE_INVALID") from exc
    title_key = _identity_text_key(title_zone_text[:100_000])
    title_identity_status = (
        "native_confirmed"
        if _designation_confirmed(expected_designation, title_key)
        else "native_text_missing"
        if not title_key
        else "native_not_confirmed"
    )
    if active_keys:
        observations.extend(f"ACTIVE_CONTENT:{key}" for key in active_keys)
    if embedded_file_count:
        observations.append(f"EMBEDDED_FILES:{embedded_file_count}")
    if title_identity_status != "native_confirmed":
        observations.append(f"TITLE_IDENTITY:{title_identity_status}")
    validation_status = "quarantined" if active_keys else "supported"
    content_digest = f"sha256:{digest.hexdigest()}"
    payload = {
        "schema": NTD_ARTIFACT_VALIDATION_VERSION,
        "content_digest": content_digest,
        "byte_length": byte_length,
        "representation_version": representation_version,
        "encryption_status": encryption_status,
        "signature_status": signature_status,
        "page_count": page_count,
        "embedded_file_count": embedded_file_count,
        "active_content_status": active_content_status,
        "title_identity_status": title_identity_status,
        "validation_status": validation_status,
        "observations": observations,
    }
    return ArtifactValidation(
        "application/pdf",
        byte_length,
        content_digest,
        representation_version,
        encryption_status,
        signature_status,
        page_count,
        embedded_file_count,
        active_content_status,
        title_identity_status,
        validation_status,
        tuple(observations),
        digest_of(payload),
    )


def extract_shared_native_document(
    path: Path,
    *,
    document_id: UUID,
    source_version_id: UUID,
) -> NativeDocument:
    """Use the same native-first extractor as workspace Document Understanding."""

    return inspect_pdf_path(
        path=path,
        document_id=document_id,
        document_version=1,
        source_version_id=source_version_id,
    )


def inventory_pages(
    document: NativeDocument, *, normative_artifact_id: UUID
) -> tuple[RepresentationPage, ...]:
    pages: list[RepresentationPage] = []
    for page in document.pages:
        text_count = sum(len(element.raw_text) for element in page.elements)
        area = max(Decimal("1"), page.width_points * page.height_points)
        coverage = min(Decimal("1"), Decimal(text_count) / (area / Decimal("40")))
        kind = _representation_kind(page.health.primary_kind)
        route = (
            "native"
            if page.health.route.value == "not_required"
            else "polza_candidate"
            if kind in {"raster", "mixed", "damaged_native", "rotated", "vector"}
            else "blocked"
        )
        outcome = "native_complete" if route == "native" else "failed"
        page_id = deterministic_uuid(f"ntd-page:{normative_artifact_id}:{page.page_number}")
        payload = {
            "schema": NTD_REPRESENTATION_INVENTORY_VERSION,
            "page_id": page_id,
            "page_index": page.page_number,
            "kind": kind,
            "width": page.width_points,
            "height": page.height_points,
            "rotation": page.rotation_degrees,
            "native_text_characters": text_count,
            "native_text_coverage": coverage,
            "route": route,
            "terminal_outcome": outcome,
            "health_fingerprint": page.health.fingerprint,
        }
        pages.append(
            RepresentationPage(
                page_id,
                page.page_number,
                None,
                kind,
                page.width_points,
                page.height_points,
                page.rotation_degrees,
                text_count,
                coverage,
                None,
                route,
                outcome,
                NTD_REPRESENTATION_INVENTORY_VERSION,
                digest_of(payload),
            )
        )
    return tuple(pages)


def reconstruct_native_structure(
    document: NativeDocument, *, normative_edition_id: UUID
) -> tuple[StructuralFragment, ...]:
    """Reconstruct numbered source structures; continuation lines retain all locators."""

    recurring_marginal_keys = _recurring_marginal_element_keys(document)
    table_of_contents_pages = _table_of_contents_pages(document)
    builders: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    context_prefix = ""
    ordinal = 0
    preamble_ordinal = 0
    used_paths: dict[str, int] = {}
    for page in document.pages:
        if page.page_number in table_of_contents_pages:
            continue
        for element in sorted(page.elements, key=lambda value: value.reading_order):
            raw = " ".join(element.raw_text.split())
            if not raw:
                continue
            marginal_key = _marginal_element_key(element)
            if marginal_key in recurring_marginal_keys or _is_marginal_page_number(element):
                continue
            match = _APPENDIX.match(raw)
            unit_type = "appendix"
            exact_number: str | None = None
            exact_heading: str | None = None
            if match is not None:
                exact_number = match.group("number")
                context_prefix = f"appendix:{exact_number}"
                structural_path = context_prefix
                exact_heading = raw
            else:
                match = _TABLE.match(raw)
                unit_type = "table"
                if match is not None:
                    exact_number = match.group("number")
                    structural_path = (
                        f"{context_prefix + '/' if context_prefix else ''}table:{exact_number}"
                    )
                    exact_heading = raw
                else:
                    match = _STRUCTURAL_NUMBER.match(raw)
                    unit_type = "other"
                    if match is not None:
                        exact_number = match.group("number")
                        structural_path = (
                            f"{context_prefix + '/' if context_prefix else ''}{exact_number}"
                        )
                        unit_type = (
                            "edition_metadata"
                            if _EDITION_METADATA.match(raw)
                            else _unit_type(exact_number, context_prefix=context_prefix)
                        )
                        exact_heading = raw if unit_type in {"section", "subsection"} else None
                    else:
                        if current is not None:
                            current["texts"].append(raw)
                            current["locators"].append(element)
                            continue
                        preamble_ordinal += 1
                        structural_path = f"preamble:{preamble_ordinal}"
            duplicate = used_paths.get(structural_path, 0)
            used_paths[structural_path] = duplicate + 1
            if duplicate:
                structural_path = f"{structural_path}@occurrence:{duplicate + 1}"
            ordinal += 1
            parent_path = _parent_path(structural_path)
            current = {
                "path": structural_path,
                "unit_type": unit_type,
                "parent_path": parent_path,
                "ordinal": ordinal,
                "exact_heading": exact_heading,
                "exact_number": exact_number,
                "texts": [raw],
                "locators": [element],
            }
            builders.append(current)
    fragments: list[StructuralFragment] = []
    for builder in builders:
        raw_text = "\n".join(builder["texts"])
        normalized = _search_text(raw_text)
        fragment_digest = f"sha256:{hashlib.sha256(raw_text.encode()).hexdigest()}"
        structural_id = deterministic_uuid(
            f"ntd-structural:{normative_edition_id}:{builder['path']}:{fragment_digest}"
        )
        payload = {
            "schema": NTD_STRUCTURE_PROFILE_VERSION,
            "structural_id": structural_id,
            "path": builder["path"],
            "unit_type": builder["unit_type"],
            "parent_path": builder["parent_path"],
            "ordinal": builder["ordinal"],
            "fragment_digest": fragment_digest,
            "locator_digests": [item.locator.evidence_digest for item in builder["locators"]],
        }
        fragments.append(
            StructuralFragment(
                structural_id,
                builder["path"],
                builder["unit_type"],
                builder["parent_path"],
                builder["ordinal"],
                builder["exact_heading"],
                builder["exact_number"],
                raw_text,
                normalized,
                tuple(builder["locators"]),
                "native_pdf_layout",
                fragment_digest,
                digest_of(payload),
            )
        )
    return tuple(fragments)


def _recurring_marginal_element_keys(document: NativeDocument) -> frozenset[str]:
    pages_by_key: dict[str, set[int]] = {}
    for page in document.pages:
        for element in page.elements:
            key = _marginal_element_key(element)
            if key is not None:
                pages_by_key.setdefault(key, set()).add(page.page_number)
    return frozenset(key for key, pages in pages_by_key.items() if len(pages) >= 3)


def _table_of_contents_pages(document: NativeDocument) -> frozenset[int]:
    result: set[int] = set()
    previous_was_contents = False
    for page in document.pages:
        values = tuple(element.raw_text.strip() for element in page.elements)
        leader_count = sum(_TOC_LEADER.search(value) is not None for value in values)
        explicitly_contents = any(_search_text(value) == "содержание" for value in values)
        if explicitly_contents or leader_count >= 2 or (previous_was_contents and leader_count):
            result.add(page.page_number)
            previous_was_contents = True
        else:
            previous_was_contents = False
    return frozenset(result)


def _marginal_element_key(element: LayoutElement) -> str | None:
    top, bottom = element.locator.region[1], element.locator.region[3]
    if top > 0.09 and bottom < 0.91:
        return None
    normalized = _search_text(element.raw_text)
    return normalized if normalized else None


def _is_marginal_page_number(element: LayoutElement) -> bool:
    top, bottom = element.locator.region[1], element.locator.region[3]
    return (top <= 0.09 or bottom >= 0.91) and re.fullmatch(
        r"(?:[ivxlcdm]+|\d+)", element.raw_text.strip(), re.IGNORECASE
    ) is not None


def derive_provision_semantics(fragment: StructuralFragment) -> ProvisionSemantics:
    """Classify exact source modality without rewriting its proposition."""

    lowered = fragment.raw_text.casefold()
    if re.search(r"\b(?:не допускается|запрещается|запрещено)\b", lowered):
        modality = "prohibition"
    elif re.search(r"\b(?:должен|должна|должно|должны|подлежит|требуется)\b", lowered):
        modality = "mandatory"
    elif re.search(r"\bдопускается\b", lowered):
        modality = "permission"
    elif re.search(r"\bследует\b", lowered):
        modality = "recommendation"
    elif re.search(r"\bозначает\b|\bопределение\b", lowered):
        modality = "definition"
    elif fragment.unit_type == "formula" or _FORMULA.search(fragment.raw_text):
        modality = "formula"
    else:
        modality = "reference"
    conditions = tuple(
        match.group(0)
        for match in re.finditer(
            r"(?i)\b(?:если|при условии|в случае|для)\b[^.;]{0,240}", fragment.raw_text
        )
    )
    exclusions = tuple(
        match.group(0)
        for match in re.finditer(r"(?i)\b(?:за исключением|кроме)\b[^.;]{0,240}", fragment.raw_text)
    )
    units = tuple(dict.fromkeys(re.findall(r"(?i)(?:мм|см|м²|м³|м|кг|т|%|‰)", fragment.raw_text)))
    referenced = tuple(
        dict.fromkeys(
            re.findall(
                r"(?i)(?:СП\s+\d+(?:[.\-]\d+)+|ГОСТ(?:\s+Р)?\s+\d+(?:\.\d+)*(?:-\d{4})?)",
                fragment.raw_text,
            )
        )
    )
    critical = extract_critical_tokens(fragment.raw_text)
    uncertainty = () if modality != "reference" else ("SEMANTIC_MODALITY_NOT_DETERMINISTIC",)
    return ProvisionSemantics(
        modality,
        {"raw_scope": None},
        {"raw_modality": modality},
        {"verbatim_digest": fragment.fragment_digest},
        conditions,
        exclusions,
        {"status": "unresolved" if conditions else "general_candidate"},
        units,
        referenced,
        uncertainty,
        critical,
    )


def extract_critical_tokens(text: str) -> tuple[str, ...]:
    """Return evidence-critical tokens without matching unit letters inside words.

    Ordering follows the source text.  Units are matched longest-first and only as
    standalone tokens, so Cyrillic ``т``/``м`` in ordinary words cannot silently
    become numeric evidence.
    """

    matches = [
        *(_token_match(match, "modal") for match in _MODAL_OR_NEGATION_TOKEN.finditer(text)),
        *(_token_match(match, "numeric") for match in _NUMERIC_OR_SIGN_TOKEN.finditer(text)),
        *(_token_match(match, "unit") for match in _UNIT_TOKEN.finditer(text)),
    ]
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return tuple(item[2] for item in matches)


def _token_match(match: re.Match[str], token_class: str) -> tuple[int, str, str]:
    return match.start(), token_class, match.group(0)


def _blocked_validation(
    byte_length: int,
    hexdigest: str,
    representation_version: str | None,
    encryption_status: str,
    signature_status: str,
    active_content_status: str,
    title_identity_status: str,
    observations: tuple[str, ...],
) -> ArtifactValidation:
    content_digest = f"sha256:{hexdigest}"
    payload = {
        "schema": NTD_ARTIFACT_VALIDATION_VERSION,
        "content_digest": content_digest,
        "byte_length": byte_length,
        "representation_version": representation_version,
        "encryption_status": encryption_status,
        "signature_status": signature_status,
        "page_count": 0,
        "embedded_file_count": 0,
        "active_content_status": active_content_status,
        "title_identity_status": title_identity_status,
        "validation_status": "quarantined",
        "observations": observations,
    }
    return ArtifactValidation(
        "application/pdf",
        byte_length,
        content_digest,
        representation_version,
        encryption_status,
        signature_status,
        0,
        0,
        active_content_status,
        title_identity_status,
        "quarantined",
        observations,
        digest_of(payload),
    )


def _resolved_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    resolved = value.get_object() if hasattr(value, "get_object") else value
    return dict(resolved) if isinstance(resolved, dict) else {}


def _embedded_file_count(names: dict[str, Any]) -> int:
    embedded = _resolved_mapping(names.get("/EmbeddedFiles"))
    values = embedded.get("/Names", ())
    try:
        return len(values) // 2
    except TypeError:
        return 0


def _signature_status(reader: PdfReader) -> str:
    root = reader.trailer.get("/Root")
    root_object = root.get_object() if root is not None else {}
    form = _resolved_mapping(root_object.get("/AcroForm"))
    for field in form.get("/Fields", ()):
        resolved = field.get_object() if hasattr(field, "get_object") else field
        if isinstance(resolved, dict) and str(resolved.get("/FT")) == "/Sig":
            return "signature_field_present_unverified"
    return "absent"


def _identity_text_key(value: str) -> str:
    return re.sub(r"[^0-9a-zа-я]+", "", value.casefold().replace("ё", "е"))


def _designation_confirmed(expected_designation: str, source_key: str) -> bool:
    expected = expected_designation.casefold()
    order = re.search(r"№\s*(\d+)\s*/\s*пр\s+от\s+(\d{2}\.\d{2}\.\d{4})", expected)
    if order is not None:
        number, issued = order.groups()
        return f"{number}пр" in source_key and issued.replace(".", "") in source_key
    designation = re.search(
        r"(?:сп|гост(?:\s+р)?)\s+([0-9]+(?:[.\-][0-9]+)+)", expected, re.IGNORECASE
    )
    if designation is not None:
        number = re.sub(r"[^0-9]", "", designation.group(1))
        return number in source_key
    return _identity_text_key(expected_designation) in source_key


def _representation_kind(kind: PageHealthKind) -> str:
    return {
        PageHealthKind.BORN_DIGITAL: "native_text",
        PageHealthKind.RASTER_ONLY: "raster",
        PageHealthKind.MIXED: "mixed",
        PageHealthKind.EXISTING_OCR: "existing_ocr",
        PageHealthKind.DAMAGED_ENCODING: "damaged_native",
        PageHealthKind.TABLE_HEAVY: "table_heavy",
        # The external pass recovers only printed normative text/labels from vector pages;
        # it does not promote drawing geometry to CAD authority.
        PageHealthKind.DRAWING: "vector",
        PageHealthKind.BLANK: "blank",
        PageHealthKind.PASSWORD_PROTECTED: "unsupported",
        PageHealthKind.RENDER_FAILURE: "render_failure",
    }[kind]


def _unit_type(number: str, *, context_prefix: str) -> str:
    if number.count(".") == 0:
        return "clause" if context_prefix else "section"
    if number.count(".") == 1:
        return "clause"
    return "subclause"


def _parent_path(path: str) -> str | None:
    if "/" in path:
        prefix, leaf = path.rsplit("/", 1)
        if re.fullmatch(r"\d+(?:\.\d+)+", leaf):
            parent_number = leaf.rsplit(".", 1)[0]
            return f"{prefix}/{parent_number}"
        return prefix
    if re.fullmatch(r"\d+(?:\.\d+)+", path):
        return path.rsplit(".", 1)[0]
    return None


def _search_text(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _strict_png_dimensions(value: bytes) -> tuple[int, int]:
    if (
        len(value) < 45
        or value[:8] != b"\x89PNG\r\n\x1a\n"
        or value[12:16] != b"IHDR"
        or value[-8:-4] != b"IEND"
    ):
        raise ValueError("NTD_RENDER_PNG_INVALID")
    width = int.from_bytes(value[16:20], "big")
    height = int.from_bytes(value[20:24], "big")
    if width < 1 or height < 1 or width * height > 100_000_000:
        raise ValueError("NTD_RENDER_PNG_DIMENSIONS_INVALID")
    return width, height


def _rotation_transforms(
    rotation_degrees: int,
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    zero, one, negative_one = Decimal("0"), Decimal("1"), Decimal("-1")
    matrices = {
        0: (
            (one, zero, zero, zero, one, zero, zero, zero, one),
            (one, zero, zero, zero, one, zero, zero, zero, one),
        ),
        90: (
            (zero, negative_one, one, one, zero, zero, zero, zero, one),
            (zero, one, zero, negative_one, zero, one, zero, zero, one),
        ),
        180: (
            (negative_one, zero, one, zero, negative_one, one, zero, zero, one),
            (negative_one, zero, one, zero, negative_one, one, zero, zero, one),
        ),
        270: (
            (zero, one, zero, negative_one, zero, one, zero, zero, one),
            (zero, negative_one, one, one, zero, zero, zero, zero, one),
        ),
    }
    try:
        return matrices[rotation_degrees]
    except KeyError as exc:
        raise ValueError("NTD_RENDER_ROTATION_INVALID") from exc
