"""Bounded local OCR adapters with coordinate and numeric fidelity."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
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


class QwenVisionOcrAdapter:
    """Loopback Qwen vision OCR with image bytes and validated layout evidence."""

    adapter_key = "qwen3.8-27b-local-vision"
    adapter_version = "qwen-vision-ocr-v3"

    def __init__(self, endpoint: str, *, timeout_seconds: float = 600.0) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def available(self) -> bool:
        health = self._endpoint.removesuffix("/vision") + "/health"
        try:
            with urllib.request.urlopen(health, timeout=2) as response:
                payload = json.loads(response.read(4096))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return False
        return bool(
            response.status == 200
            and isinstance(payload, dict)
            and payload.get("status") == "ready"
        )

    def extract(
        self,
        image_path: Path,
        *,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        page_number: int,
    ) -> OcrAdapterResult:
        image_bytes = image_path.read_bytes()
        if not image_bytes or len(image_bytes) > 12 * 1024 * 1024:
            raise OcrFailure("qwen_vision_image_size_invalid")
        request_body = json.dumps(
            {
                "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                "prompt": (
                    "Распознай текст строительного документа на изображении. Верни только JSON "
                    '{"observations":[{"text":"точный текст","region":[x0,y0,x1,y1]}]}. '
                    "Координаты нормированы от 0 до 1; не выдумывай неразборчивый текст."
                ),
                "max_tokens": 800,
                "temperature": 0.0,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read(4 * 1024 * 1024))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise OcrFailure("qwen_vision_runtime_unavailable") from exc
        if (
            response.status != 200
            or not isinstance(payload, dict)
            or not isinstance(payload.get("text"), str)
        ):
            raise OcrFailure("qwen_vision_response_invalid")
        return self._parse_result(
            payload["text"],
            image_path,
            document_id=document_id,
            document_version=document_version,
            source_version_id=source_version_id,
            page_number=page_number,
        )

    def _parse_result(
        self,
        text: str,
        image_path: Path,
        *,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        page_number: int,
    ) -> OcrAdapterResult:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
            candidate = candidate.rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            payload = _embedded_json_object(candidate)
            if payload is None:
                raise OcrFailure("qwen_vision_result_malformed") from exc
        if not isinstance(payload, dict):
            raise OcrFailure("qwen_vision_result_schema_invalid")
        raw_observations = payload.get("observations")
        observations: list[object]
        if isinstance(raw_observations, list):
            observations = raw_observations
        else:
            root_text = payload.get("text")
            if not isinstance(root_text, str):
                raise OcrFailure("qwen_vision_result_schema_invalid")
            observations = [root_text]
        elements: list[LayoutElement] = []
        for order, item in enumerate(observations, start=1):
            if isinstance(item, str):
                raw_text = item
                raw_region: object | None = None
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                raw_text = item["text"]
                raw_region = item.get("region", item.get("bbox"))
            else:
                raise OcrFailure("qwen_vision_result_schema_invalid")
            region = _normalise_model_region(
                raw_region,
                image_path=image_path,
            )
            elements.append(
                _ocr_element(
                    document_id,
                    document_version,
                    source_version_id,
                    page_number,
                    region,
                    order,
                    raw_text,
                    self.adapter_key,
                )
            )
        return _result(self.adapter_key, self.adapter_version, "ru-RU+en-US", image_path, elements)


def _embedded_json_object(value: str) -> object | None:
    """Return one complete JSON object embedded in an otherwise textual model response."""

    decoder = json.JSONDecoder()
    for start, character in enumerate(value):
        if character != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(value[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _normalise_model_region(
    raw: object | None,
    *,
    image_path: Path,
) -> tuple[float, float, float, float]:
    """Validate normalized or pixel model coordinates; use page scope only when absent."""

    if raw is None:
        return (0.0, 0.0, 1.0, 1.0)
    if not isinstance(raw, list) or len(raw) != 4 or any(isinstance(value, bool) for value in raw):
        raise OcrFailure("qwen_vision_result_schema_invalid")
    try:
        coordinates = tuple(float(value) for value in raw)
    except (TypeError, ValueError) as exc:
        raise OcrFailure("qwen_vision_result_schema_invalid") from exc
    if _valid_region(list(coordinates)):
        return (coordinates[0], coordinates[1], coordinates[2], coordinates[3])
    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size
    if width <= 0 or height <= 0:
        raise OcrFailure("qwen_vision_result_schema_invalid")
    x0, y0, x1, y1 = coordinates
    normalized = (x0 / width, y0 / height, x1 / width, y1 / height)
    if not _valid_region(list(normalized)):
        raise OcrFailure("qwen_vision_result_schema_invalid")
    return normalized


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
    qwen: QwenVisionOcrAdapter,
) -> tuple[OcrAdapter, ...]:
    if route is OcrRoute.NOT_REQUIRED:
        return ()
    if route is OcrRoute.BLOCKED:
        return ()
    qwen_routes = {
        OcrRoute.QWEN_VISION,
        OcrRoute.APPLE_VISION,
        OcrRoute.TESSERACT,
        OcrRoute.VLM_REQUIRED,
    }
    if route in qwen_routes:
        return (qwen,) if qwen.available() else ()
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
