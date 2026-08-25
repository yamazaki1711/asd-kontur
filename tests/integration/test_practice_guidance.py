from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.integrity.models import IntegrityFailure
from asd_kontur.integrity.postgres import (
    active_context_binding_fingerprint,
    active_semantic_duplicate_inventory,
    memory_relation_inventory,
)
from asd_kontur.knowledge import InMemoryObjectStore
from asd_kontur.knowledge.errors import KnowledgeError, KnowledgeErrorCode
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
from asd_kontur.lifecycle import PostgresWorkspaceStorageAdapter, StorageAdapterDefinition
from asd_kontur.persistence import WorkspaceUnitOfWork
from asd_kontur.practice_guidance.intelligence_postgres import (
    construct_manifest,
    default_context_assembly_policy,
    persist_backup_manifest,
    persist_manifest,
)
from asd_kontur.practice_guidance.memory_backup import (
    build_backup_manifest,
    verify_restored_practice_memory,
)
from asd_kontur.practice_guidance.models import (
    CoverageManifest,
    GuidanceCandidateVersion,
    GuidanceCuratorAuthority,
    GuidanceKind,
    GuidanceVerification,
    GuideContentKind,
    GuideExecutionProfile,
    GuideLocator,
    GuideNtdRelevanceAssertion,
    GuidePageManifest,
    GuidePageTerminalReceipt,
    GuideSourceRow,
    GuideTerminalState,
    NormativeReferenceCandidate,
    NormativeReferenceResolutionState,
    VerificationDisposition,
    reconcile_page_receipts,
)
from asd_kontur.practice_guidance.pipeline import ntd_assertion_candidate
from asd_kontur.practice_guidance.postgres import PracticeGuideRepository

from .conftest import (
    PostgreSQLEnvironment,
    create_database,
    drop_database,
    run_migration,
)
from .test_workspace_lifecycle import create_tenant, workspace_context

pytestmark = __import__("pytest").mark.postgres
ZERO = "sha256:" + "0" * 64


def test_practice_guide_admission_requires_permanent_platform_core(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    ledger = PlatformSourceLedger(
        postgres_environment.curator_engine,
        InMemoryObjectStore(),
    )
    with pytest.raises(KnowledgeError) as blocked:
        ledger.admit(
            PlatformSourceAdmission(
                None,
                f"synthetic-invalid-practice-guide-{uuid7()}",
                "Synthetic invalid practice guide",
                "Synthetic guide author",
                "methodological",
                "edition-1",
                "methodological_practice_guide",
                "local-evidence://invalid-retention.pdf",
                "verified-local-copy",
                "synthetic metadata",
                "application/pdf",
                "platform-methodological",
                "workspace.canonical",
                "identity.synthetic.curator",
                uuid7(),
            ),
            b"synthetic invalid retention source",
        )
    assert blocked.value.code is KnowledgeErrorCode.RETENTION_CLASS_INVALID


def test_platform_guide_ingestion_gateway_and_workspace_independence(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    correlation_id = uuid7()
    ledger = PlatformSourceLedger(postgres_environment.curator_engine, InMemoryObjectStore())
    stable_designation = f"synthetic-practice-guide-{uuid7()}"
    guide_key = f"synthetic-guide-{uuid7()}"
    admitted = ledger.admit(
        PlatformSourceAdmission(
            None,
            stable_designation,
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
            "permanent_platform_core",
            "identity.synthetic.curator",
            correlation_id,
        ),
        b"synthetic practice guide bytes",
    )
    repository = PracticeGuideRepository(postgres_environment.guidance_ingestion_engine)
    guide_id, edition_id = repository.register_guide_edition(
        guide_key=guide_key,
        title="Synthetic methodological guide",
        edition_label="edition-1",
        source_artifact_id=admitted.source_artifact_id,
        source_version_id=admitted.source_version_id,
        source_digest=admitted.content_digest,
        page_count=1,
        provenance={"method": "synthetic", "receipt": "verified"},
        actor_identity_id="identity.synthetic.curator",
    )
    repeated_guide_id, repeated_edition_id = repository.register_guide_edition(
        guide_key=guide_key,
        title="Synthetic methodological guide",
        edition_label="edition-1",
        source_artifact_id=admitted.source_artifact_id,
        source_version_id=admitted.source_version_id,
        source_digest=admitted.content_digest,
        page_count=1,
        provenance={"method": "synthetic", "receipt": "verified"},
        actor_identity_id="identity.synthetic.curator",
    )
    assert (repeated_guide_id, repeated_edition_id) == (guide_id, edition_id)
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
    source_row = GuideSourceRow(
        source_row_id=uuid7(),
        parent_candidate_id=candidate.candidate_id,
        parent_candidate_version=candidate.version,
        source_version_id=admitted.source_version_id,
        page_number=1,
        row_ordinal=1,
        locator=GuideLocator(1, (0.1, 0.1, 0.9, 0.3)),
        printed_ntd="SYNTHETIC-NTD-1 «Synthetic NTD»",
        work_or_rd_sections="Synthetic work",
        id_note="Synthetic ID note",
        layout_profile_version="guide_ntd_three_column_rows_v0.1",
        extraction_digest=ZERO,
        parent_failed_receipt_digest=ZERO,
    )
    reference = NormativeReferenceCandidate(
        uuid7(),
        "SYNTHETIC-NTD-1",
        "Synthetic NTD",
        NormativeReferenceResolutionState.NOT_ATTEMPTED,
        "NTD_EDITION_RESOLUTION_PENDING",
    )
    ntd_assertion = GuideNtdRelevanceAssertion(
        assertion_id=uuid7(),
        candidate_id=candidate.candidate_id,
        parent_candidate_version=candidate.version,
        source_row_id=source_row.source_row_id,
        source_version_id=admitted.source_version_id,
        locator=source_row.locator,
        printed_identifier=reference.printed_identifier,
        printed_title=reference.printed_title,
        work_or_rd_sections=source_row.work_or_rd_sections,
        id_note=source_row.id_note,
        relevance_summary="Synthetic NTD is methodologically relevant to ID.",
        document_or_form_type="synthetic-form",
        workflow_stage="synthetic-stage",
        applicability_conditions=("synthetic applicability",),
        uncertainty_codes=("NTD_EDITION_RESOLUTION_PENDING",),
        normative_reference=reference,
        model_profile_fingerprint=profile.fingerprint,
    )
    ntd_candidate = ntd_assertion_candidate(ntd_assertion)
    repository.save_ntd_source_row(run_id, source_row)
    repository.save_candidate(run_id, ntd_candidate)
    repository.save_ntd_relevance_assertion(ntd_assertion)
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
    stale_verification = GuidanceVerification(
        uuid7(),
        candidate.candidate_id,
        1,
        VerificationDisposition.MODEL_FAILED,
        admitted.source_version_id,
        candidate.locator,
        profile.fingerprint,
        "stale-preflight-v0.1.0",
        "sha256:" + "2" * 64,
        (),
        datetime.now(UTC),
    )
    repository.save_verification(stale_verification)
    repository.save_verification(verification)
    with Session(postgres_environment.owner_engine) as session:
        selected_attempts = tuple(
            session.execute(
                sa.text(
                    "SELECT d.version,v.disposition FROM "
                    "platform.practice_guide_verification_selection_decisions d JOIN "
                    "platform.practice_guide_verifications v ON "
                    "v.verification_id=d.selected_verification_id WHERE "
                    "d.guidance_candidate_id=:candidate AND d.candidate_version=1 "
                    "ORDER BY d.version"
                ),
                {"candidate": candidate.candidate_id},
            )
        )
    assert selected_attempts == ((1, "model_failed"), (2, "supported"))
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
            frozenset({"methodological_practice.publish"}),
        ),
    )
    with Session(postgres_environment.owner_engine) as session:
        assert (
            session.scalar(
                sa.text(
                    "SELECT authority_layer FROM platform.practice_guidance_units "
                    "WHERE guidance_unit_id=:id AND version=1"
                ),
                {"id": unit_id},
            )
            == "methodological_practice"
        )
    coverage_manifest_id = uuid7()
    repository.save_coverage_manifest(
        CoverageManifest(
            coverage_manifest_id=coverage_manifest_id,
            practice_guide_edition_id=edition_id,
            ingestion_run_id=run_id,
            version=1,
            publication_status="complete",
            expected_page_count=1,
            terminal_page_count=1,
            page_state_counts={"verified": 1},
            candidate_state_counts={"supported": 1},
            guidance_unit_count=1,
            gap_count=0,
            conflict_count=0,
            reconciliation_fingerprint=reconciliation.fingerprint,
            manifest_fingerprint=ZERO,
            recorded_at=datetime.now(UTC),
        ),
        (),
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
    assert response.evidence_pack.evidence[0].authority_layer == "methodological_practice"
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
    assert GUIDANCE_SCHEMA_ID.endswith("practice-intelligence")
    assert trace.result["guidance"][0]["authority_layer"] == "methodological_practice"

    construction = construct_manifest(
        postgres_environment.guidance_ingestion_engine,
        coverage_manifest_id,
    )
    persistence = persist_manifest(
        postgres_environment.guidance_ingestion_engine,
        construction,
    )
    assert active_semantic_duplicate_inventory(postgres_environment.owner_engine) == []
    repeated_persistence = persist_manifest(
        postgres_environment.guidance_ingestion_engine,
        construction,
    )
    assert repeated_persistence == persistence
    with Session(postgres_environment.owner_engine) as session:
        retention = session.execute(
            sa.text(
                "SELECT a.retention_class,v.retention_class,o.retention_class "
                "FROM platform.source_artifacts a JOIN platform.source_versions v ON "
                "v.source_artifact_id=a.source_artifact_id JOIN platform.objects o ON "
                "o.object_id=v.object_id WHERE v.source_version_id=:source"
            ),
            {"source": admitted.source_version_id},
        ).one()
        release = session.execute(
            sa.text(
                "SELECT authority_layer,retention_class,canonical_semantic_fingerprint,"
                "activation_decision_id,activation_decision_version,product_ready FROM "
                "platform.practice_intelligence_releases WHERE release_id=:id"
            ),
            {"id": persistence["practice_intelligence_release_id"]},
        ).one()
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.practice_intelligence_release_memberships "
                    "WHERE release_id=:release AND release_version=1"
                ),
                {"release": persistence["practice_intelligence_release_id"]},
            )
            == construction["intelligence_unit_count"]
        )
    assert tuple(retention) == (
        "permanent_platform_core",
        "permanent_platform_core",
        "permanent_platform_core",
    )
    assert tuple(release) == (
        "methodological_practice",
        "permanent_platform_core",
        persistence["canonical_semantic_fingerprint"],
        UUID(str(persistence["activation_decision_id"])),
        persistence["activation_decision_version"],
        False,
    )
    context_policy = default_context_assembly_policy(edition_id)
    backup_manifest = build_backup_manifest(
        practice_guide_edition_id=edition_id,
        source_version_id=admitted.source_version_id,
        source_bytes=b"synthetic practice guide bytes",
        construction_manifest_id=UUID(str(persistence["construction_manifest_id"])),
        construction_fingerprint=str(persistence["construction_fingerprint"]),
        coverage_manifest_fingerprint=str(construction["coverage_manifest_fingerprint"]),
        activation_decision_id=UUID(str(persistence["activation_decision_id"])),
        activation_decision_version=int(persistence["activation_decision_version"]),
        intelligence_unit_digests=tuple(
            str(value["integrity_digest"]) for value in construction["intelligence_units"]
        ),
        playbook_digests=tuple(
            str(value["integrity_digest"]) for value in construction["playbooks"]
        ),
        context_policy=context_policy,
        projection_fingerprints=(
            {
                "projection_kind": "fts",
                "fingerprint": str(persistence["construction_fingerprint"]),
            },
        ),
        backup_object_reference="platform-backup:synthetic-practice-memory",
    )
    persist_backup_manifest(
        postgres_environment.guidance_ingestion_engine,
        release_id=UUID(str(persistence["practice_intelligence_release_id"])),
        release_version=1,
        manifest=backup_manifest,
    )
    verify_restored_practice_memory(
        manifest=backup_manifest,
        restored_source_bytes=b"synthetic practice guide bytes",
        construction_fingerprint=str(persistence["construction_fingerprint"]),
        coverage_manifest_fingerprint=str(construction["coverage_manifest_fingerprint"]),
        intelligence_unit_digests=tuple(
            str(value["integrity_digest"]) for value in construction["intelligence_units"]
        ),
        playbook_digests=tuple(
            str(value["integrity_digest"]) for value in construction["playbooks"]
        ),
        context_policy=context_policy,
    )

    with Session(postgres_environment.guidance_ingestion_engine) as session, session.begin():
        session.execute(
            sa.text(
                "DELETE FROM projection.practice_intelligence_lexical_entries "
                "WHERE lexical_version_id=:id"
            ),
            {"id": persistence["lexical_version_id"]},
        )
    rebuilt = persist_manifest(postgres_environment.guidance_ingestion_engine, construction)
    assert (
        rebuilt["canonical_semantic_fingerprint"] == persistence["canonical_semantic_fingerprint"]
    )
    with Session(postgres_environment.owner_engine) as session:
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM projection.practice_intelligence_lexical_entries "
                    "WHERE lexical_version_id=:id"
                ),
                {"id": persistence["lexical_version_id"]},
            )
            == persistence["lexical_entry_count"]
        )
    intelligence_payload = {
        "query": "confirmed synthetic value",
        "intent": "field_completion",
        "lexical_version_id": persistence["lexical_version_id"],
        "practice_guide_edition_id": str(edition_id),
        "context_assembly_policy_id": persistence["context_assembly_policy_id"],
        "context_assembly_policy_version": persistence["context_assembly_policy_version"],
        "mode": "Support",
        "purpose": "id.support",
    }
    intelligence = gateway.invoke(
        GatewayRequest(
            "knowledge.get_id_task_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            intelligence_payload,
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.get_id_task_guidance.invoke",
            "synthetic practice-intelligence qualification",
            uuid7(),
        ),
    )
    assert intelligence.status is GatewayStatus.OK
    assert intelligence.result["practice_intelligence"]
    assert intelligence.result["practice_playbooks"]
    assert (
        intelligence.result["authority_composition"]["methodological_practice"][
            "may_activate_rule_version"
        ]
        is False
    )
    assert intelligence.evidence_pack.evidence[0].source_version_id == str(
        admitted.source_version_id
    )

    missing_payload = {**intelligence_payload, "query": "syntheticmissingguidance"}
    missing = gateway.invoke(
        GatewayRequest(
            "knowledge.get_id_task_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            missing_payload,
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.get_id_task_guidance.invoke",
            "synthetic missing practice intelligence",
            uuid7(),
        ),
    )
    assert missing.status in {GatewayStatus.NO_RESULT, GatewayStatus.KNOWLEDGE_INCOMPLETE}
    assert missing.result["practice_guide_edition_id"] == str(edition_id)
    assert missing.evidence_pack.evidence == ()

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
            frozenset({"methodological_practice.conflict.record"}),
        ),
    )
    conflicted_context = gateway.invoke(
        GatewayRequest(
            "knowledge.get_id_task_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            intelligence_payload,
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.get_id_task_guidance.invoke",
            "synthetic practice/normative conflict",
            uuid7(),
        ),
    )
    assert conflicted_context.status is GatewayStatus.GUIDANCE_NORMATIVE_CONFLICT
    assert conflicted_context.evidence_pack.conflicts
    assert conflicted_context.result["practice_intelligence"] == []
    assert conflicted_context.result["quarantined_conflict_match_count"] > 0

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
    assert explained.result["practice_guide_edition_id"] == str(edition_id)
    assert explained.evidence_pack.evidence[0].authority_layer == "methodological_practice"

    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    for tenant in (tenant_a, tenant_b):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine, workspace_context(tenant)
        ) as unit:
            assert unit.workspaces is not None
            unit.workspaces.create_mode_execution(
                mode_execution_id=uuid7(),
                mode="Audit",
                purpose="id.audit",
                input_manifest_ref="manifest.synthetic.practice-memory",
                policy_assignment_key="policy.synthetic",
                policy_assignment_version="0.1.0",
                rule_set_key="rules.synthetic",
                rule_set_version="0.1.0",
            )
    scoped_results = []
    for tenant in (tenant_a, tenant_b):
        scoped = gateway.invoke(
            GatewayRequest(
                "knowledge.get_id_task_guidance",
                GUIDANCE_CONTRACT_VERSION,
                GUIDANCE_SCHEMA_ID,
                GUIDANCE_CONTRACT_VERSION,
                intelligence_payload,
            ),
            GatewayContext(
                "identity.synthetic.consumer",
                "knowledge.get_id_task_guidance.invoke",
                "id.support",
                uuid7(),
                tenant.organization_id,
                tenant.workspace_id,
            ),
        )
        scoped_results.append(scoped.result["practice_intelligence"])
    assert scoped_results[0] == scoped_results[1]
    workspace_adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant_a.organization_id,
        StorageAdapterDefinition(
            "postgres.workspace",
            "0.1.0",
            "postgres_workspace_relations",
            "authoritative",
            "workspace",
            True,
            True,
            True,
            True,
            True,
            "1.0.0",
        ),
    )
    platform_semantic_before = persistence["canonical_semantic_fingerprint"]
    for item in workspace_adapter.inventory(tenant_a.workspace_id):
        workspace_adapter.purge_item(
            workspace_id=tenant_a.workspace_id,
            item_id=item.item_id,
            operation_id=uuid7(),
        )
    with Session(postgres_environment.owner_engine) as session:
        assert (
            session.scalar(
                sa.text(
                    "SELECT canonical_semantic_fingerprint FROM "
                    "platform.practice_intelligence_releases WHERE release_id=:id"
                ),
                {"id": persistence["practice_intelligence_release_id"]},
            )
            == platform_semantic_before
        )
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.mode_executions WHERE workspace_id=:workspace"
                ),
                {"workspace": tenant_b.workspace_id},
            )
            == 1
        )

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
            session.scalar(sa.text("SELECT count(*) FROM platform.practice_guide_source_rows")) == 1
        )
        assert (
            session.scalar(
                sa.text("SELECT count(*) FROM platform.practice_guide_ntd_relevance_assertions")
            )
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

    second_source = ledger.admit(
        PlatformSourceAdmission(
            None,
            stable_designation,
            "Synthetic methodological guide",
            "Synthetic guide author",
            "methodological",
            "edition-2",
            "methodological_practice_guide",
            "local-evidence://synthetic-guide-v2.pdf",
            "verified-local-copy",
            "synthetic metadata v2",
            "application/pdf",
            "platform-methodological",
            "permanent_platform_core",
            "identity.synthetic.curator",
            uuid7(),
        ),
        b"synthetic practice guide bytes edition two",
    )
    same_guide_id, second_edition_id = repository.register_guide_edition(
        guide_key=guide_key,
        title="Synthetic methodological guide",
        edition_label="edition-2",
        source_artifact_id=second_source.source_artifact_id,
        source_version_id=second_source.source_version_id,
        source_digest=second_source.content_digest,
        page_count=1,
        provenance={"method": "synthetic", "receipt": "verified-v2"},
        actor_identity_id="identity.synthetic.curator",
    )
    assert same_guide_id == guide_id
    assert second_edition_id != edition_id
    first_activation = repository.activate_guide_edition(
        practice_guide_id=guide_id,
        selected_edition_id=edition_id,
        reason_code="INITIAL_PERMANENT_PRACTICE_EDITION",
        owner_decision_ref="ADR-0011;owner:Oleg Shcherbakov;2026-08-25",
        authority_identity_id="owner.oleg-shcherbakov",
    )
    assert (
        repository.activate_guide_edition(
            practice_guide_id=guide_id,
            selected_edition_id=edition_id,
            reason_code="INITIAL_PERMANENT_PRACTICE_EDITION",
            owner_decision_ref="ADR-0011;owner:Oleg Shcherbakov;2026-08-25",
            authority_identity_id="owner.oleg-shcherbakov",
        )
        == first_activation
    )
    second_activation = repository.activate_guide_edition(
        practice_guide_id=guide_id,
        selected_edition_id=second_edition_id,
        reason_code="new_verified_edition",
        owner_decision_ref="owner-decision:synthetic:2",
        authority_identity_id="identity.synthetic.curator",
    )
    superseded_edition_response = gateway.invoke(
        GatewayRequest(
            "knowledge.get_id_task_guidance",
            GUIDANCE_CONTRACT_VERSION,
            GUIDANCE_SCHEMA_ID,
            GUIDANCE_CONTRACT_VERSION,
            intelligence_payload,
        ),
        GatewayContext(
            "identity.synthetic.consumer",
            "knowledge.get_id_task_guidance.invoke",
            "exact edition pin after activation",
            uuid7(),
        ),
    )
    assert superseded_edition_response.status is GatewayStatus.EDITION_MISMATCH
    rollback_activation = repository.activate_guide_edition(
        practice_guide_id=guide_id,
        selected_edition_id=edition_id,
        reason_code="controlled_rollback",
        owner_decision_ref="owner-decision:synthetic:3",
        authority_identity_id="identity.synthetic.curator",
    )
    assert (first_activation.version, second_activation.version, rollback_activation.version) == (
        1,
        2,
        3,
    )
    assert (
        repository.resolve_edition_activation(
            activation_decision_id=second_activation.activation_decision_id,
            version=2,
        ).selected_edition_id
        == second_edition_id
    )
    with pytest.raises(sa.exc.NoResultFound):
        repository.activate_guide_edition(
            practice_guide_id=guide_id,
            selected_edition_id=uuid7(),
            reason_code="invalid_cross_identity",
            owner_decision_ref="owner-decision:synthetic:invalid",
            authority_identity_id="identity.synthetic.curator",
        )
    with Session(postgres_environment.owner_engine) as session:
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.practice_guide_editions "
                    "WHERE practice_guide_id=:guide"
                ),
                {"guide": guide_id},
            )
            == 2
        )
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.practice_guide_editions "
                    "WHERE practice_guide_edition_id=:edition AND source_version_id=:source"
                ),
                {"edition": edition_id, "source": admitted.source_version_id},
            )
            == 1
        )
        assert (
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.practice_guide_edition_activation_decisions "
                    "WHERE practice_guide_id=:guide"
                ),
                {"guide": guide_id},
            )
            == 3
        )


def test_disposable_practice_memory_head_to_0008_to_head(
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
        disposable_engine = sa.create_engine(database_url)
        with disposable_engine.connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0018_memory_integrity"
            )
        with pytest.raises(IntegrityFailure) as missing_relation:
            memory_relation_inventory(
                disposable_engine,
                (("platform", "practice_memory_relation_that_does_not_exist"),),
            )
        assert missing_relation.value.code == "PLATFORM_MEMORY_SCHEMA_INCOMPLETE"
        with pytest.raises(IntegrityFailure) as missing_binding:
            active_context_binding_fingerprint(disposable_engine)
        assert missing_binding.value.code == "ACTIVE_RELEASE_SELECTION_INCOMPLETE"
        disposable_engine.dispose()
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster, database_name)
        cluster.dispose()
