"""Execute the bounded 25-identity NTD remediation into permanent platform memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
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
from asd_kontur.ntd.minstroy import MinstroyCatalogueClient, UrllibOfficialTransport
from asd_kontur.ntd.models import NormativeArtifact
from asd_kontur.ntd.official_sources import TransportProfile
from asd_kontur.ntd.postgres import (
    NormativeDocumentRegistration,
    NormativeEditionRegistration,
    NtdRepository,
)
from asd_kontur.ntd.remediation import (
    NtdRemediationRepository,
    ReconciledSeedIdentity,
    load_historical_seed_identities,
    remediation_environment_fingerprint,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--historical-manifest", type=Path, required=True)
    parser.add_argument("--minstroy-resolution", type=Path, required=True)
    parser.add_argument("--canonical-commit", required=True)
    parser.add_argument("--max-download-mib", type=int, default=512)
    parser.add_argument("--limit-identities", type=int)
    parser.add_argument("--identity-key", action="append", default=[])
    args = parser.parse_args()
    _require_private_directory(args.object_root)
    _require_private_directory(args.receipt_dir)
    if args.max_download_mib < 32 or args.max_download_mib > 1024:
        raise ValueError("NTD_DOWNLOAD_BOUND_INVALID")

    identities = load_historical_seed_identities(args.historical_manifest)
    report = json.loads(args.minstroy_resolution.read_text(encoding="utf-8"))
    by_identity = {str(value["stable_identity_key"]): value for value in report["identities"]}
    if len(by_identity) != 25:
        raise ValueError("NTD_RESOLUTION_REPORT_DENOMINATOR_MISMATCH")
    lock_digest = "sha256:" + hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest()
    engine = sa.create_engine(args.database_url)
    with engine.connect() as connection:
        database_version = str(connection.scalar(sa.text("SHOW server_version")))
    environment = remediation_environment_fingerprint(
        code_commit=args.canonical_commit,
        lock_digest=lock_digest,
        python_version=platform.python_version(),
        database_version=database_version,
    )
    remediation = NtdRemediationRepository(engine)
    decision_id, decision_version = remediation.register_reopening_decision(
        canonical_commit=args.canonical_commit,
        environment_fingerprint=environment,
        decided_at=datetime.now(UTC),
        prior_receipt_fingerprints=(
            "sha256:1392964228c5732f69c74026011b554768eacf2cce85a73abbfdac1133302386",
            str(report["report_fingerprint"]),
        ),
    )
    remediation.register_identities(
        decision_id=decision_id,
        decision_version=decision_version,
        identities=identities,
        recorded_at=datetime.now(UTC),
    )
    ledger = PlatformSourceLedger(engine, LocalFilesystemObjectStore(args.object_root))
    ntd = NtdRepository(engine)
    client = MinstroyCatalogueClient(
        UrllibOfficialTransport(
            timeout_seconds=60,
            max_response_bytes=args.max_download_mib * 1024 * 1024,
            max_attempts=2,
            min_interval_seconds=0.25,
            profile=TransportProfile.DIRECT,
        ),
        max_search_pages=3,
        max_category_pages=64,
    )
    results: list[dict[str, object]] = []
    selected_identities = identities
    if args.identity_key:
        selected = frozenset(str(value) for value in args.identity_key)
        selected_identities = tuple(
            identity
            for identity in identities
            if identity.canonical_stable_identity_key in selected
        )
        if len(selected_identities) != len(selected):
            raise ValueError("NTD_SELECTED_IDENTITY_NOT_IN_MANIFEST")
    if args.limit_identities:
        selected_identities = selected_identities[: args.limit_identities]
    for identity in selected_identities:
        outcome = by_identity[identity.canonical_stable_identity_key]
        results.append(
            _process_identity(
                identity=identity,
                outcome=outcome,
                client=client,
                ledger=ledger,
                ntd=ntd,
                remediation=remediation,
                environment_fingerprint=environment,
                receipt_dir=args.receipt_dir,
            )
        )
    summary = {
        "schema": "ntd-seed-remediation-run-v1",
        "logical_manifest_fingerprint": (
            "sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6"
        ),
        "identity_denominator": 25,
        "processed_in_run": len(results),
        "environment_fingerprint": environment,
        "results": results,
    }
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    summary_path = args.receipt_dir / f"ntd-seed-remediation-run-v1-{run_stamp}.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.chmod(0o600)
    print(
        json.dumps(
            {
                "identity_denominator": 25,
                "processed_in_run": len(results),
                "statuses": _counts(results, "terminal_state"),
                "downloaded": sum(bool(value.get("artifact_digest")) for value in results),
                "verified_provisions": sum(
                    _int_value(value.get("verified_provision_count", 0)) for value in results
                ),
                "environment_fingerprint": environment,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    engine.dispose()
    return 0


def _process_identity(
    *,
    identity: ReconciledSeedIdentity,
    outcome: dict[str, object],
    client: MinstroyCatalogueClient,
    ledger: PlatformSourceLedger,
    ntd: NtdRepository,
    remediation: NtdRemediationRepository,
    environment_fingerprint: str,
    receipt_dir: Path,
) -> dict[str, object]:
    now = datetime.now(UTC)
    record = outcome.get("catalogue_record")
    if not isinstance(record, dict):
        remediation.record_identity_resolution(
            identity=identity,
            provider="minstroy_catalogue",
            transport_profile="direct",
            official_record_id=None,
            official_record_url=None,
            official_record_digest=None,
            resolution_status=str(outcome["terminal_status"]),
            failure_code=_failure_code(outcome),
            diagnostic={"uncertainty_codes": outcome.get("uncertainty_codes", [])},
            environment_fingerprint=environment_fingerprint,
            recorded_at=now,
        )
        return {
            "identity": identity.canonical_stable_identity_key,
            "printed_editions": identity.printed_editions,
            "terminal_state": str(outcome["terminal_status"]),
            "failure_code": _failure_code(outcome),
        }
    artifact_urls = tuple(str(value) for value in record.get("artifact_urls", []))
    if not artifact_urls:
        remediation.record_identity_resolution(
            identity=identity,
            provider="minstroy_catalogue",
            transport_profile="direct",
            official_record_id=str(record["catalog_id"]),
            official_record_url=str(record["catalog_url"]),
            official_record_digest=str(record["metadata_digest"]),
            resolution_status=str(outcome["terminal_status"]),
            failure_code=_failure_code(outcome),
            diagnostic={"artifact_urls": []},
            environment_fingerprint=environment_fingerprint,
            recorded_at=now,
        )
        return {
            "identity": identity.canonical_stable_identity_key,
            "printed_editions": identity.printed_editions,
            "official_record_id": record["catalog_id"],
            "terminal_state": str(outcome["terminal_status"]),
            "failure_code": _failure_code(outcome),
        }
    # The current exact denominator cards expose one primary artifact each. Multiple
    # attachments remain individually admissible but are not silently merged into an edition.
    artifact_url = artifact_urls[0]
    staging_path = receipt_dir / f"download-{identity.reconciliation_id}.part"
    staging_path.unlink(missing_ok=True)
    try:
        downloaded = client.download_artifact_to_path(artifact_url, staging_path)
        validation = validate_official_pdf(
            staging_path, expected_designation=identity.normalized.normalized_designation
        )
        if validation.content_digest != downloaded.content_digest:
            raise ValueError("NTD_STREAM_VALIDATION_DIGEST_MISMATCH")
        source_family = f"official-ntd:{identity.canonical_stable_identity_key}"
        ledger.register_official_source(
            OfficialSourceRegistration(
                source_family,
                artifact_url,
                "Минстрой России",
                "RU",
                json.dumps(
                    {
                        "catalog_id": record["catalog_id"],
                        "catalog_url": record["catalog_url"],
                        "record_digest": record["metadata_digest"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "identity.owner-ntd-seed-remediation-01",
                uuid7(),
            )
        )
        admitted = ledger.admit_file(
            PlatformSourceAdmission(
                source_family,
                identity.normalized.normalized_designation,
                str(record["title"]),
                "Минстрой России",
                "RU",
                _edition_label(identity, validation.content_digest),
                (
                    "legal_act"
                    if identity.document_kind == "minstroy_order"
                    else "normative_document"
                ),
                artifact_url,
                "official_https_stream_v0.1",
                json.dumps(
                    {
                        "catalog_id": record["catalog_id"],
                        "catalog_url": record["catalog_url"],
                        "record_digest": record["metadata_digest"],
                        "declared_media_type": downloaded.metadata.content_type,
                        "detected_media_type": validation.detected_media_type,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                validation.detected_media_type,
                "public_normative_authority",
                PERMANENT_PLATFORM_CORE,
                "identity.owner-ntd-seed-remediation-01",
                uuid7(),
            ),
            staging_path,
        )
        registered_document = ntd.register_document(
            NormativeDocumentRegistration(
                identity.canonical_stable_identity_key,
                _designation_namespace(identity),
                identity.normalized.normalized_designation,
                str(record["title"]),
                "Минстрой России",
                "RU",
                identity.document_kind,
                "identity.owner-ntd-seed-remediation-01",
            )
        )
        registered_edition = ntd.register_edition(
            NormativeEditionRegistration(
                registered_document.normative_document_id,
                _edition_label(identity, validation.content_digest),
                admitted.source_version_id,
                str(record["catalog_id"]),
                str(record["catalog_url"]),
                {
                    "approval_reference": record.get("approval_reference"),
                    "published_at": record.get("published_at"),
                    "printed_editions": identity.printed_editions,
                    "record_digest": record["metadata_digest"],
                },
                None,
                None,
                downloaded.metadata.retrieved_at,
                "identity.owner-ntd-seed-remediation-01",
            )
        )
        artifact_id = deterministic_uuid(
            f"normative-artifact:{registered_edition.normative_edition_id}:"
            f"{admitted.source_version_id}:{validation.content_digest}"
        )
        artifact = NormativeArtifact(
            artifact_id,
            registered_edition.normative_edition_id,
            admitted.source_version_id,
            str(record["catalog_id"]),
            artifact_url,
            Path(urllib.parse.urlsplit(artifact_url).path).name or "official.pdf",
            validation.detected_media_type,
            validation.byte_length,
            validation.content_digest,
            "primary_text",
            str(record["metadata_digest"]),
        )
        ntd.register_artifact(artifact, registered_at=downloaded.metadata.retrieved_at)
        remediation.record_artifact_validation(
            normative_artifact_id=artifact_id,
            source_version_id=admitted.source_version_id,
            declared_media_type=downloaded.metadata.content_type,
            validation=validation,
            validated_at=datetime.now(UTC),
        )
        structural_count = verified_count = 0
        native_document = extract_shared_native_document(
            staging_path,
            document_id=registered_document.normative_document_id,
            source_version_id=admitted.source_version_id,
        )
        pages = inventory_pages(native_document, normative_artifact_id=artifact_id)
        remediation.record_representation_pages(
            normative_artifact_id=artifact_id,
            source_version_id=admitted.source_version_id,
            pages=pages,
            recorded_at=datetime.now(UTC),
        )
        raster_pending = sum(
            page.extraction_route == "polza_candidate" or page.terminal_outcome != "native_complete"
            for page in pages
        )
        if (
            validation.validation_status == "supported"
            and validation.title_identity_status == "native_confirmed"
        ):
            fragments = reconstruct_native_structure(
                native_document,
                normative_edition_id=registered_edition.normative_edition_id,
            )
            structural_count, verified_count = remediation.persist_native_fragment_candidates(
                normative_edition_id=registered_edition.normative_edition_id,
                source_version_id=admitted.source_version_id,
                fragments=fragments,
                recorded_at=datetime.now(UTC),
                verifier_identity="identity.owner-ntd-seed-remediation-01",
            )
        terminal = (
            "parsed_verified" if verified_count > 0 and raster_pending == 0 else "parse_partial"
        )
        remediation.record_identity_resolution(
            identity=identity,
            provider="minstroy_catalogue",
            transport_profile="direct",
            official_record_id=str(record["catalog_id"]),
            official_record_url=str(record["catalog_url"]),
            official_record_digest=str(record["metadata_digest"]),
            resolution_status=terminal,
            failure_code=("RASTER_RECOVERY_PENDING" if raster_pending else None),
            diagnostic={
                "artifact_digest": validation.content_digest,
                "page_count": validation.page_count,
                "raster_or_recovery_pending": raster_pending,
                "structural_node_count": structural_count,
                "verified_provision_count": verified_count,
            },
            environment_fingerprint=environment_fingerprint,
            recorded_at=datetime.now(UTC),
            normative_document_id=registered_document.normative_document_id,
            normative_edition_id=registered_edition.normative_edition_id,
            normative_artifact_ids=(artifact_id,),
        )
        return {
            "identity": identity.canonical_stable_identity_key,
            "printed_editions": identity.printed_editions,
            "official_record_id": record["catalog_id"],
            "official_url": artifact_url,
            "artifact_digest": validation.content_digest,
            "artifact_bytes": validation.byte_length,
            "page_count": validation.page_count,
            "page_kinds": _counts([{"kind": page.kind} for page in pages], "kind"),
            "raster_or_recovery_pending": raster_pending,
            "structural_node_count": structural_count,
            "verified_provision_count": verified_count,
            "terminal_state": terminal,
        }
    except Exception as exc:
        remediation.record_identity_resolution(
            identity=identity,
            provider="minstroy_catalogue",
            transport_profile="direct",
            official_record_id=str(record["catalog_id"]),
            official_record_url=str(record["catalog_url"]),
            official_record_digest=str(record["metadata_digest"]),
            resolution_status="blocked_deterministic_failure",
            failure_code=type(exc).__name__,
            diagnostic={"message": str(exc)[:500]},
            environment_fingerprint=environment_fingerprint,
            recorded_at=datetime.now(UTC),
        )
        return {
            "identity": identity.canonical_stable_identity_key,
            "printed_editions": identity.printed_editions,
            "official_record_id": record["catalog_id"],
            "terminal_state": "blocked_deterministic_failure",
            "failure_code": type(exc).__name__,
            "failure_message": str(exc)[:500],
        }
    finally:
        staging_path.unlink(missing_ok=True)


def _edition_label(identity: ReconciledSeedIdentity, digest: str) -> str:
    printed = ",".join(identity.printed_editions) or "edition-unresolved"
    return f"printed:{printed};source:{digest[7:19]}"


def _designation_namespace(identity: ReconciledSeedIdentity) -> str:
    return {
        "minstroy_order": "ru:minstroy:order",
        "code_of_practice": "ru:sp",
        "national_standard": "ru:gost-r",
        "interstate_standard": "ru:gost",
        "instruction": "ru:instruction",
    }[identity.document_kind]


def _failure_code(outcome: dict[str, object]) -> str | None:
    values = outcome.get("uncertainty_codes")
    if isinstance(values, list) and values:
        return str(values[0])
    terminal = outcome.get("terminal_receipt")
    return (
        str(terminal.get("failure_code"))
        if isinstance(terminal, dict) and terminal.get("failure_code")
        else None
    )


def _counts(values: list[dict[str, object]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        item = str(value.get(key))
        result[item] = result.get(item, 0) + 1
    return result


def _int_value(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("NTD_RECEIPT_COUNT_INVALID")
    return value


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_EXTERNAL_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_EXTERNAL_DIRECTORY_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
