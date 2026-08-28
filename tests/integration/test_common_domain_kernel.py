from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import uuid7
from asd_kontur.kernel import (
    ConfirmCandidateCommand,
    FactClass,
    FactValueKind,
    KernelError,
    KernelErrorCode,
    PostgresCommonKernel,
)
from asd_kontur.lifecycle import (
    LifecycleState,
    PostgresLifecycleRepository,
    PostgresWorkspaceStorageAdapter,
    StorageAdapterDefinition,
)

from .conftest import PostgreSQLEnvironment, create_database, drop_database, run_migration
from .test_ai_vlm_harness import _insert_request, _seed_profile, _seed_source
from .test_workspace_lifecycle import Tenant, create_tenant, transition, workspace_context

pytestmark = pytest.mark.postgres
DIGEST = "sha256:" + "a" * 64


def _scope(connection: sa.Connection, tenant: Tenant) -> None:
    connection.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(tenant.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(tenant.workspace_id), True),
        )
    )


def _seed_rule(environment: PostgreSQLEnvironment, tenant: Tenant) -> tuple[UUID, UUID, UUID, UUID]:
    context_id = uuid7()
    rule_id = uuid7()
    rule_version_id = uuid7()
    rule_set_id = uuid7()
    evaluation_id = uuid7()
    trace_id = uuid7()
    with environment.owner_engine.begin() as connection:
        existing_rule_set_id = connection.scalar(
            sa.text(
                "SELECT rule_set_version_id FROM platform.rule_set_versions "
                "WHERE rule_set_key='rules.synthetic' AND version='0.1.0'"
            )
        )
        if existing_rule_set_id is not None:
            rule_set_id = existing_rule_set_id
        membership_ordinal = int(
            connection.scalar(
                sa.text(
                    "SELECT coalesce(max(ordinal),-1)+1 FROM platform.rule_set_memberships "
                    "WHERE rule_set_version_id=:ruleset"
                ),
                {"ruleset": rule_set_id},
            )
            or 0
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.applicability_contexts (applicability_context_id,context_version,dimensions,unknown_behavior,integrity_digest) "
                "VALUES (:context,1,'{}'::jsonb,'indeterminate',:digest)"
            ),
            {"context": context_id, "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.rules (rule_id,rule_key,rule_class,purpose,created_by_identity_id) "
                "VALUES (:rule,:key,'work_type_classification','synthetic','human:synthetic-author')"
            ),
            {"rule": rule_id, "key": f"synthetic.rule.{rule_id}"},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.rule_versions (rule_version_id,rule_id,version,predicate_contract,input_contract,output_contract,applicability_context_id,uncertainty_behavior,failure_behavior,implementation_binding,test_manifest_digest,integrity_digest,author_identity_id) "
                "VALUES (:version,:rule,'1.0.0','{}'::jsonb,'{}'::jsonb,'{}'::jsonb,:context,'indeterminate','fail_closed','kernel.synthetic',:digest,:digest,'human:synthetic-author')"
            ),
            {"version": rule_version_id, "rule": rule_id, "context": context_id, "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.rule_version_states (rule_version_state_id,rule_version_id,state_sequence,status,authority_identity_id,decision_ref,effective_at) "
                "VALUES (:state,:version,1,'active','human:synthetic-approver','decision:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"state": uuid7(), "version": rule_version_id},
        )
        if existing_rule_set_id is None:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.rule_set_versions (rule_set_version_id,rule_set_key,version,status,manifest_digest,schema_version,compatibility_contract,approval_decision_ref,approved_by_identity_id) "
                    "VALUES (:ruleset,'rules.synthetic','0.1.0','active',:digest,'1.0.0','{}'::jsonb,'decision:synthetic','human:synthetic-approver')"
                ),
                {"ruleset": rule_set_id, "digest": DIGEST},
            )
        connection.execute(
            sa.text(
                "INSERT INTO platform.rule_set_memberships (rule_set_version_id,rule_version_id,membership_role,ordinal,rule_integrity_digest) "
                "VALUES (:ruleset,:version,'primary',:ordinal,:digest)"
            ),
            {
                "ruleset": rule_set_id,
                "version": rule_version_id,
                "ordinal": membership_ordinal,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.rule_evaluations (organization_id,workspace_id,rule_evaluation_id,rule_set_version_id,rule_version_id,applicability,outcome,input_snapshot,typed_output,deterministic_fingerprint,policy_versions,evaluated_at,correlation_id) "
                "VALUES (:o,:w,:evaluation,:ruleset,:rule,'applicable','pass','{}'::jsonb,'{}'::jsonb,:digest,'[]'::jsonb,CURRENT_TIMESTAMP,:correlation)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "evaluation": evaluation_id,
                "ruleset": rule_set_id,
                "rule": rule_version_id,
                "digest": DIGEST,
                "correlation": uuid7(),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.rule_traces (organization_id,workspace_id,rule_trace_id,rule_evaluation_id,rule_set_version_id,rule_version_id,trace_payload,deterministic_fingerprint) "
                "VALUES (:o,:w,:trace,:evaluation,:ruleset,:rule,'{}'::jsonb,:digest)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "trace": trace_id,
                "evaluation": evaluation_id,
                "ruleset": rule_set_id,
                "rule": rule_version_id,
                "digest": DIGEST,
            },
        )
    return rule_set_id, rule_version_id, evaluation_id, trace_id


def _seed_candidate(
    environment: PostgreSQLEnvironment, tenant: Tenant
) -> tuple[UUID, UUID, UUID, UUID]:
    source, locator = _seed_source(environment, tenant)
    profile, _ = _seed_profile(environment)
    request = uuid7()
    attempt = uuid7()
    candidate = uuid7()
    validation = uuid7()
    evidence = uuid7()
    with environment.harness_engine.begin() as connection:
        _scope(connection, tenant)
        _insert_request(connection, tenant, source, locator, profile, request_id=request)
        connection.execute(
            sa.text(
                "INSERT INTO workspace.vlm_execution_attempts (organization_id,workspace_id,attempt_id,request_id,attempt_kind,status,expected_source_digest,started_at) "
                "VALUES (:o,:w,:attempt,:request,'initial','completed',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "attempt": attempt,
                "request": request,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidates (organization_id,workspace_id,candidate_id,purpose,source_version_id,retention_class,created_at) "
                "VALUES (:o,:w,:candidate,'synthetic.kernel',:source,'workspace.candidate',CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate,
                "source": source,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidate_versions (organization_id,workspace_id,candidate_id,candidate_version,attempt_id,origin,status,output_schema_version,digest,created_at) "
                "VALUES (:o,:w,:candidate,1,:attempt,'native_parser','validated_candidate','0.1.0',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate,
                "attempt": attempt,
                "digest": DIGEST,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidate_fields (organization_id,workspace_id,candidate_id,candidate_version,field_path,value_type,typed_value,validation_state) "
                "VALUES (:o,:w,:candidate,1,'/work/type','text',to_jsonb('synthetic.work'::text),'valid')"
            ),
            {"o": tenant.organization_id, "w": tenant.workspace_id, "candidate": candidate},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.vlm_validation_runs (organization_id,workspace_id,validation_run_id,candidate_id,candidate_version,validator_profile_version,required_validators,skipped_validators,status,digest,validated_at) "
                "VALUES (:o,:w,:validation,:candidate,1,'1.0.0',ARRAY['schema','locator'],ARRAY[]::text[],'passed',:digest,CURRENT_TIMESTAMP)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "validation": validation,
                "candidate": candidate,
                "digest": DIGEST,
            },
        )
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.evidence_links (organization_id,workspace_id,evidence_link_id,subject_type,subject_id,subject_version,source_version_id,source_locator_id,evidence_role,validity_status,decision_ref) "
                "VALUES (:o,:w,:evidence,'candidate_field',:candidate,'1:/work/type',:source,:locator,'material_field','verified','decision:synthetic-evidence')"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "evidence": evidence,
                "candidate": candidate,
                "source": source,
                "locator": locator,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.candidate_field_evidence (organization_id,workspace_id,candidate_id,candidate_version,field_path,source_version_id,source_locator_id,evidence_link_id,evidence_role) "
                "VALUES (:o,:w,:candidate,1,'/work/type',:source,:locator,:evidence,'material_field')"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "candidate": candidate,
                "source": source,
                "locator": locator,
                "evidence": evidence,
            },
        )
    return candidate, validation, source, locator


def _seed_policy_and_grant(environment: PostgreSQLEnvironment, tenant: Tenant) -> tuple[UUID, UUID]:
    policy = uuid7()
    grant = uuid7()
    with environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.confirmation_policy_versions (confirmation_policy_id,version,policy_key,environment,auto_confirm_fact_classes,professional_fact_classes,validator_profile_version,status,effective_from,integrity_digest) "
                "VALUES (:policy,'1.0.0',:key,'development',ARRAY['classification','observation'],ARRAY['legal_effect','contractual_obligation','geometry','measurement','payable_volume','signer_authority','material_blocker','professional_finalization'],'1.0.0','active',CURRENT_TIMESTAMP,:digest)"
            ),
            {"policy": policy, "key": f"synthetic.policy.{policy}", "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace.confirmation_authority_grants (organization_id,workspace_id,grant_id,grant_version,human_identity_id,capability,fact_classes,professional_qualification_ref,status,effective_from,authority_reference,integrity_digest) "
                "VALUES (:o,:w,:grant,1,'human:synthetic-confirmer','fact.confirm',ARRAY['classification','geometry'],'qualification:synthetic','active',CURRENT_TIMESTAMP,'authority:synthetic',:digest)"
            ),
            {
                "o": tenant.organization_id,
                "w": tenant.workspace_id,
                "grant": grant,
                "digest": DIGEST,
            },
        )
    return policy, grant


def _command(
    candidate: UUID,
    policy: UUID,
    grant: UUID,
    *,
    fact_id: UUID | None = None,
    expected: int = 0,
    key: str = "confirm-synthetic",
) -> ConfirmCandidateCommand:
    return ConfirmCandidateCommand(
        uuid7(),
        uuid7(),
        fact_id or uuid7(),
        expected,
        candidate,
        1,
        "/work/type",
        "work_type.classification",
        FactClass.CLASSIFICATION,
        FactValueKind.TEXT,
        policy,
        "1.0.0",
        "qualified_human",
        "human:synthetic-confirmer",
        grant,
        1,
        None,
        None,
        None,
        None,
        key,
        uuid7(),
        uuid7(),
        datetime.now(UTC),
    )


def _rule_command(
    candidate: UUID,
    policy: UUID,
    rule_authority: tuple[UUID, UUID, UUID, UUID],
) -> ConfirmCandidateCommand:
    rule_set, rule, evaluation, trace = rule_authority
    return ConfirmCandidateCommand(
        uuid7(),
        uuid7(),
        uuid7(),
        0,
        candidate,
        1,
        "/work/type",
        "work_type.classification",
        FactClass.CLASSIFICATION,
        FactValueKind.TEXT,
        policy,
        "1.0.0",
        "deterministic_rule",
        "service:synthetic-rule-runtime",
        None,
        None,
        rule_set,
        rule,
        evaluation,
        trace,
        "auto-confirm-synthetic",
        uuid7(),
        uuid7(),
        datetime.now(UTC),
    )


def test_wp11_schema_role_and_migration_head(postgres_environment: PostgreSQLEnvironment) -> None:
    inspector = sa.inspect(postgres_environment.owner_engine)
    assert {
        "workspace_facts",
        "confirmation_decisions",
        "work_instance_versions",
        "material_requirement_versions",
        "control_operation_versions",
        "document_requirement_versions",
        "id_package_versions",
        "ks_line_versions",
        "payment_claim_versions",
        "kernel_finding_versions",
    } <= set(inspector.get_table_names(schema="workspace"))
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0028_industrial_intake"
        )
        assert (
            connection.scalar(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname='asd_kernel_service'")
            )
            == "asd_kernel_service"
        )


def test_candidate_confirmation_is_atomic_idempotent_and_workspace_isolated(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant_a, 1, LifecycleState.ACTIVE, "wp11-a-active")
    transition(lifecycle, tenant_b, 1, LifecycleState.ACTIVE, "wp11-b-active")
    candidate, _, _, _ = _seed_candidate(postgres_environment, tenant_a)
    policy, grant = _seed_policy_and_grant(postgres_environment, tenant_a)
    command = _command(candidate, policy, grant)
    kernel = PostgresCommonKernel(postgres_environment.kernel_engine)
    first = kernel.confirm_candidate(context=workspace_context(tenant_a), command=command)
    second = kernel.confirm_candidate(context=workspace_context(tenant_a), command=command)
    assert first.fact_version == second.fact_version == 1
    with postgres_environment.kernel_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.workspace_facts")) == 0
    with postgres_environment.kernel_engine.begin() as connection:
        _scope(connection, tenant_b)
        assert connection.scalar(sa.text("SELECT count(*) FROM workspace.workspace_facts")) == 0
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.confirmation_decisions WHERE workspace_id=:w"
                ),
                {"w": tenant_a.workspace_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM messaging.workspace_outbox WHERE workspace_id=:w AND aggregate_id=:fact"
                ),
                {"w": tenant_a.workspace_id, "fact": command.fact_id},
            )
            == 1
        )


def test_concurrency_authority_and_lifecycle_fence_fail_closed(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant, 1, LifecycleState.ACTIVE, "wp11-active")
    candidate, _, _, _ = _seed_candidate(postgres_environment, tenant)
    policy, grant = _seed_policy_and_grant(postgres_environment, tenant)
    kernel = PostgresCommonKernel(postgres_environment.kernel_engine)
    fact = uuid7()
    kernel.confirm_candidate(
        context=workspace_context(tenant), command=_command(candidate, policy, grant, fact_id=fact)
    )
    with pytest.raises(DBAPIError):
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE workspace.workspace_fact_versions SET text_value='mutated' "
                    "WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact"
                ),
                {"o": tenant.organization_id, "w": tenant.workspace_id, "fact": fact},
            )
    with pytest.raises(KernelError, match=KernelErrorCode.CONCURRENCY_CONFLICT):
        kernel.confirm_candidate(
            context=workspace_context(tenant),
            command=_command(
                candidate, policy, grant, fact_id=fact, expected=0, key="stale-version"
            ),
        )
    unauthorized = _command(candidate, policy, uuid7(), key="missing-grant")
    with pytest.raises(KernelError, match=KernelErrorCode.AUTHORITY_DENIED):
        kernel.confirm_candidate(context=workspace_context(tenant), command=unauthorized)
    transition(lifecycle, tenant, 2, LifecycleState.FREEZING, "wp11-freezing")
    lifecycle.record_freeze_manifest(
        context=workspace_context(tenant, service=True),
        lifecycle_version=3,
        workspace_revision=1,
        canonical_revision_digest=DIGEST,
        job_inventory={"cancelled": [], "checkpointed": []},
        result="verified",
    )
    transition(lifecycle, tenant, 3, LifecycleState.FROZEN, "wp11-frozen")
    with pytest.raises(KernelError, match=KernelErrorCode.WORKSPACE_FENCED):
        kernel.confirm_candidate(
            context=workspace_context(tenant),
            command=_command(candidate, policy, grant, key="late-after-freeze"),
        )


def test_deterministic_auto_confirmation_requires_active_pinned_rule_trace(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant = create_tenant(postgres_environment)
    transition(
        PostgresLifecycleRepository(postgres_environment.lifecycle_engine),
        tenant,
        1,
        LifecycleState.ACTIVE,
        "wp11-rule-active",
    )
    candidate, _, _, _ = _seed_candidate(postgres_environment, tenant)
    policy, _ = _seed_policy_and_grant(postgres_environment, tenant)
    authority = _seed_rule(postgres_environment, tenant)
    result = PostgresCommonKernel(postgres_environment.kernel_engine).confirm_candidate(
        context=workspace_context(tenant),
        command=_rule_command(candidate, policy, authority),
    )
    assert result.reason_code == "policy_controlled_deterministic_rule"
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT authority_kind FROM workspace.confirmation_decisions "
                    "WHERE organization_id=:o AND workspace_id=:w AND confirmation_decision_id=:decision"
                ),
                {
                    "o": tenant.organization_id,
                    "w": tenant.workspace_id,
                    "decision": result.decision_id,
                },
            )
            == "deterministic_rule"
        )


def test_cross_workspace_fact_reference_is_rejected_by_composite_fk(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant_a, 1, LifecycleState.ACTIVE, "wp11-fk-a")
    transition(lifecycle, tenant_b, 1, LifecycleState.ACTIVE, "wp11-fk-b")
    candidate, _, _, _ = _seed_candidate(postgres_environment, tenant_a)
    policy, grant = _seed_policy_and_grant(postgres_environment, tenant_a)
    command = _command(candidate, policy, grant)
    PostgresCommonKernel(postgres_environment.kernel_engine).confirm_candidate(
        context=workspace_context(tenant_a), command=command
    )
    with pytest.raises(DBAPIError):
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.construction_structure_versions (organization_id,workspace_id,structure_id,version,source_fact_id,source_fact_version,rule_set_version_id,rule_trace_id,status,structure_digest,recorded_at) "
                    "VALUES (:o,:w,:structure,1,:fact,1,:ruleset,:trace,'active',:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": tenant_b.organization_id,
                    "w": tenant_b.workspace_id,
                    "structure": uuid7(),
                    "fact": command.fact_id,
                    "ruleset": uuid7(),
                    "trace": uuid7(),
                    "digest": DIGEST,
                },
            )


def test_full_common_chain_serves_all_modes_and_reset_preserves_platform(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = create_tenant(postgres_environment)
    tenant_b = create_tenant(postgres_environment, tenant_a.organization_id)
    lifecycle = PostgresLifecycleRepository(postgres_environment.lifecycle_engine)
    transition(lifecycle, tenant_a, 1, LifecycleState.ACTIVE, "wp11-chain-a")
    transition(lifecycle, tenant_b, 1, LifecycleState.ACTIVE, "wp11-chain-b")
    candidate, _, _, _ = _seed_candidate(postgres_environment, tenant_a)
    policy, grant = _seed_policy_and_grant(postgres_environment, tenant_a)
    command = _command(candidate, policy, grant)
    PostgresCommonKernel(postgres_environment.kernel_engine).confirm_candidate(
        context=workspace_context(tenant_a), command=command
    )
    candidate_b, _, _, _ = _seed_candidate(postgres_environment, tenant_b)
    policy_b, grant_b = _seed_policy_and_grant(postgres_environment, tenant_b)
    command_b = _command(candidate_b, policy_b, grant_b, key="confirm-synthetic-b")
    PostgresCommonKernel(postgres_environment.kernel_engine).confirm_candidate(
        context=workspace_context(tenant_b), command=command_b
    )
    rule_set, rule, evaluation, trace = _seed_rule(postgres_environment, tenant_a)
    ids = {
        name: uuid7()
        for name in (
            "work_type",
            "material",
            "doc_type",
            "structure",
            "element",
            "work",
            "volume",
            "material_requirement",
            "batch",
            "application",
            "control",
            "evidence_requirement",
            "document_requirement",
            "coverage",
            "package",
            "presented",
            "ks",
            "ks_line",
            "payment",
            "issue",
            "finding",
        )
    }
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_types VALUES (:id,'synthetic.work','1.0.0','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["work_type"]},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.work_type_versions VALUES (:id,'1.0.0','1.0.0','Synthetic work','active',:digest,:digest,NULL,NULL)"
            ),
            {"id": ids["work_type"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.material_classes VALUES (:id,'synthetic.material','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["material"]},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.material_class_versions VALUES (:id,'1.0.0','1.0.0','Synthetic material','active',:digest,:digest)"
            ),
            {"id": ids["material"], "digest": DIGEST},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.required_document_types VALUES (:id,'synthetic.id','human:synthetic',CURRENT_TIMESTAMP)"
            ),
            {"id": ids["doc_type"]},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.required_document_type_versions VALUES (:id,'1.0.0','synthetic','PDF_NON_FILLABLE','active',:rule,:digest)"
            ),
            {"id": ids["doc_type"], "rule": rule, "digest": DIGEST},
        )
        o, w = tenant_a.organization_id, tenant_a.workspace_id
        params = {
            "o": o,
            "w": w,
            "fact": command.fact_id,
            "ruleset": rule_set,
            "rule": rule,
            "evaluation": evaluation,
            "trace": trace,
            "digest": DIGEST,
            **ids,
        }
        statements = (
            "INSERT INTO workspace.construction_structure_versions VALUES (:o,:w,:structure,1,:fact,1,:ruleset,:trace,'active',:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.construction_element_versions VALUES (:o,:w,:element,1,:structure,1,NULL,'synthetic_element','E-1','zone-1',:fact,1,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.work_instance_versions VALUES (:o,:w,:work,1,:work_type,'1.0.0',:element,1,'planned',:fact,1,:ruleset,:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.work_volume_versions VALUES (:o,:w,:volume,1,:work,1,'confirmed',10.000,'m3',3,'1.0.0','calc:synthetic',:fact,1,:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.material_requirement_versions VALUES (:o,:w,:material_requirement,1,:work,1,:material,'1.0.0',2.000,'t',3,'applicable','required',:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.material_batch_versions VALUES (:o,:w,:batch,1,:material,'1.0.0','batch-synthetic','admitted',:fact,1,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.material_applications VALUES (:o,:w,:application,:batch,1,:work,1,2.000,'t',3,(SELECT evidence_link_id FROM workspace.workspace_fact_evidence WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact LIMIT 1),:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.control_operation_versions VALUES (:o,:w,:control,1,:work,1,'synthetic_control','1.0.0','applicable','passed','authority:synthetic',:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.evidence_requirement_versions VALUES (:o,:w,:evidence_requirement,1,:work,1,:control,1,'synthetic_evidence','applicable','satisfied','0.1.0',:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.document_requirement_versions VALUES (:o,:w,:document_requirement,1,:work,1,:doc_type,'1.0.0','required','covered',:evaluation,:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.document_coverages VALUES (:o,:w,:coverage,:document_requirement,1,'source_version',(SELECT source_version_id FROM workspace.workspace_fact_versions WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact AND fact_version=1),'1','covered',(SELECT evidence_link_id FROM workspace.workspace_fact_evidence WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact LIMIT 1),:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.id_package_versions VALUES (:o,:w,:package,1,'work',:work,'complete',1,1,0,0,:digest,:ruleset,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.id_package_items VALUES (:o,:w,:package,1,:document_requirement,1,:coverage,'covered')",
            "INSERT INTO workspace.presented_volume_versions VALUES (:o,:w,:presented,1,:volume,1,:package,1,'contract:synthetic','eligible',:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.ks_document_versions VALUES (:o,:w,:ks,1,'KS-2',DATE '2026-01-01',DATE '2026-01-31','contract:synthetic','validated',NULL,NULL,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.ks_line_versions VALUES (:o,:w,:ks_line,1,:ks,1,:presented,1,10.000,'m3',3,100.00,1000.00,'TST','calc:synthetic',:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.kernel_issue_versions VALUES (:o,:w,:issue,1,'uncertainty','SYNTHETIC.OPEN_INPUT','work',:work,'1',ARRAY['synthetic-input'],'resolved',ARRAY[]::uuid[],:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.payment_claim_versions VALUES (:o,:w,:payment,1,:ks,1,1000.00,'TST','eligible','authority:synthetic',:trace,:digest,CURRENT_TIMESTAMP)",
            "INSERT INTO workspace.kernel_finding_versions VALUES (:o,:w,:finding,1,'audit_delta','work',:work,'1','applicable','confirmed',ARRAY[:fact]::uuid[],ARRAY[(SELECT evidence_link_id FROM workspace.workspace_fact_evidence WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact LIMIT 1)]::uuid[],ARRAY[:issue]::uuid[],:ruleset,:trace,:digest,CURRENT_TIMESTAMP)",
        )
        for statement in statements:
            connection.execute(sa.text(statement), params)
        mode_ids = tuple(
            connection.scalars(
                sa.text(
                    "SELECT mode_execution_id FROM workspace.mode_executions WHERE organization_id=:o AND workspace_id=:w"
                ),
                {"o": o, "w": w},
            )
        )
        assert len(mode_ids) == 0
        for mode in ("Tender", "Support", "Audit", "Restoration"):
            mode_id = uuid7()
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.mode_executions (organization_id,workspace_id,mode_execution_id,mode,purpose,state,revision,input_manifest_ref,contract_key,contract_version,schema_id,schema_version,process_definition_key,process_definition_version,authority_profile_key,authority_profile_version,output_contract_key,output_contract_version,policy_assignment_key,policy_assignment_version,rule_set_key,rule_set_version,retention_class,created_by_identity_id,correlation_id,created_at,updated_at) VALUES (:o,:w,:mode_id,:mode,'synthetic','requested',1,'manifest:synthetic','mode.execution-request','0.1.0','urn:asd-kontur:contracts:v0.1:schema:mode-deliverable','0.1.0','common-kernel','1.0.0','authority.synthetic','1.0.0','mode.terminal-result','0.1.0','policy.synthetic','0.1.0','rules.synthetic','0.1.0','workspace.mode','human:synthetic',:correlation,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"o": o, "w": w, "mode_id": mode_id, "mode": mode, "correlation": uuid7()},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO workspace.mode_kernel_bindings VALUES (:o,:w,:mode_id,:fact,1,'use_as_input','decision:synthetic-sharing',CURRENT_TIMESTAMP)"
                ),
                {"o": o, "w": w, "mode_id": mode_id, "fact": command.fact_id},
            )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(DISTINCT mode) FROM workspace.mode_executions WHERE organization_id=:o AND workspace_id=:w"
                ),
                {"o": o, "w": w},
            )
            == 4
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.workspace_fact_versions fv "
                    "JOIN workspace.construction_structure_versions cs ON "
                    "(cs.organization_id,cs.workspace_id,cs.source_fact_id,cs.source_fact_version)="
                    "(fv.organization_id,fv.workspace_id,fv.fact_id,fv.fact_version) "
                    "JOIN workspace.construction_element_versions ce ON "
                    "(ce.organization_id,ce.workspace_id,ce.structure_id,ce.structure_version)="
                    "(cs.organization_id,cs.workspace_id,cs.structure_id,cs.version) "
                    "JOIN workspace.work_instance_versions wi ON "
                    "(wi.organization_id,wi.workspace_id,wi.element_id,wi.element_version)="
                    "(ce.organization_id,ce.workspace_id,ce.element_id,ce.version) "
                    "JOIN workspace.work_volume_versions wv ON "
                    "(wv.organization_id,wv.workspace_id,wv.work_instance_id,wv.work_instance_version)="
                    "(wi.organization_id,wi.workspace_id,wi.work_instance_id,wi.version) "
                    "JOIN workspace.presented_volume_versions pv ON "
                    "(pv.organization_id,pv.workspace_id,pv.work_volume_id,pv.work_volume_version)="
                    "(wv.organization_id,wv.workspace_id,wv.work_volume_id,wv.version) "
                    "JOIN workspace.ks_line_versions kl ON "
                    "(kl.organization_id,kl.workspace_id,kl.presented_volume_id,kl.presented_volume_version)="
                    "(pv.organization_id,pv.workspace_id,pv.presented_volume_id,pv.version) "
                    "JOIN workspace.payment_claim_versions pc ON "
                    "(pc.organization_id,pc.workspace_id,pc.ks_document_id,pc.ks_document_version)="
                    "(kl.organization_id,kl.workspace_id,kl.ks_document_id,kl.ks_document_version) "
                    "WHERE fv.organization_id=:o AND fv.workspace_id=:w AND fv.fact_id=:fact"
                ),
                {"o": o, "w": w, "fact": command.fact_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.mode_kernel_bindings WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact"
                ),
                {"o": o, "w": w, "fact": command.fact_id},
            )
            == 4
        )
    with postgres_environment.owner_engine.connect() as connection:
        platform_count_before = int(
            connection.scalar(sa.text("SELECT count(*) FROM platform.work_types")) or 0
        )
    definition = StorageAdapterDefinition(
        "postgres-workspace",
        "1.0.0",
        "postgres_workspace_relations",
        "authoritative",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
    )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine, tenant_a.organization_id, definition
    )
    for item in adapter.inventory(tenant_a.workspace_id):
        adapter.purge_item(
            workspace_id=tenant_a.workspace_id, item_id=item.item_id, operation_id=uuid7()
        )
    assert adapter.inventory(tenant_a.workspace_id) == ()
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM workspace.workspace_facts WHERE workspace_id=:w"),
                {"w": tenant_b.workspace_id},
            )
            == 1
        )
        assert (
            int(connection.scalar(sa.text("SELECT count(*) FROM platform.work_types")) or 0)
            == platform_count_before
        )


def test_disposable_0005_downgrade_upgrade(
    postgres_environment: PostgreSQLEnvironment, repository_root: object
) -> None:
    suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    database_name = f"asd_g04_test_wp11_{suffix}"
    cluster_engine = sa.create_engine(
        postgres_environment.cluster_admin_url, isolation_level="AUTOCOMMIT"
    )
    create_database(cluster_engine, database_name)
    database_url = postgres_environment.cluster_admin_url.set(database=database_name)
    try:
        run_migration(str(repository_root), database_url, "head")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        run_migration(str(repository_root), database_url, "0004_g07")
        run_migration(str(repository_root), database_url, "head")
        with sa.create_engine(database_url).connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0028_industrial_intake"
            )
    finally:
        os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
        drop_database(cluster_engine, database_name)
        cluster_engine.dispose()
