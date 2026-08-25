from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.knowledge import (
    AuthorityIdentity,
    GatewayContext,
    GatewayRequest,
    InMemoryObjectStore,
    KnowledgeGateway,
)
from asd_kontur.knowledge.gateway import GatewayStatus
from asd_kontur.knowledge.postgres import (
    NormativeKnowledgeRepository,
    PostgresKnowledgeAudit,
    PostgresKnowledgeQuery,
    RuleRegistryService,
)
from asd_kontur.knowledge.projections import ProjectionBuilder, ProjectionState
from asd_kontur.knowledge.rules import RuleState, RuleVersionDefinition
from asd_kontur.knowledge.source_ledger import (
    OfficialSourceRegistration,
    PlatformSourceAdmission,
    PlatformSourceLedger,
)

from .conftest import PostgreSQLEnvironment
from .test_postgresql_foundation import _create_tenant, _workspace_context

pytestmark = pytest.mark.postgres


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalFixture:
    source_version_id: UUID
    source_locator_id: UUID
    document_id: UUID
    edition_id: UUID
    structural_unit_ids: tuple[UUID, UUID]
    assertion_id: UUID
    applicability_id: UUID


def _admit_source(
    environment: PostgreSQLEnvironment,
) -> tuple[PlatformSourceLedger, InMemoryObjectStore, UUID, PlatformSourceAdmission]:
    store = InMemoryObjectStore()
    ledger = PlatformSourceLedger(environment.curator_engine, store)
    correlation = uuid7()
    token = str(uuid7())
    family = f"synthetic-source-family-{token}"
    designation = f"SYNTHETIC-NTD-{token}"
    url = f"https://example.invalid/official/{token}"
    ledger.register_official_source(
        OfficialSourceRegistration(
            family,
            url,
            "Synthetic issuer",
            "Synthetic jurisdiction",
            "metadata-v1",
            "identity.synthetic.curator",
            correlation,
        )
    )
    request = PlatformSourceAdmission(
        family,
        designation,
        "Synthetic normative source",
        "Synthetic issuer",
        "Synthetic jurisdiction",
        "edition-1",
        "normative_document",
        url,
        "synthetic-copy",
        "metadata-v1",
        "application/pdf",
        "platform-public",
        "permanent_platform_core",
        "identity.synthetic.curator",
        correlation,
    )
    admitted = ledger.admit(request, f"synthetic normative bytes {token}".encode())
    return ledger, store, admitted.source_version_id, request


def _canonical_fixture(environment: PostgreSQLEnvironment) -> CanonicalFixture:
    _ledger, _store, source_version_id, request = _admit_source(environment)
    document_id, edition_id = uuid7(), uuid7()
    unit_a, unit_b, applicability_id, assertion_id = uuid7(), uuid7(), uuid7(), uuid7()
    with Session(environment.curator_engine) as session, session.begin():
        locator_id = UUID(
            str(
                session.execute(
                    sa.text(
                        "SELECT source_locator_id FROM platform.source_locators "
                        "WHERE source_version_id=:source"
                    ),
                    {"source": source_version_id},
                ).scalar_one()
            )
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.normative_documents "
                "(normative_document_id,designation_namespace,designation,title,issuer,jurisdiction,"
                "document_class,created_by_identity_id) VALUES "
                "(:id,'synthetic',:designation,'Synthetic NTD','Synthetic issuer',"
                "'Synthetic jurisdiction','technical_normative','identity.synthetic.curator')"
            ),
            {"id": document_id, "designation": request.stable_designation},
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.applicability_contexts "
                "(applicability_context_id,context_version,dimensions,unknown_behavior,integrity_digest) "
                "VALUES (:id,1,CAST(:dimensions AS jsonb),'indeterminate',:digest)"
            ),
            {"id": applicability_id, "dimensions": "{}", "digest": _sha("applicability")},
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.normative_editions "
                "(normative_edition_id,normative_document_id,edition_label,source_version_id,effective_from,"
                "applicability_context_id,admitted_by_identity_id) "
                "VALUES (:id,:document,'edition-1',:source,:effective,:applicability,'identity.synthetic.curator')"
            ),
            {
                "id": edition_id,
                "document": document_id,
                "source": source_version_id,
                "effective": date(2026, 1, 1),
                "applicability": applicability_id,
            },
        )
        session.execute(
            sa.text(
                "INSERT INTO platform.normative_edition_states "
                "(edition_state_id,normative_edition_id,state_sequence,status,effective_at,authority_reference,evidence_ref) "
                "VALUES (:id,:edition,1,'active',CURRENT_TIMESTAMP,'authority.synthetic','evidence.synthetic')"
            ),
            {"id": uuid7(), "edition": edition_id},
        )
        for ordinal, unit_id in enumerate((unit_a, unit_b), start=1):
            text = f"Synthetic clause {ordinal} for projection qualification"
            session.execute(
                sa.text(
                    "INSERT INTO platform.structural_units "
                    "(structural_unit_id,normative_edition_id,unit_type,structural_path,ordinal,"
                    "source_locator_id,normalized_text,content_digest) "
                    "VALUES (:id,:edition,'clause',:path,:ordinal,:locator,:text,:digest)"
                ),
                {
                    "id": unit_id,
                    "edition": edition_id,
                    "path": f"clause/{ordinal}",
                    "ordinal": ordinal,
                    "locator": locator_id,
                    "text": text,
                    "digest": _sha(text),
                },
            )
    NormativeKnowledgeRepository(environment.curator_engine).create_assertion(
        assertion_id=assertion_id,
        assertion_kind="requirement",
        proposition="Synthetic canonical assertion",
        structural_unit_id=unit_a,
        source_version_id=source_version_id,
        source_locator_id=locator_id,
        applicability_context_id=applicability_id,
        actor_identity_id="identity.synthetic.reviewer",
        correlation_id=uuid7(),
    )
    return CanonicalFixture(
        source_version_id,
        locator_id,
        document_id,
        edition_id,
        (unit_a, unit_b),
        assertion_id,
        applicability_id,
    )


def test_source_admission_is_immutable_idempotent_and_provenanced(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    ledger, store, source_version_id, request = _admit_source(postgres_environment)
    token = request.source_family_key.removeprefix("synthetic-source-family-")
    duplicate = ledger.admit(request, f"synthetic normative bytes {token}".encode())
    assert duplicate.duplicate is True
    assert duplicate.source_version_id == source_version_id
    store.available = False
    with pytest.raises(Exception, match="unavailable"):
        ledger.admit(
            replace(request, external_version_label="edition-2"),
            b"synthetic changed bytes unavailable",
        )
    store.available = True
    with pytest.raises(Exception, match="conflicts"):
        ledger.admit(request, b"synthetic changed bytes conflict")
    store.fail_deletes = True
    with pytest.raises(Exception, match="conflicts"):
        ledger.admit(request, b"synthetic changed bytes residue")
    with postgres_environment.curator_engine.connect() as connection:
        statuses = tuple(
            connection.execute(
                sa.text(
                    "SELECT status FROM platform.acquisition_attempts "
                    "WHERE source_artifact_id=:artifact ORDER BY recorded_at"
                ),
                {"artifact": duplicate.source_artifact_id},
            ).scalars()
        )
    assert "failed" in statuses
    assert "reconciliation_required" in statuses
    with pytest.raises(DBAPIError):
        with postgres_environment.curator_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE platform.source_versions SET external_version_label='changed' "
                    "WHERE source_version_id=:id"
                ),
                {"id": source_version_id},
            )


def test_ntd_edition_resolution_keeps_cancelled_provenance_and_gaps(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    fixture = _canonical_fixture(postgres_environment)
    repository = NormativeKnowledgeRepository(postgres_environment.curator_engine)
    assert repository.resolve_edition(fixture.document_id, date(2026, 8, 23)) == fixture.edition_id
    with postgres_environment.curator_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.normative_edition_states "
                "(edition_state_id,normative_edition_id,state_sequence,status,effective_at,authority_reference,evidence_ref) "
                "VALUES (:id,:edition,2,'cancelled',CURRENT_TIMESTAMP,'authority.synthetic','evidence.synthetic')"
            ),
            {"id": uuid7(), "edition": fixture.edition_id},
        )
    with pytest.raises(Exception, match="absent or ambiguous"):
        repository.resolve_edition(fixture.document_id, date(2026, 8, 23))
    with postgres_environment.curator_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_editions WHERE normative_edition_id=:id"
                ),
                {"id": fixture.edition_id},
            )
            == 1
        )


def test_projection_rebuild_equivalence_and_canonical_survival(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    fixture = _canonical_fixture(postgres_environment)
    builder = ProjectionBuilder(postgres_environment.projection_engine)
    entries = (
        (fixture.structural_unit_ids[0], "Synthetic clause projection", (1.0, 0.0, 0.0)),
        (fixture.structural_unit_ids[1], "Other synthetic clause", (0.0, 1.0, 0.0)),
    )
    edges = ((fixture.structural_unit_ids[0], fixture.structural_unit_ids[1], "references"),)
    snapshot = builder.rebuild(
        canonical_snapshot_digest=_sha("snapshot"),
        embedding_profile_version="1.0.0",
        entries=entries,
        edges=edges,
    )
    assert snapshot.state is ProjectionState.READY
    assert builder.exact_fts(snapshot.lexical_index_version_id, "projection") == (
        fixture.structural_unit_ids[0],
    )
    assert (
        builder.vector_search(snapshot.embedding_index_version_id, (1.0, 0.0, 0.0))[0]
        == fixture.structural_unit_ids[0]
    )
    assert builder.graph_neighbors(
        snapshot.graph_projection_version_id, fixture.structural_unit_ids[0]
    ) == (fixture.structural_unit_ids[1],)
    builder.delete(snapshot)
    rebuilt = builder.rebuild(
        canonical_snapshot_digest=_sha("snapshot"),
        embedding_profile_version="1.0.0",
        entries=entries,
        edges=edges,
    )
    assert rebuilt.entry_digest == snapshot.entry_digest
    with postgres_environment.curator_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.structural_units WHERE normative_edition_id=:id"
                ),
                {"id": fixture.edition_id},
            )
            == 2
        )


def test_gateway_returns_evidence_and_explicit_gap_semantics(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    fixture = _canonical_fixture(postgres_environment)
    builder = ProjectionBuilder(postgres_environment.projection_engine)
    snapshot = builder.rebuild(
        canonical_snapshot_digest=_sha("gateway-snapshot"),
        embedding_profile_version="1.0.0",
        entries=(
            (fixture.structural_unit_ids[0], "Synthetic canonical assertion", (1.0, 0.0, 0.0)),
        ),
        edges=(),
    )
    gateway = KnowledgeGateway(
        PostgresKnowledgeQuery(postgres_environment.application_engine),
        PostgresKnowledgeAudit(
            postgres_environment.curator_engine, service_identity_id="service.knowledge-gateway"
        ),
    )
    context = GatewayContext(
        "identity.synthetic.reader",
        "knowledge.search.invoke",
        "qualification",
        uuid7(),
    )
    response = gateway.invoke(
        GatewayRequest(
            "knowledge.search",
            "0.1.0",
            "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge",
            "0.1.0",
            {
                "query": "canonical",
                "lexical_index_version_id": str(snapshot.lexical_index_version_id),
            },
        ),
        context,
    )
    assert response.status is GatewayStatus.OK
    assert response.evidence_pack.evidence[0].source_version_id == str(fixture.source_version_id)
    builder.delete(snapshot)
    unavailable = gateway.invoke(
        GatewayRequest(
            "knowledge.search",
            "0.1.0",
            "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge",
            "0.1.0",
            {
                "query": "canonical",
                "lexical_index_version_id": str(snapshot.lexical_index_version_id),
            },
        ),
        context,
    )
    assert unavailable.status is GatewayStatus.INDEX_UNAVAILABLE
    with postgres_environment.curator_engine.connect() as connection:
        audit = connection.execute(
            sa.text(
                "SELECT operation,outcome_code,capability FROM audit.platform_records "
                "ORDER BY recorded_at"
            )
        ).all()
    assert audit[-2:] == [
        ("knowledge.search", str(GatewayStatus.OK), "knowledge.search.invoke"),
        ("knowledge.search", str(GatewayStatus.INDEX_UNAVAILABLE), "knowledge.search.invoke"),
    ]


def test_workspace_source_rls_and_platform_customer_regulation_rejection(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    tenant_a = _create_tenant(postgres_environment)
    tenant_b = _create_tenant(postgres_environment)
    source_id = uuid7()
    from asd_kontur.persistence import WorkspaceUnitOfWork

    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant_a)
    ) as unit:
        assert unit.session is not None
        unit.session.execute(
            sa.text(
                "INSERT INTO workspace.source_artifacts "
                "(organization_id,workspace_id,source_artifact_id,source_kind,title,status,"
                "retention_class,created_by_identity_id,correlation_id) "
                "VALUES (:organization,:workspace,:source,'customer_regulation','Synthetic regulation',"
                "'active','workspace-source','identity.synthetic',:correlation)"
            ),
            {
                "organization": tenant_a.organization_id,
                "workspace": tenant_a.workspace_id,
                "source": source_id,
                "correlation": uuid7(),
            },
        )
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant_b)
    ) as unit:
        assert unit.session is not None
        assert unit.session.scalar(sa.text("SELECT count(*) FROM workspace.source_artifacts")) == 0
    with pytest.raises(DBAPIError):
        with WorkspaceUnitOfWork(
            postgres_environment.application_engine, _workspace_context(tenant_b)
        ) as unit:
            assert unit.session is not None
            unit.session.execute(
                sa.text(
                    "INSERT INTO workspace.source_artifacts "
                    "(organization_id,workspace_id,source_artifact_id,source_kind,title,status,"
                    "retention_class,created_by_identity_id,correlation_id) "
                    "VALUES (:organization,:workspace,:source,'rd','Cross-scope','active',"
                    "'workspace-source','identity.synthetic',:correlation)"
                ),
                {
                    "organization": tenant_a.organization_id,
                    "workspace": tenant_a.workspace_id,
                    "source": uuid7(),
                    "correlation": uuid7(),
                },
            )
    with pytest.raises(DBAPIError):
        with postgres_environment.curator_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.source_artifacts "
                    "(source_artifact_id,source_kind,title,issuer,jurisdiction,stable_designation,status,"
                    "retention_class,created_by_identity_id,correlation_id) "
                    "VALUES (:id,'customer_regulation','Forbidden','Synthetic issuer','Synthetic',"
                    "'FORBIDDEN','active','platform','identity.synthetic',:correlation)"
                ),
                {"id": uuid7(), "correlation": uuid7()},
            )


def test_published_assertion_without_evidence_is_rejected_and_promotion_has_no_live_fk(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    fixture = _canonical_fixture(postgres_environment)
    with pytest.raises(DBAPIError, match="requires exact evidence"):
        with postgres_environment.curator_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.knowledge_assertions "
                    "(knowledge_assertion_id,assertion_version,assertion_type,normalized_proposition,"
                    "structural_unit_id,applicability_context_id,status,reviewer_identity_id,"
                    "approval_decision_ref,integrity_digest,published_at) VALUES "
                    "(:id,1,'requirement','No evidence',:unit,:applicability,'published',"
                    "'identity.synthetic','decision.synthetic',:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": uuid7(),
                    "unit": fixture.structural_unit_ids[1],
                    "applicability": fixture.applicability_id,
                    "digest": _sha("no-evidence"),
                },
            )
    inspector = sa.inspect(postgres_environment.owner_engine)
    capsule_columns = {
        column["name"] for column in inspector.get_columns("evidence_capsules", schema="platform")
    }
    publication_fks = inspector.get_foreign_keys("promotion_publications", schema="platform")
    assert "workspace_id" not in capsule_columns
    assert "organization_id" not in capsule_columns
    assert all(fk["referred_schema"] != "workspace" for fk in publication_fks)


def test_platform_audit_is_append_only(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    audit = PostgresKnowledgeAudit(
        postgres_environment.curator_engine, service_identity_id="service.synthetic"
    )
    context = GatewayContext(
        "identity.synthetic",
        "knowledge.search.invoke",
        "qualification",
        uuid7(),
    )
    audit.record(
        context=context,
        tool="knowledge.search",
        status=GatewayStatus.NO_RESULT,
        evidence_count=0,
    )
    with postgres_environment.curator_engine.connect() as connection:
        audit_id = connection.scalar(
            sa.text(
                "SELECT audit_record_id FROM audit.platform_records ORDER BY recorded_at DESC LIMIT 1"
            )
        )
    for statement in (
        "UPDATE audit.platform_records SET outcome_code='changed' WHERE audit_record_id=:id",
        "DELETE FROM audit.platform_records WHERE audit_record_id=:id",
    ):
        with pytest.raises(DBAPIError):
            with postgres_environment.curator_engine.begin() as connection:
                connection.execute(sa.text(statement), {"id": audit_id})


def test_rule_registry_requires_evidence_and_separated_authorities(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    fixture = _canonical_fixture(postgres_environment)
    policy_id, rule_version_id = uuid7(), uuid7()
    with postgres_environment.curator_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.conflict_policy_versions "
                "(conflict_policy_version_id,conflict_group_key,version,subject_domain,predicate_contract,"
                "outcome_contract,authority_reference,status,integrity_digest) VALUES "
                "(:id,'synthetic-conflict','1.0.0','synthetic','{}'::jsonb,'{}'::jsonb,"
                "'authority.synthetic','active',:digest)"
            ),
            {"id": policy_id, "digest": _sha("conflict-policy")},
        )
    definition = RuleVersionDefinition(
        str(rule_version_id),
        f"synthetic.rule.{rule_version_id}",
        {"field": "synthetic_class", "operator": "eq", "value": "a"},
        {"required": True},
        ("synthetic-assertion-evidence",),
        str(policy_id),
        None,
        None,
    )
    service = RuleRegistryService(postgres_environment.curator_engine)
    service.register_version(
        definition=definition,
        rule_class="synthetic",
        purpose="qualification",
        applicability_context_id=fixture.applicability_id,
        author=AuthorityIdentity("identity.synthetic.author", "human"),
        test_manifest_digest=_sha("rule-tests"),
    )
    with pytest.raises(Exception, match="exact RuleEvidence"):
        service.transition(
            rule_version_id=rule_version_id,
            target=RuleState.EVIDENCE_ATTACHED,
            actor=AuthorityIdentity("identity.synthetic.author", "human"),
            decision_ref="decision.synthetic.evidence",
        )
    with postgres_environment.curator_engine.begin() as connection:
        assertion_evidence_id = connection.scalar(
            sa.text(
                "SELECT assertion_evidence_id FROM platform.assertion_evidence "
                "WHERE knowledge_assertion_id=:assertion"
            ),
            {"assertion": fixture.assertion_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.rule_evidence "
                "(rule_evidence_id,rule_version_id,assertion_evidence_id,source_authority_layer,"
                "applicability_basis,integrity_digest) VALUES "
                "(:id,:version,:evidence,'synthetic-official','synthetic-applicability',:digest)"
            ),
            {
                "id": uuid7(),
                "version": rule_version_id,
                "evidence": assertion_evidence_id,
                "digest": _sha("rule-evidence"),
            },
        )
    author = AuthorityIdentity("identity.synthetic.author", "human")
    reviewer = AuthorityIdentity("identity.synthetic.reviewer", "human")
    approver = AuthorityIdentity(
        "identity.synthetic.approver", "human", frozenset({"rule.approve"})
    )
    service.transition(
        rule_version_id=rule_version_id,
        target=RuleState.EVIDENCE_ATTACHED,
        actor=author,
        decision_ref="decision.synthetic.evidence",
    )
    service.transition(
        rule_version_id=rule_version_id,
        target=RuleState.CANDIDATE,
        actor=author,
        decision_ref="decision.synthetic.candidate",
    )
    service.transition(
        rule_version_id=rule_version_id,
        target=RuleState.REVIEWED,
        actor=reviewer,
        decision_ref="decision.synthetic.review",
        qualification_ref="qualification.synthetic.reviewer",
        test_manifest_digest=_sha("rule-tests"),
    )
    service.transition(
        rule_version_id=rule_version_id,
        target=RuleState.APPROVED,
        actor=approver,
        decision_ref="decision.synthetic.approval",
        qualification_ref="qualification.synthetic.approver",
    )
    service.transition(
        rule_version_id=rule_version_id,
        target=RuleState.ACTIVE,
        actor=approver,
        decision_ref="decision.synthetic.activation",
    )
    rule_set_id = uuid7()
    manifest_digest = service.publish_rule_set(
        rule_set_version_id=rule_set_id,
        rule_set_key=f"synthetic.rule-set.{rule_set_id}",
        version="1.0.0",
        members=((rule_version_id, definition.fingerprint()),),
        approver=approver,
    )
    with postgres_environment.curator_engine.connect() as connection:
        states = tuple(
            connection.execute(
                sa.text(
                    "SELECT status FROM platform.rule_version_states WHERE rule_version_id=:id "
                    "ORDER BY state_sequence"
                ),
                {"id": rule_version_id},
            ).scalars()
        )
    assert states == (
        "drafted",
        "evidence_attached",
        "candidate",
        "reviewed",
        "approved",
        "active",
    )
    assert manifest_digest.startswith("sha256:")
