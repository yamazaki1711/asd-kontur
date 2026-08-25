"""Canonical backup fingerprints and rebuildable Harness projections."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from .models import (
    ConstructionHarnessContextPack,
    HarnessBackupManifest,
    ProjectDefinition,
    WorkRequirementMatrix,
)


def build_harness_backup_manifest(
    *,
    manifest_id: UUID,
    project: ProjectDefinition,
    matrix: WorkRequirementMatrix,
    context_pack: ConstructionHarnessContextPack,
    platform_memory_fingerprints: tuple[str, ...],
    projection_profile_version: str,
    created_on: date,
) -> HarnessBackupManifest:
    return HarnessBackupManifest(
        manifest_id,
        1,
        project.fingerprint,
        matrix.fingerprint,
        context_pack.fingerprint,
        platform_memory_fingerprints,
        projection_profile_version,
        created_on,
    )


def rebuild_projection_entries(matrix: WorkRequirementMatrix) -> tuple[dict[str, str], ...]:
    """Rebuild a disposable exact/lexical projection from canonical matrix rows."""
    return tuple(
        {
            "matrix_id": str(matrix.matrix_id),
            "matrix_version": str(matrix.version),
            "matrix_fingerprint": matrix.fingerprint,
            "work_package_id": str(row.work_package_id),
            "document_requirement_ids": ",".join(
                sorted(str(item.document_requirement_id) for item in row.documents)
            ),
            "normative_gaps": ",".join(sorted(row.normative_gaps)),
        }
        for row in matrix.rows
    )


def verify_restored_harness(
    *,
    manifest: HarnessBackupManifest,
    project: ProjectDefinition,
    matrix: WorkRequirementMatrix,
    context_pack: ConstructionHarnessContextPack,
) -> None:
    restored = (
        project.fingerprint,
        matrix.fingerprint,
        context_pack.fingerprint,
    )
    expected = (
        manifest.project_definition_fingerprint,
        manifest.matrix_fingerprint,
        manifest.context_pack_fingerprint,
    )
    if restored != expected:
        raise ValueError("restored Harness canonical semantic fingerprint mismatch")
