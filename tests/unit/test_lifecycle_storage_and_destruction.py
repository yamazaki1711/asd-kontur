from __future__ import annotations

import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import (
    AdapterOutcome,
    ArchiveEntry,
    AssuranceClass,
    Authority,
    Basis,
    ContainedFilesystemAdapter,
    DestructionCoordinator,
    ExactVersionReference,
    InMemoryStorageAdapter,
    LifecycleError,
    LifecycleErrorCode,
    PortableArchiveService,
    RegistrySnapshot,
    RetentionProfile,
    StorageAdapterDefinition,
    VerificationOutcome,
)

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000000610")
WORKSPACE_A = UUID("018f5c3e-7b00-7000-8000-000000000611")
WORKSPACE_B = UUID("018f5c3e-7b00-7000-8000-000000000612")
NOW = datetime(2026, 8, 23, tzinfo=UTC)


def definition(key: str = "synthetic.objects") -> StorageAdapterDefinition:
    return StorageAdapterDefinition(
        key,
        "0.1.0",
        "workspace_object_store",
        "authoritative",
        "workspace",
        True,
        True,
        True,
        True,
        True,
        "1.0.0",
    )


def authorities() -> tuple[Authority, Authority, Authority, Authority]:
    return (
        Authority("human.requester", "human", frozenset({"workspace.reset.plan"})),
        Authority("human.confirmer", "human", frozenset({"workspace.reset.authorize"})),
        Authority("service.executor", "service", frozenset({"workspace.purge.execute"})),
        Authority("human.verifier", "human", frozenset({"workspace.reset.verify"})),
    )


def coordinator_with_item() -> tuple[DestructionCoordinator, InMemoryStorageAdapter]:
    adapter = InMemoryStorageAdapter(definition())
    adapter.put(WORKSPACE_A, "source:1", b"synthetic-alpha", "text/plain")
    adapter.put(WORKSPACE_B, "source:1", b"synthetic-beta", "text/plain")
    return (
        DestructionCoordinator(
            RegistrySnapshot(ExactVersionReference("adapters.synthetic", "0.1.0"), (adapter,))
        ),
        adapter,
    )


def profile(*, environment: str = "development", approved: bool = False) -> RetentionProfile:
    return RetentionProfile(
        ExactVersionReference("retention.synthetic", "0.1.0"),
        environment,
        frozenset({"workspace_object_store"}),
        True,
        approved,
    )


def basis() -> Basis:
    return Basis(
        ExactVersionReference("basis.synthetic", "0.1.0"),
        "SYNTHETIC_TEST_DISPOSAL",
        ("evidence:synthetic-test-boundary",),
        NOW + timedelta(hours=2),
    )


def test_plan_authorize_purge_verify_and_development_attestation() -> None:
    coordinator, adapter = coordinator_with_item()
    requester, confirmer, executor, verifier = authorities()
    plan = coordinator.plan(
        operation_kind="reset",
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_A,
        lifecycle_version=11,
        workspace_revision=3,
        profile=profile(),
        basis=basis(),
        requester=requester,
        legal_hold_active=False,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    authorization = coordinator.authorize(
        plan=plan,
        requester=requester,
        confirmer=confirmer,
        executor=executor,
        verifier=verifier,
        current_lifecycle_version=11,
        legal_hold_active=False,
        now=NOW,
    )
    purge = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=NOW,
    )
    assert purge.complete
    assert purge.receipts[0].outcome is AdapterOutcome.DELETED
    repeated = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=NOW,
        operation_id=purge.operation_id,
    )
    assert repeated.receipts == purge.receipts
    scans = coordinator.verify(
        plan=plan,
        known_ids=frozenset({"source:1"}),
        known_digests=frozenset(),
        known_fragments=frozenset({"synthetic-alpha"}),
        now=NOW,
    )
    attestation = coordinator.attest(
        plan=plan,
        authorization=authorization,
        receipts=purge.receipts,
        scans=scans,
        profile=profile(),
        platform_integrity_before="sha256:" + "a" * 64,
        platform_integrity_after="sha256:" + "a" * 64,
        legal_hold_check_ids=(uuid7(),),
        verifier=verifier,
        now=NOW,
        requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
    )
    assert attestation.outcome is VerificationOutcome.VERIFIED
    assert attestation.assurance_class is AssuranceClass.DEVELOPMENT_DISPOSABLE
    assert adapter.read(WORKSPACE_B, "source:1") == b"synthetic-beta"


def test_changed_inventory_hold_and_same_actor_authorization_fail_closed() -> None:
    coordinator, adapter = coordinator_with_item()
    requester, confirmer, executor, verifier = authorities()
    plan = coordinator.plan(
        operation_kind="reset",
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_A,
        lifecycle_version=1,
        workspace_revision=1,
        profile=profile(),
        basis=basis(),
        requester=requester,
        legal_hold_active=False,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    adapter.put(WORKSPACE_A, "late", b"late", "text/plain")
    with pytest.raises(LifecycleError) as changed:
        coordinator.authorize(
            plan=plan,
            requester=requester,
            confirmer=confirmer,
            executor=executor,
            verifier=verifier,
            current_lifecycle_version=1,
            legal_hold_active=False,
            now=NOW,
        )
    assert changed.value.code is LifecycleErrorCode.INVENTORY_CHANGED
    with pytest.raises(LifecycleError) as held:
        coordinator.plan(
            operation_kind="reset",
            organization_id=ORGANIZATION_ID,
            workspace_id=WORKSPACE_A,
            lifecycle_version=1,
            workspace_revision=1,
            profile=profile(),
            basis=basis(),
            requester=requester,
            legal_hold_active=True,
            now=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    assert held.value.code is LifecycleErrorCode.LEGAL_HOLD_ACTIVE


def test_workspace_deletion_cannot_address_permanent_practice_memory() -> None:
    coordinator, _adapter = coordinator_with_item()
    requester, _confirmer, _executor, _verifier = authorities()
    permanent_profile = RetentionProfile(
        ExactVersionReference("retention.invalid-platform-core", "0.1.0"),
        "development",
        frozenset({"workspace_object_store", "permanent_platform_core"}),
        True,
        False,
    )
    with pytest.raises(LifecycleError) as blocked:
        coordinator.plan(
            operation_kind="reset",
            organization_id=ORGANIZATION_ID,
            workspace_id=WORKSPACE_A,
            lifecycle_version=1,
            workspace_revision=1,
            profile=permanent_profile,
            basis=basis(),
            requester=requester,
            legal_hold_active=False,
            now=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    assert blocked.value.code is LifecycleErrorCode.POLICY_BLOCKED


def test_workspace_deletion_registry_rejects_platform_scoped_adapter() -> None:
    platform_definition = StorageAdapterDefinition(
        "platform.practice-memory",
        "0.1.0",
        "platform_object_store",
        "authoritative",
        "platform",
        True,
        True,
        False,
        True,
        False,
        "1.0.0",
    )
    adapter = InMemoryStorageAdapter(platform_definition)
    coordinator = DestructionCoordinator(
        RegistrySnapshot(ExactVersionReference("adapters.invalid", "0.1.0"), (adapter,))
    )
    requester, _confirmer, _executor, _verifier = authorities()
    with pytest.raises(LifecycleError) as blocked:
        coordinator.plan(
            operation_kind="reset",
            organization_id=ORGANIZATION_ID,
            workspace_id=WORKSPACE_A,
            lifecycle_version=1,
            workspace_revision=1,
            profile=profile(),
            basis=basis(),
            requester=requester,
            legal_hold_active=False,
            now=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    assert blocked.value.code is LifecycleErrorCode.PLAN_INVALID


def test_partial_adapter_failure_never_attests_verified() -> None:
    coordinator, adapter = coordinator_with_item()
    requester, confirmer, executor, verifier = authorities()
    plan = coordinator.plan(
        operation_kind="reset",
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_A,
        lifecycle_version=1,
        workspace_revision=1,
        profile=profile(),
        basis=basis(),
        requester=requester,
        legal_hold_active=False,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    authorization = coordinator.authorize(
        plan=plan,
        requester=requester,
        confirmer=confirmer,
        executor=executor,
        verifier=verifier,
        current_lifecycle_version=1,
        legal_hold_active=False,
        now=NOW,
    )
    adapter.fail_items.add("source:1")
    purge = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=NOW,
    )
    checkpoint = coordinator.checkpoint(plan=plan, outcome=purge, now=NOW)
    scans = coordinator.verify(
        plan=plan,
        known_ids=frozenset({"source:1"}),
        known_digests=frozenset(),
        known_fragments=frozenset(),
        now=NOW,
    )
    attestation = coordinator.attest(
        plan=plan,
        authorization=authorization,
        receipts=purge.receipts,
        scans=scans,
        profile=profile(),
        platform_integrity_before="sha256:" + "a" * 64,
        platform_integrity_after="sha256:" + "a" * 64,
        legal_hold_check_ids=(uuid7(),),
        verifier=verifier,
        now=NOW,
        requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
    )
    assert not purge.complete
    assert checkpoint.plan_digest == plan.digest
    assert checkpoint.pending_items == ("synthetic.objects:source:1",)
    assert checkpoint.affected_adapters == ("synthetic.objects",)
    assert attestation.outcome is VerificationOutcome.INCOMPLETE


def test_development_profile_cannot_claim_production_attestation() -> None:
    coordinator, _adapter = coordinator_with_item()
    requester, confirmer, executor, verifier = authorities()
    plan = coordinator.plan(
        operation_kind="reset",
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_A,
        lifecycle_version=1,
        workspace_revision=1,
        profile=profile(),
        basis=basis(),
        requester=requester,
        legal_hold_active=False,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    authorization = coordinator.authorize(
        plan=plan,
        requester=requester,
        confirmer=confirmer,
        executor=executor,
        verifier=verifier,
        current_lifecycle_version=1,
        legal_hold_active=False,
        now=NOW,
    )
    purge = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=NOW,
    )
    scans = coordinator.verify(
        plan=plan,
        known_ids=frozenset(),
        known_digests=frozenset(),
        known_fragments=frozenset(),
        now=NOW,
    )
    with pytest.raises(LifecycleError) as blocked:
        coordinator.attest(
            plan=plan,
            authorization=authorization,
            receipts=purge.receipts,
            scans=scans,
            profile=profile(),
            platform_integrity_before="sha256:" + "a" * 64,
            platform_integrity_after="sha256:" + "a" * 64,
            legal_hold_check_ids=(uuid7(),),
            verifier=verifier,
            now=NOW,
            requested_assurance=AssuranceClass.PRODUCTION,
        )
    assert blocked.value.code is LifecycleErrorCode.POLICY_BLOCKED


def test_destroy_uses_fresh_destroy_authorities_and_exact_retained_copy_plan() -> None:
    adapter = InMemoryStorageAdapter(definition("synthetic.retained-copies"))
    adapter.put(WORKSPACE_A, "archive:sealed:1", b"synthetic-archive", "application/zip")
    coordinator = DestructionCoordinator(
        RegistrySnapshot(ExactVersionReference("adapters.synthetic.destroy", "0.1.0"), (adapter,))
    )
    requester = Authority("human.destroy.requester", "human", frozenset({"workspace.destroy.plan"}))
    confirmer = Authority(
        "human.destroy.confirmer", "human", frozenset({"workspace.destroy.authorize"})
    )
    executor = Authority(
        "service.destroy.executor", "service", frozenset({"workspace.destroy.execute"})
    )
    verifier = Authority("human.destroy.verifier", "human", frozenset({"workspace.destroy.verify"}))
    destroy_profile = RetentionProfile(
        ExactVersionReference("retention.synthetic.destroy", "0.1.0"),
        "development",
        frozenset({"workspace_object_store"}),
        True,
        False,
    )
    plan = coordinator.plan(
        operation_kind="destroy",
        organization_id=ORGANIZATION_ID,
        workspace_id=WORKSPACE_A,
        lifecycle_version=18,
        workspace_revision=3,
        profile=destroy_profile,
        basis=basis(),
        requester=requester,
        legal_hold_active=False,
        now=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    authorization = coordinator.authorize(
        plan=plan,
        requester=requester,
        confirmer=confirmer,
        executor=executor,
        verifier=verifier,
        current_lifecycle_version=18,
        legal_hold_active=False,
        now=NOW,
    )
    outcome = coordinator.execute(
        plan=plan,
        authorization=authorization,
        executor=executor,
        legal_hold_active=False,
        now=NOW,
    )
    scans = coordinator.verify(
        plan=plan,
        known_ids=frozenset({"archive:sealed:1"}),
        known_digests=frozenset(),
        known_fragments=frozenset(),
        now=NOW,
    )
    attestation = coordinator.attest(
        plan=plan,
        authorization=authorization,
        receipts=outcome.receipts,
        scans=scans,
        profile=destroy_profile,
        platform_integrity_before="sha256:" + "b" * 64,
        platform_integrity_after="sha256:" + "b" * 64,
        legal_hold_check_ids=(uuid7(),),
        verifier=verifier,
        now=NOW,
        requested_assurance=AssuranceClass.DEVELOPMENT_DISPOSABLE,
    )
    assert outcome.complete
    assert attestation.outcome is VerificationOutcome.VERIFIED
    assert adapter.inventory(WORKSPACE_A) == ()

    wrong_executor = Authority(
        "service.reset-only", "service", frozenset({"workspace.purge.execute"})
    )
    with pytest.raises(LifecycleError) as denied:
        coordinator.authorize(
            plan=plan,
            requester=requester,
            confirmer=confirmer,
            executor=wrong_executor,
            verifier=verifier,
            current_lifecycle_version=18,
            legal_hold_active=False,
            now=NOW,
        )
    assert denied.value.code is LifecycleErrorCode.AUTHORITY_DENIED


def test_contained_filesystem_adapter_blocks_traversal_and_symlink_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    adapter = ContainedFilesystemAdapter(root, definition("synthetic.files"))
    adapter.put(WORKSPACE_A, "safe/item.txt", b"safe")
    with pytest.raises(LifecycleError):
        adapter.put(WORKSPACE_A, "../escape.txt", b"unsafe")
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace_root = root / str(WORKSPACE_A)
    os.symlink(outside, workspace_root / "link")
    with pytest.raises(LifecycleError):
        adapter.put(WORKSPACE_A, "link/escape.txt", b"unsafe")


def test_portable_archive_verifies_hashes_readability_and_exact_inventory(
    tmp_path: Path,
) -> None:
    service = PortableArchiveService()
    package = tmp_path / "archive.zip"
    receipt = service.create(
        package_id=uuid7(),
        organization_id=ORGANIZATION_ID,
        construction_object_id=uuid7(),
        workspace_id=WORKSPACE_A,
        workspace_revision=4,
        contract_versions={"lifecycle.archive": "0.1.0"},
        policy_versions={"retention.synthetic": "0.1.0"},
        rule_set_version="0.1.0",
        entries=(ArchiveEntry("source/one.txt", "source-version:1", b"alpha", "text/plain"),),
        destination=package,
    )
    assert receipt.item_count == 1
    os.chmod(package, 0o644)
    with zipfile.ZipFile(package, "a") as changed:
        changed.writestr("unexpected.txt", b"extra")
    with pytest.raises(LifecycleError) as invalid:
        service.verify(package)
    assert invalid.value.code is LifecycleErrorCode.ARCHIVE_INVALID
