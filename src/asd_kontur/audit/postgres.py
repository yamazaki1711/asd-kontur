"""Narrow transactional persistence for shared corpus and Audit records."""

# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.corpus import (
    Composition,
    CorpusReconciliation,
    CorpusSnapshot,
    PhysicalObjectInspection,
    ProcessingPlan,
)
from asd_kontur.harness.models import digest_of
from asd_kontur.persistence.scope import WorkspaceContext

from .evaluation import package_readiness_counts
from .models import (
    ActionRequest,
    AuditReport,
    AuditScope,
    CausalReadinessDelta,
    DeltaDenominator,
    DeltaState,
    DocumentDelta,
    PackageAssessment,
    PackageReadiness,
)
from .process import AuditCommand, AuditCommandType, AuditStateMachine, CommandOutcome, ProcessState


class PostgresCorpusAuditStore:
    """Persist only typed WP-14 aggregates; arbitrary SQL is not exposed."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def start_audit_process(self, context: WorkspaceContext, scope: AuditScope) -> None:
        """Create the immutable-snapshot Audit aggregate in its own service scope.

        The database enforces that ``mode_execution_id`` is an Audit execution
        and that the precise corpus snapshot/rule-set version already exists.
        This method deliberately does not create either prerequisite and cannot
        substitute a latest version.
        """

        self._require_scope(context, scope.organization_id, scope.workspace_id)
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                inserted = session.scalar(
                    sa.text(
                        "INSERT INTO workspace.audit_processes "
                        "(organization_id,workspace_id,audit_process_id,mode_execution_id,"
                        "corpus_snapshot_id,corpus_snapshot_version,state,revision,"
                        "current_fingerprint,rule_set_version_id,conflict_policy_version,"
                        "authority_profile_version,contract_registry_version,correlation_id,"
                        "created_at,updated_at) VALUES "
                        "(:organization,:workspace,:process,:mode,:snapshot,:snapshot_version,"
                        "'requested',1,:fingerprint,:ruleset,:conflict_policy,:authority_profile,"
                        ":contract_registry,:correlation,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) "
                        "ON CONFLICT (organization_id,workspace_id,audit_process_id) DO NOTHING "
                        "RETURNING audit_process_id"
                    ),
                    {
                        "organization": scope.organization_id,
                        "workspace": scope.workspace_id,
                        "process": scope.audit_process_id,
                        "mode": scope.mode_execution_id,
                        "snapshot": scope.corpus_snapshot_id,
                        "snapshot_version": scope.corpus_snapshot_version,
                        "fingerprint": digest_of(scope),
                        "ruleset": scope.rule_set_version_id,
                        "conflict_policy": scope.conflict_policy_version,
                        "authority_profile": scope.authority_profile_version,
                        "contract_registry": scope.contract_registry_version,
                        "correlation": context.correlation_id,
                    },
                )
                if inserted is not None:
                    return
                existing = (
                    session.execute(
                        sa.text(
                            "SELECT mode_execution_id,corpus_snapshot_id,corpus_snapshot_version,"
                            "rule_set_version_id,conflict_policy_version,authority_profile_version,"
                            "contract_registry_version,current_fingerprint FROM workspace.audit_processes "
                            "WHERE organization_id=:organization AND workspace_id=:workspace "
                            "AND audit_process_id=:process FOR UPDATE"
                        ),
                        {
                            "organization": scope.organization_id,
                            "workspace": scope.workspace_id,
                            "process": scope.audit_process_id,
                        },
                    )
                    .mappings()
                    .one()
                )
                expected = {
                    "mode_execution_id": scope.mode_execution_id,
                    "corpus_snapshot_id": scope.corpus_snapshot_id,
                    "corpus_snapshot_version": scope.corpus_snapshot_version,
                    "rule_set_version_id": scope.rule_set_version_id,
                    "conflict_policy_version": scope.conflict_policy_version,
                    "authority_profile_version": scope.authority_profile_version,
                    "contract_registry_version": scope.contract_registry_version,
                    "current_fingerprint": digest_of(scope),
                }
                if dict(existing) != expected:
                    raise ValueError(
                        "Audit process id is already bound to a different immutable scope"
                    )

    def apply_command(self, context: WorkspaceContext, command: AuditCommand) -> CommandOutcome:
        """Advance the header only through the declared Audit state machine."""

        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                return self._apply_command_in_session(session, context, command)

    def evaluate_document_delta(
        self,
        context: WorkspaceContext,
        command: AuditCommand,
        value: DocumentDelta,
    ) -> CommandOutcome:
        """Persist one immutable document delta with its header transition.

        A delta cannot be attached to a merely similarly named audit process:
        the stored process must pin the same snapshot, version, and rule set.
        Header advancement and immutable rows share one transaction, so a
        failed persistence cannot make the Audit UI look as if evaluation ran.
        """

        if command.command_type is not AuditCommandType.EVALUATE_DOCUMENT_DELTA:
            raise ValueError("Audit command must evaluate a document delta")
        scope = value.audit_scope
        self._require_scope(context, scope.organization_id, scope.workspace_id)
        if command.aggregate_id != scope.audit_process_id:
            raise ValueError("Audit command aggregate does not match the delta scope")
        if value.denominator.rule_set_version_id != scope.rule_set_version_id:
            raise ValueError("Document delta denominator must pin the Audit rule set version")
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                revision = self._require_exact_evaluating_scope(session, scope)
                outcome = AuditStateMachine().apply(
                    ProcessState.EVALUATING,
                    revision,
                    command,
                )
                if not outcome.accepted:
                    return outcome
                self._insert_document_delta(session, value)
                self._advance_header(session, context, command, outcome)
                return outcome

    def evaluate_causal_delta(
        self,
        context: WorkspaceContext,
        command: AuditCommand,
        value: CausalReadinessDelta,
    ) -> CommandOutcome:
        """Persist exact causal paths and advance one evaluation transition."""

        return self._evaluate_delta(
            context,
            command,
            scope=value.audit_scope,
            denominator=value.denominator,
            command_type=AuditCommandType.EVALUATE_CAUSAL_DELTA,
            persist=lambda session: self._insert_causal_delta(session, value),
        )

    def evaluate_package_readiness(
        self,
        context: WorkspaceContext,
        command: AuditCommand,
        value: PackageReadiness,
    ) -> CommandOutcome:
        """Persist package/signing/handover states and their exact memberships."""

        return self._evaluate_delta(
            context,
            command,
            scope=value.audit_scope,
            denominator=value.denominator,
            command_type=AuditCommandType.EVALUATE_PACKAGE_READINESS,
            persist=lambda session: self._insert_package_readiness(session, value),
        )

    def issue_action_request(
        self, context: WorkspaceContext, command: AuditCommand, value: ActionRequest
    ) -> CommandOutcome:
        """Persist one immutable, evidence-bound correction request.

        The request is owned by the canonical Audit service and advances the
        exact Audit process into ``blocked``.  A request never fabricates a
        document or treats its own issue as proof that a correction occurred.
        """

        if command.command_type is not AuditCommandType.ISSUE_ACTION_REQUEST:
            raise ValueError("Audit command must issue an action request")
        scope = value.audit_scope
        self._require_scope(context, scope.organization_id, scope.workspace_id)
        if command.aggregate_id != scope.audit_process_id:
            raise ValueError("Audit command aggregate does not match the action-request scope")
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                revision = self._require_exact_evaluating_scope(session, scope)
                outcome = AuditStateMachine().apply(ProcessState.EVALUATING, revision, command)
                if not outcome.accepted:
                    return outcome
                self._insert_action_request(session, value)
                self._advance_header(session, context, command, outcome)
                return outcome

    def finalize_report(
        self, context: WorkspaceContext, command: AuditCommand, value: AuditReport
    ) -> CommandOutcome:
        """Publish a report only from the exact persisted snapshot and deltas.

        Action requests are intentionally rejected until their versioned
        membership contract is persisted as well.  Silently retaining only an
        ID would make the report depend on an arbitrary later action version.
        """

        if command.command_type is not AuditCommandType.FINALIZE_AUDIT_REPORT:
            raise ValueError("Audit command must finalize an Audit report")
        if value.action_request_ids:
            raise ValueError("Audit report action-request version references are not yet supported")
        scope = value.audit_scope
        self._require_scope(context, scope.organization_id, scope.workspace_id)
        if command.aggregate_id != scope.audit_process_id:
            raise ValueError("Audit command aggregate does not match the report scope")
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                revision = self._require_exact_evaluating_scope(session, scope)
                outcome = AuditStateMachine().apply(ProcessState.EVALUATING, revision, command)
                if not outcome.accepted:
                    return outcome
                self._insert_report(session, value)
                self._advance_header(session, context, command, outcome)
                return outcome

    def record_inspection(self, context: WorkspaceContext, value: PhysicalObjectInspection) -> None:
        self._require_scope(context, value.scope.organization_id, value.scope.workspace_id)
        compositions = {page.composition for page in value.pages}
        if not compositions:
            composition = Composition.UNKNOWN
        elif len(compositions) == 1:
            composition = next(iter(compositions))
        else:
            composition = Composition.MIXED
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.physical_object_inspections "
                        "(organization_id,workspace_id,inspection_id,physical_object_id,physical_object_version,digest,size_bytes,media_type,encrypted,readable,page_count,composition,embedded_attachment_count,signature_claim_count,inspection_profile_version,error_codes,inspected_at,fingerprint) "
                        "VALUES (:o,:w,:inspection,:object,:object_version,:digest,:size,:media,:encrypted,:readable,:pages,:composition,:attachments,:signatures,:profile,:errors,:at,:fingerprint)"
                    ),
                    {
                        "o": value.scope.organization_id,
                        "w": value.scope.workspace_id,
                        "inspection": value.inspection_id,
                        "object": value.physical_object_id,
                        "object_version": value.physical_object_version,
                        "digest": value.digest,
                        "size": value.size_bytes,
                        "media": value.media_type,
                        "encrypted": value.encrypted,
                        "readable": value.readable,
                        "pages": value.page_count,
                        "composition": composition.value,
                        "attachments": value.embedded_attachment_count,
                        "signatures": value.signature_claim_count,
                        "profile": value.inspection_profile_version,
                        "errors": list(value.error_codes),
                        "at": value.inspected_at,
                        "fingerprint": digest_of(value),
                    },
                )
                for page in value.pages:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_page_manifests "
                            "(organization_id,workspace_id,inspection_id,page_number,page_digest,width_points,height_points,rotation,native_text_characters,raster_objects,composition,readable) "
                            "VALUES (:o,:w,:inspection,:page,:digest,:width,:height,:rotation,:text,:raster,:composition,:readable)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "inspection": value.inspection_id,
                            "page": page.page_number,
                            "digest": digest_of((value.digest, page)),
                            "width": page.width_points,
                            "height": page.height_points,
                            "rotation": page.rotation,
                            "text": page.native_text_characters,
                            "raster": page.raster_objects,
                            "composition": page.composition.value,
                            "readable": page.readable,
                        },
                    )

    def record_plan(
        self,
        context: WorkspaceContext,
        value: ProcessingPlan,
        *,
        processing_profile_id: UUID,
    ) -> None:
        self._require_scope(context, value.scope.organization_id, value.scope.workspace_id)
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.corpus_processing_plan_versions "
                        "(organization_id,workspace_id,processing_plan_id,version,inspection_id,purpose,classification,processing_profile_id,processing_profile_version,page_count,estimated_cost_units,estimated_seconds,state,plan_digest,created_at) "
                        "VALUES (:o,:w,:plan,:version,:inspection,:purpose,:classification,:profile,:profile_version,:pages,:cost,:seconds,:state,:digest,:created)"
                    ),
                    {
                        "o": value.scope.organization_id,
                        "w": value.scope.workspace_id,
                        "plan": value.processing_plan_id,
                        "version": value.version,
                        "inspection": value.inspection_id,
                        "purpose": value.purpose,
                        "classification": value.classification,
                        "profile": processing_profile_id,
                        "profile_version": value.policy_version,
                        "pages": len(value.page_plans),
                        "cost": value.estimated_cost_units,
                        "seconds": value.estimated_seconds,
                        "state": value.state.value,
                        "digest": value.fingerprint,
                        "created": datetime.now(UTC),
                    },
                )
                for shard in value.shards:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_processing_shards "
                            "(organization_id,workspace_id,processing_plan_id,plan_version,shard_id,ordinal,page_numbers,context_overlap_pages,route,expected_output_contract,idempotency_key) "
                            "VALUES (:o,:w,:plan,:version,:shard,:ordinal,:pages,:overlap,:route,:contract,:idempotency)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "plan": value.processing_plan_id,
                            "version": value.version,
                            "shard": shard.shard_id,
                            "ordinal": shard.ordinal,
                            "pages": list(shard.page_numbers),
                            "overlap": list(shard.context_overlap_pages),
                            "route": shard.route.value,
                            "contract": shard.expected_output_contract,
                            "idempotency": f"{value.processing_plan_id}:{value.version}:{shard.ordinal}",
                        },
                    )

    def record_reconciliation(self, context: WorkspaceContext, value: CorpusReconciliation) -> None:
        self._require_scope(context, value.scope.organization_id, value.scope.workspace_id)
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.corpus_reconciliations "
                        "(organization_id,workspace_id,reconciliation_id,processing_plan_id,plan_version,expected_pages,validated_pages,failed_pages,unknown_pages,duplicate_pages,unresolved_segments,accepted_occurrence_ids,outcome,receipt_fingerprint,reconciled_at) "
                        "VALUES (:o,:w,:reconciliation,:plan,:version,:expected,:validated,:failed,:unknown,:duplicate,CAST(:segments AS jsonb),:occurrences,:outcome,:fingerprint,:at)"
                    ),
                    {
                        "o": value.scope.organization_id,
                        "w": value.scope.workspace_id,
                        "reconciliation": value.reconciliation_id,
                        "plan": value.plan_id,
                        "version": value.plan_version,
                        "expected": list(value.expected_pages),
                        "validated": list(value.validated_pages),
                        "failed": list(value.failed_pages),
                        "unknown": list(value.unknown_pages),
                        "duplicate": list(value.duplicate_pages),
                        "segments": json.dumps(value.unresolved_segments),
                        "occurrences": list(value.accepted_occurrence_ids),
                        "outcome": value.outcome.value,
                        "fingerprint": value.receipt_fingerprint,
                        "at": datetime.now(UTC),
                    },
                )

    def record_snapshot(self, context: WorkspaceContext, value: CorpusSnapshot) -> None:
        self._require_scope(context, value.scope.organization_id, value.scope.workspace_id)
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                coverage = value.coverage
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.corpus_snapshot_versions "
                        "(organization_id,workspace_id,corpus_snapshot_id,version,collection_scope_id,collection_scope_version,rule_set_version_id,coverage_denominator_version,discovered_object_count,admitted_object_count,expected_page_count,readable_page_count,validated_page_count,accepted_document_count,unresolved_item_count,outcome,claims_complete_oks,fingerprint,created_at) "
                        "VALUES (:o,:w,:snapshot,:version,:collection_scope,:collection_version,:ruleset,:denominator,:discovered,:admitted,:expected,:readable,:validated,:documents,:unresolved,:outcome,false,:fingerprint,:created)"
                    ),
                    {
                        "o": value.scope.organization_id,
                        "w": value.scope.workspace_id,
                        "snapshot": value.corpus_snapshot_id,
                        "version": value.version,
                        "collection_scope": value.collection_scope_id,
                        "collection_version": value.collection_scope_version,
                        "ruleset": value.rule_set_version_id,
                        "denominator": coverage.denominator_version,
                        "discovered": coverage.discovered_objects,
                        "admitted": coverage.admitted_objects,
                        "expected": coverage.expected_pages,
                        "readable": coverage.readable_pages,
                        "validated": coverage.validated_pages,
                        "documents": coverage.accepted_logical_documents,
                        "unresolved": coverage.unresolved_items,
                        "outcome": value.outcome.value,
                        "fingerprint": value.fingerprint,
                        "created": value.created_at,
                    },
                )
                for reconciliation_id in value.reconciliation_ids:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_snapshot_reconciliations "
                            "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,reconciliation_id) "
                            "VALUES (:o,:w,:snapshot,:version,:reconciliation)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "reconciliation": reconciliation_id,
                        },
                    )
                for object_ref in value.physical_objects:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_snapshot_object_memberships "
                            "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,physical_object_id,physical_object_version) "
                            "VALUES (:o,:w,:snapshot,:version,:object,:object_version)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "object": object_ref.physical_object_id,
                            "object_version": object_ref.physical_object_version,
                        },
                    )
                for inspection_id, page_number in value.page_inventory:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_snapshot_page_memberships "
                            "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,inspection_id,page_number) "
                            "VALUES (:o,:w,:snapshot,:version,:inspection,:page)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "inspection": inspection_id,
                            "page": page_number,
                        },
                    )
                for occurrence_id in value.logical_occurrence_ids:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_snapshot_occurrence_memberships "
                            "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,logical_occurrence_id) "
                            "VALUES (:o,:w,:snapshot,:version,:occurrence)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "occurrence": occurrence_id,
                        },
                    )
                for group in value.duplicate_groups:
                    group_id = UUID(digest_of(group)[7:39])
                    for object_ref in group:
                        session.execute(
                            sa.text(
                                "INSERT INTO workspace.corpus_snapshot_duplicate_memberships "
                                "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,duplicate_group_id,physical_object_id,physical_object_version) "
                                "VALUES (:o,:w,:snapshot,:version,:group,:object,:object_version)"
                            ),
                            {
                                "o": value.scope.organization_id,
                                "w": value.scope.workspace_id,
                                "snapshot": value.corpus_snapshot_id,
                                "version": value.version,
                                "group": group_id,
                                "object": object_ref.physical_object_id,
                                "object_version": object_ref.physical_object_version,
                            },
                        )
                for source_version_id in value.conflicting_version_ids:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_snapshot_conflict_memberships "
                            "(organization_id,workspace_id,corpus_snapshot_id,snapshot_version,conflicting_source_version_id) "
                            "VALUES (:o,:w,:snapshot,:version,:source)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "source": source_version_id,
                        },
                    )
                for item in value.unresolved_items:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.corpus_unresolved_items "
                            "(organization_id,workspace_id,unresolved_item_id,corpus_snapshot_id,snapshot_version,reason_code,affected_locator,blocking,recorded_at) "
                            "VALUES (:o,:w,:item,:snapshot,:version,:reason,:locator,:blocking,:at)"
                        ),
                        {
                            "o": value.scope.organization_id,
                            "w": value.scope.workspace_id,
                            "item": item.item_id,
                            "snapshot": value.corpus_snapshot_id,
                            "version": value.version,
                            "reason": item.reason_code,
                            "locator": item.affected_locator,
                            "blocking": item.blocking,
                            "at": value.created_at,
                        },
                    )

    def record_document_delta(self, context: WorkspaceContext, value: DocumentDelta) -> None:
        scope = value.audit_scope
        self._require_scope(context, scope.organization_id, scope.workspace_id)
        if value.denominator.rule_set_version_id != scope.rule_set_version_id:
            raise ValueError("Document delta denominator must pin the Audit rule set version")
        counts = {state: sum(item.state is state for item in value.items) for state in DeltaState}
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                self._require_exact_evaluating_scope(session, scope)
                self._insert_document_delta(session, value, counts=counts)

    def _insert_document_delta(
        self,
        session: Session,
        value: DocumentDelta,
        *,
        counts: dict[DeltaState, int] | None = None,
    ) -> None:
        scope = value.audit_scope
        exact_counts = counts or {
            state: sum(item.state is state for item in value.items) for state in DeltaState
        }
        existing = session.scalar(
            sa.text(
                "SELECT fingerprint FROM workspace.audit_delta_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND audit_delta_id=:delta AND version=:version"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "delta": value.document_delta_id,
                "version": value.version,
            },
        )
        if existing is not None:
            if str(existing) != value.fingerprint:
                raise ValueError(
                    "Audit document delta identity is already bound to different evidence"
                )
            return
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_denominator_versions "
                "(organization_id,workspace_id,denominator_id,version,audit_process_id,delta_kind,exact_scope,required_item_keys,rule_set_version_id,evidence_refs,fingerprint,created_at) "
                "VALUES (:o,:w,:denominator,:denominator_version,:process,'document',CAST(:scope AS jsonb),:keys,:ruleset,:evidence,:fingerprint,:at)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "denominator": value.denominator.denominator_id,
                "denominator_version": value.denominator.version,
                "process": scope.audit_process_id,
                "scope": json.dumps(value.denominator.exact_scope),
                "keys": list(value.denominator.required_item_keys),
                "ruleset": value.denominator.rule_set_version_id,
                "evidence": list(value.denominator.evidence_refs),
                "fingerprint": digest_of(value.denominator),
                "at": datetime.now(UTC),
            },
        )
        by_value = {getattr(key, "value", str(key)): count for key, count in exact_counts.items()}
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_delta_versions "
                "(organization_id,workspace_id,audit_delta_id,version,audit_process_id,delta_kind,denominator_id,denominator_version,satisfied_count,missing_count,conflict_count,indeterminate_count,blocked_count,fingerprint,evaluated_at) "
                "VALUES (:o,:w,:delta,:version,:process,'document',:denominator,:denominator_version,:satisfied,:missing,:conflict,:indeterminate,:blocked,:fingerprint,:at)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "delta": value.document_delta_id,
                "version": value.version,
                "process": scope.audit_process_id,
                "denominator": value.denominator.denominator_id,
                "denominator_version": value.denominator.version,
                "satisfied": by_value.get("satisfied", 0),
                "missing": by_value.get("missing", 0),
                "conflict": by_value.get("conflict", 0),
                "indeterminate": by_value.get("indeterminate", 0),
                "blocked": by_value.get("blocked", 0),
                "fingerprint": value.fingerprint,
                "at": datetime.now(UTC),
            },
        )
        for item in value.items:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_delta_items "
                    "(organization_id,workspace_id,audit_delta_id,delta_version,item_key,state,source_version_ids,source_locator_ids,rule_trace_ids,authority_decision_refs,uncertainty_codes,blocker_codes,downstream_impacts) "
                    "VALUES (:o,:w,:delta,:version,:key,:state,:sources,:locators,:traces,:authority,:uncertainty,:blockers,:impacts)"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "delta": value.document_delta_id,
                    "version": value.version,
                    "key": item.item_key,
                    "state": item.state.value,
                    "sources": list(item.source_version_ids),
                    "locators": list(item.source_locator_ids),
                    "traces": list(item.rule_trace_ids),
                    "authority": list(item.authority_decision_refs),
                    "uncertainty": list(item.uncertainty_codes),
                    "blockers": list(item.blocker_codes),
                    "impacts": list(item.downstream_impacts),
                },
            )

    def _evaluate_delta(
        self,
        context: WorkspaceContext,
        command: AuditCommand,
        *,
        scope: AuditScope,
        denominator: DeltaDenominator,
        command_type: AuditCommandType,
        persist: Callable[[Session], None],
    ) -> CommandOutcome:
        if command.command_type is not command_type:
            raise ValueError("Audit command does not match the immutable delta kind")
        self._require_scope(context, scope.organization_id, scope.workspace_id)
        if command.aggregate_id != scope.audit_process_id:
            raise ValueError("Audit command aggregate does not match the delta scope")
        if denominator.rule_set_version_id != scope.rule_set_version_id:
            raise ValueError("Audit delta denominator must pin the Audit rule set version")
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
                revision = self._require_exact_evaluating_scope(session, scope)
                outcome = AuditStateMachine().apply(ProcessState.EVALUATING, revision, command)
                if not outcome.accepted:
                    return outcome
                persist(session)
                self._advance_header(session, context, command, outcome)
                return outcome

    def _insert_causal_delta(self, session: Session, value: CausalReadinessDelta) -> None:
        scope = value.audit_scope
        if self._existing_delta_matches(
            session, scope, value.causal_delta_id, value.version, value.fingerprint
        ):
            return
        counts = {state: sum(path.state is state for path in value.paths) for state in DeltaState}
        self._insert_delta_header(
            session,
            scope=scope,
            denominator=value.denominator,
            delta_id=value.causal_delta_id,
            delta_version=value.version,
            delta_kind="causal_readiness",
            counts=counts,
            fingerprint=value.fingerprint,
        )
        for path in value.paths:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_delta_items "
                    "(organization_id,workspace_id,audit_delta_id,delta_version,item_key,state,"
                    "source_version_ids,source_locator_ids,rule_trace_ids,authority_decision_refs,"
                    "uncertainty_codes,blocker_codes,downstream_impacts) VALUES "
                    "(:o,:w,:delta,:version,:key,:state,ARRAY[]::uuid[],ARRAY[]::uuid[],"
                    ":traces,ARRAY[]::text[],:gaps,:gaps,:impacts)"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "delta": value.causal_delta_id,
                    "version": value.version,
                    "key": str(path.path_id),
                    "state": path.state.value,
                    "traces": list(path.rule_trace_ids),
                    "gaps": list(path.gap_codes),
                    "impacts": list(path.downstream_impacts),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_causal_path_versions "
                    "(organization_id,workspace_id,causal_delta_id,delta_version,path_id,"
                    "material_batch_ref,incoming_control_ref,admission_ref,work_ref,evidence_ref,"
                    "id_package_ref,presented_volume_ref,ks_ref,payment_claim_ref,state,rule_trace_ids,"
                    "gap_codes,downstream_impacts,fingerprint) VALUES "
                    "(:o,:w,:delta,:version,:path,:batch,:control,:admission,:work,:evidence,"
                    ":package,:volume,:ks,:payment,:state,:traces,:gaps,:impacts,:fingerprint)"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "delta": value.causal_delta_id,
                    "version": value.version,
                    "path": path.path_id,
                    "batch": path.material_batch_ref,
                    "control": path.incoming_control_ref,
                    "admission": path.admission_ref,
                    "work": path.work_ref,
                    "evidence": path.evidence_ref,
                    "package": path.id_package_ref,
                    "volume": path.presented_volume_ref,
                    "ks": path.ks_ref,
                    "payment": path.payment_claim_ref,
                    "state": path.state.value,
                    "traces": list(path.rule_trace_ids),
                    "gaps": list(path.gap_codes),
                    "impacts": list(path.downstream_impacts),
                    "fingerprint": digest_of(path),
                },
            )

    def _insert_package_readiness(self, session: Session, value: PackageReadiness) -> None:
        scope = value.audit_scope
        if self._existing_delta_matches(
            session, scope, value.package_readiness_id, value.version, value.fingerprint
        ):
            return
        counts = package_readiness_counts(value)
        self._insert_delta_header(
            session,
            scope=scope,
            denominator=value.denominator,
            delta_id=value.package_readiness_id,
            delta_version=value.version,
            delta_kind="package_signing_handover",
            counts=counts,
            fingerprint=value.fingerprint,
        )
        for package in value.packages:
            state = _package_state(package)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_delta_items "
                    "(organization_id,workspace_id,audit_delta_id,delta_version,item_key,state,"
                    "source_version_ids,source_locator_ids,rule_trace_ids,authority_decision_refs,"
                    "uncertainty_codes,blocker_codes,downstream_impacts) VALUES "
                    "(:o,:w,:delta,:version,:key,:state,ARRAY[]::uuid[],ARRAY[]::uuid[],"
                    "ARRAY[]::uuid[],ARRAY[]::text[],:blockers,:blockers,ARRAY[]::text[])"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "delta": value.package_readiness_id,
                    "version": value.version,
                    "key": str(package.package_id),
                    "state": state.value,
                    "blockers": list(package.blocker_codes),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_package_versions "
                    "(organization_id,workspace_id,package_id,version,audit_process_id,volume_or_book_id,"
                    "section_ref,professional_review_state,signer_authority_state,signature_state,"
                    "handover_state,acceptance_state,blocker_codes,fingerprint,evaluated_at) VALUES "
                    "(:o,:w,:package,:version,:process,:book,:section,:review,:signer,:signature,"
                    ":handover,:acceptance,:blockers,:fingerprint,:at)"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "package": package.package_id,
                    "version": package.package_version,
                    "process": scope.audit_process_id,
                    "book": package.volume_or_book_id,
                    "section": package.section_ref,
                    "review": package.professional_review_state.value,
                    "signer": package.signer_authority_state.value,
                    "signature": package.signature_state.value,
                    "handover": package.handover_state.value,
                    "acceptance": package.acceptance_state.value,
                    "blockers": list(package.blocker_codes),
                    "fingerprint": digest_of(package),
                    "at": datetime.now(UTC),
                },
            )
            for membership in package.memberships:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.audit_package_memberships "
                        "(organization_id,workspace_id,package_id,package_version,logical_occurrence_id,"
                        "ordinal,required_copies,actual_copies,register_level) VALUES "
                        "(:o,:w,:package,:version,:occurrence,:ordinal,:required,:actual,:level)"
                    ),
                    {
                        "o": scope.organization_id,
                        "w": scope.workspace_id,
                        "package": package.package_id,
                        "version": package.package_version,
                        "occurrence": membership.occurrence_id,
                        "ordinal": membership.ordinal,
                        "required": membership.required_copies,
                        "actual": membership.actual_copies,
                        "level": membership.register_level,
                    },
                )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.audit_package_delta_memberships "
                    "(organization_id,workspace_id,package_readiness_id,delta_version,package_id,package_version) "
                    "VALUES (:o,:w,:delta,:version,:package,:package_version)"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "delta": value.package_readiness_id,
                    "version": value.version,
                    "package": package.package_id,
                    "package_version": package.package_version,
                },
            )

    @staticmethod
    def _existing_delta_matches(
        session: Session,
        scope: AuditScope,
        delta_id: UUID,
        version: int,
        fingerprint: str,
    ) -> bool:
        existing = session.scalar(
            sa.text(
                "SELECT fingerprint FROM workspace.audit_delta_versions WHERE organization_id=:o "
                "AND workspace_id=:w AND audit_delta_id=:delta AND version=:version"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "delta": delta_id,
                "version": version,
            },
        )
        if existing is None:
            return False
        if str(existing) != fingerprint:
            raise ValueError("Audit delta identity is already bound to different evidence")
        return True

    @staticmethod
    def _insert_delta_header(
        session: Session,
        *,
        scope: AuditScope,
        denominator: DeltaDenominator,
        delta_id: UUID,
        delta_version: int,
        delta_kind: str,
        counts: dict[DeltaState, int],
        fingerprint: str,
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_denominator_versions "
                "(organization_id,workspace_id,denominator_id,version,audit_process_id,delta_kind,"
                "exact_scope,required_item_keys,rule_set_version_id,evidence_refs,fingerprint,created_at) "
                "VALUES (:o,:w,:denominator,:denominator_version,:process,:kind,CAST(:scope AS jsonb),"
                ":keys,:ruleset,:evidence,:fingerprint,:at)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "denominator": denominator.denominator_id,
                "denominator_version": denominator.version,
                "process": scope.audit_process_id,
                "kind": delta_kind,
                "scope": json.dumps(denominator.exact_scope),
                "keys": list(denominator.required_item_keys),
                "ruleset": denominator.rule_set_version_id,
                "evidence": list(denominator.evidence_refs),
                "fingerprint": digest_of(denominator),
                "at": datetime.now(UTC),
            },
        )
        by_value = {state.value: count for state, count in counts.items()}
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_delta_versions "
                "(organization_id,workspace_id,audit_delta_id,version,audit_process_id,delta_kind,"
                "denominator_id,denominator_version,satisfied_count,missing_count,conflict_count,"
                "indeterminate_count,blocked_count,fingerprint,evaluated_at) VALUES "
                "(:o,:w,:delta,:version,:process,:kind,:denominator,:denominator_version,:satisfied,"
                ":missing,:conflict,:indeterminate,:blocked,:fingerprint,:at)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "delta": delta_id,
                "version": delta_version,
                "process": scope.audit_process_id,
                "kind": delta_kind,
                "denominator": denominator.denominator_id,
                "denominator_version": denominator.version,
                "satisfied": by_value.get(DeltaState.SATISFIED.value, 0),
                "missing": by_value.get(DeltaState.MISSING.value, 0),
                "conflict": by_value.get(DeltaState.CONFLICT.value, 0),
                "indeterminate": by_value.get(DeltaState.INDETERMINATE.value, 0),
                "blocked": by_value.get(DeltaState.BLOCKED.value, 0),
                "fingerprint": fingerprint,
                "at": datetime.now(UTC),
            },
        )

    @staticmethod
    def _insert_action_request(session: Session, value: ActionRequest) -> None:
        scope = value.audit_scope
        existing = (
            session.execute(
                sa.text(
                    "SELECT audit_process_id,action_code,addressee_identity_id,affected_object_ref,"
                    "evidence_refs,deadline,blocking_impacts,initiator_identity_id,"
                    "verifier_identity_id,executor_identity_id,state,supersedes_version FROM "
                    "workspace.audit_action_request_versions WHERE organization_id=:o AND "
                    "workspace_id=:w AND action_request_id=:request AND version=:version"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "request": value.action_request_id,
                    "version": value.version,
                },
            )
            .mappings()
            .one_or_none()
        )
        expected = {
            "audit_process_id": scope.audit_process_id,
            "action_code": value.action_code,
            "addressee_identity_id": value.addressee_identity_id,
            "affected_object_ref": value.affected_object_ref,
            "evidence_refs": list(value.evidence_refs),
            "deadline": value.deadline,
            "blocking_impacts": list(value.blocking_impacts),
            "initiator_identity_id": value.initiator_identity_id,
            "verifier_identity_id": value.verifier_identity_id,
            "executor_identity_id": value.executor_identity_id,
            "state": value.state.value,
            "supersedes_version": value.supersedes_version,
        }
        if existing is not None:
            if dict(existing) != expected:
                raise ValueError("Action-request identity is already bound to different evidence")
            return
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_action_request_versions "
                "(organization_id,workspace_id,action_request_id,version,audit_process_id,action_code,"
                "addressee_identity_id,affected_object_ref,evidence_refs,deadline,blocking_impacts,"
                "initiator_identity_id,verifier_identity_id,executor_identity_id,state,"
                "supersedes_version,created_at) VALUES "
                "(:o,:w,:request,:version,:process,:action,:addressee,:affected,:evidence,:deadline,"
                ":impacts,:initiator,:verifier,:executor,:state,:supersedes,CURRENT_TIMESTAMP)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "request": value.action_request_id,
                "version": value.version,
                "process": scope.audit_process_id,
                "action": value.action_code,
                "addressee": value.addressee_identity_id,
                "affected": value.affected_object_ref,
                "evidence": list(value.evidence_refs),
                "deadline": value.deadline,
                "impacts": list(value.blocking_impacts),
                "initiator": value.initiator_identity_id,
                "verifier": value.verifier_identity_id,
                "executor": value.executor_identity_id,
                "state": value.state.value,
                "supersedes": value.supersedes_version,
            },
        )

    @staticmethod
    def _insert_report(session: Session, value: AuditReport) -> None:
        """Persist a final report only when every evidence reference is exact.

        ``AuditReport`` carries fingerprints for the snapshot and three delta
        kinds, rather than a mutable "latest" projection.  A fingerprint must
        resolve to exactly one persisted version in this Audit process; a
        duplicate match is ambiguity, not a reason to select an arbitrary
        version.  Action-request membership is intentionally not represented
        until its versioned contract exists, and is rejected by the public
        method before this helper is reached.
        """

        scope = value.audit_scope
        snapshot_fingerprint = session.scalar(
            sa.text(
                "SELECT fingerprint FROM workspace.corpus_snapshot_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND corpus_snapshot_id=:snapshot "
                "AND version=:version"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "snapshot": scope.corpus_snapshot_id,
                "version": scope.corpus_snapshot_version,
            },
        )
        if (
            snapshot_fingerprint is None
            or str(snapshot_fingerprint) != value.corpus_snapshot_fingerprint
        ):
            raise ValueError("Audit report must reference the exact persisted corpus snapshot")

        document_version = PostgresCorpusAuditStore._resolve_report_delta_version(
            session,
            scope,
            value.document_delta_id,
            value.document_delta_fingerprint,
            "document",
        )
        causal_version = PostgresCorpusAuditStore._resolve_report_delta_version(
            session,
            scope,
            value.causal_delta_id,
            value.causal_delta_fingerprint,
            "causal_readiness",
        )
        package_version = PostgresCorpusAuditStore._resolve_report_delta_version(
            session,
            scope,
            value.package_readiness_id,
            value.package_readiness_fingerprint,
            "package_signing_handover",
        )
        if value.outcome.value == "complete" and value.unresolved_codes:
            raise ValueError("A complete Audit report cannot retain unresolved codes")

        existing = session.scalar(
            sa.text(
                "SELECT fingerprint FROM workspace.audit_report_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND audit_report_id=:report "
                "AND version=:version"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "report": value.audit_report_id,
                "version": value.version,
            },
        )
        if existing is not None:
            if str(existing) != value.fingerprint:
                raise ValueError("Audit report identity is already bound to different evidence")
            return
        session.execute(
            sa.text(
                "INSERT INTO workspace.audit_report_versions "
                "(organization_id,workspace_id,audit_report_id,version,audit_process_id,"
                "corpus_snapshot_id,corpus_snapshot_version,document_delta_id,document_delta_version,"
                "causal_delta_id,causal_delta_version,package_delta_id,package_delta_version,outcome,"
                "unresolved_codes,product_ready,fingerprint,created_at) VALUES "
                "(:o,:w,:report,:version,:process,:snapshot,:snapshot_version,:document,"
                ":document_version,:causal,:causal_version,:package,:package_version,:outcome,"
                ":unresolved,false,:fingerprint,:created_at)"
            ),
            {
                "o": scope.organization_id,
                "w": scope.workspace_id,
                "report": value.audit_report_id,
                "version": value.version,
                "process": scope.audit_process_id,
                "snapshot": scope.corpus_snapshot_id,
                "snapshot_version": scope.corpus_snapshot_version,
                "document": value.document_delta_id,
                "document_version": document_version,
                "causal": value.causal_delta_id,
                "causal_version": causal_version,
                "package": value.package_readiness_id,
                "package_version": package_version,
                "outcome": value.outcome.value,
                "unresolved": list(value.unresolved_codes),
                "fingerprint": value.fingerprint,
                "created_at": value.created_at,
            },
        )

    @staticmethod
    def _resolve_report_delta_version(
        session: Session,
        scope: AuditScope,
        delta_id: UUID,
        fingerprint: str,
        delta_kind: str,
    ) -> int:
        rows = (
            session.execute(
                sa.text(
                    "SELECT version FROM workspace.audit_delta_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND audit_process_id=:process "
                    "AND audit_delta_id=:delta AND delta_kind=:kind AND fingerprint=:fingerprint "
                    "ORDER BY version"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "process": scope.audit_process_id,
                    "delta": delta_id,
                    "kind": delta_kind,
                    "fingerprint": fingerprint,
                },
            )
            .scalars()
            .all()
        )
        if len(rows) != 1:
            raise ValueError(
                "Audit report delta reference must resolve to exactly one persisted evidence version"
            )
        return int(rows[0])

    @staticmethod
    def _require_exact_evaluating_scope(session: Session, scope: AuditScope) -> int:
        row = (
            session.execute(
                sa.text(
                    "SELECT state,revision,mode_execution_id,corpus_snapshot_id,corpus_snapshot_version,"
                    "rule_set_version_id FROM workspace.audit_processes WHERE "
                    "organization_id=:o AND workspace_id=:w AND audit_process_id=:process FOR UPDATE"
                ),
                {
                    "o": scope.organization_id,
                    "w": scope.workspace_id,
                    "process": scope.audit_process_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("Audit process is not visible in the transaction scope")
        expected = {
            "mode_execution_id": scope.mode_execution_id,
            "corpus_snapshot_id": scope.corpus_snapshot_id,
            "corpus_snapshot_version": scope.corpus_snapshot_version,
            "rule_set_version_id": scope.rule_set_version_id,
        }
        if {key: row[key] for key in expected} != expected:
            raise ValueError("Audit process is bound to a different immutable scope")
        if ProcessState(str(row["state"])) is not ProcessState.EVALUATING:
            raise ValueError("Audit mutation requires an evaluating Audit process")
        return int(row["revision"])

    @staticmethod
    def _advance_header(
        session: Session,
        context: WorkspaceContext,
        command: AuditCommand,
        outcome: CommandOutcome,
    ) -> None:
        session.execute(
            sa.select(sa.func.set_config("asd.audit_operation_id", str(command.command_id), True))
        ).one()
        updated = session.scalar(
            sa.text(
                "UPDATE workspace.audit_processes SET state=:state,revision=:revision,"
                "current_fingerprint=:fingerprint,updated_at=CURRENT_TIMESTAMP WHERE "
                "organization_id=:organization AND workspace_id=:workspace "
                "AND audit_process_id=:process AND revision=:expected_revision "
                "RETURNING revision"
            ),
            {
                "state": outcome.state.value,
                "revision": outcome.revision,
                "fingerprint": command.semantic_digest,
                "organization": context.organization_id,
                "workspace": context.workspace_id,
                "process": command.aggregate_id,
                "expected_revision": command.expected_revision,
            },
        )
        if updated != outcome.revision:
            raise RuntimeError("Audit process revision changed during the transaction")

    @staticmethod
    def _apply_command_in_session(
        session: Session, context: WorkspaceContext, command: AuditCommand
    ) -> CommandOutcome:
        row = (
            session.execute(
                sa.text(
                    "SELECT state,revision FROM workspace.audit_processes WHERE "
                    "organization_id=:organization AND workspace_id=:workspace "
                    "AND audit_process_id=:process FOR UPDATE"
                ),
                {
                    "organization": context.organization_id,
                    "workspace": context.workspace_id,
                    "process": command.aggregate_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("Audit process is not visible in the transaction scope")
        state = ProcessState(str(row["state"]))
        outcome = AuditStateMachine().apply(state, int(row["revision"]), command)
        if outcome.accepted:
            PostgresCorpusAuditStore._advance_header(session, context, command, outcome)
        return outcome

    @staticmethod
    def _require_scope(
        context: WorkspaceContext, organization_id: UUID, workspace_id: UUID
    ) -> None:
        if context.organization_id != organization_id or context.workspace_id != workspace_id:
            raise ValueError("Corpus/Audit record does not match the transaction scope")


def _set_scope(session: Session, context: WorkspaceContext) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    ).one()


def _package_state(package: PackageAssessment) -> DeltaState:
    """Return the conservative package state without concealing a blocker."""

    states = (
        package.professional_review_state,
        package.signer_authority_state,
        package.signature_state,
        package.handover_state,
        package.acceptance_state,
    )
    for state in (
        DeltaState.BLOCKED,
        DeltaState.CONFLICT,
        DeltaState.MISSING,
        DeltaState.INDETERMINATE,
    ):
        if state in states:
            return state
    if all(state is DeltaState.NOT_APPLICABLE for state in states):
        return DeltaState.NOT_APPLICABLE
    return DeltaState.SATISFIED
