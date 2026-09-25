"""Durable, evidence-bound snapshots of Restoration recovery assessments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid


class RestorationRecoveryError(RuntimeError):
    """A typed boundary error for the Restoration assessment surface."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RestorationRecoveryRepository:
    """Append-only recovery-plan snapshots scoped through an application owner.

    A snapshot deliberately records an assessment rather than changing any
    source document or package membership.  It lets a user return to the exact
    evidence, recovery order, and missing-input boundary that a plan used.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def capture(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        payload = _canonical_plan(plan)
        plan_fingerprint = semantic_digest(payload)
        basis_fingerprint = semantic_digest(dict(payload.get("basis") or {}))
        process_id = deterministic_uuid(f"restoration-recovery-process:{workspace_id}")
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            latest = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.restoration_recovery_plan_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND recovery_process_id=:p "
                        "ORDER BY version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                )
                .mappings()
                .one_or_none()
            )
            if latest is not None and str(latest["plan_fingerprint"]) == plan_fingerprint:
                return {"duplicate": True, **_snapshot(cast(Mapping[str, Any], latest))}
            version = 1 if latest is None else int(latest["version"]) + 1
            state = str(payload.get("status", "blocked"))
            if state not in {"partial", "blocked"}:
                raise RestorationRecoveryError("recovery_plan_status_invalid")
            session.execute(
                sa.text(
                    "INSERT INTO workspace.restoration_recovery_plan_versions "
                    "(organization_id,workspace_id,recovery_process_id,version,state,"
                    "basis_fingerprint,plan_fingerprint,plan,recorded_by_identity_id,recorded_at) "
                    "VALUES (:o,:w,:p,:v,:state,:basis,:plan_fingerprint,"
                    "CAST(:plan AS jsonb),:owner,:at)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "p": process_id,
                    "v": version,
                    "state": state,
                    "basis": basis_fingerprint,
                    "plan_fingerprint": plan_fingerprint,
                    "plan": json.dumps(
                        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ),
                    "owner": owner_identity_id,
                    "at": now,
                },
            )
        return {
            "duplicate": False,
            "recovery_process_id": str(process_id),
            "version": version,
            "state": state,
            "basis_fingerprint": basis_fingerprint,
            "plan_fingerprint": plan_fingerprint,
            "recorded_at": now,
        }

    def latest(self, *, owner_identity_id: str, workspace_id: UUID) -> dict[str, Any] | None:
        organization_id = self._resolve_scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.restoration_recovery_plan_versions "
                        "WHERE organization_id=:o AND workspace_id=:w "
                        "ORDER BY recorded_at DESC,version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _snapshot(cast(Mapping[str, Any], row))

    def _resolve_scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise RestorationRecoveryError("workspace_not_found")
        return UUID(str(value))


def _canonical_plan(plan: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(json.dumps(plan, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        raise RestorationRecoveryError("recovery_plan_not_serializable") from exc
    if value.get("plan_kind") != "id_package_recovery_plan":
        raise RestorationRecoveryError("recovery_plan_kind_invalid")
    return cast(dict[str, Any], value)


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "recovery_process_id": str(row["recovery_process_id"]),
        "version": int(row["version"]),
        "state": str(row["state"]),
        "basis_fingerprint": str(row["basis_fingerprint"]),
        "plan_fingerprint": str(row["plan_fingerprint"]),
        "recorded_at": row["recorded_at"],
    }
