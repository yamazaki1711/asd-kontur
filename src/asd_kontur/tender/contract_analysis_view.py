"""Read-only Tender contract-analysis projection."""

# ruff: noqa: E501 -- SQL stays readable as complete clauses.
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session


class TenderContractAnalysisRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def latest(self, *, owner_identity_id: str, workspace_id: UUID) -> dict[str, Any]:
        organization_id = self._scope_for(owner_identity_id, workspace_id)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            process = (
                session.execute(
                    sa.text(
                        "SELECT tender_process_id,revision,state,updated_at FROM workspace.tender_processes WHERE organization_id=:o AND workspace_id=:w ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if process is None:
                return {
                    "status": "not_started",
                    "process": None,
                    "assessment": None,
                    "clauses": [],
                    "issues": [],
                    "deliverables": [],
                    "gaps": ["TENDER_CONTRACT_PROCESS_NOT_STARTED"],
                    "authority_boundary": "read_only_projection",
                }
            process_id = process["tender_process_id"]
            assessment = (
                session.execute(
                    sa.text(
                        "SELECT status,required_source_classes,available_source_classes,missing_source_classes,assessment_fingerprint,assessed_at FROM workspace.tender_completeness_assessments WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p ORDER BY assessed_at DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                )
                .mappings()
                .one_or_none()
            )
            clauses = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (clause_id) clause_id,clause_version,clause_key,locator_label,authority_layer,source_version_id,source_locator_id,evidence_link_id FROM workspace.tender_clause_versions WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p ORDER BY clause_id,clause_version DESC"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
            issues = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (issue_id) issue_id,issue_version,issue_kind,subject,severity,applicability,clause_id,clause_version,uncertainty_code,recommendation_text,consequence_code FROM workspace.tender_issue_versions WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p ORDER BY issue_id,issue_version DESC"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
            deliverables = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (deliverable_kind) deliverable_id,deliverable_version,deliverable_kind,state,blocker_issue_ids,uncertainty_issue_ids FROM workspace.tender_deliverable_versions WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p ORDER BY deliverable_kind,deliverable_version DESC"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
        missing = [] if assessment is None else list(assessment["missing_source_classes"])
        gaps = [] if assessment is not None else ["TENDER_CONTRACT_CORPUS_NOT_ASSESSED"]
        if "draft_contract" in missing:
            gaps.append("DRAFT_CONTRACT_SOURCE_UNAVAILABLE")
        if assessment is not None and not clauses:
            gaps.append("TENDER_CONTRACT_CLAUSES_NOT_EXTRACTED")
        if clauses and not issues:
            gaps.append("TENDER_CONTRACT_ISSUES_NOT_RECORDED")
        return {
            "status": "contract_input_unavailable"
            if "draft_contract" in missing
            else (
                "contract_clause_extraction_pending"
                if assessment is not None and not clauses
                else str(process["state"])
            ),
            "process": _row(process),
            "assessment": _row(assessment) if assessment else None,
            "clauses": [_row(x) for x in clauses],
            "issues": [_row(x) for x in issues],
            "deliverables": [_row(x) for x in deliverables],
            "gaps": gaps,
            "authority_boundary": "read_only_projection; Tender-service and qualified reviewer retain legal-writing authority",
        }

    def _scope_for(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise ValueError("workspace_not_found")
        return UUID(str(value))


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _row(value: Any) -> dict[str, Any]:
    return {key: str(item) if isinstance(item, UUID) else item for key, item in dict(value).items()}
