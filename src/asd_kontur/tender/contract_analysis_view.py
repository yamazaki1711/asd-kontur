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
from asd_kontur.tender.qwen_contract_analysis import (
    CONTRACT_ANALYSIS_PROFILE,
    contract_commercial_narrative_without_unverified_authority,
    contract_proposed_wording_is_grounded,
    contract_risk_controller_is_grounded,
)

_CONTRACT_ANALYSIS_READ_PROFILES = (
    CONTRACT_ANALYSIS_PROFILE,
    "qwen-contract-analysis-v9",
    "qwen-contract-analysis-v8",
    "qwen-contract-analysis-v7",
)

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_GOVERNING_CONTRACT_CATEGORIES = frozenset(
    {
        "payment",
        "acceptance",
        "liability",
        "warranty",
        "security",
        "termination",
        "change_procedure",
    }
)
_COMMERCIAL_CONTRACT_CATEGORIES = frozenset(
    {"payment", "security", "termination", "change_procedure"}
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
                        "SELECT DISTINCT ON (clause.clause_id) clause.clause_id,"
                        "clause.clause_version,clause.clause_key,clause.locator_label,"
                        "clause.authority_layer,clause.source_version_id,"
                        "clause.source_locator_id,clause.evidence_link_id,"
                        "source.safe_display_name AS source_name,element.page_number AS source_page "
                        "FROM workspace.tender_clause_versions clause "
                        "LEFT JOIN workspace.document_versions source ON "
                        "source.organization_id=clause.organization_id AND "
                        "source.workspace_id=clause.workspace_id AND "
                        "source.source_version_id=clause.source_version_id "
                        "LEFT JOIN LATERAL (SELECT layout.page_number FROM "
                        "workspace.native_layout_element_versions layout WHERE "
                        "layout.organization_id=clause.organization_id AND "
                        "layout.workspace_id=clause.workspace_id AND "
                        "layout.source_locator_id=clause.source_locator_id "
                        "ORDER BY layout.version DESC LIMIT 1) element ON TRUE WHERE "
                        "clause.organization_id=:o AND clause.workspace_id=:w AND "
                        "clause.tender_process_id=:p ORDER BY clause.clause_id,"
                        "clause.clause_version DESC"
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
                    "SELECT DISTINCT v.source_version_id,v.safe_display_name,v.media_type FROM "
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
            historical_contract_awaiting_current_profile = bool(
                session.scalar(
                    sa.text(
                        "SELECT EXISTS (SELECT 1 FROM workspace.document_versions v JOIN "
                        "workspace.document_role_decisions historical ON "
                        "historical.organization_id=v.organization_id AND "
                        "historical.workspace_id=v.workspace_id AND "
                        "historical.document_id=v.document_id AND "
                        "historical.document_version=v.version WHERE v.organization_id=:o AND "
                        "v.workspace_id=:w AND historical.validator_version<>:role_profile AND "
                        "'contract'=ANY(historical.selected_roles) AND EXISTS (SELECT 1 FROM "
                        "workspace.document_version_activation_decisions active WHERE "
                        "active.organization_id=v.organization_id AND "
                        "active.workspace_id=v.workspace_id AND active.document_id=v.document_id "
                        "AND active.selected_document_version=v.version AND NOT EXISTS (SELECT 1 "
                        "FROM workspace.document_version_activation_decisions newer WHERE "
                        "newer.organization_id=active.organization_id AND "
                        "newer.workspace_id=active.workspace_id AND "
                        "newer.document_id=active.document_id AND "
                        "newer.decision_version>active.decision_version)) AND NOT EXISTS (SELECT 1 "
                        "FROM workspace.document_role_decisions current_decision WHERE "
                        "current_decision.organization_id=v.organization_id AND "
                        "current_decision.workspace_id=v.workspace_id AND "
                        "current_decision.document_id=v.document_id AND "
                        "current_decision.document_version=v.version AND "
                        "current_decision.validator_version=:role_profile))"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "role_profile": QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                    },
                )
            )
            role_analysis_active = bool(
                session.scalar(
                    sa.text(
                        "SELECT EXISTS (SELECT 1 FROM workspace.durable_jobs WHERE "
                        "organization_id=:o AND workspace_id=:w AND "
                        "job_kind='DOCUMENT_PAGE_CLASSIFICATION' AND "
                        "state IN ('queued','leased','running') AND "
                        "input_manifest->>'classification_profile' LIKE '%' || :role_profile)"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "role_profile": QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                    },
                )
            )
            if role_analysis_active:
                return _empty_candidate_projection(
                    status="analysis_pending",
                    gaps=["CONTRACT_SOURCE_CLASSIFICATION_IN_PROGRESS"],
                )
            if historical_contract_awaiting_current_profile:
                return _empty_candidate_projection(
                    status="analysis_pending",
                    gaps=["CONTRACT_SOURCE_RECLASSIFICATION_PENDING"],
                )
            return _empty_candidate_projection(
                status="contract_input_unavailable",
                gaps=["DRAFT_CONTRACT_SOURCE_UNAVAILABLE"],
            )
        jobs = list(
            session.execute(
                sa.text(
                    "SELECT job_id,input_digest,state,typed_failure_code,created_at,completed_at,"
                    "input_manifest->>'contract_analysis_profile' AS profile_version FROM "
                    "workspace.durable_jobs WHERE organization_id=:o AND workspace_id=:w "
                    "AND job_kind='CONTRACT_ANALYSIS' AND "
                    "input_manifest->>'contract_analysis_profile'=ANY(:profiles) "
                    "ORDER BY created_at DESC,job_id DESC"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "profiles": list(_CONTRACT_ANALYSIS_READ_PROFILES),
                },
            ).mappings()
        )
        effective_jobs = _effective_profile_jobs(jobs)
        active = any(str(job["state"]) in {"queued", "leased", "running"} for job in effective_jobs)
        failed = [
            job
            for job in effective_jobs
            if str(job["state"]) in {"failed", "reconciliation_required"}
        ]
        effective_run_terminal = bool(effective_jobs) and not active
        results = list(
            session.execute(
                sa.text(
                    "SELECT result.job_id,result.source_version_id,result.batch_ordinal,"
                    "result.profile_version,result.result_manifest,result.recorded_at,"
                    "job.input_manifest "
                    "FROM workspace.contract_analysis_results result "
                    "JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id AND "
                    "job.workspace_id=result.workspace_id AND job.job_id=result.job_id WHERE "
                    "result.organization_id=:o AND result.workspace_id=:w AND job.state='succeeded' "
                    "AND result.profile_version=ANY(:profiles) "
                    "ORDER BY result.source_version_id,result.batch_ordinal,result.recorded_at"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "profiles": list(_CONTRACT_ANALYSIS_READ_PROFILES),
                },
            ).mappings()
        )
        results = _preferred_contract_results(results, current_run_terminal=effective_run_terminal)
        analysis_complete = bool(results) and effective_run_terminal and not failed
        source_name_by_id = {
            str(source["source_version_id"]): str(source["safe_display_name"])
            for source in contract_sources
        }
        source_ids = [UUID(value) for value in source_name_by_id]
        locator_page_by_id = {
            str(row["source_locator_id"]): int(row["page_number"])
            for row in session.execute(
                sa.text(
                    "SELECT DISTINCT ON (source_locator_id) source_locator_id,page_number "
                    "FROM workspace.native_layout_element_versions WHERE organization_id=:o "
                    "AND workspace_id=:w AND source_version_id=ANY(:sources) "
                    "ORDER BY source_locator_id,version DESC"
                ),
                {"o": organization_id, "w": workspace_id, "sources": source_ids},
            ).mappings()
        }
        clauses: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        disagreement_items: list[dict[str, Any]] = []
        revised_clauses: list[dict[str, Any]] = []
        for result in results:
            manifest = result["result_manifest"]
            if not isinstance(manifest, dict):
                continue
            input_manifest = result["input_manifest"]
            context_complete = bool(
                isinstance(input_manifest, dict) and input_manifest.get("context_complete") is True
            )
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
                        "source_name": source_name_by_id.get(str(result["source_version_id"])),
                        "source_locator_id": locator_ids[0] if locator_ids else None,
                        "source_locator_ids": locator_ids,
                        "source_page": (
                            locator_page_by_id.get(locator_ids[0]) if locator_ids else None
                        ),
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
                if not context_complete:
                    continue
                if not contract_risk_controller_is_grounded(risk):
                    continue
                description = contract_commercial_narrative_without_unverified_authority(
                    risk.get("description")
                )
                consequence = contract_commercial_narrative_without_unverified_authority(
                    risk.get("practical_consequence")
                )
                recommendation = contract_commercial_narrative_without_unverified_authority(
                    risk.get("recommended_action")
                )
                if not description or not consequence or not recommendation:
                    continue
                clause_ref = str(risk.get("clause_ref") or "")
                risk_clause_id = clause_ids.get(clause_ref)
                if risk_clause_id is None:
                    continue
                source_clause = next(
                    (item for item in clauses if str(item.get("clause_id")) == risk_clause_id),
                    None,
                )
                proposed = risk.get("proposed_contractor_wording")
                proposed_is_grounded = bool(
                    proposed
                    and source_clause is not None
                    and contract_proposed_wording_is_grounded(
                        str(source_clause.get("source_text") or ""), str(proposed)
                    )
                )
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
                    "risk_mechanism": risk.get("risk_mechanism"),
                    "trigger_text": risk.get("trigger_text"),
                    "adverse_effect_text": risk.get("adverse_effect_text"),
                    "severity": risk.get("severity"),
                    "applicability": "candidate",
                    "clause_id": risk_clause_id,
                    "clause_version": 1,
                    "uncertainty_code": risk.get("uncertainty")
                    or (
                        None
                        if not proposed or proposed_is_grounded
                        else "PROPOSED_WORDING_NUMERIC_TERM_UNGROUNDED"
                    ),
                    "description": description,
                    "recommendation_text": recommendation,
                    "consequence_code": consequence,
                    "confidence": risk.get("confidence"),
                    "authority": risk.get("authority"),
                }
                issues.append(issue)
                if risk.get("disagreement_required") is True and proposed and proposed_is_grounded:
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
                            "replacement_source_text": risk.get("replacement_source_text"),
                            "consequence_code": consequence,
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
                            "replacement_source_text": risk.get("replacement_source_text"),
                        }
                    )
        status = "analyzing" if active else "drafted" if results else "analysis_pending"
        gaps: list[str] = []
        if active:
            gaps.append("CONTRACT_ANALYSIS_IN_PROGRESS")
        if failed:
            gaps.append("CONTRACT_ANALYSIS_BATCH_FAILURES")
        if results and not issues:
            gaps.append("CONTRACT_RISKS_NOT_IDENTIFIED_IN_COMPLETED_BATCHES")
        revised_source_ids = {
            str(clause.get("source_version_id"))
            for revision in revised_clauses
            if (
                clause := next(
                    (
                        item
                        for item in clauses
                        if str(item.get("clause_id")) == str(revision.get("source_clause_id"))
                        and str(item.get("clause_version"))
                        == str(revision.get("source_clause_version"))
                    ),
                    None,
                )
            )
            and clause.get("source_version_id")
        }
        revised_sources = [
            source
            for source in contract_sources
            if str(source["source_version_id"]) in revised_source_ids
        ]
        primary_revised_source = _select_primary_revised_contract_source(
            revised_sources,
            clauses=clauses,
        )
        selected_source_id = (
            str(primary_revised_source["source_version_id"])
            if primary_revised_source is not None
            else None
        )
        included_revision_count = sum(
            1
            for revision in revised_clauses
            if _revision_source_id(revision, clauses) == selected_source_id
        )
        external_revision_count = len(revised_clauses) - included_revision_count
        revised_contract_available = (
            analysis_complete
            and primary_revised_source is not None
            and _is_docx_source(primary_revised_source)
            and included_revision_count > 0
        )
        if revised_contract_available and external_revision_count:
            gaps.append("REVISED_CONTRACT_EXCLUDES_NON_PRIMARY_SOURCE_REVISIONS")
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
                "sources": [
                    {
                        "source_version_id": str(source["source_version_id"]),
                        "safe_display_name": str(source["safe_display_name"]),
                        "media_type": str(source["media_type"]),
                    }
                    for source in contract_sources
                ],
            },
            "clauses": clauses,
            "issues": issues,
            "protocols": [],
            "disagreement_items": disagreement_items,
            "revised_contracts": (
                [
                    {
                        "revised_contract_id": f"candidate:{workspace_id}",
                        "revised_contract_version": 1,
                        "source_contract_version_id": selected_source_id,
                        "state": "source_format_supported",
                        "scope": (
                            "primary_contract_with_external_revision_schedule"
                            if external_revision_count
                            else "complete_revision_set"
                        ),
                        "included_revision_count": included_revision_count,
                        "external_revision_count": external_revision_count,
                    }
                ]
                if revised_contract_available
                else []
            ),
            "revised_clauses": revised_clauses,
            "deliverables": [
                {
                    "deliverable_kind": "disagreement_protocol",
                    "state": (
                        "draft"
                        if disagreement_items and analysis_complete
                        else "partial_draft"
                        if disagreement_items
                        else "pending"
                    ),
                    "blocker_issue_ids": [],
                    "uncertainty_issue_ids": [],
                },
                {
                    "deliverable_kind": "revised_contract",
                    "state": (
                        "source_format_supported"
                        if revised_contract_available
                        else "candidate_clause_schedule"
                        if revised_clauses
                        else "pending"
                    ),
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


def _select_primary_revised_contract_source(
    revised_sources: list[Any],
    *,
    clauses: list[dict[str, Any]],
) -> Any | None:
    """Select one governing contract without relying on filenames.

    A single revised source is unambiguous.  When revisions also belong to a
    technical assignment or other attachment, the governing contract must
    demonstrate materially broader contract mechanics.  A close score remains
    unresolved so the product keeps a clause schedule instead of rewriting the
    wrong source document.
    """

    supported = [source for source in revised_sources if _is_docx_source(source)]
    if len(supported) == 1:
        return supported[0]
    if len(supported) < 2:
        return None

    categories_by_source: dict[str, set[str]] = {}
    for clause in clauses:
        source_id = str(clause.get("source_version_id") or "")
        category = str(clause.get("category") or "").strip().lower()
        if source_id and category:
            categories_by_source.setdefault(source_id, set()).add(category)

    ranked: list[tuple[int, int, Any]] = []
    for source in supported:
        categories = categories_by_source.get(str(source["source_version_id"]), set())
        governing = categories & _GOVERNING_CONTRACT_CATEGORIES
        commercial = categories & _COMMERCIAL_CONTRACT_CATEGORIES
        ranked.append((len(governing), len(commercial), source))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best, runner_up = ranked[0], ranked[1]
    if best[0] < 4 or best[1] < 1 or best[0] - runner_up[0] < 2:
        return None
    if len(ranked) > 2 and (best[0], best[1]) == (ranked[2][0], ranked[2][1]):
        return None
    return best[2]


def _revision_source_id(revision: dict[str, Any], clauses: list[dict[str, Any]]) -> str | None:
    source_clause_id = str(revision.get("source_clause_id") or "")
    source_clause_version = str(revision.get("source_clause_version") or "")
    for clause in clauses:
        if str(clause.get("clause_id") or "") != source_clause_id:
            continue
        if str(clause.get("clause_version") or "") != source_clause_version:
            continue
        value = clause.get("source_version_id")
        return str(value) if value else None
    return None


def _is_docx_source(source: Any) -> bool:
    media_type = str(source["media_type"])
    return media_type == _DOCX_MEDIA_TYPE or (
        media_type == "application/octet-stream"
        and str(source["safe_display_name"]).lower().endswith(".docx")
    )


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _row(value: Any) -> dict[str, Any]:
    return {key: str(item) if isinstance(item, UUID) else item for key, item in dict(value).items()}


def _preferred_contract_results(results: list[Any], *, current_run_terminal: bool) -> list[Any]:
    """Switch profiles atomically when their batch boundaries may differ.

    A profile may change context size or table packing, so equal batch ordinals
    do not prove equal source coverage. Keep the complete prior professional
    projection visible while a replacement run is incomplete. A new project
    with no prior results still exposes its current profile progressively.
    """

    current = [
        result for result in results if str(result["profile_version"]) == CONTRACT_ANALYSIS_PROFILE
    ]
    prior = [
        result for result in results if str(result["profile_version"]) != CONTRACT_ANALYSIS_PROFILE
    ]
    if current and (current_run_terminal or not prior):
        return current
    return prior


def _effective_profile_jobs(jobs: list[Any]) -> list[Any]:
    """Use the current run when started, otherwise retain prior-run progress."""

    current_jobs = [job for job in jobs if str(job["profile_version"]) == CONTRACT_ANALYSIS_PROFILE]
    return _latest_job_attempts(current_jobs or jobs)


def _latest_job_attempts(jobs: list[Any]) -> list[Any]:
    """Return the newest immutable attempt for each exact analysis input.

    The query supplies newest attempts first. Historical failures remain in the
    ledger, but a later autonomous replacement with the same input digest is
    the effective attempt for product progress and deliverable readiness.
    """

    latest: dict[str, Any] = {}
    for job in jobs:
        latest.setdefault(str(job["input_digest"]), job)
    return list(latest.values())


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
