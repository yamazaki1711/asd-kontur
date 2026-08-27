"""Bounded official Minstroy catalogue client for NTD-SEED-01."""

# ruff: noqa: RUF001 -- official Russian status labels are intentional.

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from .identifiers import NormalizedNormativeIdentifier, NormativeDocumentKind
from .models import (
    CatalogueCandidate,
    OfficialCatalogueRecord,
    OfficialHttpMetadata,
    OfficialProvider,
)
from .official_sources import (
    BoundedOfficialTransport,
    OfficialSourceError,
    StreamedOfficialSource,
    TransportProfile,
)

MINSTROY_HOST = "minstroyrf.gov.ru"
MINSTROY_BASE_URL = f"https://{MINSTROY_HOST}"
MINSTROY_CATALOGUE_PROFILE_VERSION = "minstroy_catalogue_client_v0.2"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_SEARCH_PAGES = 3
MAX_CATEGORY_PAGES = 64
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
_CATEGORY_BY_KIND = {
    NormativeDocumentKind.MINSTROY_ORDER: "52",
    NormativeDocumentKind.CODE_OF_PRACTICE: "60",
    NormativeDocumentKind.INSTRUCTION: "44",
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

    def stream_to_path(self, url: str, destination: Path) -> StreamedOfficialSource: ...


class UrllibOfficialTransport:
    """Compatibility adapter over the single provider-neutral acquisition transport."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_attempts: int = 2,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        profile: TransportProfile = TransportProfile.DIRECT,
    ) -> None:
        self._delegate = BoundedOfficialTransport(
            OfficialProvider.MINSTROY_CATALOGUE,
            profile=profile,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            max_response_bytes=max_response_bytes,
            min_interval_seconds=min_interval_seconds,
        )

    def get(self, url: str) -> OfficialResponse:
        _require_official_url(url)
        try:
            response = self._delegate.get(url)
        except OfficialSourceError as exc:
            raise OfficialCatalogueError(exc.code, str(exc)) from exc
        return OfficialResponse(response.metadata, response.body)

    def stream_to_path(self, url: str, destination: Path) -> StreamedOfficialSource:
        _require_official_url(url)
        try:
            return self._delegate.stream_to_path(url, destination)
        except OfficialSourceError as exc:
            raise OfficialCatalogueError(exc.code, str(exc)) from exc


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
        max_category_pages: int = MAX_CATEGORY_PAGES,
    ) -> None:
        _require_official_url(base_url)
        if not 1 <= max_search_pages <= 5:
            raise ValueError("Catalogue pagination must remain bounded")
        if not 1 <= max_category_pages <= MAX_CATEGORY_PAGES:
            raise ValueError("Catalogue enumeration bound is invalid")
        self._transport = transport or UrllibOfficialTransport()
        self._base_url = base_url.rstrip("/")
        self._max_search_pages = max_search_pages
        self._max_category_pages = max_category_pages

    def search_exact(
        self,
        identifier: NormalizedNormativeIdentifier,
        *,
        title_hint: str | None = None,
    ) -> CatalogueSearchResult:
        queries = list(_query_variants(identifier, title_hint))
        endpoints: list[str] = []
        metadata: list[OfficialHttpMetadata] = []
        candidates: dict[str, CatalogueCandidate] = {}
        for query in queries:
            encoded = urllib.parse.quote(query)
            path = f"/docs/?q={encoded}"
            for page in range(1, self._max_search_pages + 1):
                page_path = path if page == 1 else f"{path}&PAGEN_1={page}"
                endpoint = f"{self._base_url}{page_path}"
                response = self._transport.get(endpoint)
                endpoints.append(endpoint)
                metadata.append(response.metadata)
                for candidate in _parse_candidates(response.body, identifier):
                    candidates.setdefault(candidate.catalog_id, candidate)
                if page >= min(_last_catalogue_page(response.body), self._max_search_pages):
                    break
            # An exact designation query often returns only amendment cards even
            # when the base document is discoverable by its official title.  Do
            # not terminate discovery until a non-amendment candidate is found.
            if any(not is_amendment_candidate(candidate) for candidate in candidates.values()):
                break
        if not candidates and identifier.document_kind in _CATEGORY_BY_KIND:
            category = _CATEGORY_BY_KIND[identifier.document_kind]
            path = f"/docs/?t%5B0%5D={category}"
            first_endpoint = f"{self._base_url}{path}"
            first = self._transport.get(first_endpoint)
            endpoints.append(first_endpoint)
            metadata.append(first.metadata)
            last_page = _last_catalogue_page(first.body)
            if last_page > self._max_category_pages:
                raise OfficialCatalogueError(
                    "CATALOGUE_ENUMERATION_BOUND_EXCEEDED",
                    f"Official category reports {last_page} pages; bound is "
                    f"{self._max_category_pages}.",
                )
            for candidate in _parse_candidates(first.body, identifier):
                candidates.setdefault(candidate.catalog_id, candidate)
            for page in range(2, last_page + 1):
                endpoint = f"{self._base_url}{path}&PAGEN_1={page}"
                response = self._transport.get(endpoint)
                endpoints.append(endpoint)
                metadata.append(response.metadata)
                for candidate in _parse_candidates(response.body, identifier):
                    candidates.setdefault(candidate.catalog_id, candidate)
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
                    _canonical_official_url(urllib.parse.urljoin(f"{self._base_url}/", href))
                    for href, label in (
                        *parser.links,
                        *((href, "Скачать") for href in candidate.catalogue_artifact_urls),
                    )
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
        canonical_url = _canonical_official_url(url)
        _require_official_url(canonical_url)
        response = self._transport.get(canonical_url)
        _validate_artifact_signature(response)
        return response

    def download_artifact_to_path(self, url: str, destination: Path) -> StreamedOfficialSource:
        canonical_url = _canonical_official_url(url)
        _require_official_url(canonical_url)
        if not hasattr(self._transport, "stream_to_path"):
            raise OfficialCatalogueError(
                "OFFICIAL_STREAMING_UNSUPPORTED",
                "Configured official transport has no streaming acquisition capability.",
            )
        result = self._transport.stream_to_path(canonical_url, destination)
        with result.path.open("rb") as stream:
            header = stream.read(4096)
        _validate_artifact_header(
            final_url=result.metadata.final_url,
            content_type=result.metadata.content_type,
            header=header,
            byte_length=result.byte_length,
        )
        return result


class _CandidateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._item_depth: int | None = None
        self._item_links: list[tuple[str, str]] = []
        self.item_link_groups: list[tuple[tuple[str, str], ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = dict(attrs)
        if lowered == "div":
            classes = set((attributes.get("class") or "").split())
            if self._item_depth is None and "item-wrap" in classes:
                self._item_depth = 1
                self._item_links = []
            elif self._item_depth is not None:
                self._item_depth += 1
        if lowered == "a":
            self._href = attributes.get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            link = (self._href, " ".join(" ".join(self._parts).split()))
            self.links.append(link)
            if self._item_depth is not None:
                self._item_links.append(link)
            self._href = None
            self._parts = []
        elif tag.lower() == "div" and self._item_depth is not None:
            self._item_depth -= 1
            if self._item_depth == 0:
                self.item_link_groups.append(tuple(self._item_links))
                self._item_depth = None
                self._item_links = []


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_h1 = False
        self._href: str | None = None
        self._link_parts: list[str] = []
        self._main_actions_depth: int | None = None
        self.h1 = ""
        self.links: list[tuple[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = dict(attrs)
        if lowered == "div":
            classes = set((attributes.get("class") or "").split())
            if self._main_actions_depth is None and "actions-panel-box" in classes:
                self._main_actions_depth = 1
            elif self._main_actions_depth is not None:
                self._main_actions_depth += 1
        if lowered == "h1":
            self._in_h1 = True
        elif lowered == "a":
            self._href = attributes.get("href") if self._main_actions_depth is not None else None
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
        elif lowered == "div" and self._main_actions_depth is not None:
            self._main_actions_depth -= 1
            if self._main_actions_depth == 0:
                self._main_actions_depth = None


def _parse_candidates(
    body: bytes, identifier: NormalizedNormativeIdentifier
) -> tuple[CatalogueCandidate, ...]:
    parser = _CandidateParser()
    parser.feed(_decode_html(body))
    candidates: dict[str, CatalogueCandidate] = {}
    groups = parser.item_link_groups or tuple((link,) for link in parser.links)
    for group in groups:
        artifact_urls = tuple(
            dict.fromkeys(href for href, label in group if _is_artifact_link(href, label))
        )
        for href, title in group:
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
                catalogue_artifact_urls=artifact_urls,
            )
    return tuple(candidates.values())


def _identifier_matches(identifier: NormalizedNormativeIdentifier, title: str) -> bool:
    normalized_title = _catalogue_text_key(title)
    designation = identifier.normalized_designation
    if identifier.document_kind is NormativeDocumentKind.MINSTROY_ORDER:
        number = re.search(r"(\d+)/ПР", designation)
        if number is None or f"{number.group(1)}/пр" not in normalized_title:
            return False
        if identifier.printed_edition is not None:
            parsed = _parse_first_date(title)
            return parsed is not None and parsed.strftime("%d.%m.%Y") == identifier.printed_edition
        return True
    comparable = _catalogue_text_key(designation)
    return re.search(rf"(?<!\d){re.escape(comparable)}(?!\d)", normalized_title) is not None


def _catalogue_text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value).replace("№", "")).casefold()
    normalized = re.sub(r"[\u2010-\u2015\u2212]", "-", normalized)
    return re.sub(r"[\s№]", "", normalized)


def _query_variants(
    identifier: NormalizedNormativeIdentifier, title_hint: str | None
) -> tuple[str, ...]:
    values = [identifier.normalized_designation]
    if identifier.document_kind is NormativeDocumentKind.MINSTROY_ORDER:
        number = re.search(r"(\d+)/ПР", identifier.normalized_designation)
        if number is not None:
            values.append(f"{number.group(1)}/пр")
    if title_hint and title_hint.strip():
        values.append(title_hint.strip())
    return tuple(dict.fromkeys(values))


def _last_catalogue_page(body: bytes) -> int:
    text = _decode_html(body)
    pages = [int(value) for value in re.findall(r"PAGEN_1=(\d+)", html.unescape(text))]
    return max(pages, default=1)


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


def is_amendment_candidate(candidate: CatalogueCandidate) -> bool:
    title = _catalogue_text_key(candidate.title)
    return re.match(r"^изменение\d+к", title) is not None or "овнесенииизменений" in title


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


def _canonical_official_url(url: str) -> str:
    """Encode an official IRI as a transport-safe URI without changing semantics."""

    parsed = urllib.parse.urlsplit(url)
    _require_official_url(url)
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&;%:@!$'()*+,/?-._~")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))


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


def _validate_artifact_header(
    *, final_url: str, content_type: str | None, header: bytes, byte_length: int
) -> None:
    if byte_length < 1:
        raise OfficialCatalogueError("ARTIFACT_INVALID", "Official artifact is empty.")
    declared = (content_type or "").casefold()
    if declared == "application/pdf" or final_url.casefold().endswith(".pdf"):
        if not header.startswith(b"%PDF-"):
            raise OfficialCatalogueError(
                "ARTIFACT_INVALID", "Official artifact declares PDF without a PDF signature."
            )
    elif declared in {"text/html", "application/xhtml+xml"}:
        stripped = header.lstrip().lower()
        if not (stripped.startswith(b"<!doctype html") or stripped.startswith(b"<html")):
            raise OfficialCatalogueError(
                "ARTIFACT_INVALID", "Official HTML artifact has an invalid signature."
            )
