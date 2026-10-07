"""Append-only human review of workspace-scoped contract obligation candidates."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest


class ContractObligationReviewError(ValueError):
    """The candidate or review command is not safe to accept."""


class ContractObligationReviewRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def latest_decisions(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        organization_id = self._scope(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            self._set_scope(session, organization_id, workspace_id)
            return [
                dict(item)
                for item in session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (candidate_id) candidate_id,action,original_value,"
                        "decided_at FROM workspace.project_candidate_review_decisions "
                        "WHERE organization_id=:o AND workspace_id=:w "
                        "AND candidate_kind='contract_obligation' "
                        "ORDER BY candidate_id,decided_at DESC,review_decision_id DESC"
                    ),
                    {"o": organization_id, "w": workspace_id},
                ).mappings()
            ]

    def record(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        candidate: dict[str, Any],
        expected_digest: str,
        action: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if action not in {"confirmed", "rejected"}:
            raise ContractObligationReviewError("contract_obligation_review_action_invalid")
        reason = reason.strip()
        if not 3 <= len(reason) <= 1000 or not 8 <= len(idempotency_key) <= 256:
            raise ContractObligationReviewError("contract_obligation_review_command_invalid")
        if candidate.get("candidate_digest") != expected_digest:
            raise ContractObligationReviewError("contract_obligation_candidate_stale")
        organization_id = self._scope(owner_identity_id, workspace_id)
        candidate_id = UUID(str(candidate["candidate_id"]))
        decision_id = uuid5(workspace_id, f"contract-obligation-review:{idempotency_key}")
        original_value = {
            "candidate_digest": expected_digest,
            "party": candidate["party"],
            "obligation": candidate["obligation"],
            "condition": candidate["condition"],
            "clause_id": candidate["clause_id"],
        }
        decision_digest = semantic_digest(
            {
                "decision_id": decision_id,
                "candidate_id": candidate_id,
                "candidate_digest": expected_digest,
                "action": action,
                "reason": reason,
                "owner_identity_id": owner_identity_id,
            }
        )
        with Session(self._engine) as session, session.begin():
            self._set_scope(session, organization_id, workspace_id)
            allowed = session.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM application.owner_organization_grants "
                    "WHERE owner_identity_id=:owner AND organization_id=:o "
                    "AND (capability_set @> ARRAY['workspace.write']::text[] "
                    "OR capability_set @> ARRAY['support.review']::text[]))"
                ),
                {"owner": owner_identity_id, "o": organization_id},
            )
            if not allowed:
                raise ContractObligationReviewError("contract_obligation_review_forbidden")
            existing = (
                session.execute(
                    sa.text(
                        "SELECT candidate_id,decision_digest,action,decided_at FROM "
                        "workspace.project_candidate_review_decisions WHERE organization_id=:o "
                        "AND workspace_id=:w AND review_decision_id=:decision "
                        "AND decision_version=1"
                    ),
                    {"o": organization_id, "w": workspace_id, "decision": decision_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["decision_digest"] != decision_digest:
                    raise ContractObligationReviewError("contract_obligation_idempotency_conflict")
                return {
                    "candidate_id": str(candidate_id),
                    "review_state": str(existing["action"]),
                    "decided_at": existing["decided_at"],
                    "idempotent_replay": True,
                }
            row = session.execute(
                sa.text(
                    "INSERT INTO workspace.project_candidate_review_decisions "
                    "(organization_id,workspace_id,review_decision_id,decision_version,"
                    "candidate_kind,candidate_id,candidate_version,source_version_id,"
                    "source_locator_id,action,original_value,resolved_value,reason,"
                    "supersedes_decision_version,decided_by_identity_id,decision_digest) "
                    "VALUES (:o,:w,:decision,1,'contract_obligation',:candidate,1,:source,"
                    ":locator,:action,CAST(:original AS jsonb),NULL,:reason,NULL,:owner,:digest) "
                    "ON CONFLICT (organization_id,workspace_id,review_decision_id,"
                    "decision_version) "
                    "DO NOTHING "
                    "RETURNING decided_at"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "decision": decision_id,
                    "candidate": candidate_id,
                    "source": UUID(str(candidate["source_version_id"])),
                    "locator": UUID(str(candidate["source_locator_id"])),
                    "action": action,
                    "original": json.dumps(original_value, ensure_ascii=False),
                    "reason": reason,
                    "owner": owner_identity_id,
                    "digest": decision_digest,
                },
            ).one_or_none()
            if row is None:
                concurrent = (
                    session.execute(
                        sa.text(
                            "SELECT decision_digest,action,decided_at FROM "
                            "workspace.project_candidate_review_decisions WHERE organization_id=:o "
                            "AND workspace_id=:w AND review_decision_id=:decision "
                            "AND decision_version=1"
                        ),
                        {"o": organization_id, "w": workspace_id, "decision": decision_id},
                    )
                    .mappings()
                    .one()
                )
                if concurrent["decision_digest"] != decision_digest:
                    raise ContractObligationReviewError("contract_obligation_idempotency_conflict")
                return {
                    "candidate_id": str(candidate_id),
                    "review_state": str(concurrent["action"]),
                    "decided_at": concurrent["decided_at"],
                    "idempotent_replay": True,
                }
            return {
                "candidate_id": str(candidate_id),
                "review_state": action,
                "decided_at": row.decided_at,
                "idempotent_replay": False,
            }

    def _scope(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise ContractObligationReviewError("workspace_not_found")
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
