"""Transport-independent application commands and queries for the Product Spine."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.audit.package_preflight import build_expected_actual_preflight
from asd_kontur.audit.preflight_export import render_expected_actual_preflight_csv
from asd_kontur.audit.report_export import render_audit_report_projection_csv
from asd_kontur.lifecycle import LifecycleState, PostgresLifecycleRepository
from asd_kontur.persistence.scope import WorkspaceContext
from asd_kontur.pilot import (
    PilotExportFormat,
    PilotExportKind,
    PilotMode,
    PilotResultService,
    PilotReviewAction,
)
from asd_kontur.pilot.readiness import TrialReadinessRepository
from asd_kontur.pilot.service import PilotContent
from asd_kontur.restoration import (
    RestorationRecoveryRepository,
    build_recovery_plan,
    render_recovery_plan_csv,
)
from asd_kontur.support.package_export import build_editable_id_package_archive
from asd_kontur.support.production_postgres import SupportProductionRepository
from asd_kontur.tender.analysis_package import build_tender_analysis_archive
from asd_kontur.tender.contract_analysis_view import TenderContractAnalysisRepository
from asd_kontur.tender.coverage_schedule import render_tender_document_coverage_csv
from asd_kontur.tender.facility_scope_schedule import render_tender_facility_scope_schedule_csv
from asd_kontur.tender.findings_report import render_tender_findings_docx
from asd_kontur.tender.findings_schedule import render_tender_findings_csv
from asd_kontur.tender.scope_schedule import render_tender_scope_schedule_csv
from asd_kontur.tender.structure_identity_schedule import (
    render_tender_structure_identity_schedule_csv,
)

from .config import SpineSettings
from .models import (
    BatchRegistration,
    DocumentSummary,
    EvidencePanel,
    JobProgress,
    JobSummary,
    KnowledgeStatus,
    ModeName,
    ModeWorkspaceView,
    WorkspaceSummary,
    semantic_digest,
)
from .object_store import IntakeError, StagedObject, WorkspaceObjectStore
from .postgres import RejectedUpload, SpinePostgresRepository


@dataclass(frozen=True, slots=True)
class UploadPart:
    ordinal: int
    original_name: str
    relative_path: str | None
    client_media_type: str | None
    client_size_bytes: int | None
    client_digest: str | None
    stream: BinaryIO


@dataclass(frozen=True, slots=True)
class DocumentContent:
    media_type: str
    size_bytes: int
    content_digest: str
    safe_display_name: str
    offset: int
    length: int
    chunks: Iterable[bytes]


MODE_PURPOSES: dict[ModeName, str] = {
    ModeName.TENDER: "Evidence-bound tender completeness, feasibility and risk analysis.",
    ModeName.SUPPORT: "Work control, evidence and executive-document readiness support.",
    ModeName.AUDIT: "Expected-versus-actual construction document audit.",
    ModeName.RESTORATION: "Evidence-constrained recovery planning without fabrication.",
}

MODE_REQUIRED_CAPABILITIES: dict[ModeName, tuple[str, ...]] = {
    ModeName.TENDER: (
        "PROJECT_UNDERSTANDING_REAL_DOCUMENTS",
        "VERIFIED_NTD_SUBSET",
        "QUALIFIED_RULE_VERSIONS",
        "PRODUCTION_CONTRACT_OUTPUT",
    ),
    ModeName.SUPPORT: (
        "FIELD_FACT_CAPTURE",
        "VERIFIED_NTD_SUBSET",
        "QUALIFIED_RULE_VERSIONS",
        "PRODUCTION_ID_GENERATION",
    ),
    ModeName.AUDIT: (
        "INDUSTRIAL_SCAN_CLASSIFICATION",
        "VERIFIED_NTD_SUBSET",
        "QUALIFIED_RULE_VERSIONS",
        "PRODUCTION_AUDIT_REPORT",
    ),
    ModeName.RESTORATION: (
        "DEDICATED_RESTORATION_WORKFLOW",
        "FIELD_EVIDENCE_SUFFICIENCY",
        "VERIFIED_NTD_SUBSET",
        "PRODUCTION_DOCUMENT_REGENERATION",
    ),
}


class ProductSpineService:
    def __init__(
        self,
        repository: SpinePostgresRepository,
        lifecycle_repository: PostgresLifecycleRepository,
        object_store: WorkspaceObjectStore,
        settings: SpineSettings,
    ) -> None:
        self._repository = repository
        self._lifecycle = lifecycle_repository
        self._object_store = object_store
        self._settings = settings
        self._support_production = SupportProductionRepository(repository.engine)
        self._tender_contract_analysis = TenderContractAnalysisRepository(repository.engine)
        self._restoration_recovery = RestorationRecoveryRepository(repository.engine)
        self._pilot = PilotResultService(
            repository,
            object_store,
            chunk_bytes=settings.upload_chunk_bytes,
        )
        self._trial_readiness = TrialReadinessRepository(repository.engine)

    def create_workspace(
        self,
        *,
        owner_identity_id: str,
        display_name: str,
        correlation_id: UUID,
    ) -> WorkspaceSummary:
        normalized = " ".join(display_name.split())
        if not 3 <= len(normalized) <= 200:
            raise ValueError("workspace_display_name_invalid")
        workspace = self._repository.create_workspace(
            owner_identity_id=owner_identity_id,
            display_name=normalized,
            correlation_id=correlation_id,
        )
        operation_key = f"spine.workspace.activate:{workspace.workspace_id}"
        self._lifecycle.transition(
            context=WorkspaceContext(
                workspace.organization_id,
                workspace.workspace_id,
                owner_identity_id,
                "service.product-spine-api-v0.1",
                correlation_id,
            ),
            expected_version=1,
            target_state=LifecycleState.ACTIVE,
            operation_key=operation_key,
            semantic_digest=semantic_digest(
                {"workspace_id": workspace.workspace_id, "target": "ACTIVE"}
            ),
            authority_reference="application.owner.workspace-provision-v0.1",
        )
        return self._repository.get_workspace(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace.workspace_id,
        )

    def list_workspaces(self, *, owner_identity_id: str) -> tuple[WorkspaceSummary, ...]:
        return self._repository.list_workspaces(owner_identity_id=owner_identity_id)

    def register_uploads(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        parts: tuple[UploadPart, ...],
        correlation_id: UUID,
    ) -> BatchRegistration:
        if not parts or len(parts) > self._settings.max_batch_files:
            raise ValueError("batch_file_count_limit_exceeded")
        ordinals = [part.ordinal for part in parts]
        if any(value < 1 for value in ordinals) or len(set(ordinals)) != len(ordinals):
            raise ValueError("batch_item_ordinal_invalid")
        organization_id = self._repository.resolve_scope(owner_identity_id, workspace_id)
        staged: list[tuple[int, StagedObject]] = []
        archive_members: list[tuple[int, int, int]] = []
        rejected: list[RejectedUpload] = []
        observed_bytes = 0
        manifest_items: list[dict[str, object]] = []
        try:
            for part in sorted(parts, key=lambda item: item.ordinal):
                try:
                    item = self._object_store.stage(
                        stream=part.stream,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        original_name=part.original_name,
                        relative_path=part.relative_path,
                        client_media_type=part.client_media_type,
                    )
                except IntakeError as exc:
                    rejected.append(
                        RejectedUpload(
                            part.ordinal,
                            f"rejected-upload-{part.ordinal}",
                            f"rejected/upload-{part.ordinal}",
                            part.client_media_type,
                            part.client_size_bytes,
                            part.client_digest,
                            exc.code,
                        )
                    )
                    manifest_items.append(
                        {
                            "ordinal": part.ordinal,
                            "outcome": "rejected",
                            "reason_code": exc.code,
                        }
                    )
                    continue
                observed_bytes += item.size_bytes
                if observed_bytes > self._settings.max_batch_bytes:
                    self._object_store.abort(item)
                    raise ValueError("batch_size_limit_exceeded")
                staged.append((part.ordinal, item))
                manifest_items.append(
                    {
                        "ordinal": part.ordinal,
                        "relative_path": item.relative_path,
                        "media_type": item.media_type,
                        "size_bytes": item.size_bytes,
                        "digest": item.digest,
                    }
                )
                if item.media_type == "application/zip":
                    expanded = self._object_store.expand_archive(
                        item,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        max_members=self._settings.max_batch_files - len(parts),
                        max_total_bytes=self._settings.max_batch_bytes - observed_bytes,
                    )
                    for member_ordinal, member in enumerate(expanded, start=1):
                        expanded_ordinal = len(parts) + len(archive_members) + 1
                        archive_members.append((part.ordinal, member_ordinal, expanded_ordinal))
                        staged.append((expanded_ordinal, member))
                        observed_bytes += member.size_bytes
                        manifest_items.append(
                            {
                                "ordinal": expanded_ordinal,
                                "archive_parent_ordinal": part.ordinal,
                                "archive_member_ordinal": member_ordinal,
                                "relative_path": member.relative_path,
                                "media_type": member.media_type,
                                "size_bytes": member.size_bytes,
                                "digest": member.digest,
                            }
                        )
                if len(staged) > self._settings.max_batch_files:
                    raise ValueError("batch_file_count_limit_exceeded")
                if observed_bytes > self._settings.max_batch_bytes:
                    raise ValueError("batch_size_limit_exceeded")
            manifest_digest = semantic_digest(
                {
                    "workspace_id": workspace_id,
                    "items": sorted(manifest_items, key=_manifest_ordinal),
                }
            )
            return self._repository.register_batch(
                owner_identity_id=owner_identity_id,
                workspace_id=workspace_id,
                staged_items=tuple(staged),
                rejected_items=tuple(rejected),
                object_store=self._object_store,
                correlation_id=correlation_id,
                client_manifest_digest=manifest_digest,
                archive_members=tuple(archive_members),
            )
        except BaseException:
            for _, item in staged:
                self._object_store.abort(item)
            raise

    def list_documents(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        limit: int,
        cursor: str | None,
        media_type: str | None,
        status: str | None,
        sort: str,
    ) -> tuple[tuple[DocumentSummary, ...], str | None]:
        return self._repository.list_documents(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
            media_type=media_type,
            status=status,
            sort=sort,
        )

    def document_content(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        document_id: UUID,
        byte_range: tuple[int, int] | None = None,
    ) -> DocumentContent:
        document = self._repository.get_document(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            document_id=document_id,
        )
        object_key = self._repository.get_document_object_key(
            organization_id=document.organization_id,
            workspace_id=workspace_id,
            document_id=document_id,
            document_version=document.version,
        )

        if byte_range is None:
            offset, end = 0, document.size_bytes - 1
        else:
            offset, end = byte_range
            if offset < 0 or end < offset or end >= document.size_bytes:
                raise ValueError("document_range_not_satisfiable")
        length = end - offset + 1

        def chunks() -> Iterator[bytes]:
            with self._object_store.open(object_key) as source:
                source.seek(offset)
                remaining = length
                while remaining and (
                    chunk := source.read(min(self._settings.upload_chunk_bytes, remaining))
                ):
                    remaining -= len(chunk)
                    yield chunk

        return DocumentContent(
            document.media_type,
            document.size_bytes,
            document.content_digest,
            document.safe_display_name,
            offset,
            length,
            chunks(),
        )

    def evidence(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        document_id: UUID,
        page_number: int,
    ) -> EvidencePanel:
        if page_number < 1:
            raise ValueError("page_number_invalid")
        return self._repository.get_document_page_evidence(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            document_id=document_id,
            page_number=page_number,
        )

    def exact_evidence(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        source_locator_id: UUID,
    ) -> EvidencePanel:
        return self._repository.get_exact_evidence_locator(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            source_locator_id=source_locator_id,
        )

    def list_jobs(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        effective_only: bool = False,
    ) -> tuple[JobSummary, ...]:
        return self._repository.list_jobs(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            effective_only=effective_only,
        )

    def progress_events(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        after_sequence: int,
    ) -> tuple[JobProgress, ...]:
        return self._repository.list_progress_events(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            after_sequence=after_sequence,
        )

    def cancel_job(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        job_id: UUID,
    ) -> None:
        self._repository.request_cancellation(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
            reason_code="owner_requested",
        )

    def pause_job(self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID) -> JobSummary:
        return self._repository.pause_job(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
        )

    def resume_job(self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID) -> JobSummary:
        return self._repository.resume_job(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
        )

    def retry_job(self, *, owner_identity_id: str, workspace_id: UUID, job_id: UUID) -> JobSummary:
        return self._repository.manually_retry_job(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
        )

    def mode_view(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: ModeName,
    ) -> ModeWorkspaceView:
        matrix, execution = self._repository.latest_matrix_and_mode_execution(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            mode=mode.value,
        )
        inputs = ("workspace_documents",)
        gaps = list(MODE_REQUIRED_CAPABILITIES[mode])
        if matrix is None:
            gaps.insert(0, "WORK_REQUIREMENT_MATRIX_UNAVAILABLE")
        bounded: dict[str, Any] = {}
        matrix_id: UUID | None = None
        if matrix is not None:
            matrix_id = UUID(str(matrix["matrix_id"]))
            bounded = {
                "matrix_version": int(matrix["version"]),
                "matrix_fingerprint": str(matrix["fingerprint"]),
            }
        return ModeWorkspaceView(
            mode,
            MODE_PURPOSES[mode],
            inputs,
            UUID(str(execution["mode_execution_id"])) if execution else None,
            str(execution["state"]) if execution else None,
            matrix_id,
            bounded,
            tuple(gaps),
            tuple(gaps),
            "PARTIAL" if matrix is not None else "FOUNDATION_ONLY",
        )

    def knowledge_status(self) -> KnowledgeStatus:
        return self._repository.platform_knowledge_status()

    def ntd_seed_status(self) -> dict[str, Any]:
        return self._repository.ntd_seed_status()

    def ntd_artifact_content(
        self, *, artifact_id: UUID, byte_range: tuple[int, int] | None = None
    ) -> DocumentContent:
        artifact = self._repository.get_ntd_artifact_object(artifact_id)
        size = int(artifact["size_bytes"])
        if byte_range is None:
            offset, end = 0, size - 1
        else:
            offset, end = byte_range
            if offset < 0 or end < offset or end >= size:
                raise ValueError("ntd_artifact_range_not_satisfiable")
        length = end - offset + 1

        def chunks() -> Iterator[bytes]:
            with self._object_store.open(str(artifact["object_key"])) as source:
                source.seek(offset)
                remaining = length
                while remaining and (
                    chunk := source.read(min(self._settings.upload_chunk_bytes, remaining))
                ):
                    remaining -= len(chunk)
                    yield chunk

        return DocumentContent(
            str(artifact["media_type"]),
            size,
            str(artifact["content_digest"]),
            str(artifact["filename"]),
            offset,
            length,
            chunks(),
        )

    def platform_source_content(
        self, *, source_version_id: UUID, byte_range: tuple[int, int] | None = None
    ) -> DocumentContent:
        artifact = self._repository.get_platform_source_object(source_version_id)
        size = int(artifact["size_bytes"])
        if byte_range is None:
            offset, end = 0, size - 1
        else:
            offset, end = byte_range
            if offset < 0 or end < offset or end >= size:
                raise ValueError("platform_source_range_not_satisfiable")
        length = end - offset + 1

        def chunks() -> Iterator[bytes]:
            with self._object_store.open(str(artifact["object_key"])) as source:
                source.seek(offset)
                remaining = length
                while remaining and (
                    chunk := source.read(min(self._settings.upload_chunk_bytes, remaining))
                ):
                    remaining -= len(chunk)
                    yield chunk

        return DocumentContent(
            str(artifact["media_type"]),
            size,
            str(artifact["content_digest"]),
            str(artifact["filename"]),
            offset,
            length,
            chunks(),
        )

    def tender_contract_analysis(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        return self._tender_contract_analysis.latest(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )

    def project_understanding(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any] | None:
        return self._repository.project_understanding_view(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
        )

    def tender_findings_schedule(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return an editable candidate finding schedule for the current model."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_findings_csv(
            view.get("defects", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
            evidence_index=view.get("evidence_index", {}),
            work_packages=view.get("work_packages", []),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"tender-findings-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def tender_findings_report(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return an editable candidate report for the current Tender findings."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_findings_docx(
            view.get("defects", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
            evidence_index=view.get("evidence_index", {}),
            work_packages=view.get("work_packages", []),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            len(data),
            digest,
            f"tender-findings-{workspace_id}.docx",
            0,
            len(data),
            (data,),
        )

    def tender_scope_schedule(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return an editable work/quantity/material candidate schedule."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_scope_schedule_csv(
            view.get("work_packages", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
            evidence_index=view.get("evidence_index", {}),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"tender-scope-schedule-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def tender_document_coverage_schedule(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return an editable active-source coverage schedule for Tender users."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_document_coverage_csv(
            view.get("semantic_coverage", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"tender-document-coverage-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def tender_structure_identity_schedule(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return an editable candidate schedule of cross-document identities."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_structure_identity_schedule_csv(
            view.get("structure_identity_candidates", []),
            structure_nodes=view.get("structure_nodes", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
            evidence_index=view.get("evidence_index", {}),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"tender-structure-identity-candidates-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def tender_facility_scope_schedule(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Return a locator-bound work-to-facility candidate schedule."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = view.get("materialization", {})
        data = render_tender_facility_scope_schedule_csv(
            view.get("work_packages", []),
            identity_candidates=view.get("structure_identity_candidates", []),
            materialization_state=str(materialization.get("state", "not_requested")),
            coverage_gaps=materialization.get("gaps", []),
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"tender-facility-work-observations-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def tender_analysis_export(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Export the current Tender report and schedules as one editable archive."""

        view = self.project_understanding(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if view is None:
            raise ValueError("project_understanding_no_result")
        materialization = dict(view.get("materialization") or {})
        common = {
            "materialization_state": str(materialization.get("state", "not_requested")),
            "coverage_gaps": materialization.get("gaps", []),
            "evidence_index": view.get("evidence_index", {}),
        }
        data = build_tender_analysis_archive(
            findings_report=render_tender_findings_docx(
                view.get("defects", []),
                work_packages=view.get("work_packages", []),
                **common,
            ),
            findings_schedule=render_tender_findings_csv(
                view.get("defects", []),
                work_packages=view.get("work_packages", []),
                **common,
            ),
            scope_schedule=render_tender_scope_schedule_csv(
                view.get("work_packages", []),
                **common,
            ),
            structure_identity_schedule=render_tender_structure_identity_schedule_csv(
                view.get("structure_identity_candidates", []),
                structure_nodes=view.get("structure_nodes", []),
                **common,
            ),
            facility_scope_schedule=render_tender_facility_scope_schedule_csv(
                view.get("work_packages", []),
                identity_candidates=view.get("structure_identity_candidates", []),
                materialization_state=common["materialization_state"],
                coverage_gaps=common["coverage_gaps"],
            ),
            document_coverage_schedule=render_tender_document_coverage_csv(
                view.get("semantic_coverage", []),
                materialization_state=common["materialization_state"],
                coverage_gaps=common["coverage_gaps"],
            ),
            materialization=materialization,
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "application/zip",
            len(data),
            digest,
            f"tender-analysis-{workspace_id}.zip",
            0,
            len(data),
            (data,),
        )

    def start_project_understanding(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        correlation_id: UUID,
    ) -> JobSummary:
        return self._repository.start_project_understanding(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            correlation_id=correlation_id,
        )

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
        return self._repository.review_project_candidate(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            candidate_kind=candidate_kind,
            candidate_id=candidate_id,
            candidate_version=candidate_version,
            action=action,
            resolved_value=resolved_value,
            reason=reason,
        )

    def support_production_view(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        return self._support_production.view(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )

    def audit_expected_actual_preflight(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Expose the package-composition preflight without impersonating Audit.

        Canonical Audit records have their own service role and immutable
        lifecycle.  This workspace-owner read model is intentionally limited to
        the same matrix and package data the owner can already inspect.
        """

        support = self.support_production_view(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        return build_expected_actual_preflight(
            support.get("requirements", ()),
            matrix=support.get("matrix"),
            package=support.get("package"),
            memberships=support.get("memberships", ()),
        )

    def audit_expected_actual_preflight_export(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        preflight = self.audit_expected_actual_preflight(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        data = render_expected_actual_preflight_csv(preflight)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"audit-expected-actual-preflight-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def latest_audit_report_projection(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Expose the immutable canonical-Audit read model without impersonation."""

        return self._repository.latest_audit_report_projection(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )

    def audit_report_projection_export(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Export the immutable Audit read projection without changing the report."""

        projection = self.latest_audit_report_projection(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        data = render_audit_report_projection_csv(projection)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"audit-report-projection-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def restoration_recovery_plan(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Return an evidence-constrained recovery plan for the workspace."""

        preflight = self.audit_expected_actual_preflight(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        plan = build_recovery_plan(preflight)
        snapshot = self._restoration_recovery.latest(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        return {
            **plan,
            "snapshot": snapshot,
            "snapshot_is_current": (
                None if snapshot is None else snapshot["plan_fingerprint"] == semantic_digest(plan)
            ),
        }

    def capture_restoration_recovery_plan(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Persist the exact current recovery assessment without changing evidence."""

        preflight = self.audit_expected_actual_preflight(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        plan = build_recovery_plan(preflight)
        snapshot = self._restoration_recovery.capture(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            plan=plan,
        )
        return {
            **plan,
            "snapshot": snapshot,
            "snapshot_is_current": True,
            "snapshot_duplicate": bool(snapshot["duplicate"]),
        }

    def restoration_recovery_plan_export(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Export the current non-fabricating Restoration plan as editable CSV."""

        plan = self.restoration_recovery_plan(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        data = render_recovery_plan_csv(plan)
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "text/csv; charset=utf-8",
            len(data),
            digest,
            f"restoration-recovery-plan-{workspace_id}.csv",
            0,
            len(data),
            (data,),
        )

    def form_support_id_package(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        work_package_id: UUID,
    ) -> dict[str, Any]:
        return self._support_production.form_package(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            work_package_id=work_package_id,
        )

    def support_id_package_export(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> DocumentContent:
        """Deliver the exact formed ID package with an editable register first."""

        view = self.support_production_view(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        package = view.get("package")
        registers = view.get("registers", [])
        if not isinstance(package, dict) or not registers:
            raise ValueError("id_package_not_formed")
        latest_register = registers[-1]
        if not isinstance(latest_register, dict) or not isinstance(
            latest_register.get("register_manifest"), dict
        ):
            raise ValueError("id_package_register_unavailable")

        def read_object(object_key: str) -> bytes:
            with self._object_store.open(object_key) as source:
                return source.read()

        data = build_editable_id_package_archive(
            package=package,
            register_manifest=latest_register["register_manifest"],
            memberships=view.get("memberships", []),
            field_resolutions=view.get("field_resolutions", []),
            read_object=read_object,
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return DocumentContent(
            "application/zip",
            len(data),
            digest,
            f"id-package-{workspace_id}-v{package.get('version')}.zip",
            0,
            len(data),
            (data,),
        )

    def start_support_generation(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        membership_id: UUID,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        return self._support_production.start_generation(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            membership_id=membership_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def support_candidate_content(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_id: UUID,
        byte_range: tuple[int, int] | None = None,
    ) -> DocumentContent:
        candidate = self._support_production.candidate_object(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            candidate_id=candidate_id,
        )
        return self._support_output_content(
            artifact=candidate,
            identity=candidate_id,
            kind="generated-candidate",
            byte_range=byte_range,
        )

    def review_support_candidate(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_id: UUID,
        outcome: str,
    ) -> dict[str, Any]:
        return self._support_production.review_candidate(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            candidate_id=candidate_id,
            outcome=outcome,
        )

    def finalize_support_candidate(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate_id: UUID,
    ) -> dict[str, Any]:
        return self._support_production.finalize_candidate(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            candidate_id=candidate_id,
        )

    def support_finalized_content(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        finalized_id: UUID,
        byte_range: tuple[int, int] | None = None,
    ) -> DocumentContent:
        artifact = self._support_production.finalized_object(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            finalized_id=finalized_id,
        )
        return self._support_output_content(
            artifact=artifact,
            identity=finalized_id,
            kind="finalized-document",
            byte_range=byte_range,
        )

    def record_support_package_backup_manifest(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> dict[str, Any]:
        return self._support_production.record_package_backup_manifest(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
        )

    def form_pilot_result(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: ModeName,
    ) -> dict[str, Any]:
        return self._pilot.form_result(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            mode=PilotMode(mode.value),
        )

    def pilot_result(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: ModeName,
    ) -> dict[str, Any] | None:
        return self._pilot.get_result(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            mode=PilotMode(mode.value),
        )

    def review_pilot_result_item(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: ModeName,
        item_id: UUID,
        action: PilotReviewAction,
        resolved_fields: dict[str, Any] | None,
        comment: str,
    ) -> dict[str, Any]:
        return self._pilot.review_item(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            mode=PilotMode(mode.value),
            item_id=item_id,
            action=action,
            resolved_fields=resolved_fields,
            comment=comment,
        )

    def create_pilot_export(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: ModeName,
        kind: PilotExportKind,
        output_format: PilotExportFormat,
    ) -> dict[str, Any]:
        return self._pilot.create_export(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            mode=PilotMode(mode.value),
            kind=kind,
            output_format=output_format,
        )

    def pilot_export_content(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        export_id: UUID,
        byte_range: tuple[int, int] | None = None,
    ) -> PilotContent:
        return self._pilot.export_content(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
            export_id=export_id,
            byte_range=byte_range,
        )

    def _support_output_content(
        self,
        *,
        artifact: dict[str, str],
        identity: UUID,
        kind: str,
        byte_range: tuple[int, int] | None,
    ) -> DocumentContent:
        with self._object_store.open(artifact["object_key"]) as source:
            source.seek(0, 2)
            size = source.tell()
        if byte_range is None:
            offset, end = 0, size - 1
        else:
            offset, end = byte_range
            if offset < 0 or end < offset or end >= size:
                raise ValueError("generated_candidate_range_not_satisfiable")
        length = end - offset + 1

        def chunks() -> Iterator[bytes]:
            with self._object_store.open(artifact["object_key"]) as source:
                source.seek(offset)
                remaining = length
                while remaining and (
                    chunk := source.read(min(self._settings.upload_chunk_bytes, remaining))
                ):
                    remaining -= len(chunk)
                    yield chunk

        output_format = artifact["format"]
        media_type = (
            "application/pdf"
            if output_format in {"PDF", "PDF_OVERLAY"}
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        extension = "pdf" if output_format in {"PDF", "PDF_OVERLAY"} else "docx"
        return DocumentContent(
            media_type,
            size,
            artifact["content_digest"],
            f"{kind}-{identity}.{extension}",
            offset,
            length,
            chunks(),
        )

    def capability_status(self) -> dict[str, Any]:
        latest_decision = self._trial_readiness.latest()
        decision = (
            latest_decision
            if latest_decision is not None
            and latest_decision["deployed_commit"] == self._settings.release_commit
            else None
        )
        blockers = (
            list(decision["user_blockers"])
            if decision is not None
            else ["PILOT_ACCEPTANCE_NOT_RECORDED"]
        )
        with self._repository.engine.connect() as connection:
            consultant_quality = (
                connection.execute(
                    sa.text(
                        "SELECT status,source_commit FROM "
                        "application.construction_consultant_quality_decisions "
                        "ORDER BY recorded_at DESC,version DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
        consultant_quality_ready = bool(
            consultant_quality
            and consultant_quality["status"] == "quality_ready"
            and consultant_quality["source_commit"] == self._settings.release_commit
        )
        return {
            "contract_version": "2.8.0",
            "slice": "PROFESSIONAL-ASSISTANT-REASONING-01",
            "implemented": [
                "interaction.frontend-shell",
                "interaction.workspace-selector",
                "interaction.four-mode-navigation",
                "interaction.document-registry",
                "interaction.gaps-conflicts-blockers",
                "interaction.work-requirement-matrix-ui",
                "interaction.generation-export-ui",
                "application.http-api",
                "application.authentication",
                "application.session-handling",
                "application.durable-job-orchestration",
                "intake.batch-upload",
                "intake.recursive-folder-admission",
                "intake.streamed-hashing",
                "intake.mime-content-validation",
                "intake.deduplication",
                "intake.archive-handling",
                "intake.pdf-page-inventory",
                "intake.native-extraction",
                "intake.ocr",
                "intake.sharding",
                "intake.backpressure",
                "intake.crash-recovery",
                "intake.quarantine",
                "intake.scale-1k",
                "intake.scale-5k",
                "intake.scale-10k",
                "project-understanding.pz-identification",
                "project-understanding.pd-rd-classification",
                "project-understanding.project-definition",
                "project-understanding.oks-structure",
                "project-understanding.spatial-structure",
                "project-understanding.work-types",
                "project-understanding.work-dependencies",
                "project-understanding.quantities",
                "project-understanding.materials",
                "project-understanding.vor-estimate-reconciliation",
                "project-understanding.work-packages",
                "project-understanding.requirement-matrix",
                "operations.document-worker",
                "support.id-matrix",
                "output.template-registry",
                "output.docx",
                "output.generated-document-candidate",
                "pilot.tender-professional-result",
                "pilot.support-professional-result",
                "pilot.audit-professional-result",
                "pilot.restoration-professional-result",
                "pilot.reviewed-result-version",
                "pilot.docx-pdf-zip-exports",
                "pilot.trial-readiness-decision",
                "assistant.workspace-scoped-conversations",
                "assistant.local-qwen-streaming",
                "assistant.knowledge-gateway-context",
                "assistant.multi-step-reasoning",
                "assistant.granular-knowledge-tools",
                "assistant.response-quality-gate",
            ],
            "blockers": sorted(blockers),
            "trial_ready": bool(decision and decision["status"] == "trial_ready"),
            "construction_consultant_quality_ready": consultant_quality_ready,
            "domain_harness_ready": False,
            "oks_ready": False,
            "product_ready": False,
            "deployment": {
                "source_commit": self._settings.release_commit,
                "runtime_profile": self._settings.release_profile,
                "deployed_at": self._settings.deployed_at,
                "frontend_build_digest": self._settings.frontend_build_digest,
                "openapi_digest": self._settings.openapi_digest,
                "migration_head": self._settings.expected_migration_head,
            },
        }

    def record_trial_readiness(
        self,
        *,
        owner_identity_id: str,
        criteria: dict[str, bool],
        pilot_thresholds: dict[str, Any],
        external_receipts: list[dict[str, Any]],
        user_blockers: list[str],
        rollback_target: str,
    ) -> dict[str, Any]:
        if len(self._settings.release_commit) != 40:
            raise ValueError("trial_readiness_requires_pinned_release")
        return self._trial_readiness.record(
            deployed_commit=self._settings.release_commit,
            criteria=criteria,
            pilot_thresholds=pilot_thresholds,
            external_receipts=external_receipts,
            user_blockers=user_blockers,
            rollback_target=rollback_target,
            owner_identity_id=owner_identity_id,
        )

    def trial_readiness(self) -> dict[str, Any] | None:
        return self._trial_readiness.latest()


def _manifest_ordinal(item: dict[str, object]) -> int:
    value = item["ordinal"]
    if not isinstance(value, int):
        raise ValueError("manifest_ordinal_invalid")
    return value
