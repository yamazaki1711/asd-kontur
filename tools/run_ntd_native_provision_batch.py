"""Replay and publish every independently supported native NTD provision.

The batch deliberately does not claim that an artifact or edition is complete.
It reuses the fail-closed single-provision verifier and extracts each immutable
source artifact only once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.ntd.file_processing import (
    StructuralFragment,
    extract_shared_native_document,
    reconstruct_native_structure,
)
from asd_kontur.ntd.remediation import NtdRemediationRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verifier-identity", default="codex:NTD-SEED-REMEDIATION-01")
    arguments = parser.parse_args()
    _require_private_directory(arguments.object_root)
    if not arguments.output.is_absolute():
        raise ValueError("NTD_NATIVE_BATCH_OUTPUT_MUST_BE_ABSOLUTE")
    if arguments.output.exists():
        raise ValueError("NTD_NATIVE_BATCH_OUTPUT_ALREADY_EXISTS")

    engine = sa.create_engine(arguments.database_url)
    started_at = datetime.now(UTC)
    outcomes: list[dict[str, Any]] = []
    try:
        repository = NtdRemediationRepository(engine)
        for artifact in _load_artifacts(engine):
            source_path = arguments.object_root / "platform" / "source" / str(artifact["object_id"])
            _verify_object(
                source_path,
                str(artifact["content_digest"]),
                int(artifact["size_bytes"]),
            )
            native = extract_shared_native_document(
                source_path,
                document_id=UUID(str(artifact["normative_document_id"])),
                source_version_id=UUID(str(artifact["source_version_id"])),
            )
            fragments = reconstruct_native_structure(
                native,
                normative_edition_id=UUID(str(artifact["normative_edition_id"])),
            )
            fragments_by_path = _fragments_by_path(fragments)
            for structural_path in _candidate_paths(engine, artifact):
                matches = fragments_by_path.get(structural_path, ())
                if len(matches) != 1:
                    outcomes.append(
                        _outcome(
                            artifact,
                            structural_path,
                            "blocked",
                            "NTD_NATIVE_BATCH_STRUCTURAL_PATH_NOT_UNIQUE",
                        )
                    )
                    continue
                try:
                    result = repository.qualify_native_provision(
                        normative_edition_id=UUID(str(artifact["normative_edition_id"])),
                        source_version_id=UUID(str(artifact["source_version_id"])),
                        structural_path=structural_path,
                        replay_fragment=matches[0],
                        expected_artifact_digest=str(artifact["content_digest"]),
                        verified_at=started_at,
                        verifier_identity=arguments.verifier_identity,
                    )
                except ValueError as error:
                    outcomes.append(_outcome(artifact, structural_path, "blocked", str(error)))
                    continue
                outcomes.append(
                    {
                        **_outcome(artifact, structural_path, "supported", None),
                        "provision_id": str(result.provision_id),
                        "provision_version": result.provision_version,
                        "page_numbers": list(result.page_numbers),
                        "critical_tokens": list(result.critical_tokens),
                        "verification_fingerprint": result.verification_fingerprint,
                        "provision_fingerprint": result.provision_fingerprint,
                        "reused": result.reused,
                    }
                )
        payload = _manifest(started_at, datetime.now(UTC), outcomes)
        arguments.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        arguments.output.chmod(0o600)
        print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
        return 0 if payload["summary"]["blocked"] == 0 else 2
    finally:
        engine.dispose()


def _load_artifacts(engine: sa.Engine) -> tuple[dict[str, Any], ...]:
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
                    "o.object_id=sv.object_id AND o.object_version=sv.object_version WHERE EXISTS "
                    "(SELECT 1 FROM platform.normative_provision_candidates pc WHERE "
                    "pc.normative_edition_id=ne.normative_edition_id AND "
                    "pc.source_version_id=na.source_version_id) ORDER BY nd.designation,"
                    "ne.normative_edition_id"
                )
            )
            .mappings()
            .all()
        )
    return tuple(dict(row) for row in rows)


def _candidate_paths(engine: sa.Engine, artifact: dict[str, Any]) -> tuple[str, ...]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT DISTINCT structural_path FROM platform.normative_provision_candidates "
                "WHERE normative_edition_id=:edition AND source_version_id=:source "
                "ORDER BY structural_path"
            ),
            {
                "edition": artifact["normative_edition_id"],
                "source": artifact["source_version_id"],
            },
        ).scalars()
    return tuple(str(value) for value in rows)


def _fragments_by_path(
    fragments: tuple[StructuralFragment, ...],
) -> dict[str, tuple[StructuralFragment, ...]]:
    grouped: dict[str, list[StructuralFragment]] = {}
    for fragment in fragments:
        grouped.setdefault(fragment.structural_path, []).append(fragment)
    return {path: tuple(values) for path, values in grouped.items()}


def _outcome(
    artifact: dict[str, Any], structural_path: str, status: str, blocker: str | None
) -> dict[str, Any]:
    return {
        "designation": str(artifact["designation"]),
        "normative_edition_id": str(artifact["normative_edition_id"]),
        "normative_artifact_id": str(artifact["normative_artifact_id"]),
        "source_version_id": str(artifact["source_version_id"]),
        "artifact_digest": str(artifact["content_digest"]),
        "structural_path": structural_path,
        "status": status,
        "blocker": blocker,
    }


def _manifest(
    started_at: datetime, completed_at: datetime, outcomes: list[dict[str, Any]]
) -> dict[str, Any]:
    counts = Counter(str(value["status"]) for value in outcomes)
    blocker_counts = Counter(
        str(value["blocker"]) for value in outcomes if value["blocker"] is not None
    )
    semantic_outcomes = [
        {key: value for key, value in outcome.items() if key != "reused"} for outcome in outcomes
    ]
    semantic_payload = {
        "schema": "ntd-native-provision-batch-v1",
        "outcomes": semantic_outcomes,
    }
    encoded = json.dumps(
        semantic_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "schema": semantic_payload["schema"],
        "outcomes": outcomes,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "semantic_fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "summary": {
            "denominator": len(outcomes),
            "supported": counts["supported"],
            "blocked": counts["blocked"],
            "reused": sum(bool(value.get("reused")) for value in outcomes),
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
    }


def _verify_object(path: Path, expected_digest: str, expected_size: int) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        raise ValueError("NTD_NATIVE_BATCH_SOURCE_OBJECT_INVALID")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if "sha256:" + digest.hexdigest() != expected_digest:
        raise ValueError("NTD_NATIVE_BATCH_SOURCE_DIGEST_MISMATCH")


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_NATIVE_BATCH_OBJECT_ROOT_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_NATIVE_BATCH_OBJECT_ROOT_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
