"""Scoped PostgreSQL persistence for immutable Harness versions."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.harness.models import digest_of
from asd_kontur.persistence.scope import WorkspaceContext

from .durability import rebuild_projection_entries
from .models import (
    ConstructionHarnessContextPack,
    ConstructionWorkPackage,
    HarnessBackupManifest,
    ProjectCharacteristicCandidate,
    ProjectDefinition,
    VerifiedProjectCharacteristic,
    WorkRequirementMatrix,
)


class ConstructionHarnessRepository:
    """Write immutable versions under a transaction-local workspace scope."""

    def __init__(self, engine: Engine, context: WorkspaceContext) -> None:
        self._engine = engine
        self._context = context

    def register_project(self, project: ProjectDefinition) -> None:
        self._require_scope(project.organization_id, project.workspace_id)
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_definition_versions "
                    "(organization_id,workspace_id,project_definition_id,version,purpose,"
                    "object_class,source_version_ids,definition,fingerprint,created_at) VALUES "
                    "(:organization,:workspace,:project,:version,:purpose,:object_class,"
                    ":sources,CAST(:definition AS jsonb),:fingerprint,:created_at) ON CONFLICT "
                    "(organization_id,workspace_id,fingerprint) DO NOTHING"
                ),
                {
                    "organization": project.organization_id,
                    "workspace": project.workspace_id,
                    "project": project.project_definition_id,
                    "version": project.version,
                    "purpose": project.purpose,
                    "object_class": project.object_class,
                    "sources": list(project.source_version_ids),
                    "definition": _json(project),
                    "fingerprint": project.fingerprint,
                    "created_at": project.created_at,
                },
            )
            session.commit()

    def register_characteristic_candidate(
        self,
        *,
        project: ProjectDefinition,
        candidate: ProjectCharacteristicCandidate,
        created_at: datetime,
    ) -> None:
        self._require_scope(project.organization_id, project.workspace_id)
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_characteristic_candidates VALUES "
                    "(:organization,:workspace,:candidate,:version,:project,:project_version,"
                    ":key,CAST(:value AS jsonb),:profile,:source,:locator,:evidence,:digest,"
                    ":status,:created_at)"
                ),
                {
                    "organization": project.organization_id,
                    "workspace": project.workspace_id,
                    "candidate": candidate.candidate_id,
                    "version": candidate.version,
                    "project": project.project_definition_id,
                    "project_version": project.version,
                    "key": candidate.characteristic_key,
                    "value": _json(candidate.value),
                    "profile": candidate.extraction_profile_version,
                    "source": candidate.evidence.source_version_id,
                    "locator": candidate.evidence.locator,
                    "evidence": candidate.evidence.evidence_link_id,
                    "digest": candidate.evidence.content_digest,
                    "status": candidate.status,
                    "created_at": created_at,
                },
            )
            session.commit()

    def register_verified_characteristic(
        self,
        *,
        verified: VerifiedProjectCharacteristic,
        created_at: datetime,
    ) -> None:
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.verified_project_characteristics VALUES "
                    "(:organization,:workspace,:characteristic,:version,:candidate,"
                    ":candidate_version,:key,CAST(:value AS jsonb),:profile,:receipt,:source,"
                    ":locator,:evidence,:created_at)"
                ),
                {
                    "organization": self._context.organization_id,
                    "workspace": self._context.workspace_id,
                    "characteristic": verified.characteristic_id,
                    "version": verified.version,
                    "candidate": verified.candidate_id,
                    "candidate_version": verified.candidate_version,
                    "key": verified.characteristic_key,
                    "value": _json(verified.value),
                    "profile": verified.validation_profile_version,
                    "receipt": verified.validation_receipt_digest,
                    "source": verified.evidence.source_version_id,
                    "locator": verified.evidence.locator,
                    "evidence": verified.evidence.evidence_link_id,
                    "created_at": created_at,
                },
            )
            session.commit()

    def register_work_package(
        self,
        *,
        project: ProjectDefinition,
        work_package: ConstructionWorkPackage,
        created_at: datetime,
    ) -> None:
        self._require_scope(project.organization_id, work_package.workspace_id)
        fingerprint = digest_of(work_package)
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.construction_work_package_versions "
                    "(organization_id,workspace_id,work_package_id,version,"
                    "project_definition_id,project_definition_version,work_type_key,"
                    "work_type_version,package,fingerprint,created_at) VALUES "
                    "(:organization,:workspace,:package,:version,:project,:project_version,"
                    ":work_type,:work_type_version,CAST(:document AS jsonb),:fingerprint,"
                    ":created_at) ON CONFLICT "
                    "(organization_id,workspace_id,fingerprint) DO NOTHING"
                ),
                {
                    "organization": self._context.organization_id,
                    "workspace": self._context.workspace_id,
                    "package": work_package.work_package_id,
                    "version": work_package.version,
                    "project": project.project_definition_id,
                    "project_version": project.version,
                    "work_type": work_package.work_type_key,
                    "work_type_version": work_package.work_type_version,
                    "document": _json(work_package),
                    "fingerprint": fingerprint,
                    "created_at": created_at,
                },
            )
            session.commit()

    def register_matrix(self, matrix: WorkRequirementMatrix) -> None:
        self._require_scope(matrix.organization_id, matrix.workspace_id)
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.work_requirement_matrix_versions VALUES "
                    "(:organization,:workspace,:matrix,:version,:project,:project_version,"
                    ":rule_set,CAST(:document AS jsonb),:fingerprint,:created_at) ON CONFLICT "
                    "(organization_id,workspace_id,fingerprint) DO NOTHING"
                ),
                {
                    "organization": matrix.organization_id,
                    "workspace": matrix.workspace_id,
                    "matrix": matrix.matrix_id,
                    "version": matrix.version,
                    "project": matrix.project_definition_id,
                    "project_version": matrix.project_definition_version,
                    "rule_set": matrix.rule_set_version_id,
                    "document": _json(matrix),
                    "fingerprint": matrix.fingerprint,
                    "created_at": matrix.created_at,
                },
            )
            session.commit()

    def register_context_pack(self, pack: ConstructionHarnessContextPack) -> None:
        self._require_scope(pack.organization_id, pack.workspace_id)
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.construction_harness_context_packs VALUES "
                    "(:organization,:workspace,:pack,:contract,:project,:project_version,"
                    ":matrix,:matrix_version,:matrix_fingerprint,CAST(:document AS jsonb),"
                    ":fingerprint,:assembled_at) ON CONFLICT "
                    "(organization_id,workspace_id,fingerprint) DO NOTHING"
                ),
                {
                    "organization": pack.organization_id,
                    "workspace": pack.workspace_id,
                    "pack": pack.context_pack_id,
                    "contract": pack.contract_version,
                    "project": pack.project_definition_ref[0],
                    "project_version": pack.project_definition_ref[1],
                    "matrix": pack.matrix_ref[0],
                    "matrix_version": pack.matrix_ref[1],
                    "matrix_fingerprint": pack.matrix_fingerprint,
                    "document": _json(pack),
                    "fingerprint": pack.fingerprint,
                    "assembled_at": pack.assembled_at,
                },
            )
            session.commit()

    def register_backup(self, manifest: HarnessBackupManifest) -> None:
        with self._session() as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.construction_harness_backup_manifests VALUES "
                    "(:organization,:workspace,:manifest,:version,:project,:matrix,:context,"
                    ":platform,:projection,:semantic,:created_at)"
                ),
                {
                    "organization": self._context.organization_id,
                    "workspace": self._context.workspace_id,
                    "manifest": manifest.manifest_id,
                    "version": manifest.version,
                    "project": manifest.project_definition_fingerprint,
                    "matrix": manifest.matrix_fingerprint,
                    "context": manifest.context_pack_fingerprint,
                    "platform": list(manifest.platform_memory_fingerprints),
                    "projection": manifest.projection_profile_version,
                    "semantic": manifest.semantic_fingerprint,
                    "created_at": datetime.combine(manifest.created_on, datetime.min.time()),
                },
            )
            session.commit()

    def _session(self) -> Session:
        session = Session(self._engine, autoflush=False, expire_on_commit=False)
        session.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(self._context.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(self._context.workspace_id), True),
            )
        ).one()
        return session

    def _require_scope(self, organization_id: UUID, workspace_id: UUID) -> None:
        if (organization_id, workspace_id) != (
            self._context.organization_id,
            self._context.workspace_id,
        ):
            raise ValueError("Harness repository scope mismatch")


class ConstructionHarnessProjectionRepository:
    """Delete and rebuild only the disposable matrix retrieval projection."""

    def __init__(self, engine: Engine, context: WorkspaceContext) -> None:
        self._engine = engine
        self._context = context

    def rebuild(self, matrix: WorkRequirementMatrix, profile_version: str) -> str:
        if profile_version.lower() == "latest":
            raise ValueError("projection profile must be pinned")
        if (matrix.organization_id, matrix.workspace_id) != (
            self._context.organization_id,
            self._context.workspace_id,
        ):
            raise ValueError("projection scope mismatch")
        entries = rebuild_projection_entries(matrix)
        with self._engine.begin() as connection:
            _set_connection_scope(connection, self._context)
            connection.execute(
                sa.text(
                    "DELETE FROM projection.construction_harness_matrix_entries "
                    "WHERE matrix_id=:matrix AND matrix_version=:version"
                ),
                {"matrix": matrix.matrix_id, "version": matrix.version},
            )
            for row, entry in zip(matrix.rows, entries, strict=True):
                connection.execute(
                    sa.text(
                        "INSERT INTO projection.construction_harness_matrix_entries "
                        "(organization_id,workspace_id,matrix_id,matrix_version,work_package_id,"
                        "matrix_fingerprint,projection_profile_version,entry) VALUES "
                        "(:organization,:workspace,:matrix,:version,:work,:fingerprint,:profile,"
                        "CAST(:entry AS jsonb))"
                    ),
                    {
                        "organization": matrix.organization_id,
                        "workspace": matrix.workspace_id,
                        "matrix": matrix.matrix_id,
                        "version": matrix.version,
                        "work": row.work_package_id,
                        "fingerprint": matrix.fingerprint,
                        "profile": profile_version,
                        "entry": _json(entry),
                    },
                )
        return digest_of(entries)

    def delete_rebuildable_plane(self, matrix: WorkRequirementMatrix) -> None:
        with self._engine.begin() as connection:
            _set_connection_scope(connection, self._context)
            connection.execute(
                sa.text(
                    "DELETE FROM projection.construction_harness_matrix_entries "
                    "WHERE matrix_id=:matrix AND matrix_version=:version"
                ),
                {"matrix": matrix.matrix_id, "version": matrix.version},
            )


def _set_connection_scope(connection: sa.Connection, context: WorkspaceContext) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    ).one()


def _json(value: object) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (UUID, date, datetime, Decimal, StrEnum)):
        return str(value)
    return value
