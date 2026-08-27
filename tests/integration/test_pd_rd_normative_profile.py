from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa

from asd_kontur.domain import uuid7
from asd_kontur.knowledge import AuthorityIdentity, GatewayContext, GatewayRequest, KnowledgeGateway
from asd_kontur.knowledge.gateway import (
    PD_RD_NTD_CONTRACT_VERSION,
    PD_RD_NTD_SCHEMA_ID,
    GatewayStatus,
)
from asd_kontur.knowledge.postgres import RuleRegistryService
from asd_kontur.knowledge.rules import RuleState, RuleVersionDefinition
from asd_kontur.ntd.gateway import NtdKnowledgeQueryService
from asd_kontur.ntd.models import (
    AcquisitionTerminalStatus,
    ApplicabilityPredicate,
    CorpusMemberStatus,
    NormativeCorpusManifest,
    NormativeCorpusMember,
    NormativeProvisionCandidate,
    NormativeProvisionKind,
    NormativeProvisionVersion,
    OfficialProvider,
    OfficialProviderHealthReceipt,
    ProviderAccessStatus,
    ProvisionVerificationStatus,
    RuleNormativeProvisionEvidence,
)
from asd_kontur.ntd.pd_rd import PdRdNormativeProfileRepository, PdRdProfileContext
from asd_kontur.ntd.postgres import NtdRepository

from .conftest import PostgreSQLEnvironment
from .test_ntd_seed import _seed_ntd
from .test_postgresql_foundation import _create_tenant

pytestmark = pytest.mark.postgres


class _AuditSpy:
    def record(self, **_: object) -> None:
        pass


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def test_provider_health_and_official_corpus_manifest_are_idempotent(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    repository = NtdRepository(postgres_environment.ntd_ingestion_engine)
    with postgres_environment.owner_engine.connect() as connection:
        provisions_before = int(
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_provision_versions"))
            or 0
        )
    checked_at = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)
    health = OfficialProviderHealthReceipt(
        uuid7(),
        OfficialProvider.ROSSTANDART_FUND,
        "https://protect.gost.ru/document1.aspx",
        "direct",
        checked_at,
        ProviderAccessStatus.AVAILABLE,
        200,
        _sha("synthetic-provider-response"),
        None,
    )
    member = NormativeCorpusMember(
        uuid7(),
        1,
        "ru:gost-r:21.001:2021",
        "ГОСТ Р 21.001-2021",  # noqa: RUF001
        "Система проектной документации для строительства. Общие положения",
        "synthetic-catalog-id",
        "https://protect.gost.ru/document.aspx?control=7&id=synthetic-catalog-id",
        CorpusMemberStatus.ACTIVE,
        None,
        None,
        "Synthetic official metadata scope; no provision publication.",
        {"qualification_fixture": "metadata_only"},
        AcquisitionTerminalStatus.OFFICIAL_METADATA_ONLY,
        _sha("synthetic-official-card-metadata"),
    )
    manifest = NormativeCorpusManifest(
        uuid7(),
        1,
        "ru:spds",
        "Система проектной документации для строительства",
        OfficialProvider.ROSSTANDART_FUND,
        ("https://protect.gost.ru/search.aspx",),
        1,
        (member,),
        "rosstandart-spds-manifest-v0.1",
        checked_at,
    )

    assert not repository.record_provider_health(health)
    assert repository.record_provider_health(health)
    assert not repository.register_corpus_manifest(manifest)
    assert repository.register_corpus_manifest(manifest)
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM platform.official_provider_health_receipts")
            )
            == 1
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_corpus_manifests"))
            == 1
        )
        row = connection.execute(
            sa.text(
                "SELECT denominator,manifest_fingerprint FROM "
                "platform.normative_corpus_manifests WHERE corpus_key='ru:spds'"
            )
        ).one()
        assert int(row.denominator) == 1
        assert str(row.manifest_fingerprint) == manifest.fingerprint
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_corpus_members"))
            == 1
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM platform.normative_provision_versions"))
            == provisions_before
        )


def _seed_exact_normative_rule(
    environment: PostgreSQLEnvironment,
) -> tuple[UUID, UUID, UUID, UUID]:
    seeded = _seed_ntd(environment)
    repository = NtdRepository(environment.ntd_ingestion_engine)
    text = "Synthetic section is required for a non-linear capital construction object."
    candidate = NormativeProvisionCandidate(
        uuid7(),
        1,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        "appendix/section-1",
        NormativeProvisionKind.CLAUSE,
        3,
        (0.1, 0.2, 0.9, 0.3),
        text,
        "native_pdf_layout",
        "ntd-native-layout-v1",
        _sha(text),
        None,
    )
    assert not repository.register_provision_candidate(candidate)
    structural_id = repository.register_structural_unit_for_candidate(candidate)
    provision_id = uuid7()
    provision = NormativeProvisionVersion(
        provision_id,
        1,
        candidate.candidate_id,
        1,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        candidate.structural_path,
        candidate.provision_kind,
        candidate.page_number,
        candidate.region,
        candidate.verbatim_text,
        candidate.content_digest,
        _sha("verified-section-1"),
        ProvisionVerificationStatus.VERIFIED,
        "decision:synthetic-exact-human-verification",
        "identity.synthetic.normative-verifier",
        datetime.now(UTC),
    )
    assert not repository.publish_provision(provision, structural_unit_id=structural_id)
    with environment.owner_engine.connect() as connection:
        locator_id = UUID(
            str(
                connection.scalar(
                    sa.text(
                        "SELECT source_locator_id FROM platform.structural_units "
                        "WHERE structural_unit_id=:unit"
                    ),
                    {"unit": structural_id},
                )
            )
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_structural_fragments "
                    "WHERE structural_unit_id=:unit AND source_version_id=:source"
                ),
                {"unit": structural_id, "source": seeded.artifact_source_version_id},
            )
            == 1
        )
    applicability_context_id = uuid7()
    policy_id = uuid7()
    policy_key = f"pd-rd-section-{policy_id}"
    with environment.curator_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.applicability_contexts "
                "(applicability_context_id,context_version,dimensions,unknown_behavior,"
                "integrity_digest) "
                "VALUES (:id,1,'{\"object_kind\":\"non_linear\"}'::jsonb,'block',:digest)"
            ),
            {"id": applicability_context_id, "digest": _sha("non-linear-context")},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.conflict_policy_versions "
                "(conflict_policy_version_id,conflict_group_key,version,subject_domain,"
                "predicate_contract,outcome_contract,authority_reference,status,integrity_digest) "
                "VALUES (:id,:key,'1.0.0','pd-rd','{}'::jsonb,'{}'::jsonb,"
                "'qualification:synthetic','active',:digest)"
            ),
            {"id": policy_id, "key": policy_key, "digest": _sha(f"pd-rd-policy:{policy_id}")},
        )
    rule_version_id = uuid7()
    definition = RuleVersionDefinition(
        str(rule_version_id),
        f"pd-rd.synthetic.required-section.{rule_version_id}",
        {"field": "object_kind", "operator": "eq", "value": "non_linear"},
        {"requirement_kind": "pd_section", "section": "1", "required": True},
        (f"normative-provision:{provision_id}:1",),
        str(policy_id),
        "2025-01-01",
        None,
    )
    rules = RuleRegistryService(environment.curator_engine)
    rules.register_version(
        definition=definition,
        rule_class="pd-rd-completeness",
        purpose="deterministic normative completeness",
        applicability_context_id=applicability_context_id,
        author=AuthorityIdentity("identity.synthetic.rule-author", "human"),
        test_manifest_digest=_sha("pd-rd-rule-tests"),
    )
    predicate_id = uuid7()
    predicate_payload = {"object_kind": "non_linear"}
    predicate_fingerprint = ApplicabilityPredicate.compute_fingerprint(
        provision_id=provision_id,
        provision_version=1,
        predicate=predicate_payload,
        required_inputs=("object_kind",),
        exclusions=(),
    )
    predicate = ApplicabilityPredicate(
        predicate_id,
        1,
        provision_id,
        1,
        predicate_payload,
        ("object_kind",),
        (),
        predicate_fingerprint,
    )
    assert not repository.register_applicability_predicate(
        predicate,
        qualified_by_identity_id="identity.synthetic.normative-verifier",
        qualification_decision_ref="qualification:synthetic-applicability",
        qualified_at=datetime.now(UTC),
    )
    assert not repository.link_rule_to_verified_provision(
        RuleNormativeProvisionEvidence(
            uuid7(),
            rule_version_id,
            provision_id,
            1,
            seeded.edition_id,
            seeded.artifact_source_version_id,
            locator_id,
            predicate_id,
            1,
            "qualification:synthetic-rule-to-provision",
            candidate.content_digest,
            datetime.now(UTC),
        )
    )
    author = AuthorityIdentity("identity.synthetic.rule-author", "human")
    reviewer = AuthorityIdentity("identity.synthetic.rule-reviewer", "human")
    approver = AuthorityIdentity(
        "identity.synthetic.rule-approver", "human", frozenset({"rule.approve"})
    )
    rules.transition(
        rule_version_id=rule_version_id,
        target=RuleState.EVIDENCE_ATTACHED,
        actor=author,
        decision_ref="decision:synthetic-evidence",
    )
    rules.transition(
        rule_version_id=rule_version_id,
        target=RuleState.CANDIDATE,
        actor=author,
        decision_ref="decision:synthetic-candidate",
    )
    rules.transition(
        rule_version_id=rule_version_id,
        target=RuleState.REVIEWED,
        actor=reviewer,
        decision_ref="decision:synthetic-review",
        qualification_ref="qualification:synthetic-reviewer",
        test_manifest_digest=_sha("pd-rd-rule-tests"),
    )
    rules.transition(
        rule_version_id=rule_version_id,
        target=RuleState.APPROVED,
        actor=approver,
        decision_ref="decision:synthetic-approval",
        qualification_ref="qualification:synthetic-approver",
    )
    rules.transition(
        rule_version_id=rule_version_id,
        target=RuleState.ACTIVE,
        actor=approver,
        decision_ref="decision:synthetic-activation",
    )
    return (
        rule_version_id,
        provision_id,
        seeded.edition_id,
        seeded.artifact_source_version_id,
    )


def test_exact_normative_rule_assembles_profile_and_gateway_evidence(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    rule_id, provision_id, edition_id, source_version_id = _seed_exact_normative_rule(
        postgres_environment
    )
    tenant = _create_tenant(postgres_environment)
    project_id = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.project_definition_versions "
                "(organization_id,workspace_id,project_definition_id,version,purpose,object_class,"
                "source_version_ids,definition,fingerprint,created_at) VALUES "
                "(:organization,:workspace,:project,1,'synthetic','non_linear',:sources,"
                '\'{"object_kind":"non_linear"}\'::jsonb,:fingerprint,CURRENT_TIMESTAMP)'
            ),
            {
                "organization": tenant.organization_id,
                "workspace": tenant.workspace_id,
                "project": project_id,
                "sources": [source_version_id],
                "fingerprint": _sha(f"project:{project_id}"),
            },
        )
    context = PdRdProfileContext(
        tenant.organization_id,
        tenant.workspace_id,
        project_id,
        1,
        date(2026, 8, 26),
        {"object_kind": "non_linear"},
    )
    profile = PdRdNormativeProfileRepository(postgres_environment.document_worker_engine).assemble(
        context, created_at=datetime.now(UTC)
    )
    assert profile.completeness_status == "complete"
    assert profile.normative_edition_ids == (edition_id,)
    assert profile.rule_version_ids == (rule_id,)
    assert profile.corpus_denominator["spds_members"] == 1
    assert len(profile.required_pd_sections) == 1
    requirement = profile.required_pd_sections[0]
    assert requirement["normative_provision_id"] == str(provision_id)
    assert requirement["source_version_id"] == str(source_version_id)
    assert requirement["authority_layer"] == "normative_authority"

    gateway = KnowledgeGateway(
        NtdKnowledgeQueryService(postgres_environment.ntd_gateway_engine), _AuditSpy()
    )
    response = gateway.invoke(
        GatewayRequest(
            "knowledge.resolve_applicable_pd_sections",
            PD_RD_NTD_CONTRACT_VERSION,
            PD_RD_NTD_SCHEMA_ID,
            PD_RD_NTD_CONTRACT_VERSION,
            {"profile_id": str(profile.profile_id), "version": 1},
        ),
        GatewayContext(
            "identity.synthetic.workspace",
            "knowledge.resolve_applicable_pd_sections.invoke",
            "project-understanding",
            uuid7(),
            tenant.organization_id,
            tenant.workspace_id,
        ),
    )
    assert response.status is GatewayStatus.OK
    assert response.result["corpus_denominator"]["spds_members"] == 1
    assert len(response.evidence_pack.evidence) == 1
    assert response.evidence_pack.evidence[0].source_version_id == str(source_version_id)
    assert response.evidence_pack.evidence[0].edition_id == str(edition_id)

    other = _create_tenant(postgres_environment)
    hidden = gateway.invoke(
        GatewayRequest(
            "knowledge.resolve_applicable_pd_sections",
            PD_RD_NTD_CONTRACT_VERSION,
            PD_RD_NTD_SCHEMA_ID,
            PD_RD_NTD_CONTRACT_VERSION,
            {"profile_id": str(profile.profile_id), "version": 1},
        ),
        GatewayContext(
            "identity.synthetic.other",
            "knowledge.resolve_applicable_pd_sections.invoke",
            "project-understanding",
            uuid7(),
            other.organization_id,
            other.workspace_id,
        ),
    )
    assert hidden.status is GatewayStatus.NO_RESULT


def test_missing_applicability_date_remains_typed_gap(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    _rule_id, _provision_id, _edition_id, source_version_id = _seed_exact_normative_rule(
        postgres_environment
    )
    tenant = _create_tenant(postgres_environment)
    project_id = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace.project_definition_versions "
                "(organization_id,workspace_id,project_definition_id,version,purpose,object_class,"
                "source_version_ids,definition,fingerprint,created_at) VALUES "
                "(:organization,:workspace,:project,1,'synthetic','non_linear',:sources,'{}'::jsonb,"
                ":fingerprint,CURRENT_TIMESTAMP)"
            ),
            {
                "organization": tenant.organization_id,
                "workspace": tenant.workspace_id,
                "project": project_id,
                "sources": [source_version_id],
                "fingerprint": _sha(f"project-missing-date:{project_id}"),
            },
        )
    profile = PdRdNormativeProfileRepository(postgres_environment.document_worker_engine).assemble(
        PdRdProfileContext(
            tenant.organization_id,
            tenant.workspace_id,
            project_id,
            1,
            None,
            {"object_kind": "non_linear"},
        ),
        created_at=datetime.now(UTC),
    )
    assert profile.completeness_status == "blocked"
    assert profile.corpus_denominator["spds_members"] == 1
    assert profile.normative_edition_ids == ()
    assert "applicable_on" in profile.unresolved_inputs
    assert {gap["code"] for gap in profile.gaps} >= {
        "VERIFIED_PD_RD_NTD_UNAVAILABLE",
        "ACTIVE_PD_RD_RULE_VERSION_UNAVAILABLE",
        "NORMATIVE_APPLICABILITY_INPUT_MISSING",
    }
