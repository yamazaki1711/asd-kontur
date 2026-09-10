"""Bounded local OCR adapters with coordinate and numeric fidelity."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from asd_kontur.domain import deterministic_uuid

from .models import ExactLocator, LayoutElement, OcrRoute
from .native import normalize_text

_PDFTOPPM_FALLBACKS = (
    Path("/opt/homebrew/bin/pdftoppm"),
    Path("/usr/local/bin/pdftoppm"),
)
_TESSERACT_FALLBACKS = (
    Path("/opt/homebrew/bin/tesseract"),
    Path("/usr/local/bin/tesseract"),
)


class OcrFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class OcrAdapterResult:
    adapter_key: str
    adapter_version: str
    language_profile: str
    elements: tuple[LayoutElement, ...]
    source_image_digest: str
    output_digest: str


class OcrAdapter(Protocol):
    adapter_key: str
    adapter_version: str

    def available(self) -> bool: ...

    def extract(
        self,
        image_path: Path,
        *,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        page_number: int,
    ) -> OcrAdapterResult: ...


class AppleVisionOcrAdapter:
    adapter_key = "apple-vision-accurate"
    adapter_version = "vision-framework-runtime-v0.1"

    def __init__(self, script_path: Path) -> None:
        self._script = script_path

    def available(self) -> bool:
        return self._script.is_file() and shutil.which("swift") is not None

    def extract(
        self,
        image_path: Path,
        *,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        page_number: int,
    ) -> OcrAdapterResult:
        if not self.available():
            raise OcrFailure("apple_vision_unavailable")
        completed = subprocess.run(
            ["swift", str(self._script), str(image_path)],
            capture_output=True,
            check=False,
            timeout=180,
        )
        if completed.returncode != 0 or len(completed.stdout) > 8 * 1024 * 1024:
            raise OcrFailure("apple_vision_execution_failed")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise OcrFailure("apple_vision_result_malformed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
            raise OcrFailure("apple_vision_result_schema_invalid")
        elements: list[LayoutElement] = []
        for order, item in enumerate(payload["observations"], start=1):
            if not isinstance(item, dict):
                raise OcrFailure("apple_vision_result_schema_invalid")
            raw = item.get("text")
            region = item.get("region")
            if not isinstance(raw, str) or not _valid_region(region):
                raise OcrFailure("apple_vision_result_schema_invalid")
            exact_region = cast(list[float | int], region)
            elements.append(
                _ocr_element(
                    document_id,
                    document_version,
                    source_version_id,
                    page_number,
                    (
                        float(exact_region[0]),
                        float(exact_region[1]),
                        float(exact_region[2]),
                        float(exact_region[3]),
                    ),
                    order,
                    raw,
                    self.adapter_key,
                )
            )
        return _result(self.adapter_key, self.adapter_version, "ru-RU+en-US", image_path, elements)


class TesseractOcrAdapter:
    adapter_key = "tesseract-rus-eng"
    adapter_version = "tesseract-5.5-tsv-v0.1"

    def __init__(self, executable: str = "tesseract") -> None:
        self._executable = executable

    def available(self) -> bool:
        return self._resolved_executable() is not None

    def extract(
        self,
        image_path: Path,
        *,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        page_number: int,
    ) -> OcrAdapterResult:
        executable = self._resolved_executable()
        if executable is None:
            raise OcrFailure("tesseract_unavailable")
        completed = subprocess.run(
            [
                executable,
                str(image_path),
                "stdout",
                "-l",
                "rus+eng",
                "--psm",
                "6",
                "tsv",
            ],
            capture_output=True,
            check=False,
            timeout=180,
        )
        if completed.returncode != 0 or len(completed.stdout) > 16 * 1024 * 1024:
            raise OcrFailure("tesseract_execution_failed")
        rows = csv.DictReader(
            io.StringIO(completed.stdout.decode("utf-8", "replace")), delimiter="\t"
        )
        source_width = 0
        source_height = 0
        raw_rows: list[dict[str, str]] = []
        for row in rows:
            if row.get("level") == "1":
                source_width = int(row.get("width") or 0)
                source_height = int(row.get("height") or 0)
            if row.get("level") == "5" and (row.get("text") or "").strip():
                raw_rows.append(row)
        if source_width < 1 or source_height < 1:
            raise OcrFailure("tesseract_coordinate_frame_missing")
        elements: list[LayoutElement] = []
        for order, row in enumerate(raw_rows, start=1):
            left = int(row["left"])
            top = int(row["top"])
            width = int(row["width"])
            height = int(row["height"])
            region = (
                left / source_width,
                top / source_height,
                (left + width) / source_width,
                (top + height) / source_height,
            )
            elements.append(
                _ocr_element(
                    document_id,
                    document_version,
                    source_version_id,
                    page_number,
                    region,
                    order,
                    row["text"],
                    self.adapter_key,
                )
            )
        return _result(self.adapter_key, self.adapter_version, "rus+eng", image_path, elements)

    def _resolved_executable(self) -> str | None:
        if executable := shutil.which(self._executable):
            return executable
        if self._executable == "tesseract":
            for candidate in _TESSERACT_FALLBACKS:
                if candidate.is_file() and candidate.stat().st_mode & 0o111:
                    return str(candidate)
        return None


def select_adapters(
    route: OcrRoute,
    *,
    apple: AppleVisionOcrAdapter,
    tesseract: TesseractOcrAdapter,
) -> tuple[OcrAdapter, ...]:
    if route is OcrRoute.NOT_REQUIRED:
        return ()
    if route is OcrRoute.APPLE_VISION:
        return tuple(adapter for adapter in (apple, tesseract) if adapter.available())
    if route is OcrRoute.TESSERACT:
        return tuple(adapter for adapter in (tesseract, apple) if adapter.available())
    return ()


def render_pdf_page(content: bytes, page_number: int, target: Path, *, dpi: int = 300) -> str:
    executable = _pdf_renderer()
    if executable is None:
        raise OcrFailure("pdf_renderer_unavailable")
    if page_number < 1 or dpi < 72 or dpi > 600:
        raise ValueError("invalid bounded render request")
    with tempfile.NamedTemporaryFile(prefix="asd-source-", suffix=".pdf") as source:
        source.write(content)
        source.flush()
        prefix = target.with_suffix("")
        completed = subprocess.run(
            [
                executable,
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-singlefile",
                "-r",
                str(dpi),
                "-png",
                source.name,
                str(prefix),
            ],
            capture_output=True,
            check=False,
            timeout=180,
        )
    generated = prefix.with_suffix(".png")
    if completed.returncode != 0 or not generated.is_file():
        raise OcrFailure("pdf_page_render_failed")
    if generated != target:
        generated.replace(target)
    return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()


def _pdf_renderer() -> str | None:
    """Find the locally installed Poppler renderer under launchd's restricted PATH."""

    if executable := shutil.which("pdftoppm"):
        return executable
    for candidate in _PDFTOPPM_FALLBACKS:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate)
    return None


def _ocr_element(
    document_id: UUID,
    document_version: int,
    source_version_id: UUID,
    page_number: int,
    region: tuple[float, float, float, float],
    order: int,
    raw: str,
    adapter_key: str,
) -> LayoutElement:
    evidence_digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    locator_id = deterministic_uuid(
        f"ocr-locator:{source_version_id}:{page_number}:{region}:{adapter_key}:{order}"
    )
    element_id = deterministic_uuid(
        f"ocr-element:{source_version_id}:{page_number}:{adapter_key}:{order}:{evidence_digest}"
    )
    locator = ExactLocator(
        source_version_id,
        locator_id,
        document_id,
        document_version,
        page_number,
        region,
        evidence_digest,
    )
    return LayoutElement(
        element_id,
        "ocr_word",
        raw,
        normalize_text(raw),
        order,
        locator,
    )


def _result(
    key: str,
    version: str,
    language: str,
    path: Path,
    elements: list[LayoutElement],
) -> OcrAdapterResult:
    source_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    output_payload = [
        (item.raw_text, item.locator.region, item.locator.evidence_digest) for item in elements
    ]
    output_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(output_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
    )
    return OcrAdapterResult(key, version, language, tuple(elements), source_digest, output_digest)


def _valid_region(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    if not all(isinstance(item, (int, float)) for item in value):
        return False
    x0, y0, x1, y1 = (float(item) for item in value)
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
