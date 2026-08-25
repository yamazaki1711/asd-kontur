from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import uuid7
from asd_kontur.kernel import (
    Applicability,
    FactClass,
    PostgresCommonKernel,
)
from asd_kontur.lifecycle import (
    ArchiveEntry,
    LifecycleState,
    PortableArchiveService,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)
from asd_kontur.persistence import WorkspaceContext, WorkspaceUnitOfWork
from asd_kontur.tender import (
    AuthorityLayer,
    ClauseProvenance,
    ContractClause,
    CorpusItem,
    DisagreementItem,
    LegalAuthority,
    PostgresTenderProcess,
    RevisedClause,
    RiskSubject,
    Severity,
    SourceClass,
    StartTenderCommand,
    TenderDeliverableKind,
    TenderFinalizationDecision,
    TenderIssue,
    TenderIssueKind,
    TenderRequirement,
    TenderState,
    TenderTerminalOutcome,
    TransitionTenderCommand,
    TypedTenderDeliverable,
    assess_corpus,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration
from .test_common_domain_kernel import (
    _command,
    _seed_candidate,
    _seed_policy_and_grant,
    _seed_rule,
)
from .test_workspace_lifecycle import (
    Tenant,
    create_tenant,
    transition,
    workspace_context,
)

pytestmark = pytest.mark.postgres
DIGEST = "sha256:" + "a" * 64


def _create_tender_mode(environment: PostgreSQLEnvironment, tenant: Tenant) -> UUID:
    mode_id = uuid7()
    with WorkspaceUnitOfWork(environment.application_engine, workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=mode_id,
            mode="Tender",
            purpose="purpose.synthetic.tender",
            input_manifest_ref="manifest.synthetic.tender",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    return mode_id


def _tender_context(tenant: Tenant) -> WorkspaceContext:
    return replace(
        workspace_context(tenant, service=True), service_identity_id="service:synthetic-tender"
    )


def _start_command(mode_id: UUID, ruleset: UUID, process_id: UUID) -> StartTenderCommand:
    return StartTenderCommand(
        uuid7(),
        process_id,
        mode_id,
        "1.0.0",
        "1.0.0",
        "1.0.0",
        "1.2.0",
        ("policy.synthetic@0.1.0",),
        tuple(item.value for item in SourceClass),
        "tender.contract-and-pdrd-analysis",
        "synthetic",
        ruleset,
        DIGEST,
        f"start-{process_id}",
        uuid7(),
        uuid7(),
    )


def _advance(
    service: PostgresTenderProcess,
    tenant: Tenant,
    process_id: UUID,
    revision: int,
    source: TenderState,
    target: TenderState,
) -> None:
    service.transition(
        context=_tender_context(tenant),
        command=TransitionTenderCommand(
            uuid7(),
            process_id,
            revision,
            source,
            target,
            f"synthetic.{target.value}",
            f"transition-{process_id}-{revision}",
            uuid7(),
            uuid7(),
        ),
    )


def _seed_legal_fact(
    environment: PostgreSQLEnvironment, tenant: Tenant
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    candidate, _, source, locator = _seed_candidate(environment, tenant)
    policy, _ = _seed_policy_and_grant(environment, tenant)
    legal_grant = uuid7()
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.confirmation_authority_grants (organization_id,workspace_id,grant_id,grant_version,human_identity_id,capability,fact_classes,professional_qualification_ref,status,effective_from,authority_reference,integrity_digest) "
                "VALUES (:o,:w,:grant,1,'human:synthetic-legal-confirmer','fact.confirm',ARRAY['legal_effect'],'qualification:synthetic-legal','active',CURRENT_TIMESTAMP,'authority:synthetic-legal',:digest)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "grant": legal_grant,
                "digest": DIGEST,
            },
        )
    command = replace(
        _command(candidate, policy, legal_grant, key=f"legal-clause-{candidate}"),
        fact_type="contract.clause",
        fact_class=FactClass.LEGAL_EFFECT,
        authority_identity_id="human:synthetic-legal-confirmer",
    )
    result = PostgresCommonKernel(environment.kernel_engine).confirm_candidate(
        context=workspace_context(tenant, service=True), command=command
    )
    with environment.owner_engine.connect() as connection:
        evidence = connection.execute(
            sa.text(
                "SELECT evidence_link_id FROM workspace.candidate_field_evidence WHERE organization_id=:o AND workspace_id=:w AND candidate_id=:candidate"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id, "candidate": candidate},
        ).scalar_one()
    assert result.fact_version == 1
    return command.fact_id, source, locator, evidence, candidate


def _seed_tender_grants(
    environment: PostgreSQLEnvironment, tenant: Tenant
) -> tuple[LegalAuthority, LegalAuthority]:
    review_grant = uuid7()
    final_grant = uuid7()
    with environment.owner_engine.begin() as connection:
        for grant, human, capability in (
            (review_grant, "human:synthetic-legal-reviewer", "tender.legal.review"),
            (final_grant, "human:synthetic-legal-finalizer", "tender.legal.finalize"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.tender_professional_grants (organization_id,workspace_id,grant_id,grant_version,human_identity_id,capability,professional_qualification_ref,authority_reference,status,effective_from,integrity_digest) "
                    "VALUES (:o,:w,:grant,1,:human,:capability,'qualification:synthetic-legal','authority:synthetic-legal','active',CURRENT_TIMESTAMP,:digest)"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "grant": grant,
                    "human": human,
                    "capability": capability,
                    "digest": DIGEST,
                },
            )
    return (
        LegalAuthority(
            "human:synthetic-legal-reviewer",
            review_grant,
            1,
            "tender.legal.review",
            "qualification:synthetic-legal",
            True,
        ),
        LegalAuthority(
            "human:synthetic-legal-finalizer",
            final_grant,
            1,
            "tender.legal.finalize",
            "qualification:synthetic-legal",
            True,
        ),
    )


def test_wp12_schema_role_rls_and_migration_head(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "tender_processes",
        "tender_clause_versions",
        "tender_issue_versions",
        "tender_disagreement_protocol_versions",
        "tender_revised_contract_versions",
        "tender_deliverable_versions",
        "tender_terminal_outcomes",
    } <= set(inspector.get_table_names(schema="workspace"))
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0016_ntd_seed"
        )
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_tender_service'")
            )
            == "asd_tender_service"
        )
        policies = int(
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='workspace' AND tablename LIKE 'tender_%'"
                )
            )
            or 0
        )
    assert policies >= 16 * 3


def test_at_pe_41_tender_end_to_end_lineage_authority_archive_and_reset(
    postgres_environment: PostgreSQLEnvironment, tmp_path: Path
) -> None:
    tenant = create_tenant(postgres_environment)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant, 1, LifecycleState.ACTIVE, "wp12-active")
    mode_id = _create_tender_mode(postgres_environment, tenant)
    ruleset, _, _, trace = _seed_rule(postgres_environment, tenant)
    fact_id, source, locator, evidence, candidate = _seed_legal_fact(postgres_environment, tenant)
    service = PostgresTenderProcess(postgres_environment.tender_engine)
    process_id = uuid7()
    start_command = _start_command(mode_id, ruleset, process_id)
    started = service.start(context=_tender_context(tenant), command=start_command)
    replay = service.start(context=_tender_context(tenant), command=start_command)
    assert started.state is TenderState.REQUESTED
    assert replay.idempotent_replay

    corpus_items = (
        CorpusItem(SourceClass.TENDER_DOCUMENTATION, source, locator, evidence, True),
        CorpusItem(SourceClass.DRAFT_CONTRACT, source, locator, evidence, True),
        CorpusItem(SourceClass.PD, source, locator, evidence, True),
        CorpusItem(SourceClass.RD, source, locator, evidence, True),
    )
    assessment = assess_corpus(corpus_items)
    assert not assessment.missing_classes
    service.append_corpus_assessment(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        assessment_id=uuid7(),
        assessment=assessment,
        items=corpus_items,
    )
    _advance(service, tenant, process_id, 1, TenderState.REQUESTED, TenderState.CORPUS_ASSESSED)

    requirement = TenderRequirement(
        uuid7(),
        1,
        "synthetic.payment-term",
        RiskSubject.PAYMENT,
        Applicability.APPLICABLE,
        ruleset,
        trace,
        (evidence,),
        (SourceClass.DRAFT_CONTRACT,),
    )
    service.append_requirement(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        requirement=requirement,
    )
    _advance(
        service,
        tenant,
        process_id,
        2,
        TenderState.CORPUS_ASSESSED,
        TenderState.REQUIREMENTS_DETERMINED,
    )

    clause = ContractClause(
        uuid7(),
        1,
        "clause.synthetic.payment",
        DIGEST,
        AuthorityLayer.CONTRACT,
        ClauseProvenance(source, locator, evidence, fact_id, 1),
    )
    unconfirmed_clause = replace(
        clause,
        clause_id=uuid7(),
        provenance=replace(clause.provenance, fact_id=uuid7()),
    )
    with pytest.raises(DBAPIError):
        service.append_clause(
            context=_tender_context(tenant),
            tender_process_id=process_id,
            clause_key="unconfirmed.synthetic",
            clause=unconfirmed_clause,
        )
    service.append_clause(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        clause_key="payment.synthetic",
        clause=clause,
    )
    issue = TenderIssue(
        uuid7(),
        1,
        TenderIssueKind.CONTRACT_RISK,
        RiskSubject.PAYMENT,
        Severity.HIGH,
        Applicability.APPLICABLE,
        clause,
        requirement.requirement_id,
        ruleset,
        trace,
        (evidence,),
        None,
        "Synthetic revised payment condition.",
        "PAYMENT_ALLOCATION_RISK",
    )
    service.append_issue(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        issue=issue,
    )
    kernel_finding_id = uuid7()
    with postgres_environment.kernel_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.kernel_finding_versions (organization_id,workspace_id,finding_id,version,finding_kind,subject_type,subject_id,subject_version,applicability,status,source_fact_ids,evidence_link_ids,issue_ids,rule_set_version_id,rule_trace_id,finding_digest,recorded_at) "
                "VALUES (:o,:w,:finding,1,'missing_work','workspace_fact',:fact,'1','applicable','confirmed',ARRAY[:fact]::uuid[],ARRAY[:evidence]::uuid[],ARRAY[]::uuid[],:ruleset,:trace,:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "finding": kernel_finding_id,
                "fact": fact_id,
                "evidence": evidence,
                "ruleset": ruleset,
                "trace": trace,
                "digest": DIGEST,
            },
        )
    pdrd_issue = TenderIssue(
        uuid7(),
        1,
        TenderIssueKind.MISSING_WORK,
        RiskSubject.TECHNICAL_REQUIREMENT,
        Severity.HIGH,
        Applicability.APPLICABLE,
        None,
        None,
        ruleset,
        trace,
        (evidence,),
        None,
        "Include the synthetic omitted work in the priced scope.",
        "WORK_SCOPE_OMISSION",
        kernel_finding_id,
        1,
    )
    service.append_issue(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        issue=pdrd_issue,
    )
    gap_issue = TenderIssue(
        uuid7(),
        1,
        TenderIssueKind.GAP,
        RiskSubject.SOURCE_COMPLETENESS,
        Severity.MEDIUM,
        Applicability.INDETERMINATE,
        None,
        None,
        ruleset,
        None,
        (),
        "OPTIONAL_COMMERCIAL_APPENDIX_NOT_PROVIDED",
        None,
        "LIMITED_COMMERCIAL_REVIEW",
    )
    service.append_issue(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        issue=gap_issue,
    )
    reviewer, finalizer = _seed_tender_grants(postgres_environment, tenant)
    finding_decision = service.confirm_legal_finding(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        issue_id=issue.issue_id,
        issue_version=1,
        authority=reviewer,
        correlation_id=uuid7(),
        causation_id=uuid7(),
    )
    _advance(
        service,
        tenant,
        process_id,
        3,
        TenderState.REQUIREMENTS_DETERMINED,
        TenderState.ANALYZED,
    )

    item = DisagreementItem(
        uuid7(),
        1,
        clause,
        issue.issue_id,
        1,
        "Synthetic revised payment condition.",
        issue.consequence_code,
        (evidence,),
        trace,
        finding_decision,
        (),
    )
    protocol_id = uuid7()
    service.append_disagreement_protocol(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        protocol_id=protocol_id,
        items=(item,),
        rule_set_version_id=ruleset,
        source_manifest_digest=DIGEST,
        evidence_manifest_digest=DIGEST,
    )
    revised_clause = RevisedClause(
        uuid7(),
        1,
        clause,
        issue.issue_id,
        1,
        item.item_id,
        finding_decision,
        "Synthetic revised payment condition.",
    )
    service.append_revised_contract(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        revised_contract_id=uuid7(),
        protocol_id=protocol_id,
        source_contract_version_id=source,
        clauses=(revised_clause,),
        source_manifest_digest=DIGEST,
    )
    typed_item_by_kind = {
        TenderDeliverableKind.DISAGREEMENT_PROTOCOL: item.item_id,
        TenderDeliverableKind.REVISED_CONTRACT: revised_clause.revised_clause_id,
        TenderDeliverableKind.RISK_REGISTER: issue.issue_id,
        TenderDeliverableKind.GAP_REGISTER: gap_issue.issue_id,
        TenderDeliverableKind.PDRD_ANALYSIS: pdrd_issue.issue_id,
    }
    deliverables = tuple(
        TypedTenderDeliverable(
            uuid7(),
            1,
            kind,
            (typed_item_by_kind[kind],),
            DIGEST,
            DIGEST,
            ruleset,
            "reviewed",
            (),
            (gap_issue.issue_id,) if kind is TenderDeliverableKind.GAP_REGISTER else (),
        )
        for kind in TenderDeliverableKind
    )
    for deliverable in deliverables:
        service.append_deliverable(
            context=_tender_context(tenant),
            tender_process_id=process_id,
            deliverable=deliverable,
        )
    _advance(service, tenant, process_id, 4, TenderState.ANALYZED, TenderState.DRAFTED)
    _advance(
        service,
        tenant,
        process_id,
        5,
        TenderState.DRAFTED,
        TenderState.WAITING_FOR_AUTHORITY,
    )
    decision = TenderFinalizationDecision(
        uuid7(),
        reviewer,
        finalizer,
        tuple(deliverable.deliverable_id for deliverable in deliverables),
        TenderTerminalOutcome.SUCCESS,
        ("PRINT_READY_RENDERING_BLOCKED",),
    )
    completed = service.finalize(
        context=_tender_context(tenant),
        tender_process_id=process_id,
        expected_revision=6,
        decision=decision,
        idempotency_key=f"finalize-{process_id}",
        correlation_id=uuid7(),
        causation_id=uuid7(),
    )
    assert completed.state is TenderState.FINALIZED
    assert completed.revision == 7

    with postgres_environment.owner_engine.connect() as connection:
        lineage = connection.execute(
            sa.text(
                "SELECT rc.source_clause_id,rc.issue_id,rc.decision_id,di.evidence_link_ids "
                "FROM workspace.tender_revised_clause_versions rc JOIN workspace.tender_disagreement_items di "
                "ON di.organization_id=rc.organization_id AND di.workspace_id=rc.workspace_id "
                "AND di.item_id=rc.disagreement_item_id WHERE rc.organization_id=:o AND rc.workspace_id=:w"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id},
        ).one()
        versions = connection.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.tender_deliverable_versions WHERE organization_id=:o AND workspace_id=:w AND state='finalized'"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id},
        )
        candidate_fact = connection.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.confirmation_decisions WHERE organization_id=:o AND workspace_id=:w AND candidate_id=:candidate AND outcome='confirmed'"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id, "candidate": candidate},
        )
        product_ready = connection.scalar(
            sa.text(
                "SELECT product_ready FROM workspace.tender_terminal_outcomes WHERE organization_id=:o AND workspace_id=:w"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id},
        )
    assert lineage.source_clause_id == clause.clause_id
    assert lineage.issue_id == issue.issue_id
    assert lineage.decision_id == finding_decision
    assert lineage.evidence_link_ids == [evidence]
    assert versions == 5
    assert candidate_fact == 1
    assert product_ready is False

    archive_service = PortableArchiveService()
    tender_manifest = json.dumps(
        {
            "workspace_id": str(tenant.workspace_id),
            "tender_process_id": str(process_id),
            "process_revision": 7,
            "deliverable_versions": [2, 2, 2, 2, 2],
            "contract_version": "1.2.0",
        },
        sort_keys=True,
    ).encode()
    receipt = archive_service.create(
        package_id=uuid7(),
        organization_id=tenant.organization_id,
        construction_object_id=tenant.construction_object_id,
        workspace_id=tenant.workspace_id,
        workspace_revision=1,
        contract_versions={"tender": "1.2.0"},
        policy_versions={"workspace": "0.1.0"},
        rule_set_version="0.1.0",
        entries=(
            ArchiveEntry(
                "tender/manifest.json",
                "tender-process:synthetic:7",
                tender_manifest,
                "application/json",
            ),
        ),
        destination=tmp_path / "portable-archive.zip",
    )
    assert receipt.item_count == 1
    assert archive_service.verify(receipt.package_path).manifest_digest == receipt.manifest_digest

    definition = StorageAdapterDefinition(
        "workspace.postgresql",
        "1.0.0",
        "canonical",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
        "available",
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine, tenant.organization_id, definition
    )
    operation = uuid7()
    tender_items = tuple(
        item for item in adapter.inventory(tenant.workspace_id) if "tender_" in item.item_id
    )
    assert tender_items
    for inventory_item in adapter.inventory(tenant.workspace_id):
        adapter.purge_item(
            workspace_id=tenant.workspace_id,
            item_id=inventory_item.item_id,
            operation_id=operation,
        )
    assert adapter.inventory(tenant.workspace_id) == ()
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.rule_set_versions WHERE rule_set_version_id=:id"
                ),
                {"id": ruleset},
            )
            == 1
        )


def test_tender_rls_cross_workspace_default_deny_freeze_and_direct_state_guard(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant_a, 1, LifecycleState.ACTIVE, "wp12-a-active")
    transition(lifecycle, tenant_b, 1, LifecycleState.ACTIVE, "wp12-b-active")
    mode_a = _create_tender_mode(postgres_environment, tenant_a)
    mode_b = _create_tender_mode(postgres_environment, tenant_b)
    rules_a, _, _, _ = _seed_rule(postgres_environment, tenant_a)
    rules_b, _, _, _ = _seed_rule(postgres_environment, tenant_b)
    service = PostgresTenderProcess(postgres_environment.tender_engine)
    process_a = uuid7()
    process_b = uuid7()
    service.start(
        context=_tender_context(tenant_a),
        command=_start_command(mode_a, rules_a, process_a),
    )
    service.start(
        context=_tender_context(tenant_b),
        command=_start_command(mode_b, rules_b, process_b),
    )
    service.append_corpus_assessment(
        context=_tender_context(tenant_b),
        tender_process_id=process_b,
        assessment_id=uuid7(),
        assessment=assess_corpus(()),
        items=(),
    )
    blocked = service.transition(
        context=_tender_context(tenant_b),
        command=TransitionTenderCommand(
            uuid7(),
            process_b,
            1,
            TenderState.REQUESTED,
            TenderState.BLOCKED,
            TenderTerminalOutcome.BLOCKED_INCOMPLETE_CORPUS,
            f"block-{process_b}",
            uuid7(),
            uuid7(),
        ),
    )
    assert blocked.state is TenderState.BLOCKED
    with postgres_environment.tender_engine.begin() as connection:
        connection.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(tenant_a.organization_id), True),
                sa.func.set_config("asd.workspace_id", str(tenant_a.workspace_id), True),
            )
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.tender_processes")) == 1
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.tender_processes WHERE tender_process_id=:process"
                ),
                {"process": process_b},
            )
            == 0
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                sa.text(
                    "UPDATE workspace.tender_processes SET state='finalized' WHERE tender_process_id=:process"
                ),
                {"process": process_a},
            )
    with pytest.raises(DBAPIError):
        with postgres_environment.tender_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE platform.normative_documents SET document_key='forbidden.synthetic'"
                )
            )
    with postgres_environment.tender_engine.begin() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.tender_processes")) == 0

    transition(lifecycle, tenant_a, 2, LifecycleState.FREEZING, "wp12-a-freeze")
    lifecycle.record_freeze_manifest(
        context=workspace_context(tenant_a, service=True),
        lifecycle_version=3,
        workspace_revision=1,
        canonical_revision_digest=DIGEST,
        job_inventory={"cancelled": [], "checkpointed": []},
        result="verified",
    )
    transition(lifecycle, tenant_a, 3, LifecycleState.FROZEN, "wp12-a-frozen")
    with pytest.raises(DBAPIError):
        service.append_corpus_assessment(
            context=_tender_context(tenant_a),
            tender_process_id=process_a,
            assessment_id=uuid7(),
            assessment=assess_corpus(()),
            items=(),
        )
    definition = StorageAdapterDefinition(
        "workspace.postgresql",
        "1.0.0",
        "canonical",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
        "available",
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine, tenant_a.organization_id, definition
    )
    reset_operation = uuid7()
    for item in adapter.inventory(tenant_a.workspace_id):
        adapter.purge_item(
            workspace_id=tenant_a.workspace_id,
            item_id=item.item_id,
            operation_id=reset_operation,
        )
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.tender_processes WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
                ),
                {
                    "o": tenant_b.organization_id,
                    "w": tenant_b.workspace_id,
                    "process": process_b,
                },
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.tender_terminal_outcomes WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process AND outcome='blocked_incomplete_corpus'"
                ),
                {
                    "o": tenant_b.organization_id,
                    "w": tenant_b.workspace_id,
                    "process": process_b,
                },
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.rule_set_versions WHERE rule_set_version_id IN (:a,:b)"
                ),
                {"a": rules_a, "b": rules_b},
            )
            >= 1
        )


def test_wp12_disposable_migration_roundtrip(
    postgres_environment: PostgreSQLEnvironment,
    repository_root: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_name = f"asd_g04_test_wp12_roundtrip_{uuid7().hex}"
    admin_engine = sa.create_engine(
        postgres_environment.cluster_admin_url, isolation_level="AUTOCOMMIT"
    )
    create_database(admin_engine, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(repository_root, database_url, "head")
        monkeypatch.setenv("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", "1")
        run_migration(repository_root, database_url, "0005_wp11")
        engine = sa.create_engine(database_url)
        try:
            assert "tender_processes" not in sa.inspect(engine).get_table_names(schema="workspace")
        finally:
            engine.dispose()
        run_migration(repository_root, database_url, "head")
        engine = sa.create_engine(database_url)
        try:
            assert "tender_processes" in sa.inspect(engine).get_table_names(schema="workspace")
        finally:
            engine.dispose()
    finally:
        drop_database(admin_engine, database_name)
        admin_engine.dispose()
