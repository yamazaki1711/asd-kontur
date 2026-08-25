"""Transport-independent application commands and queries for the Product Spine."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import UUID

from asd_kontur.lifecycle import LifecycleState, PostgresLifecycleRepository
from asd_kontur.persistence.scope import WorkspaceContext

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

    def list_jobs(self, *, owner_identity_id: str, workspace_id: UUID) -> tuple[JobSummary, ...]:
        return self._repository.list_jobs(
            owner_identity_id=owner_identity_id,
            workspace_id=workspace_id,
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

    @staticmethod
    def capability_status() -> dict[str, Any]:
        return {
            "contract_version": "2.1.0",
            "slice": "PRODUCT-APPLICATION-SPINE-01",
            "implemented": [
                "application.http_api",
                "application.owner_authentication",
                "application.workspace_selector",
                "intake.streamed_upload",
                "jobs.postgresql_durable_engine",
                "interaction.document_registry",
                "interaction.pdf_evidence_viewer",
                "interaction.four_mode_shell",
                "interaction.platform_knowledge_status",
            ],
            "blockers": [
                "MEMORY_DATA_DEFECT",
                "OFFICIAL_NTD_VERIFIED_EDITION_COUNT_ZERO",
                "RULE_VERSION_COUNT_ZERO",
                "MODEL_BROKER_NOT_IN_SPINE_SLICE",
                "SCALE_THRESHOLDS_UNSET",
            ],
            "trial_ready": False,
            "oks_ready": False,
            "product_ready": False,
        }


def _manifest_ordinal(item: dict[str, object]) -> int:
    value = item["ordinal"]
    if not isinstance(value, int):
        raise ValueError("manifest_ordinal_invalid")
    return value
