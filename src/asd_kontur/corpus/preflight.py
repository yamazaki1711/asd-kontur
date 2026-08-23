"""Cheap path-based technical preflight before any OCR/VLM model load."""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from asd_kontur.domain import uuid7

from .models import CorpusScope, PageInspection, PhysicalObjectInspection


def sha256_path(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file incrementally; large containers are never read into one bytes object."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def inspect_pdf(
    path: Path,
    *,
    scope: CorpusScope,
    physical_object_id: UUID,
    physical_object_version: int,
    profile_version: str,
    native_text_sample_pages: Iterable[int] | None = None,
) -> PhysicalObjectInspection:
    """Inspect PDF structure from a file handle and extract text only on requested pages."""
    size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    digest = sha256_path(path)
    errors: list[str] = []
    pages: list[PageInspection] = []
    with path.open("rb") as stream:
        magic = stream.read(5)
    if magic != b"%PDF-":
        return PhysicalObjectInspection(
            scope,
            uuid7(),
            physical_object_id,
            physical_object_version,
            digest,
            size,
            media_type,
            False,
            False,
            0,
            (),
            0,
            0,
            profile_version,
            datetime.now(UTC),
            ("MIME_MAGIC_MISMATCH",),
        )
    try:
        reader = PdfReader(path, strict=True)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            raise PdfInspectionBlocked("PDF_ENCRYPTED")
        page_count = len(reader.pages)
        samples = set(native_text_sample_pages or range(1, page_count + 1))
        for index, page in enumerate(reader.pages, start=1):
            box = page.mediabox
            text_chars = len(page.extract_text() or "") if index in samples else 0
            resources = page.get("/Resources", {})
            xobjects = resources.get("/XObject", {}) if hasattr(resources, "get") else {}
            raster_objects = len(xobjects) if hasattr(xobjects, "__len__") else 0
            if float(box.width) > 20_000 or float(box.height) > 20_000:
                errors.append(f"ANOMALOUS_PAGE_DIMENSIONS:{index}")
            pages.append(
                PageInspection(
                    index,
                    float(box.width),
                    float(box.height),
                    int(page.get("/Rotate", 0) or 0),
                    text_chars,
                    raster_objects,
                )
            )
        readable = True
        root = reader.trailer.get("/Root", {})
        names = root.get("/Names", {}) if hasattr(root, "get") else {}
        attachments = int(bool(names.get("/EmbeddedFiles"))) if hasattr(names, "get") else 0
        form = root.get("/AcroForm", {}) if hasattr(root, "get") else {}
        fields = form.get("/Fields", ()) if hasattr(form, "get") else ()
        signatures = sum(
            bool(hasattr(field, "get") and field.get("/FT") == "/Sig") for field in fields
        )
    except PdfInspectionBlocked as error:
        encrypted = True
        page_count = 0
        readable = False
        attachments = 0
        signatures = 0
        errors.append(error.code)
    except (OSError, PyPdfError, KeyError, TypeError, ValueError) as error:
        encrypted = False
        page_count = 0
        readable = False
        attachments = 0
        signatures = 0
        errors.append(type(error).__name__)
    return PhysicalObjectInspection(
        scope,
        uuid7(),
        physical_object_id,
        physical_object_version,
        digest,
        size,
        media_type,
        encrypted,
        readable,
        page_count,
        tuple(pages),
        attachments,
        signatures,
        profile_version,
        datetime.now(UTC),
        tuple(errors),
    )


class PdfInspectionBlocked(Exception):
    """Typed non-provider preflight blocker."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
