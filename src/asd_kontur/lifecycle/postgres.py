"""Narrow PostgreSQL lifecycle transition and workspace-row storage adapters."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.persistence.scope import WorkspaceContext

from .errors import LifecycleError, LifecycleErrorCode
from .models import (
    AdapterOutcome,
    AdapterReceipt,
    DeletionPlan,
    DestructionAttestation,
    DestructiveAuthorization,
    InventoryItem,
    LifecycleState,
    RecoveryCheckpoint,
    ResidualScan,
    StorageAdapterDefinition,
)
from .operations import ArchiveImportDecision
from .state_machine import TransitionDecision


class PostgresLifecycleRepository:
    """Invoke the only database path permitted to change lifecycle state."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def transition(
        self,
        *,
        context: WorkspaceContext,
        expected_version: int,
        target_state: LifecycleState,
        operation_key: str,
        semantic_digest: str,
        authority_reference: str,
    ) -> TransitionDecision:
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            try:
                with session.begin():
                    _set_scope(session, context)
                    prior_state = session.scalar(
                        sa.text(
                            "SELECT lifecycle_state FROM workspace.workspaces "
                            "WHERE organization_id=:organization AND workspace_id=:workspace"
                        ),
                        {
                            "organization": context.organization_id,
                            "workspace": context.workspace_id,
                        },
                    )
                    row = session.execute(
                        sa.text(
                            "SELECT * FROM workspace.transition_lifecycle("
                            ":organization,:workspace,:expected,:target,:operation,:digest,"
                            ":actor,:service,:authority,:correlation,:causation)"
                        ),
                        {
                            "organization": context.organization_id,
                            "workspace": context.workspace_id,
                            "expected": expected_version,
                            "target": target_state.value,
                            "operation": operation_key,
                            "digest": semantic_digest,
                            "actor": context.actor_identity_id,
                            "service": context.service_identity_id,
                            "authority": authority_reference,
                            "correlation": context.correlation_id,
                            "causation": context.causation_id,
                        },
                    ).one()
            except sa.exc.DBAPIError as exc:
                message = str(exc.orig).lower()
                code = (
                    LifecycleErrorCode.CONCURRENCY_CONFLICT
                    if "concurrency" in message
                    else LifecycleErrorCode.IDEMPOTENCY_CONFLICT
                    if "idempotency" in message
                    else LifecycleErrorCode.LEGAL_HOLD_ACTIVE
                    if "legal hold" in message
                    else LifecycleErrorCode.INVALID_TRANSITION
                )
                raise LifecycleError(
                    code, "Lifecycle transition was rejected by PostgreSQL."
                ) from exc
        if prior_state is None:
            raise LifecycleError(LifecycleErrorCode.INVALID_TRANSITION, "Workspace was not found.")
        return TransitionDecision(
            context.workspace_id,
            LifecycleState(str(prior_state)),
            LifecycleState(str(row.outcome_state)),
            expected_version,
            int(row.outcome_version),
            operation_key,
        )

    def place_legal_hold(
        self,
        *,
        context: WorkspaceContext,
        hold_id: UUID,
        basis_code: str,
        evidence_refs: tuple[str, ...],
        authority_identity_id: str,
        reason_code: str,
    ) -> None:
        if not evidence_refs:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "Legal hold requires exact evidence references.",
            )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.select(sa.func.set_config("asd.lifecycle_operation_id", str(hold_id), True))
            )
            state = session.scalar(
                sa.text(
                    "SELECT lifecycle_state FROM workspace.workspaces WHERE "
                    "organization_id=:organization AND workspace_id=:workspace FOR UPDATE"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.legal_holds "
                    "(organization_id,workspace_id,legal_hold_id,hold_version,basis_code,evidence_refs,"
                    "authority_identity_id,suspended_state,reason_code,effective_from) VALUES "
                    "(:organization,:workspace,:hold,1,:basis,CAST(:evidence AS jsonb),:authority,"
                    ":state,:reason,CURRENT_TIMESTAMP)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "hold": hold_id,
                    "basis": basis_code,
                    "evidence": _json_array(evidence_refs),
                    "authority": authority_identity_id,
                    "state": state,
                    "reason": reason_code,
                },
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.workspaces SET legal_hold_active=true,revision=revision+1 "
                    "WHERE organization_id=:organization AND workspace_id=:workspace"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.destructive_authorization_invalidations "
                    "(organization_id,workspace_id,authorization_id,invalidation_id,reason_code,"
                    "invalidated_at) SELECT organization_id,workspace_id,authorization_id,"
                    "gen_random_uuid(),'legal_hold.placed',CURRENT_TIMESTAMP "
                    "FROM workspace.destructive_authorizations WHERE organization_id=:organization "
                    "AND workspace_id=:workspace ON CONFLICT DO NOTHING"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            )

    def release_legal_hold(
        self,
        *,
        context: WorkspaceContext,
        hold_id: UUID,
        released_by_identity_id: str,
        release_decision_ref: str,
    ) -> None:
        """Append a release version and invalidate every prior destructive authorization."""
        operation_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.select(sa.func.set_config("asd.lifecycle_operation_id", str(operation_id), True))
            )
            session.execute(
                sa.text(
                    "SELECT workspace_id FROM workspace.workspaces WHERE "
                    "organization_id=:organization AND workspace_id=:workspace FOR UPDATE"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            ).one()
            current = session.execute(
                sa.text(
                    "SELECT hold_version,basis_code,evidence_refs,authority_identity_id,"
                    "suspended_state,reason_code,effective_from FROM workspace.legal_holds "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND legal_hold_id=:hold ORDER BY hold_version DESC LIMIT 1"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "hold": hold_id,
                },
            ).one_or_none()
            if (
                current is None
                or session.scalar(
                    sa.text(
                        "SELECT effective_until IS NULL FROM workspace.legal_holds "
                        "WHERE organization_id=:organization AND workspace_id=:workspace "
                        "AND legal_hold_id=:hold AND hold_version=:version"
                    ),
                    {
                        "organization": context.organization_id,
                        "workspace": context.workspace_id,
                        "hold": hold_id,
                        "version": current.hold_version,
                    },
                )
                is not True
            ):
                raise LifecycleError(
                    LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                    "The legal hold does not exist or is already released.",
                )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.legal_holds "
                    "(organization_id,workspace_id,legal_hold_id,hold_version,basis_code,evidence_refs,"
                    "authority_identity_id,suspended_state,reason_code,effective_from,effective_until,"
                    "released_by_identity_id,release_decision_ref) VALUES "
                    "(:organization,:workspace,:hold,:version,:basis,"
                    "CAST(:evidence AS jsonb),:authority,:state,"
                    ":reason,:effective_from,CURRENT_TIMESTAMP,:released_by,:decision)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "hold": hold_id,
                    "version": int(current.hold_version) + 1,
                    "basis": current.basis_code,
                    "evidence": _json_value(current.evidence_refs),
                    "authority": current.authority_identity_id,
                    "state": current.suspended_state,
                    "reason": current.reason_code,
                    "effective_from": current.effective_from,
                    "released_by": released_by_identity_id,
                    "decision": release_decision_ref,
                },
            )
            session.execute(
                sa.text(
                    "WITH latest AS (SELECT DISTINCT ON (legal_hold_id) "
                    "legal_hold_id,effective_until "
                    "FROM workspace.legal_holds WHERE organization_id=:organization "
                    "AND workspace_id=:workspace ORDER BY legal_hold_id,hold_version DESC) "
                    "UPDATE workspace.workspaces SET legal_hold_active=EXISTS "
                    "(SELECT 1 FROM latest WHERE effective_until IS NULL),revision=revision+1 "
                    "WHERE organization_id=:organization AND workspace_id=:workspace"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.destructive_authorization_invalidations "
                    "(organization_id,workspace_id,authorization_id,invalidation_id,reason_code,"
                    "invalidated_at) SELECT organization_id,workspace_id,authorization_id,"
                    "gen_random_uuid(),'legal_hold.released_requires_fresh_plan',CURRENT_TIMESTAMP "
                    "FROM workspace.destructive_authorizations WHERE organization_id=:organization "
                    "AND workspace_id=:workspace ON CONFLICT DO NOTHING"
                ),
                {"organization": context.organization_id, "workspace": context.workspace_id},
            )

    def record_archive_import(
        self,
        *,
        context: WorkspaceContext,
        decision: ArchiveImportDecision,
        source_archive_package_id: UUID,
        id_mapping_digest: str,
        authorization_reference: str,
    ) -> None:
        """Persist verified lineage only under the freshly provisioned target workspace."""
        if context.workspace_id != decision.new_workspace_id:
            raise LifecycleError(
                LifecycleErrorCode.IMPORT_BLOCKED,
                "Archive import lineage must be written under the new workspace scope.",
            )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.archive_imports "
                    "(organization_id,workspace_id,archive_import_id,source_archive_package_id,"
                    "source_workspace_id,new_workspace_revision,id_mapping_digest,schema_compatibility,"
                    "authorization_reference,status) VALUES "
                    "(:organization,:workspace,:import_id,:package,:source_workspace,:revision,"
                    ":mapping_digest,:compatibility,:authority,'imported')"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "import_id": decision.import_id,
                    "package": source_archive_package_id,
                    "source_workspace": decision.source_workspace_id,
                    "revision": decision.new_workspace_revision,
                    "mapping_digest": id_mapping_digest,
                    "compatibility": decision.schema_compatibility,
                    "authority": authorization_reference,
                },
            )

    def record_freeze_manifest(
        self,
        *,
        context: WorkspaceContext,
        lifecycle_version: int,
        workspace_revision: int,
        canonical_revision_digest: str,
        job_inventory: dict[str, object],
        result: str,
    ) -> UUID:
        manifest_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.freeze_manifests "
                    "(organization_id,workspace_id,freeze_manifest_id,lifecycle_version,"
                    "workspace_revision,canonical_revision_digest,writer_count,job_inventory,result,"
                    "created_by_identity_id) VALUES "
                    "(:organization,:workspace,:manifest,:lifecycle,:revision,:digest,0,"
                    "CAST(:jobs AS jsonb),:result,:actor)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "manifest": manifest_id,
                    "lifecycle": lifecycle_version,
                    "revision": workspace_revision,
                    "digest": canonical_revision_digest,
                    "jobs": _json_value(job_inventory),
                    "result": result,
                    "actor": context.actor_identity_id or context.service_identity_id,
                },
            )
        return manifest_id

    def record_finalization_report(
        self,
        *,
        context: WorkspaceContext,
        lifecycle_version: int,
        result_manifest_digest: str,
        blockers: tuple[str, ...],
        uncertainties: tuple[str, ...],
        mode_terminal_statuses: dict[str, str],
        outcome: str,
    ) -> UUID:
        report_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.finalization_reports "
                    "(organization_id,workspace_id,finalization_report_id,lifecycle_version,"
                    "result_manifest_digest,blockers,uncertainties,mode_terminal_statuses,"
                    "production_ready_claim,outcome,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:report,:lifecycle,:digest,CAST(:blockers AS jsonb),"
                    "CAST(:uncertainties AS jsonb),CAST(:modes AS jsonb),false,:outcome,:actor)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "report": report_id,
                    "lifecycle": lifecycle_version,
                    "digest": result_manifest_digest,
                    "blockers": _json_value(blockers),
                    "uncertainties": _json_value(uncertainties),
                    "modes": _json_value(mode_terminal_statuses),
                    "outcome": outcome,
                    "actor": context.actor_identity_id or context.service_identity_id,
                },
            )
        return report_id

    def record_verified_export(
        self,
        *,
        context: WorkspaceContext,
        workspace_revision: int,
        idempotency_key: str,
        package_digest: str,
        manifest_digest: str,
    ) -> UUID:
        export_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.export_operations "
                    "(organization_id,workspace_id,export_operation_id,idempotency_key,"
                    "workspace_revision,package_digest,manifest_digest,state,verification_report,"
                    "receipt_ref,contract_version,created_by_identity_id,completed_at) VALUES "
                    "(:organization,:workspace,:export,:key,:revision,:package,:manifest,'verified',"
                    '\'{"integrity":"verified","readability":"verified"}\'::jsonb,'
                    ":receipt,'0.1.0',:actor,CURRENT_TIMESTAMP)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "export": export_id,
                    "key": idempotency_key,
                    "revision": workspace_revision,
                    "package": package_digest,
                    "manifest": manifest_digest,
                    "receipt": f"export-receipt:{export_id}",
                    "actor": context.actor_identity_id or context.service_identity_id,
                },
            )
        return export_id

    def record_verified_archive(
        self,
        *,
        context: WorkspaceContext,
        export_operation_id: UUID,
        workspace_revision: int,
        package_digest: str,
        manifest_digest: str,
        item_count: int,
    ) -> UUID:
        package_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.archive_packages "
                    "(organization_id,workspace_id,archive_package_id,export_operation_id,"
                    "package_version,workspace_revision,package_digest,manifest_digest,"
                    "storage_adapter_key,sealed_at,import_compatibility,state) VALUES "
                    "(:organization,:workspace,:package,:export,'1.0.0',:revision,:package_digest,"
                    ":manifest_digest,'portable.synthetic',CURRENT_TIMESTAMP,'new_workspace_seed',"
                    "'verified')"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "package": package_id,
                    "export": export_operation_id,
                    "revision": workspace_revision,
                    "package_digest": package_digest,
                    "manifest_digest": manifest_digest,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.archive_verifications "
                    "(organization_id,workspace_id,archive_verification_id,archive_package_id,"
                    "expected_count,observed_count,missing_count,extra_count,changed_count,"
                    "readability_passed,outcome,verifier_identity_id,verified_at) VALUES "
                    "(:organization,:workspace,:verification,:package,:count,:count,0,0,0,true,"
                    "'verified',:verifier,CURRENT_TIMESTAMP)"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "verification": uuid7(),
                    "package": package_id,
                    "count": item_count,
                    "verifier": context.actor_identity_id or context.service_identity_id,
                },
            )
        return package_id

    def persist_deletion_plan(self, context: WorkspaceContext, plan: DeletionPlan) -> None:
        self._require_scope(context, plan.organization_id, plan.workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.deletion_plans "
                    "(organization_id,workspace_id,deletion_plan_id,plan_version,operation_kind,"
                    "lifecycle_version,workspace_revision,retention_profile_key,retention_profile_version,"
                    "basis_registry_key,basis_registry_version,basis_code,basis_evidence_refs,"
                    "legal_hold_checked_at,adapter_registry_key,adapter_registry_version,inventory_digest,"
                    "deletion_items,expected_residue_classes,requester_identity_id,dry_run_result,"
                    "expires_at,plan_digest) VALUES "
                    "(:organization,:workspace,:plan,:version,:kind,:lifecycle,:revision,"
                    ":retention_key,:retention_version,:basis_key,:basis_version,:basis_code,"
                    "CAST(:evidence AS jsonb),:hold_check,:adapter_key,:adapter_version,:inventory,"
                    "CAST(:items AS jsonb),CAST(:residues AS jsonb),:requester,'complete',"
                    ":expires,:digest)"
                ),
                {
                    "organization": plan.organization_id,
                    "workspace": plan.workspace_id,
                    "plan": plan.plan_id,
                    "version": plan.plan_version,
                    "kind": plan.operation_kind,
                    "lifecycle": plan.lifecycle_version,
                    "revision": plan.workspace_revision,
                    "retention_key": plan.retention_profile.key,
                    "retention_version": plan.retention_profile.version,
                    "basis_key": plan.basis.registry.key,
                    "basis_version": plan.basis.registry.version,
                    "basis_code": plan.basis.code,
                    "evidence": _json_value(plan.basis.evidence_refs),
                    "hold_check": plan.legal_hold_checked_at,
                    "adapter_key": plan.adapter_registry.key,
                    "adapter_version": plan.adapter_registry.version,
                    "inventory": plan.inventory_digest,
                    "items": _json_value(
                        [
                            {
                                "adapter_key": item.adapter_key,
                                "item_id": item.item_id,
                                "action": item.action,
                            }
                            for item in plan.items
                        ]
                    ),
                    "residues": _json_value(plan.expected_residue_classes),
                    "requester": plan.requester_identity_id,
                    "expires": plan.expires_at,
                    "digest": plan.digest,
                },
            )

    def persist_authorization(
        self,
        context: WorkspaceContext,
        plan: DeletionPlan,
        authorization: DestructiveAuthorization,
        legal_hold_check_id: UUID,
    ) -> None:
        self._require_scope(context, plan.organization_id, plan.workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.destructive_authorizations "
                    "(organization_id,workspace_id,authorization_id,deletion_plan_id,plan_version,"
                    "plan_digest,requester_identity_id,confirmer_identity_id,executor_identity_id,"
                    "verifier_identity_id,legal_hold_check_id,authorized_at,expires_at) VALUES "
                    "(:organization,:workspace,:authorization,:plan,:version,:digest,:requester,"
                    ":confirmer,:executor,:verifier,:hold,:authorized,:expires)"
                ),
                {
                    "organization": plan.organization_id,
                    "workspace": plan.workspace_id,
                    "authorization": authorization.authorization_id,
                    "plan": plan.plan_id,
                    "version": plan.plan_version,
                    "digest": plan.digest,
                    "requester": authorization.requester_identity_id,
                    "confirmer": authorization.confirmer_identity_id,
                    "executor": authorization.executor_identity_id,
                    "verifier": authorization.verifier_identity_id,
                    "hold": legal_hold_check_id,
                    "authorized": authorization.authorized_at,
                    "expires": authorization.expires_at,
                },
            )

    def persist_verification_evidence(
        self,
        *,
        context: WorkspaceContext,
        plan: DeletionPlan,
        receipts: tuple[AdapterReceipt, ...],
        scans: tuple[ResidualScan, ...],
        attestation: DestructionAttestation,
    ) -> None:
        self._require_scope(context, plan.organization_id, plan.workspace_id)
        payload = attestation.to_content_free_dict()
        payload["record_type"] = "destruction_attestation"
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            self._insert_receipts(session, plan, receipts)
            for scan in scans:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.residual_verifications "
                        "(organization_id,workspace_id,residual_verification_id,deletion_plan_id,"
                        "plan_version,adapter_key,scan_methods,found_count,foreign_workspace_count,"
                        "allowed_residue_classes,outcome,verifier_identity_id,verified_at) VALUES "
                        "(:organization,:workspace,:scan,:plan,:version,:adapter,"
                        "CAST(:methods AS jsonb),"
                        ":found,:foreign,CAST(:residues AS jsonb),:outcome,:verifier,:verified)"
                    ),
                    {
                        "organization": plan.organization_id,
                        "workspace": plan.workspace_id,
                        "scan": scan.scan_id,
                        "plan": plan.plan_id,
                        "version": plan.plan_version,
                        "adapter": scan.adapter_key,
                        "methods": _json_value(scan.methods),
                        "found": scan.found_count,
                        "foreign": scan.foreign_workspace_count,
                        "residues": _json_value(scan.allowed_residue_classes),
                        "outcome": scan.outcome.value,
                        "verifier": attestation.verifier_identity_id,
                        "verified": scan.recorded_at,
                    },
                )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.destruction_attestations "
                    "(organization_id,workspace_id,destruction_attestation_id,attestation_version,"
                    "lifecycle_revision,deletion_plan_id,plan_version,plan_digest,retention_profile_key,"
                    "retention_profile_version,basis_registry_key,basis_registry_version,basis_code,"
                    "requester_identity_id,confirmer_identity_id,executor_identity_id,verifier_identity_id,"
                    "adapter_registry_key,adapter_registry_version,receipt_count,scan_count,"
                    "aggregate_deleted_count,aggregate_residue_count,residue_classes,"
                    "platform_integrity_result,assurance_class,outcome,verified_at,contract_version,"
                    "content_free_payload) VALUES "
                    "(:organization,:workspace,:attestation,:attestation_version,:revision,:plan,"
                    ":plan_version,:digest,:retention_key,:retention_version,:basis_key,:basis_version,"
                    ":basis_code,:requester,:confirmer,:executor,:verifier,:adapter_key,:adapter_version,"
                    ":receipt_count,:scan_count,:deleted,:residue_count,CAST(:residues AS jsonb),"
                    ":platform_integrity,:assurance,:outcome,:verified,'1.0.0',"
                    "CAST(:payload AS jsonb))"
                ),
                {
                    "organization": plan.organization_id,
                    "workspace": plan.workspace_id,
                    "attestation": attestation.attestation_id,
                    "attestation_version": attestation.version,
                    "revision": attestation.lifecycle_revision,
                    "plan": plan.plan_id,
                    "plan_version": plan.plan_version,
                    "digest": plan.digest,
                    "retention_key": attestation.retention_profile.key,
                    "retention_version": attestation.retention_profile.version,
                    "basis_key": attestation.basis_registry.key,
                    "basis_version": attestation.basis_registry.version,
                    "basis_code": attestation.basis_code,
                    "requester": attestation.requester_identity_id,
                    "confirmer": attestation.confirmer_identity_id,
                    "executor": attestation.executor_identity_id,
                    "verifier": attestation.verifier_identity_id,
                    "adapter_key": attestation.adapter_registry.key,
                    "adapter_version": attestation.adapter_registry.version,
                    "receipt_count": len(receipts),
                    "scan_count": len(scans),
                    "deleted": attestation.aggregate_deleted_count,
                    "residue_count": attestation.aggregate_residue_count,
                    "residues": _json_value(attestation.residue_classes),
                    "platform_integrity": (
                        "unchanged"
                        if attestation.platform_integrity_before
                        == attestation.platform_integrity_after
                        else "changed"
                    ),
                    "assurance": attestation.assurance_class.value,
                    "outcome": attestation.outcome.value,
                    "verified": attestation.verified_at,
                    "payload": _json_value(payload),
                },
            )

    def persist_adapter_receipts(
        self,
        *,
        context: WorkspaceContext,
        plan: DeletionPlan,
        receipts: tuple[AdapterReceipt, ...],
    ) -> None:
        self._require_scope(context, plan.organization_id, plan.workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            self._insert_receipts(session, plan, receipts)

    def persist_recovery_checkpoint(
        self,
        *,
        context: WorkspaceContext,
        plan: DeletionPlan,
        checkpoint: RecoveryCheckpoint,
    ) -> None:
        self._require_scope(context, plan.organization_id, plan.workspace_id)
        if checkpoint.plan_digest != plan.digest:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "Recovery checkpoint is not bound to the immutable destructive plan.",
            )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.recovery_checkpoints "
                    "(organization_id,workspace_id,recovery_checkpoint_id,operation_id,plan_digest,"
                    "failed_operation,affected_adapters,completed_effects,pending_items,status,"
                    "created_at) VALUES (:organization,:workspace,:checkpoint,:operation,:digest,"
                    ":failed_operation,CAST(:adapters AS jsonb),CAST(:completed AS jsonb),"
                    "CAST(:pending AS jsonb),'required',:created)"
                ),
                {
                    "organization": plan.organization_id,
                    "workspace": plan.workspace_id,
                    "checkpoint": checkpoint.checkpoint_id,
                    "operation": checkpoint.operation_id,
                    "digest": checkpoint.plan_digest,
                    "failed_operation": checkpoint.failed_operation,
                    "adapters": _json_value(checkpoint.affected_adapters),
                    "completed": _json_value(checkpoint.completed_effects),
                    "pending": _json_value(checkpoint.pending_items),
                    "created": checkpoint.recorded_at,
                },
            )

    @staticmethod
    def _insert_receipts(
        session: Session,
        plan: DeletionPlan,
        receipts: tuple[AdapterReceipt, ...],
    ) -> None:
        for receipt in receipts:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.adapter_receipts "
                    "(organization_id,workspace_id,adapter_receipt_id,deletion_plan_id,plan_version,"
                    "operation_id,adapter_key,item_id,outcome,before_count,after_count,"
                    "receipt_schema_version,recorded_at) VALUES "
                    "(:organization,:workspace,:receipt,:plan,:version,:operation,:adapter,:item,"
                    ":outcome,:before,:after,'1.0.0',:recorded) ON CONFLICT DO NOTHING"
                ),
                {
                    "organization": plan.organization_id,
                    "workspace": plan.workspace_id,
                    "receipt": receipt.receipt_id,
                    "plan": plan.plan_id,
                    "version": plan.plan_version,
                    "operation": receipt.operation_id,
                    "adapter": receipt.adapter_key,
                    "item": receipt.item_id,
                    "outcome": receipt.outcome.value,
                    "before": receipt.before_count,
                    "after": receipt.after_count,
                    "recorded": receipt.recorded_at,
                },
            )

    @staticmethod
    def _require_scope(
        context: WorkspaceContext, organization_id: UUID, workspace_id: UUID
    ) -> None:
        if context.organization_id != organization_id or context.workspace_id != workspace_id:
            raise LifecycleError(
                LifecycleErrorCode.CROSS_WORKSPACE_RESIDUE,
                "Lifecycle record scope does not match the transaction context.",
            )


def _json_array(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(values)


def _json_value(value: object) -> str:
    import json

    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _set_scope(session: Session, context: WorkspaceContext) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    ).one()


class PostgresWorkspaceStorageAdapter:
    """Restricted exact-relation purge adapter; never drops/truncates a schema."""

    TABLES = (
        "workspace.deliverable_inputs",
        "workspace.kernel_finding_versions",
        "workspace.kernel_issue_versions",
        "workspace.payment_claim_versions",
        "workspace.ks_line_versions",
        "workspace.ks_document_versions",
        "workspace.presented_volume_versions",
        "workspace.id_package_items",
        "workspace.id_package_versions",
        "workspace.document_coverages",
        "workspace.document_requirement_versions",
        "workspace.evidence_requirement_versions",
        "workspace.control_operation_versions",
        "workspace.material_applications",
        "workspace.material_batch_versions",
        "workspace.material_requirement_versions",
        "workspace.work_volume_versions",
        "workspace.work_dependencies",
        "workspace.work_instance_versions",
        "workspace.construction_element_versions",
        "workspace.construction_structure_versions",
        "workspace.mode_kernel_bindings",
        "workspace.kernel_process_instances",
        "workspace.workspace_fact_evidence",
        "workspace.workspace_fact_versions",
        "workspace.workspace_facts",
        "workspace.confirmation_decisions",
        "workspace.confirmation_authority_grants",
        "workspace.candidate_field_evidence",
        "workspace.vlm_validation_failures",
        "workspace.vlm_repair_cycles",
        "workspace.vlm_batch_items",
        "workspace.vlm_cost_ledger",
        "workspace.candidate_fields",
        "workspace.vlm_validation_runs",
        "workspace.vlm_repair_plans",
        "workspace.candidate_versions",
        "workspace.candidates",
        "workspace.vlm_provider_failures",
        "workspace.vlm_provider_results",
        "workspace.vlm_render_artifacts",
        "workspace.vlm_batches",
        "workspace.vlm_cost_envelopes",
        "workspace.vlm_raw_artifacts",
        "workspace.vlm_routing_decisions",
        "workspace.vlm_execution_attempts",
        "workspace.vlm_execution_requests",
        "workspace.object_links",
        "workspace.promotion_decisions",
        "workspace.promotion_regression_results",
        "workspace.promotion_anonymization_results",
        "workspace.promotion_candidates",
        "workspace.controlled_rule_set_upgrades",
        "workspace.rule_traces",
        "workspace.rule_evaluations",
        "workspace.rule_evidence",
        "workspace.rule_version_states",
        "workspace.rule_versions",
        "workspace.rules",
        "workspace.evidence_links",
        "workspace.source_locators",
        "workspace.source_versions",
        "workspace.acquisition_attempts",
        "workspace.source_object_receipts",
        "workspace.source_artifacts",
        "workspace.objects",
        "workspace.mode_executions",
        "messaging.workspace_outbox",
        "messaging.workspace_inbox_receipts",
        "messaging.workspace_idempotency",
    )

    def __init__(
        self,
        engine: Engine,
        organization_id: UUID,
        definition: StorageAdapterDefinition,
    ) -> None:
        self._engine = engine
        self._organization_id = organization_id
        self.definition = definition
        self._receipts: dict[tuple[UUID, str], AdapterReceipt] = {}

    def inventory(self, workspace_id: UUID) -> tuple[InventoryItem, ...]:
        with self._engine.begin() as connection:
            _set_connection_scope(connection, self._organization_id, workspace_id)
            items: list[InventoryItem] = []
            for table in self.TABLES:
                count = int(
                    connection.scalar(
                        sa.text(
                            f"SELECT count(*) FROM {table} WHERE organization_id=:organization "
                            "AND workspace_id=:workspace"
                        ),
                        {"organization": self._organization_id, "workspace": workspace_id},
                    )
                    or 0
                )
                if count:
                    is_control_outbox = table == "messaging.workspace_outbox"
                    payload = (table if is_control_outbox else f"{table}:{count}").encode()
                    items.append(
                        InventoryItem(
                            table,
                            workspace_id,
                            "application/vnd.asd-kontur.relation-inventory",
                            0 if is_control_outbox else count,
                            "sha256:" + hashlib.sha256(payload).hexdigest(),
                        )
                    )
            return tuple(items)

    def purge_item(self, *, workspace_id: UUID, item_id: str, operation_id: UUID) -> AdapterReceipt:
        if item_id == "__inventory_empty__":
            receipt = AdapterReceipt(
                uuid7(),
                self.definition.adapter_key,
                item_id,
                AdapterOutcome.ALREADY_ABSENT,
                0,
                0,
                operation_id,
                datetime.now(UTC),
            )
            self._receipts[(operation_id, item_id)] = receipt
            return receipt
        if item_id not in self.TABLES:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "PostgreSQL adapter received a relation outside its immutable allowlist.",
            )
        key = (operation_id, item_id)
        if key in self._receipts:
            return self._receipts[key]
        with self._engine.begin() as connection:
            _set_connection_scope(connection, self._organization_id, workspace_id)
            before = int(
                connection.scalar(
                    sa.text(
                        f"SELECT count(*) FROM {item_id} WHERE organization_id=:organization "
                        "AND workspace_id=:workspace"
                    ),
                    {"organization": self._organization_id, "workspace": workspace_id},
                )
                or 0
            )
            connection.execute(
                sa.text(
                    f"DELETE FROM {item_id} WHERE organization_id=:organization "
                    "AND workspace_id=:workspace"
                ),
                {"organization": self._organization_id, "workspace": workspace_id},
            )
            after = int(
                connection.scalar(
                    sa.text(
                        f"SELECT count(*) FROM {item_id} WHERE organization_id=:organization "
                        "AND workspace_id=:workspace"
                    ),
                    {"organization": self._organization_id, "workspace": workspace_id},
                )
                or 0
            )
        receipt = AdapterReceipt(
            uuid7(),
            self.definition.adapter_key,
            item_id,
            AdapterOutcome.DELETED if before else AdapterOutcome.ALREADY_ABSENT,
            before,
            after,
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
        del known_ids, known_digests, known_fragments
        return self.inventory(workspace_id)


def _set_connection_scope(
    connection: sa.Connection, organization_id: UUID, workspace_id: UUID
) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()
