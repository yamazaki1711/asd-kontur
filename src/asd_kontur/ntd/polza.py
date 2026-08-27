"""Bounded Polza extraction adapter for public raster normative pages only."""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from base64 import b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from jsonschema import Draft202012Validator

from asd_kontur.harness.models import digest_of

POLZA_SECRET_REFERENCE = "ASD_POLZA_API_KEY"
POLZA_ENDPOINT = "https://polza.ai/api/v1/chat/completions"
POLZA_MODEL = "qwen/qwen3.8-27b"
POLZA_PROFILE_VERSION = "polza-public-ntd-page-v0.1"
POLZA_REGION_PROFILE_VERSION = "polza-public-ntd-region-v0.1"
POLZA_ROTATED_REGION_PROFILE_VERSION = "polza-public-ntd-rotated-region-v0.1"
POLZA_PROMPT_VERSION = "ntd-raster-transcription-v0.1"
POLZA_SCHEMA_VERSION = "ntd-raster-page-candidate-v0.2"
POLZA_REGION_SCHEMA_VERSION = "ntd-raster-region-candidate-v0.1"
POLZA_ROTATED_REGION_SCHEMA_VERSION = "ntd-raster-rotated-region-candidate-v0.1"
FULL_SOURCE_REGION = (Decimal("0"), Decimal("0"), Decimal("1"), Decimal("1"))
IDENTITY_TRANSFORM = (
    Decimal("1"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("1"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("1"),
)


class PolzaExtractionError(RuntimeError):
    def __init__(
        self, code: str, *, retryable: bool = False, outcome_unknown: bool = False
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown
        self.request_digest: str | None = None
        self.response_digest: str | None = None
        self.provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class PolzaPageRequest:
    document_identity: str
    edition_identity: UUID
    artifact_identity: UUID
    page_identity: UUID
    printed_page_label: str | None
    source_width_points: Decimal
    source_height_points: Decimal
    render_digest: str
    render_png: bytes = field(repr=False, compare=False)
    data_classification: str = "public_normative_authority"
    source_region: tuple[Decimal, Decimal, Decimal, Decimal] = FULL_SOURCE_REGION
    render_to_source: tuple[Decimal, ...] = IDENTITY_TRANSFORM

    def __post_init__(self) -> None:
        if self.data_classification != "public_normative_authority":
            raise ValueError("POLZA_NTD_PUBLIC_DATA_ONLY")
        if not self.render_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("POLZA_NTD_RENDER_NOT_PNG")
        actual = "sha256:" + hashlib.sha256(self.render_png).hexdigest()
        if actual != self.render_digest:
            raise ValueError("POLZA_NTD_RENDER_DIGEST_MISMATCH")
        x0, y0, x1, y1 = self.source_region
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("POLZA_NTD_SOURCE_REGION_INVALID")
        if len(self.render_to_source) != 9:
            raise ValueError("POLZA_NTD_RENDER_TO_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class PolzaPageCandidate:
    candidate_manifest: Mapping[str, Any]
    request_digest: str
    response_digest: str
    provider_model: str
    provider_profile_version: str
    prompt_version: str
    schema_version: str
    retry_count: int
    usage_receipt: Mapping[str, Any]
    provider_request_id: str | None


@dataclass(frozen=True, slots=True)
class PolzaHttpRequest:
    url: str
    body: bytes = field(repr=False)
    authorization: str = field(repr=False, compare=False)
    timeout_seconds: float
    max_response_bytes: int


@dataclass(frozen=True, slots=True)
class PolzaHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes = field(repr=False)
    final_url: str

    def header(self, name: str) -> str | None:
        expected = name.casefold()
        return next((value for key, value in self.headers if key.casefold() == expected), None)


class PolzaTransport(Protocol):
    def send(self, request: PolzaHttpRequest) -> PolzaHttpResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


class UrllibPolzaTransport:
    """Strict TLS transport for the single allow-listed Polza endpoint.

    Polza is directly reachable from the MBP deployment profile while the
    general xray proxy route can accept CONNECT and then stall before upstream
    TLS. This adapter therefore does not inherit process-wide proxy settings;
    other acquisition providers keep their independent routing profiles.
    """

    def __init__(self) -> None:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
            _NoRedirect(),
        )

    def send(self, request: PolzaHttpRequest) -> PolzaHttpResponse:
        wire = urllib.request.Request(
            request.url,
            data=request.body,
            method="POST",
            headers={
                "Authorization": request.authorization,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(wire, timeout=request.timeout_seconds) as response:
                body = response.read(request.max_response_bytes + 1)
                if len(body) > request.max_response_bytes:
                    raise PolzaExtractionError("POLZA_RESPONSE_TOO_LARGE")
                return PolzaHttpResponse(
                    response.status,
                    tuple(response.headers.items()),
                    body,
                    response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(request.max_response_bytes + 1)
            return PolzaHttpResponse(exc.code, tuple(exc.headers.items()), body, exc.geturl())
        except TimeoutError as exc:
            raise PolzaExtractionError(
                "POLZA_TIMEOUT", retryable=True, outcome_unknown=True
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise PolzaExtractionError("POLZA_NETWORK_UNAVAILABLE", retryable=True) from exc


CredentialResolver = Callable[[str], str | None]
Sleeper = Callable[[float], None]


def resolve_polza_credential(secret_reference: str) -> str | None:
    """Resolve the configured secret without logging it or persisting it in receipts.

    Environment injection remains suitable for supervised workers. On macOS an owner may
    instead keep the same named secret in the login Keychain; this avoids shell-history and
    process-command-line exposure while allowing the current bounded worker to resolve it.
    """

    environment_value = os.environ.get(secret_reference)
    if environment_value:
        return environment_value
    if os.name != "posix" or not _is_macos():
        return None
    account = os.environ.get("USER")
    if not account:
        return None
    try:
        completed = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                secret_reference,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.rstrip("\r\n")
    return value or None


def _is_macos() -> bool:
    return os.uname().sysname == "Darwin"


class PolzaPublicNtdPageExtractor:
    """Extract strict candidates while keeping source bytes and raw responses out of receipts."""

    def __init__(
        self,
        *,
        transport: PolzaTransport | None = None,
        credential_resolver: CredentialResolver | None = None,
        sleeper: Sleeper = time.sleep,
        timeout_seconds: float = 120,
        max_request_bytes: int = 12_000_000,
        max_response_bytes: int = 4_000_000,
        max_retries: int = 2,
    ) -> None:
        if timeout_seconds <= 0 or max_request_bytes <= 0 or max_response_bytes <= 0:
            raise ValueError("POLZA_NTD_BOUNDS_INVALID")
        if max_retries < 0 or max_retries > 3:
            raise ValueError("POLZA_NTD_RETRY_BOUND_INVALID")
        self._transport = transport or UrllibPolzaTransport()
        self._credential_resolver = credential_resolver or resolve_polza_credential
        self._sleeper = sleeper
        self._timeout_seconds = timeout_seconds
        self._max_request_bytes = max_request_bytes
        self._max_response_bytes = max_response_bytes
        self._max_retries = max_retries

    def credential_available(self) -> bool:
        return bool(self._credential_resolver(POLZA_SECRET_REFERENCE))

    def extract(self, request: PolzaPageRequest) -> PolzaPageCandidate:
        credential = self._credential_resolver(POLZA_SECRET_REFERENCE)
        if not credential:
            raise PolzaExtractionError("POLZA_CREDENTIAL_UNAVAILABLE")
        schema = _candidate_schema(request)
        schema_version = polza_schema_version(request)
        profile_version = polza_profile_version(request)
        body, request_digest = _request_body(request, schema)
        if len(body) > self._max_request_bytes:
            raise PolzaExtractionError("POLZA_REQUEST_TOO_LARGE")
        response: PolzaHttpResponse | None = None
        retry_count = 0
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.send(
                    PolzaHttpRequest(
                        POLZA_ENDPOINT,
                        body,
                        f"Bearer {credential}",
                        self._timeout_seconds,
                        self._max_response_bytes,
                    )
                )
                failure = _status_failure(response.status)
                if failure is not None:
                    raise failure
                break
            except PolzaExtractionError as exc:
                if exc.outcome_unknown or not exc.retryable or attempt == self._max_retries:
                    raise
                retry_count += 1
                self._sleeper(min(0.25 * (2**attempt), 2.0))
        if response is None:
            raise PolzaExtractionError("POLZA_RESPONSE_MISSING", outcome_unknown=True)
        if response.final_url != POLZA_ENDPOINT:
            raise PolzaExtractionError("POLZA_REDIRECT_REJECTED")
        try:
            structured, wire = _parse_response(response, schema)
        except PolzaExtractionError as error:
            error.request_digest = request_digest
            error.response_digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
            error.provider_request_id = response.header("x-request-id")
            raise
        return PolzaPageCandidate(
            _map_regions_to_source(
                structured,
                request.source_region,
                request.render_to_source,
            ),
            request_digest,
            "sha256:" + hashlib.sha256(response.body).hexdigest(),
            POLZA_MODEL,
            profile_version,
            POLZA_PROMPT_VERSION,
            schema_version,
            retry_count,
            _usage_receipt(wire),
            _optional_string(wire.get("id")) or response.header("x-request-id"),
        )


def _request_body(request: PolzaPageRequest, schema: Mapping[str, Any]) -> tuple[bytes, str]:
    prompt = (
        "Transcribe this single public Russian normative-document page exactly. "
        "Preserve clause numbers, dates, document designations, decimal separators, signs, "
        "units, negations and modal words. Return only the strict JSON schema. Do not infer "
        "missing text and mark every ambiguity. Regions use normalized source-page "
        "coordinates [x0,y0,x1,y1]."
    )
    crop_region = [float(value) for value in request.source_region]
    rotated_region = request.render_to_source != IDENTITY_TRANSFORM
    region_key = "render_region" if rotated_region else "source_region"
    if request.source_region != FULL_SOURCE_REGION:
        prompt += (
            f" The supplied image is a crop of {region_key}="
            f"{crop_region}; return block regions normalized to this supplied crop."
        )
    region_metadata = (
        f";{region_key}={crop_region}" if request.source_region != FULL_SOURCE_REGION else ""
    )
    image = b64encode(request.render_png).decode("ascii")
    wire = {
        "model": POLZA_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"document={request.document_identity};"
                            f"edition={request.edition_identity};artifact={request.artifact_identity};"
                            f"page={request.page_identity};label={request.printed_page_label or ''}"
                            f"{region_metadata}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"},
                    },
                ],
            },
        ],
        "temperature": 0,
        "max_completion_tokens": 16_384,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "asd_kontur_public_ntd_page_candidate",
                "strict": True,
                "schema": schema,
            },
        },
        "provider": {"allow_fallbacks": False},
        "stream": False,
    }
    body = json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    schema_version = polza_schema_version(request)
    profile_version = polza_profile_version(request)
    digest_payload = {
        "schema": schema_version,
        "prompt": POLZA_PROMPT_VERSION,
        "profile": profile_version,
        "model": POLZA_MODEL,
        "document": request.document_identity,
        "edition": request.edition_identity,
        "artifact": request.artifact_identity,
        "page": request.page_identity,
        "render_digest": request.render_digest,
    }
    if request.source_region != FULL_SOURCE_REGION:
        digest_payload["source_region"] = crop_region
    if rotated_region:
        digest_payload["render_to_source"] = [str(value) for value in request.render_to_source]
    request_digest = digest_of(digest_payload)
    return body, request_digest


def polza_request_digest(request: PolzaPageRequest) -> str:
    """Return the stable paid-effect identity without resolving a credential or calling Polza."""

    return _request_body(request, _candidate_schema(request))[1]


def polza_schema_version(request: PolzaPageRequest) -> str:
    if request.render_to_source != IDENTITY_TRANSFORM:
        return POLZA_ROTATED_REGION_SCHEMA_VERSION
    return (
        POLZA_SCHEMA_VERSION
        if request.source_region == FULL_SOURCE_REGION
        else POLZA_REGION_SCHEMA_VERSION
    )


def polza_profile_version(request: PolzaPageRequest) -> str:
    if request.render_to_source != IDENTITY_TRANSFORM:
        return POLZA_ROTATED_REGION_PROFILE_VERSION
    return (
        POLZA_PROFILE_VERSION
        if request.source_region == FULL_SOURCE_REGION
        else POLZA_REGION_PROFILE_VERSION
    )


def _candidate_schema(request: PolzaPageRequest) -> dict[str, Any]:
    scalar = {"type": "string"}
    region = {
        "type": "array",
        "prefixItems": [{"type": "number", "minimum": 0, "maximum": 1}] * 4,
        "minItems": 4,
        "maxItems": 4,
    }
    block = {
        "type": "object",
        "required": [
            "region",
            "raw_transcription",
            "normalized_transcription",
            "block_type",
            "hierarchy",
            "critical_tokens",
            "confidence",
            "ambiguity_flags",
        ],
        "properties": {
            "region": region,
            "raw_transcription": scalar,
            "normalized_transcription": scalar,
            "block_type": {
                "type": "string",
                "enum": [
                    "heading",
                    "section",
                    "clause",
                    "paragraph",
                    "list_item",
                    "table",
                    "table_cell",
                    "formula",
                    "note",
                    "appendix",
                    "page_header",
                    "page_footer",
                    "unknown",
                ],
            },
            "hierarchy": {
                "type": "object",
                "required": ["section", "clause", "table", "row", "column"],
                "properties": {
                    "section": {"type": ["string", "null"]},
                    "clause": {"type": ["string", "null"]},
                    "table": {"type": ["string", "null"]},
                    "row": {"type": ["integer", "null"], "minimum": 1},
                    "column": {"type": ["integer", "null"], "minimum": 1},
                },
                "additionalProperties": False,
            },
            "critical_tokens": {"type": "array", "items": scalar},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "ambiguity_flags": {"type": "array", "items": scalar},
        },
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "required": [
            "document_identity",
            "edition_identity",
            "artifact_identity",
            "page_identity",
            "printed_page_label",
            "blocks",
            "page_ambiguity_flags",
        ],
        "properties": {
            "document_identity": {"const": request.document_identity},
            "edition_identity": {"const": str(request.edition_identity)},
            "artifact_identity": {"const": str(request.artifact_identity)},
            "page_identity": {"const": str(request.page_identity)},
            "printed_page_label": {"type": ["string", "null"]},
            "blocks": {"type": "array", "items": block, "minItems": 1},
            "page_ambiguity_flags": {"type": "array", "items": scalar},
        },
        "additionalProperties": False,
    }
    if request.source_region != FULL_SOURCE_REGION:
        required = schema["required"]
        properties = schema["properties"]
        assert isinstance(required, list)
        assert isinstance(properties, dict)
        input_region_key = (
            "input_render_region"
            if request.render_to_source != IDENTITY_TRANSFORM
            else "input_source_region"
        )
        required.append(input_region_key)
        properties[input_region_key] = {"const": [float(value) for value in request.source_region]}
    Draft202012Validator.check_schema(schema)
    return schema


def _map_regions_to_source(
    structured: dict[str, Any],
    source_region: tuple[Decimal, Decimal, Decimal, Decimal],
    render_to_source: tuple[Decimal, ...],
) -> dict[str, Any]:
    if source_region == FULL_SOURCE_REGION and render_to_source == IDENTITY_TRANSFORM:
        return structured
    for block in structured["blocks"]:
        left, top, right, bottom = (float(value) for value in block["region"])
        if render_to_source == IDENTITY_TRANSFORM:
            x0, y0, x1, y1 = (float(value) for value in source_region)
            width = x1 - x0
            height = y1 - y0
            block["region"] = [
                x0 + left * width,
                y0 + top * height,
                x0 + right * width,
                y0 + bottom * height,
            ]
            continue
        corners = (
            _transform_point(render_to_source, left, top),
            _transform_point(render_to_source, right, top),
            _transform_point(render_to_source, right, bottom),
            _transform_point(render_to_source, left, bottom),
        )
        x_values = [value[0] for value in corners]
        y_values = [value[1] for value in corners]
        block["region"] = [
            min(x_values),
            min(y_values),
            max(x_values),
            max(y_values),
        ]
    return structured


def _transform_point(matrix: tuple[Decimal, ...], x: float, y: float) -> tuple[float, float]:
    values = tuple(float(value) for value in matrix)
    return (
        values[0] * x + values[1] * y + values[2],
        values[3] * x + values[4] * y + values[5],
    )


def _parse_response(
    response: PolzaHttpResponse, schema: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        wire = json.loads(response.body)
        if not isinstance(wire, dict):
            raise TypeError
        choices = wire["choices"]
        content = choices[0]["message"]["content"]
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(content, str):
            raise TypeError
        structured = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise PolzaExtractionError("POLZA_RESPONSE_MALFORMED") from exc
    if wire.get("model") != POLZA_MODEL:
        raise PolzaExtractionError("POLZA_MODEL_IDENTITY_MISMATCH")
    if not isinstance(structured, dict):
        raise PolzaExtractionError("POLZA_SCHEMA_INVALID")
    errors = tuple(Draft202012Validator(dict(schema)).iter_errors(structured))
    if errors:
        raise PolzaExtractionError("POLZA_SCHEMA_INVALID")
    for block in structured["blocks"]:
        region = block["region"]
        if not (0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1):
            raise PolzaExtractionError("POLZA_REGION_INVALID")
    return structured, wire


def _status_failure(status: int) -> PolzaExtractionError | None:
    if 200 <= status < 300:
        return None
    if status == 401:
        return PolzaExtractionError("POLZA_AUTHENTICATION_FAILED")
    if status == 402:
        return PolzaExtractionError("POLZA_COST_LIMIT")
    if status == 429:
        return PolzaExtractionError("POLZA_RATE_LIMITED", retryable=True)
    if status in {408, 500, 502, 503, 504}:
        return PolzaExtractionError(
            "POLZA_TRANSIENT_PROVIDER_FAILURE",
            retryable=True,
            outcome_unknown=status == 408,
        )
    return PolzaExtractionError(f"POLZA_HTTP_{status}")


def _usage_receipt(wire: Mapping[str, Any]) -> dict[str, Any]:
    usage = wire.get("usage")
    if not isinstance(usage, dict):
        return {"reported": False}
    allowed = {
        key: value
        for key, value in usage.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens", "cost_rub", "cost"}
        and isinstance(value, (int, float, str))
        and not isinstance(value, bool)
    }
    return {"reported": True, **allowed}


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
