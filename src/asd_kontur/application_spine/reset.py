"""Single-owner local reset workflow over the canonical lifecycle state machine."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import zipfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import (
    AdapterHealth,
    AdapterOutcome,
    AdapterReceipt,
    AssuranceClass,
    Authority,
    Basis,
    DeletionItem,
    DeletionPlan,
    DestructionCoordinator,
    ExactVersionReference,
    InventoryItem,
    LifecycleState,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    RegistrySnapshot,
    RetentionProfile,
    StorageAdapterDefinition,
)
from asd_kontur.lifecycle.storage import StorageAdapter
from asd_kontur.persistence.scope import WorkspaceContext

from .models import ResetChallenge, ResetReceipt, WorkspaceSummary, semantic_digest
from .object_store import WorkspaceObjectStore
from .postgres import SpinePostgresRepository


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveResult:
    package_id: UUID
    package_digest: str
    manifest_digest: str
    item_count: int


class WorkspaceObjectLifecycleAdapter:
    """Exact object-key lifecycle adapter over the Product Spine object boundary."""

    def __init__(
        self,
        store: WorkspaceObjectStore,
        organization_id: UUID,
        definition: StorageAdapterDefinition,
    ) -> None:
        self._store = store
        self._organization_id = organization_id
        self.definition = definition
        self._receipts: dict[tuple[UUID, str], AdapterReceipt] = {}

    def inventory(self, workspace_id: UUID) -> tuple[InventoryItem, ...]:
        return tuple(
            InventoryItem(
                entry.object_key,
                workspace_id,
                "application/octet-stream",
                entry.size_bytes,
                entry.digest,
            )
            for entry in self._store.workspace_entries(
                organization_id=self._organization_id,
                workspace_id=workspace_id,
            )
        )

    def purge_item(self, *, workspace_id: UUID, item_id: str, operation_id: UUID) -> AdapterReceipt:
        key = (operation_id, item_id)
        prior = self._receipts.get(key)
        if prior is not None:
            return prior
        if item_id == "__inventory_empty__":
            before = 0
            deleted = False
        else:
            allowed = {item.item_id for item in self.inventory(workspace_id)}
            if item_id not in allowed:
                before = 0
                deleted = False
            else:
                before = 1
                deleted = self._store.delete(item_id)
        receipt = AdapterReceipt(
            uuid7(),
            self.definition.adapter_key,
            item_id,
            AdapterOutcome.DELETED if deleted else AdapterOutcome.ALREADY_ABSENT,
            before,
            0,
            operation_id,
            datetime.now(UTC),
        )
        self._receipts[key] = receipt
        return receipt

    def find_residue(
        self,
        *,
        workspace_id: UUID,
        known_ids: frozenset[str],
        known_digests: frozenset[str],
        known_fragments: frozenset[str],
    ) -> tuple[InventoryItem, ...]:
        del known_fragments
        return tuple(
            item
            for item in self.inventory(workspace_id)
            if item.item_id in known_ids or item.digest in known_digests
        )


class WorkspaceResetService:
    """Development-assurance reset; never claims independent production attestation."""

    def __init__(
        self,
        *,
        repository: SpinePostgresRepository,
        lifecycle: PostgresLifecycleRepository,
        lifecycle_engine: Engine,
        destruction_engine: Engine,
        object_store: WorkspaceObjectStore,
        archive_store_root: Path,
    ) -> None:
        if not archive_store_root.is_absolute() or not archive_store_root.is_dir():
            raise ValueError("archive store root must be a pre-created absolute directory")
        if archive_store_root.is_symlink():
            raise ValueError("archive store root may not be a symlink")
        self._repository = repository
        self._lifecycle = lifecycle
        self._lifecycle_engine = lifecycle_engine
        self._destruction_engine = destruction_engine
        self._objects = object_store
        self._archives = archive_store_root.resolve(strict=True)

    def prepare(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        correlation_id: UUID,
    ) -> ResetChallenge:
        workspace = self._repository.get_workspace(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
        )
        if workspace.lifecycle_state != LifecycleState.ACTIVE.value:
            raise ValueError("workspace_reset_requires_active_state")
        context = self._context(workspace, owner_identity_id, correlation_id)
        operation_id = uuid7()
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.FREEZING,
            operation_id,
        )
        cancelled = self._repository.cancel_jobs_for_reset(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
        )
        self._lifecycle.record_freeze_manifest(
            context=context,
            lifecycle_version=workspace.lifecycle_version,
            workspace_revision=workspace.workspace_revision,
            canonical_revision_digest=semantic_digest(
                {"workspace_id": workspace_id, "workspace_revision": workspace.workspace_revision}
            ),
            job_inventory={"cancelled": [str(value) for value in cancelled], "checkpointed": []},
            result="verified",
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.FROZEN,
            operation_id,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.FINALIZING,
            operation_id,
        )
        self._lifecycle.record_finalization_report(
            context=context,
            lifecycle_version=workspace.lifecycle_version,
            result_manifest_digest=semantic_digest(
                {"workspace_id": workspace_id, "outcome": "owner_reset_requested"}
            ),
            blockers=("PRODUCT_NOT_READY", "OWNER_REQUESTED_RESET"),
            uncertainties=(),
            mode_terminal_statuses={
                "Tender": "cancelled",
                "Support": "cancelled",
                "Audit": "cancelled",
                "Restoration": "cancelled",
            },
            outcome="verified",
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.FINALIZED,
            operation_id,
        )
        archive = self._archive(workspace)
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.EXPORTING,
            operation_id,
        )
        export_id = self._lifecycle.record_verified_export(
            context=context,
            workspace_revision=workspace.workspace_revision,
            idempotency_key=f"spine-reset-export:{operation_id}",
            package_digest=archive.package_digest,
            manifest_digest=archive.manifest_digest,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.EXPORTED,
            operation_id,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.ARCHIVING,
            operation_id,
        )
        self._lifecycle.record_verified_archive(
            context=context,
            export_operation_id=export_id,
            workspace_revision=workspace.workspace_revision,
            package_digest=archive.package_digest,
            manifest_digest=archive.manifest_digest,
            item_count=archive.item_count,
            storage_adapter_key="local.workspace-reset-archive-v0.1",
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.ARCHIVED,
            operation_id,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.CLOSED,
            operation_id,
        )
        confirmation_text = f"RESET {workspace.workspace_id} {secrets.token_urlsafe(18)}"
        expires_at = datetime.now(UTC) + timedelta(minutes=15)
        challenge = self._repository.create_reset_challenge(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            target_lifecycle_version=workspace.lifecycle_version + 1,
            archive_package_digest=archive.package_digest,
            confirmation_text=confirmation_text,
            expires_at=expires_at,
        )
        transitioned = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.RESET_PLANNING,
            operation_id,
        )
        if transitioned.lifecycle_version != challenge.target_lifecycle_version:
            raise RuntimeError("reset_challenge_lifecycle_version_mismatch")
        coordinator = self._coordinator(transitioned.organization_id)
        plan = coordinator.plan(
            operation_kind="reset",
            organization_id=transitioned.organization_id,
            workspace_id=workspace_id,
            lifecycle_version=transitioned.lifecycle_version,
            workspace_revision=transitioned.workspace_revision,
            profile=self._retention_profile(),
            basis=self._basis(archive.package_digest, expires_at),
            requester=self._requester(owner_identity_id),
            legal_hold_active=False,
            now=datetime.now(UTC),
            expires_at=expires_at,
        )
        self._lifecycle.persist_deletion_plan(context, plan)
        self._repository.bind_reset_challenge_plan(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            challenge_id=challenge.challenge_id,
            deletion_plan_id=plan.plan_id,
        )
        return challenge

    def execute(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        challenge_id: UUID,
        confirmation_text: str,
        correlation_id: UUID,
    ) -> ResetReceipt:
        organization_id, expected_version, archive_digest, plan_id = (
            self._repository.consume_reset_challenge(
                owner_identity_id=owner_identity_id,
                workspace_id=workspace_id,
                challenge_id=challenge_id,
                confirmation_text=confirmation_text,
            )
        )
        workspace = self._repository.get_workspace(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
        )
        if (
            workspace.lifecycle_state != LifecycleState.RESET_PLANNING.value
            or workspace.lifecycle_version != expected_version
        ):
            raise ValueError("reset_confirmation_stale")
        operation_id = uuid7()
        before = self._platform_fingerprint()
        now = datetime.now(UTC)
        plan = self._load_plan(organization_id, workspace_id, plan_id)
        coordinator = self._coordinator(organization_id)
        requester = self._requester(owner_identity_id)
        confirmer = Authority(
            f"human:local-confirmation:{challenge_id}",
            "human",
            frozenset({"workspace.reset.authorize"}),
        )
        executor = Authority(
            "service.product-spine-reset-executor",
            "service",
            frozenset({"workspace.purge.execute"}),
        )
        verifier = Authority(
            f"human:local-verifier:{challenge_id}",
            "human",
            frozenset({"workspace.reset.verify"}),
        )
        authorization = coordinator.authorize(
            plan=plan,
            requester=requester,
            confirmer=confirmer,
            executor=executor,
            verifier=verifier,
            current_lifecycle_version=workspace.lifecycle_version,
            legal_hold_active=False,
            now=now,
        )
        context = self._context(workspace, owner_identity_id, correlation_id)
        legal_hold_check_id = uuid7()
        self._lifecycle.persist_authorization(
            context,
            plan,
            authorization,
            legal_hold_check_id,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.RESET_AUTHORIZED,
            operation_id,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.PURGING,
            operation_id,
        )
        reset_outcome = coordinator.execute(
            plan=plan,
            authorization=authorization,
            executor=executor,
            legal_hold_active=False,
            now=datetime.now(UTC),
            operation_id=operation_id,
        )
        if not reset_outcome.complete:
            checkpoint = coordinator.checkpoint(
                plan=plan,
                outcome=reset_outcome,
                now=datetime.now(UTC),
            )
            self._lifecycle.persist_recovery_checkpoint(
                context=context,
                plan=plan,
                checkpoint=checkpoint,
            )
            self._transition(
                workspace,
                owner_identity_id,
                correlation_id,
                LifecycleState.RECOVERY_REQUIRED,
                operation_id,
            )
            raise RuntimeError("workspace_reset_reconciliation_required")
        self._lifecycle.persist_adapter_receipts(
            context=context,
            plan=plan,
            receipts=reset_outcome.receipts,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.VERIFYING_RESET,
            operation_id,
        )
        scans = coordinator.verify(
            plan=plan,
            known_ids=frozenset(item.item_id for item in plan.items),
            known_digests=frozenset(),
            known_fragments=frozenset(),
            now=datetime.now(UTC),
        )
        after = self._platform_fingerprint()
        if before != after:
            self._transition(
                workspace,
                owner_identity_id,
                correlation_id,
                LifecycleState.QUARANTINED,
                operation_id,
            )
            raise RuntimeError("platform_memory_changed_during_workspace_reset")
        attestation = coordinator.attest(
            plan=plan,
            authorization=authorization,
            receipts=reset_outcome.receipts,
            scans=scans,
            profile=self._retention_profile(),
            platform_integrity_before=before,
            platform_integrity_after=after,
            legal_hold_check_ids=(legal_hold_check_id,),
            verifier=verifier,
            now=datetime.now(UTC),
            requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
        )
        self._lifecycle.persist_verification_evidence(
            context=context,
            plan=plan,
            receipts=reset_outcome.receipts,
            scans=scans,
            attestation=attestation,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.RESET_VERIFIED,
            operation_id,
        )
        destroy_expires = datetime.now(UTC) + timedelta(minutes=10)
        destroy_plan = coordinator.plan(
            operation_kind="destroy",
            organization_id=organization_id,
            workspace_id=workspace_id,
            lifecycle_version=workspace.lifecycle_version,
            workspace_revision=workspace.workspace_revision,
            profile=self._retention_profile(),
            basis=self._basis(archive_digest, destroy_expires),
            requester=requester,
            legal_hold_active=False,
            now=datetime.now(UTC),
            expires_at=destroy_expires,
        )
        self._lifecycle.persist_deletion_plan(context, destroy_plan)
        destroy_confirmer = Authority(
            f"human:local-destroy-confirmation:{challenge_id}",
            "human",
            frozenset({"workspace.destroy.authorize"}),
        )
        destroy_executor = Authority(
            "service.product-spine-destroy-executor",
            "service",
            frozenset({"workspace.destroy.execute"}),
        )
        destroy_verifier = Authority(
            f"human:local-destroy-verifier:{challenge_id}",
            "human",
            frozenset({"workspace.destroy.verify"}),
        )
        destroy_authorization = coordinator.authorize(
            plan=destroy_plan,
            requester=requester,
            confirmer=destroy_confirmer,
            executor=destroy_executor,
            verifier=destroy_verifier,
            current_lifecycle_version=workspace.lifecycle_version,
            legal_hold_active=False,
            now=datetime.now(UTC),
        )
        destroy_hold_check = uuid7()
        self._lifecycle.persist_authorization(
            context,
            destroy_plan,
            destroy_authorization,
            destroy_hold_check,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.DESTROYING,
            operation_id,
        )
        destroy_outcome = coordinator.execute(
            plan=destroy_plan,
            authorization=destroy_authorization,
            executor=destroy_executor,
            legal_hold_active=False,
            now=datetime.now(UTC),
            operation_id=uuid7(),
        )
        destroy_scans = coordinator.verify(
            plan=destroy_plan,
            known_ids=frozenset(),
            known_digests=frozenset(),
            known_fragments=frozenset(),
            now=datetime.now(UTC),
        )
        destroy_attestation = coordinator.attest(
            plan=destroy_plan,
            authorization=destroy_authorization,
            receipts=destroy_outcome.receipts,
            scans=destroy_scans,
            profile=self._retention_profile(),
            platform_integrity_before=before,
            platform_integrity_after=self._platform_fingerprint(),
            legal_hold_check_ids=(destroy_hold_check,),
            verifier=destroy_verifier,
            now=datetime.now(UTC),
            requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
        )
        self._lifecycle.persist_verification_evidence(
            context=context,
            plan=destroy_plan,
            receipts=destroy_outcome.receipts,
            scans=destroy_scans,
            attestation=destroy_attestation,
        )
        workspace = self._transition(
            workspace,
            owner_identity_id,
            correlation_id,
            LifecycleState.DESTROYED,
            operation_id,
        )
        deleted_rows = sum(
            receipt.before_count - receipt.after_count
            for receipt in reset_outcome.receipts
            if receipt.adapter_key == "workspace.postgresql"
        )
        deleted_objects = sum(
            receipt.before_count - receipt.after_count
            for receipt in reset_outcome.receipts
            if receipt.adapter_key == "workspace.objects"
        )
        self._objects.purge_workspace(
            organization_id=organization_id,
            workspace_id=workspace_id,
        )
        completed_at = datetime.now(UTC)
        receipt_id = uuid7()
        receipt_digest = semantic_digest(
            {
                "reset_receipt_id": receipt_id,
                "workspace_id": workspace_id,
                "target_lifecycle_version": workspace.lifecycle_version,
                "archive_package_digest": archive_digest,
                "platform_fingerprint_before": before,
                "platform_fingerprint_after": after,
                "deleted_relation_row_count": deleted_rows,
                "deleted_object_count": deleted_objects,
                "outcome": "verified",
            }
        )
        with Session(self._lifecycle_engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO application.workspace_reset_terminal_receipts "
                    "(reset_receipt_id,organization_id,workspace_id,target_lifecycle_version,"
                    "archive_package_digest,platform_fingerprint_before,platform_fingerprint_after,"
                    "deleted_relation_row_count,deleted_object_count,assurance_profile,outcome,"
                    "receipt_digest,correlation_id,completed_at) VALUES "
                    "(:receipt,:organization,:workspace,:version,:archive,:before,:after,:rows,"
                    ":objects,'development_single_owner_confirmation','verified',:digest,"
                    ":correlation,:completed)"
                ),
                {
                    "receipt": receipt_id,
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "version": workspace.lifecycle_version,
                    "archive": archive_digest,
                    "before": before,
                    "after": after,
                    "rows": deleted_rows,
                    "objects": deleted_objects,
                    "digest": receipt_digest,
                    "correlation": correlation_id,
                    "completed": completed_at,
                },
            )
        return ResetReceipt(
            receipt_id,
            workspace_id,
            "verified",
            deleted_rows,
            deleted_objects,
            archive_digest,
            before,
            after,
            completed_at,
        )

    def _transition(
        self,
        workspace: WorkspaceSummary,
        owner_identity_id: str,
        correlation_id: UUID,
        target: LifecycleState,
        operation_id: UUID,
    ) -> WorkspaceSummary:
        decision = self._lifecycle.transition(
            context=self._context(workspace, owner_identity_id, correlation_id),
            expected_version=workspace.lifecycle_version,
            target_state=target,
            operation_key=f"spine.lifecycle:{operation_id}:{target.value}",
            semantic_digest=semantic_digest(
                {
                    "workspace_id": workspace.workspace_id,
                    "prior_version": workspace.lifecycle_version,
                    "target": target.value,
                }
            ),
            authority_reference="application.single-owner-local-lifecycle-v0.1",
        )
        if target is LifecycleState.DESTROYED:
            return replace(
                workspace,
                lifecycle_state=decision.new_state.value,
                lifecycle_version=decision.new_version,
                write_fenced=True,
            )
        return self._repository.get_workspace(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace.workspace_id,
        )

    @staticmethod
    def _context(
        workspace: WorkspaceSummary, owner_identity_id: str, correlation_id: UUID
    ) -> WorkspaceContext:
        return WorkspaceContext(
            workspace.organization_id,
            workspace.workspace_id,
            owner_identity_id,
            "service.product-spine-lifecycle-v0.1",
            correlation_id,
        )

    @staticmethod
    def _requester(owner_identity_id: str) -> Authority:
        return Authority(
            owner_identity_id,
            "human",
            frozenset({"workspace.reset.plan", "workspace.destroy.plan"}),
        )

    @staticmethod
    def _retention_profile() -> RetentionProfile:
        return RetentionProfile(
            ExactVersionReference("retention.spine-local", "0.1.0"),
            "development",
            frozenset({"workspace_canonical", "workspace_object_store"}),
            True,
            False,
        )

    @staticmethod
    def _basis(archive_digest: str, effective_until: datetime) -> Basis:
        return Basis(
            ExactVersionReference("basis.product-spine-owner-reset", "0.1.0"),
            "OWNER_CONFIRMED_WORKSPACE_RESET",
            (f"portable-archive:{archive_digest}",),
            effective_until,
        )

    def _coordinator(self, organization_id: UUID) -> DestructionCoordinator:
        postgres_definition = StorageAdapterDefinition(
            "workspace.postgresql",
            "2.1.0",
            "canonical",
            "workspace",
            "workspace",
            True,
            True,
            True,
            True,
            True,
            "2.1.0",
            AdapterHealth.AVAILABLE,
        )
        object_definition = StorageAdapterDefinition(
            "workspace.objects",
            "2.1.0",
            "workspace_object_store",
            "authoritative",
            "workspace",
            True,
            True,
            True,
            True,
            True,
            "2.1.0",
            AdapterHealth.AVAILABLE,
        )
        adapters: tuple[StorageAdapter, ...] = (
            PostgresWorkspaceStorageAdapter(
                self._destruction_engine,
                organization_id,
                postgres_definition,
            ),
            WorkspaceObjectLifecycleAdapter(
                self._objects,
                organization_id,
                object_definition,
            ),
        )
        return DestructionCoordinator(
            RegistrySnapshot(
                ExactVersionReference("storage-adapters.product-spine", "2.1.0"),
                adapters,
            )
        )

    def _load_plan(self, organization_id: UUID, workspace_id: UUID, plan_id: UUID) -> DeletionPlan:
        with Session(self._lifecycle_engine) as session, session.begin():
            session.execute(
                sa.select(
                    sa.func.set_config("asd.organization_id", str(organization_id), True),
                    sa.func.set_config("asd.workspace_id", str(workspace_id), True),
                )
            ).one()
            row = session.execute(
                sa.text(
                    "SELECT * FROM workspace.deletion_plans WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND deletion_plan_id=:plan AND plan_version=1"
                ),
                {"organization": organization_id, "workspace": workspace_id, "plan": plan_id},
            ).one_or_none()
        if row is None:
            raise RuntimeError("workspace_reset_deletion_plan_missing")
        plan = DeletionPlan(
            UUID(str(row.deletion_plan_id)),
            int(row.plan_version),
            str(row.operation_kind),
            organization_id,
            workspace_id,
            int(row.lifecycle_version),
            int(row.workspace_revision),
            ExactVersionReference(
                str(row.retention_profile_key), str(row.retention_profile_version)
            ),
            Basis(
                ExactVersionReference(str(row.basis_registry_key), str(row.basis_registry_version)),
                str(row.basis_code),
                tuple(str(value) for value in row.basis_evidence_refs),
                row.expires_at,
            ),
            row.legal_hold_checked_at,
            str(row.inventory_digest),
            ExactVersionReference(str(row.adapter_registry_key), str(row.adapter_registry_version)),
            tuple(
                DeletionItem(str(value["adapter_key"]), str(value["item_id"]), str(value["action"]))
                for value in row.deletion_items
            ),
            tuple(str(value) for value in row.expected_residue_classes),
            str(row.requester_identity_id),
            str(row.dry_run_result) == "complete",
            row.expires_at,
        )
        # PostgreSQL stores the immutable canonical digest produced at planning time. Datetime
        # round-tripping may normalize an equivalent UTC representation, so authorization binds
        # the exact persisted digest after every typed field above has been reconstructed.
        object.__setattr__(plan, "digest", str(row.plan_digest))
        return plan

    def _archive(self, workspace: WorkspaceSummary) -> WorkspaceArchiveResult:
        entries = self._objects.workspace_entries(
            organization_id=workspace.organization_id,
            workspace_id=workspace.workspace_id,
        )
        package_id = uuid7()
        manifest = {
            "package_id": str(package_id),
            "package_version": "2.1.0",
            "package_type": "workspace_reset_portable_archive",
            "organization_id": str(workspace.organization_id),
            "workspace_id": str(workspace.workspace_id),
            "workspace_revision": workspace.workspace_revision,
            "entries": [
                {
                    "logical_path": entry.object_key,
                    "size_bytes": entry.size_bytes,
                    "digest": entry.digest,
                }
                for entry in entries
            ],
            "import_semantics": "new_workspace_only",
        }
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
        target = self._archives / str(workspace.organization_id) / str(workspace.workspace_id)
        target.mkdir(parents=True, mode=0o700)
        package_path = target / f"{package_id}.zip"
        with zipfile.ZipFile(package_path, "x", compression=zipfile.ZIP_STORED) as package:
            package.writestr(_zip_info("manifest.json"), manifest_bytes)
            for entry in entries:
                with (
                    entry.path.open("rb") as source,
                    package.open(_zip_info(f"objects/{entry.object_key}"), "w") as output,
                ):
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
        os.chmod(package_path, 0o400)
        package_digest = _path_digest(package_path)
        return WorkspaceArchiveResult(package_id, package_digest, manifest_digest, len(entries))

    def _platform_fingerprint(self) -> str:
        status = self._repository.platform_knowledge_status()
        return semantic_digest(
            {
                "practice_guides": status.practice_guide_count,
                "practice_editions": status.practice_edition_count,
                "practice_release": status.active_practice_release_count,
                "source_guidance": status.source_guidance_count,
                "intelligence": status.active_intelligence_count,
                "playbooks": status.active_playbook_count,
                "gaps": status.active_gap_count,
                "conflicts": status.conflict_count,
                "quarantine": status.quarantine_count,
                "ntd_identities": status.normative_identity_count,
                "ntd_editions": status.verified_normative_edition_count,
                "ntd_provisions": status.verified_normative_provision_count,
                "rule_versions": status.rule_version_count,
                "semantic_fingerprints": status.semantic_fingerprints,
            }
        )


def _zip_info(name: str) -> zipfile.ZipInfo:
    value = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    value.compress_type = zipfile.ZIP_STORED
    value.external_attr = 0o100400 << 16
    return value


def _path_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
