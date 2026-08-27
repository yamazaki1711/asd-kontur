"""Durable platform-NTD processing jobs for bounded external recovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

RETRY_POLICY_VERSION = "polza-outcome-aware-v0.1"
TOOL_PROFILE_VERSION = "ntd-polza-raster-batch-v0.1"
OUTCOME_UNKNOWN_FAILURES = frozenset(
    {"POLZA_TIMEOUT", "POLZA_CONNECTION_ERROR", "POLZA_RESPONSE_READ_ERROR"}
)


@dataclass(frozen=True, slots=True)
class NtdRasterRecoveryJob:
    job_id: UUID
    identity_reconciliation_id: UUID
    normative_artifact_id: UUID
    normative_page_id: UUID
    normative_page_version: int
    designation: str
    page_index: int
    input_manifest_digest: str
    attempt_number: int
    lease_generation: int


@dataclass(frozen=True, slots=True)
class NtdJobTerminalResult:
    job_id: UUID
    state: str
    failure_code: str | None
    terminal_receipt_fingerprint: str


class NtdProcessingJobRepository:
    """Own the mutable lease boundary and immutable attempt receipts."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def enqueue_pending_raster_pages(self, *, eligible_at: datetime) -> tuple[int, int]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        "WITH latest AS (SELECT DISTINCT ON (normative_page_id) * FROM "
                        "platform.normative_representation_pages ORDER BY normative_page_id,"
                        "version DESC) SELECT p.normative_page_id,p.version,p.page_index,"
                        "p.normative_artifact_id,na.content_digest,nd.designation,"
                        "resolution.identity_reconciliation_id FROM latest p JOIN "
                        "platform.normative_artifacts na ON na.normative_artifact_id="
                        "p.normative_artifact_id JOIN platform.normative_editions ne ON "
                        "ne.normative_edition_id=na.normative_edition_id JOIN "
                        "platform.normative_documents nd ON nd.normative_document_id="
                        "ne.normative_document_id JOIN LATERAL (SELECT "
                        "value.identity_reconciliation_id FROM "
                        "platform.ntd_identity_resolution_versions value WHERE "
                        "na.normative_artifact_id=ANY(value.normative_artifact_ids) ORDER BY "
                        "value.recorded_at DESC,value.version DESC LIMIT 1) resolution ON true "
                        "WHERE p.representation_kind='raster' AND "
                        "p.extraction_route='polza_candidate' AND "
                        "p.terminal_outcome<>'recovery_complete' AND NOT EXISTS (SELECT 1 FROM "
                        "platform.ntd_processing_jobs job WHERE job.stage='selective_recovery' AND "
                        "split_part(job.idempotency_key,':',2)=p.normative_page_id::text AND "
                        "split_part(job.idempotency_key,':',4)='polza-public-ntd-page-v0.1') "
                        "ORDER BY nd.designation,"
                        "p.page_index"
                    )
                )
                .mappings()
                .all()
            )
        inserted = 0
        with Session(self._engine) as session, session.begin():
            for row in rows:
                manifest = {
                    "schema": "ntd-raster-recovery-job-input-v1",
                    "normative_page_id": str(row["normative_page_id"]),
                    "normative_page_version": int(row["version"]),
                    "normative_artifact_id": str(row["normative_artifact_id"]),
                    "artifact_digest": str(row["content_digest"]),
                    "designation": str(row["designation"]),
                    "page_index": int(row["page_index"]),
                    "provider_profile_version": "polza-public-ntd-page-v0.1",
                }
                input_digest = digest_of(manifest)
                idempotency_key = (
                    "ntd-selective-recovery:"
                    f"{row['normative_page_id']}:{row['version']}:"
                    "polza-public-ntd-page-v0.1"
                )
                job_id = deterministic_uuid(f"ntd-processing-job:{idempotency_key}")
                result = session.execute(
                    sa.text(
                        "INSERT INTO platform.ntd_processing_jobs "
                        "(ntd_processing_job_id,identity_reconciliation_id,"
                        "normative_artifact_id,stage,input_manifest_digest,idempotency_key,"
                        "state,priority,eligible_at,attempt_count,max_attempts,"
                        "retry_policy_version,created_at) VALUES "
                        "(:id,:identity,:artifact,'selective_recovery',:digest,:key,'queued',"
                        "100,:eligible,0,1,:policy,:created) ON CONFLICT "
                        "(idempotency_key) DO NOTHING"
                    ),
                    {
                        "id": job_id,
                        "identity": row["identity_reconciliation_id"],
                        "artifact": row["normative_artifact_id"],
                        "digest": input_digest,
                        "key": idempotency_key,
                        "eligible": eligible_at,
                        "policy": RETRY_POLICY_VERSION,
                        "created": eligible_at,
                    },
                )
                inserted += int(getattr(result, "rowcount", 0) or 0)
        return len(rows), inserted

    def claim_next(
        self,
        *,
        lease_owner: str,
        claimed_at: datetime,
        lease_duration: timedelta,
    ) -> NtdRasterRecoveryJob | None:
        with Session(self._engine) as session, session.begin():
            row = (
                session.execute(
                    sa.text(
                        "SELECT job.ntd_processing_job_id,job.identity_reconciliation_id,"
                        "job.normative_artifact_id,job.input_manifest_digest,job.attempt_count,"
                        "job.lease_generation,page.normative_page_id,page.version "
                        "normative_page_version,page.page_index,document.designation FROM "
                        "platform.ntd_processing_jobs job JOIN "
                        "platform.normative_artifacts artifact ON "
                        "artifact.normative_artifact_id=job.normative_artifact_id JOIN "
                        "platform.normative_editions edition ON edition.normative_edition_id="
                        "artifact.normative_edition_id JOIN platform.normative_documents document "
                        "ON document.normative_document_id=edition.normative_document_id JOIN "
                        "platform.normative_representation_pages page ON "
                        "page.normative_artifact_id=job.normative_artifact_id AND "
                        "page.normative_page_id::text=split_part(job.idempotency_key,':',2) AND "
                        "page.version=split_part(job.idempotency_key,':',3)::bigint WHERE "
                        "job.state='queued' "
                        "AND job.eligible_at<=:now ORDER BY job.priority,job.eligible_at,"
                        "(page.rotation_degrees<>0),"
                        "(page.width_points*page.height_points),page.page_index,"
                        "job.ntd_processing_job_id FOR UPDATE OF job SKIP LOCKED LIMIT 1"
                    ),
                    {"now": claimed_at},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            generation = int(row["lease_generation"]) + 1
            attempt_number = int(row["attempt_count"]) + 1
            session.execute(
                sa.text(
                    "UPDATE platform.ntd_processing_jobs SET state='running',"
                    "started_at=COALESCE(started_at,:now),heartbeat_at=:now,attempt_count="
                    ":attempt,lease_owner=:owner,lease_generation=:generation,"
                    "lease_expires_at=:expires WHERE ntd_processing_job_id=:id"
                ),
                {
                    "id": row["ntd_processing_job_id"],
                    "now": claimed_at,
                    "attempt": attempt_number,
                    "owner": lease_owner,
                    "generation": generation,
                    "expires": claimed_at + lease_duration,
                },
            )
        return NtdRasterRecoveryJob(
            UUID(str(row["ntd_processing_job_id"])),
            UUID(str(row["identity_reconciliation_id"])),
            UUID(str(row["normative_artifact_id"])),
            UUID(str(row["normative_page_id"])),
            int(row["normative_page_version"]),
            str(row["designation"]),
            int(row["page_index"]),
            str(row["input_manifest_digest"]),
            attempt_number,
            generation,
        )

    def heartbeat(
        self, job: NtdRasterRecoveryJob, *, lease_owner: str, heartbeat_at: datetime
    ) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.text(
                    "UPDATE platform.ntd_processing_jobs SET heartbeat_at=:at WHERE "
                    "ntd_processing_job_id=:id AND state='running' AND lease_owner=:owner "
                    "AND lease_generation=:generation"
                ),
                {
                    "id": job.job_id,
                    "at": heartbeat_at,
                    "owner": lease_owner,
                    "generation": job.lease_generation,
                },
            )
        return (result.rowcount or 0) == 1

    def terminalize(
        self,
        job: NtdRasterRecoveryJob,
        *,
        lease_owner: str,
        state: str,
        failure_code: str | None,
        output: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
    ) -> NtdJobTerminalResult:
        if state not in {"succeeded", "failed", "reconciliation_required"}:
            raise ValueError("NTD_PROCESSING_TERMINAL_STATE_INVALID")
        output_digest = digest_of(output)
        terminal_payload = {
            "schema": "ntd-processing-terminal-receipt-v1",
            "job_id": job.job_id,
            "attempt_number": job.attempt_number,
            "lease_generation": job.lease_generation,
            "input_digest": job.input_manifest_digest,
            "output_digest": output_digest,
            "state": state,
            "failure_code": failure_code,
        }
        terminal_fingerprint = digest_of(terminal_payload)
        attempt_id = deterministic_uuid(
            f"ntd-processing-attempt:{job.job_id}:{job.attempt_number}:{job.lease_generation}"
        )
        attempt_fingerprint = digest_of(
            {
                **terminal_payload,
                "attempt_id": attempt_id,
                "tool_profile_version": TOOL_PROFILE_VERSION,
            }
        )
        with Session(self._engine) as session, session.begin():
            current = (
                session.execute(
                    sa.text(
                        "SELECT state,lease_owner,lease_generation FROM "
                        "platform.ntd_processing_jobs WHERE ntd_processing_job_id=:id FOR UPDATE"
                    ),
                    {"id": job.job_id},
                )
                .mappings()
                .one()
            )
            if (
                current["state"] != "running"
                or current["lease_owner"] != lease_owner
                or int(current["lease_generation"]) != job.lease_generation
            ):
                raise ValueError("NTD_PROCESSING_LEASE_FENCE_REJECTED")
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_processing_job_attempts "
                    "(ntd_processing_attempt_id,ntd_processing_job_id,attempt_number,"
                    "lease_generation,processor_identity,tool_profile_version,input_digest,"
                    "output_digest,status,failure_code,usage_receipt,started_at,completed_at,"
                    "attempt_fingerprint) VALUES "
                    "(:id,:job,:attempt,:generation,:processor,:profile,:input,:output,:status,"
                    ":failure,CAST(:usage AS jsonb),:started,:completed,:fingerprint)"
                ),
                {
                    "id": attempt_id,
                    "job": job.job_id,
                    "attempt": job.attempt_number,
                    "generation": job.lease_generation,
                    "processor": lease_owner,
                    "profile": TOOL_PROFILE_VERSION,
                    "input": job.input_manifest_digest,
                    "output": output_digest,
                    "status": state,
                    "failure": failure_code,
                    "usage": json.dumps(output, ensure_ascii=False),
                    "started": started_at,
                    "completed": completed_at,
                    "fingerprint": attempt_fingerprint,
                },
            )
            session.execute(
                sa.text(
                    "UPDATE platform.ntd_processing_jobs SET state=:state,heartbeat_at=:completed,"
                    "completed_at=:completed,lease_owner=NULL,lease_expires_at=NULL,"
                    "typed_failure_code=:failure,terminal_receipt_fingerprint=:receipt WHERE "
                    "ntd_processing_job_id=:id"
                ),
                {
                    "id": job.job_id,
                    "state": state,
                    "completed": completed_at,
                    "failure": failure_code,
                    "receipt": terminal_fingerprint,
                },
            )
        return NtdJobTerminalResult(job.job_id, state, failure_code, terminal_fingerprint)

    def reconcile_expired(self, *, reconciled_at: datetime) -> int:
        with Session(self._engine) as session, session.begin():
            rows = (
                session.execute(
                    sa.text(
                        "SELECT ntd_processing_job_id,attempt_count,lease_generation,"
                        "input_manifest_digest FROM platform.ntd_processing_jobs WHERE "
                        "state IN ('leased','running') AND lease_expires_at<:now FOR UPDATE"
                    ),
                    {"now": reconciled_at},
                )
                .mappings()
                .all()
            )
            for row in rows:
                receipt = digest_of(
                    {
                        "schema": "ntd-processing-stale-lease-v1",
                        "job_id": row["ntd_processing_job_id"],
                        "attempt_count": row["attempt_count"],
                        "lease_generation": row["lease_generation"],
                        "input_digest": row["input_manifest_digest"],
                        "state": "reconciliation_required",
                    }
                )
                session.execute(
                    sa.text(
                        "UPDATE platform.ntd_processing_jobs SET state='reconciliation_required',"
                        "completed_at=:now,heartbeat_at=:now,lease_owner=NULL,"
                        "lease_expires_at=NULL,typed_failure_code='NTD_PROCESSING_STALE_LEASE',"
                        "terminal_receipt_fingerprint=:receipt WHERE ntd_processing_job_id=:id"
                    ),
                    {"id": row["ntd_processing_job_id"], "now": reconciled_at, "receipt": receipt},
                )
        return len(rows)

    def reconcile_duplicate_page_jobs(self, *, reconciled_at: datetime) -> int:
        """Fence later page-version jobs when a stable page already has a job."""

        with Session(self._engine) as session, session.begin():
            rows = (
                session.execute(
                    sa.text(
                        "SELECT later.ntd_processing_job_id,later.input_manifest_digest,"
                        "split_part(later.idempotency_key,':',2) page_identity FROM "
                        "platform.ntd_processing_jobs later WHERE later.state='queued' AND EXISTS "
                        "(SELECT 1 FROM platform.ntd_processing_jobs earlier WHERE "
                        "earlier.ntd_processing_job_id<>later.ntd_processing_job_id AND "
                        "split_part(earlier.idempotency_key,':',2)="
                        "split_part(later.idempotency_key,':',2) AND "
                        "split_part(earlier.idempotency_key,':',4)="
                        "split_part(later.idempotency_key,':',4) AND "
                        "(earlier.attempt_count>0 OR earlier.created_at<later.created_at)) "
                        "FOR UPDATE"
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                receipt = digest_of(
                    {
                        "schema": "ntd-processing-duplicate-page-job-v1",
                        "job_id": row["ntd_processing_job_id"],
                        "page_identity": row["page_identity"],
                        "input_digest": row["input_manifest_digest"],
                        "state": "reconciliation_required",
                        "failure_code": "NTD_PROCESSING_DUPLICATE_PAGE_IDENTITY",
                    }
                )
                session.execute(
                    sa.text(
                        "UPDATE platform.ntd_processing_jobs SET "
                        "state='reconciliation_required',completed_at=:now,heartbeat_at=:now,"
                        "typed_failure_code='NTD_PROCESSING_DUPLICATE_PAGE_IDENTITY',"
                        "terminal_receipt_fingerprint=:receipt WHERE ntd_processing_job_id=:id"
                    ),
                    {
                        "id": row["ntd_processing_job_id"],
                        "now": reconciled_at,
                        "receipt": receipt,
                    },
                )
        return len(rows)

    def cancel_queued_for_unqualified_profile(self, *, cancelled_at: datetime) -> int:
        """Fail closed when the external-recovery profile has not qualified.

        Cancellation is intentionally limited to never-attempted queued jobs for the
        exact versioned profile. Jobs with an observed or outcome-unknown provider
        interaction retain their individual terminal result.
        """

        with Session(self._engine) as session, session.begin():
            rows = (
                session.execute(
                    sa.text(
                        "SELECT ntd_processing_job_id,input_manifest_digest,idempotency_key "
                        "FROM platform.ntd_processing_jobs WHERE stage='selective_recovery' "
                        "AND state='queued' AND attempt_count=0 AND "
                        "split_part(idempotency_key,':',4)='polza-public-ntd-page-v0.1' "
                        "FOR UPDATE"
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                receipt = digest_of(
                    {
                        "schema": "ntd-processing-profile-cancellation-v1",
                        "job_id": row["ntd_processing_job_id"],
                        "idempotency_key": row["idempotency_key"],
                        "input_digest": row["input_manifest_digest"],
                        "state": "cancelled",
                        "failure_code": "POLZA_BATCH_PROFILE_NOT_QUALIFIED",
                    }
                )
                session.execute(
                    sa.text(
                        "UPDATE platform.ntd_processing_jobs SET state='cancelled',"
                        "cancellation_state='acknowledged',completed_at=:at,heartbeat_at=:at,"
                        "typed_failure_code='POLZA_BATCH_PROFILE_NOT_QUALIFIED',"
                        "terminal_receipt_fingerprint=:receipt WHERE ntd_processing_job_id=:id"
                    ),
                    {
                        "id": row["ntd_processing_job_id"],
                        "at": cancelled_at,
                        "receipt": receipt,
                    },
                )
        return len(rows)


def terminal_state_for_failure(code: str) -> str:
    return "reconciliation_required" if code in OUTCOME_UNKNOWN_FAILURES else "failed"


def utc_now() -> datetime:
    return datetime.now(UTC)
