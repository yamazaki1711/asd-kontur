"""Permanent practice-memory backup manifest and restore integrity checks."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import ContextAssemblyPolicy, PracticeMemoryBackupManifest


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def canonical_semantic_fingerprint(
    *,
    source_version_id: UUID,
    construction_fingerprint: str,
    coverage_manifest_fingerprint: str,
    intelligence_unit_digests: Iterable[str],
    playbook_digests: Iterable[str],
    context_assembly_policy_fingerprint: str,
) -> str:
    return digest_of(
        {
            "source_version_id": str(source_version_id),
            "construction_fingerprint": construction_fingerprint,
            "coverage_manifest_fingerprint": coverage_manifest_fingerprint,
            "intelligence_units": sorted(intelligence_unit_digests),
            "playbooks": sorted(playbook_digests),
            "context_assembly_policy_fingerprint": context_assembly_policy_fingerprint,
        }
    )


def build_backup_manifest(
    *,
    practice_guide_edition_id: UUID,
    source_version_id: UUID,
    source_bytes: bytes,
    construction_manifest_id: UUID,
    construction_fingerprint: str,
    coverage_manifest_fingerprint: str,
    activation_decision_id: UUID,
    activation_decision_version: int,
    intelligence_unit_digests: Iterable[str],
    playbook_digests: Iterable[str],
    context_policy: ContextAssemblyPolicy,
    projection_fingerprints: tuple[dict[str, str], ...],
    backup_object_reference: str,
    recorded_at: datetime | None = None,
) -> PracticeMemoryBackupManifest:
    source_digest = sha256_bytes(source_bytes)
    unit_digests = tuple(intelligence_unit_digests)
    playbook_values = tuple(playbook_digests)
    semantic = canonical_semantic_fingerprint(
        source_version_id=source_version_id,
        construction_fingerprint=construction_fingerprint,
        coverage_manifest_fingerprint=coverage_manifest_fingerprint,
        intelligence_unit_digests=unit_digests,
        playbook_digests=playbook_values,
        context_assembly_policy_fingerprint=context_policy.fingerprint,
    )
    manifest_id = deterministic_uuid(
        f"practice-memory-backup:{practice_guide_edition_id}:{source_version_id}:"
        f"{construction_manifest_id}:{activation_decision_id}:{activation_decision_version}:"
        f"{context_policy.policy_id}:{context_policy.version}:{semantic}"
    )
    return PracticeMemoryBackupManifest(
        backup_manifest_id=manifest_id,
        version=1,
        practice_guide_edition_id=practice_guide_edition_id,
        source_version_id=source_version_id,
        source_object_digest=source_digest,
        construction_manifest_id=construction_manifest_id,
        construction_fingerprint=construction_fingerprint,
        coverage_manifest_fingerprint=coverage_manifest_fingerprint,
        activation_decision_id=activation_decision_id,
        activation_decision_version=activation_decision_version,
        context_assembly_policy_id=context_policy.policy_id,
        context_assembly_policy_version=context_policy.version,
        context_assembly_policy_fingerprint=context_policy.fingerprint,
        canonical_semantic_fingerprint=semantic,
        projection_fingerprints=projection_fingerprints,
        backup_object_reference=backup_object_reference,
        recorded_at=recorded_at or datetime.now(UTC),
    )


def verify_restored_practice_memory(
    *,
    manifest: PracticeMemoryBackupManifest,
    restored_source_bytes: bytes,
    construction_fingerprint: str,
    coverage_manifest_fingerprint: str,
    intelligence_unit_digests: Iterable[str],
    playbook_digests: Iterable[str],
    context_policy: ContextAssemblyPolicy,
) -> None:
    if sha256_bytes(restored_source_bytes) != manifest.source_object_digest:
        raise ValueError("practice_memory_source_digest_mismatch")
    if construction_fingerprint != manifest.construction_fingerprint:
        raise ValueError("practice_memory_construction_fingerprint_mismatch")
    if coverage_manifest_fingerprint != manifest.coverage_manifest_fingerprint:
        raise ValueError("practice_memory_coverage_fingerprint_mismatch")
    if context_policy.policy_id != manifest.context_assembly_policy_id or (
        context_policy.version != manifest.context_assembly_policy_version
    ):
        raise ValueError("practice_memory_context_policy_identity_mismatch")
    if context_policy.fingerprint != manifest.context_assembly_policy_fingerprint:
        raise ValueError("practice_memory_context_policy_fingerprint_mismatch")
    semantic = canonical_semantic_fingerprint(
        source_version_id=manifest.source_version_id,
        construction_fingerprint=construction_fingerprint,
        coverage_manifest_fingerprint=coverage_manifest_fingerprint,
        intelligence_unit_digests=intelligence_unit_digests,
        playbook_digests=playbook_digests,
        context_assembly_policy_fingerprint=context_policy.fingerprint,
    )
    if semantic != manifest.canonical_semantic_fingerprint:
        raise ValueError("practice_memory_semantic_fingerprint_mismatch")
