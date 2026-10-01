"""Read-only Tender contract-analysis projection."""

# ruff: noqa: E501 -- SQL stays readable as complete clauses.
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.document_understanding.qwen_semantic import (
    QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
)


class TenderContractAnalysisError(RuntimeError):
    """A scoped Tender projection could not be read."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
                return self._candidate_projection(
                    session, organization_id=organization_id, workspace_id=workspace_id
                )
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
            protocols = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (protocol_id) protocol_id,protocol_version,state,"
                        "source_manifest_digest,evidence_manifest_digest,rule_set_version_id,"
                        "blocker_issue_ids,uncertainty_issue_ids,recorded_at "
                        "FROM workspace.tender_disagreement_protocol_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p "
                        "ORDER BY protocol_id,protocol_version DESC"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
            disagreement_items = list(
                session.execute(
                    sa.text(
                        "WITH latest_protocols AS ("
                        "SELECT DISTINCT ON (protocol_id) protocol_id,protocol_version "
                        "FROM workspace.tender_disagreement_protocol_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p "
                        "ORDER BY protocol_id,protocol_version DESC) "
                        "SELECT i.protocol_id,i.protocol_version,i.item_id,i.ordinal,i.clause_id,"
                        "i.clause_version,i.issue_id,i.issue_version,i.proposed_clause_text,"
                        "i.consequence_code,i.rule_trace_id,i.evidence_link_ids,"
                        "i.uncertainty_issue_ids,i.finding_decision_id "
                        "FROM workspace.tender_disagreement_items i JOIN latest_protocols p "
                        "ON p.protocol_id=i.protocol_id AND p.protocol_version=i.protocol_version "
                        "WHERE i.organization_id=:o AND i.workspace_id=:w "
                        "ORDER BY i.protocol_id,i.ordinal"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
            revised_contracts = list(
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (revised_contract_id) revised_contract_id,"
                        "revised_contract_version,protocol_id,protocol_version,"
                        "source_contract_version_id,state,source_manifest_digest,recorded_at "
                        "FROM workspace.tender_revised_contract_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p "
                        "ORDER BY revised_contract_id,revised_contract_version DESC"
                    ),
                    {"o": organization_id, "w": workspace_id, "p": process_id},
                ).mappings()
            )
            revised_clauses = list(
                session.execute(
                    sa.text(
                        "WITH latest_contracts AS ("
                        "SELECT DISTINCT ON (revised_contract_id) revised_contract_id,"
                        "revised_contract_version FROM workspace.tender_revised_contract_versions "
                        "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:p "
                        "ORDER BY revised_contract_id,revised_contract_version DESC) "
                        "SELECT c.revised_contract_id,c.revised_contract_version,c.revised_clause_id,"
                        "c.ordinal,c.source_clause_id,c.source_clause_version,c.issue_id,"
                        "c.issue_version,c.disagreement_item_id,c.decision_id,c.revised_text,"
                        "c.revised_text_digest FROM workspace.tender_revised_clause_versions c "
                        "JOIN latest_contracts r ON r.revised_contract_id=c.revised_contract_id "
                        "AND r.revised_contract_version=c.revised_contract_version "
                        "WHERE c.organization_id=:o AND c.workspace_id=:w "
                        "ORDER BY c.revised_contract_id,c.ordinal"
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
        deliverable_kinds = {str(item["deliverable_kind"]) for item in deliverables}
        if "disagreement_protocol" in deliverable_kinds and not disagreement_items:
            gaps.append("TENDER_DISAGREEMENT_ITEMS_UNAVAILABLE")
        if "revised_contract" in deliverable_kinds and not revised_clauses:
            gaps.append("TENDER_REVISED_CLAUSES_UNAVAILABLE")
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
            "protocols": [_row(x) for x in protocols],
            "disagreement_items": [_row(x) for x in disagreement_items],
            "revised_contracts": [_row(x) for x in revised_contracts],
            "revised_clauses": [_row(x) for x in revised_clauses],
            "deliverables": [_row(x) for x in deliverables],
            "gaps": gaps,
            "authority_boundary": "read_only_projection; Tender-service and qualified reviewer retain legal-writing authority",
        }

    @staticmethod
    def _candidate_projection(
        session: Session, *, organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        contract_sources = list(
            session.execute(
                sa.text(
                    "SELECT DISTINCT v.source_version_id,v.safe_display_name FROM "
                    "workspace.document_versions v JOIN workspace.document_role_decisions role ON "
                    "role.organization_id=v.organization_id AND role.workspace_id=v.workspace_id AND "
                    "role.document_id=v.document_id AND role.document_version=v.version WHERE "
                    "v.organization_id=:o AND v.workspace_id=:w AND "
                    "role.validator_version=:role_profile AND 'contract'=ANY(role.selected_roles) "
                    "AND EXISTS (SELECT 1 FROM workspace.document_version_activation_decisions active "
                    "WHERE active.organization_id=v.organization_id AND active.workspace_id=v.workspace_id "
                    "AND active.document_id=v.document_id AND active.selected_document_version=v.version "
                    "AND NOT EXISTS (SELECT 1 FROM workspace.document_version_activation_decisions newer "
                    "WHERE newer.organization_id=active.organization_id AND newer.workspace_id=active.workspace_id "
                    "AND newer.document_id=active.document_id AND newer.decision_version>active.decision_version)) "
                    "ORDER BY v.source_version_id"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "role_profile": QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                },
            ).mappings()
        )
        if not contract_sources:
            return _empty_candidate_projection(
                status="contract_input_unavailable",
                gaps=["DRAFT_CONTRACT_SOURCE_UNAVAILABLE"],
            )
        jobs = list(
            session.execute(
                sa.text(
                    "SELECT job_id,state,typed_failure_code,created_at,completed_at FROM "
                    "workspace.durable_jobs WHERE organization_id=:o AND workspace_id=:w "
                    "AND job_kind='CONTRACT_ANALYSIS' ORDER BY created_at,job_id"
                ),
                {"o": organization_id, "w": workspace_id},
            ).mappings()
        )
        results = list(
            session.execute(
                sa.text(
                    "SELECT result.job_id,result.source_version_id,result.batch_ordinal,"
                    "result.result_manifest,result.recorded_at FROM workspace.contract_analysis_results result "
                    "JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id AND "
                    "job.workspace_id=result.workspace_id AND job.job_id=result.job_id WHERE "
                    "result.organization_id=:o AND result.workspace_id=:w AND job.state='succeeded' "
                    "ORDER BY result.source_version_id,result.batch_ordinal,result.recorded_at"
                ),
                {"o": organization_id, "w": workspace_id},
            ).mappings()
        )
        clauses: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        disagreement_items: list[dict[str, Any]] = []
        revised_clauses: list[dict[str, Any]] = []
        for result in results:
            manifest = result["result_manifest"]
            if not isinstance(manifest, dict):
                continue
            clause_ids: dict[str, str] = {}
            for clause in manifest.get("clauses") or ():
                if not isinstance(clause, dict):
                    continue
                clause_ref = str(clause.get("clause_ref") or "")
                clause_id = str(
                    uuid5(
                        workspace_id,
                        f"contract-clause:{result['source_version_id']}:{clause_ref}:"
                        f"{clause.get('source_text')}",
                    )
                )
                clause_ids[clause_ref] = clause_id
                locator_ids = [str(value) for value in clause.get("source_locator_ids") or ()]
                clauses.append(
                    {
                        "clause_id": clause_id,
                        "clause_version": 1,
                        "clause_key": clause_ref,
                        "locator_label": str(clause.get("section") or ""),
                        "authority_layer": "qwen_contract_candidate",
                        "source_version_id": str(result["source_version_id"]),
                        "source_locator_id": locator_ids[0] if locator_ids else None,
                        "source_locator_ids": locator_ids,
                        "source_text": clause.get("source_text"),
                        "category": clause.get("category"),
                        "customer_obligation": clause.get("customer_obligation"),
                        "contractor_obligation": clause.get("contractor_obligation"),
                        "condition": clause.get("condition"),
                    }
                )
            for risk in manifest.get("risks") or ():
                if not isinstance(risk, dict):
                    continue
                clause_ref = str(risk.get("clause_ref") or "")
                risk_clause_id = clause_ids.get(clause_ref)
                if risk_clause_id is None:
                    continue
                issue_id = str(
                    uuid5(
                        workspace_id,
                        f"contract-risk:{risk_clause_id}:{risk.get('kind')}:{risk.get('description')}",
                    )
                )
                issue = {
                    "issue_id": issue_id,
                    "issue_version": 1,
                    "issue_kind": "contract_risk",
                    "subject": risk.get("kind"),
                    "severity": risk.get("severity"),
                    "applicability": "candidate",
                    "clause_id": risk_clause_id,
                    "clause_version": 1,
                    "uncertainty_code": risk.get("uncertainty"),
                    "description": risk.get("description"),
                    "recommendation_text": risk.get("recommended_action"),
                    "consequence_code": risk.get("practical_consequence"),
                    "confidence": risk.get("confidence"),
                    "authority": risk.get("authority"),
                }
                issues.append(issue)
                proposed = risk.get("proposed_contractor_wording")
                if risk.get("disagreement_required") is True and proposed:
                    item_id = str(uuid5(workspace_id, f"contract-disagreement:{issue_id}"))
                    disagreement_items.append(
                        {
                            "item_id": item_id,
                            "ordinal": len(disagreement_items) + 1,
                            "clause_id": risk_clause_id,
                            "clause_version": 1,
                            "issue_id": issue_id,
                            "issue_version": 1,
                            "proposed_clause_text": proposed,
                            "consequence_code": risk.get("practical_consequence"),
                            "uncertainty_issue_ids": [],
                        }
                    )
                    revised_clauses.append(
                        {
                            "revised_clause_id": str(
                                uuid5(workspace_id, f"contract-revised-clause:{item_id}")
                            ),
                            "ordinal": len(revised_clauses) + 1,
                            "source_clause_id": risk_clause_id,
                            "source_clause_version": 1,
                            "issue_id": issue_id,
                            "issue_version": 1,
                            "disagreement_item_id": item_id,
                            "revised_text": proposed,
                        }
                    )
        active = any(str(job["state"]) in {"queued", "leased", "running"} for job in jobs)
        failed = [job for job in jobs if str(job["state"]) in {"failed", "reconciliation_required"}]
        status = "analyzing" if active else "drafted" if results else "analysis_pending"
        gaps: list[str] = []
        if active:
            gaps.append("CONTRACT_ANALYSIS_IN_PROGRESS")
        if failed:
            gaps.append("CONTRACT_ANALYSIS_BATCH_FAILURES")
        if results and not issues:
            gaps.append("CONTRACT_RISKS_NOT_IDENTIFIED_IN_COMPLETED_BATCHES")
        return {
            "status": status,
            "process": {
                "tender_process_id": f"draft:{workspace_id}",
                "revision": len(results),
                "state": status,
                "updated_at": max((result["recorded_at"] for result in results), default=None),
            },
            "assessment": {
                "status": "partial" if active or failed else "complete",
                "required_source_classes": ["draft_contract"],
                "available_source_classes": ["draft_contract"],
                "missing_source_classes": [],
                "source_names": [str(source["safe_display_name"]) for source in contract_sources],
            },
            "clauses": clauses,
            "issues": issues,
            "protocols": [],
            "disagreement_items": disagreement_items,
            "revised_contracts": [],
            "revised_clauses": revised_clauses,
            "deliverables": [
                {
                    "deliverable_kind": "disagreement_protocol",
                    "state": "draft" if disagreement_items else "pending",
                    "blocker_issue_ids": [],
                    "uncertainty_issue_ids": [],
                },
                {
                    "deliverable_kind": "revised_contract",
                    "state": "candidate_clause_schedule" if revised_clauses else "pending",
                    "blocker_issue_ids": [],
                    "uncertainty_issue_ids": [],
                },
            ],
            "gaps": gaps,
            "authority_boundary": (
                "autonomous commercial-risk draft; qualified human review is required before "
                "legal finalization or signature"
            ),
        }

    def _scope_for(self, owner_identity_id: str, workspace_id: UUID) -> UUID:
        with self._engine.connect() as connection:
            value = connection.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
        if value is None:
            raise TenderContractAnalysisError("workspace_not_found")
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


def _empty_candidate_projection(*, status: str, gaps: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "process": None,
        "assessment": None,
        "clauses": [],
        "issues": [],
        "protocols": [],
        "disagreement_items": [],
        "revised_contracts": [],
        "revised_clauses": [],
        "deliverables": [],
        "gaps": gaps,
        "authority_boundary": "read_only_projection",
    }
