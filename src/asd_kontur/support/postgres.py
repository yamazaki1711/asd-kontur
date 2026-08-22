"""Narrow transactional persistence service for the WP-13 Support process."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7
from asd_kontur.harness.models import digest_of
from asd_kontur.persistence.scope import WorkspaceContext

from .errors import SupportError, SupportErrorCode
from .models import ProfessionalAuthority, SupportScope, SupportState
from .process import SupportCommand, SupportCommandOutcome, SupportProcessStateMachine


@dataclass(frozen=True, slots=True)
class StartSupportProcess:
    command_id: UUID
    scope: SupportScope
    source_class_allowlist: tuple[str, ...]
    input_manifest_digest: str
    authority: ProfessionalAuthority
    idempotency_key: str
    correlation_id: UUID
    causation_id: UUID

    @property
    def semantic_digest(self) -> str:
        return digest_of(self)


class PostgresSupportProcess:
    """Persist accepted Support transitions with audit/outbox atomically."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._machine = SupportProcessStateMachine()

    def start(
        self, *, context: WorkspaceContext, command: StartSupportProcess
    ) -> SupportCommandOutcome:
        if command.authority.capability != "support.scope.configure":
            raise SupportError(
                SupportErrorCode.AUTHORITY_DENIED,
                "Support scope configuration requires its exact professional capability.",
            )
        if command.scope.organization_id != context.organization_id or (
            command.scope.workspace_id != context.workspace_id
        ):
            raise SupportError(SupportErrorCode.SCOPE_VIOLATION, "Support scope mismatch.")
        now = datetime.now(UTC)
        try:
            with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
                with session.begin():
                    _set_scope(session, context)
                    replay = self._claim_idempotency(
                        session,
                        context,
                        handler="support.configure",
                        idempotency_key=command.idempotency_key,
                        semantic_digest=command.semantic_digest,
                        command_id=command.command_id,
                        correlation_id=command.correlation_id,
                    )
                    if replay is not None:
                        return self._load_replay(replay)
                    self._verify_grant(session, context, command.authority, now)
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.support_processes "
                            "(organization_id,workspace_id,support_process_id,mode_execution_id,state,revision,process_definition_version,rule_set_version_id,authority_profile_version,contract_registry_version,input_manifest_digest,current_fingerprint,correlation_id,causation_id,created_at,updated_at) "
                            "VALUES (:o,:w,:process,:mode,'scope_configured',1,:definition,:ruleset,:authority_profile,:contracts,:manifest,:fingerprint,:correlation,:causation,:now,:now)"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.scope.support_process_id,
                            "mode": command.scope.mode_execution_id,
                            "definition": command.scope.process_definition_version,
                            "ruleset": command.scope.rule_set_version_id,
                            "authority_profile": command.scope.authority_profile_version,
                            "contracts": command.scope.contract_registry_version,
                            "manifest": command.input_manifest_digest,
                            "fingerprint": command.scope.fingerprint,
                            "correlation": command.correlation_id,
                            "causation": command.causation_id,
                            "now": now,
                        },
                    )
                    session.execute(
                        sa.text(
                            "INSERT INTO workspace.support_scope_versions "
                            "(organization_id,workspace_id,support_process_id,scope_version,deliverable_scope,source_class_allowlist,policy_versions,classification,purpose,authority_profile_version,rule_set_version_id,scope_digest,recorded_at) "
                            "VALUES (:o,:w,:process,1,:deliverables,:sources,:policies,:classification,:purpose,:authority_profile,:ruleset,:digest,:now)"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.scope.support_process_id,
                            "deliverables": list(command.scope.deliverable_scope),
                            "sources": list(command.source_class_allowlist),
                            "policies": list(command.scope.policy_versions),
                            "classification": command.scope.classification,
                            "purpose": command.scope.purpose,
                            "authority_profile": command.scope.authority_profile_version,
                            "ruleset": command.scope.rule_set_version_id,
                            "digest": command.scope.fingerprint,
                            "now": now,
                        },
                    )
                    event_id = uuid7()
                    self._append_event(
                        session,
                        context,
                        command.scope.support_process_id,
                        1,
                        event_id,
                        "SupportScopeConfigured",
                        command.scope.fingerprint,
                        command.correlation_id,
                        command.command_id,
                    )
                    self._append_audit(
                        session,
                        context,
                        command.authority,
                        command.correlation_id,
                        command.command_id,
                        "ConfigureSupportScope",
                        "accepted_completed",
                        command.semantic_digest,
                    )
                    self._complete_idempotency(
                        session,
                        context,
                        "support.configure",
                        command.idempotency_key,
                        self._outcome_reference(
                            SupportCommandOutcome(
                                "accepted_completed",
                                1,
                                SupportState.SCOPE_CONFIGURED,
                                None,
                                "OK",
                            )
                        ),
                    )
                    return SupportCommandOutcome(
                        "accepted_completed",
                        1,
                        SupportState.SCOPE_CONFIGURED,
                        None,
                        "OK",
                    )
        except SupportError:
            raise
        except sa.exc.DBAPIError as exc:
            raise _map_database_error(exc) from exc

    def execute(
        self,
        *,
        context: WorkspaceContext,
        command: SupportCommand,
        blocker_codes: tuple[str, ...] = (),
    ) -> SupportCommandOutcome:
        now = datetime.now(UTC)
        try:
            with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
                with session.begin():
                    _set_scope(session, context)
                    replay = self._claim_idempotency(
                        session,
                        context,
                        handler="support.command",
                        idempotency_key=command.idempotency_key,
                        semantic_digest=command.semantic_digest,
                        command_id=command.command_id,
                        correlation_id=command.correlation_id,
                    )
                    if replay is not None:
                        return self._load_replay(replay)
                    self._verify_grant(session, context, command.authority, now)
                    row = session.execute(
                        sa.text(
                            "SELECT state,revision FROM workspace.support_processes WHERE organization_id=:o "
                            "AND workspace_id=:w AND support_process_id=:process FOR UPDATE"
                        ),
                        {
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.support_process_id,
                        },
                    ).one_or_none()
                    if row is None:
                        raise SupportError(
                            SupportErrorCode.SCOPE_VIOLATION,
                            "Support process does not exist in this workspace.",
                        )
                    outcome = self._machine.execute(
                        current_state=SupportState(row.state),
                        current_revision=int(row.revision),
                        command=command,
                        blockers=blocker_codes,
                    )
                    if outcome.event is None:
                        self._append_audit(
                            session,
                            context,
                            command.authority,
                            command.correlation_id,
                            command.command_id,
                            command.command_type,
                            "rejected",
                            command.semantic_digest,
                        )
                        self._complete_idempotency(
                            session,
                            context,
                            "support.command",
                            command.idempotency_key,
                            self._outcome_reference(outcome),
                        )
                        return outcome
                    session.execute(
                        sa.select(
                            sa.func.set_config(
                                "asd.support_operation_id", str(command.command_id), True
                            )
                        )
                    )
                    session.execute(
                        sa.text(
                            "UPDATE workspace.support_processes SET state=:state,revision=:revision,current_fingerprint=:fingerprint,updated_at=:now "
                            "WHERE organization_id=:o AND workspace_id=:w AND support_process_id=:process AND revision=:expected"
                        ),
                        {
                            "state": outcome.state,
                            "revision": outcome.revision,
                            "fingerprint": outcome.fingerprint,
                            "now": now,
                            "o": context.organization_id,
                            "w": context.workspace_id,
                            "process": command.support_process_id,
                            "expected": command.expected_revision,
                        },
                    )
                    event_id = uuid7()
                    self._append_event(
                        session,
                        context,
                        command.support_process_id,
                        outcome.revision,
                        event_id,
                        outcome.event.event_type,
                        command.semantic_digest,
                        command.correlation_id,
                        command.command_id,
                    )
                    self._append_audit(
                        session,
                        context,
                        command.authority,
                        command.correlation_id,
                        command.command_id,
                        command.command_type,
                        "accepted_completed",
                        command.semantic_digest,
                    )
                    self._complete_idempotency(
                        session,
                        context,
                        "support.command",
                        command.idempotency_key,
                        self._outcome_reference(outcome),
                    )
                    return outcome
        except SupportError:
            raise
        except sa.exc.DBAPIError as exc:
            raise _map_database_error(exc) from exc

    @staticmethod
    def _claim_idempotency(
        session: Session,
        context: WorkspaceContext,
        *,
        handler: str,
        idempotency_key: str,
        semantic_digest: str,
        command_id: UUID,
        correlation_id: UUID,
    ) -> str | None:
        inserted = session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_idempotency "
                "(organization_id,workspace_id,handler_key,idempotency_key,semantic_digest,command_id,state,correlation_id,created_at) "
                "VALUES (:o,:w,:handler,:key,:digest,:command,'accepted_pending',:correlation,CURRENT_TIMESTAMP) "
                "ON CONFLICT DO NOTHING RETURNING command_id"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "handler": handler,
                "key": idempotency_key,
                "digest": semantic_digest,
                "command": command_id,
                "correlation": correlation_id,
            },
        ).one_or_none()
        if inserted is not None:
            return None
        existing = session.execute(
            sa.text(
                "SELECT semantic_digest,outcome_ref FROM messaging.workspace_idempotency WHERE organization_id=:o "
                "AND workspace_id=:w AND handler_key=:handler AND idempotency_key=:key FOR UPDATE"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "handler": handler,
                "key": idempotency_key,
            },
        ).one()
        if existing.semantic_digest != semantic_digest:
            raise SupportError(
                SupportErrorCode.IDEMPOTENCY_CONFLICT,
                "The idempotency key is bound to another semantic command.",
            )
        if not existing.outcome_ref:
            raise SupportError(
                SupportErrorCode.IDEMPOTENCY_CONFLICT,
                "The original Support command requires reconciliation.",
            )
        return str(existing.outcome_ref)

    @staticmethod
    def _verify_grant(
        session: Session,
        context: WorkspaceContext,
        authority: ProfessionalAuthority,
        at: datetime,
    ) -> None:
        found = session.scalar(
            sa.text(
                "SELECT count(*) FROM workspace.support_professional_grants WHERE organization_id=:o "
                "AND workspace_id=:w AND grant_id=:grant AND grant_version=:version "
                "AND human_identity_id=:identity AND capability=:capability AND status='active' "
                "AND effective_from<=:at AND (effective_until IS NULL OR effective_until>:at)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "grant": authority.grant_id,
                "version": authority.grant_version,
                "identity": authority.identity_id,
                "capability": authority.capability,
                "at": at,
            },
        )
        if found != 1:
            raise SupportError(
                SupportErrorCode.AUTHORITY_DENIED,
                "The exact Support professional grant is unavailable or inactive.",
            )

    @staticmethod
    def _load_replay(outcome_reference: str) -> SupportCommandOutcome:
        stored = json.loads(outcome_reference)
        return SupportCommandOutcome(
            "duplicate_completed",
            int(stored["revision"]),
            SupportState(stored["state"]),
            None,
            str(stored["reason_code"]),
        )

    @staticmethod
    def _outcome_reference(outcome: SupportCommandOutcome) -> str:
        return json.dumps(
            {
                "revision": outcome.revision,
                "state": outcome.state,
                "reason_code": outcome.reason_code,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _complete_idempotency(
        session: Session,
        context: WorkspaceContext,
        handler: str,
        idempotency_key: str,
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
                "handler": handler,
                "key": idempotency_key,
                "outcome": outcome_ref,
            },
        )

    @staticmethod
    def _append_event(
        session: Session,
        context: WorkspaceContext,
        aggregate_id: UUID,
        aggregate_version: int,
        event_id: UUID,
        event_type: str,
        payload_digest: str,
        correlation_id: UUID,
        causation_id: UUID,
    ) -> None:
        payload: dict[str, Any] = {
            "event_type": event_type,
            "support_process_id": str(aggregate_id),
            "aggregate_version": aggregate_version,
            "payload_fingerprint": payload_digest,
        }
        session.execute(
            sa.text(
                "INSERT INTO messaging.workspace_outbox "
                "(organization_id,workspace_id,outbox_record_id,event_id,aggregate_id,aggregate_version,destination,state,attempt_count,contract_key,contract_version,schema_id,schema_version,payload,payload_digest,retention_class,correlation_id,causation_id,created_at) "
                "VALUES (:o,:w,:outbox,:event,:aggregate,:version,'support-domain','pending',0,'support.process-event','1.3.0','urn:asd-kontur:contracts:v1.3:schema:support','1.3.0',CAST(:payload AS jsonb),:digest,'workspace_domain_event',:correlation,:causation,CURRENT_TIMESTAMP)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "outbox": uuid7(),
                "event": event_id,
                "aggregate": aggregate_id,
                "version": aggregate_version,
                "payload": json.dumps(payload),
                "digest": digest_of(payload),
                "correlation": correlation_id,
                "causation": causation_id,
            },
        )

    @staticmethod
    def _append_audit(
        session: Session,
        context: WorkspaceContext,
        authority: ProfessionalAuthority,
        correlation_id: UUID,
        causation_id: UUID,
        operation: object,
        outcome: str,
        semantic_digest: str,
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO audit.workspace_records "
                "(organization_id,workspace_id,audit_record_id,audit_version,recorded_at,actor_identity_id,service_identity_id,capability,operation,outcome_code,contract_key,contract_version,policy_key,policy_version,correlation_id,causation_id,safe_message_key,diagnostic_reference,retention_class,record_digest) "
                "VALUES (:o,:w,:audit,1,CURRENT_TIMESTAMP,:actor,'service:support',:capability,:operation,:outcome,'support.command','1.3.0','support.policy','development-1.0.0',:correlation,:causation,'support.operation.recorded',NULL,'workspace_content_minimal',:digest)"
            ),
            {
                "o": context.organization_id,
                "w": context.workspace_id,
                "audit": uuid7(),
                "actor": authority.identity_id,
                "capability": authority.capability,
                "operation": str(operation),
                "outcome": outcome,
                "correlation": correlation_id,
                "causation": causation_id,
                "digest": digest_of(
                    {
                        "operation": str(operation),
                        "outcome": outcome,
                        "semantic_digest": semantic_digest,
                    }
                ),
            },
        )


def _set_scope(session: Session, context: WorkspaceContext) -> None:
    session.execute(
        sa.select(sa.func.set_config("asd.organization_id", str(context.organization_id), True))
    )
    session.execute(
        sa.select(sa.func.set_config("asd.workspace_id", str(context.workspace_id), True))
    )


def _map_database_error(exc: sa.exc.DBAPIError) -> SupportError:
    message = str(exc.orig).lower()
    if "write fenced" in message:
        return SupportError(
            SupportErrorCode.WORKSPACE_FENCED,
            "The workspace lifecycle fence rejected the Support write.",
        )
    if "row-level security" in message or "foreign key" in message:
        return SupportError(
            SupportErrorCode.SCOPE_VIOLATION,
            "PostgreSQL rejected a cross-scope Support reference.",
        )
    if "support state changes require" in message:
        return SupportError(
            SupportErrorCode.AUTHORITY_DENIED,
            "Support state changes require the governed service path.",
        )
    return SupportError(
        SupportErrorCode.INVALID_STATE,
        "PostgreSQL rejected the Support transition.",
    )
