"""Application service for four pilot results and their immutable exports."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.support.production_postgres import SupportProductionRepository

from .builder import build_pilot_result
from .models import (
    MODE_EXPORTS,
    PilotExportFormat,
    PilotExportKind,
    PilotMode,
    PilotReviewAction,
)
from .postgres import PilotResultError, PilotResultRepository
from .render import content_digest, render_export, render_workspace_archive


@dataclass(frozen=True, slots=True)
class PilotContent:
    media_type: str
    size_bytes: int
    content_digest: str
    safe_display_name: str
    offset: int
    length: int
    chunks: Iterable[bytes]


class PilotResultService:
    def __init__(
        self,
        repository: SpinePostgresRepository,
        object_store: WorkspaceObjectStore,
        *,
        chunk_bytes: int,
    ) -> None:
        self._spine = repository
        self._repository = PilotResultRepository(repository.engine)
        self._support = SupportProductionRepository(repository.engine)
        self._objects = object_store
        self._chunk_bytes = chunk_bytes

    def form_result(
        self, *, owner_identity_id: str, workspace_id: UUID, mode: PilotMode
    ) -> dict[str, Any]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        workspace = self._spine.get_workspace(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        project = self._spine.project_understanding_view(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        if project is None or not project.get("reconciliation"):
            raise PilotResultError("pilot_project_model_required")
        documents = self._all_documents(owner_identity_id, workspace_id)
        support = self._support.view(owner_identity_id=owner_identity_id, workspace_id=workspace_id)
        result = build_pilot_result(
            workspace_id=workspace_id,
            workspace_name=workspace.display_name,
            mode=mode,
            project=project,
            documents=documents,
            support=support,
        )
        self._repository.put_result(
            organization_id=organization_id,
            workspace_id=workspace_id,
            result=result,
            owner_identity_id=owner_identity_id,
        )
        value = self._repository.latest_result(
            organization_id=organization_id, workspace_id=workspace_id, mode=mode
        )
        if value is None:
            raise PilotResultError("pilot_result_not_found")
        return value

    def get_result(
        self, *, owner_identity_id: str, workspace_id: UUID, mode: PilotMode
    ) -> dict[str, Any] | None:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.latest_result(
            organization_id=organization_id, workspace_id=workspace_id, mode=mode
        )

    def review_item(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: PilotMode,
        item_id: UUID,
        action: PilotReviewAction,
        resolved_fields: dict[str, Any] | None,
        comment: str,
    ) -> dict[str, Any]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        if len(comment.strip()) < 3:
            raise PilotResultError("pilot_review_comment_required")
        return self._repository.review_item(
            organization_id=organization_id,
            workspace_id=workspace_id,
            mode=mode,
            item_id=item_id,
            action=action,
            resolved_fields=resolved_fields,
            comment=comment,
            owner_identity_id=owner_identity_id,
        )

    def create_export(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        mode: PilotMode,
        kind: PilotExportKind,
        output_format: PilotExportFormat,
    ) -> dict[str, Any]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        result = self._repository.latest_result(
            organization_id=organization_id, workspace_id=workspace_id, mode=mode
        )
        if result is None:
            raise PilotResultError("pilot_result_not_found")
        if kind is not PilotExportKind.WORKSPACE_RESULTS and kind not in MODE_EXPORTS[mode]:
            raise PilotResultError("pilot_export_kind_not_available_for_mode")
        _require_contract_analysis(result=result, mode=mode, kind=kind)
        additional = self._support_files(organization_id, workspace_id)
        if kind is PilotExportKind.WORKSPACE_RESULTS:
            if output_format is not PilotExportFormat.ZIP:
                raise PilotResultError("pilot_workspace_export_requires_zip")
            all_results = self._repository.latest_results(
                organization_id=organization_id, workspace_id=workspace_id
            )
            if len(all_results) != len(PilotMode):
                raise PilotResultError("pilot_all_mode_results_required")
            content = render_workspace_archive(results=all_results, additional_files=additional)
        else:
            if output_format is PilotExportFormat.ZIP and kind not in {
                PilotExportKind.ID_PACKAGE,
                PilotExportKind.RECOVERED_DRAFTS,
            }:
                raise PilotResultError("pilot_export_format_not_available")
            content = render_export(
                result=result,
                kind=kind,
                output_format=output_format,
                additional_files=additional if output_format is PilotExportFormat.ZIP else (),
            )
        digest = content_digest(content)
        object_key = (
            f"derived/{organization_id}/{workspace_id}/pilot/"
            f"{kind.value}/{output_format.value}/{digest[7:]}"
        )
        stored_digest, size = self._objects.put_derived(object_key=object_key, content=content)
        media_type = _media_type(output_format)
        return self._repository.record_export(
            organization_id=organization_id,
            workspace_id=workspace_id,
            result=result,
            kind=kind,
            output_format=output_format,
            object_key=object_key,
            media_type=media_type,
            size_bytes=size,
            content_digest=stored_digest,
            owner_identity_id=owner_identity_id,
        )

    def export_content(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        export_id: UUID,
        byte_range: tuple[int, int] | None = None,
    ) -> PilotContent:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        artifact = self._repository.export_object(
            organization_id=organization_id,
            workspace_id=workspace_id,
            export_id=export_id,
        )
        size = int(artifact["size_bytes"])
        if byte_range is None:
            offset, end = 0, size - 1
        else:
            offset, end = byte_range
            if offset < 0 or end < offset or end >= size:
                raise PilotResultError("pilot_export_range_not_satisfiable")
        length = end - offset + 1

        def chunks() -> Iterator[bytes]:
            with self._objects.open(str(artifact["object_key"])) as source:
                source.seek(offset)
                remaining = length
                while remaining and (chunk := source.read(min(self._chunk_bytes, remaining))):
                    remaining -= len(chunk)
                    yield chunk

        extension = str(artifact["output_format"])
        return PilotContent(
            str(artifact["media_type"]),
            size,
            str(artifact["content_digest"]),
            f"asd-kontur-{artifact['export_kind']}-v{artifact['version']}.{extension}",
            offset,
            length,
            chunks(),
        )

    def _all_documents(self, owner_identity_id: str, workspace_id: UUID) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page, cursor = self._spine.list_documents(
                owner_identity_id=owner_identity_id,
                workspace_id=workspace_id,
                limit=100,
                cursor=cursor,
                media_type=None,
                status=None,
                sort="recorded_asc",
            )
            documents.extend(asdict(item) for item in page)
            if cursor is None:
                break
        return documents

    def _support_files(
        self, organization_id: UUID, workspace_id: UUID
    ) -> tuple[tuple[str, bytes], ...]:
        files = []
        for ordinal, item in enumerate(
            self._repository.finalized_support_objects(
                organization_id=organization_id, workspace_id=workspace_id
            ),
            start=1,
        ):
            with self._objects.open(str(item["object_key"])) as source:
                content = source.read()
            suffix = "pdf" if str(item["output_format"]).lower().startswith("pdf") else "docx"
            files.append((f"support/finalized-document-{ordinal}.{suffix}", content))
        return tuple(files)


def _require_contract_analysis(
    *, result: dict[str, Any], mode: PilotMode, kind: PilotExportKind
) -> None:
    """Reject contractual drafts when the result proves their input is absent.

    Tender design findings remain exportable without a contract.  A protocol of
    disagreements or contract amendments, however, needs the actual current
    contract terms; a DOCX title must not turn an unavailable input into a
    contractual conclusion.
    """

    if mode is not PilotMode.TENDER or kind not in {
        PilotExportKind.DISAGREEMENT_PROTOCOL,
        PilotExportKind.CONTRACT_CHANGES,
    }:
        return
    kinds = {str(item.get("kind")) for item in result.get("items") or []}
    if "contract_input_unavailable" in kinds:
        raise PilotResultError("pilot_contract_input_required")
    if "contract_analysis_pending" in kinds:
        raise PilotResultError("pilot_contract_analysis_required")


def _media_type(value: PilotExportFormat) -> str:
    return {
        PilotExportFormat.PDF: "application/pdf",
        PilotExportFormat.DOCX: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        PilotExportFormat.ZIP: "application/zip",
    }[value]
