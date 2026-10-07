"""Source-bound review of Qwen-proposed contract wording for a draft package."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest


class ContractRevisionReviewError(ValueError):
    """A proposed revision or its review command is invalid or stale."""


def revision_review_candidates(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind each proposal to its current source clause and exact drafted text."""

    clauses = {
        (str(item.get("clause_id")), str(item.get("clause_version"))): item
        for item in view.get("clauses") or ()
        if isinstance(item, dict)
    }
    result: list[dict[str, Any]] = []
    for revision in view.get("revised_clauses") or ():
        if not isinstance(revision, dict):
            continue
        clause = clauses.get(
            (str(revision.get("source_clause_id")), str(revision.get("source_clause_version")))
        )
        if clause is None:
            continue
        source_version_id = str(clause.get("source_version_id") or "")
        source_locator_id = str(clause.get("source_locator_id") or "")
        revised_clause_id = str(revision.get("revised_clause_id") or "")
        try:
            UUID(source_version_id)
            UUID(source_locator_id)
            UUID(revised_clause_id)
        except ValueError:
            continue
        revised_text = str(revision.get("revised_text") or "").strip()
        if not revised_text:
            continue
        digest = semantic_digest(
            {
                "revised_clause_id": revised_clause_id,
                "source_clause_id": str(revision.get("source_clause_id")),
                "source_clause_version": str(revision.get("source_clause_version")),
                "source_version_id": source_version_id,
                "source_locator_id": source_locator_id,
                "source_text": str(clause.get("source_text") or ""),
                "replacement_source_text": str(revision.get("replacement_source_text") or ""),
                "revised_text": revised_text,
            }
        )
        result.append(
            {
                "candidate_id": revised_clause_id,
                "candidate_digest": digest,
                "source_version_id": source_version_id,
                "source_locator_id": source_locator_id,
                "source_clause_id": str(revision.get("source_clause_id")),
                "clause_key": str(clause.get("clause_key") or ""),
                "revised_text": revised_text,
                "review_state": "unreviewed",
            }
        )
    return result


def apply_revision_reviews(
    candidates: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    latest = {str(item["candidate_id"]): item for item in decisions}
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        current = dict(candidate)
        decision = latest.get(str(candidate["candidate_id"]))
        if decision is not None:
            original = decision.get("original_value") or {}
            if isinstance(original, str):
                original = json.loads(original)
            current["review_state"] = (
                str(decision["action"])
                if original.get("candidate_digest") == candidate["candidate_digest"]
                else "stale"
            )
            current["decided_at"] = decision.get("decided_at")
        result.append(current)
    return result


class ContractRevisionReviewRepository:
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
                        "AND candidate_kind='contract_revision' "
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
            raise ContractRevisionReviewError("contract_revision_review_action_invalid")
        reason = reason.strip()
        if not 3 <= len(reason) <= 1000 or not 8 <= len(idempotency_key) <= 256:
            raise ContractRevisionReviewError("contract_revision_review_command_invalid")
        if candidate.get("candidate_digest") != expected_digest:
            raise ContractRevisionReviewError("contract_revision_candidate_stale")
        organization_id = self._scope(owner_identity_id, workspace_id)
        candidate_id = UUID(str(candidate["candidate_id"]))
        decision_id = uuid5(workspace_id, f"contract-revision-review:{idempotency_key}")
        original_value = {
            "candidate_digest": expected_digest,
            "source_clause_id": candidate["source_clause_id"],
            "clause_key": candidate["clause_key"],
            "revised_text": candidate["revised_text"],
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
                    "OR capability_set @> ARRAY['tender.review']::text[]))"
                ),
                {"owner": owner_identity_id, "o": organization_id},
            )
            if not allowed:
                raise ContractRevisionReviewError("contract_revision_review_forbidden")
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
                    raise ContractRevisionReviewError("contract_revision_idempotency_conflict")
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
                    "VALUES (:o,:w,:decision,1,'contract_revision',:candidate,1,:source,"
                    ":locator,:action,CAST(:original AS jsonb),NULL,:reason,NULL,:owner,:digest) "
                    "ON CONFLICT (organization_id,workspace_id,review_decision_id,"
                    "decision_version) "
                    "DO NOTHING RETURNING decided_at"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "decision": decision_id,
                    "candidate": candidate_id,
                    "source": UUID(candidate["source_version_id"]),
                    "locator": UUID(candidate["source_locator_id"]),
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
                    raise ContractRevisionReviewError("contract_revision_idempotency_conflict")
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
            raise ContractRevisionReviewError("workspace_not_found")
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
