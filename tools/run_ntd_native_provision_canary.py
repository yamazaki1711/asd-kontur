"""Replay and publish one exact native normative provision canary."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.ntd.file_processing import (
    extract_shared_native_document,
    reconstruct_native_structure,
)
from asd_kontur.ntd.remediation import NtdRemediationRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--designation", required=True)
    parser.add_argument("--structural-path", required=True)
    parser.add_argument("--verifier-identity", default="codex:NTD-SEED-REMEDIATION-01")
    arguments = parser.parse_args()
    _require_private_directory(arguments.object_root)
    engine = sa.create_engine(arguments.database_url)
    try:
        artifact = _load_artifact(engine, arguments.designation)
        source_path = arguments.object_root / "platform" / "source" / str(artifact["object_id"])
        _verify_object(source_path, str(artifact["content_digest"]), int(artifact["size_bytes"]))
        native = extract_shared_native_document(
            source_path,
            document_id=UUID(str(artifact["normative_document_id"])),
            source_version_id=UUID(str(artifact["source_version_id"])),
        )
        matching = tuple(
            fragment
            for fragment in reconstruct_native_structure(
                native,
                normative_edition_id=UUID(str(artifact["normative_edition_id"])),
            )
            if fragment.structural_path == arguments.structural_path
        )
        if len(matching) != 1:
            raise ValueError("NTD_NATIVE_CANARY_STRUCTURAL_PATH_NOT_UNIQUE")
        result = NtdRemediationRepository(engine).qualify_native_provision(
            normative_edition_id=UUID(str(artifact["normative_edition_id"])),
            source_version_id=UUID(str(artifact["source_version_id"])),
            structural_path=arguments.structural_path,
            replay_fragment=matching[0],
            expected_artifact_digest=str(artifact["content_digest"]),
            verified_at=datetime.now(UTC),
            verifier_identity=arguments.verifier_identity,
        )
        payload = asdict(result)
        payload.update(
            {
                "schema": "ntd-native-provision-canary-result-v1",
                "designation": arguments.designation,
                "status": "verified",
            }
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    finally:
        engine.dispose()


def _load_artifact(engine: sa.Engine, designation: str) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                sa.text(
                    "SELECT nd.normative_document_id,nd.designation,ne.normative_edition_id,"
                    "na.normative_artifact_id,na.source_version_id,na.content_digest,na.size_bytes,"
                    "o.object_id FROM platform.normative_documents nd JOIN "
                    "platform.normative_editions ne USING (normative_document_id) JOIN "
                    "platform.normative_artifacts na ON na.normative_edition_id="
                    "ne.normative_edition_id JOIN platform.source_versions sv ON "
                    "sv.source_version_id=na.source_version_id JOIN platform.objects o ON "
                    "o.object_id=sv.object_id AND o.object_version=sv.object_version WHERE "
                    "nd.designation=:designation ORDER BY ne.admitted_at DESC"
                ),
                {"designation": designation},
            )
            .mappings()
            .all()
        )
    if len(rows) != 1:
        raise ValueError("NTD_NATIVE_CANARY_ARTIFACT_NOT_UNIQUE")
    return dict(rows[0])


def _verify_object(path: Path, expected_digest: str, expected_size: int) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        raise ValueError("NTD_NATIVE_CANARY_SOURCE_OBJECT_INVALID")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != expected_digest:
        raise ValueError("NTD_NATIVE_CANARY_SOURCE_DIGEST_MISMATCH")


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_NATIVE_CANARY_OBJECT_ROOT_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_NATIVE_CANARY_OBJECT_ROOT_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
