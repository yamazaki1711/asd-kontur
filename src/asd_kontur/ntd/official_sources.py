"""Provider-specific official-source adapters over one bounded acquisition port."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from asd_kontur.domain import deterministic_uuid, uuid7

from .identifiers import normalize_identifier
from .models import (
    AcquisitionTerminalStatus,
    CorpusMemberStatus,
    NormativeCorpusManifest,
    NormativeCorpusMember,
    OfficialHttpMetadata,
    OfficialProvider,
    OfficialProviderHealthReceipt,
    ProviderAccessStatus,
)

OFFICIAL_ACQUISITION_PROFILE_VERSION = "official_ntd_acquisition_v0.2"
ROSSTANDART_SPDS_MANIFEST_PROFILE_VERSION = "spds_official_manifest_v0.1"
SPDS_QUERY = "Система проектной документации для строительства"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024

# Standards and construction NTD are resolved through the issuing ministry first.
# A no-result is evidence to continue to the official standards fund; a ministry
# news page is never promoted to the bytes of a standard.
OFFICIAL_NTD_RESOLUTION_ORDER = (
    OfficialProvider.MINSTROY_CATALOGUE,
    OfficialProvider.ROSSTANDART_FUND,
)
OFFICIAL_LEGAL_ACT_RESOLUTION_ORDER = (
    OfficialProvider.GOVERNMENT_PORTAL,
    OfficialProvider.OFFICIAL_LEGAL_PUBLICATION,
)

# Owner-approved discovery order. Only rank 1 is an official authority source;
# ranks 2 and 3 may locate designations/editions but can never supply canonical
# normative bytes, provisions, activation status or RuleVersion evidence.
NTD_PRIORITY_SEARCH_SOURCES: tuple[tuple[int, str, str], ...] = (
    (1, "https://minstroyrf.gov.ru/docs/", "official_authority_candidate"),
    (2, "https://docs.cntd.ru/", "discovery_reference_only"),
    (3, "https://meganorm.ru/", "discovery_reference_only"),
)

_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "content-disposition",
        "content-length",
        "content-type",
        "etag",
        "last-modified",
        "location",
        "server",
        "x-content-type-options",
    }
)

_PROVIDER_HOSTS: dict[OfficialProvider, frozenset[str]] = {
    OfficialProvider.GOVERNMENT_PORTAL: frozenset(
        {"government.ru", "www.government.ru", "static.government.ru"}
    ),
    OfficialProvider.OFFICIAL_LEGAL_PUBLICATION: frozenset(
        {"publication.pravo.gov.ru", "pravo.gov.ru", "www.pravo.gov.ru"}
    ),
    OfficialProvider.ROSSTANDART_FUND: frozenset(
        {"protect.gost.ru", "www.protect.gost.ru", "rst.gov.ru", "www.rst.gov.ru"}
    ),
    OfficialProvider.MINSTROY_CATALOGUE: frozenset({"minstroyrf.gov.ru", "www.minstroyrf.gov.ru"}),
}


class TransportProfile(StrEnum):
    ENVIRONMENT_PROXY = "environment_proxy"
    DIRECT = "direct"


class OfficialSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class _RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        self.chain: list[str] = []

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.chain.append(f"{code}:{newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True, slots=True)
class OfficialSourceResponse:
    metadata: OfficialHttpMetadata
    body: bytes


@dataclass(frozen=True, slots=True)
class StreamedOfficialSource:
    metadata: OfficialHttpMetadata
    path: Path
    content_digest: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class RosstandartPageDescriptor:
    page_number: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RosstandartViewerManifest:
    catalog_id: str
    manifest_url: str
    pages: tuple[RosstandartPageDescriptor, ...]
    response_digest: str
    retrieved_at: datetime
    access_token: str = field(repr=False, compare=False)

    @property
    def semantic_fingerprint(self) -> str:
        stable = json.dumps(
            {
                "schema": "rosstandart_viewer_manifest_v1",
                "catalog_id": self.catalog_id,
                "manifest_url": self.manifest_url,
                "pages": [
                    {"n": page.page_number, "w": page.width, "h": page.height}
                    for page in self.pages
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return _digest(stable)


@dataclass(frozen=True, slots=True)
class ValidatedOfficialPageImage:
    catalog_id: str
    page_number: int
    total_pages: int
    official_url: str
    declared_media_type: str | None
    detected_media_type: str
    width: int
    height: int
    byte_length: int
    content_digest: str
    validation_observations: tuple[str, ...]
    response: OfficialSourceResponse = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RosstandartViewerAccessProbe:
    catalog_id: str
    status: ProviderAccessStatus
    sampled_page_numbers: tuple[int, ...]
    sampled_digests: tuple[str, ...]
    declared_media_types: tuple[str | None, ...]
    detected_media_types: tuple[str, ...]
    observations: tuple[str, ...]


class OfficialSourcePort(Protocol):
    provider: OfficialProvider

    def get(self, url: str) -> OfficialSourceResponse: ...

    def stream_to_path(self, url: str, destination: Path) -> StreamedOfficialSource: ...


class BoundedOfficialTransport:
    """Explicit-route, TLS-verifying transport restricted to one official provider."""

    def __init__(
        self,
        provider: OfficialProvider,
        *,
        profile: TransportProfile,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        min_interval_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0 or not 1 <= max_attempts <= 3 or max_response_bytes < 1:
            raise ValueError("Official transport bounds are invalid")
        self.provider = provider
        self.profile = profile
        self._timeout = timeout_seconds
        self._attempts = max_attempts
        self._max_bytes = max_response_bytes
        self._interval = min_interval_seconds
        self._sleep = sleeper
        self._clock = clock
        self._last_request_at: float | None = None
        proxy_handler = (
            urllib.request.ProxyHandler({})
            if profile is TransportProfile.DIRECT
            else urllib.request.ProxyHandler()
        )
        self._redirect_handler = _RecordingRedirectHandler()
        self._opener = urllib.request.build_opener(
            proxy_handler,
            self._redirect_handler,
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def get(self, url: str) -> OfficialSourceResponse:
        _require_provider_url(self.provider, url)
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            self._rate_limit()
            self._redirect_handler.chain.clear()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "text/html,application/json,application/pdf,image/*;q=0.8",
                    "User-Agent": "ASD-KONTUR/0.1 bounded-official-ntd-acquisition",
                },
            )
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    final_url = response.geturl()
                    _require_provider_url(self.provider, final_url)
                    body = response.read(self._max_bytes + 1)
                    if len(body) > self._max_bytes:
                        raise OfficialSourceError(
                            "OFFICIAL_RESPONSE_TOO_LARGE", "Official response exceeded size bound."
                        )
                    headers = response.headers
                    safe_headers = tuple(
                        sorted(
                            (key.lower(), value)
                            for key, value in headers.items()
                            if key.lower() in _SAFE_RESPONSE_HEADERS
                        )
                    )
                    return OfficialSourceResponse(
                        OfficialHttpMetadata(
                            request_url=url,
                            final_url=final_url,
                            status_code=int(response.status),
                            content_type=headers.get_content_type(),
                            etag=headers.get("ETag"),
                            last_modified=headers.get("Last-Modified"),
                            byte_length=len(body),
                            retrieved_at=datetime.now(UTC),
                            redirect_chain=tuple(self._redirect_handler.chain),
                            response_headers=safe_headers,
                        ),
                        body,
                    )
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 401:
                    raise OfficialSourceError(
                        "OFFICIAL_AUTHENTICATION_REQUIRED",
                        "Official provider returned HTTP 401.",
                    ) from exc
                if exc.code == 403:
                    raise OfficialSourceError(
                        "OFFICIAL_HTTP_ACCESS_DENIED",
                        "Official provider returned HTTP 403.",
                    ) from exc
                if exc.code == 404:
                    raise OfficialSourceError(
                        "OFFICIAL_ARTIFACT_UNAVAILABLE",
                        "Official provider returned HTTP 404.",
                    ) from exc
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == self._attempts:
                    raise OfficialSourceError(
                        "OFFICIAL_HTTP_ERROR", f"Official provider returned HTTP {exc.code}."
                    ) from exc
            except ssl.SSLCertVerificationError as exc:
                raise OfficialSourceError(
                    "OFFICIAL_TLS_VERIFICATION_FAILED",
                    "Official provider certificate verification failed.",
                ) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt == self._attempts:
                    code = _network_failure_code(exc, profile=self.profile)
                    raise OfficialSourceError(
                        code,
                        "Official provider was unavailable within bounded retry policy.",
                    ) from exc
            self._sleep(float(2 ** (attempt - 1)))
        raise OfficialSourceError(
            "OFFICIAL_ACCESS_BLOCKED", "Official provider unavailable."
        ) from last_error

    def stream_to_path(self, url: str, destination: Path) -> StreamedOfficialSource:
        """Stream one official response into a pre-created private directory."""

        _require_provider_url(self.provider, url)
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise ValueError("Official download destination must have an existing absolute parent")
        if destination.exists() or destination.is_symlink():
            raise ValueError("Official download destination must not exist")
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            self._rate_limit()
            self._redirect_handler.chain.clear()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/pdf,text/html,image/*;q=0.8",
                    "User-Agent": "ASD-KONTUR/0.1 bounded-official-ntd-acquisition",
                },
            )
            try:
                with self._opener.open(request, timeout=self._timeout) as response:
                    final_url = response.geturl()
                    _require_provider_url(self.provider, final_url)
                    declared_length = response.headers.get("Content-Length")
                    if declared_length is not None and int(declared_length) > self._max_bytes:
                        raise OfficialSourceError(
                            "OFFICIAL_RESPONSE_TOO_LARGE",
                            "Official Content-Length exceeded the configured bound.",
                        )
                    digest = hashlib.sha256()
                    size = 0
                    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        with os.fdopen(descriptor, "wb") as stream:
                            while True:
                                chunk = response.read(1024 * 1024)
                                if not chunk:
                                    break
                                size += len(chunk)
                                if size > self._max_bytes:
                                    raise OfficialSourceError(
                                        "OFFICIAL_RESPONSE_TOO_LARGE",
                                        "Official response exceeded the configured bound.",
                                    )
                                digest.update(chunk)
                                stream.write(chunk)
                            stream.flush()
                            os.fsync(stream.fileno())
                    except BaseException:
                        destination.unlink(missing_ok=True)
                        raise
                    headers = response.headers
                    safe_headers = tuple(
                        sorted(
                            (key.lower(), value)
                            for key, value in headers.items()
                            if key.lower() in _SAFE_RESPONSE_HEADERS
                        )
                    )
                    metadata = OfficialHttpMetadata(
                        request_url=url,
                        final_url=final_url,
                        status_code=int(response.status),
                        content_type=headers.get_content_type(),
                        etag=headers.get("ETag"),
                        last_modified=headers.get("Last-Modified"),
                        byte_length=size,
                        retrieved_at=datetime.now(UTC),
                        redirect_chain=tuple(self._redirect_handler.chain),
                        response_headers=safe_headers,
                    )
                    return StreamedOfficialSource(
                        metadata,
                        destination,
                        f"sha256:{digest.hexdigest()}",
                        size,
                    )
            except urllib.error.HTTPError as exc:
                last_error = exc
                code = _http_error_code(exc.code)
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == self._attempts:
                    raise OfficialSourceError(
                        code, f"Official provider returned HTTP {exc.code}."
                    ) from exc
            except ssl.SSLCertVerificationError as exc:
                raise OfficialSourceError(
                    "OFFICIAL_TLS_VERIFICATION_FAILED",
                    "Official provider certificate verification failed.",
                ) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt == self._attempts:
                    raise OfficialSourceError(
                        _network_failure_code(exc, profile=self.profile),
                        "Official provider was unavailable within bounded retry policy.",
                    ) from exc
            self._sleep(float(2 ** (attempt - 1)))
        raise OfficialSourceError(
            "OFFICIAL_ACCESS_BLOCKED", "Official provider unavailable."
        ) from last_error

    def health(self, endpoint: str) -> OfficialProviderHealthReceipt:
        checked_at = datetime.now(UTC)
        try:
            response = self.get(endpoint)
        except OfficialSourceError as exc:
            access_status = _provider_access_status(exc.code)
            return OfficialProviderHealthReceipt(
                uuid7(),
                self.provider,
                endpoint,
                self.profile.value,
                checked_at,
                access_status,
                None,
                None,
                exc.code,
                {
                    "exception_chain": _exception_chain(exc),
                    "retry_policy": {
                        "max_attempts": self._attempts,
                        "timeout_seconds": self._timeout,
                    },
                    "proxy_inherited": self.profile is TransportProfile.ENVIRONMENT_PROXY,
                },
            )
        return OfficialProviderHealthReceipt(
            uuid7(),
            self.provider,
            endpoint,
            self.profile.value,
            checked_at,
            ProviderAccessStatus.AVAILABLE,
            response.metadata.status_code,
            _digest(response.body),
            None,
            {
                "final_url": response.metadata.final_url,
                "redirect_chain": response.metadata.redirect_chain,
                "declared_content_type": response.metadata.content_type,
                "response_headers": response.metadata.response_headers,
                "byte_length": response.metadata.byte_length,
                "retry_policy": {"max_attempts": self._attempts, "timeout_seconds": self._timeout},
                "proxy_inherited": self.profile is TransportProfile.ENVIRONMENT_PROXY,
            },
        )

    def _rate_limit(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self._interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()


class RosstandartSpdsClient:
    """Build the exact official SPDS search denominator and expose official page views."""

    provider = OfficialProvider.ROSSTANDART_FUND
    base_url = "https://protect.gost.ru"

    def __init__(self, transport: OfficialSourcePort) -> None:
        if transport.provider is not self.provider:
            raise ValueError("Rosstandart client requires its provider-specific transport")
        self._transport = transport

    def build_manifest(self, *, created_at: datetime) -> NormativeCorpusManifest:
        encoded = urllib.parse.urlencode({"year": 0, "month": 0, "search": SPDS_QUERY})
        first_url = f"{self.base_url}/gost?{encoded}"
        first = self._transport.get(first_url)
        parser = _RosstandartSearchParser()
        parser.feed(_decode(first.body))
        parser.close()
        denominator = parser.denominator
        if denominator is None or denominator < 1:
            raise OfficialSourceError("SPDS_DENOMINATOR_MISSING", "Official search count absent.")
        page_count = max(1, (denominator + 19) // 20)
        endpoints = [first_url]
        records = list(parser.records)
        for page in range(2, page_count + 1):
            url = f"{first_url}&page={page}"
            response = self._transport.get(url)
            page_parser = _RosstandartSearchParser()
            page_parser.feed(_decode(response.body))
            page_parser.close()
            endpoints.append(url)
            records.extend(page_parser.records)
        by_catalog_id = {record.catalog_id: record for record in records}
        if len(by_catalog_id) != denominator:
            raise OfficialSourceError(
                "SPDS_DENOMINATOR_RECONCILIATION_FAILED",
                f"Official denominator {denominator} != parsed records {len(by_catalog_id)}.",
            )
        ordered = sorted(
            by_catalog_id.values(), key=lambda item: (item.designation, item.catalog_id)
        )
        members: list[NormativeCorpusMember] = []
        for ordinal, record in enumerate(ordered, start=1):
            try:
                normalized = normalize_identifier(record.designation)
                identity = normalized.stable_identity_key
            except ValueError:
                identity = f"ru:rosstandart:catalog:{record.catalog_id}"
            members.append(
                NormativeCorpusMember(
                    member_id=deterministic_uuid(f"spds-member:{record.catalog_id}"),
                    ordinal=ordinal,
                    stable_identity_key=identity,
                    designation=record.designation,
                    title=record.title,
                    catalog_id=record.catalog_id,
                    catalog_url=f"{self.base_url}/gost/details/{record.catalog_id}",
                    status=_member_status(record.status),
                    replaces_designation=None,
                    replaced_by_designation=None,
                    scope_text=None,
                    official_metadata={"search_status": record.status},
                    acquisition_status=AcquisitionTerminalStatus.OFFICIAL_METADATA_ONLY,
                    metadata_digest=_digest(
                        f"{record.designation}\n{record.title}\n{record.status}".encode()
                    ),
                )
            )
        return NormativeCorpusManifest(
            manifest_id=deterministic_uuid(
                f"normative-corpus:spds:{ROSSTANDART_SPDS_MANIFEST_PROFILE_VERSION}"
            ),
            version=1,
            corpus_key="ru:spds",
            query=SPDS_QUERY,
            provider=self.provider,
            query_endpoints=tuple(endpoints),
            denominator=denominator,
            members=tuple(members),
            parser_version=ROSSTANDART_SPDS_MANIFEST_PROFILE_VERSION,
            created_at=created_at,
        )

    def enrich_manifest_cards(
        self,
        manifest: NormativeCorpusManifest,
        *,
        created_at: datetime,
    ) -> NormativeCorpusManifest:
        """Create a superseding manifest from every exact official catalog card."""

        if manifest.provider is not self.provider or manifest.corpus_key != "ru:spds":
            raise ValueError("SPDS card enrichment requires an exact Rosstandart manifest")
        members: list[NormativeCorpusMember] = []
        for member in manifest.members:
            response = self.fetch_card(member.catalog_id)
            metadata = parse_rosstandart_card(response.body)
            if metadata.designation != member.designation or metadata.title != member.title:
                raise OfficialSourceError(
                    "SPDS_CARD_IDENTITY_CONFLICT",
                    f"Official catalog card changed identity for {member.catalog_id}.",
                )
            members.append(
                NormativeCorpusMember(
                    member.member_id,
                    member.ordinal,
                    member.stable_identity_key,
                    member.designation,
                    member.title,
                    member.catalog_id,
                    member.catalog_url,
                    member.status,
                    metadata.replaces_designation,
                    metadata.replaced_by_designation,
                    metadata.scope_text,
                    metadata.as_dict(),
                    AcquisitionTerminalStatus.OFFICIAL_METADATA_ONLY,
                    _digest(response.body),
                )
            )
        return NormativeCorpusManifest(
            manifest.manifest_id,
            manifest.version + 1,
            manifest.corpus_key,
            manifest.query,
            manifest.provider,
            manifest.query_endpoints,
            manifest.denominator,
            tuple(members),
            f"{ROSSTANDART_SPDS_MANIFEST_PROFILE_VERSION}+cards-v1",
            created_at,
        )

    def fetch_card(self, catalog_id: str) -> OfficialSourceResponse:
        if not re.fullmatch(r"[0-9a-f-]{36}", catalog_id):
            raise ValueError("Invalid Rosstandart catalog identity")
        return self._transport.get(f"{self.base_url}/gost/details/{catalog_id}")

    def fetch_view_manifest(self, catalog_id: str) -> OfficialSourceResponse:
        if not re.fullmatch(r"[0-9a-f-]{36}", catalog_id):
            raise ValueError("Invalid Rosstandart catalog identity")
        return self._transport.get(f"{self.base_url}/api/docview/gostdoc/{catalog_id}/pages")

    def resolve_view_manifest(self, catalog_id: str) -> RosstandartViewerManifest:
        return parse_rosstandart_viewer_manifest(catalog_id, self.fetch_view_manifest(catalog_id))

    def fetch_page_image(
        self,
        manifest: RosstandartViewerManifest,
        *,
        page_number: int,
    ) -> ValidatedOfficialPageImage:
        descriptor, response = self.fetch_page_response(manifest, page_number=page_number)
        return validate_rosstandart_page_image(
            catalog_id=manifest.catalog_id,
            descriptor=descriptor,
            total_pages=len(manifest.pages),
            response=response,
        )

    def fetch_page_response(
        self,
        manifest: RosstandartViewerManifest,
        *,
        page_number: int,
    ) -> tuple[RosstandartPageDescriptor, OfficialSourceResponse]:
        descriptor = next(
            (page for page in manifest.pages if page.page_number == page_number), None
        )
        if descriptor is None:
            raise OfficialSourceError(
                "OFFICIAL_VIEWER_PAGE_IDENTITY_INVALID",
                "Requested page is outside the exact official viewer manifest.",
            )
        token = urllib.parse.quote(manifest.access_token, safe="")
        url = f"{self.base_url}/api/docview/img/{token}/{page_number}"
        return descriptor, self._transport.get(url)

    def probe_viewer_access(
        self, manifest: RosstandartViewerManifest
    ) -> RosstandartViewerAccessProbe:
        sample_numbers = tuple(range(1, min(2, len(manifest.pages)) + 1))
        digests: list[str] = []
        declared: list[str | None] = []
        detected: list[str] = []
        observations: list[str] = []
        geometry_mismatches = 0
        for page_number in sample_numbers:
            descriptor, response = self.fetch_page_response(manifest, page_number=page_number)
            media_type = _detect_media_type(response.body)
            digests.append(_digest(response.body))
            declared.append(response.metadata.content_type)
            detected.append(media_type)
            if response.metadata.content_type != media_type:
                observations.append(f"page:{page_number}:DECLARED_DETECTED_MIME_MISMATCH")
            try:
                width, height = _validate_png(response.body)
            except OfficialSourceError as exc:
                observations.append(f"page:{page_number}:{exc.code}")
                continue
            if (width, height) != (descriptor.width, descriptor.height):
                geometry_mismatches += 1
                observations.append(f"page:{page_number}:PAGE_GEOMETRY_MISMATCH")
        repeated_representation = len(set(digests)) == 1 and len(digests) >= 2
        if repeated_representation and geometry_mismatches == len(sample_numbers):
            # Identical wrong-geometry bytes prove a viewer placeholder, but do
            # not prove why the provider returned it (authentication, licensing,
            # or another server policy).  Preserve the exact observed failure.
            status = ProviderAccessStatus.INVALID_RESPONSE
            observations.append("REPEATED_VIEWER_PLACEHOLDER")
        elif geometry_mismatches or any("INVALID" in item for item in observations):
            status = ProviderAccessStatus.INVALID_RESPONSE
        else:
            status = ProviderAccessStatus.AVAILABLE
        return RosstandartViewerAccessProbe(
            catalog_id=manifest.catalog_id,
            status=status,
            sampled_page_numbers=sample_numbers,
            sampled_digests=tuple(digests),
            declared_media_types=tuple(declared),
            detected_media_types=tuple(detected),
            observations=tuple(observations),
        )


class GovernmentResolutionClient:
    provider = OfficialProvider.GOVERNMENT_PORTAL
    consolidated_pp87_url = "https://government.ru/docs/all/63014/"

    def __init__(self, transport: OfficialSourcePort) -> None:
        if transport.provider is not self.provider:
            raise ValueError("Government client requires its provider-specific transport")
        self._transport = transport

    def fetch_pp87_consolidated(self) -> OfficialSourceResponse:
        return self._transport.get(self.consolidated_pp87_url)


class OfficialLegalPublicationClient:
    provider = OfficialProvider.OFFICIAL_LEGAL_PUBLICATION

    def __init__(self, transport: OfficialSourcePort) -> None:
        if transport.provider is not self.provider:
            raise ValueError("Legal publication client requires its provider-specific transport")
        self._transport = transport

    def fetch_publication(self, publication_url: str) -> OfficialSourceResponse:
        return self._transport.get(publication_url)


@dataclass(frozen=True, slots=True)
class _SearchRecord:
    catalog_id: str
    designation: str
    title: str
    status: str


@dataclass(frozen=True, slots=True)
class RosstandartCardMetadata:
    designation: str
    title: str
    approval_order: str | None
    approval_date: date | None
    effective_from: date | None
    scope_text: str | None
    replaces_designation: str | None
    replaced_by_designation: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "designation": self.designation,
            "title": self.title,
            "approval_order": self.approval_order,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "scope_text": self.scope_text,
            "replaces_designation": self.replaces_designation,
            "replaced_by_designation": self.replaced_by_designation,
        }


class _RosstandartCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self._span_depth = 0
        self._paragraph_depth = 0
        self._label_parts: list[str] = []
        self._value_parts: list[str] = []
        self._pending_label: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "span" and "tracking-wider" in (attributes.get("class") or ""):
            self._span_depth = 1
            self._label_parts = []
        elif self._span_depth:
            self._span_depth += 1
        if tag == "p" and self._pending_label is not None:
            self._paragraph_depth = 1
            self._value_parts = []
        elif self._paragraph_depth:
            self._paragraph_depth += 1

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._span_depth:
            self._label_parts.append(value)
        elif self._paragraph_depth:
            self._value_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if self._span_depth:
            self._span_depth -= 1
            if self._span_depth == 0 and tag == "span":
                self._pending_label = " ".join(self._label_parts)
        if self._paragraph_depth:
            self._paragraph_depth -= 1
            if self._paragraph_depth == 0 and tag == "p" and self._pending_label:
                self.values[self._pending_label] = " ".join(self._value_parts)
                self._pending_label = None


def parse_rosstandart_card(body: bytes) -> RosstandartCardMetadata:
    parser = _RosstandartCardParser()
    parser.feed(_decode(body))
    parser.close()
    designation = parser.values.get("Обозначение", "").strip()
    title = parser.values.get("Заглавие на русском языке", "").strip()
    if not designation or not title:
        raise OfficialSourceError("SPDS_CARD_METADATA_INVALID", "Official card identity absent.")
    return RosstandartCardMetadata(
        designation,
        title,
        _none_if_dash(parser.values.get("Номер приказа")),
        _parse_ru_date(parser.values.get("Дата приказа")),
        _parse_ru_date(parser.values.get("Дата введения в действие")),
        _none_if_dash(parser.values.get("Область применения")),
        _none_if_dash(parser.values.get("Обозначение заменяемого(ых)")),
        _none_if_dash(parser.values.get("Обозначение заменяющего")),
    )


def parse_rosstandart_viewer_manifest(
    catalog_id: str,
    response: OfficialSourceResponse,
) -> RosstandartViewerManifest:
    if not re.fullmatch(r"[0-9a-f-]{36}", catalog_id):
        raise ValueError("Invalid Rosstandart catalog identity")
    if response.metadata.content_type != "application/json":
        raise OfficialSourceError(
            "OFFICIAL_UNEXPECTED_MIME",
            "Rosstandart viewer manifest did not declare application/json.",
        )
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfficialSourceError(
            "OFFICIAL_VIEWER_PROTOCOL_UNSUPPORTED",
            "Rosstandart viewer manifest is not valid UTF-8 JSON.",
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"token", "pages"}:
        raise OfficialSourceError(
            "OFFICIAL_VIEWER_PROTOCOL_UNSUPPORTED",
            "Rosstandart viewer manifest schema changed.",
        )
    token = payload.get("token")
    pages = payload.get("pages")
    if (
        not isinstance(token, str)
        or not 16 <= len(token) <= 4096
        or any(character.isspace() for character in token)
        or not isinstance(pages, list)
        or len(pages) > 5000
    ):
        raise OfficialSourceError(
            "OFFICIAL_VIEWER_PROTOCOL_UNSUPPORTED",
            "Rosstandart viewer access token or page list is invalid.",
        )
    if not pages:
        raise OfficialSourceError(
            "OFFICIAL_ARTIFACT_UNAVAILABLE",
            "Rosstandart official card has no viewer page representations.",
        )
    descriptors: list[RosstandartPageDescriptor] = []
    for expected, item in enumerate(pages, start=1):
        if not isinstance(item, dict) or set(item) != {"n", "w", "h"}:
            raise OfficialSourceError(
                "OFFICIAL_VIEWER_PROTOCOL_UNSUPPORTED",
                "Rosstandart page descriptor schema changed.",
            )
        number, width, height = item["n"], item["w"], item["h"]
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number != expected
            or not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
            or not 1 <= width <= 100_000
            or not 1 <= height <= 100_000
        ):
            raise OfficialSourceError(
                "OFFICIAL_VIEWER_PAGE_IDENTITY_INVALID",
                "Rosstandart page order or geometry is invalid.",
            )
        descriptors.append(RosstandartPageDescriptor(number, width, height))
    return RosstandartViewerManifest(
        catalog_id=catalog_id,
        manifest_url=response.metadata.final_url,
        pages=tuple(descriptors),
        response_digest=_digest(response.body),
        retrieved_at=response.metadata.retrieved_at,
        access_token=token,
    )


def validate_rosstandart_page_image(
    *,
    catalog_id: str,
    descriptor: RosstandartPageDescriptor,
    total_pages: int,
    response: OfficialSourceResponse,
) -> ValidatedOfficialPageImage:
    body = response.body
    declared = response.metadata.content_type
    detected = _detect_media_type(body)
    observations: list[str] = []
    if detected == "image/png":
        width, height = _validate_png(body)
    else:
        raise OfficialSourceError(
            "OFFICIAL_INVALID_BYTES",
            f"Official viewer page has unsupported or invalid bytes ({detected}).",
        )
    if declared != detected:
        observations.append("DECLARED_DETECTED_MIME_MISMATCH")
    if (width, height) != (descriptor.width, descriptor.height):
        raise OfficialSourceError(
            "OFFICIAL_VIEWER_PAGE_GEOMETRY_MISMATCH",
            "Decoded image geometry differs from the official page manifest.",
        )
    return ValidatedOfficialPageImage(
        catalog_id=catalog_id,
        page_number=descriptor.page_number,
        total_pages=total_pages,
        official_url=response.metadata.final_url,
        declared_media_type=declared,
        detected_media_type=detected,
        width=width,
        height=height,
        byte_length=len(body),
        content_digest=_digest(body),
        validation_observations=tuple(observations),
        response=response,
    )


class _RosstandartSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.denominator: int | None = None
        self.records: list[_SearchRecord] = []
        self._in_row = False
        self._cell = -1
        self._cell_parts: list[list[str]] = []
        self._catalog_id: str | None = None
        self._all_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._in_row = True
            self._cell = -1
            self._cell_parts = []
            self._catalog_id = None
        elif self._in_row and tag == "td":
            self._cell += 1
            self._cell_parts.append([])
        elif self._in_row and tag == "a":
            href = attributes.get("href") or ""
            match = re.fullmatch(r"/gost/details/([0-9a-f-]{36})", href)
            if match:
                self._catalog_id = match.group(1)

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        self._all_text.append(value)
        if self._in_row and 0 <= self._cell < len(self._cell_parts):
            self._cell_parts[self._cell].append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tr" or not self._in_row:
            return
        cells = [" ".join(parts).strip() for parts in self._cell_parts]
        if self._catalog_id and len(cells) >= 4:
            self.records.append(_SearchRecord(self._catalog_id, cells[0], cells[1], cells[3]))
        self._in_row = False

    def close(self) -> None:
        super().close()
        joined = " ".join(self._all_text)
        match = re.search(r"Найдено:\s*(\d+)", joined)
        if match:
            self.denominator = int(match.group(1))


def _member_status(value: str) -> CorpusMemberStatus:
    lowered = value.casefold()
    if "утратил силу" in lowered:
        return CorpusMemberStatus.NOT_EFFECTIVE_IN_RF
    if "замен" in lowered:
        return CorpusMemberStatus.REPLACED
    if "отмен" in lowered:
        return CorpusMemberStatus.CANCELLED
    if "действ" in lowered:
        return CorpusMemberStatus.ACTIVE
    return CorpusMemberStatus.UNKNOWN


def _none_if_dash(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip()
    return None if normalized in {"", "-", "—"} else normalized


def _parse_ru_date(value: str | None) -> date | None:
    normalized = _none_if_dash(value)
    if normalized is None:
        return None
    try:
        return datetime.strptime(normalized, "%d.%m.%Y").date()
    except ValueError as exc:
        raise OfficialSourceError(
            "SPDS_CARD_DATE_INVALID", "Official catalog date has an unexpected format."
        ) from exc


def _require_provider_url(provider: OfficialProvider, url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _PROVIDER_HOSTS[provider]:
        raise OfficialSourceError(
            "OFFICIAL_HOST_NOT_ALLOWED", "URL is outside the selected official provider."
        )
    if parsed.username or parsed.password or parsed.fragment:
        raise OfficialSourceError("OFFICIAL_URL_INVALID", "Official URL contains forbidden parts.")


def _decode(value: bytes) -> str:
    return html.unescape(value.decode("utf-8", errors="strict"))


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _detect_media_type(value: bytes) -> str:
    if value.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if value.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if value.startswith(b"%PDF-"):
        return "application/pdf"
    if value.lstrip().startswith((b"{", b"[")):
        return "application/json"
    if b"<html" in value[:4096].lower() or b"<!doctype html" in value[:4096].lower():
        return "text/html"
    return "application/octet-stream"


def _validate_png(value: bytes) -> tuple[int, int]:
    """Validate the entire PNG container, CRCs and lossless image stream.

    The official Rosstandart viewer currently serves non-interlaced PNG pages
    while declaring ``image/jpeg``. We preserve the bytes and header mismatch,
    but publication requires a complete, single-image PNG with no trailing or
    embedded payload and geometry equal to the page manifest.
    """

    signature = b"\x89PNG\r\n\x1a\n"
    if not value.startswith(signature):
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG signature is absent.")
    offset = len(signature)
    chunks: list[tuple[bytes, bytes]] = []
    seen_iend = False
    while offset < len(value):
        if len(value) - offset < 12:
            raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG chunk is truncated.")
        length = struct.unpack(">I", value[offset : offset + 4])[0]
        chunk_type = value[offset + 4 : offset + 8]
        end = offset + 12 + length
        if length > MAX_RESPONSE_BYTES or end > len(value):
            raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG chunk length is invalid.")
        payload = value[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", value[offset + 8 + length : end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(payload, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG chunk CRC mismatch.")
        if not re.fullmatch(rb"[A-Za-z]{4}", chunk_type):
            raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG chunk type is invalid.")
        if chunk_type == b"IEND":
            if length != 0 or end != len(value):
                raise OfficialSourceError(
                    "OFFICIAL_INVALID_BYTES", "PNG has invalid IEND or trailing payload."
                )
            seen_iend = True
        chunks.append((chunk_type, payload))
        offset = end
        if seen_iend:
            break
    if not seen_iend or not chunks or chunks[0][0] != b"IHDR":
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG structure is incomplete.")
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG IHDR is invalid.")
    width, height, bit_depth, colour_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if (
        width < 1
        or height < 1
        or width > 100_000
        or height > 100_000
        or compression != 0
        or filtering != 0
        or interlace != 0
    ):
        raise OfficialSourceError(
            "OFFICIAL_INVALID_BYTES", "PNG geometry or encoding profile is unsupported."
        )
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour_type)
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if channels is None or bit_depth not in valid_depths[colour_type]:
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG colour profile is invalid.")
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not compressed:
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG image data is absent.")
    try:
        decoded = zlib.decompress(compressed)
    except zlib.error as exc:
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG image stream is invalid.") from exc
    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_size = height * (row_bytes + 1)
    if len(decoded) != expected_size:
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG decoded size is inconsistent.")
    if any(decoded[row * (row_bytes + 1)] > 4 for row in range(height)):
        raise OfficialSourceError("OFFICIAL_INVALID_BYTES", "PNG row filter is invalid.")
    return width, height


def _network_failure_code(
    error: TimeoutError | urllib.error.URLError,
    *,
    profile: TransportProfile,
) -> str:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "OFFICIAL_TLS_VERIFICATION_FAILED"
    if isinstance(reason, ssl.SSLError):
        return "OFFICIAL_TLS_HANDSHAKE_FAILED"
    if isinstance(reason, socket.gaierror):
        return "OFFICIAL_DNS_RESOLUTION_FAILED"
    if profile is TransportProfile.ENVIRONMENT_PROXY and isinstance(reason, OSError):
        return "OFFICIAL_PROXY_ROUTE_FAILED"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "OFFICIAL_NETWORK_TIMEOUT"
    return "OFFICIAL_NETWORK_UNAVAILABLE"


def _http_error_code(status_code: int) -> str:
    return {
        401: "OFFICIAL_AUTHENTICATION_REQUIRED",
        403: "OFFICIAL_HTTP_ACCESS_DENIED",
        404: "OFFICIAL_ARTIFACT_UNAVAILABLE",
    }.get(status_code, "OFFICIAL_HTTP_ERROR")


def _provider_access_status(code: str) -> ProviderAccessStatus:
    return {
        "OFFICIAL_AUTHENTICATION_REQUIRED": ProviderAccessStatus.AUTHENTICATION_REQUIRED,
        "OFFICIAL_HTTP_ACCESS_DENIED": ProviderAccessStatus.HTTP_ACCESS_DENIED,
        "OFFICIAL_ARTIFACT_UNAVAILABLE": ProviderAccessStatus.ARTIFACT_UNAVAILABLE,
        "OFFICIAL_TLS_VERIFICATION_FAILED": ProviderAccessStatus.TLS_VERIFICATION_FAILED,
        "OFFICIAL_PROXY_ROUTE_FAILED": ProviderAccessStatus.PROXY_MISCONFIGURED,
        "OFFICIAL_UNEXPECTED_MIME": ProviderAccessStatus.UNEXPECTED_MIME,
        "OFFICIAL_INVALID_BYTES": ProviderAccessStatus.INVALID_BYTES,
        "OFFICIAL_VIEWER_PROTOCOL_UNSUPPORTED": ProviderAccessStatus.UNSUPPORTED_VIEWER_PROTOCOL,
        "OFFICIAL_PARSER_FAILURE": ProviderAccessStatus.PARSER_FAILURE,
    }.get(
        code,
        ProviderAccessStatus.NETWORK_UNAVAILABLE
        if code.startswith(("OFFICIAL_NETWORK_", "OFFICIAL_DNS_", "OFFICIAL_TLS_HANDSHAKE"))
        else ProviderAccessStatus.ACCESS_BLOCKED,
    )


def _exception_chain(error: BaseException) -> tuple[dict[str, str], ...]:
    chain: list[dict[str, str]] = []
    current: BaseException | None = error
    while current is not None and len(chain) < 8:
        item = {"type": type(current).__name__, "message": str(current)[:500]}
        code = getattr(current, "code", None)
        if isinstance(code, str):
            item["code"] = code
        chain.append(item)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def parse_catalog_uuid(value: str) -> UUID:
    """Strict helper used by acquisition commands before persistence."""

    return UUID(value)
