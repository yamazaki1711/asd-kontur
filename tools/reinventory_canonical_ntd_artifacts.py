"""Rebuild the canonical NTD page inventory from already admitted source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.ntd.file_processing import extract_shared_native_document, inventory_pages
from asd_kontur.ntd.remediation import NtdRemediationRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--receipt-path", type=Path)
    arguments = parser.parse_args()
    _require_private_directory(arguments.object_root)
    engine = sa.create_engine(arguments.database_url)
    repository = NtdRemediationRepository(engine)
    results: list[dict[str, Any]] = []
    try:
        for row in _artifacts(engine):
            object_path = arguments.object_root / "platform" / "source" / str(row["object_id"])
            _verify_object(object_path, str(row["content_digest"]), int(row["size_bytes"]))
            native = extract_shared_native_document(
                object_path,
                document_id=UUID(str(row["normative_document_id"])),
                source_version_id=UUID(str(row["source_version_id"])),
            )
            pages = inventory_pages(
                native, normative_artifact_id=UUID(str(row["normative_artifact_id"]))
            )
            repository.record_representation_pages(
                normative_artifact_id=UUID(str(row["normative_artifact_id"])),
                source_version_id=UUID(str(row["source_version_id"])),
                pages=pages,
                recorded_at=datetime.now(UTC),
            )
            results.append(
                {
                    "designation": row["designation"],
                    "artifact_digest": row["content_digest"],
                    "page_count": len(pages),
                    "native_complete": sum(
                        page.terminal_outcome == "native_complete" for page in pages
                    ),
                    "external_recovery": sum(
                        page.extraction_route == "polza_candidate" for page in pages
                    ),
                    "blocked": sum(page.extraction_route == "blocked" for page in pages),
                }
            )
    finally:
        engine.dispose()
    payload = {
        "schema": "canonical-ntd-reinventory-result-v1",
        "artifact_count": len(results),
        "page_count": sum(int(value["page_count"]) for value in results),
        "native_complete": sum(int(value["native_complete"]) for value in results),
        "external_recovery": sum(int(value["external_recovery"]) for value in results),
        "blocked": sum(int(value["blocked"]) for value in results),
        "results": results,
    }
    payload["semantic_fingerprint"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    if arguments.receipt_path is not None:
        _write_immutable_receipt(arguments.receipt_path, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _artifacts(engine: sa.Engine) -> tuple[dict[str, Any], ...]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                sa.text(
                    "SELECT d.normative_document_id,d.designation,a.normative_artifact_id,"
                    "a.source_version_id,a.content_digest,a.size_bytes,o.object_id FROM "
                    "platform.normative_documents d JOIN platform.normative_editions e USING "
                    "(normative_document_id) JOIN platform.normative_artifacts a ON "
                    "a.normative_edition_id=e.normative_edition_id JOIN "
                    "platform.source_versions sv ON sv.source_version_id=a.source_version_id JOIN "
                    "platform.objects o ON o.object_id=sv.object_id "
                    "AND o.object_version=sv.object_version WHERE a.media_type='application/pdf' "
                    "ORDER BY d.designation,a.normative_artifact_id"
                )
            )
            .mappings()
            .all()
        )
    return tuple(dict(row) for row in rows)


def _verify_object(path: Path, expected_digest: str, expected_size: int) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        raise ValueError("NTD_REINVENTORY_SOURCE_OBJECT_INVALID")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != expected_digest:
        raise ValueError("NTD_REINVENTORY_SOURCE_DIGEST_MISMATCH")


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_REINVENTORY_OBJECT_ROOT_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_REINVENTORY_OBJECT_ROOT_NOT_PRIVATE")


def _write_immutable_receipt(path: Path, payload: dict[str, Any]) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError("NTD_REINVENTORY_RECEIPT_PATH_INVALID")
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("NTD_REINVENTORY_RECEIPT_PARENT_NOT_PRIVATE")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    if path.exists() and path.read_bytes() != encoded:
        raise ValueError("NTD_REINVENTORY_RECEIPT_CONFLICT")
    if not path.exists():
        path.write_bytes(encoded)
        path.chmod(0o600)


if __name__ == "__main__":
    raise SystemExit(main())
