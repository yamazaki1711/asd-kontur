"""PostgreSQL adapter for Product Application Spine commands and queries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.document_understanding.models import PROJECT_RECONCILIATION_PROFILE_VERSION
from asd_kontur.domain import uuid7
from asd_kontur.tender.excavation_pit_inventory import build_excavation_pit_inventory
from asd_kontur.tender.facility_work_projection import (
    build_facility_work_candidate_projection,
)
from asd_kontur.tender.structure_identity_components import (
    build_structure_identity_components,
)
from asd_kontur.tender.structure_identity_dossier import (
    build_structure_identity_dossiers,
)

from .models import (
    ENGINEERING_SEMANTIC_RECOVERY_CONTRACT,
    STRUCTURE_IDENTITY_GROUPING_POLICY_VERSION,
    STRUCTURE_IDENTITY_RESULT_MANIFEST_VERSION,
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
ENGINEERING_SEMANTIC_PROFILE_VERSION = "qwen-engineering-extraction-v15"
ENGINEERING_CANDIDATE_PERSISTENCE_PROFILE = ENGINEERING_SEMANTIC_PROFILE_VERSION
TERMINAL_STATES = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.RECONCILIATION_REQUIRED,
    }
)

# Dispatch priorities are intentionally coarse and derived only from durable
# document-role decisions.  They influence which independent source uses the
# single local-Qwen slot next; they do not change candidate authority, evidence
# selection, or fairness within a tier.
_SEMANTIC_PRIORITY_BY_ROLE = {
    "drawing_or_scheme": 170,
    "working_documentation": 170,
    "project_documentation": 170,
    "explanatory_note": 160,
    "specification": 160,
    "bill_of_quantities": 150,
    "local_estimate": 150,
    "object_estimate": 150,
    "consolidated_estimate": 150,
}
_SEMANTIC_DEFAULT_PRIORITY = 130


def _semantic_extraction_priority(document_roles: tuple[str, ...]) -> int:
    """Return the durable dispatch priority for a classified active document."""

    return max(
        (
            _SEMANTIC_PRIORITY_BY_ROLE.get(role, _SEMANTIC_DEFAULT_PRIORITY)
            for role in document_roles
        ),
        default=_SEMANTIC_DEFAULT_PRIORITY,
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

    @property
    def engine(self) -> Engine:
        """Expose the shared persistence boundary to sibling application repositories."""

        return self._engine

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

    def latest_audit_report_projection(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Return the two exact owner-readable projections of the latest report.

        This method deliberately reads only the immutable projection boundary;
        it does not expose canonical Audit tables or give the Product
        Application role a way to mutate audit process state.
        """

        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = (
                session.execute(
                    sa.text(
                        "SELECT audit_report_id,audit_report_version,projection_kind,"
                        "projection_payload,projection_fingerprint,built_at FROM "
                        "workspace.audit_projection_versions WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND state='current' ORDER BY "
                        "built_at DESC,projection_id DESC,version DESC"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                )
                .mappings()
                .all()
            )
        if not rows:
            return {
                "status": "not_published",
                "customer": None,
                "pto": None,
                "gaps": ["CANONICAL_AUDIT_REPORT_NOT_PUBLISHED"],
            }
        latest_report = rows[0]["audit_report_id"]
        latest_version = int(rows[0]["audit_report_version"])
        projections = {
            str(row["projection_kind"]): _jsonable_row(row)
            for row in rows
            if row["audit_report_id"] == latest_report
            and int(row["audit_report_version"]) == latest_version
        }
        return {
            "status": "published" if {"customer", "pto"} <= set(projections) else "partial",
            "customer": projections.get("customer"),
            "pto": projections.get("pto"),
            "gaps": []
            if {"customer", "pto"} <= set(projections)
            else ["CANONICAL_AUDIT_PROJECTION_INCOMPLETE"],
        }

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
        archive_members: tuple[tuple[int, int, int], ...] = (),
    ) -> BatchRegistration:
        if not staged_items and not rejected_items:
            raise SpinePersistenceError("empty_batch")
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        manifest_id = uuid7()
        committed_created: list[str] = []
        accepted_ids: list[UUID] = []
        duplicate_ids: list[UUID] = []
        job_ids: list[UUID] = []
        registrations: dict[int, RegisteredDocument] = {}
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
                    registrations[ordinal] = registered
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
                for archive_ordinal, member_ordinal, child_ordinal in archive_members:
                    archive = registrations[archive_ordinal]
                    child = registrations[child_ordinal]
                    child_staged = next(
                        staged for ordinal, staged in staged_items if ordinal == child_ordinal
                    )
                    lineage_digest = semantic_digest(
                        {
                            "archive_document_id": archive.document_id,
                            "archive_document_version": archive.document_version,
                            "member_ordinal": member_ordinal,
                            "member_document_id": child.document_id,
                            "member_document_version": child.document_version,
                            "member_relative_path": child_staged.relative_path,
                            "member_content_digest": child_staged.digest,
                        }
                    )
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.intake_archive_members "
                            "(organization_id,workspace_id,archive_document_id,archive_document_version,"
                            "member_ordinal,member_document_id,member_document_version,member_relative_path,"
                            "member_content_digest,uncompressed_size_bytes,lineage_digest) VALUES "
                            "(:organization,:workspace,:archive,:archive_version,:ordinal,:member,"
                            ":member_version,:path,:digest,:size,:lineage) ON CONFLICT DO NOTHING"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "archive": archive.document_id,
                            "archive_version": archive.document_version,
                            "ordinal": member_ordinal,
                            "member": child.document_id,
                            "member_version": child.document_version,
                            "path": child_staged.relative_path,
                            "digest": child_staged.digest,
                            "size": child_staged.size_bytes,
                            "lineage": lineage_digest,
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
        kinds = tuple(
            kind
            for kind in JobKind
            if kind
            not in {
                JobKind.WORKSPACE_RESET_RECONCILIATION,
                JobKind.ID_DOCUMENT_GENERATION,
            }
        )
        if media_type == "application/zip":
            kinds = (
                JobKind.DOCUMENT_ADMISSION,
                JobKind.DOCUMENT_HASH,
                JobKind.DOCUMENT_FORMAT_INVENTORY,
            )
        for priority, kind in enumerate(kinds, start=1):
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

    def claim_next_job(
        self,
        *,
        worker_identity: str,
        lease_seconds: int,
        organization_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> ClaimedJob | None:
        if (organization_id is None) != (workspace_id is None):
            raise ValueError("document_worker_scope_incomplete")
        with Session(self._engine) as session, session.begin():
            if organization_id is not None and workspace_id is not None:
                _set_scope(session, organization_id, workspace_id)
            row = session.execute(
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

    def reconcile_expired_exhausted_jobs(
        self, *, organization_id: UUID, workspace_id: UUID, limit: int = 8
    ) -> int:
        """Fence crashed jobs whose lease and retry budget are both exhausted."""

        if not 1 <= limit <= 64:
            raise ValueError("expired job reconciliation limit is invalid")
        reconciled = 0
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT job_id,lease_generation FROM workspace.durable_jobs WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND "
                    "state IN ('leased','running') AND lease_expires_at<CURRENT_TIMESTAMP AND "
                    "attempt_count>=max_attempts ORDER BY lease_expires_at,job_id "
                    "FOR UPDATE SKIP LOCKED LIMIT :limit"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "limit": limit,
                },
            ).all()
            for row in rows:
                job_id = UUID(str(row.job_id))
                generation = int(row.lease_generation)
                receipt_id = uuid7()
                result = {
                    "semantic_effect": "unknown",
                    "reason": "lease_expired_after_attempt_exhaustion",
                }
                result_digest = semantic_digest(
                    {
                        "job_id": job_id,
                        "lease_generation": generation,
                        "terminal_state": JobState.RECONCILIATION_REQUIRED.value,
                        "outcome_code": "worker_lease_expired_after_attempt_exhaustion",
                        "result": result,
                    }
                )
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.job_terminal_receipts "
                        "(organization_id,workspace_id,terminal_receipt_id,job_id,lease_generation,"
                        "terminal_state,typed_outcome_code,result_manifest,result_digest) VALUES "
                        "(:organization,:workspace,:receipt,:job,:generation,"
                        "'reconciliation_required','worker_lease_expired_after_attempt_exhaustion',"
                        "CAST(:result AS jsonb),:digest)"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "receipt": receipt_id,
                        "job": job_id,
                        "generation": generation,
                        "result": _json(result),
                        "digest": result_digest,
                    },
                )
                session.execute(
                    sa.text(
                        "UPDATE workspace.durable_jobs SET state='reconciliation_required',"
                        "completed_at=CURRENT_TIMESTAMP,typed_failure_code="
                        "'worker_lease_expired_after_attempt_exhaustion',result_receipt_id=:receipt,"
                        "lease_owner=NULL,lease_expires_at=NULL WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND job_id=:job"
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
                    event_type="job.reconciliation_required",
                    safe_message_code="worker_lease_expired_after_attempt_exhaustion",
                    current=1,
                    total=1,
                    terminal=True,
                )
                reconciled += 1
        return reconciled

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

    def schedule_incremental_project_reconciliation(self, claimed: ClaimedJob) -> UUID | None:
        """Queue one idempotent partial-model refresh after a source semantic pass.

        The reconciliation reads only profile-selected completed stage results, so a
        refresh may safely materialize candidate-only partial results while other
        source passes remain queued.  Its priority deliberately sits below
        structural/document source extraction (170) and above lower evidence tiers,
        preventing either a stale UI or permanent starvation of the corpus.
        """

        if claimed.job_kind is not JobKind.PROJECT_DEFINITION_EXTRACTION:
            return None
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            source = (
                session.execute(
                    sa.text(
                        "SELECT subject_document_id,input_manifest,input_digest,provenance,correlation_id,"
                        "created_by_identity_id FROM workspace.durable_jobs WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND job_id=:job "
                        "AND state='succeeded' FOR UPDATE"
                    ),
                    {
                        "organization": claimed.organization_id,
                        "workspace": claimed.workspace_id,
                        "job": claimed.job_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if source is None:
                return None
            provenance = dict(source["provenance"])
            semantic_profile = provenance.get("engineering_semantic_profile")
            if not isinstance(semantic_profile, str) or not semantic_profile:
                return None
            stage_complete = session.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM workspace.project_understanding_stage_results "
                    "WHERE organization_id=:organization AND workspace_id=:workspace "
                    "AND job_id=:job AND stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                    "AND terminal_status='complete')"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": claimed.job_id,
                },
            )
            if not stage_complete:
                return None
            source_manifest = dict(source["input_manifest"])
            manifest = {
                "document_id": str(source_manifest["document_id"]),
                "document_version": int(source_manifest["document_version"]),
                "source_version_id": str(source_manifest["source_version_id"]),
                "object_key": str(source_manifest["object_key"]),
                "media_type": str(source_manifest["media_type"]),
                "content_digest": str(source_manifest["content_digest"]),
                "incremental_source_job_id": str(claimed.job_id),
                "incremental_source_input_digest": str(source["input_digest"]),
                "engineering_semantic_profile": semantic_profile,
                "project_reconciliation_profile": PROJECT_RECONCILIATION_PROFILE_VERSION,
            }
            input_digest = semantic_digest(manifest)
            idempotency_key = (
                "project-understanding-incremental:"
                f"{PROJECT_RECONCILIATION_PROFILE_VERSION}:{claimed.job_id}:{input_digest}"
            )
            existing = session.scalar(
                sa.text(
                    "SELECT job_id FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_kind='PROJECT_UNDERSTANDING_RECONCILIATION' "
                    "AND idempotency_key=:key"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "key": idempotency_key,
                },
            )
            if existing is not None:
                return UUID(str(existing))
            reconciliation_job_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                    "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                    "provenance,correlation_id,causation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,:document,'PROJECT_UNDERSTANDING_RECONCILIATION',"
                    "CAST(:manifest AS jsonb),:digest,:key,'queued',165,3,'spine-retry-v0.1',"
                    "CAST(:provenance AS jsonb),:correlation,:causation,:owner)"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "job": reconciliation_job_id,
                    "document": source["subject_document_id"],
                    "manifest": _json(manifest),
                    "digest": input_digest,
                    "key": idempotency_key,
                    "provenance": _json(
                        {
                            "contract": "project-understanding.incremental-reconciliation@1.0.0",
                            "source_semantic_job_id": str(claimed.job_id),
                            "engineering_semantic_profile": semantic_profile,
                            "project_reconciliation_profile": (
                                PROJECT_RECONCILIATION_PROFILE_VERSION
                            ),
                        }
                    ),
                    "correlation": source["correlation_id"],
                    "causation": claimed.job_id,
                    "owner": source["created_by_identity_id"],
                },
            )
            self._append_event(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                job_id=reconciliation_job_id,
                event_type="job.queued",
                safe_message_code="project_model_incremental_refresh_queued",
                current=0,
                total=1,
                terminal=False,
            )
        return reconciliation_job_id

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
            if JobState(str(row.state)) in {JobState.QUEUED, JobState.PAUSED}:
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

    def pause_job(self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID) -> JobSummary:
        return self._change_job_control_state(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
            action="pause",
            expected=JobState.QUEUED,
            target=JobState.PAUSED,
        )

    def resume_job(self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID) -> JobSummary:
        return self._change_job_control_state(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
            action="resume",
            expected=JobState.PAUSED,
            target=JobState.QUEUED,
        )

    def _change_job_control_state(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        job_id: UUID,
        action: str,
        expected: JobState,
        target: JobState,
    ) -> JobSummary:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job FOR UPDATE"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            ).one_or_none()
            if row is None:
                raise SpinePersistenceError("job_not_found")
            prior = JobState(str(row.state))
            if prior is target:
                return _job_summary(row)
            if prior is not expected:
                raise SpinePersistenceError(f"job_{action}_not_available")
            control_id = uuid7()
            digest = semantic_digest(
                {
                    "job_id": job_id,
                    "action": action,
                    "prior_state": prior,
                    "result_state": target,
                    "input_digest": str(row.input_digest),
                }
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.durable_jobs SET state=:target,eligible_at=CURRENT_TIMESTAMP "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:job"
                ),
                {
                    "target": target.value,
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": job_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.job_control_decisions "
                    "(organization_id,workspace_id,control_decision_id,job_id,action,prior_state,"
                    "result_state,decided_by_identity_id,decision_digest) VALUES "
                    "(:organization,:workspace,:control,:job,:action,:prior,:result,:owner,:digest) "
                    "ON CONFLICT (organization_id,workspace_id,decision_digest) DO NOTHING"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "control": control_id,
                    "job": job_id,
                    "action": action,
                    "prior": prior.value,
                    "result": target.value,
                    "owner": owner_identity_id,
                    "digest": digest,
                },
            )
            updated = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            ).one()
        return _job_summary(updated)

    def manually_retry_job(
        self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID
    ) -> JobSummary:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job FOR UPDATE"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            ).one_or_none()
            if row is None:
                raise SpinePersistenceError("job_not_found")
            prior = JobState(str(row.state))
            if prior not in {
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.RECONCILIATION_REQUIRED,
            }:
                raise SpinePersistenceError("job_manual_retry_not_available")
            control_id = uuid7()
            derived_job_id = uuid7()
            new_key = f"manual-retry:{job_id}:{control_id}"
            provenance = {
                **dict(row.provenance),
                "manual_retry_of": str(job_id),
                "control_decision_id": str(control_id),
            }
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                    "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                    "provenance,correlation_id,causation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:derived,:document,:kind,CAST(:manifest AS jsonb),"
                    ":digest,:key,'queued',:priority,:attempts,:policy,CAST(:provenance AS jsonb),"
                    ":correlation,:causation,:owner)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "derived": derived_job_id,
                    "document": row.subject_document_id,
                    "kind": str(row.job_kind),
                    "manifest": _json(dict(row.input_manifest)),
                    "digest": str(row.input_digest),
                    "key": new_key,
                    "priority": int(row.priority),
                    "attempts": int(row.max_attempts),
                    "policy": str(row.retry_policy_version),
                    "provenance": _json(provenance),
                    "correlation": row.correlation_id,
                    "causation": job_id,
                    "owner": owner_identity_id,
                },
            )
            decision_digest = semantic_digest(
                {
                    "job_id": job_id,
                    "action": "manual_retry",
                    "prior_state": prior,
                    "derived_job_id": derived_job_id,
                    "input_digest": str(row.input_digest),
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.job_control_decisions "
                    "(organization_id,workspace_id,control_decision_id,job_id,action,prior_state,"
                    "result_state,derived_job_id,decided_by_identity_id,decision_digest) VALUES "
                    "(:organization,:workspace,:control,:job,'manual_retry',:prior,'queued',:derived,"
                    ":owner,:digest)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "control": control_id,
                    "job": job_id,
                    "prior": prior.value,
                    "derived": derived_job_id,
                    "owner": owner_identity_id,
                    "digest": decision_digest,
                },
            )
            derived = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": derived_job_id,
                },
            ).one()
        return _job_summary(derived)

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
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        limit: int = 200,
        effective_only: bool = False,
    ) -> tuple[JobSummary, ...]:
        """List job history or one current attempt for each exact work input.

        A manual retry is a new immutable job, so raw creation order can leave a
        user looking at an old terminal failure while its replacement is running.
        ``effective_only`` intentionally collapses *only* rows with the same
        job kind and input digest.  It therefore cannot substitute a result from
        another source version or another stage for the current work item.
        """
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            if effective_only:
                rows = session.execute(
                    sa.text(
                        "WITH ranked AS (SELECT j.*,CASE WHEN j.state IN ('running','leased') "
                        "AND j.lease_expires_at < CURRENT_TIMESTAMP THEN true ELSE false END AS "
                        "lease_expired,row_number() OVER (PARTITION BY j.job_kind,"
                        "j.input_digest ORDER BY CASE WHEN j.state IN ('running','leased') "
                        "AND j.lease_expires_at >= CURRENT_TIMESTAMP THEN 0 WHEN j.state IN "
                        "('queued','paused') THEN 1 WHEN j.state IN ('running','leased') THEN 2 "
                        "ELSE 3 END,j.created_at DESC,"
                        "j.job_id DESC) AS effective_rank FROM workspace.durable_jobs j WHERE "
                        "j.organization_id=:organization AND j.workspace_id=:workspace) SELECT ranked.*,"
                        "progress.progress_current,progress.progress_total,progress.safe_message_code AS "
                        "progress_message_code,progress.recorded_at AS progress_recorded_at FROM ranked "
                        "LEFT JOIN LATERAL (SELECT progress_current,progress_total,safe_message_code,recorded_at "
                        "FROM workspace.job_progress_events event WHERE event.organization_id=ranked.organization_id "
                        "AND event.workspace_id=ranked.workspace_id AND event.job_id=ranked.job_id "
                        "ORDER BY event.event_sequence DESC LIMIT 1) progress ON true WHERE effective_rank=1 "
                        "ORDER BY CASE WHEN state IN ('running','leased') AND NOT lease_expired "
                        "THEN 0 WHEN state IN ('running','leased') THEN 1 WHEN state IN "
                        "('queued','paused') THEN 2 ELSE 3 END,created_at DESC,job_id DESC LIMIT :limit"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "limit": limit,
                    },
                ).all()
            else:
                rows = session.execute(
                    sa.text(
                        "SELECT j.*,CASE WHEN j.state IN ('running','leased') AND "
                        "j.lease_expires_at < CURRENT_TIMESTAMP THEN true ELSE false END AS "
                        "lease_expired,progress.progress_current,progress.progress_total,"
                        "progress.safe_message_code AS progress_message_code,progress.recorded_at "
                        "AS progress_recorded_at FROM workspace.durable_jobs j LEFT JOIN LATERAL "
                        "(SELECT progress_current,progress_total,safe_message_code,recorded_at FROM "
                        "workspace.job_progress_events event WHERE event.organization_id=j.organization_id "
                        "AND event.workspace_id=j.workspace_id AND event.job_id=j.job_id ORDER BY "
                        "event.event_sequence DESC LIMIT 1) progress ON true WHERE j.organization_id=:organization "
                        "AND j.workspace_id=:workspace ORDER BY j.created_at DESC,j.job_id DESC LIMIT :limit"
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

    def recover_dependency_terminal_failures(self) -> int:
        """Queue audited replacements only after an equivalent prerequisite succeeds."""
        with self._engine.begin() as connection:
            return int(
                connection.scalar(
                    sa.text("SELECT workspace.recover_dependency_terminal_failures()")
                )
                or 0
            )

    def recover_dependents_from_success(self, claimed: ClaimedJob) -> int:
        """Reconnect only terminal dependents of this accepted causal lineage.

        The document worker already holds a concrete organization/workspace scope.
        Recovering from that successful job avoids a global scan of historical
        failures and never changes the original terminal attempt.
        """
        with Session(self._engine) as session, session.begin():
            _set_scope(session, claimed.organization_id, claimed.workspace_id)
            candidates = session.execute(
                sa.text(
                    "WITH RECURSIVE ancestors AS ("
                    "SELECT job_id,causation_id,0 AS depth FROM workspace.durable_jobs "
                    "WHERE organization_id=:organization AND workspace_id=:workspace AND job_id=:success "
                    "UNION ALL "
                    "SELECT parent.job_id,parent.causation_id,ancestors.depth+1 "
                    "FROM workspace.durable_jobs parent JOIN ancestors "
                    "ON parent.job_id=ancestors.causation_id "
                    "WHERE parent.organization_id=:organization AND parent.workspace_id=:workspace "
                    "AND ancestors.depth<32"
                    ") "
                    "SELECT dependent.job_id AS blocked_job_id,dependent.subject_document_id,"
                    "dependent.job_kind,dependent.input_manifest,dependent.input_digest,dependent.priority,"
                    "dependent.max_attempts,dependent.retry_policy_version,dependent.provenance,"
                    "dependent.correlation_id,dependent.created_by_identity_id "
                    "FROM workspace.durable_jobs dependent "
                    "JOIN workspace.durable_job_dependencies dependency "
                    "ON dependency.organization_id=dependent.organization_id "
                    "AND dependency.workspace_id=dependent.workspace_id "
                    "AND dependency.job_id=dependent.job_id "
                    "AND dependency.dependency_kind='success_required' "
                    "JOIN ancestors ON ancestors.job_id=dependency.depends_on_job_id "
                    "WHERE dependent.organization_id=:organization AND dependent.workspace_id=:workspace "
                    "AND dependent.state='reconciliation_required' "
                    "AND dependent.typed_failure_code='dependency_terminal_failure' "
                    "AND NOT EXISTS (SELECT 1 FROM workspace.durable_jobs newer WHERE "
                    "newer.organization_id=dependent.organization_id AND "
                    "newer.workspace_id=dependent.workspace_id AND "
                    "newer.job_kind=dependent.job_kind AND newer.input_digest=dependent.input_digest AND "
                    "newer.state='reconciliation_required' AND "
                    "(newer.created_at,newer.job_id)>(dependent.created_at,dependent.job_id)) "
                    "AND NOT EXISTS (SELECT 1 FROM workspace.durable_jobs replacement WHERE "
                    "replacement.organization_id=dependent.organization_id AND "
                    "replacement.workspace_id=dependent.workspace_id AND "
                    "replacement.provenance->>'dependency_recovery_of'=dependent.job_id::text AND "
                    "replacement.state<>'cancelled') "
                    "ORDER BY dependent.created_at,dependent.job_id LIMIT 32"
                ),
                {
                    "organization": claimed.organization_id,
                    "workspace": claimed.workspace_id,
                    "success": claimed.job_id,
                },
            ).mappings()
            recovered = 0
            for candidate in candidates:
                recovery_id = uuid7()
                idempotency_key = (
                    f"dependency-recovery:{candidate['blocked_job_id']}:{claimed.job_id}"
                )
                inserted = session.scalar(
                    sa.text(
                        "INSERT INTO workspace.durable_jobs ("
                        "organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                        "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                        "provenance,correlation_id,causation_id,created_by_identity_id"
                        ") VALUES ("
                        ":organization,:workspace,:job,:subject,:kind,CAST(:manifest AS jsonb),"
                        ":digest,:idempotency,'queued',:priority,:attempts,:policy,"
                        "CAST(:provenance AS jsonb),:correlation,:causation,:owner"
                        ") ON CONFLICT (organization_id,workspace_id,job_kind,idempotency_key) "
                        "DO NOTHING RETURNING job_id"
                    ),
                    {
                        "organization": claimed.organization_id,
                        "workspace": claimed.workspace_id,
                        "job": recovery_id,
                        "subject": candidate["subject_document_id"],
                        "kind": candidate["job_kind"],
                        "manifest": _json(candidate["input_manifest"]),
                        "digest": candidate["input_digest"],
                        "idempotency": idempotency_key,
                        "priority": candidate["priority"],
                        "attempts": candidate["max_attempts"],
                        "policy": candidate["retry_policy_version"],
                        "provenance": _json(
                            {
                                **dict(candidate["provenance"]),
                                "dependency_recovery_of": str(candidate["blocked_job_id"]),
                                "dependency_recovery_replacement": str(claimed.job_id),
                            }
                        ),
                        "correlation": candidate["correlation_id"],
                        "causation": candidate["blocked_job_id"],
                        "owner": candidate["created_by_identity_id"],
                    },
                )
                if inserted is None:
                    continue
                session.execute(
                    sa.text(
                        "WITH RECURSIVE ancestors AS ("
                        "SELECT job_id,causation_id,0 AS depth FROM workspace.durable_jobs "
                        "WHERE organization_id=:organization AND workspace_id=:workspace "
                        "AND job_id=:success UNION ALL SELECT parent.job_id,parent.causation_id,"
                        "ancestors.depth+1 FROM workspace.durable_jobs parent JOIN ancestors "
                        "ON parent.job_id=ancestors.causation_id WHERE "
                        "parent.organization_id=:organization AND parent.workspace_id=:workspace "
                        "AND ancestors.depth<32) INSERT INTO workspace.durable_job_dependencies "
                        "(organization_id,workspace_id,job_id,depends_on_job_id,dependency_kind) "
                        "SELECT DISTINCT organization_id,workspace_id,:recovery,CASE WHEN "
                        "depends_on_job_id IN (SELECT job_id FROM ancestors) THEN :success "
                        "ELSE depends_on_job_id END,dependency_kind "
                        "FROM workspace.durable_job_dependencies WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND job_id=:blocked ON CONFLICT DO NOTHING"
                    ),
                    {
                        "organization": claimed.organization_id,
                        "workspace": claimed.workspace_id,
                        "recovery": recovery_id,
                        "blocked": candidate["blocked_job_id"],
                        "success": claimed.job_id,
                    },
                )
                self._append_event(
                    session,
                    organization_id=claimed.organization_id,
                    workspace_id=claimed.workspace_id,
                    job_id=recovery_id,
                    event_type="job.queued",
                    safe_message_code="dependency_recovery_queued",
                    current=0,
                    total=1,
                    terminal=False,
                )
                recovered += 1
        return recovered

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

    def get_exact_evidence_locator(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        source_locator_id: UUID,
    ) -> EvidencePanel:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT sl.source_locator_id,sl.source_version_id,sl.locator_value,"
                        "sl.fragment_digest,v.document_id,v.version AS document_version,"
                        "h.page_number,h.width_points,h.height_points,h.rotation_degrees,"
                        "COALESCE(e.extraction_method,'source_locator') AS extraction_method "
                        "FROM workspace.source_locators sl JOIN workspace.document_versions v ON "
                        "v.organization_id=sl.organization_id AND v.workspace_id=sl.workspace_id AND "
                        "v.source_version_id=sl.source_version_id JOIN LATERAL (SELECT * FROM "
                        "workspace.document_page_health_versions h WHERE h.organization_id=sl.organization_id "
                        "AND h.workspace_id=sl.workspace_id AND h.document_id=v.document_id AND "
                        "h.document_version=v.version AND h.page_number=(sl.locator_value->>'page')::bigint "
                        "ORDER BY h.health_version DESC LIMIT 1) h ON true LEFT JOIN "
                        "workspace.native_layout_element_versions e ON "
                        "e.organization_id=sl.organization_id AND e.workspace_id=sl.workspace_id AND "
                        "e.source_locator_id=sl.source_locator_id WHERE sl.organization_id=:organization "
                        "AND sl.workspace_id=:workspace AND sl.source_locator_id=:locator ORDER BY "
                        "e.version DESC NULLS LAST LIMIT 1"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "locator": source_locator_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SpinePersistenceError("evidence_locator_not_found")
        locator_value = dict(row["locator_value"])
        region_raw = locator_value.get("region")
        if not isinstance(region_raw, list | tuple) or len(region_raw) != 4:
            raise SpinePersistenceError("evidence_locator_region_invalid")
        region = tuple(float(value) for value in region_raw)
        locator = PageLocator(
            UUID(str(row["document_id"])),
            int(row["document_version"]),
            UUID(str(row["source_version_id"])),
            UUID(str(row["source_locator_id"])),
            int(row["page_number"]),
            region,  # type: ignore[arg-type]
            float(row["width_points"]),
            float(row["height_points"]),
            int(row["rotation_degrees"]),
            str(row["fragment_digest"]),
            str(row["extraction_method"]),
        )
        return EvidencePanel(
            locator,
            "candidate_or_verified_workspace_fact",
            "workspace_fact_candidate",
            None,
            None,
            None,
            (),
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

    def project_understanding_view(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any] | None:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            reconciliation = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.project_understanding_reconciliations WHERE "
                        "organization_id=:organization AND workspace_id=:workspace "
                        "ORDER BY recorded_at DESC,reconciliation_id,version DESC LIMIT 1"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if reconciliation is None:
                return self._empty_project_understanding_view(
                    session, organization_id=organization_id, workspace_id=workspace_id
                )
            project = (
                session.execute(
                    sa.text(
                        "SELECT project_definition_id,version,purpose,object_class,definition,"
                        "fingerprint,created_at FROM workspace.project_definition_versions WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND "
                        "project_definition_id=:project AND version=:version"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "project": reconciliation["project_definition_id"],
                        "version": reconciliation["project_definition_version"],
                    },
                )
                .mappings()
                .one()
            )
            packages = (
                session.execute(
                    sa.text(
                        "SELECT package.work_package_id,package.version,package.package,"
                        "package.fingerprint FROM "
                        "workspace.project_reconciliation_work_package_memberships member JOIN "
                        "workspace.construction_work_package_versions package ON "
                        "package.organization_id=member.organization_id AND "
                        "package.workspace_id=member.workspace_id AND "
                        "package.work_package_id=member.work_package_id AND "
                        "package.version=member.work_package_version WHERE "
                        "member.organization_id=:organization AND member.workspace_id=:workspace AND "
                        "member.reconciliation_id=:reconciliation AND "
                        "member.reconciliation_version=:reconciliation_version "
                        "ORDER BY member.member_sequence"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "reconciliation": reconciliation["reconciliation_id"],
                        "reconciliation_version": reconciliation["version"],
                    },
                )
                .mappings()
                .all()
            )
            matrix = (
                session.execute(
                    sa.text(
                        "SELECT matrix_id,version,matrix,fingerprint FROM "
                        "workspace.work_requirement_matrix_versions WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND "
                        "matrix_id=:matrix AND version=:version"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "matrix": reconciliation["matrix_id"],
                        "version": reconciliation["matrix_version"],
                    },
                )
                .mappings()
                .one()
            )
            profile = (
                session.execute(
                    sa.text(
                        "SELECT profile_id,version,applicable_on,corpus_denominator,"
                        "normative_edition_ids,rule_version_ids,"
                        "required_pd_sections,expected_rd_sets,formatting_requirements,unresolved_inputs,"
                        "gaps,completeness_status,semantic_fingerprint FROM "
                        "workspace.applicable_pd_rd_normative_profiles WHERE "
                        "organization_id=:organization AND workspace_id=:workspace AND "
                        "project_definition_id=:project AND project_definition_version=:version "
                        "ORDER BY created_at DESC,profile_id LIMIT 1"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "project": reconciliation["project_definition_id"],
                        "version": reconciliation["project_definition_version"],
                    },
                )
                .mappings()
                .one_or_none()
            )
            page_roles = (
                session.execute(
                    sa.text(
                        "SELECT v.source_version_id,split_part(d.scope,':',2)::bigint AS page_number,"
                        "d.selected_roles,d.source_locator_ids,d.decision_code FROM "
                        "workspace.document_role_decisions d JOIN workspace.document_versions v ON "
                        "v.organization_id=d.organization_id AND v.workspace_id=d.workspace_id AND "
                        "v.document_id=d.document_id AND v.version=d.document_version WHERE "
                        "d.organization_id=:organization AND d.workspace_id=:workspace "
                        "ORDER BY v.source_version_id,page_number,d.decision_version"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                )
                .mappings()
                .all()
            )
            defects = (
                session.execute(
                    sa.text(
                        "SELECT defect.defect_id,defect.version,defect.defect_kind,"
                        "defect.subject_identity,defect.related_identity,defect.source_locator_ids,"
                        "defect.parameters,defect.blocking,defect.status FROM "
                        "workspace.project_reconciliation_defect_memberships member JOIN "
                        "workspace.project_reconciliation_defects defect ON "
                        "defect.organization_id=member.organization_id AND "
                        "defect.workspace_id=member.workspace_id AND "
                        "defect.defect_id=member.defect_id AND "
                        "defect.version=member.defect_version WHERE "
                        "member.organization_id=:organization AND member.workspace_id=:workspace AND "
                        "member.reconciliation_id=:reconciliation AND "
                        "member.reconciliation_version=:reconciliation_version "
                        "ORDER BY member.member_sequence"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "reconciliation": reconciliation["reconciliation_id"],
                        "reconciliation_version": reconciliation["version"],
                    },
                )
                .mappings()
                .all()
            )
            candidates = self._project_candidate_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            structure_nodes = self._project_structure_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            structure_relationships = self._project_structure_relationship_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            structure_dossiers = self._structure_dossier_rows(
                structure_nodes,
                structure_relationships,
                [_jsonable_row(row) for row in packages],
            )
            structure_components = self._structure_component_rows(
                structure_nodes, structure_relationships
            )
            structure_identity_candidates = self._structure_identity_candidate_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            structure_identity_components = build_structure_identity_components(
                structure_identity_candidates
            )
            facility_work_projection = build_facility_work_candidate_projection(
                [_jsonable_row(row) for row in packages], structure_identity_components
            )
            structure_identity_dossiers = build_structure_identity_dossiers(
                structure_identity_components,
                structure_nodes=structure_nodes,
                relationships=structure_relationships,
                facility_work_groups=facility_work_projection["candidate_groups"],
            )
            excavation_pit_inventory = build_excavation_pit_inventory(structure_nodes)
            review_decisions = self._project_review_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            intake_summary = self._intake_summary(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            tender_input_assessment = self._tender_input_assessment(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            intake_summary["tender_input_assessment"] = tender_input_assessment
            semantic_coverage = self._semantic_extraction_coverage(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            structure_identity_reconciliation = self._structure_identity_reconciliation_status(
                session, organization_id=organization_id, workspace_id=workspace_id
            )
            evidence_index = self._workspace_evidence_index(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                locator_ids=self._response_locator_ids(
                    project,
                    packages,
                    matrix,
                    profile,
                    page_roles,
                    defects,
                    candidates,
                    structure_nodes,
                    structure_relationships,
                    structure_components,
                    structure_identity_candidates,
                    structure_identity_components,
                    structure_identity_dossiers,
                    tender_input_assessment,
                ),
            )
        return {
            "materialization": {
                "state": "complete"
                if str(reconciliation["terminal_status"]) == "complete"
                else "partial",
                "reconciliation_id": str(reconciliation["reconciliation_id"]),
                "source_count": int(reconciliation["source_count"]),
                "page_count": int(reconciliation["page_count"]),
                "gaps": list(reconciliation["gaps"]),
            },
            "reconciliation": _jsonable_row(reconciliation),
            "project_definition": _jsonable_row(project),
            "page_roles": [_jsonable_row(row) for row in page_roles],
            "work_packages": [_jsonable_row(row) for row in packages],
            "matrix": _jsonable_row(matrix),
            "normative_profile": _jsonable_row(profile) if profile is not None else None,
            "defects": [_jsonable_row(row) for row in defects],
            "evidence_index": evidence_index,
            "candidates": candidates,
            "structure_nodes": structure_nodes,
            "structure_relationships": structure_relationships,
            "structure_dossiers": structure_dossiers,
            "structure_components": structure_components,
            "structure_identity_candidates": structure_identity_candidates,
            "structure_identity_components": structure_identity_components,
            "structure_identity_reconciliation": structure_identity_reconciliation,
            "structure_identity_dossiers": structure_identity_dossiers,
            "excavation_pit_inventory": excavation_pit_inventory,
            "facility_work_projection": {
                "candidate_groups": facility_work_projection["candidate_groups"],
                "coverage": facility_work_projection["coverage"],
            },
            "review_decisions": review_decisions,
            "intake_summary": intake_summary,
            "semantic_coverage": semantic_coverage,
            "authority_layers": {
                "workspace_fact": "project_definition_and_document_registry",
                "methodological_practice": "advisory_only",
                "normative_authority": "verified_subset_only",
                "customer_addition": "workspace_additive_only",
                "ai_candidate": "candidate_only",
            },
        }

    def _schedule_workspace_semantic_extractions(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        owner_identity_id: str,
        correlation_id: UUID,
        sources: list[dict[str, Any]],
    ) -> list[dict[str, object]]:
        """Queue one explicit v15 semantic pass per native-readable active source.

        The intake pipeline historically chained semantic extraction behind OCR and
        page-role classification.  Native-readable project content must instead be
        eligible for the evidence-bound Qwen pass once its persisted layout exists.
        This does not alter the old dependency graph or terminal receipts; each new
        job has an explicit semantic-profile provenance and never duplicates an
        active equivalent pass.
        """
        coverage_by_source = {
            str(row["source_version_id"]): row
            for row in self._semantic_extraction_coverage(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
            )
        }
        scheduled: list[dict[str, object]] = []
        for source in sources:
            source_version_id = UUID(str(source["source_version_id"]))
            locator_count = int(source["native_locator_count"])
            coverage = coverage_by_source.get(str(source_version_id))
            semantic_priority = _semantic_extraction_priority(
                tuple(str(role) for role in source.get("document_roles", ()))
            )
            latest = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                        "AND workspace_id=:workspace AND job_kind='PROJECT_DEFINITION_EXTRACTION' "
                        "AND input_manifest->>'source_version_id'=:source AND "
                        "provenance->>'engineering_semantic_profile'=:profile ORDER BY "
                        "created_at DESC,job_id DESC LIMIT 1"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "source": str(source_version_id),
                        "profile": ENGINEERING_SEMANTIC_PROFILE_VERSION,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if locator_count == 0:
                scheduled.append(
                    {
                        "source_version_id": str(source_version_id),
                        "state": "native_layout_unavailable",
                    }
                )
                continue
            if latest is not None and str(latest["state"]) in {"queued", "running"}:
                # Priority is dispatch metadata, not an engineering result.  Update
                # only an unclaimed, compatible semantic pass; a running lease must
                # keep its existing ordering and immutable input contract.
                latest_provenance = dict(latest["provenance"])
                if (
                    str(latest["state"]) == "queued"
                    and latest_provenance.get("engineering_semantic_profile")
                    == ENGINEERING_SEMANTIC_PROFILE_VERSION
                    and int(latest["priority"]) != semantic_priority
                ):
                    session.execute(
                        sa.text(
                            "UPDATE workspace.durable_jobs SET priority=:priority WHERE "
                            "organization_id=:organization AND workspace_id=:workspace AND "
                            "job_id=:job AND state='queued'"
                        ),
                        {
                            "organization": organization_id,
                            "workspace": workspace_id,
                            "job": latest["job_id"],
                            "priority": semantic_priority,
                        },
                    )
                    self._append_event(
                        session,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        job_id=UUID(str(latest["job_id"])),
                        event_type="job.priority_recomputed",
                        safe_message_code="semantic_priority_recomputed_from_document_role",
                        current=None,
                        total=None,
                        terminal=False,
                    )
                scheduled.append(
                    {
                        "source_version_id": str(source_version_id),
                        "job_id": str(latest["job_id"]),
                        "state": str(latest["state"]),
                        "priority": semantic_priority,
                    }
                )
                continue
            latest_provenance = dict(latest["provenance"]) if latest is not None else {}
            coverage_complete = bool(coverage is not None and str(coverage["state"]) == "complete")
            latest_profile_persistence_complete = bool(
                latest is not None
                and latest_provenance.get("engineering_semantic_profile")
                == ENGINEERING_SEMANTIC_PROFILE_VERSION
                and latest_provenance.get("candidate_persistence_profile")
                == ENGINEERING_CANDIDATE_PERSISTENCE_PROFILE
                and coverage_complete
                and session.scalar(
                    sa.text(
                        "SELECT EXISTS (SELECT 1 FROM workspace.project_understanding_stage_results "
                        "WHERE organization_id=:organization AND workspace_id=:workspace "
                        "AND job_id=:job AND stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                        "AND terminal_status='complete')"
                    ),
                    {
                        "organization": organization_id,
                        "workspace": workspace_id,
                        "job": latest["job_id"],
                    },
                )
            )
            if (
                latest is not None
                and str(latest["state"]) == "succeeded"
                and latest_profile_persistence_complete
            ):
                scheduled.append(
                    {
                        "source_version_id": str(source_version_id),
                        "job_id": str(latest["job_id"]),
                        "state": "succeeded",
                    }
                )
                continue

            recovery_attempt = int(latest_provenance.get("semantic_coverage_recovery_attempt", 0))
            if (
                latest is not None
                and str(latest["state"]) == "succeeded"
                and coverage is not None
                and str(coverage["state"]) == "partial"
                and latest_provenance.get("semantic_coverage_recovery_contract")
                == ENGINEERING_SEMANTIC_RECOVERY_CONTRACT
                and recovery_attempt >= 1
            ):
                scheduled.append(
                    {
                        "source_version_id": str(source_version_id),
                        "job_id": str(latest["job_id"]),
                        "state": "partial_coverage_requires_contract_repair",
                        "accepted_fragment_count": int(coverage["accepted_fragment_count"]),
                        "expected_fragment_count": int(coverage["expected_fragment_count"]),
                        "unresolved_failed_fragment_count": int(
                            coverage["unresolved_failed_fragment_count"]
                        ),
                    }
                )
                continue

            # A complete accepted manifest is reusable evidence, but it does not
            # by itself prove that candidates reached the project model.  A
            # terminal semantic job without a complete persistence receipt is
            # therefore allowed to run once more and reuse those exact batches.
            # Conversely, incomplete coverage must never be hidden behind an
            # arbitrary newer reconciliation job for the same source.  The
            # coverage map is deliberately read before selecting lineage so the
            # decision is based on effective source evidence, not job-list order.

            control_id = uuid7()
            job_id = uuid7()
            coverage_state = str(coverage["state"]) if coverage is not None else "not_started"
            next_recovery_attempt = (
                recovery_attempt + 1
                if coverage is not None
                and coverage_state == "partial"
                and latest_provenance.get("semantic_coverage_recovery_contract")
                == ENGINEERING_SEMANTIC_RECOVERY_CONTRACT
                else int(coverage is not None and coverage_state == "partial")
            )
            recovery_reason = (
                "accepted_batches_pending_persistence"
                if coverage_state == "complete"
                else "incomplete_semantic_coverage"
            )
            manifest = {
                "document_id": str(source["document_id"]),
                "document_version": int(source["version"]),
                "source_version_id": str(source_version_id),
                "object_key": str(source["object_key"]),
                "media_type": str(source["media_type"]),
                "content_digest": str(source["content_digest"]),
                "engineering_semantic_profile": ENGINEERING_SEMANTIC_PROFILE_VERSION,
                "candidate_persistence_profile": ENGINEERING_CANDIDATE_PERSISTENCE_PROFILE,
                "semantic_coverage_state": coverage_state,
                "semantic_coverage_recovery_contract": ENGINEERING_SEMANTIC_RECOVERY_CONTRACT,
            }
            provenance = {
                "contract": "project-understanding.semantic-recovery@1.0.0",
                "source_version_id": str(source_version_id),
                "engineering_semantic_profile": ENGINEERING_SEMANTIC_PROFILE_VERSION,
                "candidate_persistence_profile": ENGINEERING_CANDIDATE_PERSISTENCE_PROFILE,
                "semantic_recovery_reason": recovery_reason,
                "accepted_fragment_count": int(coverage["accepted_fragment_count"])
                if coverage is not None
                else 0,
                "expected_fragment_count": int(coverage["expected_fragment_count"])
                if coverage is not None
                else 0,
                "semantic_coverage_recovery_attempt": next_recovery_attempt,
                "semantic_coverage_recovery_contract": ENGINEERING_SEMANTIC_RECOVERY_CONTRACT,
                "control_decision_id": str(control_id),
                "semantic_recovery_of": str(latest["job_id"]) if latest is not None else None,
            }
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs (organization_id,workspace_id,job_id,"
                    "subject_document_id,job_kind,input_manifest,input_digest,idempotency_key,state,"
                    "priority,max_attempts,retry_policy_version,provenance,correlation_id,causation_id,"
                    "created_by_identity_id) VALUES (:organization,:workspace,:job,:document,"
                    "'PROJECT_DEFINITION_EXTRACTION',CAST(:manifest AS jsonb),:digest,:key,'queued',"
                    ":priority,3,'spine-retry-v0.1',CAST(:provenance AS jsonb),:correlation,:causation,:owner)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": job_id,
                    "document": source["document_id"],
                    "manifest": _json(manifest),
                    "digest": semantic_digest(
                        {"kind": JobKind.PROJECT_DEFINITION_EXTRACTION.value, "manifest": manifest}
                    ),
                    "key": (
                        "semantic-recovery:"
                        f"{source_version_id}:{ENGINEERING_SEMANTIC_PROFILE_VERSION}:{control_id}"
                    ),
                    "provenance": _json(provenance),
                    "correlation": correlation_id,
                    "causation": latest["job_id"] if latest is not None else None,
                    "owner": owner_identity_id,
                    "priority": semantic_priority,
                },
            )
            self._append_event(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_id=job_id,
                event_type="job.queued",
                safe_message_code="semantic_extraction_queued_from_native_layout",
                current=0,
                total=1,
                terminal=False,
            )
            scheduled.append(
                {
                    "source_version_id": str(source_version_id),
                    "job_id": str(job_id),
                    "state": "queued",
                    "priority": semantic_priority,
                }
            )
        return scheduled

    def start_project_understanding(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        correlation_id: UUID,
    ) -> JobSummary:
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            sources = list(
                session.execute(
                    sa.text(
                        "WITH active_versions AS ("
                        " SELECT v.document_id,v.version,v.source_version_id,v.object_key,v.media_type,"
                        " v.content_digest,v.recorded_at FROM workspace.document_versions v JOIN LATERAL ("
                        " SELECT selected_document_version FROM "
                        " workspace.document_version_activation_decisions a WHERE "
                        " a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
                        " AND a.document_id=v.document_id ORDER BY a.decision_version DESC LIMIT 1"
                        " ) activation ON activation.selected_document_version=v.version WHERE "
                        " v.organization_id=:organization AND v.workspace_id=:workspace "
                        " AND v.media_type<>'application/zip'"
                        "), native_counts AS (SELECT locators.source_version_id,COUNT(DISTINCT elements.source_locator_id) "
                        "FILTER (WHERE coalesce(elements.raw_text,'')<>'') AS native_locator_count "
                        "FROM workspace.source_locators locators LEFT JOIN workspace.native_layout_element_versions elements ON "
                        "elements.organization_id=locators.organization_id AND elements.workspace_id=locators.workspace_id "
                        "AND elements.source_locator_id=locators.source_locator_id "
                        "WHERE locators.organization_id=:organization AND locators.workspace_id=:workspace "
                        "GROUP BY locators.source_version_id), role_summaries AS (SELECT d.document_id,d.document_version,"
                        "array_agg(DISTINCT role.value ORDER BY role.value) AS document_roles "
                        "FROM workspace.document_role_decisions d CROSS JOIN LATERAL "
                        "unnest(d.selected_roles) AS role(value) "
                        "WHERE d.organization_id=:organization AND d.workspace_id=:workspace "
                        "GROUP BY d.document_id,d.document_version) SELECT active_versions.*,"
                        "COALESCE(native_counts.native_locator_count,0) AS native_locator_count,"
                        "COALESCE(role_summaries.document_roles,ARRAY[]::text[]) AS document_roles "
                        "FROM active_versions LEFT JOIN native_counts ON native_counts.source_version_id=active_versions.source_version_id "
                        "LEFT JOIN role_summaries ON role_summaries.document_id=active_versions.document_id "
                        "AND role_summaries.document_version=active_versions.version "
                        "ORDER BY active_versions.recorded_at DESC,active_versions.document_id"
                    ),
                    {"organization": organization_id, "workspace": workspace_id},
                )
                .mappings()
                .all()
            )
            if not sources:
                raise SpinePersistenceError("project_understanding_sources_unavailable")
            document = sources[0]
            source_ids = [UUID(str(source["source_version_id"])) for source in sources]
            semantic_jobs = self._schedule_workspace_semantic_extractions(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                owner_identity_id=owner_identity_id,
                correlation_id=correlation_id,
                sources=[dict(source) for source in sources],
            )
            reviews = session.scalars(
                sa.text(
                    "SELECT decision_digest FROM workspace.project_candidate_review_decisions WHERE "
                    "organization_id=:organization AND workspace_id=:workspace ORDER BY "
                    "review_decision_id,decision_version"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            ).all()
            semantic_input = semantic_digest(
                {
                    "source_version_ids": [str(item) for item in source_ids],
                    "reviews": list(reviews),
                    "semantic_jobs": semantic_jobs,
                }
            )
            idempotency_key = (
                f"project-understanding:{PROJECT_RECONCILIATION_PROFILE_VERSION}:{semantic_input}"
            )
            existing = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_kind='PROJECT_UNDERSTANDING_RECONCILIATION' "
                    "AND idempotency_key=:key"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "key": idempotency_key,
                },
            ).one_or_none()
            if existing is not None:
                self._ensure_structure_reconciliation_job(
                    session,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    owner_identity_id=owner_identity_id,
                    correlation_id=correlation_id,
                    project_job_id=UUID(str(existing.job_id)),
                    document=dict(document),
                    semantic_input=semantic_input,
                )
                return _job_summary(existing)
            manifest = {
                "document_id": document["document_id"],
                "document_version": document["version"],
                "source_version_id": document["source_version_id"],
                "object_key": document["object_key"],
                "media_type": document["media_type"],
                "content_digest": document["content_digest"],
                "corpus_semantic_input": semantic_input,
                "project_reconciliation_profile": PROJECT_RECONCILIATION_PROFILE_VERSION,
            }
            job_id = uuid7()
            session.execute(
                sa.text(
                    "INSERT INTO workspace.durable_jobs "
                    "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                    "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                    "provenance,correlation_id,created_by_identity_id) VALUES "
                    "(:organization,:workspace,:job,:document,'PROJECT_UNDERSTANDING_RECONCILIATION',"
                    "CAST(:manifest AS jsonb),:digest,:key,'queued',120,3,'spine-retry-v0.1',"
                    "CAST(:provenance AS jsonb),:correlation,:owner)"
                ),
                {
                    "organization": organization_id,
                    "workspace": workspace_id,
                    "job": job_id,
                    "document": document["document_id"],
                    "manifest": _json(manifest),
                    "digest": semantic_digest(manifest),
                    "key": idempotency_key,
                    "provenance": _json(
                        {
                            "contract": "project-understanding.command@1.0.0",
                            "input": semantic_input,
                            "project_reconciliation_profile": (
                                PROJECT_RECONCILIATION_PROFILE_VERSION
                            ),
                        }
                    ),
                    "correlation": correlation_id,
                    "owner": owner_identity_id,
                },
            )
            self._append_event(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                job_id=job_id,
                event_type="job.queued",
                safe_message_code="project_model_formation_queued",
                current=0,
                total=1,
                terminal=False,
            )
            self._ensure_structure_reconciliation_job(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                owner_identity_id=owner_identity_id,
                correlation_id=correlation_id,
                project_job_id=job_id,
                document=dict(document),
                semantic_input=semantic_input,
            )
            row = session.execute(
                sa.text(
                    "SELECT * FROM workspace.durable_jobs WHERE organization_id=:organization "
                    "AND workspace_id=:workspace AND job_id=:job"
                ),
                {"organization": organization_id, "workspace": workspace_id, "job": job_id},
            ).one()
        return _job_summary(row)

    def _ensure_structure_reconciliation_job(
        self,
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        owner_identity_id: str,
        correlation_id: UUID,
        project_job_id: UUID,
        document: Mapping[str, Any],
        semantic_input: str,
    ) -> UUID:
        """Queue one identity-reconciliation pass behind the materialized model.

        Project publication deliberately does not wait for optional cross-document
        identity inference.  The corresponding durable job still has to exist: it
        consumes the published source-scoped observations and may fail partially
        without suppressing the already useful project view.
        """
        idempotency_key = (
            "project-structure-reconciliation:"
            f"{STRUCTURE_IDENTITY_GROUPING_POLICY_VERSION}:"
            f"{STRUCTURE_IDENTITY_RESULT_MANIFEST_VERSION}:{semantic_input}"
        )
        existing = session.scalar(
            sa.text(
                "SELECT job_id FROM workspace.durable_jobs WHERE organization_id=:organization "
                "AND workspace_id=:workspace AND job_kind='PROJECT_STRUCTURE_RECONCILIATION' "
                "AND idempotency_key=:key"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "key": idempotency_key,
            },
        )
        if existing is not None:
            return UUID(str(existing))
        job_id = uuid7()
        manifest = {
            "document_id": str(document["document_id"]),
            "document_version": int(document["version"]),
            "source_version_id": str(document["source_version_id"]),
            "object_key": str(document["object_key"]),
            "media_type": str(document["media_type"]),
            "content_digest": str(document["content_digest"]),
            "corpus_semantic_input": semantic_input,
            "project_reconciliation_job_id": str(project_job_id),
            "structure_identity_grouping_policy": (STRUCTURE_IDENTITY_GROUPING_POLICY_VERSION),
            "structure_identity_result_manifest_version": (
                STRUCTURE_IDENTITY_RESULT_MANIFEST_VERSION
            ),
        }
        session.execute(
            sa.text(
                "INSERT INTO workspace.durable_jobs "
                "(organization_id,workspace_id,job_id,subject_document_id,job_kind,input_manifest,"
                "input_digest,idempotency_key,state,priority,max_attempts,retry_policy_version,"
                "provenance,correlation_id,causation_id,created_by_identity_id) VALUES "
                "(:organization,:workspace,:job,:document,'PROJECT_STRUCTURE_RECONCILIATION',"
                "CAST(:manifest AS jsonb),:digest,:key,'queued',110,3,'spine-retry-v0.1',"
                "CAST(:provenance AS jsonb),:correlation,:causation,:owner)"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "job": job_id,
                "document": document["document_id"],
                "manifest": _json(manifest),
                "digest": semantic_digest(manifest),
                "key": idempotency_key,
                "provenance": _json(
                    {
                        "contract": "project-structure-reconciliation.command@1.0.0",
                        "input": semantic_input,
                        "grouping_policy": STRUCTURE_IDENTITY_GROUPING_POLICY_VERSION,
                        "result_manifest_version": STRUCTURE_IDENTITY_RESULT_MANIFEST_VERSION,
                    }
                ),
                "correlation": correlation_id,
                "causation": project_job_id,
                "owner": owner_identity_id,
            },
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.durable_job_dependencies "
                "(organization_id,workspace_id,job_id,depends_on_job_id,dependency_kind) "
                "VALUES (:organization,:workspace,:job,:project,'success_required')"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "job": job_id,
                "project": project_job_id,
            },
        )
        self._append_event(
            session,
            organization_id=organization_id,
            workspace_id=workspace_id,
            job_id=job_id,
            event_type="job.queued",
            safe_message_code="project_structure_reconciliation_queued",
            current=0,
            total=1,
            terminal=False,
        )
        return job_id

    def review_project_candidate(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_kind: str,
        candidate_id: UUID,
        candidate_version: int,
        action: str,
        resolved_value: Any | None,
        reason: str,
    ) -> dict[str, Any]:
        relation = {
            "project_field": ("project_field_candidates", "source_version_id", "raw_value"),
            "work_type": ("work_type_candidates", "source_version_id", "raw_name"),
            "quantity": ("quantity_candidates", None, "raw_value"),
            "material": ("material_candidates", None, "raw_name"),
        }.get(candidate_kind)
        if relation is None or action not in {"confirmed", "rejected", "corrected"}:
            raise SpinePersistenceError("project_candidate_review_invalid")
        if candidate_version < 1 or len(reason.strip()) < 3:
            raise SpinePersistenceError("project_candidate_review_reason_required")
        organization_id = self.resolve_scope(owner_identity_id, workspace_id)
        table, source_column, value_column = relation
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            if source_column is None:
                row = (
                    session.execute(
                        sa.text(
                            f"SELECT child.*,work.source_version_id FROM workspace.{table} child JOIN "
                            "workspace.work_type_candidates work ON work.organization_id=child.organization_id "
                            "AND work.workspace_id=child.workspace_id AND work.candidate_id=child.work_candidate_id "
                            "AND work.version=child.work_candidate_version WHERE child.organization_id=:o "
                            "AND child.workspace_id=:w AND child.candidate_id=:candidate AND child.version=:version"
                        ),
                        {
                            "o": organization_id,
                            "w": workspace_id,
                            "candidate": candidate_id,
                            "version": candidate_version,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
            else:
                row = (
                    session.execute(
                        sa.text(
                            f"SELECT * FROM workspace.{table} WHERE organization_id=:o AND "
                            "workspace_id=:w AND candidate_id=:candidate AND version=:version"
                        ),
                        {
                            "o": organization_id,
                            "w": workspace_id,
                            "candidate": candidate_id,
                            "version": candidate_version,
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
            if row is None:
                raise SpinePersistenceError("project_candidate_not_found")
            review_id = uuid5(
                OWNER_ORGANIZATION_NAMESPACE,
                f"project-review:{workspace_id}:{candidate_kind}:{candidate_id}",
            )
            prior = session.scalar(
                sa.text(
                    "SELECT max(decision_version) FROM workspace.project_candidate_review_decisions "
                    "WHERE organization_id=:o AND workspace_id=:w AND review_decision_id=:review"
                ),
                {"o": organization_id, "w": workspace_id, "review": review_id},
            )
            decision_version = int(prior or 0) + 1
            original = {"value": row[value_column]}
            corrected = resolved_value if action == "corrected" else None
            digest = semantic_digest(
                {
                    "review_decision_id": review_id,
                    "decision_version": decision_version,
                    "candidate_kind": candidate_kind,
                    "candidate_id": candidate_id,
                    "candidate_version": candidate_version,
                    "action": action,
                    "original_value": original,
                    "resolved_value": corrected,
                    "reason": reason.strip(),
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_candidate_review_decisions "
                    "(organization_id,workspace_id,review_decision_id,decision_version,candidate_kind,"
                    "candidate_id,candidate_version,source_version_id,source_locator_id,action,original_value,"
                    "resolved_value,reason,supersedes_decision_version,decided_by_identity_id,decision_digest) "
                    "VALUES (:o,:w,:review,:decision_version,:kind,:candidate,:candidate_version,:source,"
                    ":locator,:action,CAST(:original AS jsonb),CAST(:resolved AS jsonb),:reason,:supersedes,"
                    ":owner,:digest)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "review": review_id,
                    "decision_version": decision_version,
                    "kind": candidate_kind,
                    "candidate": candidate_id,
                    "candidate_version": candidate_version,
                    "source": row["source_version_id"],
                    "locator": row["source_locator_id"],
                    "action": action,
                    "original": _json(original),
                    "resolved": _json(corrected) if corrected is not None else None,
                    "reason": reason.strip(),
                    "supersedes": int(prior) if prior else None,
                    "owner": owner_identity_id,
                    "digest": digest,
                },
            )
        return {
            "review_decision_id": review_id,
            "decision_version": decision_version,
            "action": action,
            "decision_digest": digest,
        }

    @staticmethod
    def _intake_summary(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        rows = session.execute(
            sa.text(
                "SELECT s.admission_status,s.extraction_status,count(*) AS count FROM "
                "workspace.document_processing_states s WHERE s.organization_id=:o AND s.workspace_id=:w "
                "AND NOT EXISTS (SELECT 1 FROM workspace.document_processing_states newer WHERE "
                "newer.organization_id=s.organization_id AND newer.workspace_id=s.workspace_id AND "
                "newer.document_id=s.document_id AND newer.document_version=s.document_version AND "
                "newer.state_sequence>s.state_sequence) GROUP BY s.admission_status,s.extraction_status"
            ),
            {"o": organization_id, "w": workspace_id},
        ).mappings()
        jobs = session.execute(
            sa.text(
                "SELECT state,count(*) AS count FROM workspace.durable_jobs WHERE organization_id=:o "
                "AND workspace_id=:w GROUP BY state"
            ),
            {"o": organization_id, "w": workspace_id},
        ).mappings()
        return {
            "documents": [dict(item) for item in rows],
            "jobs": [dict(item) for item in jobs],
        }

    @staticmethod
    def _tender_input_assessment(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Assess usable Tender input classes from active classified sources.

        A missing contract cannot invalidate design analysis.  Conversely, an
        unclassified active source prevents the application from claiming that
        a source class is absent.  This is an operational assessment of
        supplied inputs, not a contractual or professional conclusion.
        """

        rows = (
            session.execute(
                sa.text(
                    "WITH active_versions AS (SELECT DISTINCT ON (v.document_id) "
                    "v.document_id,v.version,v.source_version_id,v.safe_display_name FROM "
                    "workspace.document_versions v JOIN workspace.document_version_activation_decisions a "
                    "ON a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
                    "AND a.document_id=v.document_id AND a.selected_document_version=v.version "
                    "WHERE v.organization_id=:o AND v.workspace_id=:w AND NOT EXISTS (SELECT 1 FROM "
                    "workspace.document_version_activation_decisions newer WHERE "
                    "newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                    "AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version) "
                    "ORDER BY v.document_id,a.decision_version DESC), roles AS (SELECT d.document_id,"
                    "d.document_version,array_agg(DISTINCT role.value ORDER BY role.value) AS roles,"
                    "array_agg(DISTINCT locator ORDER BY locator) FILTER (WHERE locator IS NOT NULL) AS locator_ids "
                    "FROM workspace.document_role_decisions d CROSS JOIN LATERAL unnest(d.selected_roles) AS role(value) "
                    "LEFT JOIN LATERAL unnest(d.source_locator_ids) AS locator ON true "
                    "WHERE d.organization_id=:o AND d.workspace_id=:w GROUP BY d.document_id,d.document_version) "
                    "SELECT active.source_version_id,active.safe_display_name,COALESCE(roles.roles,ARRAY[]::text[]) AS roles,"
                    "COALESCE(roles.locator_ids,ARRAY[]::uuid[]) AS locator_ids FROM active_versions active "
                    "LEFT JOIN roles ON roles.document_id=active.document_id AND roles.document_version=active.version "
                    "ORDER BY active.safe_display_name,active.source_version_id"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .all()
        )
        categories = (
            (
                "design_or_working_documentation",
                {
                    "project_documentation",
                    "working_documentation",
                    "explanatory_note",
                    "drawing_or_scheme",
                },
                "design_analysis",
                "Design and working documentation are required to assess design scope and constructability.",
            ),
            (
                "quantity_or_estimate",
                {
                    "bill_of_quantities",
                    "local_estimate",
                    "object_estimate",
                    "consolidated_estimate",
                },
                "quantity_comparison",
                "Quantity and cost comparison remains limited without a bill of quantities or estimate.",
            ),
            (
                "draft_contract",
                {"contract"},
                "contract_analysis",
                "Contract changes and contractual risk review remain limited without a draft contract.",
            ),
            (
                "customer_regulation",
                {"customer_regulation"},
                "customer_requirements",
                "Customer-specific submission and documentation requirements remain limited without a regulation.",
            ),
            (
                "specifications",
                {"specification"},
                "materials_comparison",
                "Material and equipment comparison remains limited without specifications.",
            ),
        )
        classified_count = sum(1 for row in rows if row["roles"])
        result: list[dict[str, Any]] = []
        for category, accepted_roles, analysis, limitation in categories:
            matched = [row for row in rows if set(row["roles"]) & accepted_roles]
            if matched:
                state = "available"
            elif classified_count < len(rows):
                state = "classification_incomplete"
            else:
                state = "not_detected_in_classified_sources"
            result.append(
                {
                    "category": category,
                    "analysis": analysis,
                    "state": state,
                    "practical_limitation": "" if state == "available" else limitation,
                    "active_source_count": len(matched),
                    "source_versions": [str(row["source_version_id"]) for row in matched],
                    "source_names": [str(row["safe_display_name"]) for row in matched],
                    "source_locator_ids": sorted(
                        {str(locator) for row in matched for locator in row["locator_ids"]}
                    ),
                    "classification_coverage": {
                        "active_source_count": len(rows),
                        "classified_source_count": classified_count,
                    },
                }
            )
        return result

    @staticmethod
    def _project_candidate_rows(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, list[dict[str, Any]]]:
        profile_scope = (
            "WITH active_sources AS (SELECT DISTINCT ON (v.document_id) v.source_version_id "
            "FROM workspace.document_versions v JOIN workspace.document_version_activation_decisions a "
            "ON a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
            "AND a.document_id=v.document_id AND a.selected_document_version=v.version "
            "WHERE v.organization_id=:o AND v.workspace_id=:w AND NOT EXISTS (SELECT 1 FROM "
            "workspace.document_version_activation_decisions newer WHERE newer.organization_id=a.organization_id "
            "AND newer.workspace_id=a.workspace_id AND newer.document_id=a.document_id "
            "AND newer.decision_version>a.decision_version) ORDER BY v.document_id,a.decision_version DESC), "
            "profile_receipts AS (SELECT result.source_version_id,"
            "COALESCE(job.provenance->>'engineering_semantic_profile',result.profile_version) AS semantic_profile,"
            "result.recorded_at,2 AS receipt_rank FROM workspace.project_understanding_stage_results result "
            "JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id AND "
            "job.workspace_id=result.workspace_id AND job.job_id=result.job_id JOIN active_sources active "
            "ON active.source_version_id=result.source_version_id WHERE result.organization_id=:o "
            "AND result.workspace_id=:w AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
            "AND result.terminal_status IN ('complete','partial') UNION ALL SELECT batch.source_version_id,"
            "batch.profile_version AS semantic_profile,batch.recorded_at,1 AS receipt_rank FROM "
            "workspace.engineering_extraction_batches batch JOIN active_sources active ON "
            "active.source_version_id=batch.source_version_id WHERE batch.organization_id=:o AND "
            "batch.workspace_id=:w AND batch.terminal_status='accepted'), selected_profiles AS "
            "(SELECT DISTINCT ON (source_version_id) source_version_id,semantic_profile FROM profile_receipts "
            "ORDER BY source_version_id,recorded_at DESC,receipt_rank DESC) "
        )
        queries = {
            "project_fields": profile_scope
            + "SELECT candidate.candidate_id,candidate.version,candidate.field_key AS label,candidate.raw_value AS value,"
            "candidate.normalized_value,candidate.source_version_id,candidate.source_locator_id,candidate.status,"
            "candidate.uncertainty_codes,candidate.conflicts,candidate.extraction_profile_version "
            "FROM workspace.project_field_candidates candidate "
            "JOIN selected_profiles selected ON selected.source_version_id=candidate.source_version_id WHERE "
            "candidate.organization_id=:o AND candidate.workspace_id=:w AND candidate.extraction_profile_version="
            "CASE WHEN selected.semantic_profile LIKE 'qwen-engineering-extraction-%' THEN selected.semantic_profile "
            "ELSE 'project-definition-extraction-v0.1' END",
            "work_types": profile_scope
            + "SELECT candidate.candidate_id,candidate.version,candidate.normalized_name AS label,candidate.raw_name AS value,"
            "candidate.source_version_id,candidate.source_locator_id,candidate.canonical_mapping_status AS status,"
            "candidate.extraction_profile_version "
            "FROM workspace.work_type_candidates candidate JOIN selected_profiles selected "
            "ON selected.source_version_id=candidate.source_version_id WHERE candidate.organization_id=:o "
            "AND candidate.workspace_id=:w AND candidate.extraction_profile_version=CASE WHEN "
            "selected.semantic_profile LIKE 'qwen-engineering-extraction-%' THEN selected.semantic_profile "
            "ELSE 'work-quantity-material-extraction-v0.1' END",
            "quantities": profile_scope
            + "SELECT q.candidate_id,q.version,w.normalized_name AS label,q.raw_value AS value,"
            "q.parsed_value AS normalized_value,w.source_version_id,q.source_locator_id,q.status,q.raw_unit,"
            "q.normalized_unit,w.extraction_profile_version FROM workspace.quantity_candidates q "
            "JOIN workspace.work_type_candidates w "
            "ON w.organization_id=q.organization_id AND w.workspace_id=q.workspace_id AND "
            "w.candidate_id=q.work_candidate_id AND w.version=q.work_candidate_version JOIN selected_profiles selected "
            "ON selected.source_version_id=w.source_version_id WHERE q.organization_id=:o AND q.workspace_id=:w "
            "AND w.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
            "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE "
            "'work-quantity-material-extraction-v0.1' END",
            "materials": profile_scope
            + "SELECT m.candidate_id,m.version,w.normalized_name AS label,m.raw_name AS value,"
            "m.parsed_quantity AS normalized_value,w.source_version_id,m.source_locator_id,m.status,"
            "m.raw_quantity,m.raw_unit,m.normalized_unit,w.extraction_profile_version "
            "FROM workspace.material_candidates m JOIN "
            "workspace.work_type_candidates w ON w.organization_id=m.organization_id AND "
            "w.workspace_id=m.workspace_id AND w.candidate_id=m.work_candidate_id AND "
            "w.version=m.work_candidate_version JOIN selected_profiles selected ON "
            "selected.source_version_id=w.source_version_id WHERE m.organization_id=:o AND m.workspace_id=:w "
            "AND w.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
            "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE "
            "'work-quantity-material-extraction-v0.1' END",
        }
        return {
            key: [
                _jsonable_row(row)
                for row in session.execute(
                    sa.text(query + " ORDER BY candidate_id,version"),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            ]
            for key, query in queries.items()
        }

    @staticmethod
    def _project_review_rows(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        rows = session.execute(
            sa.text(
                "SELECT DISTINCT ON (review_decision_id) * FROM "
                "workspace.project_candidate_review_decisions WHERE organization_id=:o AND "
                "workspace_id=:w ORDER BY review_decision_id,decision_version DESC"
            ),
            {"o": organization_id, "w": workspace_id},
        ).mappings()
        return [_jsonable_row(row) for row in rows]

    @staticmethod
    def _structure_dossier_rows(
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        work_packages: Iterable[Mapping[str, Any]] = (),
    ) -> list[dict[str, Any]]:
        """Expose source-scoped facility/area candidate dossiers without identity merging.

        A dossier is deliberately one extracted observation, not a canonical facility.
        Only relationships whose endpoint was resolved to this exact source-scoped node
        are included; same-name observations in other documents stay separate until a
        later reconciliation has adequate evidence.
        """
        work_observations_by_locator: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in work_packages:
            row = dict(item)
            package = row.get("package")
            package = package if isinstance(package, Mapping) else {}
            work_type = package.get("work_type")
            work_type = work_type if isinstance(work_type, Mapping) else {}
            observation = {
                "work_observation_id": str(
                    row.get("work_package_id") or package.get("work_package_id") or ""
                ),
                "work_name": str(work_type.get("raw") or work_type.get("normalized") or ""),
                "scope": str(package.get("scope") or "scope_not_specified"),
            }
            for locator_id in package.get("source_locator_ids") or ():
                work_observations_by_locator[str(locator_id)].append(observation)

        eligible_kinds = {"local_area", "facility", "excavation_pit", "structure", "zone"}
        rows: list[dict[str, Any]] = []
        for node in nodes:
            node_id = str(node["structure_node_id"])
            linked = [
                relationship
                for relationship in relationships
                if str(relationship.get("subject_structure_node_id") or "") == node_id
                or str(relationship.get("object_structure_node_id") or "") == node_id
            ]
            if str(node.get("node_kind")) not in eligible_kinds:
                continue
            source_locator_id = str(node["source_locator_id"])
            linked_work_observations = sorted(
                work_observations_by_locator.get(source_locator_id, []),
                key=lambda value: value["work_observation_id"],
            )
            rows.append(
                {
                    "candidate_state": "source_scoped_candidate",
                    "structure_node": node,
                    "relationships": linked,
                    "linked_work_observations": linked_work_observations,
                    "work_association_state": (
                        "exact_shared_source_locator_candidate"
                        if linked_work_observations
                        else "no_work_observation_at_exact_locator"
                    ),
                    "source_locator_ids": sorted(
                        {
                            source_locator_id,
                            *(
                                str(item["source_locator_id"])
                                for item in linked
                                if item.get("source_locator_id") is not None
                            ),
                        }
                    ),
                    "unresolved_relationship_count": sum(
                        1
                        for item in linked
                        if item.get("resolution_state") != "resolved_same_evidence"
                    ),
                }
            )
        return rows

    @staticmethod
    def _structure_component_rows(
        nodes: list[dict[str, Any]], relationships: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Expose only exact-evidence graph components without cross-source identity merges.

        A component is an aid for navigating observations already linked by an
        extracted relationship whose two endpoints were resolved in the same source
        evidence. It is never a canonical facility, and equal names in separate
        documents deliberately cannot join a component.
        """
        by_id = {str(node["structure_node_id"]): node for node in nodes}
        parent = {node_id: node_id for node_id in by_id}

        def find(node_id: str) -> str:
            while parent[node_id] != node_id:
                parent[node_id] = parent[parent[node_id]]
                node_id = parent[node_id]
            return node_id

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        resolved: list[dict[str, Any]] = []
        for relationship in relationships:
            if relationship.get("resolution_state") != "resolved_same_evidence":
                continue
            subject = str(relationship.get("subject_structure_node_id") or "")
            object_ = str(relationship.get("object_structure_node_id") or "")
            if subject not in by_id or object_ not in by_id:
                continue
            union(subject, object_)
            resolved.append(relationship)

        components: dict[str, list[str]] = {}
        for node_id in by_id:
            components.setdefault(find(node_id), []).append(node_id)
        rows: list[dict[str, Any]] = []
        for members in components.values():
            if len(members) < 2:
                continue
            member_set = set(members)
            component_relationships = [
                relationship
                for relationship in resolved
                if str(relationship.get("subject_structure_node_id")) in member_set
                and str(relationship.get("object_structure_node_id")) in member_set
            ]
            if not component_relationships:
                continue
            component_nodes = [by_id[node_id] for node_id in sorted(members)]
            locator_ids = sorted(
                {
                    *(
                        str(node["source_locator_id"])
                        for node in component_nodes
                        if node.get("source_locator_id") is not None
                    ),
                    *(
                        str(relationship["source_locator_id"])
                        for relationship in component_relationships
                        if relationship.get("source_locator_id") is not None
                    ),
                }
            )
            rows.append(
                {
                    "candidate_state": "exact_evidence_graph_component",
                    "component_key": semantic_digest(
                        {
                            "nodes": sorted(members),
                            "relationships": sorted(
                                str(item["relationship_candidate_id"])
                                for item in component_relationships
                            ),
                        }
                    ),
                    "nodes": component_nodes,
                    "relationships": component_relationships,
                    "source_locator_ids": locator_ids,
                }
            )
        return sorted(rows, key=lambda item: str(item["component_key"]))

    @staticmethod
    def _structure_identity_candidate_rows(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        current_result = session.scalar(
            sa.text(
                "SELECT receipt.result_manifest FROM workspace.durable_jobs job JOIN "
                "workspace.job_terminal_receipts receipt ON "
                "receipt.organization_id=job.organization_id AND "
                "receipt.workspace_id=job.workspace_id AND receipt.job_id=job.job_id WHERE "
                "job.organization_id=:o AND job.workspace_id=:w AND "
                "job.job_kind='PROJECT_STRUCTURE_RECONCILIATION' AND job.state='succeeded' AND "
                "receipt.result_manifest ? 'structure_identity_candidate_ids' "
                "ORDER BY job.completed_at DESC,job.job_id DESC LIMIT 1"
            ),
            {"o": organization_id, "w": workspace_id},
        )
        current_candidate_ids: list[UUID] | None = None
        if isinstance(current_result, Mapping):
            values = current_result.get("structure_identity_candidate_ids")
            if isinstance(values, list):
                current_candidate_ids = [UUID(str(value)) for value in values]
        current_predicate = (
            "AND identity_candidate_id=ANY(CAST(:candidate_ids AS uuid[])) "
            if current_candidate_ids is not None
            else ""
        )
        rows = (
            session.execute(
                sa.text(
                    "SELECT identity_candidate_id,version,identity_kind,canonical_label,"
                    "member_structure_node_ids,source_locator_ids,confidence,status,"
                    "reconciliation_profile_version,recorded_at FROM "
                    "workspace.project_structure_identity_candidates WHERE organization_id=:o "
                    f"AND workspace_id=:w {current_predicate}"
                    "ORDER BY recorded_at,identity_candidate_id,version"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    **(
                        {"candidate_ids": current_candidate_ids}
                        if current_candidate_ids is not None
                        else {}
                    ),
                },
            )
            .mappings()
            .all()
        )
        return [
            {**_jsonable_row(row), "candidate_state": "cross_source_identity_candidate"}
            for row in rows
        ]

    @classmethod
    def _empty_project_understanding_view(
        cls, session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        intake_summary = cls._intake_summary(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        tender_input_assessment = cls._tender_input_assessment(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        intake_summary["tender_input_assessment"] = tender_input_assessment
        candidates = cls._project_candidate_rows(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        structure_nodes = cls._project_structure_rows(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        structure_relationships = cls._project_structure_relationship_rows(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        structure_dossiers = cls._structure_dossier_rows(structure_nodes, structure_relationships)
        structure_components = cls._structure_component_rows(
            structure_nodes, structure_relationships
        )
        structure_identity_candidates = cls._structure_identity_candidate_rows(
            session, organization_id=organization_id, workspace_id=workspace_id
        )
        structure_identity_components = build_structure_identity_components(
            structure_identity_candidates
        )
        structure_identity_dossiers = build_structure_identity_dossiers(
            structure_identity_components,
            structure_nodes=structure_nodes,
            relationships=structure_relationships,
        )
        excavation_pit_inventory = build_excavation_pit_inventory(structure_nodes)
        return {
            "materialization": cls._project_understanding_materialization(
                session, organization_id=organization_id, workspace_id=workspace_id
            ),
            "reconciliation": {},
            "project_definition": {"definition": {"fields": {}, "gaps": []}},
            "page_roles": [],
            "work_packages": [],
            "matrix": {"matrix": {"rows": []}},
            "normative_profile": None,
            "defects": [],
            "evidence_index": cls._workspace_evidence_index(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                locator_ids=cls._response_locator_ids(
                    candidates,
                    structure_nodes,
                    structure_relationships,
                    structure_components,
                    structure_identity_candidates,
                    structure_identity_components,
                    structure_identity_dossiers,
                    tender_input_assessment,
                ),
            ),
            "candidates": candidates,
            "structure_nodes": structure_nodes,
            "structure_relationships": structure_relationships,
            "structure_dossiers": structure_dossiers,
            "structure_components": structure_components,
            "structure_identity_candidates": structure_identity_candidates,
            "structure_identity_components": structure_identity_components,
            "structure_identity_reconciliation": cls._structure_identity_reconciliation_status(
                session, organization_id=organization_id, workspace_id=workspace_id
            ),
            "structure_identity_dossiers": structure_identity_dossiers,
            "excavation_pit_inventory": excavation_pit_inventory,
            "facility_work_projection": {
                "candidate_groups": [],
                "coverage": {
                    "total_work_package_count": 0,
                    "exact_identity_package_count": 0,
                    "ambiguous_identity_package_count": 0,
                    "unassociated_package_count": 0,
                    "consolidated_candidate_group_count": 0,
                    "complete": False,
                    "candidate_authority": "candidate_only",
                    "association_rule": "exact_shared_source_locator",
                },
            },
            "review_decisions": cls._project_review_rows(
                session, organization_id=organization_id, workspace_id=workspace_id
            ),
            "intake_summary": intake_summary,
            "semantic_coverage": cls._semantic_extraction_coverage(
                session, organization_id=organization_id, workspace_id=workspace_id
            ),
            "authority_layers": {
                "workspace_fact": "project_definition_and_document_registry",
                "methodological_practice": "advisory_only",
                "normative_authority": "verified_subset_only",
                "customer_addition": "workspace_additive_only",
                "ai_candidate": "candidate_only",
            },
        }

    @staticmethod
    def _structure_identity_reconciliation_status(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        row = (
            session.execute(
                sa.text(
                    "SELECT j.job_id,j.state,j.attempt_count,j.typed_failure_code,j.started_at,"
                    "j.completed_at,progress.progress_current,progress.progress_total,"
                    "progress.safe_message_code progress_message_code,progress.recorded_at "
                    "progress_recorded_at FROM workspace.durable_jobs j LEFT JOIN LATERAL ("
                    "SELECT progress_current,progress_total,safe_message_code,recorded_at FROM "
                    "workspace.job_progress_events e WHERE e.organization_id=j.organization_id "
                    "AND e.workspace_id=j.workspace_id AND e.job_id=j.job_id ORDER BY "
                    "e.event_sequence DESC LIMIT 1) progress ON true WHERE "
                    "j.organization_id=:o AND j.workspace_id=:w AND "
                    "j.job_kind='PROJECT_STRUCTURE_RECONCILIATION' ORDER BY CASE "
                    "WHEN j.state IN ('running','leased') AND "
                    "COALESCE(j.lease_expires_at,CURRENT_TIMESTAMP)>CURRENT_TIMESTAMP THEN 0 "
                    "WHEN j.state='queued' THEN 1 WHEN j.state='paused' THEN 2 ELSE 3 END,"
                    "j.created_at DESC,j.job_id DESC LIMIT 1"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return {
                "state": "not_started",
                "progress_current": 0,
                "progress_total": 0,
                "candidate_authority": "candidate_only",
            }
        return {
            **_jsonable_row(row),
            "candidate_authority": "candidate_only",
        }

    @staticmethod
    def _semantic_extraction_coverage(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Expose accepted semantic fragments without treating them as reconciled facts."""
        rows = session.execute(
            sa.text(
                "WITH active_documents AS ("
                " SELECT DISTINCT ON (v.document_id) v.organization_id,v.workspace_id,v.document_id,"
                " v.version,v.source_version_id,v.safe_display_name FROM workspace.document_versions v JOIN "
                " workspace.document_version_activation_decisions a ON "
                " a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id AND "
                " a.document_id=v.document_id AND a.selected_document_version=v.version WHERE "
                " v.organization_id=:o AND v.workspace_id=:w AND NOT EXISTS (SELECT 1 FROM "
                " workspace.document_version_activation_decisions newer WHERE "
                " newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                " AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version) "
                " ORDER BY v.document_id,a.decision_version DESC"
                "), latest_elements AS ("
                " SELECT DISTINCT ON (source_locator_id) source_version_id,source_locator_id,"
                " evidence_digest,normalized_text FROM workspace.native_layout_element_versions "
                " WHERE organization_id=:o AND workspace_id=:w "
                " ORDER BY source_locator_id,version DESC"
                "), expected_fragments AS ("
                " SELECT source_version_id,source_locator_id::text source_locator_id,evidence_digest,"
                " offset_value character_start,LEAST(offset_value+2400,length(normalized_text)) "
                " character_end FROM latest_elements CROSS JOIN LATERAL "
                " generate_series(0,length(normalized_text)-1,2400) offset_value WHERE normalized_text<>''"
                "), expected AS ("
                " SELECT source_version_id,COUNT(*)::bigint AS expected_fragment_count "
                " FROM expected_fragments GROUP BY source_version_id"
                "), accepted_fragments AS ("
                " SELECT DISTINCT b.source_version_id,b.profile_version,fragment->>'fragment_id' "
                " AS fragment_id,COALESCE(fragment->>'source_locator_id',fragment->>'locator_id') "
                " source_locator_id,fragment->>'evidence_digest' evidence_digest,"
                " (fragment->>'character_start')::int character_start,"
                " (fragment->>'character_end')::int character_end "
                " FROM workspace.engineering_extraction_batches b "
                " CROSS JOIN LATERAL jsonb_array_elements(CASE "
                " WHEN jsonb_typeof(b.input_manifest)='array' THEN b.input_manifest "
                " ELSE COALESCE(b.input_manifest->'fragments','[]'::jsonb) END) AS fragment "
                " WHERE b.organization_id=:o AND b.workspace_id=:w "
                " AND b.terminal_status='accepted' AND b.input_manifest IS NOT NULL "
                "), accepted_batches AS ("
                " SELECT b.source_version_id,b.profile_version,COUNT(DISTINCT b.batch_digest) "
                " AS accepted_batch_count FROM workspace.engineering_extraction_batches b "
                " WHERE b.organization_id=:o AND b.workspace_id=:w AND b.terminal_status='accepted' "
                " AND b.input_manifest IS NOT NULL GROUP BY b.source_version_id,b.profile_version"
                "), accepted AS ("
                " SELECT fragments.source_version_id,fragments.profile_version,"
                " batches.accepted_batch_count,COUNT(*) AS accepted_fragment_count "
                " FROM accepted_fragments fragments JOIN accepted_batches batches "
                " ON batches.source_version_id=fragments.source_version_id AND "
                " batches.profile_version=fragments.profile_version GROUP BY "
                " fragments.source_version_id,fragments.profile_version,batches.accepted_batch_count"
                "), failed_fragments AS ("
                " SELECT DISTINCT b.source_version_id,b.profile_version,fragment->>'fragment_id' "
                " AS fragment_id FROM workspace.engineering_extraction_batches b "
                " CROSS JOIN LATERAL jsonb_array_elements(CASE "
                " WHEN jsonb_typeof(b.input_manifest)='array' THEN b.input_manifest "
                " ELSE COALESCE(b.input_manifest->'fragments','[]'::jsonb) END) AS fragment "
                " WHERE b.organization_id=:o AND b.workspace_id=:w "
                " AND b.terminal_status='failed' AND b.input_manifest IS NOT NULL "
                "), failed_batches AS ("
                " SELECT b.source_version_id,b.profile_version,COUNT(DISTINCT b.batch_digest) "
                " AS failed_batch_count FROM workspace.engineering_extraction_batches b "
                " WHERE b.organization_id=:o AND b.workspace_id=:w AND b.terminal_status='failed' "
                " AND b.input_manifest IS NOT NULL GROUP BY b.source_version_id,b.profile_version"
                "), failed AS ("
                " SELECT fragments.source_version_id,fragments.profile_version,"
                " batches.failed_batch_count,COUNT(*) AS failed_fragment_count "
                " FROM failed_fragments fragments JOIN failed_batches batches "
                " ON batches.source_version_id=fragments.source_version_id AND "
                " batches.profile_version=fragments.profile_version GROUP BY "
                " fragments.source_version_id,fragments.profile_version,batches.failed_batch_count"
                "), unresolved_failed AS ("
                " SELECT failed.source_version_id,failed.profile_version,COUNT(*) "
                " AS unresolved_failed_fragment_count FROM failed_fragments failed "
                " LEFT JOIN accepted_fragments accepted ON accepted.source_version_id=failed.source_version_id "
                " AND accepted.profile_version=failed.profile_version AND accepted.fragment_id=failed.fragment_id "
                " WHERE accepted.fragment_id IS NULL GROUP BY failed.source_version_id,failed.profile_version"
                "), latest_activity AS (SELECT DISTINCT ON (source_version_id) source_version_id,"
                " profile_version FROM workspace.engineering_extraction_batches WHERE "
                " organization_id=:o AND workspace_id=:w AND input_manifest IS NOT NULL "
                " ORDER BY source_version_id,recorded_at DESC,batch_ordinal DESC,batch_digest DESC"
                "), covered AS ("
                " SELECT expected.source_version_id,activity.profile_version,COUNT(*)::bigint "
                " AS covered_fragment_count FROM expected_fragments expected JOIN latest_activity "
                " activity USING(source_version_id) JOIN accepted_fragments accepted ON "
                " accepted.source_version_id=expected.source_version_id AND "
                " accepted.profile_version=activity.profile_version AND "
                " accepted.source_locator_id=expected.source_locator_id AND "
                " accepted.evidence_digest=expected.evidence_digest AND "
                " accepted.character_start=expected.character_start AND "
                " accepted.character_end=expected.character_end GROUP BY "
                " expected.source_version_id,activity.profile_version"
                ") SELECT v.source_version_id,COALESCE(activity.profile_version,'not_started') AS profile_version,"
                " COALESCE(a.accepted_batch_count,0) AS accepted_batch_count,"
                " COALESCE(a.accepted_fragment_count,0) AS accepted_fragment_count,"
                " COALESCE(f.failed_batch_count,0) AS failed_batch_count,"
                " COALESCE(f.failed_fragment_count,0) AS failed_fragment_count,"
                " COALESCE(u.unresolved_failed_fragment_count,0) AS unresolved_failed_fragment_count,"
                " COALESCE(e.expected_fragment_count,0) AS expected_fragment_count,"
                " COALESCE(covered.covered_fragment_count,0) AS covered_fragment_count,"
                " v.document_id,v.version AS document_version,v.safe_display_name,"
                " COALESCE(s.page_count,0) AS page_count,"
                " s.admission_status,s.extraction_status "
                " FROM active_documents v LEFT JOIN expected e ON e.source_version_id=v.source_version_id "
                " LEFT JOIN latest_activity activity ON activity.source_version_id=v.source_version_id "
                " LEFT JOIN accepted a ON a.source_version_id=v.source_version_id "
                " AND a.profile_version=activity.profile_version "
                " LEFT JOIN failed f ON f.source_version_id=v.source_version_id "
                " AND f.profile_version=activity.profile_version "
                " LEFT JOIN unresolved_failed u ON u.source_version_id=v.source_version_id "
                " AND u.profile_version=activity.profile_version "
                " LEFT JOIN covered ON covered.source_version_id=v.source_version_id "
                " AND covered.profile_version=activity.profile_version "
                " LEFT JOIN LATERAL (SELECT page_count,admission_status,extraction_status FROM "
                " workspace.document_processing_states state "
                " WHERE state.organization_id=v.organization_id AND state.workspace_id=v.workspace_id "
                " AND state.document_id=v.document_id AND state.document_version=v.version "
                " ORDER BY state.state_sequence DESC LIMIT 1) s ON TRUE "
                " ORDER BY v.safe_display_name,v.source_version_id"
            ),
            {"o": organization_id, "w": workspace_id},
        ).mappings()
        return [
            {
                "source_version_id": str(row["source_version_id"]),
                "document_id": str(row["document_id"]),
                "document_version": int(row["document_version"]),
                "safe_display_name": str(row["safe_display_name"]),
                "page_count": int(row["page_count"]),
                "admission_status": (
                    str(row["admission_status"])
                    if row["admission_status"] is not None
                    else "not_admitted"
                ),
                "extraction_status": (
                    str(row["extraction_status"])
                    if row["extraction_status"] is not None
                    else "not_started"
                ),
                "profile_version": str(row["profile_version"]),
                "accepted_batch_count": int(row["accepted_batch_count"]),
                "accepted_fragment_count": int(row["accepted_fragment_count"]),
                "failed_batch_count": int(row["failed_batch_count"]),
                "failed_fragment_count": int(row["failed_fragment_count"]),
                "unresolved_failed_fragment_count": int(row["unresolved_failed_fragment_count"]),
                "recovered_failed_fragment_count": max(
                    0,
                    int(row["failed_fragment_count"])
                    - int(row["unresolved_failed_fragment_count"]),
                ),
                "expected_fragment_count": int(row["expected_fragment_count"]),
                "covered_fragment_count": int(row["covered_fragment_count"]),
                "unresolved_fragment_count": max(
                    0,
                    int(row["expected_fragment_count"]) - int(row["covered_fragment_count"]),
                ),
                "state": SpinePostgresRepository._semantic_coverage_state(
                    covered_fragment_count=int(row["covered_fragment_count"]),
                    expected_fragment_count=int(row["expected_fragment_count"]),
                    unresolved_failed_fragment_count=int(row["unresolved_failed_fragment_count"]),
                ),
            }
            for row in rows
        ]

    @staticmethod
    def _semantic_coverage_state(
        *,
        covered_fragment_count: int,
        expected_fragment_count: int,
        unresolved_failed_fragment_count: int,
    ) -> str:
        if covered_fragment_count == 0:
            return "failed" if unresolved_failed_fragment_count else "not_started"
        return "complete" if covered_fragment_count == expected_fragment_count else "partial"

    @staticmethod
    def _project_structure_rows(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Return source-backed structural candidates before reconciliation materializes facts."""
        rows = session.execute(
            sa.text(
                "WITH active_sources AS (SELECT DISTINCT ON (v.document_id) v.source_version_id "
                "FROM workspace.document_versions v JOIN workspace.document_version_activation_decisions a "
                "ON a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
                "AND a.document_id=v.document_id AND a.selected_document_version=v.version "
                "WHERE v.organization_id=:organization AND v.workspace_id=:workspace AND NOT EXISTS "
                "(SELECT 1 FROM workspace.document_version_activation_decisions newer WHERE "
                "newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                "AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version) "
                "ORDER BY v.document_id,a.decision_version DESC), profile_receipts AS (SELECT "
                "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                "result.profile_version) AS semantic_profile,result.recorded_at,2 AS receipt_rank FROM "
                "workspace.project_understanding_stage_results result JOIN workspace.durable_jobs job ON "
                "job.organization_id=result.organization_id AND job.workspace_id=result.workspace_id AND "
                "job.job_id=result.job_id JOIN active_sources active ON active.source_version_id=result.source_version_id "
                "WHERE result.organization_id=:organization AND result.workspace_id=:workspace AND "
                "result.stage_kind='PROJECT_DEFINITION_EXTRACTION' AND result.terminal_status IN ('complete','partial') "
                "UNION ALL SELECT batch.source_version_id,batch.profile_version,batch.recorded_at,1 FROM "
                "workspace.engineering_extraction_batches batch JOIN active_sources active ON "
                "active.source_version_id=batch.source_version_id WHERE batch.organization_id=:organization "
                "AND batch.workspace_id=:workspace AND batch.terminal_status='accepted'), selected_profiles AS "
                "(SELECT DISTINCT ON (source_version_id) source_version_id,semantic_profile FROM profile_receipts "
                "ORDER BY source_version_id,recorded_at DESC,receipt_rank DESC) "
                "SELECT n.structure_node_id,n.version,n.node_kind,n.raw_name,n.normalized_name,n.parent_node_id,"
                "n.source_locator_id,n.status,n.extraction_profile_version,n.fingerprint FROM "
                "workspace.project_structure_node_versions n JOIN workspace.source_locators locator ON "
                "locator.organization_id=n.organization_id AND locator.workspace_id=n.workspace_id AND "
                "locator.source_locator_id=n.source_locator_id JOIN selected_profiles selected ON "
                "selected.source_version_id=locator.source_version_id WHERE n.organization_id=:organization "
                "AND n.workspace_id=:workspace AND n.extraction_profile_version=CASE WHEN "
                "selected.semantic_profile LIKE 'qwen-engineering-extraction-%' THEN selected.semantic_profile "
                "ELSE 'project-definition-extraction-v0.1' END ORDER BY n.recorded_at,n.structure_node_id,n.version"
            ),
            {"organization": organization_id, "workspace": workspace_id},
        ).mappings()
        return [_jsonable_row(row) for row in rows]

    @staticmethod
    def _project_structure_relationship_rows(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Return relationship observations with only source-scoped endpoint resolution.

        A raw normalized name is deliberately insufficient to connect entities across
        documents.  We expose an endpoint only when exactly one structural candidate
        with that name was extracted from the same evidence locator; all other links
        remain unresolved observations for cross-document reconciliation.
        """
        rows = session.execute(
            sa.text(
                "WITH active_sources AS (SELECT DISTINCT ON (v.document_id) v.source_version_id "
                "FROM workspace.document_versions v JOIN workspace.document_version_activation_decisions a "
                "ON a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
                "AND a.document_id=v.document_id AND a.selected_document_version=v.version "
                "WHERE v.organization_id=:organization AND v.workspace_id=:workspace AND NOT EXISTS "
                "(SELECT 1 FROM workspace.document_version_activation_decisions newer WHERE "
                "newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                "AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version) "
                "ORDER BY v.document_id,a.decision_version DESC), profile_receipts AS (SELECT "
                "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                "result.profile_version) AS semantic_profile,result.recorded_at,2 AS receipt_rank FROM "
                "workspace.project_understanding_stage_results result JOIN workspace.durable_jobs job ON "
                "job.organization_id=result.organization_id AND job.workspace_id=result.workspace_id AND "
                "job.job_id=result.job_id JOIN active_sources active ON active.source_version_id=result.source_version_id "
                "WHERE result.organization_id=:organization AND result.workspace_id=:workspace AND "
                "result.stage_kind='PROJECT_DEFINITION_EXTRACTION' AND result.terminal_status IN ('complete','partial') "
                "UNION ALL SELECT batch.source_version_id,batch.profile_version,batch.recorded_at,1 FROM "
                "workspace.engineering_extraction_batches batch JOIN active_sources active ON "
                "active.source_version_id=batch.source_version_id WHERE batch.organization_id=:organization "
                "AND batch.workspace_id=:workspace AND batch.terminal_status='accepted'), selected_profiles AS "
                "(SELECT DISTINCT ON (source_version_id) source_version_id,semantic_profile FROM profile_receipts "
                "ORDER BY source_version_id,recorded_at DESC,receipt_rank DESC) "
                "SELECT r.relationship_candidate_id,r.version,r.relationship_kind,r.subject_raw_name,"
                "r.subject_normalized_name,r.object_raw_name,r.object_normalized_name,r.source_version_id,"
                "r.source_locator_id,r.status,r.extraction_profile_version,r.candidate_digest,subject.node_id AS subject_structure_node_id,"
                "object.node_id AS object_structure_node_id,CASE WHEN subject.node_id IS NOT NULL "
                "AND object.node_id IS NOT NULL THEN 'resolved_same_evidence' ELSE "
                "'unresolved_source_scoped_identity' END AS resolution_state FROM "
                "workspace.project_structure_relationship_candidates r LEFT JOIN LATERAL (SELECT "
                "(array_agg(DISTINCT n.structure_node_id))[1] AS node_id FROM workspace.project_structure_node_versions n "
                "WHERE n.organization_id=r.organization_id AND n.workspace_id=r.workspace_id "
                "AND n.source_locator_id=r.source_locator_id AND n.normalized_name=r.subject_normalized_name "
                "AND n.extraction_profile_version=r.extraction_profile_version "
                "HAVING COUNT(DISTINCT n.structure_node_id)=1) subject ON true LEFT JOIN LATERAL "
                "(SELECT (array_agg(DISTINCT n.structure_node_id))[1] AS node_id FROM workspace.project_structure_node_versions n "
                "WHERE n.organization_id=r.organization_id AND n.workspace_id=r.workspace_id "
                "AND n.source_locator_id=r.source_locator_id AND n.normalized_name=r.object_normalized_name "
                "AND n.extraction_profile_version=r.extraction_profile_version "
                "HAVING COUNT(DISTINCT n.structure_node_id)=1) object ON true JOIN selected_profiles selected "
                "ON selected.source_version_id=r.source_version_id WHERE "
                "r.organization_id=:organization AND r.workspace_id=:workspace "
                "AND r.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE "
                "'project-definition-extraction-v0.1' END "
                "ORDER BY r.recorded_at,r.relationship_candidate_id,r.version"
            ),
            {"organization": organization_id, "workspace": workspace_id},
        ).mappings()
        return [_jsonable_row(row) for row in rows]

    @staticmethod
    def _workspace_evidence_index(
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        locator_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not locator_ids:
            return {}
        rows = session.execute(
            sa.text(
                "SELECT DISTINCT ON (sl.source_locator_id) sl.source_locator_id,"
                "sl.source_version_id,sl.locator_kind,sl.locator_value,sl.fragment_digest,"
                "v.document_id,v.version AS document_version,v.safe_display_name,e.raw_text "
                "FROM workspace.source_locators sl "
                "JOIN workspace.document_versions v ON v.organization_id=sl.organization_id AND "
                "v.workspace_id=sl.workspace_id AND v.source_version_id=sl.source_version_id "
                "LEFT JOIN workspace.native_layout_element_versions e ON "
                "e.organization_id=sl.organization_id AND e.workspace_id=sl.workspace_id AND "
                "e.source_locator_id=sl.source_locator_id WHERE "
                "sl.organization_id=:organization AND sl.workspace_id=:workspace "
                "AND sl.source_locator_id = ANY(CAST(:locator_ids AS uuid[])) ORDER BY "
                "sl.source_locator_id,v.version DESC,e.version DESC NULLS LAST"
            ),
            {
                "organization": organization_id,
                "workspace": workspace_id,
                "locator_ids": locator_ids,
            },
        ).mappings()
        return {str(row["source_locator_id"]): _jsonable_row(row) for row in rows}

    @classmethod
    def _response_locator_ids(cls, *values: Any) -> list[str]:
        locator_ids: set[str] = set()

        def collect(value: Any, key: str | None = None) -> None:
            if key == "source_locator_ids":
                for locator_id in value if isinstance(value, (list, tuple, set)) else ():
                    collect(locator_id, "source_locator_id")
                return
            if isinstance(value, Mapping):
                for item_key, item_value in value.items():
                    collect(item_value, str(item_key))
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    collect(item, key)
                return
            if key == "source_locator_id" and value is not None:
                locator_ids.add(str(value))

        for item in values:
            collect(item)
        return sorted(locator_ids)

    @staticmethod
    def _project_understanding_materialization(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        """Expose a truthful state when no reconciliation is materialized yet."""
        latest = (
            session.execute(
                sa.text(
                    "SELECT job_id,state,typed_failure_code,created_at FROM workspace.durable_jobs WHERE "
                    "organization_id=:organization AND workspace_id=:workspace AND "
                    "job_kind='PROJECT_UNDERSTANDING_RECONCILIATION' ORDER BY created_at DESC,job_id DESC "
                    "LIMIT 1"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            )
            .mappings()
            .one_or_none()
        )
        role_count = int(
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.document_role_decisions WHERE "
                    "organization_id=:organization AND workspace_id=:workspace"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            )
            or 0
        )
        candidate_count = int(
            session.scalar(
                sa.text(
                    "SELECT (SELECT count(*) FROM workspace.project_field_candidates WHERE "
                    "organization_id=:organization AND workspace_id=:workspace) + "
                    "(SELECT count(*) FROM workspace.work_type_candidates WHERE "
                    "organization_id=:organization AND workspace_id=:workspace) + "
                    "(SELECT count(*) FROM workspace.quantity_candidates WHERE "
                    "organization_id=:organization AND workspace_id=:workspace) + "
                    "(SELECT count(*) FROM workspace.material_candidates WHERE "
                    "organization_id=:organization AND workspace_id=:workspace)"
                ),
                {"organization": organization_id, "workspace": workspace_id},
            )
            or 0
        )
        if latest is None:
            state = "partial" if role_count or candidate_count else "not_requested"
            return {
                "state": state,
                "role_decision_count": role_count,
                "candidate_count": candidate_count,
                "gaps": [],
            }
        job_state = str(latest["state"])
        if job_state == "queued":
            state = "queued"
        elif job_state in {"leased", "running"}:
            state = "running"
        else:
            state = "blocked"
        return {
            "state": state,
            "job_id": str(latest["job_id"]),
            "job_state": job_state,
            "failure_code": latest["typed_failure_code"],
            "role_decision_count": role_count,
            "candidate_count": candidate_count,
            "gaps": [],
        }

    def platform_knowledge_status(self) -> KnowledgeStatus:
        with self._engine.connect() as connection:
            value = connection.scalar(sa.text("SELECT application.get_platform_knowledge_status()"))
            conflict_status = connection.scalar(
                sa.text("SELECT application.get_platform_practice_conflict_status()")
            )
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
            ntd_inventory = (
                connection.execute(
                    sa.text(
                        "SELECT count(*) total_documents,"
                        "count(*) FILTER (WHERE authority_class='official') official_documents,"
                        "count(*) FILTER (WHERE authority_class='legacy_reference') reference_documents,"
                        "count(*) FILTER (WHERE bytes_status='present') bytes_present,"
                        "count(*) FILTER (WHERE search_status='searchable') searchable,"
                        "count(*) FILTER (WHERE search_status='partially_searchable') partially_searchable,"
                        "count(*) FILTER (WHERE authority_class='official' AND search_status IN "
                        "('searchable','partially_searchable')) searchable_official_documents,"
                        "count(*) FILTER (WHERE authority_class='legacy_reference' AND search_status IN "
                        "('searchable','partially_searchable')) searchable_reference_documents,"
                        "count(*) FILTER (WHERE structure_status IN ('structured','verified_provisions')) structured_editions,"
                        "sum(verified_provision_count) verified_provisions,"
                        "count(*) FILTER (WHERE text_status='none') documents_without_text,"
                        "count(*) FILTER (WHERE edition_currency_status='not_checked') edition_currency_unchecked "
                        "FROM platform.ntd_search_documents"
                    )
                )
                .mappings()
                .one()
            )
            ntd_identity_denominator = int(
                connection.scalar(
                    sa.text(
                        "SELECT coalesce(max(identity_count),0) FROM platform.ntd_seed_manifests"
                    )
                )
                or 0
            )
        if not isinstance(value, dict):
            raise SpinePersistenceError("platform_knowledge_status_unavailable")
        if not isinstance(conflict_status, dict):
            raise SpinePersistenceError("platform_practice_conflict_status_unavailable")
        value = dict(value)
        ntd_inventory_value = {key: int(item or 0) for key, item in ntd_inventory.items()}
        ntd_inventory_value["absent_identities"] = max(
            0,
            ntd_identity_denominator - ntd_inventory_value["official_documents"],
        )
        ntd_inventory_value["identity_denominator"] = ntd_identity_denominator
        value["conflict_count"] = int(conflict_status["conflict_count"])
        value["quarantine_count"] = int(conflict_status["quarantine_count"])
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
            ntd_inventory_value,
            dict(value["projection_states"]),
            backup_at,
            dict(value["semantic_fingerprints"]),
            bool(value["memory_data_defect"]),
            bool(value["knowledge_ready"]),
            tuple(str(item) for item in value["blockers"]),
        )

    def ntd_seed_status(self) -> dict[str, Any]:
        """Return exact-25 status and bounded verified provision evidence."""

        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        "WITH latest AS (SELECT DISTINCT ON (identity_resolution_id) * FROM "
                        "platform.ntd_identity_resolution_versions ORDER BY identity_resolution_id,"
                        "version DESC) SELECT i.identity_reconciliation_id,"
                        "i.canonical_stable_identity_key,i.printed_designations,i.identity_status,"
                        "l.provider,l.resolution_status,l.failure_code,l.official_record_url,"
                        "l.official_record_digest,l.diagnostic,l.normative_document_id,"
                        "l.normative_edition_id,l.normative_artifact_ids,d.designation,d.title,"
                        "e.edition_label,a.normative_artifact_id,a.official_url,a.content_digest,"
                        "a.media_type,a.size_bytes FROM "
                        "platform.ntd_seed_identity_reconciliations i LEFT JOIN latest l ON "
                        "l.identity_reconciliation_id=i.identity_reconciliation_id LEFT JOIN "
                        "platform.normative_documents d ON d.normative_document_id=l.normative_document_id "
                        "LEFT JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=l.normative_edition_id LEFT JOIN LATERAL "
                        "unnest(l.normative_artifact_ids) artifact_id ON true LEFT JOIN "
                        "platform.normative_artifacts a ON a.normative_artifact_id=artifact_id "
                        "ORDER BY i.canonical_stable_identity_key,"
                        "l.provider,a.normative_artifact_id"
                    )
                )
                .mappings()
                .all()
            )
            metrics = {
                UUID(str(row["normative_artifact_id"])): dict(row)
                for row in connection.execute(
                    sa.text(
                        "WITH latest_pages AS (SELECT DISTINCT ON (normative_page_id) * FROM "
                        "platform.normative_representation_pages ORDER BY normative_page_id,"
                        "version DESC) SELECT p.normative_artifact_id,"
                        "count(DISTINCT p.normative_page_id) page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE p.extraction_route='native') native_page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE p.extraction_route='polza_candidate') polza_routed_page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE p.extraction_route='blocked') blocked_page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE p.terminal_outcome='recovery_complete') recovered_page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE p.terminal_outcome='native_complete') native_complete_page_count,"
                        "count(DISTINCT p.normative_page_id) FILTER "
                        "(WHERE x.status='candidate') external_candidate_page_count FROM latest_pages p "
                        "LEFT JOIN platform.ntd_external_extraction_receipts x ON "
                        "x.normative_page_id=p.normative_page_id AND x.normative_page_version=p.version "
                        "GROUP BY p.normative_artifact_id"
                    )
                ).mappings()
            }
            provision_counts = {
                UUID(str(row["normative_edition_id"])): int(row["verified_count"])
                for row in connection.execute(
                    sa.text(
                        "SELECT normative_edition_id,count(*) FILTER (WHERE verification_status='verified') "
                        "verified_count FROM platform.normative_provision_versions "
                        "GROUP BY normative_edition_id"
                    )
                ).mappings()
            }
            provision_details: dict[UUID, list[dict[str, Any]]] = {}
            for provision_row in connection.execute(
                sa.text(
                    "WITH latest_alignments AS (SELECT DISTINCT ON (alignment_id) * FROM "
                    "platform.practice_ntd_alignments ORDER BY alignment_id,version DESC),"
                    "bounded AS (SELECT value.*,row_number() OVER (PARTITION BY "
                    "normative_edition_id ORDER BY structural_path,normative_provision_id,version) "
                    "evidence_ordinal FROM platform.normative_provision_versions value WHERE "
                    "verification_status='verified'),selected AS (SELECT p.* FROM bounded p "
                    "WHERE p.evidence_ordinal<=20 OR EXISTS (SELECT 1 FROM latest_alignments a "
                    "WHERE a.normative_edition_id=p.normative_edition_id AND "
                    "a.normative_provision_id=p.normative_provision_id AND "
                    "a.normative_provision_version=p.version) OR EXISTS (SELECT 1 FROM "
                    "platform.normative_rule_candidates candidate WHERE "
                    "candidate.normative_provision_id=p.normative_provision_id AND "
                    "candidate.normative_provision_version=p.version)) SELECT p.normative_edition_id,"
                    "p.normative_provision_id,p.version,"
                    "p.source_version_id,p.structural_path,p.page_number,p.verbatim_text,"
                    "p.content_digest,p.verification_decision_ref,COALESCE((SELECT status FROM "
                    "platform.normative_activation_decisions activation WHERE "
                    "activation.selected_edition_id=p.normative_edition_id ORDER BY "
                    "activation.as_of DESC,activation.version DESC LIMIT 1),'not_activated') "
                    "edition_activation_status,COALESCE((SELECT jsonb_agg(jsonb_build_object("
                    "'rule_candidate_id',candidate.normative_rule_candidate_id,"
                    "'candidate_version',candidate.version,'deontic_type',candidate.deontic_type,"
                    "'qualification_status',COALESCE(qualification.status,'not_qualified'),"
                    "'qualification_gates',COALESCE(qualification.gate_results,'[]'::jsonb),"
                    "'activation_status',COALESCE(outcome.status,'not_activated'),"
                    "'activation_reason',COALESCE(outcome.reason_code,'RULE_ACTIVATION_NOT_DECIDED'),"
                    "'rule_version_id',outcome.rule_version_id,"
                    "'rule_lifecycle_status',outcome.rule_lifecycle_status) ORDER BY "
                    "candidate.normative_rule_candidate_id,candidate.version) FROM "
                    "platform.normative_rule_candidates candidate LEFT JOIN LATERAL (SELECT q.* FROM "
                    "platform.normative_rule_qualification_decisions q WHERE "
                    "q.normative_rule_candidate_id=candidate.normative_rule_candidate_id AND "
                    "q.normative_rule_candidate_version=candidate.version ORDER BY q.decided_at DESC,"
                    "q.version DESC LIMIT 1) qualification ON true LEFT JOIN LATERAL (SELECT o.* FROM "
                    "platform.normative_rule_activation_outcomes o WHERE "
                    "o.normative_rule_candidate_id=candidate.normative_rule_candidate_id AND "
                    "o.normative_rule_candidate_version=candidate.version ORDER BY o.decided_at DESC,"
                    "o.version DESC LIMIT 1) outcome ON true WHERE "
                    "candidate.normative_provision_id=p.normative_provision_id AND "
                    "candidate.normative_provision_version=p.version),'[]'::jsonb) rules,"
                    "COALESCE((SELECT jsonb_agg(jsonb_build_object("
                    "'alignment_id',alignment.alignment_id,'version',alignment.version,"
                    "'status',alignment.alignment_status,'practice_guide_reference_id',"
                    "alignment.practice_guide_reference_id,'guidance_unit_id',"
                    "alignment.guidance_unit_id,'guidance_unit_version',"
                    "alignment.guidance_unit_version,'evidence_refs',alignment.evidence_refs,"
                    "'decision_ref',alignment.decision_ref) ORDER BY alignment.alignment_id,"
                    "alignment.version) FROM latest_alignments alignment WHERE "
                    "alignment.normative_provision_id=p.normative_provision_id AND "
                    "alignment.normative_provision_version=p.version),'[]'::jsonb) alignments,"
                    "jsonb_agg(jsonb_build_object("
                    "'source_locator_id',sl.source_locator_id,'page',"
                    "(sl.locator_value->>'page')::integer,'region',sl.locator_value->'region',"
                    "'fragment_digest',sl.fragment_digest) ORDER BY ids.ordinality) locators FROM "
                    "selected p JOIN "
                    "platform.normative_structural_fragments sf ON "
                    "sf.structural_unit_id=p.structural_unit_id AND "
                    "sf.source_version_id=p.source_version_id CROSS JOIN LATERAL "
                    "unnest(sf.source_locator_ids) WITH ORDINALITY ids(locator_id,ordinality) JOIN "
                    "platform.source_locators sl ON sl.source_locator_id=ids.locator_id GROUP BY "
                    "p.normative_edition_id,"
                    "p.normative_provision_id,p.version,p.source_version_id,p.structural_path,"
                    "p.page_number,p.verbatim_text,p.content_digest,p.verification_decision_ref "
                    "ORDER BY p.normative_edition_id,p.structural_path,p.normative_provision_id,"
                    "p.version"
                )
            ).mappings():
                edition_id = UUID(str(provision_row["normative_edition_id"]))
                provision_details.setdefault(edition_id, []).append(
                    {
                        "provision_id": str(provision_row["normative_provision_id"]),
                        "version": int(provision_row["version"]),
                        "source_version_id": str(provision_row["source_version_id"]),
                        "structural_path": str(provision_row["structural_path"]),
                        "page_number": int(provision_row["page_number"]),
                        "locators": list(provision_row["locators"]),
                        "verbatim_text": str(provision_row["verbatim_text"]),
                        "content_digest": str(provision_row["content_digest"]),
                        "verification_decision_ref": str(
                            provision_row["verification_decision_ref"]
                        ),
                        "edition_activation_status": str(
                            provision_row["edition_activation_status"]
                        ),
                        "rules": list(provision_row["rules"]),
                        "alignments": list(provision_row["alignments"]),
                    }
                )
            alignment_counts = {
                UUID(str(row["normative_document_id"])): int(row["alignment_count"])
                for row in connection.execute(
                    sa.text(
                        "WITH latest AS (SELECT DISTINCT ON (alignment_id) * FROM "
                        "platform.practice_ntd_alignments ORDER BY alignment_id,version DESC) "
                        "SELECT normative_document_id,count(*) alignment_count FROM latest "
                        "WHERE normative_document_id IS NOT NULL GROUP BY normative_document_id"
                    )
                ).mappings()
            }
            rule_counts = {
                UUID(str(row["normative_edition_id"])): int(row["rule_count"])
                for row in connection.execute(
                    sa.text(
                        "SELECT candidate.normative_edition_id,count(DISTINCT "
                        "qualification.normative_rule_candidate_id) FILTER (WHERE "
                        "qualification.status='qualified') rule_count FROM "
                        "platform.normative_rule_candidates candidate LEFT JOIN "
                        "platform.normative_rule_qualification_decisions qualification ON "
                        "qualification.normative_rule_candidate_id="
                        "candidate.normative_rule_candidate_id AND "
                        "qualification.normative_rule_candidate_version=candidate.version "
                        "GROUP BY candidate.normative_edition_id"
                    )
                ).mappings()
            }
            rule_summary = dict(
                connection.execute(
                    sa.text(
                        "SELECT (SELECT count(*) FROM platform.normative_rule_candidates) "
                        "rule_candidates,(SELECT count(*) FROM "
                        "platform.normative_rule_qualification_decisions WHERE status='qualified') "
                        "qualified_rules,(SELECT count(*) FROM (SELECT DISTINCT ON "
                        "(normative_rule_candidate_id,normative_rule_candidate_version) status FROM "
                        "platform.normative_rule_activation_outcomes ORDER BY "
                        "normative_rule_candidate_id,normative_rule_candidate_version,decided_at DESC,"
                        "version DESC) latest WHERE status='active') active_rules,(SELECT count(*) "
                        "FROM (SELECT DISTINCT ON (normative_rule_candidate_id,"
                        "normative_rule_candidate_version) status FROM "
                        "platform.normative_rule_activation_outcomes ORDER BY "
                        "normative_rule_candidate_id,normative_rule_candidate_version,decided_at DESC,"
                        "version DESC) latest WHERE status='not_activated') qualified_not_active"
                    )
                )
                .mappings()
                .one()
            )
        grouped: dict[UUID, dict[str, Any]] = {}
        for row in rows:
            identity_id = UUID(str(row["identity_reconciliation_id"]))
            item = grouped.setdefault(
                identity_id,
                {
                    "stable_identity": str(row["canonical_stable_identity_key"]),
                    "printed_designations": list(row["printed_designations"]),
                    "identity_status": str(row["identity_status"]),
                    "resolutions": [],
                    "artifacts": [],
                },
            )
            if row["provider"] is not None and not any(
                value["provider"] == str(row["provider"]) for value in item["resolutions"]
            ):
                item["resolutions"].append(
                    {
                        "provider": str(row["provider"]),
                        "status": str(row["resolution_status"]),
                        "failure_code": str(row["failure_code"])
                        if row["failure_code"] is not None
                        else None,
                        "official_record_url": str(row["official_record_url"])
                        if row["official_record_url"] is not None
                        else None,
                        "official_record_digest": str(row["official_record_digest"])
                        if row["official_record_digest"] is not None
                        else None,
                        "observations": list(dict(row["diagnostic"]).get("observations", [])),
                    }
                )
            if row["normative_artifact_id"] is None:
                continue
            artifact_id = UUID(str(row["normative_artifact_id"]))
            if any(value["artifact_id"] == str(artifact_id) for value in item["artifacts"]):
                continue
            metric = metrics.get(artifact_id, {})
            edition_id = UUID(str(row["normative_edition_id"]))
            document_id = UUID(str(row["normative_document_id"]))
            item["artifacts"].append(
                {
                    "artifact_id": str(artifact_id),
                    "document_id": str(document_id),
                    "edition_id": str(edition_id),
                    "designation": str(row["designation"]),
                    "title": str(row["title"]),
                    "edition_label": str(row["edition_label"]),
                    "official_url": str(row["official_url"]),
                    "content_digest": str(row["content_digest"]),
                    "media_type": str(row["media_type"]),
                    "size_bytes": int(row["size_bytes"]),
                    "page_count": int(metric.get("page_count", 0)),
                    "native_page_count": int(metric.get("native_page_count", 0)),
                    "polza_routed_page_count": int(metric.get("polza_routed_page_count", 0)),
                    "blocked_page_count": int(metric.get("blocked_page_count", 0)),
                    "native_complete_page_count": int(metric.get("native_complete_page_count", 0)),
                    "recovered_page_count": int(metric.get("recovered_page_count", 0)),
                    "external_candidate_page_count": int(
                        metric.get("external_candidate_page_count", 0)
                    ),
                    "verified_provision_count": provision_counts.get(edition_id, 0),
                    "practice_alignment_count": alignment_counts.get(document_id, 0),
                    "qualified_rule_count": rule_counts.get(edition_id, 0),
                    "verified_provisions": provision_details.get(edition_id, []),
                }
            )
        items = sorted(grouped.values(), key=lambda value: value["stable_identity"])
        counts = {
            "denominator": 25,
            "registered_identity_count": len(items),
            "official_record_resolved": sum(
                any(value["official_record_url"] for value in item["resolutions"]) for item in items
            ),
            "artifact_downloaded": sum(bool(item["artifacts"]) for item in items),
            "provisions_verified": sum(
                sum(value["verified_provision_count"] for value in item["artifacts"])
                for item in items
            ),
            "alignments": sum(
                sum(value["practice_alignment_count"] for value in item["artifacts"])
                for item in items
            ),
            "qualified_rules": sum(
                sum(value["qualified_rule_count"] for value in item["artifacts"]) for item in items
            ),
            "rule_candidates": int(rule_summary["rule_candidates"]),
            "active_rules": int(rule_summary["active_rules"]),
            "qualified_not_active": int(rule_summary["qualified_not_active"]),
        }
        return {
            "schema_version": "ntd-seed-status-v2",
            "logical_manifest_fingerprint": (
                "sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6"
            ),
            "counts": counts,
            "identities": items,
            "complete": counts["registered_identity_count"] == counts["denominator"]
            and counts["artifact_downloaded"] == counts["denominator"]
            and counts["provisions_verified"] > 0,
        }

    def get_ntd_artifact_object(self, artifact_id: UUID) -> dict[str, Any]:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT a.normative_artifact_id,a.filename,a.media_type,a.size_bytes,"
                        "a.content_digest,o.object_id FROM platform.normative_artifacts a JOIN "
                        "platform.source_versions sv ON sv.source_version_id=a.source_version_id "
                        "JOIN platform.objects o ON o.object_id=sv.object_id AND "
                        "o.object_version=sv.object_version WHERE a.normative_artifact_id=:artifact"
                    ),
                    {"artifact": artifact_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SpinePersistenceError("ntd_artifact_not_found")
        return {
            "artifact_id": UUID(str(row["normative_artifact_id"])),
            "filename": str(row["filename"]),
            "media_type": str(row["media_type"]),
            "size_bytes": int(row["size_bytes"]),
            "content_digest": str(row["content_digest"]),
            "object_key": f"platform/source/{row['object_id']}",
        }

    def get_platform_source_object(self, source_version_id: UUID) -> dict[str, Any]:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT sv.source_version_id,sv.content_digest,o.object_id,o.size_bytes,"
                        "o.media_type,a.title FROM platform.source_versions sv JOIN platform.objects o "
                        "ON o.object_id=sv.object_id AND o.object_version=sv.object_version JOIN "
                        "platform.source_artifacts a ON a.source_artifact_id=sv.source_artifact_id "
                        "WHERE sv.source_version_id=:source"
                    ),
                    {"source": source_version_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SpinePersistenceError("platform_source_not_found")
        return {
            "source_version_id": UUID(str(row["source_version_id"])),
            "filename": f"{str(row['title']).strip() or 'source'}.pdf",
            "media_type": str(row["media_type"]),
            "size_bytes": int(row["size_bytes"]),
            "content_digest": str(row["content_digest"]),
            "object_key": f"platform/source/{row['object_id']}",
        }

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
        row.lease_expires_at,
        bool(getattr(row, "lease_expired", False)),
        int(row.progress_current) if getattr(row, "progress_current", None) is not None else None,
        int(row.progress_total) if getattr(row, "progress_total", None) is not None else None,
        (
            str(row.progress_message_code)
            if getattr(row, "progress_message_code", None) is not None
            else None
        ),
        getattr(row, "progress_recorded_at", None),
    )


def _json(value: object) -> str:
    import json

    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _jsonable_row(row: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(row).items():
        if isinstance(value, UUID):
            result[str(key)] = str(value)
        elif isinstance(value, (datetime, date)):
            result[str(key)] = value.isoformat()
        elif isinstance(value, tuple):
            result[str(key)] = [str(item) if isinstance(item, UUID) else item for item in value]
        elif isinstance(value, list):
            result[str(key)] = [str(item) if isinstance(item, UUID) else item for item in value]
        else:
            result[str(key)] = value
    return result
