"""NTD canonical backup fingerprints and rebuildable lexical projection."""

# ruff: noqa: E501 -- explicit SQL supports integrity review.

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.harness.models import digest_of
from asd_kontur.knowledge.object_store import ObjectStorePort

from .models import NtdBackupManifest

NTD_PROJECTION_PROFILE_VERSION = "ntd_exact_fts_projection_v0.1"


class NtdDurabilityError(RuntimeError):
    pass


def build_backup_manifest(
    engine: Engine,
    *,
    seed_manifest_fingerprint: str,
    created_at: datetime | None = None,
) -> NtdBackupManifest:
    with Session(engine) as session:
        sources = tuple(
            (UUID(str(row[0])), str(row[1]))
            for row in session.execute(
                sa.text(
                    "SELECT DISTINCT sv.source_version_id,sv.content_digest "
                    "FROM platform.source_versions sv "
                    "WHERE sv.source_version_id IN ("
                    "SELECT source_version_id FROM platform.normative_artifacts UNION "
                    "SELECT source_version_id FROM platform.ntd_seed_manifests) "
                    "ORDER BY sv.source_version_id"
                )
            ).all()
        )
        editions = tuple(
            (UUID(str(row[0])), str(row[1]))
            for row in session.execute(
                sa.text(
                    "SELECT normative_edition_id,edition_fingerprint "
                    "FROM platform.normative_editions WHERE edition_fingerprint IS NOT NULL "
                    "ORDER BY normative_edition_id"
                )
            ).all()
        )
        provisions = tuple(
            (UUID(str(row[0])), int(row[1]), str(row[2]))
            for row in session.execute(
                sa.text(
                    "SELECT normative_provision_id,version,semantic_fingerprint "
                    "FROM platform.normative_provision_versions "
                    "WHERE verification_status='verified' "
                    "ORDER BY normative_provision_id,version"
                )
            ).all()
        )
        activations = tuple(
            (UUID(str(row[0])), int(row[1]))
            for row in session.execute(
                sa.text(
                    "SELECT activation_decision_id,version FROM platform.normative_activation_decisions "
                    "ORDER BY activation_decision_id,version"
                )
            ).all()
        )
        gaps = tuple(
            str(value)
            for value in session.execute(
                sa.text("SELECT gap_fingerprint FROM platform.ntd_gaps ORDER BY gap_fingerprint")
            ).scalars()
        )
        conflicts = tuple(
            str(value)
            for value in session.execute(
                sa.text(
                    "SELECT conflict_fingerprint FROM platform.ntd_conflicts "
                    "ORDER BY conflict_fingerprint"
                )
            ).scalars()
        )
    canonical_payload = {
        "seed_manifest_fingerprint": seed_manifest_fingerprint,
        "sources": sources,
        "editions": editions,
        "provisions": provisions,
        "activations": activations,
        "gaps": gaps,
        "conflicts": conflicts,
    }
    return NtdBackupManifest(
        backup_manifest_id=uuid7(),
        version=1,
        seed_manifest_fingerprint=seed_manifest_fingerprint,
        source_versions=sources,
        edition_fingerprints=editions,
        provision_fingerprints=provisions,
        activation_decision_refs=activations,
        gap_fingerprints=gaps,
        conflict_fingerprints=conflicts,
        projection_profile_version=NTD_PROJECTION_PROFILE_VERSION,
        canonical_semantic_fingerprint=digest_of(canonical_payload),
        created_at=created_at or datetime.now(UTC),
    )


def persist_backup_manifest(engine: Engine, manifest: NtdBackupManifest) -> bool:
    with Session(engine) as session, session.begin():
        existing = session.execute(
            sa.text(
                "SELECT backup_manifest_id FROM platform.ntd_backup_manifests "
                "WHERE seed_manifest_fingerprint=:seed AND canonical_semantic_fingerprint=:semantic"
            ),
            {
                "seed": manifest.seed_manifest_fingerprint,
                "semantic": manifest.canonical_semantic_fingerprint,
            },
        ).scalar_one_or_none()
        if existing is not None:
            return True
        session.execute(
            sa.text(
                "INSERT INTO platform.ntd_backup_manifests "
                "(backup_manifest_id,version,seed_manifest_fingerprint,source_versions,"
                "edition_fingerprints,provision_fingerprints,activation_decision_refs,"
                "gap_fingerprints,conflict_fingerprints,projection_profile_version,"
                "canonical_semantic_fingerprint,created_at) VALUES "
                "(:id,:version,:seed,CAST(:sources AS jsonb),CAST(:editions AS jsonb),"
                "CAST(:provisions AS jsonb),CAST(:activations AS jsonb),:gaps,:conflicts,"
                ":projection,:semantic,:created)"
            ),
            {
                "id": manifest.backup_manifest_id,
                "version": manifest.version,
                "seed": manifest.seed_manifest_fingerprint,
                "sources": json.dumps(
                    [(str(key), value) for key, value in manifest.source_versions]
                ),
                "editions": json.dumps(
                    [(str(key), value) for key, value in manifest.edition_fingerprints]
                ),
                "provisions": json.dumps(
                    [
                        (str(key), version, value)
                        for key, version, value in manifest.provision_fingerprints
                    ]
                ),
                "activations": json.dumps(
                    [(str(key), version) for key, version in manifest.activation_decision_refs]
                ),
                "gaps": list(manifest.gap_fingerprints),
                "conflicts": list(manifest.conflict_fingerprints),
                "projection": manifest.projection_profile_version,
                "semantic": manifest.canonical_semantic_fingerprint,
                "created": manifest.created_at,
            },
        )
    return False


def verify_restored_memory(engine: Engine, expected: NtdBackupManifest) -> None:
    actual = build_backup_manifest(
        engine,
        seed_manifest_fingerprint=expected.seed_manifest_fingerprint,
        created_at=expected.created_at,
    )
    if actual.canonical_semantic_fingerprint != expected.canonical_semantic_fingerprint:
        raise NtdDurabilityError("NTD_RESTORE_SEMANTIC_FINGERPRINT_MISMATCH")
    if actual.source_versions != expected.source_versions:
        raise NtdDurabilityError("NTD_RESTORE_SOURCE_DIGEST_MISMATCH")


def verify_source_objects(engine: Engine, object_store: ObjectStorePort) -> int:
    with Session(engine) as session:
        rows = session.execute(
            sa.text(
                "SELECT DISTINCT sv.object_id,sv.content_digest FROM platform.source_versions sv "
                "WHERE sv.source_version_id IN ("
                "SELECT source_version_id FROM platform.normative_artifacts UNION "
                "SELECT source_version_id FROM platform.ntd_seed_manifests) "
                "ORDER BY sv.object_id"
            )
        ).all()
    for object_id, expected_digest in rows:
        receipt = object_store.head(f"platform/source/{object_id}")
        if receipt is None or receipt.digest != expected_digest or not receipt.verified:
            raise NtdDurabilityError("NTD_SOURCE_OBJECT_INTEGRITY_FAILED")
    return len(rows)


class NtdProjectionBuilder:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def rebuild(self, canonical_semantic_fingerprint: str) -> tuple[UUID, int]:
        version_id = deterministic_uuid(
            f"ntd-lexical-projection:{NTD_PROJECTION_PROFILE_VERSION}:"
            f"{canonical_semantic_fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT status FROM projection.ntd_lexical_versions "
                    "WHERE lexical_version_id=:id"
                ),
                {"id": version_id},
            ).scalar_one_or_none()
            if existing in {"ready", "empty"}:
                count = int(
                    session.execute(
                        sa.text(
                            "SELECT count(*) FROM projection.ntd_lexical_entries "
                            "WHERE lexical_version_id=:id"
                        ),
                        {"id": version_id},
                    ).scalar_one()
                )
                return version_id, count
            session.execute(
                sa.text(
                    "INSERT INTO projection.ntd_lexical_versions "
                    "(lexical_version_id,profile_version,canonical_semantic_fingerprint,status) "
                    "VALUES (:id,:profile,:semantic,'building')"
                ),
                {
                    "id": version_id,
                    "profile": NTD_PROJECTION_PROFILE_VERSION,
                    "semantic": canonical_semantic_fingerprint,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO projection.ntd_lexical_entries "
                    "(lexical_version_id,normative_provision_id,normative_provision_version,"
                    "normative_edition_id,structural_path,verbatim_text) "
                    "SELECT :id,normative_provision_id,version,normative_edition_id,"
                    "structural_path,verbatim_text FROM platform.normative_provision_versions "
                    "WHERE verification_status='verified'"
                ),
                {"id": version_id},
            )
            count = int(
                session.execute(
                    sa.text(
                        "SELECT count(*) FROM projection.ntd_lexical_entries "
                        "WHERE lexical_version_id=:id"
                    ),
                    {"id": version_id},
                ).scalar_one()
            )
            session.execute(
                sa.text(
                    "UPDATE projection.ntd_lexical_versions SET status=:status,built_at=:built "
                    "WHERE lexical_version_id=:id"
                ),
                {
                    "id": version_id,
                    "status": "ready" if count else "empty",
                    "built": datetime.now(UTC),
                },
            )
        return version_id, count

    def delete_rebuildable_plane(self) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(sa.text("DELETE FROM projection.ntd_lexical_versions"))
