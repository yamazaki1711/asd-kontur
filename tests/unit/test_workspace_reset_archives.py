from __future__ import annotations

from uuid import uuid4

import pytest

from asd_kontur.application_spine.reset import WorkspaceResetArchiveLifecycleAdapter
from asd_kontur.lifecycle import AdapterHealth, AdapterOutcome, StorageAdapterDefinition


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
