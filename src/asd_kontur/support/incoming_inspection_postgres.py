"""Owner-scoped, immutable incoming-inspection preflights."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7

from .incoming_inspection import (
    evaluate_incoming_inspection,
    render_incoming_inspection_register,
)


class IncomingInspectionError(RuntimeError):
    pass


class IncomingInspectionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _scope(self, session: Session, owner_identity_id: str, workspace_id: UUID) -> UUID:
        organization_id = session.scalar(
            sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
            {"owner": owner_identity_id, "workspace": workspace_id},
        )
        if organization_id is None:
            raise IncomingInspectionError("workspace_not_found")
        session.execute(
            sa.select(
                sa.func.set_config("asd.organization_id", str(organization_id), True),
                sa.func.set_config("asd.workspace_id", str(workspace_id), True),
            )
        ).one()
        return UUID(str(organization_id))

    def submit(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        material_name: str,
        batch_reference: str,
        checks: Sequence[Mapping[str, Any]],
        idempotency_key: str,
    ) -> dict[str, Any]:
        material_name = " ".join(material_name.split())
        batch_reference = " ".join(batch_reference.split())
        if not 2 <= len(material_name) <= 200 or not 1 <= len(batch_reference) <= 200:
            raise IncomingInspectionError("incoming_inspection_identity_invalid")
        if not 8 <= len(idempotency_key) <= 200:
            raise IncomingInspectionError("incoming_inspection_idempotency_key_invalid")
        try:
            result = evaluate_incoming_inspection(checks)
        except ValueError as exc:
            raise IncomingInspectionError(str(exc)) from exc
        inspection = {
            "material_name": material_name,
            "batch_reference": batch_reference,
            "checks": result["checks"],
        }
        digest = semantic_digest(inspection)
        with Session(self._engine) as session, session.begin():
            organization_id = self._scope(session, owner_identity_id, workspace_id)
            existing = (
                session.execute(
                    sa.text(
                        "SELECT preflight_id,payload_digest,result,submitted_at FROM "
                        "workspace.support_incoming_inspection_preflights WHERE "
                        "organization_id=:o AND workspace_id=:w AND idempotency_key=:k"
                    ),
                    {"o": organization_id, "w": workspace_id, "k": idempotency_key},
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["payload_digest"] != digest:
                    raise IncomingInspectionError("incoming_inspection_idempotency_conflict")
                return self._view(existing, inspection)
            preflight_id = uuid7()
            try:
                row = (
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.support_incoming_inspection_preflights "
                            "(organization_id,workspace_id,preflight_id,idempotency_key,material_name,"
                            "batch_reference,inspection,result,payload_digest,submitted_by) VALUES "
                            "(:o,:w,:id,:k,:material,:batch,CAST(:inspection AS jsonb),"
                            "CAST(:result AS jsonb),:digest,:owner) ON CONFLICT "
                            "(organization_id,workspace_id,idempotency_key) DO NOTHING "
                            "RETURNING preflight_id,payload_digest,result,submitted_at"
                        ),
                        {
                            "o": organization_id,
                            "w": workspace_id,
                            "id": preflight_id,
                            "k": idempotency_key,
                            "material": material_name,
                            "batch": batch_reference,
                            "inspection": json.dumps(inspection, ensure_ascii=False),
                            "result": json.dumps(result, ensure_ascii=False),
                            "digest": digest,
                            "owner": owner_identity_id,
                        },
                    )
                    .mappings()
                    .first()
                )
            except sa.exc.DBAPIError as exc:
                if "support_workspace_not_active" in str(exc.orig):
                    raise IncomingInspectionError("support_workspace_not_active") from exc
                raise
            if row is None:
                row = (
                    session.execute(
                        sa.text(
                            "SELECT preflight_id,payload_digest,result,submitted_at FROM "
                            "workspace.support_incoming_inspection_preflights WHERE "
                            "organization_id=:o AND workspace_id=:w AND idempotency_key=:k"
                        ),
                        {"o": organization_id, "w": workspace_id, "k": idempotency_key},
                    )
                    .mappings()
                    .one()
                )
                if row["payload_digest"] != digest:
                    raise IncomingInspectionError("incoming_inspection_idempotency_conflict")
            return self._view(row, inspection)

    @staticmethod
    def _view(row: Mapping[str, Any], inspection: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "preflight_id": row["preflight_id"],
            "material_name": inspection["material_name"],
            "batch_reference": inspection["batch_reference"],
            "payload_digest": row["payload_digest"],
            "result": row["result"],
            "submitted_at": row["submitted_at"],
        }

    def list(
        self, *, owner_identity_id: str, workspace_id: UUID, limit: int | None = 100
    ) -> list[dict[str, Any]]:
        if limit is not None and not 1 <= limit <= 100:
            raise IncomingInspectionError("incoming_inspection_list_limit_invalid")
        with Session(self._engine) as session, session.begin():
            organization_id = self._scope(session, owner_identity_id, workspace_id)
            rows = (
                session.execute(
                    sa.text(
                        "SELECT preflight_id,material_name,batch_reference,payload_digest,"
                        "result,submitted_at FROM workspace.support_incoming_inspection_preflights "
                        "WHERE organization_id=:o AND workspace_id=:w "
                        "ORDER BY submitted_at DESC,preflight_id DESC "
                        + ("LIMIT :limit" if limit is not None else "")
                    ),
                    {"o": organization_id, "w": workspace_id, "limit": limit},
                )
                .mappings()
                .all()
            )
            return [self._view(row, row) for row in rows]

    def export_register(self, *, owner_identity_id: str, workspace_id: UUID) -> bytes:
        records = self.list(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id, limit=None
        )
        return render_incoming_inspection_register(records)
