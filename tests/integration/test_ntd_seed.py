from __future__ import annotations

# ruff: noqa: E501 -- exact designations and SQL are intentional.
import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from asd_kontur.domain import deterministic_uuid, uuid7
from asd_kontur.knowledge import InMemoryObjectStore
from asd_kontur.knowledge.gateway import (
    NTD_CONTRACT_VERSION,
    NTD_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayStatus,
    KnowledgeGateway,
)
from asd_kontur.knowledge.source_ledger import PlatformSourceAdmission, PlatformSourceLedger
from asd_kontur.lifecycle import PostgresWorkspaceStorageAdapter, StorageAdapterDefinition
from asd_kontur.ntd.durability import (
    NtdProjectionBuilder,
    build_backup_manifest,
    persist_backup_manifest,
    verify_restored_memory,
    verify_source_objects,
)
from asd_kontur.ntd.gateway import NtdKnowledgeQueryService
from asd_kontur.ntd.identifiers import normalize_identifier
from asd_kontur.ntd.manifest import (
    NTD_SEED_MANIFEST_PROFILE_VERSION,
    PracticeGuideNormativeReference,
    PracticeGuideNtdSeedManifest,
)
from asd_kontur.ntd.models import (
    EditionRelationshipKind,
    NormativeActivationDecision,
    NormativeArtifact,
    NormativeEditionRelationship,
    NormativeProvisionCandidate,
    NormativeProvisionKind,
    NormativeProvisionVersion,
    ProvisionVerificationStatus,
)
from asd_kontur.ntd.postgres import (
    NormativeDocumentRegistration,
    NormativeEditionRegistration,
    NtdPersistenceError,
    NtdRepository,
)
from asd_kontur.persistence import (
    OrganizationContext,
    OrganizationUnitOfWork,
    WorkspaceContext,
    WorkspaceUnitOfWork,
)
from asd_kontur.practice_guidance.postgres import PracticeGuideRepository

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres
ZERO = "sha256:" + "0" * 64
TEST_OBJECT_STORE = InMemoryObjectStore()


class AuditSpy:
    def record(self, **_: object) -> None:
        pass


@dataclass(frozen=True, slots=True)
class SeededNtd:
    seed_manifest_id: UUID
    seed_manifest_fingerprint: str
    guide_reference_id: UUID
    document_id: UUID
    edition_id: UUID
    edition_source_version_id: UUID
    artifact_source_version_id: UUID
    artifact_id: UUID
    stable_identity_key: str
    stable_designation: str


@dataclass(frozen=True, slots=True)
class WorkspaceTenant:
    organization_id: UUID
    construction_object_id: UUID
    workspace_id: UUID


def _workspace_context(tenant: WorkspaceTenant) -> WorkspaceContext:
    return WorkspaceContext(
        tenant.organization_id,
        tenant.workspace_id,
        "identity.synthetic.workspace",
        None,
        uuid7(),
    )


def _create_workspace(environment: PostgreSQLEnvironment) -> WorkspaceTenant:
    tenant = WorkspaceTenant(uuid7(), uuid7(), uuid7())
    with OrganizationUnitOfWork(
        environment.application_engine,
        OrganizationContext(
            tenant.organization_id,
            "identity.synthetic.workspace",
            None,
            uuid7(),
        ),
    ) as unit:
        assert unit.organizations is not None
        unit.organizations.add_organization(
            organization_id=tenant.organization_id,
            display_name="Synthetic NTD isolation organization",
        )
        unit.organizations.add_construction_object(
            construction_object_id=tenant.construction_object_id,
            display_name="Synthetic NTD isolation object",
        )
    with WorkspaceUnitOfWork(environment.application_engine, _workspace_context(tenant)) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_workspace(
            construction_object_id=tenant.construction_object_id,
            retention_profile_key="retention.synthetic",
            retention_profile_version="0.1.0",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    return tenant


def _admit(
    environment: PostgreSQLEnvironment,
    *,
    stable_designation: str,
    label: str,
    content: bytes,
    media_type: str,
    source_kind: str,
) -> object:
    return PlatformSourceLedger(environment.ntd_ingestion_engine, TEST_OBJECT_STORE).admit(
        PlatformSourceAdmission(
            None,
            stable_designation,
            f"Synthetic {stable_designation}",
            "Минстрой России",
            "RU",
            label,
            source_kind,
            f"https://minstroyrf.gov.ru/docs/{stable_designation}/",
            "official_https",
            "synthetic official fixture metadata",
            media_type,
            "public",
            "permanent_platform_core",
            "identity.synthetic.ntd-ingestion",
            uuid7(),
        ),
        content,
    )


def _seed_guide(environment: PostgreSQLEnvironment) -> tuple[UUID, UUID]:
    guide_token = uuid7()
    admitted = PlatformSourceLedger(environment.curator_engine, TEST_OBJECT_STORE).admit(
        PlatformSourceAdmission(
            None,
            f"synthetic-guide-{guide_token}",
            "Synthetic guide",
            "Synthetic author",
            "methodological",
            "edition-1",
            "methodological_practice_guide",
            "local-evidence://synthetic-guide.pdf",
            "verified_local_copy",
            "synthetic guide metadata",
            "application/pdf",
            "platform-methodological",
            "permanent_platform_core",
            "identity.synthetic.guide",
            uuid7(),
        ),
        f"synthetic guide bytes {guide_token}".encode(),
    )
    _, edition_id = PracticeGuideRepository(
        environment.guidance_ingestion_engine
    ).register_guide_edition(
        guide_key=f"synthetic-guide-{uuid7()}",
        title="Synthetic guide",
        edition_label="edition-1",
        source_artifact_id=admitted.source_artifact_id,
        source_version_id=admitted.source_version_id,
        source_digest=admitted.content_digest,
        page_count=19,
        provenance={"method": "synthetic"},
        actor_identity_id="identity.synthetic.guide",
    )
    return edition_id, admitted.source_version_id


def _seed_manifest(environment: PostgreSQLEnvironment) -> tuple[UUID, str, UUID]:
    guide_edition_id, guide_source_version_id = _seed_guide(environment)
    normalized = normalize_identifier("СП 543.1325800.2024")
    reference = PracticeGuideNormativeReference(
        reference_id=uuid7(),
        practice_guide_edition_id=guide_edition_id,
        source_version_id=guide_source_version_id,
        pdf_page=16,
        region=(0.1, 0.1, 0.9, 0.2),
        occurrence_ordinal=1,
        raw_designation="СП 543.1325800.2024",
        raw_title="Synthetic title",
        raw_context="Synthetic guide reference",
        normalized=normalized,
        extraction_method="native_pdf_three_column_row_v0.1",
        extraction_receipt_digest=ZERO,
        source_fragment_digest="sha256:" + hashlib.sha256(b"Synthetic guide reference").hexdigest(),
    )
    fingerprint = "sha256:" + hashlib.sha256(str(reference.reference_id).encode()).hexdigest()
    manifest = PracticeGuideNtdSeedManifest(
        profile_version=NTD_SEED_MANIFEST_PROFILE_VERSION,
        practice_guide_edition_id=guide_edition_id,
        source_version_id=guide_source_version_id,
        references=(reference,),
        identity_keys=(normalized.stable_identity_key,),
        page_counts=((15, 0), (16, 1), (17, 0), (18, 0), (19, 0)),
        fingerprint=fingerprint,
    )
    repository = NtdRepository(environment.ntd_ingestion_engine)
    manifest_id, duplicate = repository.register_seed_manifest(
        manifest,
        created_by_identity_id="identity.synthetic.ntd-ingestion",
        created_at=datetime.now(UTC),
    )
    repeated_id, repeated = repository.register_seed_manifest(
        manifest,
        created_by_identity_id="identity.synthetic.ntd-ingestion",
        created_at=datetime.now(UTC),
    )
    assert not duplicate and repeated and repeated_id == manifest_id
    return manifest_id, fingerprint, reference.reference_id


def _seed_ntd(environment: PostgreSQLEnvironment) -> SeededNtd:
    manifest_id, manifest_fingerprint, reference_id = _seed_manifest(environment)
    card_token = uuid7()
    card = _admit(
        environment,
        stable_designation=f"synthetic-sp543-card-{card_token}",
        label="catalog-419099",
        content=f"<!doctype html><html>synthetic official card {card_token}</html>".encode(),
        media_type="text/html",
        source_kind="official_reference",
    )
    repository = NtdRepository(environment.ntd_ingestion_engine)
    synthetic_suffix = str(uuid7())
    stable_identity_key = f"synthetic:ru:sp:543.1325800:{synthetic_suffix}"
    stable_designation = f"СП 543.1325800 synthetic {synthetic_suffix}"
    document_registration = NormativeDocumentRegistration(
        stable_identity_key=stable_identity_key,
        designation_namespace="RU:SP",
        stable_designation=stable_designation,
        title="Synthetic construction control",
        issuer="Минстрой России",
        jurisdiction="RU",
        document_class="code_of_practice",
        created_by_identity_id="identity.synthetic.ntd-ingestion",
    )
    document = repository.register_document(document_registration)
    repeated_document = repository.register_document(document_registration)
    assert not document.duplicate and repeated_document.duplicate
    edition_registration = NormativeEditionRegistration(
        normative_document_id=document.normative_document_id,
        edition_label="2024",
        source_version_id=card.source_version_id,
        official_catalog_id="419099",
        official_catalog_url="https://minstroyrf.gov.ru/docs/419099/",
        approval_metadata={"order": "synthetic"},
        effective_from=date(2025, 1, 1),
        effective_to=None,
        retrieved_at=datetime.now(UTC),
        admitted_by_identity_id="identity.synthetic.ntd-ingestion",
    )
    edition = repository.register_edition(edition_registration)
    repeated_edition = repository.register_edition(edition_registration)
    assert not edition.duplicate and repeated_edition.duplicate
    artifact_token = uuid7()
    artifact_content = f"%PDF-1.7\nsynthetic official bytes {artifact_token}".encode()
    artifact_source = _admit(
        environment,
        stable_designation=f"synthetic-sp543-pdf-{artifact_token}",
        label="artifact-2024",
        content=artifact_content,
        media_type="application/pdf",
        source_kind="normative_document",
    )
    artifact_id = uuid7()
    artifact = NormativeArtifact(
        normative_artifact_id=artifact_id,
        normative_edition_id=edition.normative_edition_id,
        source_version_id=artifact_source.source_version_id,
        official_catalog_id="419099",
        official_url="https://minstroyrf.gov.ru/upload/synthetic-sp543.pdf",
        filename="synthetic-sp543.pdf",
        media_type="application/pdf",
        size_bytes=len(artifact_content),
        content_digest=artifact_source.content_digest,
        relation_to_edition="primary_text",
        retrieval_metadata_digest=ZERO,
    )
    assert not repository.register_artifact(artifact, registered_at=datetime.now(UTC))
    assert repository.register_artifact(artifact, registered_at=datetime.now(UTC))
    return SeededNtd(
        manifest_id,
        manifest_fingerprint,
        reference_id,
        document.normative_document_id,
        edition.normative_edition_id,
        card.source_version_id,
        artifact_source.source_version_id,
        artifact_id,
        stable_identity_key,
        stable_designation,
    )


def test_document_edition_artifact_registration_is_idempotent_and_immutable(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    repository = NtdRepository(postgres_environment.ntd_ingestion_engine)
    with pytest.raises(NtdPersistenceError, match="conflicting metadata"):
        repository.register_document(
            NormativeDocumentRegistration(
                seeded.stable_identity_key,
                "RU:SP",
                seeded.stable_designation,
                "Conflicting title",
                "Минстрой России",
                "RU",
                "code_of_practice",
                "identity.synthetic.ntd-ingestion",
            )
        )
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_documents "
                    "WHERE normative_document_id=:id"
                ),
                {"id": seeded.document_id},
            )
            == 1
        )


def test_new_edition_preserves_old_and_as_of_requires_activation(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    repository = NtdRepository(postgres_environment.ntd_ingestion_engine)
    new_card_token = uuid7()
    new_card = _admit(
        postgres_environment,
        stable_designation=f"synthetic-sp543-card-2025-{new_card_token}",
        label="catalog-500000",
        content=(
            f"<!doctype html><html>synthetic new official card {new_card_token}</html>".encode()
        ),
        media_type="text/html",
        source_kind="official_reference",
    )
    new_edition = repository.register_edition(
        NormativeEditionRegistration(
            seeded.document_id,
            "2025",
            new_card.source_version_id,
            "500000",
            "https://minstroyrf.gov.ru/docs/500000/",
            {"order": "synthetic-new"},
            date(2026, 1, 1),
            None,
            datetime.now(UTC),
            "identity.synthetic.ntd-ingestion",
        )
    )
    repository.register_relationship(
        NormativeEditionRelationship(
            uuid7(),
            new_edition.normative_edition_id,
            seeded.edition_id,
            EditionRelationshipKind.SUPERSEDES,
            "official-card:500000",
            None,
            "verified",
        ),
        recorded_at=datetime.now(UTC),
    )
    decision_id = deterministic_uuid(f"activation:{seeded.document_id}")
    repository.record_activation(
        NormativeActivationDecision(
            decision_id,
            1,
            seeded.document_id,
            seeded.edition_id,
            date(2025, 1, 1),
            "active",
            "official-card:419099",
            ("official-card:419099",),
            None,
            datetime.now(UTC),
        )
    )
    repository.record_activation(
        NormativeActivationDecision(
            decision_id,
            2,
            seeded.document_id,
            new_edition.normative_edition_id,
            date(2026, 1, 1),
            "active",
            "official-card:500000",
            ("official-card:500000",),
            1,
            datetime.now(UTC),
        )
    )
    assert (
        repository.resolve_edition_as_of(seeded.document_id, date(2025, 6, 1)) == seeded.edition_id
    )
    assert (
        repository.resolve_edition_as_of(seeded.document_id, date(2026, 6, 1))
        == new_edition.normative_edition_id
    )
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_editions "
                    "WHERE normative_document_id=:document"
                ),
                {"document": seeded.document_id},
            )
            == 2
        )


def test_verified_provision_gateway_backup_and_projection_rebuild(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    with postgres_environment.owner_engine.connect() as connection:
        rules_before = int(connection.scalar(sa.text("SELECT count(*) FROM platform.rules")))
    locator_id = uuid7()
    structural_id = uuid7()
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.source_locators "
                "(source_locator_id,source_version_id,locator_kind,locator_key,locator_value,fragment_digest) "
                "VALUES (:id,:source,'page_region','7.2',CAST(:value AS jsonb),:digest)"
            ),
            {
                "id": locator_id,
                "source": seeded.artifact_source_version_id,
                "value": '{"page":7,"region":[0.1,0.1,0.9,0.2]}',
                "digest": ZERO,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.structural_units "
                "(structural_unit_id,normative_edition_id,unit_type,structural_path,ordinal,"
                "source_locator_id,normalized_text,content_digest) "
                "VALUES (:id,:edition,'clause','7.2',1,:locator,:text,:digest)"
            ),
            {
                "id": structural_id,
                "edition": seeded.edition_id,
                "locator": locator_id,
                "text": "Synthetic exact normative provision",
                "digest": ZERO,
            },
        )
    candidate = NormativeProvisionCandidate(
        uuid7(),
        1,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        "7.2",
        NormativeProvisionKind.CLAUSE,
        7,
        (0.1, 0.1, 0.9, 0.2),
        "Synthetic exact normative provision",
        "native_pdf_layout",
        "ntd_native_pdf_layout_v0.1",
        ZERO,
        None,
    )
    repository = NtdRepository(postgres_environment.ntd_ingestion_engine)
    assert not repository.register_provision_candidate(candidate)
    provision = NormativeProvisionVersion(
        uuid7(),
        1,
        candidate.candidate_id,
        1,
        seeded.edition_id,
        seeded.artifact_source_version_id,
        "7.2",
        NormativeProvisionKind.CLAUSE,
        7,
        (0.1, 0.1, 0.9, 0.2),
        candidate.verbatim_text,
        ZERO,
        "sha256:" + hashlib.sha256(b"semantic-provision").hexdigest(),
        ProvisionVerificationStatus.VERIFIED,
        "decision:synthetic-human-verification",
        "identity.synthetic.verifier",
        datetime.now(UTC),
    )
    assert not repository.publish_provision(provision, structural_unit_id=structural_id)

    decision_id = deterministic_uuid(f"activation:{seeded.document_id}:single")
    repository.record_activation(
        NormativeActivationDecision(
            decision_id,
            1,
            seeded.document_id,
            seeded.edition_id,
            date(2025, 1, 1),
            "active",
            "official-card:419099",
            ("official-card:419099",),
            None,
            datetime.now(UTC),
        )
    )
    backup = build_backup_manifest(
        postgres_environment.ntd_gateway_engine,
        seed_manifest_fingerprint=seeded.seed_manifest_fingerprint,
    )
    assert not persist_backup_manifest(postgres_environment.ntd_ingestion_engine, backup)
    verify_restored_memory(postgres_environment.ntd_gateway_engine, backup)
    assert verify_source_objects(postgres_environment.ntd_gateway_engine, TEST_OBJECT_STORE) >= 2

    projection = NtdProjectionBuilder(postgres_environment.projection_engine)
    first_id, first_count = projection.rebuild(backup.canonical_semantic_fingerprint)
    projection.delete_rebuildable_plane()
    second_id, second_count = projection.rebuild(backup.canonical_semantic_fingerprint)
    assert (first_id, first_count) == (second_id, second_count) == (first_id, 1)
    verify_restored_memory(postgres_environment.ntd_gateway_engine, backup)

    gateway = KnowledgeGateway(
        NtdKnowledgeQueryService(postgres_environment.ntd_gateway_engine), AuditSpy()
    )
    response = gateway.invoke(
        GatewayRequest(
            "knowledge.get_ntd_provision",
            NTD_CONTRACT_VERSION,
            NTD_SCHEMA_ID,
            NTD_CONTRACT_VERSION,
            {"edition_id": str(seeded.edition_id), "locator": "7.2"},
        ),
        GatewayContext(
            "model:any-provider",
            "knowledge.get_ntd_provision.invoke",
            "id_analysis",
            uuid7(),
        ),
    )
    assert response.status is GatewayStatus.OK
    assert response.evidence_pack.evidence[0].authority_layer == "normative_authority"
    assert response.result["practice_recommendation"] is None
    assert response.result["deterministic_rule_version"] is None
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            int(connection.scalar(sa.text("SELECT count(*) FROM platform.rules"))) == rules_before
        )


def test_workspace_application_cannot_mutate_ntd_but_gateway_can_read(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    with pytest.raises(DBAPIError):
        with postgres_environment.application_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.normative_documents "
                    "(normative_document_id,designation_namespace,designation,title,issuer,"
                    "jurisdiction,document_class,created_by_identity_id) "
                    "VALUES (:id,'RU:SP','СП 999','forbidden','x','RU','code_of_practice','workspace')"
                ),
                {"id": uuid7()},
            )
    with postgres_environment.ntd_gateway_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_editions "
                    "WHERE normative_edition_id=:edition"
                ),
                {"edition": seeded.edition_id},
            )
            == 1
        )


def test_workspace_reset_does_not_change_platform_ntd_memory(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    seeded = _seed_ntd(postgres_environment)
    tenant = _create_workspace(postgres_environment)
    with WorkspaceUnitOfWork(
        postgres_environment.application_engine, _workspace_context(tenant)
    ) as unit:
        assert unit.workspaces is not None
        unit.workspaces.create_mode_execution(
            mode_execution_id=uuid7(),
            mode="Audit",
            purpose="id.normative-audit",
            input_manifest_ref="manifest.synthetic.ntd",
            policy_assignment_key="policy.synthetic",
            policy_assignment_version="0.1.0",
            rule_set_key="rules.synthetic",
            rule_set_version="0.1.0",
        )
    adapter = PostgresWorkspaceStorageAdapter(
        postgres_environment.destruction_engine,
        tenant.organization_id,
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
    before = build_backup_manifest(
        postgres_environment.ntd_gateway_engine,
        seed_manifest_fingerprint=seeded.seed_manifest_fingerprint,
    ).canonical_semantic_fingerprint
    for item in adapter.inventory(tenant.workspace_id):
        adapter.purge_item(
            workspace_id=tenant.workspace_id,
            item_id=item.item_id,
            operation_id=uuid7(),
        )
    after = build_backup_manifest(
        postgres_environment.ntd_gateway_engine,
        seed_manifest_fingerprint=seeded.seed_manifest_fingerprint,
    ).canonical_semantic_fingerprint
    assert after == before
    with postgres_environment.owner_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM platform.normative_editions "
                    "WHERE normative_edition_id=:edition"
                ),
                {"edition": seeded.edition_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.mode_executions WHERE workspace_id=:workspace"
                ),
                {"workspace": tenant.workspace_id},
            )
            == 0
        )
