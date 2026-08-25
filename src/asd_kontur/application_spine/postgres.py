"""PostgreSQL adapter for Product Application Spine commands and queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .models import (
    BatchRegistration,
    ClaimedJob,
    DocumentSummary,
    EvidencePanel,
    JobKind,
    JobProgress,
    JobState,
    JobSummary,
    KnowledgeStatus,
    PageLocator,
    ResetChallenge,
    WorkspaceSummary,
    decode_cursor,
    encode_cursor,
    semantic_digest,
)
from .object_store import StagedObject, WorkspaceObjectStore

OWNER_ORGANIZATION_NAMESPACE = UUID("a57c6d8e-f982-4ec3-8c0f-96d35debd0be")
TERMINAL_STATES = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.RECONCILIATION_REQUIRED,
    }
)


class SpinePersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RejectedUpload:
    ordinal: int
    safe_display_name: str
    relative_path: str
    client_media_type: str | None
    client_size_bytes: int | None
    client_digest: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class RegisteredDocument:
    document_id: UUID
    document_version: int
    source_artifact_id: UUID
    source_version_id: UUID
    object_id: UUID
    duplicate: bool


class SpinePostgresRepository:
    """All Product Spine SQL lives here; web handlers use application services."""

    def __init__(self, engine: Engine, *, event_retention_seconds: int = 86400) -> None:
        self._engine = engine
        self._event_retention_seconds = event_retention_seconds

    def migration_head(self) -> str:
        with self._engine.connect() as connection:
            value = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        if value is None:
            raise SpinePersistenceError("migration_head_unavailable")
        return str(value)

    def create_workspace(
        self,
        *,
        owner_identity_id: str,
        display_name: str,
        correlation_id: UUID,
    ) -> WorkspaceSummary:
        organization_id = uuid5(OWNER_ORGANIZATION_NAMESPACE, owner_identity_id)
        construction_object_id = uuid7()
        workspace_id = uuid7()
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            session.execute(
                sa.text(
                    "INSERT INTO organization.organizations "
                    "(organization_id,display_name,external_id,status,revision,retention_class,"
                    "created_by_identity_id,correlation_id) "
                    "VALUES (:organization,'ASD-KONTUR owner installation',:external,'active',1,"
                    "'organization.local-owner',:owner,:correlation) ON CONFLICT (organization_id) DO NOTHING"
                ),
                {
                    "organization": organization_id,
                    "external": f"local-owner:{owner_identity_id}",
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO application.owner_organization_grants "
                    "(owner_identity_id,organization_id,capability_set,grant_version) "
                    "VALUES (:owner,:organization,ARRAY['workspace.create','workspace.read',"
                    "'workspace.write','workspace.reset.plan','workspace.reset.authorize'],1) "
                    "ON CONFLICT (owner_identity_id,organization_id) DO NOTHING"
                ),
                {"owner": owner_identity_id, "organization": organization_id},
            )
            session.execute(
                sa.text(
                    "INSERT INTO organization.construction_objects "
                    "(organization_id,construction_object_id,display_name,external_id,status,revision,"
                    "retention_class,created_by_identity_id,correlation_id) "
                    "VALUES (:organization,:construction,:display,:external,'active',1,"
                    "'workspace.construction-object',:owner,:correlation)"
                ),
                {
                    "organization": organization_id,
                    "construction": construction_object_id,
                    "display": display_name.strip(),
                    "external": f"workspace:{workspace_id}",
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.workspaces "
                    "(organization_id,workspace_id,construction_object_id,lifecycle_state,lifecycle_version,"
                    "workspace_revision,write_fenced,legal_hold_active,revision,retention_class,"
                    "retention_profile_key,retention_profile_version,policy_assignment_key,"
                    "policy_assignment_version,rule_set_key,rule_set_version,contract_registry_version,"
                    "created_by_identity_id,correlation_id) VALUES "
                    "(:organization,:workspace,:construction,'PROVISIONING',1,1,false,false,1,"
                    "'workspace.canonical','retention.spine-local','0.1.0','policy.spine-local','0.1.0',"
                    "'rules.none','0.1.0','2.1.0',:owner,:correlation)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "construction": construction_object_id,
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.workspace_revisions "
                    "(organization_id,workspace_id,revision,workspace_version_id,lifecycle_state,reason_code,"
                    "retention_profile_key,retention_profile_version,policy_assignment_key,"
                    "policy_assignment_version,rule_set_key,rule_set_version,contract_registry_version,"
                    "created_by_identity_id,correlation_id) VALUES "
                    "(:organization,:workspace,1,:version,'PROVISIONING','workspace.provisioned',"
                    "'retention.spine-local','0.1.0','policy.spine-local','0.1.0','rules.none','0.1.0',"
                    "'2.1.0',:owner,:correlation)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "version": uuid7(),
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
        return self.get_workspace(owner_identity_id=owner_identity_id, workspace_id=workspace_id)

    def list_workspaces(self, *, owner_identity_id: str) -> tuple[WorkspaceSummary, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                sa.text("SELECT * FROM application.list_authorized_workspaces(:owner)"),
                {"owner": owner_identity_id},
            ).all()
        return tuple(_workspace_summary(row) for row in rows)

    def get_workspace(self, *, owner_identity_id: str, workspace_id: UUID) -> WorkspaceSummary:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT w.organization_id,w.workspace_id,w.construction_object_id,c.display_name,"
                    "w.lifecycle_state,w.lifecycle_version,w.workspace_revision,w.write_fenced,w.created_at "
                    "FROM workspace.workspaces w JOIN organization.construction_objects c "
                    "ON c.organization_id=w.organization_id AND c.construction_object_id=w.construction_object_id "
                    "WHERE w.organization_id=:organization AND w.workspace_id=:workspace"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            ).one_or_none()
        if row is None:
            raise SpinePersistenceError("workspace_not_found")
        return _workspace_summary(row)

    def resolve_scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            organization_id = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if organization_id is None:
            raise SpinePersistenceError("workspace_not_found")
        return UUID(str(organization_id))

    def register_batch(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        staged_items: tuple[tuple[int, StagedObject], ...],
        rejected_items: tuple[RejectedUpload, ...],
        object_store: WorkspaceObjectStore,
        correlation_id: UUID,
        client_manifest_digest: str,
    ) -> BatchRegistration:
        if not staged_items and not rejected_items:
            raise SpinePersistenceError("empty_batch")
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        manifest_id = uuid7()
        committed_created: list[str] = []
        accepted_ids: list[UUID] = []
        duplicate_ids: list[UUID] = []
        job_ids: list[UUID] = []
        total_bytes = sum(item.size_bytes for _, item in staged_items) + sum(
            item.client_size_bytes or 0 for item in rejected_items
        )
        try:
            with Session(self._engine) as session, session.begin():
                _set_scope(session, organization_id, workspace_id)
                session.execute(
                    sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:digest,0))"),
                    {"digest": client_manifest_digest},
                ).one()
                existing_manifest = session.execute(
                    sa.text(
                        "SELECT intake_manifest_id,correlation_id,rejected_file_count "
                        "FROM workspace.intake_manifests WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND manifest_digest=:digest"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "digest": client_manifest_digest,
                    },
                ).one_or_none()
                if existing_manifest is not None:
                    items = session.execute(
                        sa.text(
                            "SELECT outcome,document_id FROM workspace.intake_manifest_items "
                            "WHERE organization_id=:organization AND workspace_id=:workspace "
                            "AND intake_manifest_id=:manifest ORDER BY item_ordinal"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "manifest": existing_manifest.intake_manifest_id,
                        },
                    ).all()
                    jobs = session.scalars(
                        sa.text(
                            "SELECT job_id FROM workspace.durable_jobs WHERE "
                            "organization_id=:organization AND workspace_id=:workspace "
                            "AND correlation_id=:correlation ORDER BY priority DESC,created_at,job_id"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "correlation": existing_manifest.correlation_id,
                        },
                    ).all()
                    for _, staged in staged_items:
                        object_store.abort(staged)
                    return BatchRegistration(
                        UUID(str(existing_manifest.intake_manifest_id)),
                        client_manifest_digest,
                        tuple(
                            UUID(str(item.document_id))
                            for item in items
                            if item.outcome == "accepted" and item.document_id is not None
                        ),
                        tuple(
                            UUID(str(item.document_id))
                            for item in items
                            if item.outcome == "duplicate" and item.document_id is not None
                        ),
                        int(existing_manifest.rejected_file_count),
                        tuple(UUID(str(job_id)) for job_id in jobs),
                    )
                workspace_state = session.execute(
                    sa.text(
                        "SELECT lifecycle_state,write_fenced FROM workspace.workspaces "
                        "WHERE organization_id=:organization AND workspace_id=:workspace"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                ).one()
                if tuple(workspace_state) != ("ACTIVE", False):
                    raise SpinePersistenceError("workspace_not_writable")
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.intake_manifests "
                        "(organization_id,workspace_id,intake_manifest_id,manifest_version,manifest_digest,"
                        "declared_file_count,declared_total_bytes,accepted_file_count,rejected_file_count,"
                        "status,created_by_identity_id,correlation_id) VALUES "
                        "(:organization,:workspace,:manifest,1,:digest,:declared,:bytes,:accepted,:rejected,"
                        ":status,:owner,:correlation)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "manifest": manifest_id,
                        "digest": client_manifest_digest,
                        "declared": len(staged_items) + len(rejected_items),
                        "bytes": total_bytes,
                        "accepted": len(staged_items),
                        "rejected": len(rejected_items),
                        "status": "partial"
                        if staged_items and rejected_items
                        else "admitted"
                        if staged_items
                        else "rejected",
                        "owner": owner_identity_id,
                        "correlation": correlation_id,
                    },
                )
                for ordinal, staged in staged_items:
                    committed = object_store.commit(staged)
                    if committed.created:
                        committed_created.append(staged.object_key)
                    registered, jobs = self._register_document(
                        session,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        owner_identity_id=owner_identity_id,
                        correlation_id=correlation_id,
                        manifest_id=manifest_id,
                        ordinal=ordinal,
                        staged=staged,
                    )
                    (duplicate_ids if registered.duplicate else accepted_ids).append(
                        registered.document_id
                    )
                    job_ids.extend(jobs)
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.intake_manifest_items "
                            "(organization_id,workspace_id,intake_manifest_id,item_ordinal,safe_display_name,"
                            "sanitized_relative_path,client_media_type,client_size_bytes,outcome,document_id) "
                            "VALUES (:organization,:workspace,:manifest,:ordinal,:name,:path,:media,:size,"
                            ":outcome,:document)"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "manifest": manifest_id,
                            "ordinal": ordinal,
                            "name": staged.safe_display_name,
                            "path": staged.relative_path,
                            "media": staged.media_type,
                            "size": staged.size_bytes,
                            "outcome": "duplicate" if registered.duplicate else "accepted",
                            "document": registered.document_id,
                        },
                    )
                for rejected in rejected_items:
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.intake_manifest_items "
                            "(organization_id,workspace_id,intake_manifest_id,item_ordinal,safe_display_name,"
                            "sanitized_relative_path,client_media_type,client_size_bytes,client_digest,"
                            "outcome,reason_code) VALUES (:organization,:workspace,:manifest,:ordinal,:name,"
                            ":path,:media,:size,:client_digest,'rejected',:reason)"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "manifest": manifest_id,
                            "ordinal": rejected.ordinal,
                            "name": rejected.safe_display_name,
                            "path": rejected.relative_path,
                            "media": rejected.client_media_type,
                            "size": rejected.client_size_bytes,
                            "client_digest": rejected.client_digest,
                            "reason": rejected.reason_code,
                        },
                    )
        except BaseException:
            for _, staged in staged_items:
                object_store.abort(staged)
            for object_key in committed_created:
                object_store.delete(object_key)
            raise
        return BatchRegistration(
            manifest_id,
            client_manifest_digest,
            tuple(accepted_ids),
            tuple(duplicate_ids),
            len(rejected_items),
            tuple(job_ids),
        )

    def _register_document(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        owner_identity_id: str,
        correlation_id: UUID,
        manifest_id: UUID,
        ordinal: int,
        staged: StagedObject,
    ) -> tuple[RegisteredDocument, tuple[UUID, ...]]:
        semantic_key = semantic_digest({"relative_path": staged.relative_path.casefold()})
        document_id = session.scalar(
            sa.text(
                "SELECT document_id FROM workspace.document_records "
                "WHERE organization_id=:organization AND workspace_id=:workspace "
                "AND semantic_key_digest=:semantic"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "semantic": semantic_key,
            },
        )
        if document_id is None:
            document_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.document_records "
                    "(organization_id,workspace_id,document_id,semantic_key_digest,created_by_identity_id,"
                    "correlation_id) VALUES (:organization,:workspace,:document,:semantic,:owner,:correlation)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                    "semantic": semantic_key,
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
        existing = session.execute(
            sa.text(
                "SELECT version,source_artifact_id,source_version_id,object_id "
                "FROM workspace.document_versions WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND document_id=:document AND content_digest=:digest"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "document": document_id,
                "digest": staged.digest,
            },
        ).one_or_none()
        if existing is not None:
            return (
                RegisteredDocument(
                    UUID(str(document_id)),
                    int(existing.version),
                    UUID(str(existing.source_artifact_id)),
                    UUID(str(existing.source_version_id)),
                    UUID(str(existing.object_id)),
                    True,
                ),
                (),
            )
        document_version = int(
            session.scalar(
                sa.text(
                    "SELECT COALESCE(max(version),0)+1 FROM workspace.document_versions "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND document_id=:document"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                },
            )
        )
        object_id = session.scalar(
            sa.text(
                "SELECT object_id FROM workspace.objects WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND content_digest=:digest LIMIT 1"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "digest": staged.digest,
            },
        )
        if object_id is None:
            object_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.objects "
                    "(organization_id,workspace_id,object_id,object_version,object_class,content_digest,"
                    "size_bytes,media_type,storage_adapter_key,storage_receipt_ref,access_capability_ref,"
                    "classification,retention_class,created_by_identity_id,correlation_id) VALUES "
                    "(:organization,:workspace,:object,1,'workspace_source',:digest,:size,:media,"
                    "'local-workspace-object-store-v0.1',:receipt,'document.read','workspace_restricted',"
                    "'workspace.source-bytes',:owner,:correlation)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "object": object_id,
                    "digest": staged.digest,
                    "size": staged.size_bytes,
                    "media": staged.media_type,
                    "receipt": f"object:{staged.digest}",
                    "owner": owner_identity_id,
                    "correlation": correlation_id,
                },
            )
        source_artifact_id = UUID(str(document_id))
        session.execute(
            sa.text(
                "INSERT INTO workspace.source_artifacts "
                "(organization_id,workspace_id,source_artifact_id,source_kind,title,status,revision,"
                "retention_class,created_by_identity_id,correlation_id) VALUES "
                "(:organization,:workspace,:source,'project_evidence',:title,'active',1,"
                "'workspace.source',:owner,:correlation) ON CONFLICT DO NOTHING"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "source": source_artifact_id,
                "title": staged.safe_display_name,
                "owner": owner_identity_id,
                "correlation": correlation_id,
            },
        )
        receipt_id = uuid7()
        attempt_id = uuid7()
        source_version_id = uuid7()
        operation_id = f"intake:{manifest_id}:{ordinal}"
        session.execute(
            sa.text(
                "INSERT INTO workspace.source_object_receipts "
                "(organization_id,workspace_id,object_receipt_id,object_id,object_version,adapter_key,"
                "operation_id,status,observed_digest,observed_size_bytes,residue_state) VALUES "
                "(:organization,:workspace,:receipt,:object,1,'local-workspace-object-store-v0.1',"
                ":operation,'verified',:digest,:size,'none')"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "receipt": receipt_id,
                "object": object_id,
                "operation": operation_id,
                "digest": staged.digest,
                "size": staged.size_bytes,
            },
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.acquisition_attempts "
                "(organization_id,workspace_id,acquisition_attempt_id,source_artifact_id,"
                "acquisition_method,external_locator,requested_at,retrieved_at,status,"
                "observed_content_digest,object_receipt_id,correlation_id) VALUES "
                "(:organization,:workspace,:attempt,:source,'browser_stream_upload',:locator,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'accepted',:digest,:receipt,:correlation)"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "attempt": attempt_id,
                "source": source_artifact_id,
                "locator": staged.relative_path,
                "digest": staged.digest,
                "receipt": receipt_id,
                "correlation": correlation_id,
            },
        )
        metadata_digest = semantic_digest(
            {
                "display_name": staged.safe_display_name,
                "relative_path": staged.relative_path,
                "media_type": staged.media_type,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.source_versions "
                "(organization_id,workspace_id,source_version_id,source_artifact_id,version_ordinal,"
                "external_version_label,object_id,object_receipt_id,acquisition_attempt_id,content_digest,"
                "semantic_metadata_digest,acquisition_method,retrieved_at,admission_status,"
                "admitted_by_identity_id,retention_class) VALUES "
                "(:organization,:workspace,:version_id,:source,:ordinal,:label,:object,:receipt,:attempt,"
                ":digest,:metadata,'browser_stream_upload',CURRENT_TIMESTAMP,'accepted',:owner,"
                "'workspace.source-version')"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "version_id": source_version_id,
                "source": source_artifact_id,
                "ordinal": document_version,
                "label": f"upload-{document_version}-{staged.digest[7:19]}",
                "object": object_id,
                "receipt": receipt_id,
                "attempt": attempt_id,
                "digest": staged.digest,
                "metadata": metadata_digest,
                "owner": owner_identity_id,
            },
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.document_versions "
                "(organization_id,workspace_id,document_id,version,source_artifact_id,source_version_id,"
                "object_id,object_version,safe_display_name,sanitized_relative_path,media_type,size_bytes,"
                "content_digest,object_key,provenance) VALUES "
                "(:organization,:workspace,:document,:version,:source,:source_version,:object,1,:name,"
                ":path,:media,:size,:digest,:object_key,CAST(:provenance AS jsonb))"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "document": document_id,
                "version": document_version,
                "source": source_artifact_id,
                "source_version": source_version_id,
                "object": object_id,
                "name": staged.safe_display_name,
                "path": staged.relative_path,
                "media": staged.media_type,
                "size": staged.size_bytes,
                "digest": staged.digest,
                "object_key": staged.object_key,
                "provenance": _json(
                    {
                        "intake_manifest_id": manifest_id,
                        "item_ordinal": ordinal,
                        "acquisition_attempt_id": attempt_id,
                        "object_receipt_id": receipt_id,
                    }
                ),
            },
        )
        self._append_document_state(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            document_id=UUID(str(document_id)),
            document_version=document_version,
            admission_status="pending",
            extraction_status="not_started",
            page_count=None,
            capability_gaps=(),
            caused_by_job_id=None,
        )
        self._activate_document_version(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            document_id=UUID(str(document_id)),
            document_version=document_version,
            owner_identity_id=owner_identity_id,
        )
        jobs = self._enqueue_document_jobs(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            document_id=UUID(str(document_id)),
            document_version=document_version,
            source_version_id=source_version_id,
            object_key=staged.object_key,
            media_type=staged.media_type,
            content_digest=staged.digest,
            owner_identity_id=owner_identity_id,
            correlation_id=correlation_id,
        )
        return (
            RegisteredDocument(
                UUID(str(document_id)),
                document_version,
                source_artifact_id,
                source_version_id,
                UUID(str(object_id)),
                False,
            ),
            jobs,
        )

    def _activate_document_version(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        document_id: UUID,
        document_version: int,
        owner_identity_id: str,
    ) -> None:
        prior = session.execute(
            sa.text(
                "SELECT activation_decision_id,decision_version FROM "
                "workspace.document_version_activation_decisions WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND document_id=:document "
                "ORDER BY decision_version DESC LIMIT 1"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "document": document_id,
            },
        ).one_or_none()
        activation_id = UUID(str(prior.activation_decision_id)) if prior else uuid7()
        decision_version = int(prior.decision_version) + 1 if prior else 1
        decision_digest = semantic_digest(
            {
                "activation_id": activation_id,
                "decision_version": decision_version,
                "document_id": document_id,
                "document_version": document_version,
                "reason": "intake.version-selected",
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.document_version_activation_decisions "
                "(organization_id,workspace_id,activation_decision_id,document_id,decision_version,"
                "selected_document_version,supersedes_decision_version,reason_code,decision_digest,"
                "decided_by_identity_id) VALUES (:organization,:workspace,:activation,:document,"
                ":decision_version,:selected,:supersedes,'intake.version-selected',:digest,:owner)"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "activation": activation_id,
                "document": document_id,
                "decision_version": decision_version,
                "selected": document_version,
                "supersedes": int(prior.decision_version) if prior else None,
                "digest": decision_digest,
                "owner": owner_identity_id,
            },
        )

    def _enqueue_document_jobs(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        document_id: UUID,
        document_version: int,
        source_version_id: UUID,
        object_key: str,
        media_type: str,
        content_digest: str,
        owner_identity_id: str,
        correlation_id: UUID,
    ) -> tuple[UUID, ...]:
        manifest = {
            "document_id": document_id,
            "document_version": document_version,
            "source_version_id": source_version_id,
            "object_key": object_key,
            "media_type": media_type,
            "content_digest": content_digest,
        }
        job_ids: list[UUID] = []
        prior: UUID | None = None
        for priority, kind in enumerate(JobKind, start=1):
            if kind is JobKind.WORKSPACE_RESET_RECONCILIATION:
                continue
            job_id = uuid7()
            job_ids.append(job_id)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,input_digest,"
                    "idempotency_key,state,priority,max_attempts,retry_policy_version,provenance,"
                    "correlation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,:document,:kind,CAST(:manifest AS jsonb),:digest,:idempotency,"
                    "'queued',:priority,3,'spine-retry-v0.1',CAST(:provenance AS jsonb),:correlation,:owner)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": job_id,
                    "document": document_id,
                    "kind": kind.value,
                    "manifest": _json(manifest),
                    "digest": semantic_digest({"kind": kind.value, "manifest": manifest}),
                    "idempotency": f"document:{document_id}:{document_version}:{kind.value}",
                    "priority": 100 - priority,
                    "provenance": _json(
                        {
                            "contract": "application.durable-job@2.1.0",
                            "source_version_id": source_version_id,
                        }
                    ),
                    "correlation": correlation_id,
                    "owner": owner_identity_id,
                },
            )
            if prior is not None:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.durable_job_dependencies "
                        "(organization_id,workspace_id,job_id,depends_on_job_id,dependency_kind) "
                        "VALUES (:organization,:workspace,:job,:prior,'success_required')"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "job": job_id,
                        "prior": prior,
                    },
                )
            self._append_event(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_id=job_id,
                event_type="job.queued",
                safe_message_code="job.queued",
                current=0,
                total=1,
                terminal=False,
            )
            prior = job_id
        return tuple(job_ids)

    def list_documents(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        limit: int,
        cursor: str | None,
        media_type: str | None = None,
        query: str | None = None,
        status: str | None = None,
        sort: str = "recorded_desc",
    ) -> tuple[tuple[DocumentSummary, ...], str | None]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        if not 1 <= limit <= 200:
            raise SpinePersistenceError("invalid_page_limit")
        cursor_time: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            time_raw, id_raw = decode_cursor(cursor, 2)
            cursor_time = datetime.fromisoformat(time_raw)
            cursor_id = UUID(id_raw)
        filters = [
            "d.organization_id=:organization",
            "d.workspace_id=:workspace",
        ]
        parameters: dict[str, object] = {
            "organization": organization_id,
            "workspace": workspace_id,
            "limit": limit + 1,
        }
        if sort not in {"recorded_asc", "recorded_desc"}:
            raise SpinePersistenceError("document_sort_invalid")
        direction = "ASC" if sort == "recorded_asc" else "DESC"
        comparator = ">" if sort == "recorded_asc" else "<"
        if cursor_time and cursor_id:
            filters.append(f"(v.recorded_at,v.document_id) {comparator} (:cursor_time,:cursor_id)")
            parameters.update(cursor_time=cursor_time, cursor_id=cursor_id)
        if media_type:
            filters.append("v.media_type=:media_type")
            parameters["media_type"] = media_type
        if query:
            filters.append("v.safe_display_name ILIKE :query")
            parameters["query"] = f"%{query}%"
        if status:
            filters.append("(s.admission_status=:status OR s.extraction_status=:status)")
            parameters["status"] = status
        statement = f"""
          SELECT v.*,s.admission_status,s.extraction_status,s.page_count,s.capability_gaps,
            COALESCE(history.prior_versions,ARRAY[]::bigint[]) AS prior_versions,
            COALESCE(jobs.job_ids,ARRAY[]::uuid[]) AS job_ids
          FROM workspace.document_records d
          JOIN LATERAL (
            SELECT a.selected_document_version
            FROM workspace.document_version_activation_decisions a
            WHERE a.organization_id=d.organization_id AND a.workspace_id=d.workspace_id
              AND a.document_id=d.document_id
            ORDER BY a.decision_version DESC LIMIT 1
          ) a ON true
          JOIN workspace.document_versions v ON v.organization_id=d.organization_id
            AND v.workspace_id=d.workspace_id AND v.document_id=d.document_id
            AND v.version=a.selected_document_version
          JOIN LATERAL (
            SELECT state.admission_status,state.extraction_status,state.page_count,
              state.capability_gaps
            FROM workspace.document_processing_states state
            WHERE state.organization_id=v.organization_id AND state.workspace_id=v.workspace_id
              AND state.document_id=v.document_id AND state.document_version=v.version
            ORDER BY state.state_sequence DESC LIMIT 1
          ) s ON true
          LEFT JOIN LATERAL (
            SELECT array_agg(history_version.version ORDER BY history_version.version) AS prior_versions
            FROM workspace.document_versions history_version
            WHERE history_version.organization_id=v.organization_id
              AND history_version.workspace_id=v.workspace_id
              AND history_version.document_id=v.document_id AND history_version.version<>v.version
          ) history ON true
          LEFT JOIN LATERAL (
            SELECT array_agg(job.job_id ORDER BY job.priority DESC,job.created_at,job.job_id) AS job_ids
            FROM workspace.durable_jobs job
            WHERE job.organization_id=v.organization_id AND job.workspace_id=v.workspace_id
              AND job.subject_document_id=v.document_id
          ) jobs ON true
          WHERE {" AND ".join(filters)}
          ORDER BY v.recorded_at {direction},v.document_id {direction} LIMIT :limit
        """
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(sa.text(statement), parameters).all()
        has_more = len(rows) > limit
        visible = rows[:limit]
        documents = tuple(_document_summary(row) for row in visible)
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = encode_cursor(last.recorded_at.isoformat(), last.document_id)
        return documents, next_cursor

    def get_document(
        self, *, owner_identity_id: str, workspace_id: UUID, document_id: UUID
    ) -> DocumentSummary:
        documents, _ = self.list_documents(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            limit=200,
            cursor=None,
        )
        for document in documents:
            if document.document_id == document_id:
                return document
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "WITH selected AS (SELECT selected_document_version FROM "
                    "workspace.document_version_activation_decisions WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND document_id=:document ORDER BY decision_version DESC LIMIT 1),"
                    "latest_state AS (SELECT * FROM workspace.document_processing_states "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND document_id=:document "
                    "ORDER BY document_version DESC,state_sequence DESC LIMIT 1) "
                    "SELECT v.*,s.admission_status,s.extraction_status,s.page_count,s.capability_gaps,"
                    "ARRAY(SELECT history.version FROM workspace.document_versions history WHERE "
                    "history.organization_id=v.organization_id AND history.workspace_id=v.workspace_id "
                    "AND history.document_id=v.document_id AND history.version<>v.version "
                    "ORDER BY history.version) AS prior_versions,"
                    "ARRAY(SELECT job.job_id FROM workspace.durable_jobs job WHERE "
                    "job.organization_id=v.organization_id AND job.workspace_id=v.workspace_id "
                    "AND job.subject_document_id=v.document_id ORDER BY job.priority DESC,"
                    "job.created_at,job.job_id) AS job_ids "
                    "FROM workspace.document_versions v JOIN selected a ON a.selected_document_version=v.version "
                    "JOIN latest_state s ON s.document_version=v.version WHERE v.organization_id=:organization "
                    "AND v.workspace_id=:workspace AND v.document_id=:document"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                },
            ).one_or_none()
        if row is None:
            raise SpinePersistenceError("document_not_found")
        return _document_summary(row)

    def get_document_object_key(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        document_id: UUID,
        document_version: int,
    ) -> str:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            value = session.scalar(
                sa.text(
                    "SELECT object_key FROM workspace.document_versions WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND document_id=:document "
                    "AND version=:version"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                    "version": document_version,
                },
            )
        if value is None:
            raise SpinePersistenceError("document_not_found")
        return str(value)

    def claim_next_job(self, *, worker_identity: str, lease_seconds: int) -> ClaimedJob | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                sa.text("SELECT * FROM workspace.claim_next_durable_job(:worker,:lease)"),
                {"worker": worker_identity, "lease": lease_seconds},
            ).one_or_none()
        if row is None:
            return None
        return ClaimedJob(
            UUID(str(row.organization_id)),
            UUID(str(row.workspace_id)),
            UUID(str(row.job_id)),
            JobKind(str(row.job_kind)),
            dict(row.input_manifest),
            str(row.input_digest),
            int(row.attempt_number),
            int(row.lease_generation),
            str(row.cancellation_state),
        )

    def mark_job_running(self, claimed: ClaimedJob, *, worker_identity: str) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            changed = int(
                getattr(
                    session.execute(
                        sa.text(
                            "UPDATE workspace.durable_jobs SET state='running',heartbeat_at=CURRENT_TIMESTAMP "
                            "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job "
                            "AND state='leased' AND lease_owner=:worker AND lease_generation=:generation"
                        ),
                        {
                            "organization": claimed.organization_id,
                            "workspace": claimed.workspace_id,
                            "job": claimed.job_id,
                            "worker": worker_identity,
                            "generation": claimed.lease_generation,
                        },
                    ),
                    "rowcount",
                    0,
                )
            )
            if changed != 1:
                raise SpinePersistenceError("job_lease_fence_rejected")
            self._append_event(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                job_id=claimed.job_id,
                event_type="job.running",
                safe_message_code="job.running",
                current=0,
                total=1,
                terminal=False,
            )

    def heartbeat_job(
        self, claimed: ClaimedJob, *, worker_identity: str, lease_seconds: int
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            changed = int(
                getattr(
                    session.execute(
                        sa.text(
                            "UPDATE workspace.durable_jobs SET heartbeat_at=CURRENT_TIMESTAMP,"
                            "lease_expires_at=CURRENT_TIMESTAMP + make_interval(secs=>:lease) "
                            "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job "
                            "AND state='running' AND lease_owner=:worker AND lease_generation=:generation"
                        ),
                        {
                            "lease": lease_seconds,
                            "organization": claimed.organization_id,
                            "workspace": claimed.workspace_id,
                            "job": claimed.job_id,
                            "worker": worker_identity,
                            "generation": claimed.lease_generation,
                        },
                    ),
                    "rowcount",
                    0,
                )
            )
            if changed != 1:
                raise SpinePersistenceError("job_lease_fence_rejected")

    def cancellation_requested(self, claimed: ClaimedJob) -> bool:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            value = session.scalar(
                sa.text(
                    "SELECT cancellation_state FROM workspace.durable_jobs WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND job_id=:job "
                    "AND lease_generation=:generation"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                    "generation": claimed.lease_generation,
                },
            )
        if value is None:
            raise SpinePersistenceError("job_lease_fence_rejected")
        return str(value) == "requested"

    def report_progress(
        self,
        claimed: ClaimedJob,
        *,
        current: int,
        total: int,
        safe_message_code: str,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            self._append_event(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                job_id=claimed.job_id,
                event_type="job.progress",
                safe_message_code=safe_message_code,
                current=current,
                total=total,
                terminal=False,
            )

    def finish_job(
        self,
        claimed: ClaimedJob,
        *,
        terminal_state: JobState,
        outcome_code: str,
        result_manifest: dict[str, Any],
        worker_identity: str,
    ) -> UUID:
        if terminal_state not in TERMINAL_STATES:
            raise ValueError("terminal state required")
        receipt_id = uuid7()
        result_digest = semantic_digest(
            {
                "job_id": claimed.job_id,
                "lease_generation": claimed.lease_generation,
                "terminal_state": terminal_state.value,
                "outcome_code": outcome_code,
                "result": result_manifest,
            }
        )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            current = session.execute(
                sa.text(
                    "SELECT state,lease_owner,lease_generation FROM workspace.durable_jobs "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job "
                    "FOR UPDATE"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                },
            ).one()
            if str(current.state) in {state.value for state in TERMINAL_STATES}:
                existing = session.scalar(
                    sa.text(
                        "SELECT terminal_receipt_id FROM workspace.job_terminal_receipts WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                    ),
                    {
                        "organization": claimed.organization_id,
                        "workspace": claimed.workspace_id,
                        "job": claimed.job_id,
                    },
                )
                return UUID(str(existing))
            if (
                current.lease_owner != worker_identity
                or int(current.lease_generation) != claimed.lease_generation
            ):
                raise SpinePersistenceError("job_lease_fence_rejected")
            session.execute(
                sa.text(
                    "INSERT INTO workspace.job_terminal_receipts "
                    "(organization_id,workspace_id,terminal_receipt_id,job_id,lease_generation,"
                    "terminal_state,typed_outcome_code,result_manifest,result_digest) VALUES "
                    "(:organization,:workspace,:receipt,:job,:generation,:state,:outcome,"
                    "CAST(:result AS jsonb),:digest)"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "receipt": receipt_id,
                    "job": claimed.job_id,
                    "generation": claimed.lease_generation,
                    "state": terminal_state.value,
                    "outcome": outcome_code,
                    "result": _json(result_manifest),
                    "digest": result_digest,
                },
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET state=:state,completed_at=CURRENT_TIMESTAMP,"
                    "typed_failure_code=:failure,result_receipt_id=:receipt,lease_owner=NULL,"
                    "lease_expires_at=NULL,cancellation_state=CASE WHEN :state='cancelled' "
                    "THEN 'acknowledged' ELSE cancellation_state END "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                ),
                {
                    "state": terminal_state.value,
                    "failure": None if terminal_state is JobState.SUCCEEDED else outcome_code,
                    "receipt": receipt_id,
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                },
            )
            self._append_event(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                job_id=claimed.job_id,
                event_type=f"job.{terminal_state.value}",
                safe_message_code=outcome_code,
                current=1,
                total=1,
                terminal=True,
            )
        return receipt_id

    def retry_job(
        self, claimed: ClaimedJob, *, worker_identity: str, failure_code: str, delay_seconds: int
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT attempt_count,max_attempts,lease_owner,lease_generation FROM "
                    "workspace.durable_jobs WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND job_id=:job FOR UPDATE"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                },
            ).one()
            if (
                row.lease_owner != worker_identity
                or int(row.lease_generation) != claimed.lease_generation
            ):
                raise SpinePersistenceError("job_lease_fence_rejected")
            if int(row.attempt_count) >= int(row.max_attempts):
                return False
            session.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET state='queued',eligible_at=CURRENT_TIMESTAMP+"
                    "make_interval(secs=>:delay),typed_failure_code=:failure,lease_owner=NULL,"
                    "lease_expires_at=NULL WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND job_id=:job"
                ),
                {
                    "delay": delay_seconds,
                    "failure": failure_code,
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                },
            )
            self._append_event(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                job_id=claimed.job_id,
                event_type="job.retry_scheduled",
                safe_message_code=failure_code,
                current=None,
                total=None,
                terminal=False,
            )
        return True

    def request_cancellation(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        job_id: UUID,
        reason_code: str,
    ) -> None:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        cancellation_id = uuid7()
        digest = semantic_digest(
            {"cancellation_id": cancellation_id, "job_id": job_id, "reason_code": reason_code}
        )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT state,lease_generation FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job FOR UPDATE"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            ).one_or_none()
            if row is None:
                raise SpinePersistenceError("job_not_found")
            if JobState(str(row.state)) in TERMINAL_STATES:
                return
            session.execute(
                sa.text(
                    "INSERT INTO workspace.job_cancellations "
                    "(organization_id,workspace_id,cancellation_id,job_id,requested_by_identity_id,"
                    "reason_code,cancellation_digest) VALUES "
                    "(:organization,:workspace,:id,:job,:owner,:reason,:digest)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "id": cancellation_id,
                    "job": job_id,
                    "owner": owner_identity_id,
                    "reason": reason_code,
                    "digest": digest,
                },
            )
            if JobState(str(row.state)) is JobState.QUEUED:
                result = {"semantic_effect": False, "reason": reason_code}
                result_digest = semantic_digest(
                    {"job_id": job_id, "state": "cancelled", "result": result}
                )
                receipt_id = uuid7()
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.job_terminal_receipts "
                        "(organization_id,workspace_id,terminal_receipt_id,job_id,lease_generation,"
                        "terminal_state,typed_outcome_code,result_manifest,result_digest) VALUES "
                        "(:organization,:workspace,:receipt,:job,:generation,'cancelled',"
                        "'job_cancelled_before_effect',CAST(:result AS jsonb),:digest)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "receipt": receipt_id,
                        "job": job_id,
                        "generation": int(row.lease_generation),
                        "result": _json(result),
                        "digest": result_digest,
                    },
                )
                session.execute(
                    sa.text(
                        "UPDATE workspace.durable_jobs SET state='cancelled',"
                        "cancellation_state='acknowledged',completed_at=CURRENT_TIMESTAMP,"
                        "typed_failure_code='job_cancelled_before_effect',result_receipt_id=:receipt "
                        "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "job": job_id,
                        "receipt": receipt_id,
                    },
                )
                self._append_event(
                    session,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    event_type="job.cancelled",
                    safe_message_code="job_cancelled_before_effect",
                    current=1,
                    total=1,
                    terminal=True,
                )
            else:
                session.execute(
                    sa.text(
                        "UPDATE workspace.durable_jobs SET cancellation_state='requested' WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                    ),
                    {"organization": organization_id, "workspace": workspace_id, "job": job_id},
                )

    def cancel_jobs_for_reset(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> tuple[UUID, ...]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        cancelled: list[UUID] = []
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT job_id,lease_generation FROM workspace.durable_jobs "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND state NOT IN ('succeeded','failed','cancelled','reconciliation_required') "
                    "ORDER BY created_at,job_id FOR UPDATE"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            ).all()
            for row in rows:
                job_id = UUID(str(row.job_id))
                cancellation_id = uuid7()
                cancellation_digest = semantic_digest(
                    {
                        "cancellation_id": cancellation_id,
                        "job_id": job_id,
                        "reason_code": "workspace_reset_fence",
                    }
                )
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.job_cancellations "
                        "(organization_id,workspace_id,cancellation_id,job_id,"
                        "requested_by_identity_id,reason_code,cancellation_digest) VALUES "
                        "(:organization,:workspace,:cancellation,:job,:owner,"
                        "'workspace_reset_fence',:digest)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "cancellation": cancellation_id,
                        "job": job_id,
                        "owner": owner_identity_id,
                        "digest": cancellation_digest,
                    },
                )
                result = {"semantic_effect": False, "reason": "workspace_reset_fence"}
                result_digest = semantic_digest(
                    {"job_id": job_id, "state": "cancelled", "result": result}
                )
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.job_terminal_receipts "
                        "(organization_id,workspace_id,terminal_receipt_id,job_id,lease_generation,"
                        "terminal_state,typed_outcome_code,result_manifest,result_digest) VALUES "
                        "(:organization,:workspace,:receipt,:job,:generation,'cancelled',"
                        "'workspace_reset_fence',CAST(:result AS jsonb),:digest)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "receipt": uuid7(),
                        "job": job_id,
                        "generation": int(row.lease_generation),
                        "result": _json(result),
                        "digest": result_digest,
                    },
                )
                session.execute(
                    sa.text(
                        "UPDATE workspace.durable_jobs SET state='cancelled',"
                        "cancellation_state='acknowledged',typed_failure_code='workspace_reset_fence',"
                        "completed_at=CURRENT_TIMESTAMP,lease_owner=NULL,lease_expires_at=NULL "
                        "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                    ),
                    {"organization": organization_id, "workspace": workspace_id, "job": job_id},
                )
                self._append_event(
                    session,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    event_type="job.cancelled",
                    safe_message_code="workspace_reset_fence",
                    current=None,
                    total=None,
                    terminal=True,
                )
                cancelled.append(job_id)
        return tuple(cancelled)

    def create_reset_challenge(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        target_lifecycle_version: int,
        archive_package_digest: str,
        confirmation_text: str,
        expires_at: datetime,
    ) -> ResetChallenge:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        challenge_id = uuid7()
        challenge_digest = semantic_digest({"confirmation_text": confirmation_text})
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.reset_confirmation_challenges "
                    "(organization_id,workspace_id,challenge_id,target_lifecycle_version,"
                    "archive_package_digest,challenge_digest,issued_to_identity_id,expires_at) VALUES "
                    "(:organization,:workspace,:challenge,:version,:archive,:digest,:owner,:expires)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "challenge": challenge_id,
                    "version": target_lifecycle_version,
                    "archive": archive_package_digest,
                    "digest": challenge_digest,
                    "owner": owner_identity_id,
                    "expires": expires_at,
                },
            )
        return ResetChallenge(
            challenge_id,
            workspace_id,
            target_lifecycle_version,
            confirmation_text,
            expires_at,
            "development_single_owner_confirmation",
        )

    def consume_reset_challenge(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        challenge_id: UUID,
        confirmation_text: str,
    ) -> tuple[UUID, int, str, UUID]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT target_lifecycle_version,archive_package_digest,challenge_digest,"
                    "deletion_plan_id,deletion_plan_version FROM "
                    "workspace.reset_confirmation_challenges WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND challenge_id=:challenge "
                    "AND issued_to_identity_id=:owner AND consumed_at IS NULL "
                    "AND expires_at>CURRENT_TIMESTAMP FOR UPDATE"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "challenge": challenge_id,
                    "owner": owner_identity_id,
                },
            ).one_or_none()
            if (
                row is None
                or row.deletion_plan_id is None
                or str(row.challenge_digest)
                != semantic_digest({"confirmation_text": confirmation_text})
            ):
                raise SpinePersistenceError("reset_confirmation_invalid")
            session.execute(
                sa.text(
                    "UPDATE workspace.reset_confirmation_challenges SET consumed_at=CURRENT_TIMESTAMP "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND challenge_id=:challenge"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "challenge": challenge_id,
                },
            )
        return (
            organization_id,
            int(row.target_lifecycle_version),
            str(row.archive_package_digest),
            UUID(str(row.deletion_plan_id)),
        )

    def bind_reset_challenge_plan(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        challenge_id: UUID,
        deletion_plan_id: UUID,
    ) -> None:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            result = session.execute(
                sa.text(
                    "UPDATE workspace.reset_confirmation_challenges SET deletion_plan_id=:plan,"
                    "deletion_plan_version=1 "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND challenge_id=:challenge AND deletion_plan_id IS NULL AND consumed_at IS NULL"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "challenge": challenge_id,
                    "plan": deletion_plan_id,
                },
            )
            changed = int(getattr(result, "rowcount", 0))
        if changed != 1:
            raise SpinePersistenceError("reset_challenge_plan_binding_failed")

    def list_jobs(
        self, *, owner_identity_id: str, workspace_id: UUID, limit: int = 200
    ) -> tuple[JobSummary, ...]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace ORDER BY created_at,job_id LIMIT :limit"
                ),
                {"organization": organization_id, "workspace": workspace_id, "limit": limit},
            ).all()
        return tuple(_job_summary(row) for row in rows)

    def list_progress_events(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        after_sequence: int,
        limit: int = 500,
    ) -> tuple[JobProgress, ...]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT * FROM workspace.job_progress_events WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND progress_event_id>:after "
                    "AND retention_until>CURRENT_TIMESTAMP ORDER BY progress_event_id LIMIT :limit"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "after": after_sequence,
                    "limit": limit,
                },
            ).all()
        return tuple(
            JobProgress(
                UUID(str(row.job_id)),
                int(row.progress_event_id),
                str(row.event_type),
                int(row.progress_current) if row.progress_current is not None else None,
                int(row.progress_total) if row.progress_total is not None else None,
                str(row.safe_message_code),
                bool(row.terminal),
                row.recorded_at,
            )
            for row in rows
        )

    def reconcile_unclaimable_jobs(self) -> int:
        with self._engine.begin() as connection:
            return int(
                connection.scalar(sa.text("SELECT workspace.reconcile_unclaimable_durable_jobs()"))
                or 0
            )

    def latest_document_state(
        self, claimed: ClaimedJob
    ) -> tuple[str, str, int | None, tuple[str, ...]]:
        document_id = UUID(str(claimed.input_manifest["document_id"]))
        document_version = int(claimed.input_manifest["document_version"])
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT admission_status,extraction_status,page_count,capability_gaps "
                    "FROM workspace.document_processing_states WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND document_id=:document AND document_version=:version "
                    "ORDER BY state_sequence DESC LIMIT 1"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "document": document_id,
                    "version": document_version,
                },
            ).one()
        return (
            str(row.admission_status),
            str(row.extraction_status),
            int(row.page_count) if row.page_count is not None else None,
            tuple(row.capability_gaps or ()),
        )

    def append_document_state(
        self,
        claimed: ClaimedJob,
        *,
        admission_status: str,
        extraction_status: str,
        page_count: int | None,
        capability_gaps: tuple[str, ...],
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            self._append_document_state(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                document_id=UUID(str(claimed.input_manifest["document_id"])),
                document_version=int(claimed.input_manifest["document_version"]),
                admission_status=admission_status,
                extraction_status=extraction_status,
                page_count=page_count,
                capability_gaps=capability_gaps,
                caused_by_job_id=claimed.job_id,
            )

    def _append_document_state(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        document_id: UUID,
        document_version: int,
        admission_status: str,
        extraction_status: str,
        page_count: int | None,
        capability_gaps: tuple[str, ...],
        caused_by_job_id: UUID | None,
    ) -> None:
        sequence = int(
            session.scalar(
                sa.text(
                    "SELECT COALESCE(max(state_sequence),0)+1 FROM workspace.document_processing_states "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND document_id=:document AND document_version=:version"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                    "version": document_version,
                },
            )
        )
        fingerprint = semantic_digest(
            {
                "document_id": document_id,
                "document_version": document_version,
                "sequence": sequence,
                "admission_status": admission_status,
                "extraction_status": extraction_status,
                "page_count": page_count,
                "capability_gaps": sorted(capability_gaps),
                "job_id": caused_by_job_id,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.document_processing_states "
                "(organization_id,workspace_id,document_id,document_version,state_sequence,"
                "admission_status,extraction_status,page_count,capability_gaps,caused_by_job_id,"
                "state_fingerprint) VALUES (:organization,:workspace,:document,:version,:sequence,"
                ":admission,:extraction,:page_count,:gaps,:job,:fingerprint)"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "document": document_id,
                "version": document_version,
                "sequence": sequence,
                "admission": admission_status,
                "extraction": extraction_status,
                "page_count": page_count,
                "gaps": list(capability_gaps),
                "job": caused_by_job_id,
                "fingerprint": fingerprint,
            },
        )

    def record_document_page(
        self,
        claimed: ClaimedJob,
        *,
        page_number: int,
        width_points: float,
        height_points: float,
        rotation_degrees: int,
        crop_box: dict[str, float],
        native_text_digest: str | None,
        native_text_object_key: str | None,
        extraction_method: str,
    ) -> UUID:
        document_id = UUID(str(claimed.input_manifest["document_id"]))
        document_version = int(claimed.input_manifest["document_version"])
        source_version_id = UUID(str(claimed.input_manifest["source_version_id"]))
        locator_id = uuid7()
        locator_value = {
            "page": page_number,
            "region": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
            "coordinate_space": "normalized-top-left",
            "width_points": width_points,
            "height_points": height_points,
            "rotation_degrees": rotation_degrees,
        }
        page_fingerprint = semantic_digest(
            {
                "source_version_id": source_version_id,
                "page": page_number,
                "geometry": locator_value,
                "native_text_digest": native_text_digest,
                "method": extraction_method,
            }
        )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            existing = session.scalar(
                sa.text(
                    "SELECT evidence_locator_id FROM workspace.document_pages WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND document_id=:document "
                    "AND document_version=:version AND page_number=:page"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "document": document_id,
                    "version": document_version,
                    "page": page_number,
                },
            )
            if existing is not None:
                return UUID(str(existing))
            session.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators "
                    "(organization_id,workspace_id,source_locator_id,source_version_id,locator_kind,"
                    "locator_key,locator_value,fragment_digest) VALUES "
                    "(:organization,:workspace,:locator,:source,'pdf_page_region',:key,"
                    "CAST(:value AS jsonb),:fragment)"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "locator": locator_id,
                    "source": source_version_id,
                    "key": f"page:{page_number}:full",
                    "value": _json(locator_value),
                    "fragment": native_text_digest,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.document_pages "
                    "(organization_id,workspace_id,document_id,document_version,page_number,width_points,"
                    "height_points,rotation_degrees,crop_box,native_text_digest,native_text_object_key,"
                    "extraction_method,evidence_locator_id,page_fingerprint) VALUES "
                    "(:organization,:workspace,:document,:version,:page,:width,:height,:rotation,"
                    "CAST(:crop AS jsonb),:text_digest,:text_key,:method,:locator,:fingerprint)"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "document": document_id,
                    "version": document_version,
                    "page": page_number,
                    "width": width_points,
                    "height": height_points,
                    "rotation": rotation_degrees,
                    "crop": _json(crop_box),
                    "text_digest": native_text_digest,
                    "text_key": native_text_object_key,
                    "method": extraction_method,
                    "locator": locator_id,
                    "fingerprint": page_fingerprint,
                },
            )
        return locator_id

    def get_document_page_evidence(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        document_id: UUID,
        page_number: int,
    ) -> EvidencePanel:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT p.document_id,p.document_version,p.evidence_locator_id,p.page_number,"
                    "p.width_points,p.height_points,p.rotation_degrees,p.native_text_digest,"
                    "p.extraction_method,v.source_version_id FROM workspace.document_pages p "
                    "JOIN workspace.document_versions v ON v.organization_id=p.organization_id "
                    "AND v.workspace_id=p.workspace_id AND v.document_id=p.document_id "
                    "AND v.version=p.document_version JOIN "
                    "workspace.document_version_activation_decisions a ON "
                    "a.organization_id=p.organization_id AND a.workspace_id=p.workspace_id "
                    "AND a.document_id=p.document_id AND a.selected_document_version=p.document_version "
                    "WHERE p.organization_id=:organization AND p.workspace_id=:workspace "
                    "AND p.document_id=:document AND p.page_number=:page AND NOT EXISTS "
                    "(SELECT 1 FROM workspace.document_version_activation_decisions newer "
                    "WHERE newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                    "AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "document": document_id,
                    "page": page_number,
                },
            ).one_or_none()
        if row is None:
            raise SpinePersistenceError("evidence_locator_not_found")
        evidence_digest = str(
            row.native_text_digest
            or semantic_digest(
                {
                    "source_version_id": row.source_version_id,
                    "page": row.page_number,
                    "evidence": "page_geometry_only",
                }
            )
        )
        locator = PageLocator(
            UUID(str(row.document_id)),
            int(row.document_version),
            UUID(str(row.source_version_id)),
            UUID(str(row.evidence_locator_id)),
            int(row.page_number),
            (0.0, 0.0, 1.0, 1.0),
            float(row.width_points),
            float(row.height_points),
            int(row.rotation_degrees),
            evidence_digest,
            str(row.extraction_method),
        )
        return EvidencePanel(
            locator,
            "source_evidence_only",
            "workspace_fact_candidate",
            None,
            None,
            None,
            ("NO_VERIFIED_FACT_BOUND_TO_LOCATOR",),
            (),
            False,
        )

    def latest_matrix_and_mode_execution(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            matrix = (
                session.execute(
                    sa.text(
                        "SELECT matrix_id,version,matrix,fingerprint FROM "
                        "workspace.work_requirement_matrix_versions WHERE "
                        "organization_id=:organization AND workspace_id=:workspace "
                        "ORDER BY created_at DESC,matrix_id,version DESC LIMIT 1"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            execution = (
                session.execute(
                    sa.text(
                        "SELECT mode_execution_id,state,purpose,contract_key,contract_version "
                        "FROM workspace.mode_executions WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND mode=:mode ORDER BY revision DESC LIMIT 1"
                    ),
                    {"organization": organization_id, "workspace": workspace_id, "mode": mode},
                )
                .mappings()
                .one_or_none()
            )
        return (
            dict(matrix) if matrix is not None else None,
            dict(execution) if execution is not None else None,
        )

    def platform_knowledge_status(self) -> KnowledgeStatus:
        with self._engine.connect() as connection:
            value = connection.scalar(sa.text("SELECT application.get_platform_knowledge_status()"))
            qualification = (
                connection.execute(
                    sa.text(
                        "SELECT status,all_history_fingerprint,active_release_fingerprint,"
                        "context_binding_fingerprint,blocker_codes FROM "
                        "platform.platform_memory_qualification_decisions "
                        "ORDER BY recorded_at DESC,version DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            active_release = (
                connection.execute(
                    sa.text(
                        "WITH selected AS (SELECT *,row_number() OVER (PARTITION BY "
                        "practice_guide_id ORDER BY version DESC) rank FROM "
                        "platform.practice_intelligence_release_activation_decisions) "
                        "SELECT (SELECT count(*) FROM "
                        "platform.practice_intelligence_release_memberships m WHERE "
                        "m.release_id=selected.selected_release_id AND "
                        "m.release_version=selected.selected_release_version) intelligence_count,"
                        "(SELECT count(*) FROM platform.practice_playbook_release_memberships m "
                        "WHERE m.release_id=selected.selected_release_id AND "
                        "m.release_version=selected.selected_release_version) playbook_count "
                        "FROM selected WHERE rank=1"
                    )
                )
                .mappings()
                .one_or_none()
            )
        if not isinstance(value, dict):
            raise SpinePersistenceError("platform_knowledge_status_unavailable")
        value = dict(value)
        qualification_passed = qualification is not None and qualification["status"] == "pass"
        blockers = {str(item) for item in value.get("blockers", [])}
        if qualification_passed:
            blockers.discard("MEMORY_DATA_DEFECT")
        else:
            blockers.add("MEMORY_DATA_DEFECT")
        if qualification is not None:
            value["semantic_fingerprints"] = {
                **dict(value.get("semantic_fingerprints", {})),
                "all_history": str(qualification["all_history_fingerprint"]),
                "active_release": str(qualification["active_release_fingerprint"]),
                "context_binding": str(qualification["context_binding_fingerprint"]),
            }
            blockers.update(str(item) for item in qualification["blocker_codes"])
        if active_release is not None:
            value["active_intelligence_count"] = int(active_release["intelligence_count"])
            value["active_playbook_count"] = int(active_release["playbook_count"])
        value["memory_data_defect"] = not qualification_passed
        value["blockers"] = sorted(blockers)
        backup_at_raw = value.get("last_verified_backup_at")
        backup_at = (
            datetime.fromisoformat(str(backup_at_raw).replace("Z", "+00:00"))
            if backup_at_raw
            else None
        )
        return KnowledgeStatus(
            int(value["practice_guide_count"]),
            int(value["practice_edition_count"]),
            int(value["active_practice_release_count"]),
            int(value["source_guidance_count"]),
            int(value["active_intelligence_count"]),
            int(value["active_playbook_count"]),
            int(value["active_gap_count"]),
            int(value["conflict_count"]),
            int(value["quarantine_count"]),
            int(value["normative_identity_count"]),
            int(value["verified_normative_edition_count"]),
            int(value["verified_normative_provision_count"]),
            int(value["rule_version_count"]),
            dict(value["projection_states"]),
            backup_at,
            dict(value["semantic_fingerprints"]),
            bool(value["memory_data_defect"]),
            bool(value["knowledge_ready"]),
            tuple(str(item) for item in value["blockers"]),
        )

    def _append_event(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        job_id: UUID,
        event_type: str,
        safe_message_code: str,
        current: int | None,
        total: int | None,
        terminal: bool,
    ) -> None:
        session.execute(
            sa.text(
                "SELECT job_id FROM workspace.durable_jobs WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND job_id=:job FOR UPDATE"
            ),
            {"organization": organization_id, "workspace": workspace_id, "job": job_id},
        ).one()
        sequence = int(
            session.scalar(
                sa.text(
                    "SELECT COALESCE(max(event_sequence),0)+1 FROM workspace.job_progress_events "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            )
        )
        recorded_at = datetime.now(UTC)
        event_digest = semantic_digest(
            {
                "job_id": job_id,
                "sequence": sequence,
                "event_type": event_type,
                "current": current,
                "total": total,
                "message": safe_message_code,
                "terminal": terminal,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.job_progress_events "
                "(organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,"
                "progress_total,safe_message_code,terminal,recorded_at,retention_until,event_digest) "
                "VALUES (:organization,:workspace,:job,:sequence,:event,:current,:total,:message,"
                ":terminal,:recorded,:retention,:digest)"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "job": job_id,
                "sequence": sequence,
                "event": event_type,
                "current": current,
                "total": total,
                "message": safe_message_code,
                "terminal": terminal,
                "recorded": recorded_at,
                "retention": recorded_at + timedelta(seconds=self._event_retention_seconds),
                "digest": event_digest,
            },
        )


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _workspace_summary(row: Any) -> WorkspaceSummary:
    return WorkspaceSummary(
        UUID(str(row.organization_id)),
        UUID(str(row.workspace_id)),
        UUID(str(row.construction_object_id)),
        str(row.display_name),
        str(row.lifecycle_state),
        int(row.lifecycle_version),
        int(row.workspace_revision),
        bool(row.write_fenced),
        row.created_at,
    )


def _document_summary(row: Any) -> DocumentSummary:
    return DocumentSummary(
        UUID(str(row.organization_id)),
        UUID(str(row.workspace_id)),
        UUID(str(row.document_id)),
        int(row.version),
        tuple(int(value) for value in getattr(row, "prior_versions", ()) or ()),
        tuple(UUID(str(value)) for value in getattr(row, "job_ids", ()) or ()),
        UUID(str(row.source_artifact_id)) if row.source_artifact_id else None,
        UUID(str(row.source_version_id)) if row.source_version_id else None,
        str(row.safe_display_name),
        str(row.sanitized_relative_path),
        str(row.media_type),
        int(row.size_bytes),
        str(row.content_digest),
        int(row.page_count) if row.page_count is not None else None,
        str(row.admission_status),
        str(row.extraction_status),
        tuple(row.capability_gaps or ()),
        row.recorded_at,
    )


def _job_summary(row: Any) -> JobSummary:
    return JobSummary(
        UUID(str(row.organization_id)),
        UUID(str(row.workspace_id)),
        UUID(str(row.job_id)),
        JobKind(str(row.job_kind)),
        JobState(str(row.state)),
        int(row.priority),
        int(row.attempt_count),
        int(row.max_attempts),
        str(row.cancellation_state),
        str(row.typed_failure_code) if row.typed_failure_code else None,
        UUID(str(row.result_receipt_id)) if row.result_receipt_id else None,
        row.created_at,
        row.started_at,
        row.heartbeat_at,
        row.completed_at,
    )


def _json(value: object) -> str:
    import json

    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
