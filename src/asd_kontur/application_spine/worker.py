"""Bounded PostgreSQL document worker for the initial Product Spine job kinds."""

from __future__ import annotations

import hashlib
import io
import signal
import time
from dataclasses import dataclass
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import exc as sa_exc

from .models import ClaimedJob, JobKind, JobState
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


class DocumentWorker:
    """One-process worker; PostgreSQL leases and fences are the source of truth."""

    def __init__(
        self,
        repository: SpinePostgresRepository,
        object_store: WorkspaceObjectStore,
        *,
        worker_identity: str,
        lease_seconds: int,
    ) -> None:
        if len(worker_identity) < 3:
            raise ValueError("worker identity is required")
        self._repository = repository
        self._object_store = object_store
        self._worker_identity = worker_identity
        self._lease_seconds = lease_seconds
        self._stopping = False

    def request_stop(self) -> None:
        self._stopping = True

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())

    def run_once(self) -> WorkerOutcome | None:
        self._repository.reconcile_unclaimable_jobs()
        claimed = self._repository.claim_next_job(
            worker_identity=self._worker_identity,
            lease_seconds=self._lease_seconds,
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
        try:
            result = self._execute(claimed)
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
            return self._terminal(
                claimed,
                JobState.FAILED,
                exc.code,
                {"semantic_effect": False},
            )
        except (OSError, SpinePersistenceError, sa_exc.SQLAlchemyError) as exc:
            code = getattr(exc, "code", "worker_io_unavailable")
            return self._terminal(
                claimed,
                JobState.RECONCILIATION_REQUIRED,
                str(code),
                {"exception_type": type(exc).__name__},
            )
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
        }
        handler = handlers.get(claimed.job_kind)
        if handler is None:
            raise DeterministicJobFailure("job_kind_not_supported_by_document_worker")
        return handler(claimed)

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
