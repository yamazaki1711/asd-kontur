"""Native-first, streaming PDF inspection for methodological guides."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pypdf import PdfReader
from pypdf.generic import DictionaryObject, IndirectObject

from .models import GuideContentKind, GuidePageManifest


@dataclass(frozen=True, slots=True)
class GuidePdfInspection:
    path: Path
    content_digest: str
    size_bytes: int
    media_type: str
    encrypted: bool
    page_count: int
    pages: tuple[GuidePageManifest, ...]

    def __post_init__(self) -> None:
        if self.page_count != len(self.pages):
            raise ValueError("PageManifest must cover every source page")
        if tuple(page.page_number for page in self.pages) != tuple(range(1, self.page_count + 1)):
            raise ValueError("PageManifest must be ordered and one-based")


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _resolved(value: object) -> object:
    return value.get_object() if isinstance(value, IndirectObject) else value


def _image_count(resources: object) -> int:
    resolved = _resolved(resources)
    if not isinstance(resolved, DictionaryObject):
        return 0
    xobjects = _resolved(resolved.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return 0
    count = 0
    for candidate in xobjects.values():
        item = _resolved(candidate)
        if not isinstance(item, DictionaryObject):
            continue
        subtype = str(item.get("/Subtype", ""))
        if subtype == "/Image":
            count += 1
        elif subtype == "/Form":
            count += _image_count(item.get("/Resources"))
    return count


def _update_xobject_digest(digest: Any, resources: object) -> None:
    resolved = _resolved(resources)
    if not isinstance(resolved, DictionaryObject):
        return
    xobjects = _resolved(resolved.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return
    for name, candidate in sorted(xobjects.items(), key=lambda item: str(item[0])):
        item = _resolved(candidate)
        if not isinstance(item, DictionaryObject):
            continue
        digest.update(str(name).encode())
        digest.update(str(item.get("/Subtype", "")).encode())
        raw_data = getattr(item, "_data", None)
        if isinstance(raw_data, bytes):
            digest.update(raw_data)
        else:
            get_data = getattr(item, "get_data", None)
            if callable(get_data):
                try:
                    digest.update(bytes(get_data()))
                except (AttributeError, TypeError, ValueError):
                    digest.update(b"unreadable-xobject")
        if str(item.get("/Subtype", "")) == "/Form":
            _update_xobject_digest(digest, item.get("/Resources"))


def _page_digest(page: object, page_number: int, native_text: str) -> str:
    digest = hashlib.sha256()
    digest.update(f"page:{page_number}\n{native_text}".encode())
    mediabox = getattr(page, "mediabox", None)
    digest.update(str(mediabox).encode())
    get_method = getattr(page, "get", None)
    if callable(get_method):
        digest.update(str(get_method("/Rotate", 0) or 0).encode())
    get_contents = getattr(page, "get_contents", None)
    if callable(get_contents):
        contents = get_contents()
        if contents is not None:
            try:
                digest.update(bytes(contents.get_data()))
            except (AttributeError, TypeError, ValueError):
                digest.update(b"unreadable-content-stream")
    if callable(get_method):
        _update_xobject_digest(digest, get_method("/Resources"))
    return f"sha256:{digest.hexdigest()}"


def _content_kind(native_characters: int, images: int) -> GuideContentKind:
    if native_characters and images:
        return GuideContentKind.MIXED
    if native_characters:
        return GuideContentKind.NATIVE_TEXT
    if images:
        return GuideContentKind.RASTER_IMAGE
    return GuideContentKind.BLANK_OR_TECHNICAL


def _technical_flags(
    *, native_text: str, images: int, width: float, height: float, rotation: int
) -> tuple[str, ...]:
    flags: list[str] = []
    if images:
        flags.append("contains_images")
    if "\t" in native_text or native_text.count("|") >= 3:
        flags.append("possible_table")
    normalized = native_text.casefold()
    if any(marker in normalized for marker in ("пример заполнения", "образец", "форма ")):
        flags.append("possible_form_or_template_example")
    if any(marker in normalized for marker in ("схема", "диаграм", "рисунок", "рис. ")):
        flags.append("possible_diagram")
    if len(native_text.strip()) < 24:
        flags.append("native_text_insufficient")
    if width > height:
        flags.append("landscape_page")
    if rotation % 360:
        flags.append("rotated_page")
    return tuple(flags)


def iter_page_manifest(pdf_path: Path, source_version_id: UUID) -> Iterator[GuidePageManifest]:
    reader = PdfReader(str(pdf_path), strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted practice guides require an explicit decryption authority")
    total = len(reader.pages)
    for index, page in enumerate(reader.pages):
        page_number = index + 1
        native_text = page.extract_text() or ""
        native_characters = len(native_text.strip())
        resources = page.get("/Resources")
        images = _image_count(resources)
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(page.get("/Rotate", 0) or 0)
        kind = _content_kind(native_characters, images)
        page_digest = _page_digest(page, page_number, native_text)
        flags = _technical_flags(
            native_text=native_text,
            images=images,
            width=width,
            height=height,
            rotation=rotation,
        )
        yield GuidePageManifest(
            source_version_id=source_version_id,
            page_number=page_number,
            page_digest=page_digest,
            width_points=width,
            height_points=height,
            rotation=rotation,
            native_text_characters=native_characters,
            image_count=images,
            content_kind=kind,
            render_required=kind in {GuideContentKind.RASTER_IMAGE, GuideContentKind.MIXED}
            or "native_text_insufficient" in flags,
            previous_page=page_number - 1 if page_number > 1 else None,
            next_page=page_number + 1 if page_number < total else None,
            technical_flags=flags,
        )


def inspect_pdf(pdf_path: Path, source_version_id: UUID) -> GuidePdfInspection:
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("A practice-guide intake currently accepts PDF only")
    reader = PdfReader(str(pdf_path), strict=True)
    encrypted = reader.is_encrypted
    page_count = len(reader.pages)
    del reader
    pages = tuple(iter_page_manifest(pdf_path, source_version_id))
    return GuidePdfInspection(
        path=pdf_path,
        content_digest=file_sha256(pdf_path),
        size_bytes=pdf_path.stat().st_size,
        media_type="application/pdf",
        encrypted=encrypted,
        page_count=page_count,
        pages=pages,
    )
