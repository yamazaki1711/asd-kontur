# ruff: noqa: E501, RUF001 -- bounded SQL and Russian model prompts are intentionally literal.
"""Durable bounded local-Qwen interpretation of already admitted NTD chunks."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.document_understanding.qwen_semantic import (
    QwenSemanticFailure,
    _complete,
)
from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .processing_jobs import NtdProcessingJobRepository, NtdRasterRecoveryJob

LOCAL_NTD_PROVISION_PROFILE = "local-qwen-ntd-provision@1.0.0"
LOCAL_NTD_PROMPT_VERSION = "local-qwen-ntd-provision-prompt@1.0.0"
LOCAL_NTD_SCHEMA_VERSION = "normative-provision-semantics@1.0.0"
LOCAL_NTD_MODEL = "Qwen3.8-27B-MLX-8bit"
_MODALITIES = frozenset(
    {
        "mandatory",
        "prohibition",
        "permission",
        "recommendation",
        "definition",
        "condition",
        "exception",
        "procedure",
        "deadline",
        "tolerance",
        "formula",
        "reference",
        "amendment",
    }
)
_PROVISION_KINDS = frozenset(
    {"section", "clause", "subclause", "table", "appendix", "form", "definition", "other"}
)


@dataclass(frozen=True, slots=True)
class LocalNtdProvisionJob:
    job_id: UUID
    identity_reconciliation_id: UUID
    normative_artifact_id: UUID
    chunk_id: UUID
    chunk_version: int
    input_manifest_digest: str
    attempt_number: int
    lease_generation: int


@dataclass(frozen=True, slots=True)
class LocalNtdProvisionInput:
    chunk_id: UUID
    chunk_version: int
    normative_edition_id: UUID
    source_version_id: UUID
    designation: str
    authority_class: str
    structural_path: str
    page_number: int
    source_locator_ids: tuple[UUID, ...]
    raw_text: str
    raw_text_digest: str
    provision_kind: str
    existing_candidate_id: UUID | None = None


class LocalNtdProvisionRepository:
    """Idempotent producer/consumer for the existing NTD durable queue."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def enqueue_bounded(
        self, *, eligible_at: datetime, limit: int, profile_cap: int
    ) -> tuple[int, int]:
        if limit < 1 or profile_cap < 1:
            raise ValueError("local_ntd_queue_bound_invalid")
        with Session(self._engine) as session, session.begin():
            existing = int(
                session.scalar(
                    sa.text(
                        "SELECT count(*) FROM platform.ntd_processing_jobs WHERE stage="
                        "'provision_extraction' AND idempotency_key LIKE :profile"
                    ),
                    {"profile": f"%:{LOCAL_NTD_PROVISION_PROFILE}"},
                )
                or 0
            )
            allowance = min(limit, max(0, profile_cap - existing))
            if allowance == 0:
                return 0, 0
            candidate_rows = list(
                session.execute(
                    sa.text(
                        "SELECT candidate.provision_candidate_id chunk_id,"
                        "candidate.candidate_version version,candidate.content_digest "
                        "raw_text_digest,candidate.normative_edition_id,artifact.normative_artifact_id,"
                        "resolution.identity_reconciliation_id FROM "
                        "platform.normative_provision_candidates candidate JOIN "
                        "platform.normative_artifacts artifact ON artifact.normative_edition_id="
                        "candidate.normative_edition_id JOIN LATERAL (SELECT "
                        "value.identity_reconciliation_id FROM "
                        "platform.ntd_identity_resolution_versions value WHERE "
                        "artifact.normative_artifact_id=ANY(value.normative_artifact_ids) ORDER BY "
                        "value.recorded_at DESC,value.version DESC LIMIT 1) resolution ON true "
                        "LEFT JOIN platform.normative_provision_semantics semantics ON "
                        "semantics.provision_candidate_id=candidate.provision_candidate_id AND "
                        "semantics.candidate_version=candidate.candidate_version WHERE "
                        "semantics.provision_candidate_id IS NULL AND length(candidate.verbatim_text) "
                        "BETWEEN 120 AND 6000 AND NOT EXISTS (SELECT 1 FROM "
                        "platform.ntd_processing_jobs job WHERE job.stage='provision_extraction' AND "
                        "job.idempotency_key=:prefix||candidate.provision_candidate_id::text||':'||"
                        "candidate.candidate_version::text||':'||:profile_version) ORDER BY "
                        "candidate.created_at,candidate.provision_candidate_id LIMIT :limit"
                    ),
                    {
                        "prefix": "ntd-local-provision:",
                        "profile_version": LOCAL_NTD_PROVISION_PROFILE,
                        "limit": allowance,
                    },
                ).mappings()
            )
            rows: list[Any] = list(candidate_rows)
            allowance -= len(rows)
            chunk_rows = list(
                session.execute(
                    sa.text(
                        "SELECT chunk.chunk_id,chunk.version,chunk.raw_text_digest,"
                        "chunk.normative_edition_id,object.normative_artifact_id,"
                        "resolution.identity_reconciliation_id FROM platform.ntd_chunks chunk "
                        "JOIN platform.ntd_corpus_objects object ON object.corpus_object_id="
                        "chunk.corpus_object_id JOIN LATERAL (SELECT value.identity_reconciliation_id "
                        "FROM platform.ntd_identity_resolution_versions value WHERE "
                        "object.normative_artifact_id=ANY(value.normative_artifact_ids) ORDER BY "
                        "value.recorded_at DESC,value.version DESC LIMIT 1) resolution ON true WHERE "
                        "chunk.normative_edition_id IS NOT NULL AND chunk.page_start=chunk.page_end AND "
                        "length(chunk.raw_text) BETWEEN 120 AND 6000 AND chunk.raw_text ~* "
                        ":modal AND NOT EXISTS (SELECT 1 FROM platform.normative_provision_candidates "
                        "candidate WHERE candidate.normative_edition_id=chunk.normative_edition_id AND "
                        "candidate.source_version_id=chunk.source_version_id AND "
                        "candidate.structural_path=chunk.structural_path AND "
                        "candidate.content_digest=chunk.raw_text_digest) AND NOT EXISTS (SELECT 1 FROM "
                        "platform.ntd_processing_jobs job WHERE job.stage='provision_extraction' AND "
                        "job.idempotency_key=:prefix||chunk.chunk_id::text||':'||chunk.version::text||"
                        "':'||:profile_version) ORDER BY (chunk.authority_class='official') DESC,"
                        "chunk.corpus_object_id,chunk.ordinal LIMIT :limit"
                    ),
                    {
                        "modal": r"должен|должна|должны|следует|не допускается|требуется|допускается",
                        "prefix": "ntd-local-provision:",
                        "profile_version": LOCAL_NTD_PROVISION_PROFILE,
                        "limit": max(0, allowance),
                    },
                ).mappings()
            )
            rows.extend(chunk_rows)
            inserted = 0
            for row in rows:
                manifest = {
                    "schema": "local-ntd-provision-job-input-v1",
                    "chunk_id": str(row["chunk_id"]),
                    "chunk_version": int(row["version"]),
                    "raw_text_digest": str(row["raw_text_digest"]),
                    "model": LOCAL_NTD_MODEL,
                    "profile": LOCAL_NTD_PROVISION_PROFILE,
                    "prompt": LOCAL_NTD_PROMPT_VERSION,
                    "output_schema": LOCAL_NTD_SCHEMA_VERSION,
                }
                input_digest = digest_of(manifest)
                key = (
                    f"ntd-local-provision:{row['chunk_id']}:{row['version']}:"
                    f"{LOCAL_NTD_PROVISION_PROFILE}"
                )
                job_id = deterministic_uuid(f"ntd-processing-job:{key}")
                result = session.execute(
                    sa.text(
                        "INSERT INTO platform.ntd_processing_jobs "
                        "(ntd_processing_job_id,identity_reconciliation_id,normative_artifact_id,"
                        "stage,input_manifest_digest,idempotency_key,state,priority,eligible_at,"
                        "attempt_count,max_attempts,retry_policy_version,created_at) VALUES "
                        "(:id,:identity,:artifact,'provision_extraction',:digest,:key,'queued',50,"
                        ":eligible,0,3,'local-qwen-bounded-v1',:eligible) ON CONFLICT "
                        "(idempotency_key) DO NOTHING"
                    ),
                    {
                        "id": job_id,
                        "identity": row["identity_reconciliation_id"],
                        "artifact": row["normative_artifact_id"],
                        "digest": input_digest,
                        "key": key,
                        "eligible": eligible_at,
                    },
                )
                inserted += int(getattr(result, "rowcount", 0) or 0)
        return len(rows), inserted

    def claim_next(
        self, *, lease_owner: str, claimed_at: datetime, lease_duration: timedelta
    ) -> LocalNtdProvisionJob | None:
        with Session(self._engine) as session, session.begin():
            row = (
                session.execute(
                    sa.text(
                        "SELECT ntd_processing_job_id,identity_reconciliation_id,"
                        "normative_artifact_id,input_manifest_digest,attempt_count,lease_generation,"
                        "split_part(idempotency_key,':',2)::uuid chunk_id,"
                        "split_part(idempotency_key,':',3)::bigint chunk_version FROM "
                        "platform.ntd_processing_jobs WHERE stage='provision_extraction' AND "
                        "state='queued' AND eligible_at<=:now AND attempt_count<max_attempts ORDER BY "
                        "priority,eligible_at,ntd_processing_job_id FOR UPDATE SKIP LOCKED LIMIT 1"
                    ),
                    {"now": claimed_at},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            generation = int(row["lease_generation"]) + 1
            attempt = int(row["attempt_count"]) + 1
            session.execute(
                sa.text(
                    "UPDATE platform.ntd_processing_jobs SET state='running',started_at="
                    "COALESCE(started_at,:now),heartbeat_at=:now,attempt_count=:attempt,"
                    "lease_owner=:owner,lease_generation=:generation,lease_expires_at=:expires "
                    "WHERE ntd_processing_job_id=:id"
                ),
                {
                    "id": row["ntd_processing_job_id"],
                    "now": claimed_at,
                    "attempt": attempt,
                    "owner": lease_owner,
                    "generation": generation,
                    "expires": claimed_at + lease_duration,
                },
            )
        return LocalNtdProvisionJob(
            UUID(str(row["ntd_processing_job_id"])),
            UUID(str(row["identity_reconciliation_id"])),
            UUID(str(row["normative_artifact_id"])),
            UUID(str(row["chunk_id"])),
            int(row["chunk_version"]),
            str(row["input_manifest_digest"]),
            attempt,
            generation,
        )

    def load_input(self, job: LocalNtdProvisionJob) -> LocalNtdProvisionInput:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT candidate.provision_candidate_id chunk_id,"
                        "candidate.candidate_version version,candidate.normative_edition_id,"
                        "candidate.source_version_id,document.designation stable_designation,"
                        "'normative_authority' authority_class,candidate.structural_path,"
                        "candidate.page_number page_start,ARRAY[]::uuid[] source_locator_ids,"
                        "candidate.verbatim_text raw_text,candidate.content_digest raw_text_digest,"
                        "candidate.provision_kind FROM platform.normative_provision_candidates "
                        "candidate JOIN platform.normative_editions edition ON "
                        "edition.normative_edition_id=candidate.normative_edition_id JOIN "
                        "platform.normative_documents document ON document.normative_document_id="
                        "edition.normative_document_id WHERE candidate.provision_candidate_id=:chunk "
                        "AND candidate.candidate_version=:version"
                    ),
                    {"chunk": job.chunk_id, "version": job.chunk_version},
                )
                .mappings()
                .one_or_none()
            )
            existing_candidate_id = job.chunk_id if row is not None else None
            if row is None:
                row = (
                    connection.execute(
                        sa.text(
                            "SELECT chunk.chunk_id,chunk.version,chunk.normative_edition_id,"
                            "chunk.source_version_id,object.stable_designation,chunk.authority_class,"
                            "chunk.structural_path,chunk.page_start,chunk.source_locator_ids,"
                            "chunk.raw_text,chunk.raw_text_digest,'other' provision_kind FROM "
                            "platform.ntd_chunks chunk JOIN "
                            "platform.ntd_corpus_objects object ON object.corpus_object_id="
                            "chunk.corpus_object_id WHERE chunk.chunk_id=:chunk AND chunk.version=:version"
                        ),
                        {"chunk": job.chunk_id, "version": job.chunk_version},
                    )
                    .mappings()
                    .one()
                )
        return LocalNtdProvisionInput(
            UUID(str(row["chunk_id"])),
            int(row["version"]),
            UUID(str(row["normative_edition_id"])),
            UUID(str(row["source_version_id"])),
            str(row["stable_designation"]),
            str(row["authority_class"]),
            str(row["structural_path"]),
            int(row["page_start"]),
            tuple(UUID(str(value)) for value in row["source_locator_ids"]),
            str(row["raw_text"]),
            str(row["raw_text_digest"]),
            str(row["provision_kind"]),
            existing_candidate_id,
        )

    def persist_candidate(
        self,
        *,
        item: LocalNtdProvisionInput,
        semantics: dict[str, Any],
        job: LocalNtdProvisionJob,
        completed_at: datetime,
    ) -> tuple[UUID, str]:
        candidate_id = item.existing_candidate_id or deterministic_uuid(
            f"local-ntd-provision:{item.normative_edition_id}:{item.source_version_id}:"
            f"{item.structural_path}:{item.raw_text_digest}:{LOCAL_NTD_PROVISION_PROFILE}"
        )
        model_provenance = {
            "model": LOCAL_NTD_MODEL,
            "profile_version": LOCAL_NTD_PROVISION_PROFILE,
            "prompt_version": LOCAL_NTD_PROMPT_VERSION,
            "schema_version": LOCAL_NTD_SCHEMA_VERSION,
            "job_id": str(job.job_id),
            "input_manifest_digest": job.input_manifest_digest,
            "source_locator_ids": [str(value) for value in item.source_locator_ids],
            "authority_class": item.authority_class,
            "candidate_authority": "unverified_model_interpretation",
        }
        semantics_fingerprint = digest_of(
            {
                "schema": LOCAL_NTD_SCHEMA_VERSION,
                "candidate_id": candidate_id,
                "candidate_version": 1,
                "semantics": semantics,
                "model_provenance": model_provenance,
            }
        )
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_candidates "
                    "(provision_candidate_id,candidate_version,normative_edition_id,source_version_id,"
                    "structural_path,provision_kind,page_number,region,verbatim_text,extraction_method,"
                    "extraction_profile_version,content_digest,model_provenance) VALUES "
                    "(:id,1,:edition,:source,:path,:kind,:page,ARRAY[0.0,0.0,1.0,1.0],:text,"
                    "'native_pdf_layout',:profile,:digest,CAST(:model AS jsonb)) ON CONFLICT "
                    "(provision_candidate_id,candidate_version) DO NOTHING"
                ),
                {
                    "id": candidate_id,
                    "edition": item.normative_edition_id,
                    "source": item.source_version_id,
                    "path": item.structural_path,
                    "kind": item.provision_kind,
                    "page": item.page_number,
                    "text": item.raw_text,
                    "profile": LOCAL_NTD_PROVISION_PROFILE,
                    "digest": item.raw_text_digest,
                    "model": json.dumps(model_provenance, ensure_ascii=False),
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_semantics "
                    "(provision_candidate_id,candidate_version,normalized_proposition,subject,"
                    "predicate,object_value,modality,conditions,exclusions,applicability,"
                    "units_dimensions,referenced_designations,uncertainty_codes,"
                    "semantics_fingerprint,recorded_at) VALUES "
                    "(:id,1,CAST(:proposition AS jsonb),CAST(:subject AS jsonb),"
                    "CAST(:predicate AS jsonb),CAST(:object AS jsonb),:modality,"
                    "CAST(:conditions AS jsonb),CAST(:exclusions AS jsonb),"
                    "CAST(:applicability AS jsonb),CAST(:units AS jsonb),:references,"
                    ":uncertainties,:fingerprint,:recorded) ON CONFLICT "
                    "(provision_candidate_id,candidate_version) DO NOTHING"
                ),
                {
                    "id": candidate_id,
                    "proposition": json.dumps(
                        semantics["normalized_proposition"], ensure_ascii=False
                    ),
                    "subject": json.dumps(semantics["subject"], ensure_ascii=False),
                    "predicate": json.dumps(semantics["predicate"], ensure_ascii=False),
                    "object": json.dumps(semantics["object_value"], ensure_ascii=False),
                    "modality": semantics["modality"],
                    "conditions": json.dumps(semantics["conditions"], ensure_ascii=False),
                    "exclusions": json.dumps(semantics["exclusions"], ensure_ascii=False),
                    "applicability": json.dumps(semantics["applicability"], ensure_ascii=False),
                    "units": json.dumps(semantics["units_dimensions"], ensure_ascii=False),
                    "references": semantics["referenced_designations"],
                    "uncertainties": semantics["uncertainty_codes"],
                    "fingerprint": semantics_fingerprint,
                    "recorded": completed_at,
                },
            )
        return candidate_id, semantics_fingerprint

    def release_for_foreground(self, job: LocalNtdProvisionJob, *, eligible_at: datetime) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(
                sa.text(
                    "UPDATE platform.ntd_processing_jobs SET state='queued',eligible_at=:eligible,"
                    "attempt_count=GREATEST(attempt_count-1,0),lease_owner=NULL,lease_expires_at=NULL "
                    "WHERE ntd_processing_job_id=:id AND state='running' AND lease_generation=:generation"
                ),
                {"id": job.job_id, "generation": job.lease_generation, "eligible": eligible_at},
            )
        if result.rowcount != 1:
            raise ValueError("local_ntd_job_release_fence_rejected")

    def retry_failed_validation(self, *, eligible_at: datetime, limit: int = 1) -> int:
        """Requeue typed validation failures while preserving immutable attempt rows."""

        with self._engine.begin() as connection:
            result = connection.execute(
                sa.text(
                    "WITH retry AS (SELECT ntd_processing_job_id FROM "
                    "platform.ntd_processing_jobs WHERE stage='provision_extraction' AND "
                    "state='failed' AND attempt_count<max_attempts AND typed_failure_code LIKE "
                    "'local_ntd_semantics_%' ORDER BY completed_at,ntd_processing_job_id LIMIT "
                    ":limit FOR UPDATE) UPDATE platform.ntd_processing_jobs job SET state='queued',"
                    "eligible_at=:eligible,completed_at=NULL,heartbeat_at=NULL,typed_failure_code=NULL,"
                    "terminal_receipt_fingerprint=NULL FROM retry WHERE "
                    "job.ntd_processing_job_id=retry.ntd_processing_job_id"
                ),
                {"eligible": eligible_at, "limit": limit},
            )
        return int(getattr(result, "rowcount", 0) or 0)


class LocalNtdProvisionWorker:
    def __init__(self, engine: Engine, *, qwen_url: str, identity: str) -> None:
        self._repository = LocalNtdProvisionRepository(engine)
        self._terminal = NtdProcessingJobRepository(engine)
        self._qwen_url = qwen_url
        self._identity = identity

    def process_one(self) -> dict[str, Any] | None:
        started = datetime.now(UTC)
        job = self._repository.claim_next(
            lease_owner=self._identity,
            claimed_at=started,
            lease_duration=timedelta(minutes=30),
        )
        if job is None:
            return None
        try:
            item = self._repository.load_input(job)
            answer = _complete(
                self._qwen_url,
                _prompt(item),
                900.0,
                max_tokens=1000,
            )
            semantics = _parse_semantics(answer)
            if semantics["provision_kind"] != item.provision_kind:
                raise QwenSemanticFailure("local_ntd_semantics_provision_kind_conflict")
            completed = datetime.now(UTC)
            candidate_id, semantics_fingerprint = self._repository.persist_candidate(
                item=item,
                semantics=semantics,
                job=job,
                completed_at=completed,
            )
            output = {
                "schema": "local-ntd-provision-job-output-v1",
                "model": LOCAL_NTD_MODEL,
                "profile": LOCAL_NTD_PROVISION_PROFILE,
                "chunk_id": str(item.chunk_id),
                "chunk_version": item.chunk_version,
                "source_version_id": str(item.source_version_id),
                "page_number": item.page_number,
                "candidate_id": str(candidate_id),
                "candidate_version": 1,
                "semantics_fingerprint": semantics_fingerprint,
            }
            self._terminal.terminalize(
                _terminal_job(job, item),
                lease_owner=self._identity,
                state="succeeded",
                failure_code=None,
                output=output,
                started_at=started,
                completed_at=completed,
                tool_profile_version=LOCAL_NTD_PROVISION_PROFILE,
            )
            return output
        except QwenSemanticFailure as exc:
            if exc.code == "qwen_semantic_runtime_unavailable":
                self._repository.release_for_foreground(
                    job, eligible_at=datetime.now(UTC) + timedelta(seconds=60)
                )
                return {"state": "deferred_for_foreground", "job_id": str(job.job_id)}
            completed = datetime.now(UTC)
            self._terminal.terminalize(
                _terminal_job(job, None),
                lease_owner=self._identity,
                state="failed",
                failure_code=exc.code,
                output={"schema": "local-ntd-provision-job-output-v1", "failure": exc.code},
                started_at=started,
                completed_at=completed,
                tool_profile_version=LOCAL_NTD_PROVISION_PROFILE,
            )
            return {"state": "failed", "job_id": str(job.job_id), "failure": exc.code}

    def run_forever(self, *, refill_limit: int = 2, profile_cap: int = 20) -> None:
        while True:
            self._repository.enqueue_bounded(
                eligible_at=datetime.now(UTC), limit=refill_limit, profile_cap=profile_cap
            )
            result = self.process_one()
            time.sleep(2 if result is not None else 30)


def _terminal_job(
    job: LocalNtdProvisionJob, item: LocalNtdProvisionInput | None
) -> NtdRasterRecoveryJob:
    return NtdRasterRecoveryJob(
        job.job_id,
        job.identity_reconciliation_id,
        job.normative_artifact_id,
        deterministic_uuid(f"ntd-local-provision-placeholder:{job.chunk_id}"),
        job.chunk_version,
        item.designation if item is not None else "unknown",
        item.page_number if item is not None else 0,
        job.input_manifest_digest,
        job.attempt_number,
        job.lease_generation,
    )


def _prompt(item: LocalNtdProvisionInput) -> str:
    return (
        "Ты извлекаешь только семантику одного дословного фрагмента нормативного документа. "
        "Не изменяй и не дополняй норму. Верни ровно один JSON-объект со всеми ключами: "
        '"provision_kind", "normalized_proposition", "subject", "predicate", '
        '"object_value", "modality", "conditions", "exclusions", "applicability", '
        '"units_dimensions", "referenced_designations", "uncertainty_codes". '
        "provision_kind: section|clause|subclause|table|appendix|form|definition|other. "
        "modality: mandatory|prohibition|permission|recommendation|definition|condition|"
        "exception|procedure|deadline|tolerance|formula|reference|amendment. "
        "Поля normalized_proposition/subject/predicate/object_value/conditions/exclusions/"
        "applicability/units_dimensions должны быть JSON-объектами, даже когда они пусты; "
        "referenced_designations и uncertainty_codes — массивами строк. Используй эту точную "
        "форму, не заменяй объекты массивами: "
        '{"provision_kind":"clause","normalized_proposition":{},"subject":{},'
        '"predicate":{},"object_value":{},"modality":"mandatory","conditions":{},'
        '"exclusions":{},"applicability":{},"units_dimensions":{},'
        '"referenced_designations":[],"uncertainty_codes":[]}. '
        "Если смысл неоднозначен, запиши код неопределённости, не угадывай.\n"
        + json.dumps(
            {
                "designation": item.designation,
                "structural_path": item.structural_path,
                "page_number": item.page_number,
                "verbatim_text": item.raw_text,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _parse_semantics(answer: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", answer, re.DOTALL)
    if match is None:
        raise QwenSemanticFailure("local_ntd_semantics_invalid_json")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("local_ntd_semantics_invalid_json") from exc
    required = {
        "provision_kind",
        "normalized_proposition",
        "subject",
        "predicate",
        "object_value",
        "modality",
        "conditions",
        "exclusions",
        "applicability",
        "units_dimensions",
        "referenced_designations",
        "uncertainty_codes",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise QwenSemanticFailure("local_ntd_semantics_invalid_shape")
    if value["provision_kind"] not in _PROVISION_KINDS or value["modality"] not in _MODALITIES:
        raise QwenSemanticFailure("local_ntd_semantics_invalid_enum")
    for key in (
        "normalized_proposition",
        "subject",
        "predicate",
        "object_value",
        "conditions",
        "exclusions",
        "applicability",
        "units_dimensions",
    ):
        if not isinstance(value[key], dict):
            raise QwenSemanticFailure("local_ntd_semantics_invalid_shape")
    for key in ("referenced_designations", "uncertainty_codes"):
        if not isinstance(value[key], list) or not all(
            isinstance(item, str) for item in value[key]
        ):
            raise QwenSemanticFailure("local_ntd_semantics_invalid_shape")
    return value
