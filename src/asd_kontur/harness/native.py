"""Native-first deterministic preflight before any provider invocation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from pypdf import PdfReader

from .models import Locator


class PreflightDisposition(StrEnum):
    NATIVE_SUFFICIENT = "native_sufficient"
    NATIVE_INSUFFICIENT = "native_insufficient"
    UNSUPPORTED_SOURCE = "unsupported_source"
    POLICY_BLOCKED = "policy_blocked"
    SOURCE_STALE = "source_stale"
    LIFECYCLE_BLOCKED = "lifecycle_blocked"
    NEEDS_LOCAL_EXECUTION = "needs_local_execution"
    EXTERNAL_ROUTE_DENIED = "external_route_denied"


@dataclass(frozen=True, slots=True)
class NativeLayer:
    media_type: str
    text: str
    structured_fields: tuple[tuple[str, object], ...]
    parser_key: str
    parser_version: str


@dataclass(frozen=True, slots=True)
class PreflightInput:
    source_digest: str
    observed_digest: str
    locators: tuple[Locator, ...]
    media_type: str
    classification: str | None
    purpose: str
    workspace_writable: bool
    native_layer: NativeLayer | None
    external_allowed: bool


@dataclass(frozen=True, slots=True)
class PreflightResult:
    disposition: PreflightDisposition
    reason_code: str
    native_fields: tuple[tuple[str, object], ...] = ()


class NativePreflight:
    SUPPORTED = frozenset(
        {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "image/png",
            "image/jpeg",
        }
    )

    def evaluate(
        self, value: PreflightInput, *, required_fields: frozenset[str]
    ) -> PreflightResult:
        if not value.workspace_writable:
            return PreflightResult(PreflightDisposition.LIFECYCLE_BLOCKED, "workspace.not_writable")
        if value.source_digest != value.observed_digest:
            return PreflightResult(PreflightDisposition.SOURCE_STALE, "source.digest_changed")
        if value.media_type not in self.SUPPORTED or not value.locators:
            return PreflightResult(
                PreflightDisposition.UNSUPPORTED_SOURCE, "source.unsupported_or_unlocated"
            )
        if value.classification is None or value.classification in {
            "ambiguous",
            "expired",
            "unset",
        }:
            return PreflightResult(PreflightDisposition.POLICY_BLOCKED, "classification.not_active")
        native = value.native_layer
        if native is not None:
            found = {key for key, _ in native.structured_fields}
            if required_fields.issubset(found):
                return PreflightResult(
                    PreflightDisposition.NATIVE_SUFFICIENT,
                    "native.required_fields_present",
                    native.structured_fields,
                )
        if value.classification in {"legal", "contract_sensitive", "confidential", "geometry"}:
            return PreflightResult(
                PreflightDisposition.NEEDS_LOCAL_EXECUTION, "classification.local_only"
            )
        if not value.external_allowed:
            return PreflightResult(
                PreflightDisposition.EXTERNAL_ROUTE_DENIED, "egress.default_deny"
            )
        return PreflightResult(
            PreflightDisposition.NATIVE_INSUFFICIENT, "native.validators_insufficient"
        )


class PdfNativeExtractor:
    """Extract only explicitly authorized one-based pages from PDF bytes."""

    parser_key = "pdf.pypdf.native-text"

    def __init__(self, parser_version: str) -> None:
        self.parser_version = parser_version

    def extract(self, content: bytes, locators: tuple[Locator, ...]) -> NativeLayer:
        reader = PdfReader(BytesIO(content), strict=True)
        texts: list[str] = []
        fields: list[tuple[str, object]] = []
        for locator in locators:
            index = locator.page - 1
            if index < 0 or index >= len(reader.pages):
                raise ValueError("authorized PDF page is outside the exact source version")
            text = reader.pages[index].extract_text() or ""
            texts.append(text)
            if text.strip():
                fields.append((f"page:{locator.page}:text", text))
        return NativeLayer(
            "application/pdf",
            "\n".join(texts),
            tuple(fields),
            self.parser_key,
            self.parser_version,
        )
