"""Narrow transactional persistence for shared corpus and Audit records."""

# ruff: noqa: E501

from __future__ import annotations

import json
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

from .models import DeltaState, DocumentDelta


class PostgresCorpusAuditStore:
    """Persist only typed WP-14 aggregates; arbitrary SQL is not exposed."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

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
        counts = {state: sum(item.state is state for item in value.items) for state in DeltaState}
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, context)
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
                by_value = {getattr(key, "value", str(key)): count for key, count in counts.items()}
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
