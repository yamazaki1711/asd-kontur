"""Append-only persistence for pilot mode results, reviews and exports."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest

from .builder import PILOT_NAMESPACE
from .models import PilotExportFormat, PilotExportKind, PilotMode, PilotReviewAction


class PilotResultError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PilotResultRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def put_result(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        result: dict[str, Any],
        owner_identity_id: str,
    ) -> dict[str, Any]:
        fingerprint = str(result["fingerprint"])
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            existing = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.pilot_mode_result_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND result_fingerprint=:fingerprint"
                    ),
                    {"o": organization_id, "w": workspace_id, "fingerprint": fingerprint},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _result_row(existing)
            result_id = UUID(str(result["result_id"]))
            version = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(version),0)+1 FROM workspace.pilot_mode_result_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND result_id=:result"
                    ),
                    {"o": organization_id, "w": workspace_id, "result": result_id},
                )
                or 1
            )
            value = {**result, "version": version}
            session.execute(
                sa.text(
                    "INSERT INTO workspace.pilot_mode_result_versions "
                    "(organization_id,workspace_id,result_id,version,mode,project_definition_id,"
                    "project_definition_version,matrix_id,matrix_version,result_payload,source_manifest,"
                    "unresolved_questions,status,result_fingerprint,formed_by_identity_id) VALUES "
                    "(:o,:w,:result,:version,:mode,:project,:project_version,:matrix,:matrix_version,"
                    "CAST(:payload AS jsonb),CAST(:sources AS jsonb),CAST(:unresolved AS jsonb),:status,"
                    ":fingerprint,:owner)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "result": result_id,
                    "version": version,
                    "mode": str(result["mode"]),
                    "project": _uuid_or_none(result.get("project_definition_id")),
                    "project_version": int(result.get("project_definition_version") or 0) or None,
                    "matrix": _uuid_or_none(result.get("matrix_id")),
                    "matrix_version": int(result.get("matrix_version") or 0) or None,
                    "payload": _json(value),
                    "sources": _json(result.get("source_manifest") or []),
                    "unresolved": _json(result.get("unresolved_questions") or []),
                    "status": str(result["status"]),
                    "fingerprint": fingerprint,
                    "owner": owner_identity_id,
                },
            )
        return value

    def latest_result(
        self, *, organization_id: UUID, workspace_id: UUID, mode: PilotMode
    ) -> dict[str, Any] | None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.pilot_mode_result_versions WHERE organization_id=:o "
                        "AND workspace_id=:w AND mode=:mode ORDER BY formed_at DESC,result_id,version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "mode": mode.value},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            result = _result_row(row)
            decisions = session.execute(
                sa.text(
                    "SELECT DISTINCT ON (item_id) * FROM workspace.pilot_result_item_decisions "
                    "WHERE organization_id=:o AND workspace_id=:w AND result_id=:result AND "
                    "result_version=:version ORDER BY item_id,decision_version DESC"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "result": row["result_id"],
                    "version": row["version"],
                },
            ).mappings()
            exports = session.execute(
                sa.text(
                    "SELECT DISTINCT ON (export_id) export_id,version,export_kind,output_format,"
                    "media_type,size_bytes,content_digest,export_fingerprint,created_at "
                    "FROM workspace.pilot_export_versions "
                    "WHERE organization_id=:o AND workspace_id=:w AND result_id=:result AND "
                    "result_version=:version ORDER BY export_id,version DESC"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "result": row["result_id"],
                    "version": row["version"],
                },
            ).mappings()
        return _apply_decisions(
            result, [dict(item) for item in decisions], [dict(item) for item in exports]
        )

    def latest_results(
        self, *, organization_id: UUID, workspace_id: UUID
    ) -> tuple[dict[str, Any], ...]:
        results = []
        for mode in PilotMode:
            value = self.latest_result(
                organization_id=organization_id, workspace_id=workspace_id, mode=mode
            )
            if value is not None:
                results.append(value)
        return tuple(results)

    def review_item(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        mode: PilotMode,
        item_id: UUID,
        action: PilotReviewAction,
        resolved_fields: dict[str, Any] | None,
        comment: str,
        owner_identity_id: str,
    ) -> dict[str, Any]:
        result = self.latest_result(
            organization_id=organization_id, workspace_id=workspace_id, mode=mode
        )
        if result is None:
            raise PilotResultError("pilot_result_not_found")
        item = next(
            (value for value in result["items"] if str(value["item_id"]) == str(item_id)), None
        )
        if item is None:
            raise PilotResultError("pilot_result_item_not_found")
        if action in {PilotReviewAction.CORRECT, PilotReviewAction.STATUS} and not resolved_fields:
            raise PilotResultError("pilot_result_correction_required")
        if action not in {PilotReviewAction.CORRECT, PilotReviewAction.STATUS} and resolved_fields:
            raise PilotResultError("pilot_result_unexpected_correction")
        if action is PilotReviewAction.STATUS and "status" not in (resolved_fields or {}):
            raise PilotResultError("pilot_result_status_required")
        result_id = UUID(str(result["result_id"]))
        result_version = int(result["version"])
        decision_id = uuid5(PILOT_NAMESPACE, f"pilot-review:{result_id}:{result_version}:{item_id}")
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            prior = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(decision_version),0) FROM workspace.pilot_result_item_decisions "
                        "WHERE organization_id=:o AND workspace_id=:w AND decision_id=:decision"
                    ),
                    {"o": organization_id, "w": workspace_id, "decision": decision_id},
                )
                or 0
            )
            version = prior + 1
            digest = semantic_digest(
                {
                    "decision_id": decision_id,
                    "decision_version": version,
                    "result_id": result_id,
                    "result_version": result_version,
                    "item_id": item_id,
                    "item_version": int(item["version"]),
                    "action": action.value,
                    "original": item,
                    "resolved_fields": resolved_fields,
                    "comment": comment.strip(),
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.pilot_result_item_decisions "
                    "(organization_id,workspace_id,decision_id,decision_version,result_id,result_version,"
                    "item_id,item_version,action,original_payload,resolved_fields,comment,"
                    "supersedes_decision_version,decided_by_identity_id,decision_digest) VALUES "
                    "(:o,:w,:decision,:version,:result,:result_version,:item,:item_version,:action,"
                    "CAST(:original AS jsonb),CAST(:resolved AS jsonb),:comment,:supersedes,:owner,:digest)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "decision": decision_id,
                    "version": version,
                    "result": result_id,
                    "result_version": result_version,
                    "item": item_id,
                    "item_version": int(item["version"]),
                    "action": action.value,
                    "original": _json(item),
                    "resolved": _json(resolved_fields) if resolved_fields else None,
                    "comment": comment.strip(),
                    "supersedes": prior or None,
                    "owner": owner_identity_id,
                    "digest": digest,
                },
            )
        updated = self.latest_result(
            organization_id=organization_id, workspace_id=workspace_id, mode=mode
        )
        if updated is None:
            raise PilotResultError("pilot_result_not_found")
        return updated

    def record_export(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        result: dict[str, Any],
        kind: PilotExportKind,
        output_format: PilotExportFormat,
        object_key: str,
        media_type: str,
        size_bytes: int,
        content_digest: str,
        owner_identity_id: str,
    ) -> dict[str, Any]:
        result_id = UUID(str(result["result_id"]))
        result_version = int(result["version"])
        export_id = uuid5(
            PILOT_NAMESPACE,
            f"pilot-export:{result_id}:{result_version}:{kind.value}:{output_format.value}",
        )
        fingerprint = semantic_digest(
            {
                "export_id": export_id,
                "result_fingerprint": result["fingerprint"],
                "kind": kind.value,
                "format": output_format.value,
                "content_digest": content_digest,
                "source_manifest": result["source_manifest"],
                "unresolved_questions": result["unresolved_questions"],
            }
        )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            existing = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.pilot_export_versions WHERE organization_id=:o AND "
                        "workspace_id=:w AND export_id=:export AND export_fingerprint=:fingerprint"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "export": export_id,
                        "fingerprint": fingerprint,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _export_row(existing)
            version = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(version),0)+1 FROM workspace.pilot_export_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND export_id=:export"
                    ),
                    {"o": organization_id, "w": workspace_id, "export": export_id},
                )
                or 1
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.pilot_export_versions "
                    "(organization_id,workspace_id,export_id,version,result_id,result_version,export_kind,"
                    "output_format,object_key,media_type,size_bytes,content_digest,source_manifest,"
                    "unresolved_questions,export_fingerprint,created_by_identity_id) VALUES "
                    "(:o,:w,:export,:version,:result,:result_version,:kind,:format,:object_key,:media_type,"
                    ":size,:digest,CAST(:sources AS jsonb),CAST(:unresolved AS jsonb),:fingerprint,:owner)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "export": export_id,
                    "version": version,
                    "result": result_id,
                    "result_version": result_version,
                    "kind": kind.value,
                    "format": output_format.value,
                    "object_key": object_key,
                    "media_type": media_type,
                    "size": size_bytes,
                    "digest": content_digest,
                    "sources": _json(result["source_manifest"]),
                    "unresolved": _json(result["unresolved_questions"]),
                    "fingerprint": fingerprint,
                    "owner": owner_identity_id,
                },
            )
        return {
            "export_id": str(export_id),
            "version": version,
            "export_kind": kind.value,
            "output_format": output_format.value,
            "media_type": media_type,
            "size_bytes": size_bytes,
            "content_digest": content_digest,
            "export_fingerprint": fingerprint,
        }

    def export_object(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        export_id: UUID,
    ) -> dict[str, Any]:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.pilot_export_versions WHERE organization_id=:o AND "
                        "workspace_id=:w AND export_id=:export ORDER BY version DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "export": export_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise PilotResultError("pilot_export_not_found")
        return dict(row)

    def finalized_support_objects(
        self, *, organization_id: UUID, workspace_id: UUID
    ) -> tuple[dict[str, Any], ...]:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT DISTINCT ON (f.finalized_document_id) f.finalized_document_id,f.version,"
                    "c.object_reference AS object_key,c.bytes_digest AS content_digest,"
                    "c.format AS output_format FROM workspace.support_finalized_document_versions f "
                    "JOIN workspace.support_generated_document_candidates c "
                    "ON c.organization_id=f.organization_id AND c.workspace_id=f.workspace_id "
                    "AND c.generated_candidate_id=f.generated_candidate_id "
                    "WHERE f.organization_id=:o AND f.workspace_id=:w "
                    "ORDER BY f.finalized_document_id,f.version DESC"
                ),
                {"o": organization_id, "w": workspace_id},
            ).mappings()
        return tuple(dict(row) for row in rows)


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _result_row(row: sa.RowMapping) -> dict[str, Any]:
    value = dict(row["result_payload"])
    value["result_id"] = str(row["result_id"])
    value["version"] = int(row["version"])
    value["fingerprint"] = str(row["result_fingerprint"])
    value["formed_at"] = row["formed_at"].isoformat()
    return value


def _apply_decisions(
    result: dict[str, Any], decisions: list[dict[str, Any]], exports: list[dict[str, Any]]
) -> dict[str, Any]:
    by_item = {str(item["item_id"]): item for item in decisions}
    items = []
    for original in result.get("items") or []:
        item = dict(original)
        decision = by_item.get(str(item["item_id"]))
        if decision:
            item["review"] = {
                "action": decision["action"],
                "comment": decision["comment"],
                "decision_version": int(decision["decision_version"]),
                "decided_at": decision["decided_at"].isoformat(),
            }
            fields = dict(decision["resolved_fields"] or {})
            if fields:
                for key in (
                    "description",
                    "status",
                    "recommended_action",
                    "responsible",
                    "resolution_status",
                ):
                    if key in fields:
                        item[f"effective_{key}"] = fields[key]
            if decision["action"] == PilotReviewAction.ACCEPT.value:
                item["effective_resolution_status"] = "accepted"
            elif decision["action"] == PilotReviewAction.EXCLUDE.value:
                item["effective_resolution_status"] = "excluded"
        items.append(item)
    result["items"] = items
    open_items = [
        item
        for item in items
        if str(item.get("effective_resolution_status") or item.get("resolution_status"))
        not in {"accepted", "excluded", "resolved"}
    ]
    result["unresolved_questions"] = sorted(
        {str(item.get("effective_status") or item.get("status")) for item in open_items}
    )
    result["status"] = "draft_with_open_questions" if open_items else "reviewed_draft"
    result["summary"] = {**dict(result.get("summary") or {}), "open_questions": len(open_items)}
    result["exports"] = [_jsonable_export(item) for item in exports]
    result["reviewed_item_count"] = len(decisions)
    return result


def _jsonable_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "export_id": str(row["export_id"]),
        "version": int(row["version"]),
        "export_kind": str(row["export_kind"]),
        "output_format": str(row["output_format"]),
        "media_type": str(row["media_type"]),
        "size_bytes": int(row["size_bytes"]),
        "content_digest": str(row["content_digest"]),
        "export_fingerprint": str(row["export_fingerprint"]),
        "created_at": row["created_at"].isoformat(),
    }


def _export_row(row: sa.RowMapping) -> dict[str, Any]:
    return _jsonable_export(dict(row))


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
