"""Publish immutable targeted official-resolution evidence into canonical NTD lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.ntd.remediation import (
    HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT,
    NtdRemediationRepository,
    load_historical_seed_identities,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--historical-manifest", required=True, type=Path)
    parser.add_argument("--resolution-manifest", required=True, type=Path)
    arguments = parser.parse_args()
    manifest = _load_manifest(arguments.resolution_manifest)
    identities = {
        item.canonical_stable_identity_key: item
        for item in load_historical_seed_identities(arguments.historical_manifest)
    }
    engine = sa.create_engine(arguments.database_url)
    repository = NtdRemediationRepository(engine)
    recorded = 0
    reused = 0
    try:
        environment = _environment_fingerprint(engine, manifest)
        for result in manifest["results"]:
            identity_key = str(result["stable_identity_key"])
            identity = identities.get(identity_key)
            if identity is None:
                raise ValueError("TARGETED_NTD_RESOLUTION_IDENTITY_OUTSIDE_DENOMINATOR")
            provider = _provider(result)
            source_fingerprint = str(manifest["semantic_fingerprint"])
            requires_binding = bool(result["official_artifact_downloaded"])
            if _already_imported(
                engine,
                identity.reconciliation_id,
                provider,
                source_fingerprint,
                requires_binding=requires_binding,
            ):
                reused += 1
                continue
            status, failure = _resolution_outcome(result)
            document_id, edition_id, artifact_ids = _canonical_binding(engine, result)
            record_url = _optional_string(result.get("official_record_url"))
            diagnostic = {
                "schema": "targeted-official-resolution-diagnostic-v1",
                "source_manifest_fingerprint": source_fingerprint,
                "printed_designation": result["printed_designation"],
                "resolved_official_designation": result.get("resolved_official_designation"),
                "edition_resolution": result["edition_resolution"],
                "terminal_state": result["terminal_state"],
                "official_artifact_downloaded": result["official_artifact_downloaded"],
                "official_artifact_digest": result.get("official_artifact_digest"),
                "recovered_candidate_digests": result["recovered_candidate_digests"],
                "recovered_bytes_officially_bound": result["recovered_bytes_officially_bound"],
                "observations": result.get("observations", []),
                "official_amendment_records": result.get("official_amendment_records", []),
                "discovery_references": result.get("discovery_references", []),
                "minstroy_priority_probe": result.get("minstroy_priority_probe"),
            }
            repository.record_identity_resolution(
                identity=identity,
                provider=provider,
                transport_profile="direct",
                official_record_id=_record_id(record_url),
                official_record_url=record_url,
                official_record_digest=_optional_string(result.get("official_record_digest")),
                resolution_status=status,
                failure_code=failure,
                diagnostic=diagnostic,
                environment_fingerprint=environment,
                recorded_at=datetime.now(UTC),
                normative_document_id=document_id,
                normative_edition_id=edition_id,
                normative_artifact_ids=artifact_ids,
            )
            recorded += 1
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "schema": "targeted-ntd-resolution-import-result-v1",
                "source_manifest_fingerprint": manifest["semantic_fingerprint"],
                "recorded": recorded,
                "reused": reused,
            },
            sort_keys=True,
        )
    )
    return 0


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("TARGETED_NTD_RESOLUTION_MANIFEST_INVALID")
    value = json.loads(path.read_text())
    if value.get("schema") != "exact-11-official-provenance-resolution-v1":
        raise ValueError("TARGETED_NTD_RESOLUTION_SCHEMA_INVALID")
    if value.get("logical_seed_manifest_fingerprint") != HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT:
        raise ValueError("TARGETED_NTD_RESOLUTION_DENOMINATOR_MISMATCH")
    if value.get("identity_denominator") != 11 or len(value.get("results", [])) != 11:
        raise ValueError("TARGETED_NTD_RESOLUTION_COUNT_MISMATCH")
    expected = str(value.get("semantic_fingerprint"))
    payload = dict(value)
    del payload["semantic_fingerprint"]
    actual = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )
    if actual != expected:
        raise ValueError("TARGETED_NTD_RESOLUTION_FINGERPRINT_MISMATCH")
    return cast(dict[str, Any], value)


def _provider(result: dict[str, Any]) -> str:
    provider = str(result["official_provider"])
    if provider.startswith("Росстандарт"):
        return "rosstandart_fund"
    if provider == "Минстрой России":
        return "minstroy_catalogue"
    raise ValueError("TARGETED_NTD_RESOLUTION_PROVIDER_UNSUPPORTED")


def _resolution_outcome(result: dict[str, Any]) -> tuple[str, str | None]:
    terminal = str(result["terminal_state"])
    if terminal == "OFFICIAL_PROVENANCE_BINDING_RESTORED":
        return "parse_partial", "RASTER_RECOVERY_PENDING"
    if terminal == "OFFICIAL_ARTIFACT_UNAVAILABLE_EMPTY_VIEWER_MANIFEST":
        return "official_artifact_unavailable", "ROSSTANDART_VIEWER_MANIFEST_EMPTY"
    if terminal == "OFFICIAL_ARTIFACT_UNAVAILABLE_REPEATED_INVALID_PLACEHOLDER":
        return "artifact_invalid", "ROSSTANDART_VIEWER_PLACEHOLDER_INVALID"
    if terminal == "ONLY_AMENDMENT_RECORDS_FOUND":
        return "official_artifact_unavailable", "OFFICIAL_BASE_RECORD_NOT_FOUND"
    if terminal == "NO_EXACT_OFFICIAL_RECORD":
        return "not_found_official", str(result["failure_code"])
    raise ValueError("TARGETED_NTD_RESOLUTION_TERMINAL_STATE_UNSUPPORTED")


def _already_imported(
    engine: sa.Engine,
    identity_reconciliation_id: object,
    provider: str,
    fingerprint: str,
    *,
    requires_binding: bool,
) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM platform.ntd_identity_resolution_versions "
                    "WHERE identity_reconciliation_id=:identity AND provider=:provider "
                    "AND diagnostic->>'source_manifest_fingerprint'=:fingerprint "
                    "AND (:requires_binding=false OR (normative_edition_id IS NOT NULL "
                    "AND cardinality(normative_artifact_ids)>0)))"
                ),
                {
                    "identity": identity_reconciliation_id,
                    "provider": provider,
                    "fingerprint": fingerprint,
                    "requires_binding": requires_binding,
                },
            )
        )


def _canonical_binding(
    engine: sa.Engine, result: dict[str, Any]
) -> tuple[UUID | None, UUID | None, tuple[UUID, ...]]:
    if not result["official_artifact_downloaded"]:
        return None, None, ()
    digest = _optional_string(result.get("official_artifact_digest"))
    if digest is None:
        raise ValueError("TARGETED_NTD_RESOLUTION_DOWNLOADED_DIGEST_MISSING")
    with engine.connect() as connection:
        rows = (
            connection.execute(
                sa.text(
                    "SELECT ne.normative_document_id,na.normative_edition_id,"
                    "na.normative_artifact_id "
                    "FROM platform.normative_artifacts na JOIN platform.normative_editions ne "
                    "ON ne.normative_edition_id=na.normative_edition_id "
                    "WHERE na.content_digest=:digest"
                ),
                {"digest": digest},
            )
            .mappings()
            .all()
        )
    if len(rows) != 1:
        raise ValueError("TARGETED_NTD_RESOLUTION_CANONICAL_BINDING_NOT_UNIQUE")
    row = rows[0]
    return (
        UUID(str(row["normative_document_id"])),
        UUID(str(row["normative_edition_id"])),
        (UUID(str(row["normative_artifact_id"])),),
    )


def _record_id(record_url: str | None) -> str | None:
    if record_url is None:
        return None
    parts = [part for part in urlsplit(record_url).path.split("/") if part]
    return parts[-1] if parts else None


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _environment_fingerprint(engine: sa.Engine, manifest: dict[str, Any]) -> str:
    with engine.connect() as connection:
        postgresql = str(connection.scalar(sa.text("SHOW server_version")))
    payload = {
        "schema": "targeted-official-resolution-environment-v1",
        "acquisition_host": "king25",
        "postgresql": postgresql,
        "source_receipts": manifest["source_receipts"],
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )


if __name__ == "__main__":
    raise SystemExit(main())
