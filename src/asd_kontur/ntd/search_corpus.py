"""Build the consultant's searchable NTD corpus from already admitted bytes.

The index is a read model.  It does not publish normative provisions, activate
editions, or grant recovered legacy files normative authority.
"""

# ruff: noqa: E501, RUF001 -- SQL and Russian normative designations stay readable.

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.native import NativeExtractionFailure, inspect_pdf_path
from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.file_processing import render_normative_pdf_page

NTD_SEARCH_INDEX_PROFILE = "ntd-consultant-search-index@1.0.0"
NTD_SEARCH_OCR_PROFILE = "apple-vision-accurate-page-search@1.0.0"


@dataclass(frozen=True, slots=True)
class NtdSearchBuildResult:
    official_denominator: int
    reference_denominator: int
    document_count: int
    searchable_document_count: int
    partially_searchable_document_count: int
    document_without_text_count: int
    page_count: int
    searchable_page_count: int
    build_fingerprint: str


def build_ntd_search_corpus(
    engine: Engine,
    *,
    object_store_root: Path,
    reference_manifest: Path | None = None,
    apple_vision_executable: Path | None = None,
    ocr_workers: int = 4,
) -> NtdSearchBuildResult:
    """Index admitted official artifacts and optional recovered reference bytes."""

    if not object_store_root.is_absolute() or not object_store_root.is_dir():
        raise ValueError("ntd_search_object_store_invalid")
    if apple_vision_executable is not None and (
        not apple_vision_executable.is_absolute()
        or not apple_vision_executable.is_file()
        or apple_vision_executable.is_symlink()
    ):
        raise ValueError("ntd_search_ocr_executable_invalid")
    if not 1 <= ocr_workers <= 8:
        raise ValueError("ntd_search_ocr_workers_invalid")
    manifest_digest: str | None = None
    reference_assets: list[dict[str, Any]] = []
    if reference_manifest is not None:
        if not reference_manifest.is_absolute() or not reference_manifest.is_file():
            raise ValueError("ntd_search_reference_manifest_invalid")
        manifest_bytes = reference_manifest.read_bytes()
        manifest_digest = _digest(manifest_bytes)
        parsed = json.loads(manifest_bytes)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("assets"), list):
            raise ValueError("ntd_search_reference_manifest_schema_invalid")
        reference_assets = [dict(item) for item in parsed["assets"]]

    with engine.begin() as connection:
        official = list(
            connection.execute(
                sa.text(
                    "SELECT d.normative_document_id,d.designation,d.title,"
                    "e.normative_edition_id,e.edition_label,e.effective_from,e.effective_to,"
                    "a.normative_artifact_id,a.source_version_id,a.content_digest,a.size_bytes,"
                    "a.official_url,sv.object_id,"
                    "(SELECT count(*) FROM platform.normative_structural_fragments f "
                    " WHERE f.source_version_id=a.source_version_id) structured_fragment_count,"
                    "(SELECT count(*) FROM platform.normative_provision_versions p "
                    " WHERE p.source_version_id=a.source_version_id AND p.verification_status='verified') "
                    "verified_provision_count,"
                    "(SELECT count(DISTINCT rp.page_index) FROM platform.normative_representation_pages rp "
                    " WHERE rp.source_version_id=a.source_version_id) inventoried_page_count "
                    "FROM platform.normative_artifacts a "
                    "JOIN platform.normative_editions e ON e.normative_edition_id=a.normative_edition_id "
                    "JOIN platform.normative_documents d ON d.normative_document_id=e.normative_document_id "
                    "JOIN platform.source_versions sv ON sv.source_version_id=a.source_version_id "
                    "ORDER BY d.designation,a.registered_at"
                )
            ).mappings()
        )
        documents: list[dict[str, Any]] = []
        for row in official:
            object_path = object_store_root / "platform" / "source" / str(row["object_id"])
            documents.append(
                _index_official(
                    connection,
                    dict(row),
                    object_path=object_path,
                    apple_vision_executable=apple_vision_executable,
                    ocr_workers=ocr_workers,
                )
            )
        for asset in reference_assets:
            documents.append(
                _index_reference(
                    connection,
                    asset,
                    manifest_digest=manifest_digest,
                )
            )

        counters = _counters(documents)
        receipt_payload = {
            "profile_version": NTD_SEARCH_INDEX_PROFILE,
            "official_denominator": len(official),
            "reference_denominator": len(reference_assets),
            **counters,
            "source_manifest_digests": {
                "reference_staging_manifest": manifest_digest,
                "official_source_ledger": semantic_digest(
                    [str(item["content_digest"]) for item in official]
                ),
                "ocr_executable": (
                    _file_digest(apple_vision_executable)
                    if apple_vision_executable is not None
                    else None
                ),
            },
            "documents": [item["document_fingerprint"] for item in documents],
        }
        fingerprint = semantic_digest(receipt_payload)
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_search_index_build_receipts("
                "build_receipt_id,profile_version,official_denominator,reference_denominator,"
                "document_count,searchable_document_count,partially_searchable_document_count,"
                "document_without_text_count,page_count,searchable_page_count,"
                "source_manifest_digests,build_fingerprint) VALUES ("
                ":id,:profile,:official,:reference,:documents,:searchable,:partial,:without_text,"
                ":pages,:searchable_pages,CAST(:manifests AS jsonb),:fingerprint) "
                "ON CONFLICT (build_fingerprint) DO NOTHING"
            ),
            {
                "id": deterministic_uuid(f"ntd-search-build:{fingerprint}"),
                "profile": NTD_SEARCH_INDEX_PROFILE,
                "official": len(official),
                "reference": len(reference_assets),
                "documents": counters["document_count"],
                "searchable": counters["searchable_document_count"],
                "partial": counters["partially_searchable_document_count"],
                "without_text": counters["document_without_text_count"],
                "pages": counters["page_count"],
                "searchable_pages": counters["searchable_page_count"],
                "manifests": json.dumps(receipt_payload["source_manifest_digests"]),
                "fingerprint": fingerprint,
            },
        )
    return NtdSearchBuildResult(
        len(official),
        len(reference_assets),
        counters["document_count"],
        counters["searchable_document_count"],
        counters["partially_searchable_document_count"],
        counters["document_without_text_count"],
        counters["page_count"],
        counters["searchable_page_count"],
        fingerprint,
    )


def _index_official(
    connection: sa.Connection,
    row: dict[str, Any],
    *,
    object_path: Path,
    apple_vision_executable: Path | None,
    ocr_workers: int,
) -> dict[str, Any]:
    expected_digest = str(row["content_digest"])
    bytes_present = object_path.is_file() and not object_path.is_symlink()
    if bytes_present:
        if _file_digest(object_path) != expected_digest or object_path.stat().st_size != int(
            row["size_bytes"]
        ):
            raise ValueError("ntd_search_official_bytes_mismatch")
    pages = (
        _extract_pages(
            object_path,
            document_id=UUID(str(row["normative_document_id"])),
            source_version_id=UUID(str(row["source_version_id"])),
        )
        if bytes_present
        else []
    )
    native_text_characters = sum(len(page) for page in pages)
    ocr_applied = False
    ocr_page_count = 0
    ocr_text_characters = 0
    if apple_vision_executable is not None and pages and any(not page.strip() for page in pages):
        pages, ocr_applied, ocr_page_count, ocr_text_characters = _ocr_missing_pages(
            object_path,
            pages,
            executable=apple_vision_executable,
            workers=ocr_workers,
        )
    aliases = designation_aliases(str(row["designation"]))
    structured = int(row["structured_fragment_count"])
    verified = int(row["verified_provision_count"])
    return _persist_document(
        connection,
        authority_class="official",
        identity=f"official:{row['normative_artifact_id']}",
        normative_document_id=row["normative_document_id"],
        normative_edition_id=row["normative_edition_id"],
        normative_artifact_id=row["normative_artifact_id"],
        source_version_id=row["source_version_id"],
        designation=str(row["designation"]),
        aliases=aliases,
        title=str(row["title"]),
        edition_label=str(row["edition_label"]),
        artifact_digest=expected_digest,
        bytes_present=bytes_present,
        inventoried_page_count=int(row["inventoried_page_count"]),
        pages=pages,
        native_text_characters=native_text_characters,
        ocr_page_count=ocr_page_count,
        ocr_text_characters=ocr_text_characters,
        structured=structured,
        verified=verified,
        origin_manifest_digest=None,
        href=f"/api/v1/platform/sources/{row['source_version_id']}/content",
        extraction_method=(
            "admitted_native_plus_ocr_pdf" if ocr_applied else "admitted_native_pdf"
        ),
        source_metadata={
            "official_url": str(row["official_url"]),
            "effective_from": str(row["effective_from"]) if row["effective_from"] else None,
            "effective_to": str(row["effective_to"]) if row["effective_to"] else None,
            "authority_statement": "official_source_artifact",
            "text_extraction": (
                NTD_SEARCH_OCR_PROFILE if ocr_applied else "admitted-native-pdf@1.0.0"
            ),
        },
    )


def _index_reference(
    connection: sa.Connection,
    asset: dict[str, Any],
    *,
    manifest_digest: str | None,
) -> dict[str, Any]:
    digest = str(asset.get("sha256", ""))
    path_value = asset.get("staged_object_path")
    path = Path(str(path_value)) if path_value else Path("/__missing__")
    bytes_present = path.is_absolute() and path.is_file() and not path.is_symlink()
    if bytes_present:
        if _file_digest(path) != digest or path.stat().st_size != int(asset.get("byte_length", 0)):
            raise ValueError("ntd_search_reference_bytes_mismatch")
    designation = str(
        asset.get("probable_edition_identity")
        or asset.get("probable_document_identity")
        or "Неопознанный нормативный документ"
    )
    identity = f"legacy-reference:{digest}"
    pages = (
        _extract_pages(
            path,
            document_id=deterministic_uuid(identity),
            source_version_id=deterministic_uuid(f"{identity}:source"),
        )
        if bytes_present and str(asset.get("detected_mime_type")) == "application/pdf"
        else []
    )
    return _persist_document(
        connection,
        authority_class="legacy_reference",
        identity=identity,
        normative_document_id=None,
        normative_edition_id=None,
        normative_artifact_id=None,
        source_version_id=None,
        designation=designation,
        aliases=designation_aliases(designation),
        title=str(asset.get("probable_document_identity") or designation),
        edition_label=str(asset.get("probable_edition_identity") or "") or None,
        artifact_digest=digest,
        bytes_present=bytes_present,
        inventoried_page_count=int(asset.get("page_count") or 0),
        pages=pages,
        native_text_characters=sum(len(page) for page in pages),
        ocr_page_count=0,
        ocr_text_characters=0,
        structured=0,
        verified=0,
        origin_manifest_digest=manifest_digest,
        href=None,
        extraction_method="recovered_legacy_native_pdf",
        source_metadata={
            "recovery_state": str(asset.get("state", "unknown")),
            "authority_statement": "legacy_reference_not_active_authority",
            "detected_mime_type": str(asset.get("detected_mime_type", "")),
        },
    )


def _extract_pages(path: Path, *, document_id: UUID, source_version_id: UUID) -> list[str]:
    try:
        native = inspect_pdf_path(
            path=path,
            document_id=document_id,
            document_version=1,
            source_version_id=source_version_id,
        )
    except NativeExtractionFailure:
        return []
    return [
        "\n".join(
            element.raw_text.strip()
            for element in sorted(page.elements, key=lambda value: value.reading_order)
            if element.raw_text.strip()
        )
        for page in native.pages
    ]


def _ocr_missing_pages(
    path: Path,
    pages: list[str],
    *,
    executable: Path,
    workers: int,
) -> tuple[list[str], bool, int, int]:
    """OCR only pages with no usable native text, preserving one-based page identity."""

    missing = [index for index, text in enumerate(pages, start=1) if not text.strip()]
    if not missing:
        return pages, False, 0, 0

    def extract(page_number: int) -> tuple[int, str]:
        rendered = render_normative_pdf_page(
            path,
            page_index=page_number,
            source_rotation_degrees=0,
        )
        with tempfile.NamedTemporaryFile(prefix="asd-ntd-ocr-", suffix=".png") as image:
            image.write(rendered.png_bytes)
            image.flush()
            completed = subprocess.run(
                [str(executable), image.name],
                capture_output=True,
                check=False,
                timeout=180,
            )
        if completed.returncode != 0 or len(completed.stdout) > 16 * 1024 * 1024:
            return page_number, ""
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return page_number, ""
        observations = value.get("observations") if isinstance(value, dict) else None
        if not isinstance(observations, list):
            return page_number, ""
        text = "\n".join(
            str(item.get("text", "")).strip()
            for item in observations
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        )
        return page_number, text

    result = list(pages)
    ocr_page_count = 0
    ocr_text_characters = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ntd-ocr") as pool:
        for page_number, text in pool.map(extract, missing):
            if text:
                result[page_number - 1] = text
                ocr_page_count += 1
                ocr_text_characters += len(text)
    return result, True, ocr_page_count, ocr_text_characters


def _persist_document(
    connection: sa.Connection,
    *,
    authority_class: str,
    identity: str,
    normative_document_id: Any,
    normative_edition_id: Any,
    normative_artifact_id: Any,
    source_version_id: Any,
    designation: str,
    aliases: list[str],
    title: str,
    edition_label: str | None,
    artifact_digest: str,
    bytes_present: bool,
    inventoried_page_count: int,
    pages: list[str],
    native_text_characters: int,
    ocr_page_count: int,
    ocr_text_characters: int,
    structured: int,
    verified: int,
    origin_manifest_digest: str | None,
    href: str | None,
    extraction_method: str,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    search_document_id = deterministic_uuid(f"ntd-search-document:{identity}")
    searchable_pages = sum(bool(page.strip()) for page in pages)
    page_count = max(inventoried_page_count, len(pages))
    if searchable_pages == 0:
        text_status = "none"
        search_status = "not_searchable"
    elif searchable_pages < page_count:
        text_status = "partial"
        search_status = "partially_searchable"
    else:
        text_status = "complete"
        search_status = "searchable"
    structure_status = (
        "verified_provisions" if verified else "structured" if structured else "not_structured"
    )
    payload = {
        "profile": NTD_SEARCH_INDEX_PROFILE,
        "identity": identity,
        "artifact_digest": artifact_digest,
        "page_text_digests": [_digest(page.encode()) for page in pages],
        "statuses": [bytes_present, page_count, text_status, search_status, structure_status],
    }
    fingerprint = semantic_digest(payload)
    search_text = " ".join([designation, *aliases, title])
    connection.execute(
        sa.text(
            "INSERT INTO platform.ntd_search_documents("
            "search_document_id,version,authority_class,normative_document_id,normative_edition_id,"
            "normative_artifact_id,source_version_id,stable_designation,normalized_designation,"
            "alternative_designations,title,edition_label,artifact_digest,bytes_status,"
            "page_inventory_status,text_status,search_status,structure_status,edition_currency_status,"
            "page_count,searchable_page_count,native_text_characters,structured_fragment_count,"
            "ocr_page_count,ocr_text_characters,verified_provision_count,origin_manifest_digest,"
            "source_access_href,source_metadata,"
            "index_profile_version,document_fingerprint,search_text) VALUES ("
            ":id,1,:authority,:document_id,:edition_id,:artifact_id,:source_version_id,:designation,"
            ":normalized,:aliases,:title,:edition_label,:digest,:bytes_status,:inventory_status,"
            ":text_status,:search_status,:structure_status,'not_checked',:page_count,:searchable_pages,"
            ":characters,:structured,:ocr_pages,:ocr_characters,:verified,:manifest,:href,"
            "CAST(:metadata AS jsonb),:profile,"
            ":fingerprint,:search_text) ON CONFLICT (document_fingerprint) DO NOTHING"
        ),
        {
            "id": search_document_id,
            "authority": authority_class,
            "document_id": normative_document_id,
            "edition_id": normative_edition_id,
            "artifact_id": normative_artifact_id,
            "source_version_id": source_version_id,
            "designation": designation,
            "normalized": normalize_designation(designation),
            "aliases": aliases,
            "title": title,
            "edition_label": edition_label,
            "digest": artifact_digest,
            "bytes_status": "present" if bytes_present else "missing",
            "inventory_status": "inventoried" if page_count else "not_inventory",
            "text_status": text_status,
            "search_status": search_status,
            "structure_status": structure_status,
            "page_count": page_count,
            "searchable_pages": searchable_pages,
            "characters": native_text_characters,
            "structured": structured,
            "ocr_pages": ocr_page_count,
            "ocr_characters": ocr_text_characters,
            "verified": verified,
            "manifest": origin_manifest_digest,
            "href": href,
            "metadata": json.dumps(source_metadata, ensure_ascii=False),
            "profile": NTD_SEARCH_INDEX_PROFILE,
            "fingerprint": fingerprint,
            "search_text": search_text,
        },
    )
    for page_number, text in enumerate(pages, start=1):
        digest = _digest(text.encode())
        locator_id: UUID | None = None
        if source_version_id is not None:
            locator_id = deterministic_uuid(f"ntd-search-page:{source_version_id}:{page_number}")
            connection.execute(
                sa.text(
                    "INSERT INTO platform.source_locators(source_locator_id,source_version_id,"
                    "locator_kind,locator_key,locator_value,fragment_digest) VALUES ("
                    ":id,:source,'normative_search_page',:key,CAST(:value AS jsonb),:digest) "
                    "ON CONFLICT (source_version_id,locator_kind,locator_key) DO NOTHING"
                ),
                {
                    "id": locator_id,
                    "source": source_version_id,
                    "key": f"page:{page_number}",
                    "value": json.dumps({"page_number": page_number}),
                    "digest": digest,
                },
            )
        page_fingerprint = semantic_digest(
            {"document": str(search_document_id), "page": page_number, "digest": digest}
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_search_pages(search_document_id,search_document_version,"
                "page_number,source_locator_id,page_text,page_text_digest,text_status,extraction_method,"
                "page_fingerprint) VALUES (:document,1,:page,:locator,:text,:digest,:status,:method,"
                ":fingerprint) ON CONFLICT (page_fingerprint) DO NOTHING"
            ),
            {
                "document": search_document_id,
                "page": page_number,
                "locator": locator_id,
                "text": text,
                "digest": digest,
                "status": "searchable" if text.strip() else "no_text",
                "method": extraction_method,
                "fingerprint": page_fingerprint,
            },
        )
    return {
        "document_fingerprint": fingerprint,
        "search_status": search_status,
        "page_count": page_count,
        "searchable_page_count": searchable_pages,
    }


def normalize_designation(value: str) -> str:
    normalized = re.sub(r"[^0-9а-яa-z]", "", value.casefold().replace("ё", "е"))
    for latin, cyrillic in (("gost", "гост"), ("snip", "снип"), ("sp", "сп")):
        if normalized.startswith(latin):
            normalized = cyrillic + normalized[len(latin) :]
            break
    return normalized


def designation_aliases(designation: str) -> list[str]:
    """Return designation spellings; inventory resolution owns ambiguity."""

    compact = re.sub(r"\s+", "", designation)
    aliases = {designation, compact}
    match = re.search(
        r"\b(СП|SP|ГОСТ(?:\s+Р)?|GOST(?:\s+R)?)\s*"
        r"([0-9]+(?:\.[0-9]+)*(?:-[0-9]+)?)",
        designation,
        re.I,
    )
    if match:
        raw_prefix = " ".join(match.group(1).upper().split())
        normalized_prefix = normalize_designation(raw_prefix)
        prefix_variants = {
            "сп": ("СП", "SP"),
            "гост": ("ГОСТ", "GOST"),
            "гостр": ("ГОСТ Р", "GOST R"),
        }.get(normalized_prefix, (raw_prefix,))
        number = match.group(2)
        aliases.add(number)
        number_variants = {number, number.split(".")[0], number.split("-", maxsplit=1)[0]}
        components = number.split(".")
        if len(components) >= 3:
            number_variants.add(".".join(components[:2]))
        for prefix in prefix_variants:
            compact_prefix = prefix.replace(" ", "")
            for number_variant in number_variants:
                aliases.add(f"{prefix} {number_variant}")
                aliases.add(f"{compact_prefix}{number_variant}")
    gesn = re.search(r"\b(ГЭСНм?|GESNm?)\s*81-0[23]-([0-9]+)(?:-[0-9]{4})?", designation, re.I)
    if gesn:
        prefix = "ГЭСНм" if gesn.group(1).casefold().endswith("m") else "ГЭСН"
        collection = gesn.group(2)
        aliases.update(
            {
                f"{prefix} {collection}",
                f"{prefix}{collection}",
                f"{prefix} 81-02-{collection}",
                f"{prefix}81-02-{collection}",
            }
        )
    return sorted(alias for alias in aliases if alias)


_designation_aliases = designation_aliases


def _counters(documents: Iterable[dict[str, Any]]) -> dict[str, int]:
    values = list(documents)
    return {
        "document_count": len(values),
        "searchable_document_count": sum(v["search_status"] == "searchable" for v in values),
        "partially_searchable_document_count": sum(
            v["search_status"] == "partially_searchable" for v in values
        ),
        "document_without_text_count": sum(v["search_status"] == "not_searchable" for v in values),
        "page_count": sum(int(v["page_count"]) for v in values),
        "searchable_page_count": sum(int(v["searchable_page_count"]) for v in values),
    }


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return "sha256:" + value.hexdigest()
