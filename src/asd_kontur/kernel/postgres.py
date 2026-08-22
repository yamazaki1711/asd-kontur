"""Narrow transactional persistence services for the WP-11 kernel."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of
from asd_kontur.persistence.scope import WorkspaceContext

from .authority import ConfirmationGate
from .errors import KernelError, KernelErrorCode
from .models import (
    Applicability,
    ConfirmationPolicy,
    ConfirmationRequest,
    ConfirmationResult,
    DecisionOutcome,
    DeterministicAuthority,
    EvidenceBinding,
    FactClass,
    FactValueKind,
    HumanAuthority,
)


@dataclass(frozen=True, slots=True)
class ConfirmCandidateCommand:
    command_id: UUID
    confirmation_decision_id: UUID
    fact_id: UUID
    expected_fact_version: int
    candidate_id: UUID
    candidate_version: int
    field_path: str
    fact_type: str
    fact_class: FactClass
    value_kind: FactValueKind
    confirmation_policy_id: UUID
    confirmation_policy_version: str
    authority_kind: str
    authority_identity_id: str
    grant_id: UUID | None
    grant_version: int | None
    rule_set_version_id: UUID | None
    rule_version_id: UUID | None
    rule_evaluation_id: UUID | None
    rule_trace_id: UUID | None
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID
    effective_from: datetime

    @property
    def semantic_digest(self) -> str:
        return digest_of(self)


class PostgresCommonKernel:
    """Confirm exact Candidate fields and append typed Fact versions atomically."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._gate = ConfirmationGate()

    def confirm_candidate(
        self, *, context: WorkspaceContext, command: ConfirmCandidateCommand
    ) -> ConfirmationResult:
        if command.confirmation_policy_version.lower() == "latest":
            raise KernelError(
                KernelErrorCode.AUTHORITY_DENIED, "Persisted policy references must be exact."
            )
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            try:
                with session.begin():
                    _set_scope(session, context)
                    replay = self._claim_idempotency(session, context, command)
                    if replay is not None:
                        return replay
                    session.execute(
                        sa.select(
                            sa.func.set_config(
                                "asd.kernel_operation_id",
                                str(command.confirmation_decision_id),
                                True,
                            )
                        )
                    )
                    candidate, evidence = self._load_candidate(session, context, command)
                    policy = self._load_policy(session, command)
                    authority = self._load_authority(session, context, command)
                    request = ConfirmationRequest(
                        command.confirmation_decision_id,
                        command.fact_id,
                        command.expected_fact_version,
                        command.fact_type,
                        command.fact_class,
                        command.value_kind,
                        candidate,
                        policy,
                        authority,
                        command.correlation_id,
                        command.causation_id,
                        command.idempotency_key,
                    )
                    result = self._gate.confirm(request)
                    value = _typed_value(
                        command.value_kind, candidate_value=candidate_value(candidate)
                    )
                    fact_version = self._lock_and_advance_fact(session, context, command)
                    self._persist_decision_and_fact(
                        session,
                        context,
                        command,
                        request,
                        result,
                        fact_version,
                        value,
                        evidence,
                    )
                    self._append_audit_and_event(session, context, command, fact_version)
                    session.execute(
                        sa.text(
                            "UPDATE messaging.workspace_idempotency SET state='accepted_completed',"
                            "outcome_ref=:outcome,completed_at=CURRENT_TIMESTAMP WHERE organization_id=:o "
                            "AND workspace_id=:w AND handler_key='kernel.confirm-fact' AND idempotency_key=:key"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "key": command.idempotency_key,
                            "outcome": f"workspace-fact:{command.fact_id}:{fact_version}",
                        },
                    )
                    return ConfirmationResult(
                        result.outcome,
                        result.decision_id,
                        result.fact_id,
                        fact_version,
                        result.reason_code,
                    )
            except KernelError:
                raise
            except sa.exc.DBAPIError as exc:
                message = str(exc.orig).lower()
                code = (
                    KernelErrorCode.WORKSPACE_FENCED
                    if "write fenced" in message
                    else KernelErrorCode.SCOPE_VIOLATION
                    if "row-level security" in message or "foreign key" in message
                    else KernelErrorCode.CONCURRENCY_CONFLICT
                    if "concurrency" in message
                    else KernelErrorCode.AUTHORITY_DENIED
                )
                raise KernelError(
                    code, "PostgreSQL rejected the fact confirmation transition."
                ) from exc

    @staticmethod
    def _claim_idempotency(
        session: Session, context: WorkspaceContext, command: ConfirmCandidateCommand
    ) -> ConfirmationResult | None:
        inserted = session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_idempotency "
                "(organization_id,workspace_id,handler_key,idempotency_key,semantic_digest,command_id,state,correlation_id,created_at) "
                "VALUES (:o,:w,'kernel.confirm-fact',:key,:digest,:command,'accepted_pending',:correlation,CURRENT_TIMESTAMP) "
                "ON CONFLICT DO NOTHING RETURNING command_id"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "key": command.idempotency_key,
                "digest": command.semantic_digest,
                "command": command.command_id,
                "correlation": command.correlation_id,
            },
        ).one_or_none()
        if inserted is not None:
            return None
        existing = session.execute(
            sa.text(
                "SELECT semantic_digest,outcome_ref FROM messaging.workspace_idempotency "
                "WHERE organization_id=:o AND workspace_id=:w AND handler_key='kernel.confirm-fact' "
                "AND idempotency_key=:key FOR UPDATE"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "key": command.idempotency_key,
            },
        ).one()
        if existing.semantic_digest != command.semantic_digest:
            raise KernelError(
                KernelErrorCode.IDEMPOTENCY_CONFLICT,
                "The idempotency key is already bound to a different semantic command.",
            )
        if not existing.outcome_ref:
            raise KernelError(
                KernelErrorCode.IDEMPOTENCY_CONFLICT,
                "The original command has no terminal outcome and requires reconciliation.",
            )
        version = int(str(existing.outcome_ref).rsplit(":", 1)[1])
        return ConfirmationResult(
            outcome=DecisionOutcome.CONFIRMED,
            decision_id=command.confirmation_decision_id,
            fact_id=command.fact_id,
            fact_version=version,
            reason_code="idempotent_replay",
        )

    @staticmethod
    def _load_candidate(
        session: Session, context: WorkspaceContext, command: ConfirmCandidateCommand
    ) -> tuple[Any, tuple[EvidenceBinding, ...]]:
        row = session.execute(
            sa.text(
                "SELECT cv.status,cf.typed_value,vr.validation_run_id,vr.status AS validation_status,"
                "vr.skipped_validators FROM workspace.candidate_versions cv "
                "JOIN workspace.candidate_fields cf USING (organization_id,workspace_id,candidate_id,candidate_version) "
                "JOIN workspace.vlm_validation_runs vr ON vr.organization_id=cv.organization_id "
                "AND vr.workspace_id=cv.workspace_id AND vr.candidate_id=cv.candidate_id "
                "AND vr.candidate_version=cv.candidate_version "
                "WHERE cv.organization_id=:o AND cv.workspace_id=:w AND cv.candidate_id=:candidate "
                "AND cv.candidate_version=:version AND cf.field_path=:field AND vr.status='passed' "
                "ORDER BY vr.validated_at DESC LIMIT 1"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "candidate": command.candidate_id,
                "version": command.candidate_version,
                "field": command.field_path,
            },
        ).one_or_none()
        if row is None:
            raise KernelError(
                KernelErrorCode.CANDIDATE_NOT_VALIDATED,
                "The exact validated Candidate field was not found in this workspace.",
            )
        failures = int(
            session.scalar(
                sa.text(
                    "SELECT count(*) FROM workspace.vlm_validation_failures WHERE organization_id=:o "
                    "AND workspace_id=:w AND validation_run_id=:run AND blocking=true"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "run": row.validation_run_id,
                },
            )
            or 0
        )
        evidence_rows = session.execute(
            sa.text(
                "SELECT cfe.source_version_id,cfe.source_locator_id,cfe.evidence_link_id "
                "FROM workspace.candidate_field_evidence cfe JOIN workspace.source_versions sv "
                "USING (organization_id,workspace_id,source_version_id) "
                "WHERE cfe.organization_id=:o AND cfe.workspace_id=:w AND cfe.candidate_id=:candidate "
                "AND cfe.candidate_version=:version AND cfe.field_path=:field "
                "AND cfe.evidence_link_id IS NOT NULL AND sv.admission_status='accepted' "
                "ORDER BY cfe.source_locator_id"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "candidate": command.candidate_id,
                "version": command.candidate_version,
                "field": command.field_path,
            },
        ).all()
        evidence = tuple(
            EvidenceBinding(item.source_version_id, item.source_locator_id, item.evidence_link_id)
            for item in evidence_rows
        )
        from .models import CandidateAssessment

        assessment = CandidateAssessment(
            command.candidate_id,
            command.candidate_version,
            command.field_path,
            row.status,
            row.validation_run_id,
            row.validation_status == "passed" and failures == 0,
            tuple(row.skipped_validators),
            bool(evidence),
            evidence,
            row.typed_value,
        )
        return assessment, evidence

    @staticmethod
    def _load_policy(session: Session, command: ConfirmCandidateCommand) -> ConfirmationPolicy:
        row = session.execute(
            sa.text(
                "SELECT auto_confirm_fact_classes,professional_fact_classes,status "
                "FROM platform.confirmation_policy_versions WHERE confirmation_policy_id=:id "
                "AND version=:version AND effective_from<=CURRENT_TIMESTAMP "
                "AND (effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP)"
            ),
            {"id": command.confirmation_policy_id, "version": command.confirmation_policy_version},
        ).one_or_none()
        if row is None:
            raise KernelError(
                KernelErrorCode.AUTHORITY_DENIED, "Confirmation policy is unavailable."
            )
        return ConfirmationPolicy(
            command.confirmation_policy_id,
            command.confirmation_policy_version,
            frozenset(FactClass(item) for item in row.auto_confirm_fact_classes),
            frozenset(FactClass(item) for item in row.professional_fact_classes),
            row.status,
        )

    @staticmethod
    def _load_authority(
        session: Session, context: WorkspaceContext, command: ConfirmCandidateCommand
    ) -> HumanAuthority | DeterministicAuthority:
        if command.authority_kind == "qualified_human":
            if command.grant_id is None or command.grant_version is None:
                raise KernelError(KernelErrorCode.AUTHORITY_DENIED, "Human grant is required.")
            row = session.execute(
                sa.text(
                    "SELECT human_identity_id,capability,fact_classes,status,professional_qualification_ref "
                    "FROM workspace.confirmation_authority_grants "
                    "WHERE organization_id=:o AND workspace_id=:w AND grant_id=:grant AND grant_version=:version "
                    "AND effective_from<=CURRENT_TIMESTAMP AND (effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "grant": command.grant_id,
                    "version": command.grant_version,
                },
            ).one_or_none()
            if row is None or row.human_identity_id != command.authority_identity_id:
                raise KernelError(
                    KernelErrorCode.AUTHORITY_DENIED, "Human authority grant is invalid."
                )
            return HumanAuthority(
                row.human_identity_id,
                command.grant_id,
                command.grant_version,
                row.capability,
                frozenset(FactClass(item) for item in row.fact_classes),
                row.status == "active",
                row.professional_qualification_ref,
            )
        if command.authority_kind != "deterministic_rule" or None in (
            command.rule_set_version_id,
            command.rule_version_id,
            command.rule_evaluation_id,
            command.rule_trace_id,
        ):
            raise KernelError(
                KernelErrorCode.AUTHORITY_DENIED, "Deterministic authority is incomplete."
            )
        assert command.rule_set_version_id is not None
        assert command.rule_version_id is not None
        assert command.rule_evaluation_id is not None
        assert command.rule_trace_id is not None
        row = session.execute(
            sa.text(
                "SELECT re.applicability,re.outcome,rt.deterministic_fingerprint,"
                "(SELECT status FROM platform.rule_version_states rvs WHERE rvs.rule_version_id=:rule ORDER BY state_sequence DESC LIMIT 1) AS rule_status,"
                "EXISTS (SELECT 1 FROM platform.rule_set_memberships rsm WHERE rsm.rule_set_version_id=:ruleset AND rsm.rule_version_id=:rule) AS member,"
                "EXISTS (SELECT 1 FROM platform.rule_set_versions rsv JOIN workspace.workspaces w "
                "ON w.rule_set_key=rsv.rule_set_key AND w.rule_set_version=rsv.version "
                "WHERE rsv.rule_set_version_id=:ruleset AND w.organization_id=:o AND w.workspace_id=:w) AS pinned "
                "FROM workspace.rule_evaluations re JOIN workspace.rule_traces rt "
                "ON rt.organization_id=re.organization_id AND rt.workspace_id=re.workspace_id "
                "AND rt.rule_evaluation_id=re.rule_evaluation_id "
                "WHERE re.organization_id=:o AND re.workspace_id=:w AND re.rule_evaluation_id=:evaluation "
                "AND re.rule_set_version_id=:ruleset AND re.rule_version_id=:rule AND rt.rule_trace_id=:trace"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "evaluation": command.rule_evaluation_id,
                "ruleset": command.rule_set_version_id,
                "rule": command.rule_version_id,
                "trace": command.rule_trace_id,
            },
        ).one_or_none()
        if row is None:
            raise KernelError(KernelErrorCode.RULE_NOT_ACTIVE, "Exact RuleTrace was not found.")
        return DeterministicAuthority(
            command.authority_identity_id,
            command.rule_version_id,
            command.rule_set_version_id,
            command.rule_evaluation_id,
            command.rule_trace_id,
            row.deterministic_fingerprint,
            Applicability(row.applicability),
            row.outcome,
            row.rule_status == "active",
            bool(row.member and row.pinned),
        )

    @staticmethod
    def _lock_and_advance_fact(
        session: Session, context: WorkspaceContext, command: ConfirmCandidateCommand
    ) -> int:
        row = session.execute(
            sa.text(
                "SELECT current_version FROM workspace.workspace_facts WHERE organization_id=:o "
                "AND workspace_id=:w AND fact_id=:fact FOR UPDATE"
            ),
            {"o": context.organization_id, "w": context.workspace_id, "fact": command.fact_id},
        ).one_or_none()
        if row is None:
            if command.expected_fact_version != 0:
                raise KernelError(
                    KernelErrorCode.CONCURRENCY_CONFLICT,
                    "A new fact requires expected version zero.",
                )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.workspace_facts (organization_id,workspace_id,fact_id,fact_type,fact_class,current_version,revision,retention_class,created_at,updated_at) "
                    "VALUES (:o,:w,:fact,:type,:class,1,1,'workspace.domain',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "fact": command.fact_id,
                    "type": command.fact_type,
                    "class": command.fact_class.value,
                },
            )
            return 1
        current = int(row.current_version)
        if current != command.expected_fact_version:
            raise KernelError(
                KernelErrorCode.CONCURRENCY_CONFLICT,
                "Fact expected version does not match current state.",
            )
        session.execute(
            sa.text(
                "UPDATE workspace.workspace_facts SET current_version=current_version+1,revision=revision+1,updated_at=CURRENT_TIMESTAMP "
                "WHERE organization_id=:o AND workspace_id=:w AND fact_id=:fact"
            ),
            {"o": context.organization_id, "w": context.workspace_id, "fact": command.fact_id},
        )
        return current + 1

    @staticmethod
    def _persist_decision_and_fact(
        session: Session,
        context: WorkspaceContext,
        command: ConfirmCandidateCommand,
        request: ConfirmationRequest,
        result: ConfirmationResult,
        fact_version: int,
        value: dict[str, Any],
        evidence: tuple[EvidenceBinding, ...],
    ) -> None:
        authority = request.authority
        is_human = isinstance(authority, HumanAuthority)
        session.execute(
            sa.text(
                "INSERT INTO workspace.confirmation_decisions (organization_id,workspace_id,confirmation_decision_id,candidate_id,candidate_version,field_path,validation_run_id,fact_class,outcome,authority_kind,actor_identity_id,service_identity_id,grant_id,grant_version,confirmation_policy_id,confirmation_policy_version,rule_set_version_id,rule_version_id,rule_evaluation_id,rule_trace_id,authority_reference,reason_code,decision_fingerprint,correlation_id,causation_id,decided_at) "
                "VALUES (:o,:w,:decision,:candidate,:candidate_version,:field,:validation,:fact_class,'confirmed',:authority_kind,:actor,:service,:grant,:grant_version,:policy,:policy_version,:ruleset,:rule,:evaluation,:trace,:authority_ref,:reason,:fingerprint,:correlation,:causation,CURRENT_TIMESTAMP)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "decision": command.confirmation_decision_id,
                "candidate": command.candidate_id,
                "candidate_version": command.candidate_version,
                "field": command.field_path,
                "validation": request.candidate.validation_run_id,
                "fact_class": command.fact_class.value,
                "authority_kind": command.authority_kind,
                "actor": command.authority_identity_id if is_human else None,
                "service": None if is_human else command.authority_identity_id,
                "grant": command.grant_id,
                "grant_version": command.grant_version,
                "policy": command.confirmation_policy_id,
                "policy_version": command.confirmation_policy_version,
                "ruleset": command.rule_set_version_id,
                "rule": command.rule_version_id,
                "evaluation": command.rule_evaluation_id,
                "trace": command.rule_trace_id,
                "authority_ref": (
                    f"grant:{command.grant_id}:{command.grant_version}"
                    if is_human
                    else f"rule-trace:{command.rule_trace_id}"
                ),
                "reason": result.reason_code,
                "fingerprint": result.fingerprint,
                "correlation": command.correlation_id,
                "causation": command.causation_id,
            },
        )
        first = evidence[0]
        parameters = {
            "o": context.organization_id,
            "w": context.workspace_id,
            "fact": command.fact_id,
            "version": fact_version,
            "kind": command.value_kind.value,
            "source": first.source_version_id,
            "locator": first.source_locator_id,
            "decision": command.confirmation_decision_id,
            "effective": command.effective_from,
            "supersedes": fact_version - 1 if fact_version > 1 else None,
            "digest": digest_of(value),
            **value,
        }
        session.execute(
            sa.text(
                "INSERT INTO workspace.workspace_fact_versions (organization_id,workspace_id,fact_id,fact_version,value_kind,text_value,boolean_value,numeric_value,date_value,reference_value,unit_code,precision_scale,rounding_policy_version,crs_reference,measurement_authority_ref,source_version_id,source_locator_id,confirmation_decision_id,effective_from,recorded_at,supersedes_fact_version,value_digest) "
                "VALUES (:o,:w,:fact,:version,:kind,:text_value,:boolean_value,:numeric_value,:date_value,:reference_value,:unit_code,:precision_scale,:rounding_policy_version,:crs_reference,:measurement_authority_ref,:source,:locator,:decision,:effective,CURRENT_TIMESTAMP,:supersedes,:digest)"
            ),
            parameters,
        )
        for item in evidence:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.workspace_fact_evidence (organization_id,workspace_id,fact_id,fact_version,evidence_link_id,source_version_id,source_locator_id,evidence_role) "
                    "VALUES (:o,:w,:fact,:version,:evidence,:source,:locator,'material_field')"
                ),
                {
                    "o": context.organization_id,
                    "w": context.workspace_id,
                    "fact": command.fact_id,
                    "version": fact_version,
                    "evidence": item.evidence_link_id,
                    "source": item.source_version_id,
                    "locator": item.source_locator_id,
                },
            )

    @staticmethod
    def _append_audit_and_event(
        session: Session,
        context: WorkspaceContext,
        command: ConfirmCandidateCommand,
        fact_version: int,
    ) -> None:
        event_id = uuid7()
        event_payload = {
            "event_type": "FactConfirmed",
            "fact_id": str(command.fact_id),
            "fact_version": fact_version,
            "confirmation_decision_id": str(command.confirmation_decision_id),
        }
        session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_outbox (organization_id,workspace_id,outbox_record_id,event_id,aggregate_id,aggregate_version,destination,state,attempt_count,contract_key,contract_version,schema_id,schema_version,payload,payload_digest,retention_class,correlation_id,causation_id,created_at) "
                "VALUES (:o,:w,:outbox,:event,:fact,:version,'domain','pending',0,'event.domain','0.1.0','urn:asd-kontur:contracts:v0.1:schema:message','0.1.0',CAST(:payload AS jsonb),:digest,'workspace.event',:correlation,:causation,CURRENT_TIMESTAMP)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "outbox": uuid7(),
                "event": event_id,
                "fact": command.fact_id,
                "version": fact_version,
                "payload": json.dumps(event_payload, separators=(",", ":"), sort_keys=True),
                "digest": digest_of(event_payload),
                "correlation": command.correlation_id,
                "causation": command.causation_id,
            },
        )
        session.execute(
            sa.text(
                "INSERT INTO audit.workspace_records (organization_id,workspace_id,audit_record_id,audit_version,recorded_at,actor_identity_id,service_identity_id,capability,operation,outcome_code,contract_key,contract_version,policy_key,policy_version,correlation_id,causation_id,safe_message_key,retention_class,record_digest) "
                "VALUES (:o,:w,:audit,1,CURRENT_TIMESTAMP,:actor,:service,'fact.confirm','kernel.confirm-fact','confirmed','confirmation.decision','0.1.0','confirmation-policy',:policy,:correlation,:causation,'fact.confirmed','workspace.audit',:digest)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "audit": uuid7(),
                "actor": command.authority_identity_id
                if command.authority_kind == "qualified_human"
                else None,
                "service": command.authority_identity_id
                if command.authority_kind != "qualified_human"
                else None,
                "policy": command.confirmation_policy_version,
                "correlation": command.correlation_id,
                "causation": command.causation_id,
                "digest": digest_of({"operation": "kernel.confirm-fact", "outcome": "confirmed"}),
            },
        )


def _set_scope(session: Session, context: WorkspaceContext) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(context.organization_id), True),
            sa.func.set_config("asd.workspace_id", str(context.workspace_id), True),
        )
    ).one()


def candidate_value(candidate: Any) -> Any:
    return candidate.typed_value


def _typed_value(kind: FactValueKind, *, candidate_value: Any) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "text_value": None,
        "boolean_value": None,
        "numeric_value": None,
        "date_value": None,
        "reference_value": None,
        "unit_code": None,
        "precision_scale": None,
        "rounding_policy_version": None,
        "crs_reference": None,
        "measurement_authority_ref": None,
    }
    try:
        if kind is FactValueKind.TEXT and isinstance(candidate_value, str):
            empty["text_value"] = candidate_value
        elif kind is FactValueKind.BOOLEAN and isinstance(candidate_value, bool):
            empty["boolean_value"] = candidate_value
        elif kind is FactValueKind.DATE and isinstance(candidate_value, str):
            empty["date_value"] = candidate_value
        elif kind is FactValueKind.REFERENCE and isinstance(candidate_value, str):
            empty["reference_value"] = UUID(candidate_value)
        elif kind in (FactValueKind.DECIMAL_QUANTITY, FactValueKind.MEASUREMENT) and isinstance(
            candidate_value, dict
        ):
            empty["numeric_value"] = Decimal(str(candidate_value["value"]))
            empty["unit_code"] = str(candidate_value["unit"])
            empty["precision_scale"] = int(candidate_value["precision_scale"])
            empty["rounding_policy_version"] = str(candidate_value["rounding_policy_version"])
            if kind is FactValueKind.MEASUREMENT:
                empty["crs_reference"] = str(candidate_value["crs_reference"])
                empty["measurement_authority_ref"] = str(
                    candidate_value["measurement_authority_ref"]
                )
        else:
            raise ValueError
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise KernelError(
            KernelErrorCode.INVALID_QUANTITY,
            "Candidate value does not satisfy the selected typed Fact contract.",
        ) from exc
    if all(value is None for value in empty.values()):
        raise KernelError(
            KernelErrorCode.INVALID_QUANTITY,
            "Candidate value does not satisfy the selected typed Fact contract.",
        )
    return empty
