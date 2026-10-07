from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from asd_kontur.application_spine.reset import (
    WorkspaceResetArchiveLifecycleAdapter,
    WorkspaceResetService,
)
from asd_kontur.lifecycle import (
    AdapterHealth,
    AdapterOutcome,
    AdapterReceipt,
    DestructionCoordinator,
    LifecycleState,
    PurgeOutcome,
    StorageAdapterDefinition,
    VerificationOutcome,
)


def _adapter(tmp_path, organization_id):
    return WorkspaceResetArchiveLifecycleAdapter(
        tmp_path,
        organization_id,
        StorageAdapterDefinition(
            "workspace.reset_archives",
            "2.2.0",
            "workspace_reset_archive_store",
            "workspace",
            "workspace",
            True,
            True,
            True,
            True,
            True,
            "2.2.0",
            AdapterHealth.AVAILABLE,
        ),
    )


def test_reset_archive_is_scoped_purged_and_verified(tmp_path):
    organization_id, deleted_workspace, other_workspace = uuid4(), uuid4(), uuid4()
    deleted_dir = tmp_path / str(organization_id) / str(deleted_workspace)
    other_dir = tmp_path / str(organization_id) / str(other_workspace)
    deleted_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    (deleted_dir / "reset.zip").write_bytes(b"project A")
    (other_dir / "other.zip").write_bytes(b"project B")
    adapter = _adapter(tmp_path, organization_id)

    inventory = adapter.inventory(deleted_workspace)
    assert len(inventory) == 1
    assert inventory[0].item_id == "reset.zip"
    assert inventory[0].digest.startswith("sha256:")
    receipt = adapter.purge_item(
        workspace_id=deleted_workspace, item_id="reset.zip", operation_id=uuid4()
    )
    assert receipt.outcome == AdapterOutcome.DELETED
    assert (
        adapter.find_residue(
            workspace_id=deleted_workspace,
            known_ids=frozenset({"reset.zip"}),
            known_digests=frozenset(),
            known_fragments=frozenset(),
        )
        == ()
    )
    assert not deleted_dir.exists()
    assert (other_dir / "other.zip").read_bytes() == b"project B"


def test_reset_archive_rejects_symlink_in_inventory(tmp_path):
    organization_id, workspace_id = uuid4(), uuid4()
    directory = tmp_path / str(organization_id) / str(workspace_id)
    directory.mkdir(parents=True)
    (directory / "unsafe.zip").symlink_to(tmp_path / "elsewhere.zip")
    with pytest.raises(RuntimeError, match="workspace_reset_archive_unknown_entry"):
        _adapter(tmp_path, organization_id).inventory(workspace_id)


def test_incomplete_destroy_persists_checkpoint_before_recovery_transition(monkeypatch):
    service = object.__new__(WorkspaceResetService)
    lifecycle = SimpleNamespace(
        persist_adapter_receipts=Mock(),
        persist_recovery_checkpoint=Mock(),
    )
    service._lifecycle = lifecycle
    transition = Mock()
    monkeypatch.setattr(WorkspaceResetService, "_transition", transition)
    plan = SimpleNamespace(digest="sha256:synthetic", operation_kind="destroy")
    operation_id = uuid4()
    receipt = AdapterReceipt(
        uuid4(),
        "workspace.objects",
        "object-1",
        AdapterOutcome.INCOMPLETE,
        1,
        1,
        operation_id,
        datetime.now(UTC),
    )
    outcome = PurgeOutcome(operation_id, (receipt,), False)
    context, workspace, owner_id, correlation_id = object(), object(), "owner", uuid4()

    with pytest.raises(RuntimeError, match="workspace_destroy_reconciliation_required"):
        service._require_destroy_completion(
            coordinator=SimpleNamespace(checkpoint=DestructionCoordinator.checkpoint),
            context=context,
            plan=plan,
            outcome=outcome,
            workspace=workspace,
            owner_identity_id=owner_id,
            correlation_id=correlation_id,
            operation_id=operation_id,
        )

    lifecycle.persist_adapter_receipts.assert_called_once_with(
        context=context, plan=plan, receipts=(receipt,)
    )
    checkpoint = lifecycle.persist_recovery_checkpoint.call_args.kwargs["checkpoint"]
    assert checkpoint.failed_operation == "destroy"
    assert checkpoint.pending_items == ("workspace.objects:object-1",)
    transition.assert_called_once_with(
        workspace,
        owner_id,
        correlation_id,
        LifecycleState.RECOVERY_REQUIRED,
        operation_id,
    )


@pytest.mark.parametrize(
    ("platform_changed", "quarantined_scan", "expected_state", "expected_error"),
    [
        (False, False, LifecycleState.RECOVERY_REQUIRED, "workspace_destroy_verification_required"),
        (True, False, LifecycleState.QUARANTINED, "workspace_destroy_integrity_quarantined"),
        (False, True, LifecycleState.QUARANTINED, "workspace_destroy_integrity_quarantined"),
    ],
)
def test_incomplete_destroy_verification_never_claims_destroyed(
    monkeypatch, platform_changed, quarantined_scan, expected_state, expected_error
):
    service = object.__new__(WorkspaceResetService)
    lifecycle = SimpleNamespace(persist_recovery_checkpoint=Mock())
    service._lifecycle = lifecycle
    transition = Mock()
    monkeypatch.setattr(WorkspaceResetService, "_transition", transition)
    operation_id = uuid4()
    outcome = PurgeOutcome(operation_id, (), True)
    plan = SimpleNamespace(digest="sha256:synthetic", operation_kind="destroy")
    context, workspace, owner_id, correlation_id = object(), object(), "owner", uuid4()
    attestation = SimpleNamespace(
        outcome=(
            VerificationOutcome.QUARANTINED if quarantined_scan else VerificationOutcome.INCOMPLETE
        ),
        platform_integrity_before="sha256:before",
        platform_integrity_after=("sha256:after" if platform_changed else "sha256:before"),
    )
    scans = (
        SimpleNamespace(adapter_key="workspace.objects", outcome=VerificationOutcome.INCOMPLETE),
    )

    with pytest.raises(RuntimeError, match=expected_error):
        service._require_destroy_verification(
            context=context,
            plan=plan,
            outcome=outcome,
            scans=scans,
            attestation=attestation,
            workspace=workspace,
            owner_identity_id=owner_id,
            correlation_id=correlation_id,
            operation_id=operation_id,
        )

    transition.assert_called_once_with(
        workspace, owner_id, correlation_id, expected_state, operation_id
    )
    if platform_changed or quarantined_scan:
        lifecycle.persist_recovery_checkpoint.assert_not_called()
    else:
        checkpoint = lifecycle.persist_recovery_checkpoint.call_args.kwargs["checkpoint"]
        assert checkpoint.pending_items == ("verify:workspace.objects",)
