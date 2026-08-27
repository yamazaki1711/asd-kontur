"""Run one idempotent Polza canary for an admitted public normative raster page."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.harness.models import digest_of
from asd_kontur.ntd.file_processing import (
    NTD_REPRESENTATION_INVENTORY_VERSION,
    RepresentationPage,
    render_normative_pdf_page,
    render_normative_pdf_region,
)
from asd_kontur.ntd.polza import (
    POLZA_PROFILE_VERSION,
    POLZA_PROMPT_VERSION,
    POLZA_REGION_PROFILE_VERSION,
    POLZA_ROTATED_REGION_PROFILE_VERSION,
    PolzaExtractionError,
    PolzaPageRequest,
    PolzaPublicNtdPageExtractor,
    polza_profile_version,
    polza_request_digest,
    polza_schema_version,
)
from asd_kontur.ntd.remediation import NtdRemediationRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--designation", required=True)
    parser.add_argument("--page-index", type=int, required=True)
    parser.add_argument(
        "--source-region",
        help="Normalized x0,y0,x1,y1 crop for damaged-native/mixed/table canaries",
    )
    arguments = parser.parse_args()
    _require_private_directory(arguments.object_root)
    _require_private_directory(arguments.receipt_dir)
    engine = sa.create_engine(arguments.database_url)
    repository = NtdRemediationRepository(engine)
    page: dict[str, Any] | None = None
    page_version: int | None = None
    render_digest: str | None = None
    request_digest: str | None = None
    source_region = _parse_source_region(arguments.source_region)
    provider_profile_version = (
        POLZA_REGION_PROFILE_VERSION if source_region is not None else POLZA_PROFILE_VERSION
    )
    try:
        page = _load_page(engine, arguments.designation, arguments.page_index)
        if source_region is not None and int(page["rotation_degrees"]) != 0:
            provider_profile_version = POLZA_ROTATED_REGION_PROFILE_VERSION
        _require_route(page, source_region)
        source_path = _source_path(arguments.object_root, UUID(str(page["object_id"])))
        _verify_source_bytes(source_path, str(page["content_digest"]))
        if source_region is None:
            rendered = render_normative_pdf_page(
                source_path,
                page_index=int(page["page_index"]),
                source_rotation_degrees=int(page["rotation_degrees"]),
            )
        else:
            rendered = render_normative_pdf_region(
                source_path,
                page_index=int(page["page_index"]),
                source_rotation_degrees=int(page["rotation_degrees"]),
                source_width_points=Decimal(str(page["width_points"])),
                source_height_points=Decimal(str(page["height_points"])),
                source_region=source_region,
            )
        render_digest = rendered.render_digest
        rendered_page = _rendered_page_version(
            page,
            rendered.render_digest,
            "failed",
            provider_profile_version=provider_profile_version,
        )
        request = _polza_request(
            page,
            rendered_page,
            rendered.png_bytes,
            source_region=source_region,
            render_to_source=(
                rendered.render_to_source
                if source_region is not None and int(page["rotation_degrees"]) != 0
                else None
            ),
        )
        request_digest = polza_request_digest(request)
        schema_version = polza_schema_version(request)
        profile_version = polza_profile_version(request)
        existing = repository.find_external_page_candidate(
            normative_page_id=rendered_page.page_id,
            normative_page_version=None,
            provider_profile_version=profile_version,
            prompt_version=POLZA_PROMPT_VERSION,
            schema_version=schema_version,
            request_digest=request_digest,
        )
        if existing is not None:
            _print_safe_result(
                page, int(page["version"]), rendered.render_digest, existing, reused=True
            )
            return 0
        # A page request can legitimately require more than two minutes.  Outcome-unknown
        # transport timeouts are never retried because a completed provider execution could
        # otherwise be paid for twice.
        extractor = PolzaPublicNtdPageExtractor(timeout_seconds=240, max_retries=0)
        if not extractor.credential_available():
            _write_failure_receipt(
                arguments.receipt_dir,
                page,
                int(page["version"]),
                rendered.render_digest,
                "POLZA_CREDENTIAL_UNAVAILABLE",
                provider_profile_version=provider_profile_version,
            )
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "failure_code": "POLZA_CREDENTIAL_UNAVAILABLE",
                        "designation": page["designation"],
                        "page_index": page["page_index"],
                        "render_digest": rendered.render_digest,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        if source_region is None:
            repository.record_representation_pages(
                normative_artifact_id=UUID(str(page["normative_artifact_id"])),
                source_version_id=UUID(str(page["source_version_id"])),
                pages=(rendered_page,),
                recorded_at=datetime.now(UTC),
            )
            page_version = _latest_page_version(engine, rendered_page.page_id)
        else:
            page_version = int(page["version"])
        candidate = extractor.extract(request)
        repository.record_external_page_candidate(
            normative_page_id=rendered_page.page_id,
            normative_page_version=page_version,
            candidate=candidate,
            recorded_at=datetime.now(UTC),
        )
        stored = repository.find_external_page_candidate(
            normative_page_id=rendered_page.page_id,
            normative_page_version=page_version,
            provider_profile_version=profile_version,
            prompt_version=POLZA_PROMPT_VERSION,
            schema_version=schema_version,
            request_digest=candidate.request_digest,
        )
        if stored is None:
            raise RuntimeError("POLZA_CANDIDATE_RECEIPT_NOT_PERSISTED")
        if source_region is None:
            complete_page = _rendered_page_version(
                page,
                rendered.render_digest,
                "recovery_complete",
                provider_profile_version=provider_profile_version,
            )
            repository.record_representation_pages(
                normative_artifact_id=UUID(str(page["normative_artifact_id"])),
                source_version_id=UUID(str(page["source_version_id"])),
                pages=(complete_page,),
                recorded_at=datetime.now(UTC),
            )
        _print_safe_result(page, page_version, rendered.render_digest, stored, reused=False)
        return 0
    except PolzaExtractionError as error:
        if page is not None and render_digest is not None:
            _write_failure_receipt(
                arguments.receipt_dir,
                page,
                page_version if page_version is not None else int(page["version"]),
                render_digest,
                error.code,
                provider_profile_version=provider_profile_version,
                request_digest=error.request_digest or request_digest,
                response_digest=error.response_digest,
                provider_request_id=error.provider_request_id,
            )
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "failure_code": error.code,
                    "request_digest": error.request_digest or request_digest,
                    "response_digest": error.response_digest,
                },
                sort_keys=True,
            )
        )
        return 2
    finally:
        engine.dispose()


def _load_page(engine: sa.Engine, designation: str, page_index: int) -> dict[str, Any]:
    if page_index < 1:
        raise ValueError("NTD_POLZA_PAGE_INDEX_INVALID")
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT nd.designation_namespace,nd.designation,ne.normative_edition_id,"
                    "na.normative_artifact_id,na.content_digest,sv.source_version_id,o.object_id,"
                    "p.normative_page_id,p.version,p.page_index,p.printed_page_label,"
                    "p.representation_kind,p.width_points,p.height_points,p.rotation_degrees,"
                    "p.native_text_character_count,p.native_text_coverage,p.extraction_route,"
                    "p.terminal_outcome FROM platform.normative_documents nd "
                    "JOIN platform.normative_editions ne ON "
                    "ne.normative_document_id=nd.normative_document_id "
                    "JOIN platform.normative_artifacts na ON "
                    "na.normative_edition_id=ne.normative_edition_id "
                    "JOIN platform.source_versions sv ON sv.source_version_id=na.source_version_id "
                    "JOIN platform.objects o ON o.object_id=sv.object_id "
                    "AND o.object_version=sv.object_version "
                    "JOIN LATERAL (SELECT page.* FROM platform.normative_representation_pages page "
                    "WHERE page.normative_artifact_id=na.normative_artifact_id "
                    "AND page.page_index=:page "
                    "ORDER BY page.version DESC LIMIT 1) p ON true "
                    "WHERE nd.designation=:designation ORDER BY ne.admitted_at DESC LIMIT 1"
                ),
                {"designation": designation, "page": page_index},
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise ValueError("NTD_POLZA_PAGE_NOT_FOUND")
    return dict(row)


def _rendered_page_version(
    page: dict[str, Any],
    render_digest: str,
    terminal_outcome: str,
    *,
    provider_profile_version: str,
) -> RepresentationPage:
    payload = {
        "schema": "ntd-representation-render-v1",
        "page_id": page["normative_page_id"],
        "render_digest": render_digest,
        "provider_profile": provider_profile_version,
        "terminal_outcome": terminal_outcome,
    }
    return RepresentationPage(
        UUID(str(page["normative_page_id"])),
        int(page["page_index"]),
        str(page["printed_page_label"]) if page["printed_page_label"] is not None else None,
        str(page["representation_kind"]),
        Decimal(str(page["width_points"])),
        Decimal(str(page["height_points"])),
        int(page["rotation_degrees"]),
        int(page["native_text_character_count"]),
        Decimal(str(page["native_text_coverage"])),
        render_digest,
        "polza_candidate",
        terminal_outcome,
        NTD_REPRESENTATION_INVENTORY_VERSION,
        digest_of(payload),
    )


def _polza_request(
    page: dict[str, Any],
    rendered_page: RepresentationPage,
    render_png: bytes,
    *,
    source_region: tuple[Decimal, Decimal, Decimal, Decimal] | None,
    render_to_source: tuple[Decimal, ...] | None,
) -> PolzaPageRequest:
    return PolzaPageRequest(
        str(page["designation_namespace"]) + ":" + str(page["designation"]),
        UUID(str(page["normative_edition_id"])),
        UUID(str(page["normative_artifact_id"])),
        rendered_page.page_id,
        rendered_page.printed_page_label,
        Decimal(str(page["width_points"])),
        Decimal(str(page["height_points"])),
        rendered_page.render_digest or "",
        render_png,
        source_region=source_region
        or (
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
            Decimal("1"),
        ),
        render_to_source=render_to_source
        or (
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("1"),
        ),
    )


def _parse_source_region(
    value: str | None,
) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    if value is None:
        return None
    parts = tuple(Decimal(part.strip()) for part in value.split(","))
    if len(parts) != 4:
        raise ValueError("NTD_POLZA_SOURCE_REGION_INVALID")
    x0, y0, x1, y1 = parts
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("NTD_POLZA_SOURCE_REGION_INVALID")
    return x0, y0, x1, y1


def _require_route(
    page: dict[str, Any],
    source_region: tuple[Decimal, Decimal, Decimal, Decimal] | None,
) -> None:
    if source_region is None:
        if page["extraction_route"] != "polza_candidate":
            raise ValueError("NTD_POLZA_PAGE_NOT_ROUTED_TO_EXTERNAL_RECOVERY")
        return
    if page["representation_kind"] == "raster" and page["terminal_outcome"] in {
        "failed",
        "recovery_complete",
    }:
        return
    if page["representation_kind"] not in {"damaged_native", "mixed", "table_heavy"}:
        raise ValueError("NTD_POLZA_REGION_ROUTE_NOT_APPLICABLE")


def _latest_page_version(engine: sa.Engine, page_id: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.scalar(
                sa.text(
                    "SELECT max(version) FROM platform.normative_representation_pages "
                    "WHERE normative_page_id=:page"
                ),
                {"page": page_id},
            )
        )


def _source_path(object_root: Path, object_id: UUID) -> Path:
    candidate = object_root / "platform" / "source" / str(object_id)
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("NTD_POLZA_SOURCE_OBJECT_UNAVAILABLE")
    if object_root.resolve(strict=True) not in candidate.resolve(strict=True).parents:
        raise ValueError("NTD_POLZA_SOURCE_OBJECT_ESCAPED_ROOT")
    return candidate


def _verify_source_bytes(source_path: Path, expected_digest: str) -> None:
    digest = hashlib.sha256()
    with source_path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != expected_digest:
        raise ValueError("NTD_POLZA_SOURCE_OBJECT_DIGEST_MISMATCH")


def _print_safe_result(
    page: dict[str, Any],
    page_version: int,
    render_digest: str,
    receipt: dict[str, Any],
    *,
    reused: bool,
) -> None:
    candidate = receipt["candidate_manifest"]
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "reused": reused,
                "designation": page["designation"],
                "page_index": page["page_index"],
                "page_version": page_version,
                "render_digest": render_digest,
                "request_digest": receipt["request_digest"],
                "response_digest": receipt["response_digest"],
                "block_count": len(candidate.get("blocks", [])),
                "retry_count": receipt["retry_count"],
                "usage_receipt": receipt["usage_receipt"],
                "receipt_fingerprint": receipt["receipt_fingerprint"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _write_failure_receipt(
    receipt_dir: Path,
    page: dict[str, Any],
    page_version: int,
    render_digest: str,
    failure_code: str,
    provider_profile_version: str,
    request_digest: str | None = None,
    response_digest: str | None = None,
    provider_request_id: str | None = None,
) -> None:
    payload = {
        "schema": "ntd-polza-canary-failure-v1",
        "designation": page["designation"],
        "page_identity": str(page["normative_page_id"]),
        "page_version": page_version,
        "page_index": page["page_index"],
        "render_digest": render_digest,
        "provider_profile": provider_profile_version,
        "failure_code": failure_code,
        "request_digest": request_digest,
        "response_digest": response_digest,
        "provider_request_id": provider_request_id,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    payload["receipt_fingerprint"] = digest_of(payload)
    name = datetime.now(UTC).strftime("ntd-polza-canary-failure-%Y%m%dT%H%M%S%fZ.json")
    target = receipt_dir / name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_EXTERNAL_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_EXTERNAL_DIRECTORY_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
