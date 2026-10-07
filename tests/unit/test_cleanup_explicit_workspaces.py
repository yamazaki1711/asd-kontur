"""Exact-ID cleanup guards for a dedicated qualification owner."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

_assert_inventory = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "tools/cleanup_explicit_workspaces.py")
)["_assert_inventory"]


class _Repository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def list_workspaces(self, *, owner_identity_id: str) -> list[SimpleNamespace]:
        assert owner_identity_id == "test-owner"
        return self.rows


_TARGET = "11111111-1111-4111-8111-111111111111"
_OTHER = "22222222-2222-4222-8222-222222222222"
_ORGANIZATION = "33333333-3333-4333-8333-333333333333"


def _manifest() -> dict[str, object]:
    return {
        "owner_identity_id": "test-owner",
        "organization_id": _ORGANIZATION,
        "unwanted_workspace_ids": [_TARGET],
        "target_display_names": {_TARGET: "Changed Contract Portability Control"},
        "expected_authorized_workspace_count_before": 1,
    }


def _row(identity: str) -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id=UUID(identity),
        organization_id=UUID(_ORGANIZATION),
        display_name="Changed Contract Portability Control",
        lifecycle_state="ACTIVE",
    )


def test_exact_control_owner_can_be_cleaned_to_zero_authorized_workspaces() -> None:
    repository = _Repository([_row(_TARGET)])
    assert _assert_inventory(repository, _manifest(), allow_partial=False) == (_TARGET,)
    repository.rows = []
    assert _assert_inventory(repository, _manifest(), allow_partial=True) == ()


def test_unlisted_workspace_blocks_control_owner_cleanup() -> None:
    repository = _Repository([_row(_TARGET), _row(_OTHER)])
    with pytest.raises(RuntimeError, match="cleanup_authorized_inventory_conflict"):
        _assert_inventory(repository, _manifest(), allow_partial=False)


def test_changed_target_name_blocks_control_owner_cleanup() -> None:
    repository = _Repository([_row(_TARGET)])
    manifest = _manifest()
    manifest["target_display_names"] = {_TARGET: "Different Control"}
    with pytest.raises(RuntimeError, match="cleanup_target_metadata_mismatch"):
        _assert_inventory(repository, manifest, allow_partial=False)
