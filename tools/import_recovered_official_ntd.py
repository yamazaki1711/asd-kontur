"""Admit recovered bytes after an exact official SHA-256 provenance binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.knowledge.object_store import LocalFilesystemObjectStore
from asd_kontur.knowledge.source_ledger import (
    PERMANENT_PLATFORM_CORE,
    OfficialSourceRegistration,
    PlatformSourceAdmission,
    PlatformSourceLedger,
)
from asd_kontur.ntd.file_processing import (
    extract_shared_native_document,
    inventory_pages,
    reconstruct_native_structure,
    validate_official_pdf,
)
from asd_kontur.ntd.models import NormativeArtifact
from asd_kontur.ntd.postgres import (
    NormativeDocumentRegistration,
    NormativeEditionRegistration,
    NtdRepository,
)
from asd_kontur.ntd.remediation import (
    NtdRemediationRepository,
    load_historical_seed_identities,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--historical-manifest", required=True, type=Path)
    parser.add_argument("--binding-receipt", required=True, type=Path)
    parser.add_argument("--source-file", required=True, type=Path)
    arguments = parser.parse_args()
    _require_private_directory(arguments.object_root)
    _require_private_directory(arguments.receipt_dir)
    if not arguments.source_file.is_absolute() or not arguments.source_file.is_file():
        raise ValueError("RECOVERED_NTD_SOURCE_FILE_INVALID")
    binding = json.loads(arguments.binding_receipt.read_text())
    _validate_binding(binding, arguments.source_file)
    identity_key = str(binding["identity"])
    identity = next(
        (
            value
            for value in load_historical_seed_identities(arguments.historical_manifest)
            if value.canonical_stable_identity_key == identity_key
        ),
        None,
    )
    if identity is None:
        raise ValueError("RECOVERED_NTD_IDENTITY_OUTSIDE_SEED_DENOMINATOR")
    engine = sa.create_engine(arguments.database_url)
    ledger = PlatformSourceLedger(engine, LocalFilesystemObjectStore(arguments.object_root))
    ntd = NtdRepository(engine)
    remediation = NtdRemediationRepository(engine)
    artifact_url = str(binding["official_artifact_url"])
    record_url = str(binding["official_record_url"])
    record_id = str(binding["official_catalog_id"])
    record_digest = str(binding["official_card_receipt"]["sha256"])
    source_family = f"official-ntd:{identity_key}"
    registry_metadata = json.dumps(
        {
            "schema": "recovered-official-sha256-binding-v1",
            "catalog_id": record_id,
            "catalog_url": record_url,
            "record_digest": record_digest,
            "artifact_digest": binding["official_artifact_digest"],
            "binding_fingerprint": binding["semantic_fingerprint"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    ledger.register_official_source(
        OfficialSourceRegistration(
            source_family,
            artifact_url,
            "Минстрой России",
            "RU",
            registry_metadata,
            "identity.owner-ntd-seed-remediation-01",
            uuid7(),
        )
    )
    validation = validate_official_pdf(
        arguments.source_file,
        expected_designation=identity.normalized.normalized_designation,
    )
    title = (
        identity.title_hints[0]
        if identity.title_hints
        else identity.normalized.normalized_designation
    )
    edition_label = _edition_label(identity.printed_editions, validation.content_digest)
    admitted = ledger.admit_file(
        PlatformSourceAdmission(
            source_family,
            identity.normalized.normalized_designation,
            title,
            "Минстрой России",
            "RU",
            edition_label,
            "normative_document",
            artifact_url,
            "recovered_official_sha256_binding_v0.1",
            registry_metadata,
            validation.detected_media_type,
            "public_normative_authority",
            PERMANENT_PLATFORM_CORE,
            "identity.owner-ntd-seed-remediation-01",
            uuid7(),
        ),
        arguments.source_file,
    )
    document = ntd.register_document(
        NormativeDocumentRegistration(
            identity_key,
            "ru:sp",
            identity.normalized.normalized_designation,
            title,
            "Минстрой России",
            "RU",
            identity.document_kind,
            "identity.owner-ntd-seed-remediation-01",
        )
    )
    retrieved_at = datetime.fromisoformat(str(binding["artifact_receipt"]["retrieved_at"]))
    edition = ntd.register_edition(
        NormativeEditionRegistration(
            document.normative_document_id,
            edition_label,
            admitted.source_version_id,
            record_id,
            record_url,
            {
                "printed_editions": identity.printed_editions,
                "record_digest": record_digest,
                "official_artifact_digest": validation.content_digest,
                "binding_fingerprint": binding["semantic_fingerprint"],
            },
            None,
            None,
            retrieved_at,
            "identity.owner-ntd-seed-remediation-01",
        )
    )
    artifact_id = deterministic_uuid(
        f"normative-artifact:{edition.normative_edition_id}:"
        f"{admitted.source_version_id}:{validation.content_digest}"
    )
    ntd.register_artifact(
        NormativeArtifact(
            artifact_id,
            edition.normative_edition_id,
            admitted.source_version_id,
            record_id,
            artifact_url,
            Path(urllib.parse.urlsplit(artifact_url).path).name or "official.pdf",
            validation.detected_media_type,
            validation.byte_length,
            validation.content_digest,
            "primary_text",
            record_digest,
        ),
        registered_at=retrieved_at,
    )
    now = datetime.now(UTC)
    remediation.record_artifact_validation(
        normative_artifact_id=artifact_id,
        source_version_id=admitted.source_version_id,
        declared_media_type=str(binding["artifact_receipt"]["declared_content_type"]),
        validation=validation,
        validated_at=now,
    )
    native = extract_shared_native_document(
        arguments.source_file,
        document_id=document.normative_document_id,
        source_version_id=admitted.source_version_id,
    )
    pages = inventory_pages(native, normative_artifact_id=artifact_id)
    remediation.record_representation_pages(
        normative_artifact_id=artifact_id,
        source_version_id=admitted.source_version_id,
        pages=pages,
        recorded_at=now,
    )
    fragments = reconstruct_native_structure(
        native, normative_edition_id=edition.normative_edition_id
    )
    structural_count, verified_count = remediation.persist_native_fragment_candidates(
        normative_edition_id=edition.normative_edition_id,
        source_version_id=admitted.source_version_id,
        fragments=fragments,
        recorded_at=now,
        verifier_identity="identity.owner-ntd-seed-remediation-01",
    )
    pending = sum(page.terminal_outcome != "native_complete" for page in pages)
    remediation.record_identity_resolution(
        identity=identity,
        provider="minstroy_catalogue",
        transport_profile="direct",
        official_record_id=record_id,
        official_record_url=record_url,
        official_record_digest=record_digest,
        resolution_status="parse_partial",
        failure_code="RASTER_RECOVERY_PENDING" if pending else "PROVISION_VERIFICATION_PENDING",
        diagnostic={
            "artifact_digest": validation.content_digest,
            "page_count": len(pages),
            "recovery_pending": pending,
            "structural_node_count": structural_count,
            "verified_provision_count": verified_count,
            "binding_fingerprint": binding["semantic_fingerprint"],
        },
        environment_fingerprint=_environment_fingerprint(engine),
        recorded_at=now,
        normative_document_id=document.normative_document_id,
        normative_edition_id=edition.normative_edition_id,
        normative_artifact_ids=(artifact_id,),
    )
    result = {
        "schema": "recovered-official-ntd-import-v1",
        "identity": identity_key,
        "normative_document_id": str(document.normative_document_id),
        "normative_edition_id": str(edition.normative_edition_id),
        "normative_artifact_id": str(artifact_id),
        "source_version_id": str(admitted.source_version_id),
        "duplicate_source_bytes": admitted.duplicate,
        "artifact_digest": validation.content_digest,
        "page_count": len(pages),
        "native_complete_pages": sum(page.terminal_outcome == "native_complete" for page in pages),
        "recovery_pending_pages": pending,
        "structural_node_count": structural_count,
        "verified_provision_count": verified_count,
        "binding_fingerprint": binding["semantic_fingerprint"],
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    target = arguments.receipt_dir / "recovered-official-ntd-import-sp70-v0.1.json"
    if target.exists() and target.read_bytes() != encoded:
        raise ValueError("RECOVERED_NTD_IMPORT_RECEIPT_CONFLICT")
    if not target.exists():
        target.write_bytes(encoded)
        target.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    engine.dispose()
    return 0


def _validate_binding(binding: dict[str, object], source: Path) -> None:
    required = {
        "schema": "sp70-official-provenance-binding-v1",
        "identity": "ru:sp:70.13330",
        "byte_identity_status": "EXACT_SHA256_MATCH",
        "terminal_state": "OFFICIAL_PROVENANCE_BINDING_RESTORED",
    }
    if any(binding.get(key) != value for key, value in required.items()):
        raise ValueError("RECOVERED_NTD_BINDING_INVALID")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != binding.get("official_artifact_digest"):
        raise ValueError("RECOVERED_NTD_BINDING_DIGEST_MISMATCH")


def _edition_label(printed_editions: tuple[str, ...], digest: str) -> str:
    printed = ",".join(printed_editions) or "edition-unresolved"
    return f"printed:{printed};source:{digest[7:19]}"


def _environment_fingerprint(engine: sa.Engine) -> str:
    with engine.connect() as connection:
        version = str(connection.scalar(sa.text("SHOW server_version")))
    value = json.dumps(
        {
            "schema": "recovered-ntd-import-environment-v1",
            "python": "3.12",
            "postgresql": version,
            "pipeline": "recovered_official_sha256_binding_v0.1",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("RECOVERED_NTD_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("RECOVERED_NTD_DIRECTORY_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
