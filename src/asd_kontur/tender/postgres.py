"""Narrow PostgreSQL application service for the Tender process."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of
from asd_kontur.persistence.scope import WorkspaceContext

from .errors import TenderError, TenderErrorCode
from .models import (
    ContractClause,
    CorpusAssessment,
    CorpusItem,
    DisagreementItem,
    LegalAuthority,
    RevisedClause,
    TenderDeliverableKind,
    TenderFinalizationDecision,
    TenderIssue,
    TenderRequirement,
    TenderState,
    TenderTerminalOutcome,
    TypedTenderDeliverable,
)


@dataclass(frozen=True, slots=True)
class StartTenderCommand:
    command_id: UUID
    tender_process_id: UUID
    mode_execution_id: UUID
    process_definition_version: str
    analysis_scope_version: str
    authority_profile_version: str
    contract_registry_version: str
    policy_versions: tuple[str, ...]
    source_class_allowlist: tuple[str, ...]
    purpose: str
    classification: str
    rule_set_version_id: UUID
    input_manifest_digest: str
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID | None

    @property
    def semantic_digest(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class TransitionTenderCommand:
    command_id: UUID
    tender_process_id: UUID
    expected_revision: int
    from_state: TenderState
    to_state: TenderState
    reason_code: str
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID

    @property
    def semantic_digest(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class TenderProcessResult:
    tender_process_id: UUID
    revision: int
    state: TenderState
    fingerprint: str
    idempotent_replay: bool = False


ALLOWED_TRANSITIONS: dict[TenderState, frozenset[TenderState]] = {
    TenderState.REQUESTED: frozenset((TenderState.CORPUS_ASSESSED, TenderState.BLOCKED)),
    TenderState.CORPUS_ASSESSED: frozenset(
        (TenderState.REQUIREMENTS_DETERMINED, TenderState.BLOCKED)
    ),
    TenderState.REQUIREMENTS_DETERMINED: frozenset((TenderState.ANALYZED, TenderState.BLOCKED)),
    TenderState.ANALYZED: frozenset((TenderState.DRAFTED, TenderState.BLOCKED)),
    TenderState.DRAFTED: frozenset((TenderState.WAITING_FOR_AUTHORITY, TenderState.BLOCKED)),
    TenderState.WAITING_FOR_AUTHORITY: frozenset((TenderState.FINALIZED, TenderState.BLOCKED)),
    TenderState.BLOCKED: frozenset(),
    TenderState.FINALIZED: frozenset(),
}

TENDER_CONTRACT_KEYS = {
    TenderDeliverableKind.DISAGREEMENT_PROTOCOL: "tender.disagreement-protocol",
    TenderDeliverableKind.REVISED_CONTRACT: "tender.revised-contract",
    TenderDeliverableKind.RISK_REGISTER: "tender.risk-register",
    TenderDeliverableKind.GAP_REGISTER: "tender.gap-register",
    TenderDeliverableKind.PDRD_ANALYSIS: "tender.pd-rd-analysis",
}


class PostgresTenderProcess:
    """Persist Tender decisions under one explicit workspace transaction scope."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def start(
        self, *, context: WorkspaceContext, command: StartTenderCommand
    ) -> TenderProcessResult:
        self._reject_latest(
            command.process_definition_version,
            command.analysis_scope_version,
            command.authority_profile_version,
            command.contract_registry_version,
            *command.policy_versions,
        )
        fingerprint = digest_of(
            {
                "process": command.tender_process_id,
                "revision": 1,
                "state": TenderState.REQUESTED,
                "input": command.input_manifest_digest,
                "rule_set": command.rule_set_version_id,
            }
        )
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            try:
                with session.begin():
                    _set_scope(session, context)
                    replay = self._claim_idempotency(
                        session,
                        context,
                        handler_key="tender.start",
                        key=command.idempotency_key,
                        digest=command.semantic_digest,
                        command_id=command.command_id,
                        correlation_id=command.correlation_id,
                    )
                    if replay is not None:
                        return self._load_replay(session, context, command.tender_process_id)
                    mode = session.execute(
                        sa.text(
                            "SELECT mode,state,rule_set_version FROM workspace.mode_executions "
                            "WHERE organization_id=:o AND workspace_id=:w AND mode_execution_id=:mode"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "mode": command.mode_execution_id,
                        },
                    ).one_or_none()
                    if mode is None or mode.mode != "Tender":
                        raise TenderError(
                            TenderErrorCode.INVALID_SCOPE,
                            "Tender process requires a Tender ModeExecution in the same workspace.",
                        )
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.tender_processes "
                            "(organization_id,workspace_id,tender_process_id,mode_execution_id,process_definition_version,state,revision,rule_set_version_id,authority_profile_version,contract_registry_version,input_manifest_digest,current_fingerprint,correlation_id,causation_id,created_at,updated_at) "
                            "VALUES (:o,:w,:process,:mode,:definition,'requested',1,:ruleset,:authority,:registry,:manifest,:fingerprint,:correlation,:causation,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.tender_process_id,
                            "mode": command.mode_execution_id,
                            "definition": command.process_definition_version,
                            "ruleset": command.rule_set_version_id,
                            "authority": command.authority_profile_version,
                            "registry": command.contract_registry_version,
                            "manifest": command.input_manifest_digest,
                            "fingerprint": fingerprint,
                            "correlation": command.correlation_id,
                            "causation": command.causation_id,
                        },
                    )
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.tender_scope_versions (organization_id,workspace_id,tender_process_id,scope_version,analysis_scope_version,source_class_allowlist,policy_versions,purpose,classification,authority_profile_version,rule_set_version_id,scope_digest,recorded_at) "
                            "VALUES (:o,:w,:process,1,:scope,:sources,:policies,:purpose,:classification,:authority,:ruleset,:digest,CURRENT_TIMESTAMP)"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.tender_process_id,
                            "scope": command.analysis_scope_version,
                            "sources": list(command.source_class_allowlist),
                            "policies": list(command.policy_versions),
                            "purpose": command.purpose,
                            "classification": command.classification,
                            "authority": command.authority_profile_version,
                            "ruleset": command.rule_set_version_id,
                            "digest": digest_of(
                                {
                                    "scope": command.analysis_scope_version,
                                    "sources": command.source_class_allowlist,
                                    "policies": command.policy_versions,
                                    "purpose": command.purpose,
                                    "classification": command.classification,
                                }
                            ),
                        },
                    )
                    self._append_event(
                        session,
                        context,
                        command.tender_process_id,
                        1,
                        "TenderProcessRequested",
                        fingerprint,
                        command.correlation_id,
                        command.causation_id,
                    )
                    self._complete_idempotency(
                        session,
                        context,
                        "tender.start",
                        command.idempotency_key,
                        f"tender:{command.tender_process_id}:1",
                    )
                return TenderProcessResult(
                    command.tender_process_id, 1, TenderState.REQUESTED, fingerprint
                )
            except TenderError:
                raise
            except sa.exc.DBAPIError as exc:
                raise self._map_db_error(exc) from exc

    def transition(
        self, *, context: WorkspaceContext, command: TransitionTenderCommand
    ) -> TenderProcessResult:
        if command.to_state not in ALLOWED_TRANSITIONS[command.from_state]:
            self._audit_rejection(context, command, "TENDER_INVALID_TRANSITION")
            raise TenderError(TenderErrorCode.INVALID_STATE, "Tender transition is not allowed.")
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            try:
                with session.begin():
                    _set_scope(session, context)
                    replay = self._claim_idempotency(
                        session,
                        context,
                        handler_key="tender.transition",
                        key=command.idempotency_key,
                        digest=command.semantic_digest,
                        command_id=command.command_id,
                        correlation_id=command.correlation_id,
                    )
                    if replay is not None:
                        result = self._load_replay(session, context, command.tender_process_id)
                        return TenderProcessResult(
                            result.tender_process_id,
                            result.revision,
                            result.state,
                            result.fingerprint,
                            True,
                        )
                    row = session.execute(
                        sa.text(
                            "SELECT state,revision,input_manifest_digest,rule_set_version_id FROM workspace.tender_processes "
                            "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process FOR UPDATE"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.tender_process_id,
                        },
                    ).one_or_none()
                    if row is None:
                        raise TenderError(
                            TenderErrorCode.INVALID_SCOPE, "Tender process was not found."
                        )
                    if row.state != command.from_state or row.revision != command.expected_revision:
                        raise TenderError(
                            TenderErrorCode.CONCURRENCY_CONFLICT,
                            "Tender state or expected revision changed.",
                        )
                    self._assert_transition_preconditions(session, context, command)
                    revision = command.expected_revision + 1
                    fingerprint = digest_of(
                        {
                            "process": command.tender_process_id,
                            "revision": revision,
                            "state": command.to_state,
                            "reason": command.reason_code,
                            "input": row.input_manifest_digest,
                            "rule_set": row.rule_set_version_id,
                        }
                    )
                    if command.to_state is TenderState.BLOCKED:
                        try:
                            blocked_outcome = TenderTerminalOutcome(command.reason_code)
                        except ValueError as exc:
                            raise TenderError(
                                TenderErrorCode.INVALID_STATE,
                                "A blocked Tender transition requires a typed terminal outcome.",
                            ) from exc
                        if blocked_outcome is TenderTerminalOutcome.SUCCESS:
                            raise TenderError(
                                TenderErrorCode.INVALID_STATE,
                                "Successful Tender completion requires professional finalization.",
                            )
                        deliverable_ids = list(
                            session.scalars(
                                sa.text(
                                    "SELECT DISTINCT deliverable_id FROM workspace.tender_deliverable_versions "
                                    "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process ORDER BY deliverable_id"
                                ),
                                {
                                    "o": context.organization_id,
                                    "w": context.workspace_id,
                                    "process": command.tender_process_id,
                                },
                            ).all()
                        )
                        session.execute(
                            sa.text(
                                "INSERT INTO workspace.tender_terminal_outcomes (organization_id,workspace_id,terminal_outcome_id,tender_process_id,process_revision,outcome,deliverable_ids,limitation_codes,product_ready,outcome_fingerprint,completed_at) "
                                "VALUES (:o,:w,:terminal,:process,:revision,:outcome,:deliverables,:limitations,false,:fingerprint,CURRENT_TIMESTAMP)"
                            ),
                            {
                                "o": context.organization_id,
                                "w": context.workspace_id,
                                "terminal": uuid7(),
                                "process": command.tender_process_id,
                                "revision": revision,
                                "outcome": blocked_outcome,
                                "deliverables": deliverable_ids,
                                "limitations": [command.reason_code],
                                "fingerprint": fingerprint,
                            },
                        )
                    session.execute(
                        sa.select(
                            sa.func.set_config(
                                "asd.tender_operation_id", str(command.command_id), True
                            )
                        )
                    )
                    session.execute(
                        sa.text(
                            "UPDATE workspace.tender_processes SET state=:state,revision=:revision,current_fingerprint=:fingerprint,updated_at=CURRENT_TIMESTAMP "
                            "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.tender_process_id,
                            "state": command.to_state,
                            "revision": revision,
                            "fingerprint": fingerprint,
                        },
                    )
                    self._append_event(
                        session,
                        context,
                        command.tender_process_id,
                        revision,
                        f"Tender{command.to_state.value.title().replace('_', '')}",
                        fingerprint,
                        command.correlation_id,
                        command.causation_id,
                    )
                    self._complete_idempotency(
                        session,
                        context,
                        "tender.transition",
                        command.idempotency_key,
                        f"tender:{command.tender_process_id}:{revision}",
                    )
                    return TenderProcessResult(
                        command.tender_process_id, revision, command.to_state, fingerprint
                    )
            except TenderError:
                raise
            except sa.exc.DBAPIError as exc:
                raise self._map_db_error(exc) from exc

    def append_corpus_assessment(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        assessment_id: UUID,
        assessment: CorpusAssessment,
        items: tuple[CorpusItem, ...],
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            for item in items:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.tender_corpus_items (organization_id,workspace_id,tender_process_id,corpus_item_id,source_class,source_version_id,source_locator_id,evidence_link_id,admission_state,item_digest,recorded_at) "
                        "VALUES (:o,:w,:process,:item,:class,:source,:locator,:evidence,:state,:digest,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": context.organization_id,
                        "w": context.workspace_id,
                        "process": tender_process_id,
                        "item": uuid7(),
                        "class": item.source_class,
                        "source": item.source_version_id,
                        "locator": item.source_locator_id,
                        "evidence": item.evidence_link_id,
                        "state": "accepted" if item.accepted else "rejected",
                        "digest": digest_of(item),
                    },
                )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_completeness_assessments (organization_id,workspace_id,assessment_id,tender_process_id,assessment_version,required_source_classes,available_source_classes,missing_source_classes,optional_absent_source_classes,status,assessment_fingerprint,assessed_at) "
                    "VALUES (:o,:w,:assessment,:process,1,:required,:available,:missing,:optional,:status,:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "assessment": assessment_id,
                    "process": tender_process_id,
                    "required": list(assessment.required_classes),
                    "available": list(assessment.available_classes),
                    "missing": list(assessment.missing_classes),
                    "optional": list(assessment.optional_absent_classes),
                    "status": assessment.status,
                    "fingerprint": assessment.fingerprint,
                },
            )

    def append_clause(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        clause_key: str,
        clause: ContractClause,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_clause_versions (organization_id,workspace_id,clause_id,clause_version,tender_process_id,clause_key,locator_label,authority_layer,source_version_id,source_locator_id,evidence_link_id,fact_id,fact_version,effective_edition_ref,text_digest,recorded_at) "
                    "VALUES (:o,:w,:clause,:version,:process,:key,:label,:layer,:source,:locator,:evidence,:fact,:fact_version,:edition,:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "clause": clause.clause_id,
                    "version": clause.clause_version,
                    "process": tender_process_id,
                    "key": clause_key,
                    "label": clause.locator_label,
                    "layer": clause.authority_layer,
                    "source": clause.provenance.source_version_id,
                    "locator": clause.provenance.source_locator_id,
                    "evidence": clause.provenance.evidence_link_id,
                    "fact": clause.provenance.fact_id,
                    "fact_version": clause.provenance.fact_version,
                    "edition": clause.effective_edition_ref,
                    "digest": clause.text_digest,
                },
            )

    def append_requirement(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        requirement: TenderRequirement,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_requirement_versions (organization_id,workspace_id,requirement_id,requirement_version,tender_process_id,requirement_key,subject,applicability,rule_set_version_id,rule_trace_id,required_source_classes,evidence_link_ids,uncertainty_code,requirement_digest,recorded_at) "
                    "VALUES (:o,:w,:requirement,:version,:process,:key,:subject,:applicability,:ruleset,:trace,:sources,:evidence,:uncertainty,:digest,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "requirement": requirement.requirement_id,
                    "version": requirement.requirement_version,
                    "process": tender_process_id,
                    "key": requirement.requirement_key,
                    "subject": requirement.subject,
                    "applicability": requirement.applicability,
                    "ruleset": requirement.rule_set_version_id,
                    "trace": requirement.rule_trace_id,
                    "sources": list(requirement.required_source_classes),
                    "evidence": list(requirement.evidence_refs),
                    "uncertainty": "REQUIREMENT_APPLICABILITY_INDETERMINATE"
                    if requirement.applicability.value == "indeterminate"
                    else None,
                    "digest": digest_of(requirement),
                },
            )

    def append_issue(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        issue: TenderIssue,
    ) -> None:
        clause = issue.clause
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_issue_versions (organization_id,workspace_id,issue_id,issue_version,tender_process_id,issue_kind,subject,severity,applicability,clause_id,clause_version,requirement_id,requirement_version,kernel_finding_id,kernel_finding_version,rule_set_version_id,rule_trace_id,uncertainty_code,recommendation_text,consequence_code,status,finding_fingerprint,recorded_at) "
                    "VALUES (:o,:w,:issue,:version,:process,:kind,:subject,:severity,:applicability,:clause,:clause_version,:requirement,:requirement_version,:kernel_finding,:kernel_finding_version,:ruleset,:trace,:uncertainty,:recommendation,:consequence,:status,:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "issue": issue.issue_id,
                    "version": issue.issue_version,
                    "process": tender_process_id,
                    "kind": issue.kind,
                    "subject": issue.subject,
                    "severity": issue.severity,
                    "applicability": issue.applicability,
                    "clause": clause.clause_id if clause else None,
                    "clause_version": clause.clause_version if clause else None,
                    "requirement": issue.requirement_id,
                    "requirement_version": 1 if issue.requirement_id else None,
                    "kernel_finding": issue.kernel_finding_id,
                    "kernel_finding_version": issue.kernel_finding_version,
                    "ruleset": issue.rule_set_version_id,
                    "trace": issue.rule_trace_id,
                    "uncertainty": issue.uncertainty_code,
                    "recommendation": issue.recommended_change,
                    "consequence": issue.consequence_code,
                    "status": "validated",
                    "fingerprint": issue.fingerprint,
                },
            )
            for evidence_id in issue.evidence_refs:
                inserted = session.execute(
                    sa.text(
                        "INSERT INTO workspace.tender_issue_evidence (organization_id,workspace_id,issue_id,issue_version,evidence_link_id,source_version_id,source_locator_id,evidence_role) "
                        "SELECT :o,:w,:issue,:version,evidence_link_id,source_version_id,source_locator_id,'material_finding' "
                        "FROM workspace.evidence_links WHERE organization_id=:o AND workspace_id=:w AND evidence_link_id=:evidence "
                        "RETURNING evidence_link_id"
                    ),
                    {
                        "o": context.organization_id,
                        "w": context.workspace_id,
                        "issue": issue.issue_id,
                        "version": issue.issue_version,
                        "evidence": evidence_id,
                    },
                ).one_or_none()
                if inserted is None:
                    raise TenderError(
                        TenderErrorCode.PROVENANCE_INCOMPLETE,
                        "Tender issue evidence was not found in this workspace.",
                    )

    def confirm_legal_finding(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        issue_id: UUID,
        issue_version: int,
        authority: LegalAuthority,
        correlation_id: UUID,
        causation_id: UUID,
    ) -> UUID:
        if authority.capability != "tender.legal.review":
            raise TenderError(
                TenderErrorCode.AUTHORITY_DENIED,
                "Legal finding confirmation requires tender.legal.review.",
            )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            grant = session.execute(
                sa.text(
                    "SELECT status,human_identity_id,professional_qualification_ref FROM workspace.tender_professional_grants "
                    "WHERE organization_id=:o AND workspace_id=:w AND grant_id=:grant AND grant_version=:version "
                    "AND capability='tender.legal.review' AND effective_from<=CURRENT_TIMESTAMP "
                    "AND (effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "grant": authority.grant_id,
                    "version": authority.grant_version,
                },
            ).one_or_none()
            if (
                grant is None
                or grant.status != "active"
                or grant.human_identity_id != authority.human_identity_id
                or grant.professional_qualification_ref != authority.professional_qualification_ref
            ):
                raise TenderError(TenderErrorCode.AUTHORITY_DENIED, "Legal grant is invalid.")
            issue = session.execute(
                sa.text(
                    "SELECT applicability,severity FROM workspace.tender_issue_versions WHERE organization_id=:o AND workspace_id=:w AND issue_id=:issue AND issue_version=:version"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "issue": issue_id,
                    "version": issue_version,
                },
            ).one_or_none()
            if issue is None or issue.applicability != "applicable":
                raise TenderError(
                    TenderErrorCode.APPLICABILITY_INDETERMINATE,
                    "Only an applicable evidence-bound finding can be professionally confirmed.",
                )
            decision_id = uuid7()
            fingerprint = digest_of(
                {
                    "decision": decision_id,
                    "process": tender_process_id,
                    "issue": issue_id,
                    "issue_version": issue_version,
                    "human": authority.human_identity_id,
                    "grant": authority.grant_id,
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_finding_confirmation_decisions (organization_id,workspace_id,decision_id,tender_process_id,issue_id,issue_version,human_identity_id,grant_id,grant_version,outcome,reason_code,authority_reference,decision_fingerprint,correlation_id,causation_id,decided_at) "
                    "VALUES (:o,:w,:decision,:process,:issue,:issue_version,:human,:grant,:grant_version,'confirmed','TENDER_FINDING_CONFIRMED','authority:qualified-legal-review',:fingerprint,:correlation,:causation,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "decision": decision_id,
                    "process": tender_process_id,
                    "issue": issue_id,
                    "issue_version": issue_version,
                    "human": authority.human_identity_id,
                    "grant": authority.grant_id,
                    "grant_version": authority.grant_version,
                    "fingerprint": fingerprint,
                    "correlation": correlation_id,
                    "causation": causation_id,
                },
            )
            return decision_id

    def append_deliverable(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        deliverable: TypedTenderDeliverable,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_deliverable_versions (organization_id,workspace_id,deliverable_id,deliverable_version,tender_process_id,deliverable_kind,typed_item_ids,source_manifest_digest,evidence_manifest_digest,rule_set_version_id,contract_key,contract_version,schema_id,schema_version,state,blocker_issue_ids,uncertainty_issue_ids,deliverable_fingerprint,recorded_at) "
                    "VALUES (:o,:w,:deliverable,:version,:process,:kind,:items,:source,:evidence,:ruleset,:key,'1.2.0','urn:asd-kontur:contracts:v1.2:schema:tender','1.2.0',:state,:blockers,:uncertainties,:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "deliverable": deliverable.deliverable_id,
                    "version": deliverable.deliverable_version,
                    "process": tender_process_id,
                    "kind": deliverable.kind,
                    "items": list(deliverable.item_ids),
                    "source": deliverable.source_manifest_digest,
                    "evidence": deliverable.evidence_manifest_digest,
                    "ruleset": deliverable.rule_set_version_id,
                    "key": TENDER_CONTRACT_KEYS[deliverable.kind],
                    "state": deliverable.state,
                    "blockers": list(deliverable.blocker_ids),
                    "uncertainties": list(deliverable.uncertainty_ids),
                    "fingerprint": deliverable.fingerprint,
                },
            )

    def append_disagreement_protocol(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        protocol_id: UUID,
        items: tuple[DisagreementItem, ...],
        rule_set_version_id: UUID,
        source_manifest_digest: str,
        evidence_manifest_digest: str,
    ) -> None:
        if not items:
            raise TenderError(TenderErrorCode.OUTPUT_INCOMPLETE, "Protocol items are required.")
        fingerprint = digest_of(items)
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_disagreement_protocol_versions (organization_id,workspace_id,protocol_id,protocol_version,tender_process_id,source_manifest_digest,evidence_manifest_digest,rule_set_version_id,state,blocker_issue_ids,uncertainty_issue_ids,protocol_fingerprint,recorded_at) "
                    "VALUES (:o,:w,:protocol,1,:process,:source,:evidence,:ruleset,'draft',ARRAY[]::uuid[],:uncertainties,:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "protocol": protocol_id,
                    "process": tender_process_id,
                    "source": source_manifest_digest,
                    "evidence": evidence_manifest_digest,
                    "ruleset": rule_set_version_id,
                    "uncertainties": list(
                        dict.fromkeys(
                            uncertainty for item in items for uncertainty in item.uncertainty_ids
                        )
                    ),
                    "fingerprint": fingerprint,
                },
            )
            for item in items:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.tender_disagreement_items (organization_id,workspace_id,protocol_id,protocol_version,item_id,ordinal,clause_id,clause_version,issue_id,issue_version,proposed_clause_text,consequence_code,rule_trace_id,evidence_link_ids,uncertainty_issue_ids,finding_decision_id,item_fingerprint) "
                        "VALUES (:o,:w,:protocol,1,:item,:ordinal,:clause,:clause_version,:issue,:issue_version,:proposed,:consequence,:trace,:evidence,:uncertainties,:decision,:fingerprint)"
                    ),
                    {
                        "o": context.organization_id,
                        "w": context.workspace_id,
                        "protocol": protocol_id,
                        "item": item.item_id,
                        "ordinal": item.ordinal,
                        "clause": item.clause.clause_id,
                        "clause_version": item.clause.clause_version,
                        "issue": item.issue_id,
                        "issue_version": item.issue_version,
                        "proposed": item.proposed_clause_text,
                        "consequence": item.consequence_code,
                        "trace": item.rule_trace_id,
                        "evidence": list(item.evidence_refs),
                        "uncertainties": list(item.uncertainty_ids),
                        "decision": item.finding_decision_id,
                        "fingerprint": digest_of(item),
                    },
                )

    def append_revised_contract(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        revised_contract_id: UUID,
        protocol_id: UUID,
        source_contract_version_id: UUID,
        clauses: tuple[RevisedClause, ...],
        source_manifest_digest: str,
    ) -> None:
        if not clauses:
            raise TenderError(
                TenderErrorCode.OUTPUT_INCOMPLETE, "Revised contract clauses are required."
            )
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.tender_revised_contract_versions (organization_id,workspace_id,revised_contract_id,revised_contract_version,tender_process_id,protocol_id,protocol_version,source_contract_version_id,state,source_manifest_digest,contract_fingerprint,recorded_at) "
                    "VALUES (:o,:w,:contract,1,:process,:protocol,1,:source,'draft',:manifest,:fingerprint,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "contract": revised_contract_id,
                    "process": tender_process_id,
                    "protocol": protocol_id,
                    "source": source_contract_version_id,
                    "manifest": source_manifest_digest,
                    "fingerprint": digest_of(clauses),
                },
            )
            for clause in clauses:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.tender_revised_clause_versions (organization_id,workspace_id,revised_contract_id,revised_contract_version,revised_clause_id,ordinal,source_clause_id,source_clause_version,issue_id,issue_version,disagreement_item_id,decision_id,revised_text,revised_text_digest) "
                        "VALUES (:o,:w,:contract,1,:revised,:ordinal,:source_clause,:source_version,:issue,:issue_version,:item,:decision,:text,:digest)"
                    ),
                    {
                        "o": context.organization_id,
                        "w": context.workspace_id,
                        "contract": revised_contract_id,
                        "revised": clause.revised_clause_id,
                        "ordinal": clause.ordinal,
                        "source_clause": clause.source_clause.clause_id,
                        "source_version": clause.source_clause.clause_version,
                        "issue": clause.issue_id,
                        "issue_version": clause.issue_version,
                        "item": clause.disagreement_item_id,
                        "decision": clause.decision_id,
                        "text": clause.revised_text,
                        "digest": digest_of(clause.revised_text),
                    },
                )

    def finalize(
        self,
        *,
        context: WorkspaceContext,
        tender_process_id: UUID,
        expected_revision: int,
        decision: TenderFinalizationDecision,
        idempotency_key: str,
        correlation_id: UUID,
        causation_id: UUID,
    ) -> TenderProcessResult:
        if decision.outcome is not TenderTerminalOutcome.SUCCESS:
            raise TenderError(
                TenderErrorCode.MATERIAL_BLOCKER,
                "Blocked Tender outcomes use an explicit blocking terminal transition.",
            )
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            try:
                with session.begin():
                    _set_scope(session, context)
                    digest = digest_of(
                        {
                            "process": tender_process_id,
                            "expected": expected_revision,
                            "decision": decision.fingerprint,
                        }
                    )
                    replay = self._claim_idempotency(
                        session,
                        context,
                        handler_key="tender.finalize",
                        key=idempotency_key,
                        digest=digest,
                        command_id=decision.decision_id,
                        correlation_id=correlation_id,
                    )
                    if replay is not None:
                        result = self._load_replay(session, context, tender_process_id)
                        return TenderProcessResult(
                            result.tender_process_id,
                            result.revision,
                            result.state,
                            result.fingerprint,
                            True,
                        )
                    row = session.execute(
                        sa.text(
                            "SELECT state,revision FROM workspace.tender_processes WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process FOR UPDATE"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": tender_process_id,
                        },
                    ).one_or_none()
                    if (
                        row is None
                        or row.state != "waiting_for_authority"
                        or row.revision != expected_revision
                    ):
                        raise TenderError(
                            TenderErrorCode.CONCURRENCY_CONFLICT,
                            "Tender finalization state or revision changed.",
                        )
                    kinds = set(
                        session.scalars(
                            sa.text(
                                "SELECT deliverable_kind FROM workspace.tender_deliverable_versions "
                                "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process "
                                "AND state IN ('draft','reviewed','finalized')"
                            ),
                            {
                                "o": context.organization_id,
                                "w": context.workspace_id,
                                "process": tender_process_id,
                            },
                        ).all()
                    )
                    if kinds != {item.value for item in TenderDeliverableKind}:
                        raise TenderError(
                            TenderErrorCode.OUTPUT_INCOMPLETE,
                            "All five typed Tender outputs are required.",
                        )
                    material_blockers = int(
                        session.scalar(
                            sa.text(
                                "SELECT count(*) FROM workspace.tender_issue_versions i WHERE organization_id=:o AND workspace_id=:w "
                                "AND tender_process_id=:process AND severity='blocking' AND status NOT IN ('resolved','superseded') "
                                "AND NOT EXISTS (SELECT 1 FROM workspace.tender_finding_confirmation_decisions d "
                                "WHERE d.organization_id=i.organization_id AND d.workspace_id=i.workspace_id "
                                "AND d.issue_id=i.issue_id AND d.issue_version=i.issue_version AND d.outcome='confirmed')"
                            ),
                            {
                                "o": context.organization_id,
                                "w": context.workspace_id,
                                "process": tender_process_id,
                            },
                        )
                        or 0
                    )
                    if material_blockers:
                        raise TenderError(
                            TenderErrorCode.MATERIAL_BLOCKER,
                            "Unresolved material Tender blockers prevent success.",
                        )
                    reviewer_decision = self._append_authority_decision(
                        session,
                        context,
                        tender_process_id,
                        decision.reviewer,
                        "legal_review",
                        decision.deliverable_ids[0],
                        correlation_id,
                        causation_id,
                    )
                    finalizer_decision = self._append_authority_decision(
                        session,
                        context,
                        tender_process_id,
                        decision.finalizer,
                        "finalization",
                        decision.deliverable_ids[1],
                        correlation_id,
                        causation_id,
                    )
                    for deliverable_id in decision.deliverable_ids:
                        prior = session.execute(
                            sa.text(
                                "SELECT deliverable_version,tender_process_id,deliverable_kind,typed_item_ids,source_manifest_digest,evidence_manifest_digest,rule_set_version_id,contract_key,contract_version,schema_id,schema_version,uncertainty_issue_ids "
                                "FROM workspace.tender_deliverable_versions WHERE organization_id=:o AND workspace_id=:w AND deliverable_id=:deliverable ORDER BY deliverable_version DESC LIMIT 1"
                            ),
                            {
                                "o": context.organization_id,
                                "w": context.workspace_id,
                                "deliverable": deliverable_id,
                            },
                        ).one()
                        finalized_version = prior.deliverable_version + 1
                        finalized_fingerprint = digest_of(
                            {
                                "deliverable": deliverable_id,
                                "version": finalized_version,
                                "prior_version": prior.deliverable_version,
                                "review": reviewer_decision,
                                "finalize": finalizer_decision,
                            }
                        )
                        session.execute(
                            sa.text(
                                "INSERT INTO workspace.tender_deliverable_versions (organization_id,workspace_id,deliverable_id,deliverable_version,tender_process_id,deliverable_kind,typed_item_ids,source_manifest_digest,evidence_manifest_digest,rule_set_version_id,contract_key,contract_version,schema_id,schema_version,state,blocker_issue_ids,uncertainty_issue_ids,review_decision_id,finalization_decision_id,deliverable_fingerprint,recorded_at) "
                                "VALUES (:o,:w,:deliverable,:version,:process,:kind,:items,:source,:evidence,:ruleset,:key,:contract_version,:schema,:schema_version,'finalized',ARRAY[]::uuid[],:uncertainties,:review,:finalize,:fingerprint,CURRENT_TIMESTAMP)"
                            ),
                            {
                                "o": context.organization_id,
                                "w": context.workspace_id,
                                "deliverable": deliverable_id,
                                "version": finalized_version,
                                "process": prior.tender_process_id,
                                "kind": prior.deliverable_kind,
                                "items": prior.typed_item_ids,
                                "source": prior.source_manifest_digest,
                                "evidence": prior.evidence_manifest_digest,
                                "ruleset": prior.rule_set_version_id,
                                "key": prior.contract_key,
                                "contract_version": prior.contract_version,
                                "schema": prior.schema_id,
                                "schema_version": prior.schema_version,
                                "uncertainties": prior.uncertainty_issue_ids,
                                "review": reviewer_decision,
                                "finalize": finalizer_decision,
                                "fingerprint": finalized_fingerprint,
                            },
                        )
                    revision = expected_revision + 1
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.tender_terminal_outcomes (organization_id,workspace_id,terminal_outcome_id,tender_process_id,process_revision,outcome,deliverable_ids,limitation_codes,reviewer_decision_id,finalization_decision_id,product_ready,outcome_fingerprint,completed_at) "
                            "VALUES (:o,:w,:terminal,:process,:revision,'successful',:deliverables,:limitations,:review,:finalize,false,:fingerprint,CURRENT_TIMESTAMP)"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "terminal": uuid7(),
                            "process": tender_process_id,
                            "revision": revision,
                            "deliverables": list(decision.deliverable_ids),
                            "limitations": list(decision.limitation_codes),
                            "review": reviewer_decision,
                            "finalize": finalizer_decision,
                            "fingerprint": decision.fingerprint,
                        },
                    )
                    fingerprint = digest_of(
                        {
                            "process": tender_process_id,
                            "revision": revision,
                            "state": "finalized",
                            "decision": decision.fingerprint,
                        }
                    )
                    session.execute(
                        sa.select(
                            sa.func.set_config(
                                "asd.tender_operation_id", str(decision.decision_id), True
                            )
                        )
                    )
                    session.execute(
                        sa.text(
                            "UPDATE workspace.tender_processes SET state='finalized',revision=:revision,current_fingerprint=:fingerprint,updated_at=CURRENT_TIMESTAMP "
                            "WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": tender_process_id,
                            "revision": revision,
                            "fingerprint": fingerprint,
                        },
                    )
                    self._append_event(
                        session,
                        context,
                        tender_process_id,
                        revision,
                        "TenderDeliverableFinalized",
                        fingerprint,
                        correlation_id,
                        causation_id,
                    )
                    self._complete_idempotency(
                        session,
                        context,
                        "tender.finalize",
                        idempotency_key,
                        f"tender:{tender_process_id}:{revision}",
                    )
                    return TenderProcessResult(
                        tender_process_id, revision, TenderState.FINALIZED, fingerprint
                    )
            except TenderError:
                raise
            except sa.exc.DBAPIError as exc:
                raise self._map_db_error(exc) from exc

    @staticmethod
    def _append_authority_decision(
        session: Session,
        context: WorkspaceContext,
        process_id: UUID,
        authority: LegalAuthority,
        kind: str,
        deliverable_id: UUID,
        correlation_id: UUID,
        causation_id: UUID,
    ) -> UUID:
        expected_capability = (
            "tender.legal.review" if kind == "legal_review" else "tender.legal.finalize"
        )
        if authority.capability != expected_capability:
            raise TenderError(
                TenderErrorCode.AUTHORITY_DENIED,
                "Tender authority does not carry the required capability.",
            )
        grant = session.execute(
            sa.text(
                "SELECT status,human_identity_id,capability,professional_qualification_ref FROM workspace.tender_professional_grants "
                "WHERE organization_id=:o AND workspace_id=:w AND grant_id=:grant AND grant_version=:version "
                "AND effective_from<=CURRENT_TIMESTAMP AND (effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "grant": authority.grant_id,
                "version": authority.grant_version,
            },
        ).one_or_none()
        if (
            grant is None
            or grant.status != "active"
            or grant.human_identity_id != authority.human_identity_id
            or grant.capability != expected_capability
            or grant.professional_qualification_ref != authority.professional_qualification_ref
        ):
            raise TenderError(TenderErrorCode.AUTHORITY_DENIED, "Tender grant is invalid.")
        version = session.scalar(
            sa.text(
                "SELECT max(deliverable_version) FROM workspace.tender_deliverable_versions WHERE organization_id=:o AND workspace_id=:w AND deliverable_id=:deliverable"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "deliverable": deliverable_id,
            },
        )
        if version is None:
            raise TenderError(TenderErrorCode.OUTPUT_INCOMPLETE, "Deliverable was not found.")
        decision_id = uuid7()
        decision_fingerprint = digest_of(
            {
                "decision": decision_id,
                "kind": kind,
                "deliverable": deliverable_id,
                "version": version,
                "human": authority.human_identity_id,
                "grant": authority.grant_id,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.tender_review_decisions (organization_id,workspace_id,decision_id,tender_process_id,decision_kind,deliverable_id,deliverable_version,human_identity_id,grant_id,grant_version,outcome,reason_code,authority_reference,decision_fingerprint,correlation_id,causation_id,decided_at) "
                "VALUES (:o,:w,:decision,:process,:kind,:deliverable,:version,:human,:grant,:grant_version,'approved','TENDER_PROFESSIONAL_APPROVAL','authority:qualified-human',:fingerprint,:correlation,:causation,CURRENT_TIMESTAMP)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "decision": decision_id,
                "process": process_id,
                "kind": kind,
                "deliverable": deliverable_id,
                "version": version,
                "human": authority.human_identity_id,
                "grant": authority.grant_id,
                "grant_version": authority.grant_version,
                "fingerprint": decision_fingerprint,
                "correlation": correlation_id,
                "causation": causation_id,
            },
        )
        return decision_id

    @staticmethod
    def _assert_transition_preconditions(
        session: Session, context: WorkspaceContext, command: TransitionTenderCommand
    ) -> None:
        if command.to_state is TenderState.CORPUS_ASSESSED:
            count = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.tender_completeness_assessments WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "process": command.tender_process_id,
                },
            )
            if not count:
                raise TenderError(
                    TenderErrorCode.CORPUS_INCOMPLETE,
                    "Corpus assessment must be persisted before the transition.",
                )
        if command.to_state is TenderState.ANALYZED:
            count = session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.tender_issue_versions WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "process": command.tender_process_id,
                },
            )
            if not count:
                raise TenderError(
                    TenderErrorCode.PROVENANCE_INCOMPLETE,
                    "Tender analysis cannot be empty-success.",
                )

    @staticmethod
    def _claim_idempotency(
        session: Session,
        context: WorkspaceContext,
        *,
        handler_key: str,
        key: str,
        digest: str,
        command_id: UUID,
        correlation_id: UUID,
    ) -> str | None:
        inserted = session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_idempotency (organization_id,workspace_id,handler_key,idempotency_key,semantic_digest,command_id,state,correlation_id,created_at) "
                "VALUES (:o,:w,:handler,:key,:digest,:command,'accepted_pending',:correlation,CURRENT_TIMESTAMP) "
                "ON CONFLICT DO NOTHING RETURNING command_id"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "handler": handler_key,
                "key": key,
                "digest": digest,
                "command": command_id,
                "correlation": correlation_id,
            },
        ).one_or_none()
        if inserted is not None:
            return None
        existing = session.execute(
            sa.text(
                "SELECT semantic_digest,outcome_ref FROM messaging.workspace_idempotency WHERE organization_id=:o AND workspace_id=:w AND handler_key=:handler AND idempotency_key=:key FOR UPDATE"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "handler": handler_key,
                "key": key,
            },
        ).one()
        if existing.semantic_digest != digest:
            raise TenderError(
                TenderErrorCode.IDEMPOTENCY_CONFLICT,
                "Idempotency key is bound to a different Tender command.",
            )
        if not existing.outcome_ref:
            raise TenderError(
                TenderErrorCode.IDEMPOTENCY_CONFLICT,
                "Original Tender operation requires reconciliation.",
            )
        return str(existing.outcome_ref)

    @staticmethod
    def _complete_idempotency(
        session: Session,
        context: WorkspaceContext,
        handler_key: str,
        key: str,
        outcome_ref: str,
    ) -> None:
        session.execute(
            sa.text(
                "UPDATE messaging.workspace_idempotency SET state='accepted_completed',outcome_ref=:outcome,completed_at=CURRENT_TIMESTAMP "
                "WHERE organization_id=:o AND workspace_id=:w AND handler_key=:handler AND idempotency_key=:key"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "handler": handler_key,
                "key": key,
                "outcome": outcome_ref,
            },
        )

    @staticmethod
    def _append_event(
        session: Session,
        context: WorkspaceContext,
        process_id: UUID,
        revision: int,
        event_name: str,
        fingerprint: str,
        correlation_id: UUID,
        causation_id: UUID | None,
    ) -> None:
        event_id = uuid7()
        mode_execution_id = session.scalar(
            sa.text(
                "SELECT mode_execution_id FROM workspace.tender_processes WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "process": process_id,
            },
        )
        if mode_execution_id is None:
            raise TenderError(TenderErrorCode.INVALID_SCOPE, "Tender process was not found.")
        payload: dict[str, Any] = {
            "record_type": "tender_process_event",
            "contract_version": "1.2.0",
            "scope": {
                "organization_id": str(context.organization_id),
                "workspace_id": str(context.workspace_id),
                "mode_execution_id": str(mode_execution_id),
            },
            "event_name": event_name,
            "tender_process_id": str(process_id),
            "aggregate_version": revision,
            "fingerprint": fingerprint,
        }
        session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_outbox (organization_id,workspace_id,outbox_record_id,event_id,aggregate_id,aggregate_version,destination,state,attempt_count,contract_key,contract_version,schema_id,schema_version,payload,payload_digest,retention_class,correlation_id,causation_id) "
                "VALUES (:o,:w,:outbox,:event,:aggregate,:version,'workspace-domain','pending',0,'tender.process-event','1.2.0','urn:asd-kontur:contracts:v1.2:schema:tender','1.2.0',CAST(:payload AS jsonb),:digest,'workspace.messaging',:correlation,:causation)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "outbox": uuid7(),
                "event": event_id,
                "aggregate": process_id,
                "version": revision,
                "payload": json.dumps(payload),
                "digest": digest_of(payload),
                "correlation": correlation_id,
                "causation": causation_id,
            },
        )

    @staticmethod
    def _load_replay(
        session: Session, context: WorkspaceContext, process_id: UUID
    ) -> TenderProcessResult:
        row = session.execute(
            sa.text(
                "SELECT revision,state,current_fingerprint FROM workspace.tender_processes WHERE organization_id=:o AND workspace_id=:w AND tender_process_id=:process"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "process": process_id,
            },
        ).one()
        return TenderProcessResult(
            process_id, row.revision, TenderState(row.state), row.current_fingerprint, True
        )

    def _audit_rejection(
        self, context: WorkspaceContext, command: TransitionTenderCommand, reason: str
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, context)
            payload = {
                "command": command.command_id,
                "process": command.tender_process_id,
                "reason": reason,
            }
            session.execute(
                sa.text(
                    "INSERT INTO audit.workspace_records (organization_id,workspace_id,audit_record_id,audit_version,actor_identity_id,service_identity_id,capability,operation,outcome_code,contract_key,contract_version,policy_key,policy_version,correlation_id,causation_id,safe_message_key,retention_class,record_digest) "
                    "VALUES (:o,:w,:audit,1,:actor,:service,'tender.execute','tender.transition','rejected','tender.command','1.2.0','workspace.tender.authority','1.0.0',:correlation,:causation,'TENDER_INVALID_TRANSITION','workspace.audit.content-free',:digest)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "audit": uuid7(),
                    "actor": context.actor_identity_id,
                    "service": context.service_identity_id,
                    "correlation": command.correlation_id,
                    "causation": command.causation_id,
                    "digest": digest_of(payload),
                },
            )

    @staticmethod
    def _reject_latest(*versions: str) -> None:
        if any(not version or version.lower() == "latest" for version in versions):
            raise TenderError(
                TenderErrorCode.INVALID_SCOPE,
                "Persisted Tender commands require exact versions.",
            )

    @staticmethod
    def _map_db_error(exc: sa.exc.DBAPIError) -> TenderError:
        message = str(exc.orig).lower()
        if "write fenced" in message:
            code = TenderErrorCode.WORKSPACE_FENCED
        elif "row-level security" in message or "foreign key" in message:
            code = TenderErrorCode.SCOPE_VIOLATION
        elif "tender process mutation" in message:
            code = TenderErrorCode.AUTHORITY_DENIED
        else:
            code = TenderErrorCode.CONCURRENCY_CONFLICT
        return TenderError(code, "PostgreSQL rejected the Tender operation.")


def _set_scope(session: Session, context: WorkspaceContext) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    )
