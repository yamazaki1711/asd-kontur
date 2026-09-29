from __future__ import annotations

from unittest.mock import Mock
from uuid import UUID

from asd_kontur.application_spine.postgres import SpinePostgresRepository

ORGANIZATION_ID = UUID("018f5c3e-7b00-7000-8000-000000000701")
WORKSPACE_ID = UUID("018f5c3e-7b00-7000-8000-000000000702")


def _session_with_state(state: tuple[str, bool] | None) -> Mock:
    session = Mock()
    session.execute.return_value.one_or_none.return_value = state
    return session


def test_active_unfenced_workspace_accepts_new_jobs() -> None:
    session = _session_with_state(("ACTIVE", False))

    assert SpinePostgresRepository._workspace_accepts_jobs(
        session, organization_id=ORGANIZATION_ID, workspace_id=WORKSPACE_ID
    )


def test_lifecycle_fence_rejects_successors_and_refills() -> None:
    for state in (("ACTIVE", True), ("RESET_PLANNING", True), ("PURGING", True), None):
        session = _session_with_state(state)
        assert not SpinePostgresRepository._workspace_accepts_jobs(
            session, organization_id=ORGANIZATION_ID, workspace_id=WORKSPACE_ID
        )
