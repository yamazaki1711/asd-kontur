from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.knowledge import InMemoryObjectStore
from asd_kontur.knowledge.gateway import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayStatus,
    KnowledgeGateway,
)
from asd_kontur.knowledge.postgres import PostgresKnowledgeAudit, PostgresKnowledgeQuery
from asd_kontur.knowledge.source_ledger import PlatformSourceAdmission, PlatformSourceLedger
from asd_kontur.practice_guidance.models import (
    GuidanceCandidateVersion,
    GuidanceCuratorAuthority,
    GuidanceKind,
    GuidanceVerification,
    GuideContentKind,
    GuideExecutionProfile,
    GuideLocator,
    GuidePageManifest,
    GuidePageTerminalReceipt,
    GuideTerminalState,
    VerificationDisposition,
    reconcile_page_receipts,
)
from asd_kontur.practice_guidance.postgres import PracticeGuideRepository

from .conftest import (
    PostgreSQLEnvironment,
    create_database,
    drop_database,
    run_migration,
)

pytestmark = __import__("pytest").mark.postgres
ZERO = "sha256:" + "0" * 64


def test_platform_guide_ingestion_gateway_and_workspace_independence(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    correlation_id = uuid7()
    ledger = PlatformSourceLedger(postgres_environment.curator_engine, InMemoryObjectStore())
    admitted = ledger.admit(
        PlatformSourceAdmission(
            None,
            f"synthetic-practice-guide-{uuid7()}",
            "Synthetic methodological guide",
            "Synthetic guide author",
            "methodological",
            "edition-1",
            "methodological_practice_guide",
            "local-evidence://synthetic-guide.pdf",
            "verified-local-copy",
            "synthetic metadata",
            "application/pdf",
            "platform-methodological",
            "platform-permanent",
            "identity.synthetic.curator",
            correlation_id,
        ),
        b"synthetic practice guide bytes",
    )
    repository = PracticeGuideRepository(postgres_environment.guidance_ingestion_engine)
    guide_id, edition_id = repository.register_guide_edition(
        guide_key=f"synthetic-guide-{uuid7()}",
        title="Synthetic methodological guide",
        edition_label="edition-1",
        source_artifact_id=admitted.source_artifact_id,
        source_version_id=admitted.source_version_id,
        source_digest=admitted.content_digest,
        page_count=1,
        provenance={"method": "synthetic", "receipt": "verified"},
        actor_identity_id="identity.synthetic.curator",
    )
    page = GuidePageManifest(
        admitted.source_version_id,
        1,
        ZERO,
        421.0,
        597.0,
        0,
        100,
        1,
        GuideContentKind.MIXED,
        True,
        None,
        None,
    )
    repository.save_page_manifest(edition_id, (page,))
    profile = GuideExecutionProfile(
        "local.mlx",
        "Qwen3.8-27B",
        "synthetic-revision-v1",
        ZERO,
        "mlx-vlm",
        "8bit",
        "synthetic-runtime-v1",
        "development-v0.1.0",
        "pass-a-v0.1.0",
        "1.5.0",
        "preflight-v0.1.0",
        "renderer-v0.1.0",
        "two-pass-v0.1.0",
        True,
    )
    profile_id = repository.register_execution_profile(
        profile=profile,
        profile_version="0.1.0",
        qualification_state="qualified_development",
        qualification_evidence_digest=ZERO,
    )
    run_id = repository.start_ingestion_run(
        edition_id=edition_id,
        execution_profile_id=profile_id,
        expected_page_count=1,
        pass_a_prompt_version="pass-a-v0.1.0",
        pass_b_prompt_version="pass-b-v0.1.0",
        validator_version="validator-v0.1.0",
        idempotency_key=f"synthetic-ingestion-{uuid7()}",
        actor_identity_id="identity.synthetic.ingestion-service",
    )
    candidate = GuidanceCandidateVersion(
        uuid7(),
        1,
        admitted.source_version_id,
        GuideLocator(1, (0.1, 0.1, 0.9, 0.9)),
        GuidanceKind.FORM_FIELD_GUIDANCE,
        "Synthetic section",
        "Synthetic topic",
        "synthetic-form",
        "preparation",
        "synthetic-field",
        "Use the confirmed synthetic value.",
        ("confirmed value",),
        ("exact source locator",),
        (),
        "inventing a value",
        "leave an explicit gap",
        GuideLocator(1, (0.2, 0.2, 0.7, 0.7)),
        ("synthetic qualification",),
        ("not normative",),
        ("synthetic uncertainty",),
        profile.fingerprint,
    )
    repository.save_candidate(run_id, candidate)
    verification = GuidanceVerification(
        uuid7(),
        candidate.candidate_id,
        1,
        VerificationDisposition.SUPPORTED,
        admitted.source_version_id,
        candidate.locator,
        profile.fingerprint,
        "pass-b-v0.1.0",
        ZERO,
        (),
        datetime.now(UTC),
    )
    repository.save_verification(verification)
    receipt = GuidePageTerminalReceipt(
        run_id,
        admitted.source_version_id,
        1,
        GuideTerminalState.VERIFIED,
        uuid7(),
        uuid7(),
        1,
        1,
        0,
        ZERO,
        datetime.now(UTC),
    )
    repository.save_page_receipt(receipt)
    reconciliation = reconcile_page_receipts(run_id, 1, (receipt,))
    assert reconciliation.complete
    reconciliation_id = repository.save_reconciliation(
        reconciliation, actor_identity_id="identity.synthetic.verifier"
    )
    assert (
        repository.save_reconciliation(
            reconciliation, actor_identity_id="identity.synthetic.verifier"
        )
        == reconciliation_id
    )
    unit_id = repository.publish_verified_candidate(
        edition_id=edition_id,
        candidate=candidate,
        verification=verification,
        publication_decision_ref="decision:synthetic-curation",
        curator=GuidanceCuratorAuthority(
            "identity.synthetic.curator",
            True,
            frozenset({"methodological_guidance.publish"}),
        ),
    )
    conflict_id = repository.record_guidance_conflict(
        guidance_unit_id=unit_id,
        guidance_unit_version=1,
        conflicting_authority_layer="normative",
        conflicting_subject_ref="synthetic-ntd-edition:unit-1",
        conflict_type="methodological_normative_conflict",
        uncertainty_ref="uncertainty:synthetic-conflict",
        curator=GuidanceCuratorAuthority(
            "identity.synthetic.curator",
            True,
            frozenset({"methodological_guidance.conflict.record"}),
        ),
    )
    lexical_version_id = repository.rebuild_lexical_projection(edition_id)

    gateway = KnowledgeGateway(
        PostgresKnowledgeQuery(postgres_environment.guidance_gateway_engine),
        PostgresKnowledgeAudit(
            postgres_environment.guidance_gateway_engine,
            service_identity_id="service.synthetic.guidance-gateway",
        ),
    )
    response = gateway.invoke(
        GatewayRequest(
            "knowledge.get_id_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            {"query": "confirmed synthetic value", "lexical_version_id": lexical_version_id},
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.get_id_guidance.invoke",
            "synthetic qualification",
            uuid7(),
        ),
    )
    assert response.status is GatewayStatus.OK
    assert response.contract_version == GUIDANCE_CONTRACT_VERSION
    assert response.evidence_pack.evidence[0].authority_layer == "methodological_guidance"
    assert len(response.evidence_pack.evidence) == 2
    assert "page:1:region:" in response.evidence_pack.evidence[0].structural_unit_locator

    trace = gateway.invoke(
        GatewayRequest(
            "knowledge.trace_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            {"guidance_unit_id": unit_id, "version": 1},
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.trace_guidance.invoke",
            "synthetic trace",
            uuid7(),
        ),
    )
    assert trace.status is GatewayStatus.OK
    assert GUIDANCE_SCHEMA_ID.endswith("practice-guidance")

    explained = gateway.invoke(
        GatewayRequest(
            "knowledge.explain_guidance_conflict",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            {"guidance_conflict_id": conflict_id},
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.explain_guidance_conflict.invoke",
            "synthetic conflict trace",
            uuid7(),
        ),
    )
    assert explained.status is GatewayStatus.OK
    assert explained.evidence_pack.conflicts

    with Session(postgres_environment.owner_engine) as session:
        platform_before = session.scalar(
            sa.text("SELECT count(*) FROM platform.practice_guidance_units")
        )
        assert (
            session.scalar(sa.text("SELECT count(*) FROM platform.practice_guide_structural_units"))
            == 1
        )
        assert tuple(
            session.scalars(
                sa.text(
                    "SELECT state FROM platform.practice_guide_edition_states "
                    "WHERE practice_guide_edition_id=:edition ORDER BY state_sequence"
                ),
                {"edition": edition_id},
            )
        ) == ("admitted", "processing", "verified")
        assert (
            session.scalar(sa.text("SELECT count(*) FROM platform.practice_guidance_uncertainties"))
            == 1
        )
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema='platform' "
                    "AND table_name LIKE 'practice_guide%' AND column_name='workspace_id'"
                )
            )
            == 0
        )
        platform_after = session.scalar(
            sa.text("SELECT count(*) FROM platform.practice_guidance_units")
        )
    assert platform_before == platform_after == 1
    assert guide_id is not None


def test_disposable_0009_to_0008_to_0009(
    postgres_environment: PostgreSQLEnvironment,
    repository_root: object,
) -> None:
    suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    database_name = f"asd_g04_test_kgid_{suffix}"
    cluster = sa.create_engine(
        postgres_environment.cluster_admin_url,
        isolation_level="AUTOCOMMIT",
    )
    create_database(cluster, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(str(repository_root), database_url, "head")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        run_migration(str(repository_root), database_url, "0008_wp14")
        run_migration(str(repository_root), database_url, "head")
        with sa.create_engine(database_url).connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0009_kg_id"
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
