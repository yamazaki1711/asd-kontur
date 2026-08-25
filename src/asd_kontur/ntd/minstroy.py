"""Bounded official Minstroy catalogue client for NTD-SEED-01."""

# ruff: noqa: RUF001 -- official Russian status labels are intentional.

from __future__ import annotations

import hashlib
import html
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Protocol

from .identifiers import NormalizedNormativeIdentifier, NormativeDocumentKind
from .models import CatalogueCandidate, OfficialCatalogueRecord, OfficialHttpMetadata

MINSTROY_HOST = "minstroyrf.gov.ru"
MINSTROY_BASE_URL = f"https://{MINSTROY_HOST}"
MINSTROY_CATALOGUE_PROFILE_VERSION = "minstroy_catalogue_client_v0.1"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_SEARCH_PAGES = 3
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MIN_INTERVAL_SECONDS = 0.25

_CARD_LINK = re.compile(r"^/docs/(?P<id>\d+)(?:/|$)")
_RU_DATE = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})")
_APPROVAL = re.compile(
    r"(?i)(приказ[^«»\n]{0,140}?(?:№\s*)?\d+\s*/\s*пр(?:[^«»\n]{0,40}?\d{2}\.\d{2}\.\d{4})?)"
)
_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


class OfficialCatalogueError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class OfficialResponse:
    metadata: OfficialHttpMetadata
    body: bytes


class OfficialTransport(Protocol):
    def get(self, url: str) -> OfficialResponse: ...


class UrllibOfficialTransport:
    """TLS-verifying, size-bounded official-host-only HTTP transport."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_attempts: int = 2,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes < 1 or not 1 <= max_attempts <= 3:
            raise ValueError("Official transport bounds are invalid")
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_attempts = max_attempts
        self._min_interval = min_interval_seconds
        self._sleep = sleeper
        self._clock = clock
        self._last_request_at: float | None = None

    def get(self, url: str) -> OfficialResponse:
        _require_official_url(url)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._rate_limit()
            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Accept": "text/html,application/pdf,application/octet-stream;q=0.8",
                    "User-Agent": "ASD-KONTUR-NTD-SEED/0.1 (bounded official-source acquisition)",
                },
            )
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self._timeout,
                    context=ssl.create_default_context(),
                ) as response:
                    final_url = response.geturl()
                    _require_official_url(final_url)
                    body = response.read(self._max_response_bytes + 1)
                    if len(body) > self._max_response_bytes:
                        raise OfficialCatalogueError(
                            "OFFICIAL_RESPONSE_TOO_LARGE",
                            "Official response exceeds the configured byte bound.",
                        )
                    headers = response.headers
                    return OfficialResponse(
                        metadata=OfficialHttpMetadata(
                            request_url=url,
                            final_url=final_url,
                            status_code=int(response.status),
                            content_type=headers.get_content_type() if headers else None,
                            etag=headers.get("ETag") if headers else None,
                            last_modified=headers.get("Last-Modified") if headers else None,
                            byte_length=len(body),
                            retrieved_at=datetime.now(UTC),
                        ),
                        body=body,
                    )
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == self._max_attempts:
                    raise OfficialCatalogueError(
                        "OFFICIAL_HTTP_ERROR", f"Official endpoint returned HTTP {exc.code}."
                    ) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise OfficialCatalogueError(
                        "OFFICIAL_ACCESS_BLOCKED",
                        "Official endpoint was unavailable within the bounded retry policy.",
                    ) from exc
            self._sleep(float(2 ** (attempt - 1)))
        raise OfficialCatalogueError(
            "OFFICIAL_ACCESS_BLOCKED", "Official endpoint remained unavailable."
        ) from last_error

    def _rate_limit(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self._min_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()


@dataclass(frozen=True, slots=True)
class CatalogueSearchResult:
    normalized_query: str
    official_endpoints: tuple[str, ...]
    responses: tuple[OfficialHttpMetadata, ...]
    candidates: tuple[CatalogueCandidate, ...]


class MinstroyCatalogueClient:
    """Official discovery/card/download client with exact identifier matching."""

    def __init__(
        self,
        transport: OfficialTransport | None = None,
        *,
        base_url: str = MINSTROY_BASE_URL,
        max_search_pages: int = MAX_SEARCH_PAGES,
    ) -> None:
        _require_official_url(base_url)
        if not 1 <= max_search_pages <= 5:
            raise ValueError("Catalogue pagination must remain bounded")
        self._transport = transport or UrllibOfficialTransport()
        self._base_url = base_url.rstrip("/")
        self._max_search_pages = max_search_pages

    def search_exact(
        self,
        identifier: NormalizedNormativeIdentifier,
        *,
        title_hint: str | None = None,
    ) -> CatalogueSearchResult:
        queries = [identifier.normalized_designation]
        if title_hint and title_hint.strip() and title_hint.strip() not in queries:
            queries.append(f"{identifier.normalized_designation} {title_hint.strip()}")
        endpoints: list[str] = []
        metadata: list[OfficialHttpMetadata] = []
        candidates: dict[str, CatalogueCandidate] = {}
        for query in queries:
            encoded = urllib.parse.quote(query)
            for path in (f"/docs/?q={encoded}", f"/search/?q={encoded}"):
                for page in range(1, self._max_search_pages + 1):
                    separator = "&" if "?" in path else "?"
                    page_path = path if page == 1 else f"{path}{separator}PAGEN_1={page}"
                    endpoint = f"{self._base_url}{page_path}"
                    response = self._transport.get(endpoint)
                    endpoints.append(endpoint)
                    metadata.append(response.metadata)
                    page_candidates = _parse_candidates(response.body, identifier)
                    new_count = 0
                    for candidate in page_candidates:
                        if candidate.catalog_id not in candidates:
                            candidates[candidate.catalog_id] = candidate
                            new_count += 1
                    if new_count == 0:
                        break
        return CatalogueSearchResult(
            normalized_query=identifier.normalized_designation,
            official_endpoints=tuple(endpoints),
            responses=tuple(metadata),
            candidates=tuple(sorted(candidates.values(), key=lambda item: item.catalog_id)),
        )

    def fetch_record(self, candidate: CatalogueCandidate) -> OfficialCatalogueRecord:
        url = urllib.parse.urljoin(f"{self._base_url}/", candidate.catalog_url)
        response = self._transport.get(url)
        parser = _CardParser()
        parser.feed(_decode_html(response.body))
        title = parser.h1.strip() or candidate.title
        text = " ".join(parser.text_parts)
        published_at = _parse_first_date(text)
        artifact_urls = tuple(
            sorted(
                {
                    urllib.parse.urljoin(f"{self._base_url}/", href)
                    for href, label in parser.links
                    if _is_artifact_link(href, label)
                }
            )
        )
        for artifact_url in artifact_urls:
            _require_official_url(artifact_url)
        approval = _APPROVAL.search(text)
        digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
        return OfficialCatalogueRecord(
            catalog_id=candidate.catalog_id,
            catalog_url=url,
            title=title,
            published_at=published_at,
            approving_authority=("Минстрой России" if "Минстрой" in text else None),
            approval_reference=(" ".join(approval.group(1).split()) if approval else None),
            effective_from=None,
            effective_to=None,
            status_text=_extract_status(text),
            artifact_urls=artifact_urls,
            metadata=response.metadata,
            metadata_digest=digest,
        )

    def download_artifact(self, url: str) -> OfficialResponse:
        _require_official_url(url)
        response = self._transport.get(url)
        _validate_artifact_signature(response)
        return response


class _CandidateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._parts).split())))
            self._href = None
            self._parts = []


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_h1 = False
        self._href: str | None = None
        self._link_parts: list[str] = []
        self.h1 = ""
        self.links: list[tuple[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "h1":
            self._in_h1 = True
        elif lowered == "a":
            self._href = dict(attrs).get("href")
            self._link_parts = []

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if clean:
            self.text_parts.append(clean)
            if self._in_h1:
                self.h1 += (" " if self.h1 else "") + clean
            if self._href is not None:
                self._link_parts.append(clean)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "h1":
            self._in_h1 = False
        elif lowered == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._link_parts)))
            self._href = None
            self._link_parts = []


def _parse_candidates(
    body: bytes, identifier: NormalizedNormativeIdentifier
) -> tuple[CatalogueCandidate, ...]:
    parser = _CandidateParser()
    parser.feed(_decode_html(body))
    candidates: dict[str, CatalogueCandidate] = {}
    for href, title in parser.links:
        path = urllib.parse.urlsplit(href).path
        match = _CARD_LINK.match(path)
        if match is None or not title or not _identifier_matches(identifier, title):
            continue
        catalog_id = match.group("id")
        candidates[catalog_id] = CatalogueCandidate(
            catalog_id=catalog_id,
            catalog_url=path,
            title=html.unescape(title),
            matched_designation=identifier.normalized_designation,
        )
    return tuple(candidates.values())


def _identifier_matches(identifier: NormalizedNormativeIdentifier, title: str) -> bool:
    normalized_title = re.sub(r"[\s.№]", "", title).casefold()
    designation = identifier.normalized_designation
    if identifier.document_kind is NormativeDocumentKind.MINSTROY_ORDER:
        number = re.search(r"(\d+)/ПР", designation)
        if number is None or f"{number.group(1)}/пр" not in normalized_title:
            return False
        if identifier.printed_edition is not None:
            return identifier.printed_edition in title
        return True
    comparable = re.sub(r"[\s.]", "", designation).casefold()
    return re.search(rf"(?<!\d){re.escape(comparable)}(?!\d)", normalized_title) is not None


def _decode_html(body: bytes) -> str:
    return body.decode("utf-8", errors="strict")


def _parse_first_date(text: str) -> date | None:
    match = _RU_DATE.search(text)
    if match is not None:
        return date(
            int(match.group("year")),
            _MONTHS[match.group("month").lower()],
            int(match.group("day")),
        )
    numeric = _NUMERIC_DATE.search(text)
    if numeric is not None:
        return date(
            int(numeric.group("year")),
            int(numeric.group("month")),
            int(numeric.group("day")),
        )
    return None


def _extract_status(text: str) -> str | None:
    for status in ("Действует", "Не действует", "Утратил силу", "Отменен"):
        if status.casefold() in text.casefold():
            return status
    return None


def _is_artifact_link(href: str, label: str) -> bool:
    path = urllib.parse.urlsplit(href).path.casefold()
    return "скачать" in label.casefold() or path.endswith((".pdf", ".doc", ".docx", ".rtf", ".zip"))


def _require_official_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {MINSTROY_HOST, f"www.{MINSTROY_HOST}"}:
        raise OfficialCatalogueError(
            "OFFICIAL_ENDPOINT_NOT_ALLOWED", "Only the official Minstroy HTTPS host is allowed."
        )
    if parsed.username is not None or parsed.password is not None:
        raise OfficialCatalogueError(
            "OFFICIAL_ENDPOINT_NOT_ALLOWED", "Credentials in URLs are forbidden."
        )


def _validate_artifact_signature(response: OfficialResponse) -> None:
    content_type = (response.metadata.content_type or "").casefold()
    body = response.body
    if content_type == "application/pdf" or response.metadata.final_url.casefold().endswith(".pdf"):
        if not body.startswith(b"%PDF-"):
            raise OfficialCatalogueError(
                "ARTIFACT_INVALID", "Official artifact declares PDF without a PDF signature."
            )
    elif content_type in {"text/html", "application/xhtml+xml"}:
        stripped = body.lstrip().lower()
        if not (stripped.startswith(b"<!doctype html") or stripped.startswith(b"<html")):
            raise OfficialCatalogueError(
                "ARTIFACT_INVALID", "Official HTML artifact has an invalid signature."
            )
    elif not body:
        raise OfficialCatalogueError("ARTIFACT_INVALID", "Official artifact is empty.")
