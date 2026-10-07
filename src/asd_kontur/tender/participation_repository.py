"""Workspace-isolated, append-only contractor Tender assessment inputs."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7
from asd_kontur.tender.participation_decision import (
    TenderParticipationInputError,
    validate_contractor_assessment,
)


class TenderParticipationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def latest(self, *, owner_identity_id: str, workspace_id: UUID) -> dict[str, Any] | None:
        organization_id = self._scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            self._set_scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT assessment_id,assessment,assessment_digest,submitted_at "
                        "FROM workspace.tender_participation_assessments WHERE "
                        "organization_id=:o AND workspace_id=:w "
                        "ORDER BY submitted_at DESC,assessment_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row else None

    def record(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = validate_contractor_assessment(assessment)
        digest = semantic_digest(normalized)
        organization_id = self._scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            self._set_scope(session, organization_id, workspace_id)
            workspace = session.execute(
                sa.text("SELECT workspace.workspace_accepts_durable_jobs(:o,:w)"),
                {"o": organization_id, "w": workspace_id},
            ).scalar_one()
            if not workspace:
                raise TenderParticipationInputError("tender_workspace_not_active")
            current = (
                session.execute(
                    sa.text(
                        "SELECT assessment_id,assessment,assessment_digest,submitted_at "
                        "FROM workspace.tender_participation_assessments WHERE "
                        "organization_id=:o AND workspace_id=:w "
                        "ORDER BY submitted_at DESC,assessment_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if current and current["assessment_digest"] == digest:
                return dict(current)
            row = (
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.tender_participation_assessments "
                        "(organization_id,workspace_id,assessment_id,assessment,"
                        "assessment_digest,submitted_by) VALUES "
                        "(:o,:w,:id,CAST(:assessment AS jsonb),:digest,:submitted_by) "
                        "RETURNING assessment_id,assessment,assessment_digest,submitted_at"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "id": uuid7(),
                        "assessment": json.dumps(normalized, ensure_ascii=False),
                        "digest": digest,
                        "submitted_by": owner_identity_id,
                    },
                )
                .mappings()
                .one()
            )
        return dict(row)

    def _scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise TenderParticipationInputError("workspace_not_found")
        return UUID(str(value))

    @staticmethod
    def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
        session.execute(
            sa.text(
                "SELECT set_config('asd.organization_id',:o,true),"
                "set_config('asd.workspace_id',:w,true)"
            ),
            {"o": str(organization_id), "w": str(workspace_id)},
        )
