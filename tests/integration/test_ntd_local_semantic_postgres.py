from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import sqlalchemy as sa

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.ntd.local_semantic import (
    LOCAL_NTD_PROVISION_PROFILE,
    LocalNtdProvisionInput,
    LocalNtdProvisionJob,
    LocalNtdProvisionRepository,
    LocalNtdProvisionWorker,
)
from asd_kontur.ntd.models import NormativeProvisionCandidate, NormativeProvisionKind
from asd_kontur.ntd.postgres import NtdRepository

from .conftest import PostgreSQLEnvironment
from .test_ntd_seed import SeededNtd, _seed_ntd

pytestmark = pytest.mark.postgres


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _semantics() -> dict[str, object]:
    return {
        "normalized_proposition": {"text": "Исполнитель должен вести журнал."},
        "subject": {"kind": "исполнитель"},
        "predicate": {"action": "вести"},
        "object_value": {"document": "журнал"},
        "modality": "mandatory",
        "conditions": {},
        "exclusions": {},
        "applicability": {"work": "монолитные работы"},
        "units_dimensions": {},
        "referenced_designations": [],
        "uncertainty_codes": [],
    }


def _candidate(
    *, candidate_id: UUID, version: int, seeded: SeededNtd, text: str
) -> NormativeProvisionCandidate:
    return NormativeProvisionCandidate(
        candidate_id,
        version,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        f"7.{version}",
        NormativeProvisionKind.CLAUSE,
        7,
        (0.1, 0.1, 0.9, 0.2),
        text,
        "native_pdf_layout",
        "synthetic-local-ntd-input@1.0.0",
        _digest(text),
        None,
    )


def _resolution(environment: PostgreSQLEnvironment, seeded: SeededNtd) -> UUID:
    decision_id = uuid7()
    reconciliation_id = uuid7()
    resolution_id = uuid7()
    now = datetime.now(UTC)
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_seed_remediation_decisions "
                "(remediation_decision_id,version,prior_seed_manifest_id,"
                "prior_seed_manifest_version,logical_manifest_fingerprint,decision_key,status,"
                "reopened_defect_codes,reason,canonical_commit,environment_fingerprint,"
                "prior_receipt_fingerprints,supersedes_version,decision_fingerprint,decided_at) "
                "VALUES (:id,1,:manifest,1,:manifest_fingerprint,:key,'in_progress',ARRAY['TEST'],"
                "'synthetic queue fixture',:commit,:environment,ARRAY[]::text[],NULL,"
                ":fingerprint,:now)"
            ),
            {
                "id": decision_id,
                "manifest": seeded.seed_manifest_id,
                "manifest_fingerprint": seeded.seed_manifest_fingerprint,
                "key": f"synthetic-local-ntd-{decision_id}",
                "commit": "0" * 40,
                "environment": _digest(f"environment:{decision_id}"),
                "fingerprint": _digest(f"decision:{decision_id}"),
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_seed_identity_reconciliations "
                "(identity_reconciliation_id,remediation_decision_id,"
                "remediation_decision_version,legacy_stable_identity_key,"
                "canonical_stable_identity_key,practice_guide_reference_ids,"
                "printed_designations,identity_status,decision_basis,"
                "reconciliation_fingerprint,recorded_at) VALUES "
                "(:id,:decision,1,:legacy,:canonical,ARRAY[:reference]::uuid[],ARRAY[:designation],"
                "'resolved','{}'::jsonb,:fingerprint,:now)"
            ),
            {
                "id": reconciliation_id,
                "decision": decision_id,
                "legacy": seeded.stable_identity_key,
                "canonical": seeded.stable_identity_key,
                "reference": seeded.guide_reference_id,
                "designation": seeded.stable_designation,
                "fingerprint": _digest(f"reconciliation:{reconciliation_id}"),
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_identity_resolution_versions "
                "(identity_resolution_id,version,identity_reconciliation_id,provider,"
                "transport_profile,resolution_status,normative_document_id,normative_edition_id,"
                "normative_artifact_ids,diagnostic,environment_fingerprint,supersedes_version,"
                "resolution_fingerprint,recorded_at) VALUES "
                "(:id,1,:reconciliation,'minstroy_catalogue','direct','parsed_verified',:document,"
                ":edition,ARRAY[:artifact]::uuid[],'{}'::jsonb,:environment,NULL,:fingerprint,:now)"
            ),
            {
                "id": resolution_id,
                "reconciliation": reconciliation_id,
                "document": seeded.document_id,
                "edition": seeded.edition_id,
                "artifact": seeded.artifact_id,
                "environment": _digest(f"environment:{resolution_id}"),
                "fingerprint": _digest(f"resolution:{resolution_id}"),
                "now": now,
            },
        )
    return reconciliation_id


def _insert_job(
    environment: PostgreSQLEnvironment,
    *,
    identity_id: UUID,
    artifact_id: UUID,
    key: str,
    state: str,
    priority: int,
) -> UUID:
    job_id = deterministic_uuid(f"ntd-processing-job:{key}")
    now = datetime.now(UTC)
    terminal = _digest(f"terminal:{key}") if state == "succeeded" else None
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_processing_jobs "
                "(ntd_processing_job_id,identity_reconciliation_id,normative_artifact_id,stage,"
                "input_manifest_digest,idempotency_key,state,priority,eligible_at,attempt_count,"
                "max_attempts,retry_policy_version,terminal_receipt_fingerprint,created_at) VALUES "
                "(:id,:identity,:artifact,'provision_extraction',:digest,:key,:state,:priority,:now,"
                "0,3,'synthetic-test@1.0.0',:terminal,:now)"
            ),
            {
                "id": job_id,
                "identity": identity_id,
                "artifact": artifact_id,
                "digest": _digest(f"input:{key}"),
                "key": key,
                "state": state,
                "priority": priority,
                "now": now,
                "terminal": terminal,
            },
        )
    return job_id


def test_local_ntd_queue_is_outstanding_bounded_and_claim_namespace_is_fenced(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    identity = _resolution(postgres_environment, seeded)
    candidate_id = uuid7()
    text = "Исполнитель должен вести журнал производства работ. " * 4
    NtdRepository(postgres_environment.ntd_ingestion_engine).register_provision_candidate(
        _candidate(candidate_id=candidate_id, version=1, seeded=seeded, text=text)
    )
    _insert_job(
        postgres_environment,
        identity_id=identity,
        artifact_id=seeded.artifact_id,
        key=f"ntd-local-provision:{uuid7()}:1:{LOCAL_NTD_PROVISION_PROFILE}",
        state="succeeded",
        priority=50,
    )
    foreign_job = _insert_job(
        postgres_environment,
        identity_id=identity,
        artifact_id=seeded.artifact_id,
        key=f"another-worker:{uuid7()}:1:foreign-profile@1.0.0",
        state="queued",
        priority=0,
    )
    repository = LocalNtdProvisionRepository(postgres_environment.owner_engine)

    refill = repository.enqueue_bounded(eligible_at=datetime.now(UTC), limit=1, profile_cap=1)

    assert (refill.eligible, refill.inserted, refill.outstanding, refill.reason) == (
        1,
        1,
        1,
        "enqueued",
    )
    claimed = repository.claim_next(
        lease_owner="identity.synthetic.local-ntd",
        claimed_at=datetime.now(UTC),
        lease_duration=timedelta(minutes=5),
    )
    assert claimed is not None
    assert claimed.chunk_id == candidate_id
    assert claimed.job_id != foreign_job


def test_local_ntd_preserves_candidate_version_and_reuses_crash_window_result(
    postgres_environment: PostgreSQLEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    identity = _resolution(postgres_environment, seeded)
    candidate_id = uuid7()
    text_v1 = "Работы следует выполнять по проекту производства работ. " * 3
    text_v2 = "Исполнитель должен вести журнал бетонных работ. " * 4
    repository_writer = NtdRepository(postgres_environment.ntd_ingestion_engine)
    repository_writer.register_provision_candidate(
        _candidate(candidate_id=candidate_id, version=1, seeded=seeded, text=text_v1)
    )
    repository_writer.register_provision_candidate(
        _candidate(candidate_id=candidate_id, version=2, seeded=seeded, text=text_v2)
    )
    key = f"ntd-local-provision:{candidate_id}:2:{LOCAL_NTD_PROVISION_PROFILE}"
    job_id = _insert_job(
        postgres_environment,
        identity_id=identity,
        artifact_id=seeded.artifact_id,
        key=key,
        state="queued",
        priority=50,
    )
    repository = LocalNtdProvisionRepository(postgres_environment.owner_engine)
    claimed = repository.claim_next(
        lease_owner="crashed-worker",
        claimed_at=datetime.now(UTC),
        lease_duration=timedelta(seconds=-1),
    )
    assert claimed is not None and claimed.job_id == job_id
    item = repository.load_input(claimed)
    persisted = repository.persist_candidate(
        item=item,
        semantics=_semantics(),
        job=claimed,
        completed_at=datetime.now(UTC),
    )
    assert persisted.candidate_version == 2
    assert repository.recover_expired_local_leases(recovered_at=datetime.now(UTC)) == 1

    def _must_not_repeat_inference(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("accepted semantics must be reused after the crash window")

    monkeypatch.setattr("asd_kontur.ntd.local_semantic._complete", _must_not_repeat_inference)
    output = LocalNtdProvisionWorker(
        postgres_environment.owner_engine,
        qwen_url="http://127.0.0.1:1/generate",
        identity="replacement-worker",
    ).process_one()

    assert output is not None
    assert output["candidate_version"] == 2
    assert output["reused_persisted_semantics_after_crash"] is True
    with postgres_environment.owner_engine.connect() as connection:
        state = connection.execute(
            sa.text(
                "SELECT state,attempt_count FROM platform.ntd_processing_jobs WHERE "
                "ntd_processing_job_id=:id"
            ),
            {"id": job_id},
        ).one()
        versions = connection.scalars(
            sa.text(
                "SELECT candidate_version FROM platform.normative_provision_semantics WHERE "
                "provision_candidate_id=:id ORDER BY candidate_version"
            ),
            {"id": candidate_id},
        ).all()
    assert state == ("succeeded", 2)
    assert versions == [2]


def test_local_ntd_uses_qwen_kind_for_a_new_native_chunk(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    identity = _resolution(postgres_environment, seeded)
    text = "Форма акта содержит обязательные реквизиты и подписи участников. " * 3
    chunk_id = uuid7()
    item = LocalNtdProvisionInput(
        chunk_id,
        1,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        seeded.stable_designation,
        "official_binding_recovered",
        "Приложение 3",
        12,
        (),
        text,
        _digest(text),
        "other",
        None,
    )
    job = LocalNtdProvisionJob(
        uuid7(), identity, seeded.artifact_id, chunk_id, 1, _digest("input"), 1, 1
    )
    semantics = {"provision_kind": "form", **_semantics()}

    persisted = LocalNtdProvisionRepository(postgres_environment.owner_engine).persist_candidate(
        item=item,
        semantics=semantics,
        job=job,
        completed_at=datetime.now(UTC),
    )

    with postgres_environment.owner_engine.connect() as connection:
        kind = connection.scalar(
            sa.text(
                "SELECT provision_kind FROM platform.normative_provision_candidates WHERE "
                "provision_candidate_id=:id AND candidate_version=:version"
            ),
            {"id": persisted.candidate_id, "version": persisted.candidate_version},
        )
    assert kind == "form"
