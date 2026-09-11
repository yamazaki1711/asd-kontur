# ruff: noqa: E501
"""Bounded PostgreSQL document worker for the Product Spine job kinds."""

from __future__ import annotations

import hashlib
import io
import json
import signal
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Thread
from typing import BinaryIO
from uuid import UUID

import sqlalchemy as sa
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from asd_kontur.document_understanding.native import NativeExtractionFailure
from asd_kontur.document_understanding.ocr import OcrFailure, QwenVisionOcrAdapter
from asd_kontur.document_understanding.pipeline import (
    IndustrialDocumentUnderstandingPipeline,
    UnderstandingStageFailure,
    translate_stage_error,
)
from asd_kontur.document_understanding.postgres import IndustrialUnderstandingRepository
from asd_kontur.document_understanding.qwen_semantic import QwenDocumentSemanticAdapter
from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.support.models import FieldResolution, ResolutionState
from asd_kontur.support.production import TemplateBackedDocxRenderer
from asd_kontur.support.template_qualification import (
    PdfOverlayBinding,
    PdfOverlayRenderer,
)

from .models import ClaimedJob, JobKind, JobState, semantic_digest
from .object_store import IntakeError, WorkspaceObjectStore
from .postgres import SpinePersistenceError, SpinePostgresRepository


class DeterministicJobFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RetryableJobFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CancelledJob(RuntimeError):
    """Cancellation observed before the next semantic effect."""


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    job_id: str
    state: JobState
    outcome_code: str


class _LeaseKeepalive:
    """Extend a durable-job lease while one bounded handler is executing."""

    def __init__(
        self,
        repository: SpinePostgresRepository,
        claimed: ClaimedJob,
        *,
        worker_identity: str,
        lease_seconds: int,
    ) -> None:
        self._repository = repository
        self._claimed = claimed
        self._worker_identity = worker_identity
        self._lease_seconds = lease_seconds
        self._interval_seconds = max(0.1, min(10.0, lease_seconds / 3))
        self._stopped = Event()
        self._failure: SpinePersistenceError | None = None
        self._thread = Thread(target=self._run, name="asd-document-job-lease", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=self._interval_seconds + 1)

    def raise_if_lost(self) -> None:
        if self._failure is not None:
            raise self._failure

    def _run(self) -> None:
        while not self._stopped.wait(self._interval_seconds):
            try:
                self._repository.heartbeat_job(
                    self._claimed,
                    worker_identity=self._worker_identity,
                    lease_seconds=self._lease_seconds,
                )
            except SpinePersistenceError as exc:
                self._failure = exc
                self._stopped.set()
                return


class DocumentWorker:
    """One-process worker; PostgreSQL leases and fences are the source of truth."""

    def __init__(
        self,
        repository: SpinePostgresRepository,
        object_store: WorkspaceObjectStore,
        *,
        worker_identity: str,
        lease_seconds: int,
        qwen_vision_url: str = "http://127.0.0.1:8790/vision",
        qwen_semantic_url: str | None = "http://127.0.0.1:8790/generate",
        organization_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> None:
        if len(worker_identity) < 3:
            raise ValueError("worker identity is required")
        if (organization_id is None) != (workspace_id is None):
            raise ValueError("document_worker_scope_incomplete")
        self._repository = repository
        self._object_store = object_store
        self._worker_identity = worker_identity
        self._lease_seconds = lease_seconds
        self._organization_id = organization_id
        self._workspace_id = workspace_id
        self._stopping = False
        self._understanding = IndustrialDocumentUnderstandingPipeline(
            IndustrialUnderstandingRepository(repository.engine),
            qwen_vision=QwenVisionOcrAdapter(qwen_vision_url),
            qwen_semantic=(
                QwenDocumentSemanticAdapter(qwen_semantic_url)
                if qwen_semantic_url is not None
                else None
            ),
        )

    def request_stop(self) -> None:
        self._stopping = True

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())

    def run_once(self) -> WorkerOutcome | None:
        claimed = self._repository.claim_next_job(
            worker_identity=self._worker_identity,
            lease_seconds=self._lease_seconds,
            organization_id=self._organization_id,
            workspace_id=self._workspace_id,
        )
        if claimed is None:
            # Recoveries are maintenance work, not a prerequisite for runnable
            # jobs.  One bounded pass avoids an unbounded scan from starving a
            # newly eligible document job.
            self._repository.recover_dependency_terminal_failures()
            self._repository.reconcile_unclaimable_jobs()
            claimed = self._repository.claim_next_job(
                worker_identity=self._worker_identity,
                lease_seconds=self._lease_seconds,
                organization_id=self._organization_id,
                workspace_id=self._workspace_id,
            )
        if claimed is None:
            return None
        self._repository.mark_job_running(claimed, worker_identity=self._worker_identity)
        if self._repository.cancellation_requested(claimed):
            return self._terminal(
                claimed,
                JobState.CANCELLED,
                "job_cancelled_before_effect",
                {"semantic_effect": False},
            )
        keepalive = _LeaseKeepalive(
            self._repository,
            claimed,
            worker_identity=self._worker_identity,
            lease_seconds=self._lease_seconds,
        )
        keepalive.start()
        try:
            result = self._execute(claimed)
            keepalive.raise_if_lost()
        except RetryableJobFailure as exc:
            scheduled = self._repository.retry_job(
                claimed,
                worker_identity=self._worker_identity,
                failure_code=exc.code,
                delay_seconds=min(2**claimed.attempt_number, 30),
            )
            if scheduled:
                return WorkerOutcome(str(claimed.job_id), JobState.QUEUED, exc.code)
            return self._terminal(
                claimed,
                JobState.RECONCILIATION_REQUIRED,
                "retry_exhausted",
                {"last_failure_code": exc.code},
            )
        except CancelledJob:
            return self._terminal(
                claimed,
                JobState.CANCELLED,
                "job_cancelled_at_safe_checkpoint",
                {"semantic_effect": "bounded_to_completed_pages"},
            )
        except DeterministicJobFailure as exc:
            if (
                exc.code
                in {
                    "pdf_structure_invalid",
                    "pdf_has_no_pages",
                    "source_digest_mismatch",
                    "docx_structure_invalid",
                    "xlsx_structure_invalid",
                    "archive_structure_invalid",
                }
                and "document_id" in claimed.input_manifest
            ):
                _admission, _extraction, page_count, gaps = self._repository.latest_document_state(
                    claimed
                )
                self._repository.append_document_state(
                    claimed,
                    admission_status="quarantined",
                    extraction_status="failed",
                    page_count=page_count,
                    capability_gaps=tuple(sorted({*gaps, exc.code})),
                )
            return self._terminal(
                claimed,
                JobState.FAILED,
                exc.code,
                {"semantic_effect": False},
            )
        except (OSError, SpinePersistenceError, sa_exc.SQLAlchemyError) as exc:
            code = getattr(exc, "code", None)
            if not code and isinstance(exc, sa_exc.DBAPIError):
                code = getattr(exc.orig, "sqlstate", None)
            if not code and isinstance(exc, OSError) and exc.errno is not None:
                code = f"worker_os_error_{exc.errno}"
            if not code and isinstance(exc, sa_exc.SQLAlchemyError):
                code = f"worker_sqlalchemy_{type(exc).__name__.casefold()}"
            if not code:
                code = "worker_io_unavailable"
            return self._terminal(
                claimed,
                JobState.RECONCILIATION_REQUIRED,
                str(code),
                {"exception_type": type(exc).__name__},
            )
        finally:
            keepalive.stop()
        return self._terminal(claimed, JobState.SUCCEEDED, "job_succeeded", result)

    def run_forever(self, *, idle_seconds: float = 0.25) -> None:
        self.install_signal_handlers()
        while not self._stopping:
            if self.run_once() is None:
                time.sleep(idle_seconds)

    def _execute(self, claimed: ClaimedJob) -> dict[str, object]:
        handlers = {
            JobKind.DOCUMENT_ADMISSION: self._admit,
            JobKind.DOCUMENT_HASH: self._verify_hash,
            JobKind.PDF_INVENTORY: self._inventory,
            JobKind.NATIVE_TEXT_EXTRACTION: self._extract_native_text,
            JobKind.EVIDENCE_INDEX_UPDATE: self._index_evidence,
            JobKind.ID_DOCUMENT_GENERATION: self._generate_id_document,
        }
        handler = handlers.get(claimed.job_kind)
        if handler is None and claimed.job_kind in {
            JobKind.DOCUMENT_FORMAT_INVENTORY,
            JobKind.PDF_PAGE_HEALTH_ANALYSIS,
            JobKind.NATIVE_LAYOUT_EXTRACTION,
            JobKind.OCR_ROUTING,
            JobKind.OCR_EXTRACTION,
            JobKind.DOCUMENT_PAGE_CLASSIFICATION,
            JobKind.DOCUMENT_AGGREGATION,
            JobKind.PROJECT_DEFINITION_EXTRACTION,
            JobKind.WORK_QUANTITY_MATERIAL_EXTRACTION,
            JobKind.WORK_PACKAGE_ASSEMBLY,
            JobKind.REQUIREMENT_MATRIX_ASSEMBLY,
            JobKind.PROJECT_UNDERSTANDING_RECONCILIATION,
        }:
            try:
                with self._open_source(claimed) as source:
                    return self._understanding.execute(claimed, source)
            except (UnderstandingStageFailure, NativeExtractionFailure, OcrFailure) as exc:
                raise DeterministicJobFailure(translate_stage_error(exc)) from exc
        if handler is None:
            raise DeterministicJobFailure("job_kind_not_supported_by_document_worker")
        return handler(claimed)

    def _generate_id_document(self, claimed: ClaimedJob) -> dict[str, object]:
        manifest = claimed.input_manifest
        run_id = UUID(str(manifest["generation_run_id"]))
        existing = self._existing_generation_candidate(claimed, run_id)
        if existing is not None:
            return existing
        self._advance_generation(claimed, run_id, "rendering")
        fields = self._generation_fields(claimed, run_id)
        try:
            with self._object_store.open(str(manifest["template_object_key"])) as source:
                template_bytes = source.read()
        except FileNotFoundError as exc:
            raise RetryableJobFailure("template_object_temporarily_unavailable") from exc
        output_format = str(manifest.get("format", "DOCX"))
        validation_fingerprint: str | None = None
        print_ready = False
        try:
            if output_format == "PDF_OVERLAY":
                with self._object_store.open(str(manifest["font_object_key"])) as source:
                    font_bytes = source.read()
                rendered, print_receipt = PdfOverlayRenderer().render(
                    template_bytes=template_bytes,
                    template_digest=str(manifest["template_digest"]),
                    fields=fields,
                    bindings=tuple(
                        PdfOverlayBinding(
                            field_key=str(item["field_key"]),
                            page_index=int(item["page_index"]),
                            x=float(item["x"]),
                            y=float(item["y"]),
                            width=float(item["width"]),
                            height=float(item["height"]),
                            font_size=float(item["font_size"]),
                            line_height=float(item["line_height"]),
                            alignment=str(item["alignment"]),
                            material=bool(item.get("material", True)),
                            required=bool(item.get("required", True)),
                        )
                        for item in manifest["bindings"]
                    ),
                    font_bytes=font_bytes,
                    font_digest=str(manifest["font_digest"]),
                    renderer_profile_version=str(manifest["renderer_profile_version"]),
                    validator_profile_version=str(manifest["validator_profile_version"]),
                    semantic_input=dict(manifest["semantic_input"]),
                )
                validation_fingerprint = print_receipt.fingerprint
                print_ready = print_receipt.result == "print_ready"
            else:
                rendered = TemplateBackedDocxRenderer().render(
                    template_bytes=template_bytes,
                    template_digest=str(manifest["template_digest"]),
                    fields=fields,
                    semantic_input=dict(manifest["semantic_input"]),
                )
        except ValueError as exc:
            self._fail_generation(claimed, run_id, str(exc).split(":", 1)[0])
            raise DeterministicJobFailure(str(exc).split(":", 1)[0]) from exc
        self._advance_generation(claimed, run_id, "validating")
        candidate_id = deterministic_uuid(f"support-generated-candidate:{run_id}")
        extension = "pdf" if output_format == "PDF_OVERLAY" else "docx"
        object_key = (
            f"derived/{claimed.organization_id}/{claimed.workspace_id}/generated/"
            f"{rendered.bytes_digest[7:]}.{extension}"
        )
        stored_digest, size = self._object_store.put_derived(
            object_key=object_key, content=rendered.package_bytes
        )
        if stored_digest != rendered.bytes_digest:
            self._fail_generation(claimed, run_id, "generated_object_digest_mismatch")
            raise DeterministicJobFailure("generated_object_digest_mismatch")
        assurance = self._publish_generation_candidate(
            claimed,
            run_id=run_id,
            candidate_id=candidate_id,
            object_key=object_key,
            bytes_digest=stored_digest,
            semantic_fingerprint=rendered.semantic_fingerprint,
            checks=rendered.structural_checks,
            output_format="PDF" if output_format == "PDF_OVERLAY" else "DOCX",
            renderer_profile_version=str(manifest["renderer_profile_version"]),
            validator_profile_version=str(manifest["validator_profile_version"]),
            validation_fingerprint=validation_fingerprint,
            print_ready=print_ready,
        )
        return {
            "generation_run_id": str(run_id),
            "generated_candidate_id": str(candidate_id),
            "object_reference": object_key,
            "bytes_digest": stored_digest,
            "size_bytes": size,
            "semantic_fingerprint": rendered.semantic_fingerprint,
            "assurance": assurance,
            "finalized": False,
        }

    def _existing_generation_candidate(
        self, claimed: ClaimedJob, run_id: UUID
    ) -> dict[str, object] | None:
        with Session(self._repository.engine) as session, session.begin():
            _set_worker_scope(session, claimed)
            row = (
                session.execute(
                    sa.text(
                        "SELECT generated_candidate_id,object_reference,bytes_digest,semantic_fingerprint "
                        "FROM workspace.support_generated_document_candidates WHERE "
                        "organization_id=:o AND workspace_id=:w AND generation_run_id=:run"
                    ),
                    {"o": claimed.organization_id, "w": claimed.workspace_id, "run": run_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return {
            "generation_run_id": str(run_id),
            "generated_candidate_id": str(row["generated_candidate_id"]),
            "object_reference": str(row["object_reference"]),
            "bytes_digest": str(row["bytes_digest"]),
            "semantic_fingerprint": str(row["semantic_fingerprint"]),
            "recovered_idempotently": True,
            "finalized": False,
        }

    def _generation_fields(self, claimed: ClaimedJob, run_id: UUID) -> tuple[FieldResolution, ...]:
        with Session(self._repository.engine) as session, session.begin():
            _set_worker_scope(session, claimed)
            rows = session.execute(
                sa.text(
                    "SELECT f.*,e.evidence_link_id,e.source_locator_id FROM "
                    "workspace.support_generation_field_resolutions f LEFT JOIN "
                    "workspace.support_generation_evidence_bindings e ON "
                    "e.organization_id=f.organization_id AND e.workspace_id=f.workspace_id AND "
                    "e.generation_run_id=f.generation_run_id AND e.field_key=f.field_key WHERE "
                    "f.organization_id=:o AND f.workspace_id=:w AND f.generation_run_id=:run "
                    "ORDER BY f.field_key"
                ),
                {"o": claimed.organization_id, "w": claimed.workspace_id, "run": run_id},
            ).mappings()
            return tuple(
                FieldResolution(
                    str(row["field_key"]),
                    ResolutionState(str(row["state"])),
                    row["normalized_value"],
                    row["display_value"],
                    UUID(str(row["fact_id"])) if row["fact_id"] else None,
                    int(row["fact_version"]) if row["fact_version"] else None,
                    (UUID(str(row["evidence_link_id"])),) if row["evidence_link_id"] else (),
                    (UUID(str(row["source_locator_id"])),) if row["source_locator_id"] else (),
                    bool(row["material"]),
                )
                for row in rows
            )

    def _advance_generation(self, claimed: ClaimedJob, run_id: UUID, target: str) -> None:
        with Session(self._repository.engine) as session, session.begin():
            _set_worker_scope(session, claimed)
            current = session.scalar(
                sa.text(
                    "SELECT status FROM workspace.support_generation_runs WHERE "
                    "organization_id=:o AND workspace_id=:w AND generation_run_id=:run FOR UPDATE"
                ),
                {"o": claimed.organization_id, "w": claimed.workspace_id, "run": run_id},
            )
            if current == target or current == "candidate_created":
                return
            allowed = {
                "rendering": {"planned", "resolving"},
                "validating": {"rendering"},
            }
            if str(current) not in allowed[target]:
                raise DeterministicJobFailure("generation_state_transition_invalid")
            session.execute(
                sa.select(
                    sa.func.set_config("asd.generation_operation_id", str(claimed.job_id), True)
                )
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.support_generation_runs SET status=:target WHERE "
                    "organization_id=:o AND workspace_id=:w AND generation_run_id=:run"
                ),
                {
                    "target": target,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "run": run_id,
                },
            )

    def _fail_generation(self, claimed: ClaimedJob, run_id: UUID, blocker: str) -> None:
        with Session(self._repository.engine) as session, session.begin():
            _set_worker_scope(session, claimed)
            session.execute(
                sa.select(
                    sa.func.set_config("asd.generation_operation_id", str(claimed.job_id), True)
                )
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.support_generation_runs SET status='failed',"
                    "blocker_codes=ARRAY[:blocker],completed_at=CURRENT_TIMESTAMP WHERE "
                    "organization_id=:o AND workspace_id=:w AND generation_run_id=:run AND "
                    "status IN ('planned','resolving','rendering','validating')"
                ),
                {
                    "blocker": blocker,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "run": run_id,
                },
            )

    def _publish_generation_candidate(
        self,
        claimed: ClaimedJob,
        *,
        run_id: UUID,
        candidate_id: UUID,
        object_key: str,
        bytes_digest: str,
        semantic_fingerprint: str,
        checks: tuple[str, ...],
        output_format: str,
        renderer_profile_version: str,
        validator_profile_version: str,
        validation_fingerprint: str | None,
        print_ready: bool,
    ) -> str:
        now = datetime.now(UTC)
        with Session(self._repository.engine) as session, session.begin():
            _set_worker_scope(session, claimed)
            template = (
                session.execute(
                    sa.text(
                        "SELECT tv.assurance_class,tv.official_status,tv.qualification_state FROM "
                        "workspace.support_generation_job_bindings b JOIN platform.template_versions tv "
                        "ON tv.template_id=b.template_id AND tv.version=b.template_version WHERE "
                        "b.organization_id=:o AND b.workspace_id=:w AND b.generation_run_id=:run"
                    ),
                    {"o": claimed.organization_id, "w": claimed.workspace_id, "run": run_id},
                )
                .mappings()
                .one()
            )
            production_template = (
                template["assurance_class"] == "production"
                and template["official_status"] == "verified"
                and template["qualification_state"] == "active"
            )
            render_id = deterministic_uuid(f"support-render:{candidate_id}")
            validation_id = deterministic_uuid(f"support-print-validation:{candidate_id}")
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_generated_document_candidates VALUES "
                    "(:o,:w,:candidate,:run,:object,:format,:semantic,:bytes,'non_final_candidate',:now) "
                    "ON CONFLICT (organization_id,workspace_id,generation_run_id,bytes_digest) DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "candidate": candidate_id,
                    "run": run_id,
                    "object": object_key,
                    "format": output_format,
                    "semantic": semantic_fingerprint,
                    "bytes": bytes_digest,
                    "now": now,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_render_artifacts VALUES "
                    "(:o,:w,:render,:candidate,:renderer,:format,"
                    ":object,:bytes,:assurance,'verified',:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "render": render_id,
                    "candidate": candidate_id,
                    "object": object_key,
                    "bytes": bytes_digest,
                    "renderer": renderer_profile_version,
                    "format": output_format,
                    "assurance": (
                        "production_qualified"
                        if production_template and print_ready
                        else "template_candidate"
                    ),
                    "now": now,
                },
            )
            blockers = []
            if not production_template:
                blockers.append("TEMPLATE_NOT_PRODUCTION_QUALIFIED")
            if not print_ready:
                blockers.append("PRINT_LAYOUT_VALIDATION_NOT_QUALIFIED")
            result = "print_ready" if not blockers else "blocked"
            session.execute(
                sa.text(
                    "INSERT INTO workspace.support_print_validation_results VALUES "
                    "(:o,:w,:validation,:candidate,:render,:validator,"
                    ":checks,:blockers,:result,:assurance,:digest,:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "validation": validation_id,
                    "candidate": candidate_id,
                    "render": render_id,
                    "checks": list(checks),
                    "validator": validator_profile_version,
                    "blockers": blockers,
                    "result": result,
                    "assurance": "production" if not blockers else "synthetic_development",
                    "digest": semantic_digest(
                        {
                            "candidate": str(candidate_id),
                            "checks": checks,
                            "blockers": blockers,
                            "layout_receipt": validation_fingerprint,
                        }
                    ),
                    "now": now,
                },
            )
            self._append_generated_package_version(
                session,
                claimed,
                run_id=run_id,
                candidate_id=candidate_id,
                candidate_digest=bytes_digest,
                template_blockers=tuple(blockers),
                now=now,
            )
            session.execute(
                sa.select(
                    sa.func.set_config("asd.generation_operation_id", str(claimed.job_id), True)
                )
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.support_generation_runs SET status='candidate_created',"
                    "blocker_codes=ARRAY[]::text[],completed_at=:now WHERE organization_id=:o AND "
                    "workspace_id=:w AND generation_run_id=:run AND status='validating'"
                ),
                {
                    "now": now,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "run": run_id,
                },
            )
        return "production_qualified" if not blockers else "template_candidate"

    def _append_generated_package_version(
        self,
        session: Session,
        claimed: ClaimedJob,
        *,
        run_id: UUID,
        candidate_id: UUID,
        candidate_digest: str,
        template_blockers: tuple[str, ...],
        now: datetime,
    ) -> None:
        binding = (
            session.execute(
                sa.text(
                    "SELECT b.membership_id,b.membership_version,m.id_package_id,m.id_package_version "
                    "FROM workspace.support_generation_job_bindings b JOIN "
                    "workspace.id_package_document_membership_versions m ON "
                    "m.organization_id=b.organization_id AND m.workspace_id=b.workspace_id AND "
                    "m.membership_id=b.membership_id AND m.version=b.membership_version WHERE "
                    "b.organization_id=:o AND b.workspace_id=:w AND b.generation_run_id=:run"
                ),
                {"o": claimed.organization_id, "w": claimed.workspace_id, "run": run_id},
            )
            .mappings()
            .one()
        )
        if session.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.id_package_document_membership_versions WHERE "
                "organization_id=:o AND workspace_id=:w AND subject_ref=:candidate"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": str(candidate_id),
            },
        ):
            return
        old_package = (
            session.execute(
                sa.text(
                    "SELECT * FROM workspace.id_package_versions WHERE organization_id=:o AND "
                    "workspace_id=:w AND id_package_id=:p AND version=:v"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "p": binding["id_package_id"],
                    "v": binding["id_package_version"],
                },
            )
            .mappings()
            .one()
        )
        old_books = list(
            session.execute(
                sa.text(
                    "SELECT * FROM workspace.id_package_volume_book_versions WHERE organization_id=:o "
                    "AND workspace_id=:w AND id_package_id=:p AND id_package_version=:v ORDER BY ordinal"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "p": binding["id_package_id"],
                    "v": binding["id_package_version"],
                },
            ).mappings()
        )
        old_members = list(
            session.execute(
                sa.text(
                    "SELECT * FROM workspace.id_package_document_membership_versions WHERE organization_id=:o "
                    "AND workspace_id=:w AND id_package_id=:p AND id_package_version=:v ORDER BY volume_book_id,ordinal"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "p": binding["id_package_id"],
                    "v": binding["id_package_version"],
                },
            ).mappings()
        )
        new_version = int(old_package["version"]) + 1
        member_documents: list[dict[str, object]] = []
        transformed: list[dict[str, object]] = []
        for member in old_members:
            value = dict(member)
            value["version"] = int(member["version"]) + 1
            value["id_package_version"] = new_version
            value["volume_book_version"] = int(member["volume_book_version"]) + 1
            if member["membership_id"] == binding["membership_id"]:
                value["subject_kind"] = "generated_document_candidate"
                value["subject_ref"] = str(candidate_id)
                value["state"] = "generated_candidate"
                value["evidence_refs"] = [*member["evidence_refs"], candidate_digest]
                value["blocker_codes"] = list(template_blockers)
            if member["role"] == "register":
                value["subject_ref"] = (
                    f"package-register:{old_package['id_package_id']}:v{new_version}"
                )
                value["state"] = "generated_candidate"
            value["semantic_fingerprint"] = semantic_digest(
                {
                    key: str(item)
                    for key, item in value.items()
                    if key not in {"recorded_at", "semantic_fingerprint"}
                }
            )
            transformed.append(value)
            if value["role"] != "register":
                member_documents.append(
                    {
                        "ordinal": value["ordinal"],
                        "membership_id": str(value["membership_id"]),
                        "membership_version": value["version"],
                        "role": value["role"],
                        "subject_kind": value["subject_kind"],
                        "subject_ref": value["subject_ref"],
                        "copies": value["required_copy_count"],
                        "stage": value["stage"],
                        "state": value["state"],
                    }
                )
        states = [str(item["state"]) for item in transformed if str(item["role"]) != "register"]
        required = len([state for state in states if state != "not_applicable"])
        covered = sum(state in {"covered", "finalized"} for state in states)
        missing = states.count("missing")
        indeterminate = sum(
            state in {"required", "generated_candidate", "conflict", "indeterminate", "blocked"}
            for state in states
        )
        package_fingerprint = semantic_digest(
            {
                "prior": old_package["calculation_fingerprint"],
                "version": new_version,
                "memberships": [item["semantic_fingerprint"] for item in transformed],
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.id_package_versions VALUES (:o,:w,:p,:v,:scope,:subject,"
                "'incomplete',:required,:covered,:missing,:indeterminate,:fingerprint,:ruleset,:now)"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "p": old_package["id_package_id"],
                "v": new_version,
                "scope": old_package["scope_kind"],
                "subject": old_package["scope_subject_id"],
                "required": required,
                "covered": covered,
                "missing": missing,
                "indeterminate": indeterminate,
                "fingerprint": package_fingerprint,
                "ruleset": old_package["rule_set_version_id"],
                "now": now,
            },
        )
        for book in old_books:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.id_package_volume_book_versions VALUES "
                    "(:o,:w,:p,:pv,:book,:v,:ordinal,:title,:level,:copies,:fingerprint,:now)"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "p": old_package["id_package_id"],
                    "pv": new_version,
                    "book": book["volume_book_id"],
                    "v": int(book["version"]) + 1,
                    "ordinal": book["ordinal"],
                    "title": book["title"],
                    "level": book["register_level"],
                    "copies": book["required_copy_count"],
                    "fingerprint": semantic_digest(
                        {"prior": book["semantic_fingerprint"], "package_version": new_version}
                    ),
                    "now": now,
                },
            )
        for transformed_member in transformed:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.id_package_document_membership_versions VALUES "
                    "(:organization_id,:workspace_id,:membership_id,:version,:id_package_id,"
                    ":id_package_version,:volume_book_id,:volume_book_version,:matrix_id,:matrix_version,"
                    ":document_requirement_id,:document_requirement_version,:role,:ordinal,"
                    ":required_copy_count,:stage,:subject_kind,:subject_ref,:state,:evidence_refs,"
                    ":blocker_codes,:semantic_fingerprint,:recorded_at)"
                ),
                {**transformed_member, "recorded_at": now},
            )
        register_member = transformed[0]
        register_manifest = {
            "package_id": str(old_package["id_package_id"]),
            "package_version": new_version,
            "volume_book_id": str(register_member["volume_book_id"]),
            "volume_book_version": register_member["volume_book_version"],
            "register_membership_id": str(register_member["membership_id"]),
            "documents": member_documents,
            "fingerprint": semantic_digest(member_documents),
        }
        session.execute(
            sa.text(
                "INSERT INTO workspace.support_register_candidates VALUES "
                "(:o,:w,:register,1,:p,:pv,:book,:bv,:membership,:mv,CAST(:manifest AS jsonb),"
                ":fingerprint,'structured_candidate',ARRAY['REGISTER_TEMPLATE_AUTHORITY_UNRESOLVED'],:now)"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "register": deterministic_uuid(
                    f"support-register:{old_package['id_package_id']}:v{new_version}"
                ),
                "p": old_package["id_package_id"],
                "pv": new_version,
                "book": register_member["volume_book_id"],
                "bv": register_member["volume_book_version"],
                "membership": register_member["membership_id"],
                "mv": register_member["version"],
                "manifest": json.dumps(register_manifest, sort_keys=True, separators=(",", ":")),
                "fingerprint": register_manifest["fingerprint"],
                "now": now,
            },
        )
        blockers = sorted(
            {
                str(code)
                for item in transformed
                for code in (
                    item["blocker_codes"]
                    if isinstance(item["blocker_codes"], (list, tuple))
                    else ()
                )
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.id_package_readiness_evaluations VALUES "
                "(:o,:w,:evaluation,1,:p,:pv,:required,:covered,:generated,:finalized,:missing,"
                ":conflict,:indeterminate,:blocked,:not_applicable,:blockers,'incomplete',:fingerprint,:now)"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "evaluation": uuid7(),
                "p": old_package["id_package_id"],
                "pv": new_version,
                "required": required,
                "covered": covered,
                "generated": states.count("generated_candidate"),
                "finalized": states.count("finalized"),
                "missing": missing,
                "conflict": states.count("conflict"),
                "indeterminate": states.count("indeterminate"),
                "blocked": states.count("blocked"),
                "not_applicable": states.count("not_applicable"),
                "blockers": blockers,
                "fingerprint": semantic_digest(
                    {"package": package_fingerprint, "states": states, "blockers": blockers}
                ),
                "now": now,
            },
        )

    def _admit(self, claimed: ClaimedJob) -> dict[str, object]:
        with self._open_source(claimed) as source:
            prefix = source.read(4096)
        if not prefix:
            raise DeterministicJobFailure("source_object_empty")
        admission, extraction, page_count, gaps = self._repository.latest_document_state(claimed)
        self._repository.append_document_state(
            claimed,
            admission_status="accepted",
            extraction_status=extraction,
            page_count=page_count,
            capability_gaps=gaps,
        )
        return {"admission_status": "accepted", "prior_admission_status": admission}

    def _verify_hash(self, claimed: ClaimedJob) -> dict[str, object]:
        digest = hashlib.sha256()
        size = 0
        with self._open_source(claimed) as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                if size % (16 * 1024 * 1024) == 0:
                    self._repository.heartbeat_job(
                        claimed,
                        worker_identity=self._worker_identity,
                        lease_seconds=self._lease_seconds,
                    )
        observed = "sha256:" + digest.hexdigest()
        expected = str(claimed.input_manifest["content_digest"])
        if observed != expected:
            raise DeterministicJobFailure("source_digest_mismatch")
        admission, extraction, page_count, gaps = self._repository.latest_document_state(claimed)
        self._repository.append_document_state(
            claimed,
            admission_status="accepted",
            extraction_status=extraction,
            page_count=page_count,
            capability_gaps=gaps,
        )
        return {"content_digest": observed, "size_bytes": size, "prior_status": admission}

    def _inventory(self, claimed: ClaimedJob) -> dict[str, object]:
        media_type = str(claimed.input_manifest["media_type"])
        admission, _, _, current_gaps = self._repository.latest_document_state(claimed)
        gaps = set(current_gaps)
        if media_type != "application/pdf":
            gaps.add("PDF_VIEWER_UNSUPPORTED")
            gaps.add(
                "OCR_OR_VLM_REQUIRED"
                if media_type.startswith("image/")
                else "PDF_INVENTORY_NOT_APPLICABLE"
            )
            self._repository.append_document_state(
                claimed,
                admission_status=admission,
                extraction_status=(
                    "partial_with_capability_gap" if media_type.startswith("image/") else "running"
                ),
                page_count=None,
                capability_gaps=tuple(sorted(gaps)),
            )
            return {"page_count": None, "capability_gaps": sorted(gaps)}
        try:
            with self._open_source(claimed) as source:
                reader = PdfReader(source, strict=True)
                page_count = len(reader.pages)
        except PdfReadError as exc:
            raise DeterministicJobFailure("pdf_structure_invalid") from exc
        if page_count < 1:
            raise DeterministicJobFailure("pdf_has_no_pages")
        self._repository.append_document_state(
            claimed,
            admission_status=admission,
            extraction_status="running",
            page_count=page_count,
            capability_gaps=tuple(sorted(gaps)),
        )
        return {"page_count": page_count}

    def _extract_native_text(self, claimed: ClaimedJob) -> dict[str, object]:
        media_type = str(claimed.input_manifest["media_type"])
        admission, _, page_count, current_gaps = self._repository.latest_document_state(claimed)
        gaps = set(current_gaps)
        if media_type == "text/plain":
            with self._open_source(claimed) as source:
                content = source.read()
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DeterministicJobFailure("native_text_invalid_utf8") from exc
            self._repository.append_document_state(
                claimed,
                admission_status=admission,
                extraction_status="complete",
                page_count=None,
                capability_gaps=tuple(sorted(gaps)),
            )
            return {"native_text_digest": "sha256:" + hashlib.sha256(content).hexdigest()}
        if media_type != "application/pdf":
            gaps.add("OCR_OR_VLM_REQUIRED")
            self._repository.append_document_state(
                claimed,
                admission_status=admission,
                extraction_status="partial_with_capability_gap",
                page_count=page_count,
                capability_gaps=tuple(sorted(gaps)),
            )
            return {"capability_gaps": sorted(gaps), "extracted_pages": 0}
        try:
            with self._open_source(claimed) as source:
                reader = PdfReader(source, strict=True)
                extracted = self._extract_pdf_pages(claimed, reader)
        except PdfReadError as exc:
            raise DeterministicJobFailure("pdf_native_extraction_failed") from exc
        empty = extracted[1]
        if empty:
            gaps.add("OCR_REQUIRED")
        self._repository.append_document_state(
            claimed,
            admission_status=admission,
            extraction_status="partial_with_capability_gap" if empty else "complete",
            page_count=extracted[0],
            capability_gaps=tuple(sorted(gaps)),
        )
        return {
            "page_count": extracted[0],
            "empty_native_pages": empty,
            "capability_gaps": sorted(gaps),
        }

    def _extract_pdf_pages(self, claimed: ClaimedJob, reader: PdfReader) -> tuple[int, list[int]]:
        empty_pages: list[int] = []
        document_id = str(claimed.input_manifest["document_id"])
        version = int(claimed.input_manifest["document_version"])
        total = len(reader.pages)
        for index, page in enumerate(reader.pages, start=1):
            if self._repository.cancellation_requested(claimed):
                raise CancelledJob
            text = page.extract_text() or ""
            encoded = text.encode("utf-8")
            text_digest: str | None = None
            text_key: str | None = None
            method = "none"
            if text.strip():
                text_key = (
                    f"derived/{claimed.organization_id}/{claimed.workspace_id}/native-text/"
                    f"{document_id}/{version}/{index}.txt"
                )
                text_digest, _ = self._object_store.put_derived(
                    object_key=text_key,
                    content=encoded,
                )
                method = "native_pdf"
            else:
                empty_pages.append(index)
            box = page.cropbox
            width = float(box.right) - float(box.left)
            height = float(box.top) - float(box.bottom)
            self._repository.record_document_page(
                claimed,
                page_number=index,
                width_points=width,
                height_points=height,
                rotation_degrees=int(page.rotation or 0) % 360,
                crop_box={
                    "left": float(box.left),
                    "bottom": float(box.bottom),
                    "right": float(box.right),
                    "top": float(box.top),
                },
                native_text_digest=text_digest,
                native_text_object_key=text_key,
                extraction_method=method,
            )
            self._repository.report_progress(
                claimed,
                current=index,
                total=total,
                safe_message_code="native_text.page_processed",
            )
            self._repository.heartbeat_job(
                claimed,
                worker_identity=self._worker_identity,
                lease_seconds=self._lease_seconds,
            )
        return total, empty_pages

    def _index_evidence(self, claimed: ClaimedJob) -> dict[str, object]:
        admission, _extraction, page_count, gaps = self._repository.latest_document_state(claimed)
        if admission != "accepted":
            raise DeterministicJobFailure("document_admission_not_verified")
        state = "partial_with_capability_gap" if gaps else "complete"
        self._repository.append_document_state(
            claimed,
            admission_status=admission,
            extraction_status=state,
            page_count=page_count,
            capability_gaps=gaps,
        )
        return {"index_status": state, "page_count": page_count, "capability_gaps": list(gaps)}

    def _open_source(self, claimed: ClaimedJob) -> BinaryIO:
        try:
            return self._object_store.open(str(claimed.input_manifest["object_key"]))
        except FileNotFoundError as exc:
            raise RetryableJobFailure("source_object_temporarily_unavailable") from exc
        except IntakeError as exc:
            raise DeterministicJobFailure(exc.code) from exc

    def _terminal(
        self,
        claimed: ClaimedJob,
        state: JobState,
        code: str,
        result: dict[str, object],
    ) -> WorkerOutcome:
        self._repository.finish_job(
            claimed,
            terminal_state=state,
            outcome_code=code,
            result_manifest=result,
            worker_identity=self._worker_identity,
        )
        return WorkerOutcome(str(claimed.job_id), state, code)


def verify_stream_digest(stream: BinaryIO) -> tuple[str, int]:
    """Small deterministic helper used by focused tests and diagnostics."""

    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


def verify_bytes_digest(content: bytes) -> tuple[str, int]:
    return verify_stream_digest(io.BytesIO(content))


def _set_worker_scope(session: Session, claimed: ClaimedJob) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(claimed.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(claimed.workspace_id), True),
        )
    ).one()
