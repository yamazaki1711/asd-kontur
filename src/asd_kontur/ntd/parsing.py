"""Native-first extraction of bounded official NTD artifacts."""

# ruff: noqa: RUF001 -- exact Russian structural labels are intentional.

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import NormativeProvisionCandidate, NormativeProvisionKind

NTD_NATIVE_PDF_PROFILE_VERSION = "ntd_native_pdf_layout_v0.1"
NTD_NATIVE_HTML_PROFILE_VERSION = "ntd_native_html_structure_v0.1"

_STRUCTURAL_PATH = re.compile(
    r"^(?P<path>\d+(?:\.\d+)*)(?:[.)]|\s)|^(?P<appendix>Приложение\s+[А-ЯA-Z0-9]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NativeExtractionResult:
    source_version_id: UUID
    media_type: str
    page_count: int | None
    native_text_characters: int
    candidates: tuple[NormativeProvisionCandidate, ...]
    pages_requiring_ocr: tuple[int, ...]
    extraction_profile_version: str
    extraction_fingerprint: str


class PdfLayoutRunner(Protocol):
    def extract(self, content: bytes) -> bytes: ...


class PopplerPdfLayoutRunner:
    def __init__(self, *, timeout_seconds: float = 180.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Poppler timeout must be positive")
        self._timeout = timeout_seconds

    def extract(self, content: bytes) -> bytes:
        if not content.startswith(b"%PDF-"):
            raise ValueError("ARTIFACT_INVALID_PDF_SIGNATURE")
        with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
            source.write(content)
            source.flush()
            completed = subprocess.run(
                ["pdftotext", "-bbox-layout", "-enc", "UTF-8", source.name, "-"],
                capture_output=True,
                check=False,
                timeout=self._timeout,
            )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise RuntimeError("NATIVE_PDF_EXTRACTION_FAILED")
        return completed.stdout


def extract_native_pdf(
    *,
    content: bytes,
    normative_edition_id: UUID,
    source_version_id: UUID,
    runner: PdfLayoutRunner | None = None,
    minimum_page_characters: int = 20,
) -> NativeExtractionResult:
    if not content.startswith(b"%PDF-"):
        raise ValueError("ARTIFACT_INVALID_PDF_SIGNATURE")
    raw = (runner or PopplerPdfLayoutRunner()).extract(content)
    invalid_control = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    root = ET.fromstring(invalid_control.sub(b"", raw))
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    page_nodes = root.findall(".//x:page", namespace)
    candidates: list[NormativeProvisionCandidate] = []
    pages_requiring_ocr: list[int] = []
    total_characters = 0
    for page_number, page in enumerate(page_nodes, start=1):
        width = float(page.attrib["width"])
        height = float(page.attrib["height"])
        page_characters = 0
        block_ordinal = 0
        for block in page.findall(".//x:block", namespace):
            words = block.findall(".//x:word", namespace)
            text = " ".join(
                (word.text or "").strip() for word in words if (word.text or "").strip()
            )
            if not text:
                continue
            page_characters += len(text)
            total_characters += len(text)
            structural = _STRUCTURAL_PATH.match(text)
            if structural is None:
                continue
            block_ordinal += 1
            structural_path = structural.group("path") or structural.group("appendix")
            kind = _provision_kind(structural_path, text)
            xs0 = [float(word.attrib["xMin"]) for word in words]
            ys0 = [float(word.attrib["yMin"]) for word in words]
            xs1 = [float(word.attrib["xMax"]) for word in words]
            ys1 = [float(word.attrib["yMax"]) for word in words]
            region = (min(xs0) / width, min(ys0) / height, max(xs1) / width, max(ys1) / height)
            content_digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
            candidate_key = (
                f"ntd-provision-candidate:{normative_edition_id}:{source_version_id}:"
                f"{page_number}:{structural_path}:{block_ordinal}:{content_digest}"
            )
            candidates.append(
                NormativeProvisionCandidate(
                    candidate_id=deterministic_uuid(candidate_key),
                    candidate_version=1,
                    normative_edition_id=normative_edition_id,
                    source_version_id=source_version_id,
                    structural_path=structural_path,
                    provision_kind=kind,
                    page_number=page_number,
                    region=region,
                    verbatim_text=text,
                    extraction_method="native_pdf_layout",
                    extraction_profile_version=NTD_NATIVE_PDF_PROFILE_VERSION,
                    content_digest=content_digest,
                    model_provenance=None,
                )
            )
        if page_characters < minimum_page_characters:
            pages_requiring_ocr.append(page_number)
    payload = {
        "profile": NTD_NATIVE_PDF_PROFILE_VERSION,
        "source_version_id": str(source_version_id),
        "page_count": len(page_nodes),
        "candidate_digests": [candidate.content_digest for candidate in candidates],
        "pages_requiring_ocr": pages_requiring_ocr,
    }
    return NativeExtractionResult(
        source_version_id=source_version_id,
        media_type="application/pdf",
        page_count=len(page_nodes),
        native_text_characters=total_characters,
        candidates=tuple(candidates),
        pages_requiring_ocr=tuple(pages_requiring_ocr),
        extraction_profile_version=NTD_NATIVE_PDF_PROFILE_VERSION,
        extraction_fingerprint=digest_of(payload),
    )


def _provision_kind(structural_path: str, text: str) -> NormativeProvisionKind:
    lowered = text.casefold()
    if structural_path.casefold().startswith("приложение"):
        return NormativeProvisionKind.APPENDIX
    if "таблица" in lowered:
        return NormativeProvisionKind.TABLE
    if "форма" in lowered:
        return NormativeProvisionKind.FORM
    if "." not in structural_path:
        return NormativeProvisionKind.SECTION
    if structural_path.count(".") == 1:
        return NormativeProvisionKind.CLAUSE
    return NormativeProvisionKind.SUBCLAUSE
