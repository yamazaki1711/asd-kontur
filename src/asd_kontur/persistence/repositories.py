"""Explicit repositories for the G-04 aggregate and ledgers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .errors import IdempotencyConflictError, OptimisticConcurrencyError
from .scope import OrganizationContext, WorkspaceContext
from .tables import (
    construction_objects,
    idempotency_records,
    inbox_receipts,
    mode_executions,
    object_links,
    organizations,
    outbox_records,
    workspace_audit_records,
    workspace_objects,
    workspace_revisions,
    workspaces,
)


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    is_new: bool
    command_id: uuid.UUID
    state: str
    outcome_ref: str | None


class OrganizationRepository:
    def __init__(self, session: Session, context: OrganizationContext) -> None:
        self._session = session
        self._context = context

    def add_organization(
        self,
        *,
        organization_id: uuid.UUID,
        display_name: str,
        external_id: str | None = None,
        retention_class: str = "organization.canonical",
    ) -> None:
        self._session.execute(
            organizations.insert().values(
                organization_id=organization_id,
                display_name=display_name,
                external_id=external_id,
                status="active",
                revision=1,
                retention_class=retention_class,
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                created_at=sa.func.current_timestamp(),
            )
        )

    def add_construction_object(
        self,
        *,
        construction_object_id: uuid.UUID,
        display_name: str,
        external_id: str | None = None,
        retention_class: str = "organization.construction-object",
    ) -> None:
        self._session.execute(
            construction_objects.insert().values(
                organization_id=self._context.organization_id,
                construction_object_id=construction_object_id,
                display_name=display_name,
                external_id=external_id,
                status="active",
                revision=1,
                retention_class=retention_class,
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                created_at=sa.func.current_timestamp(),
            )
        )

    def list_organization_ids(self) -> list[uuid.UUID]:
        return list(self._session.scalars(sa.select(organizations.c.organization_id)))

    @property
    def _identity_id(self) -> str:
        return self._context.actor_identity_id or self._context.service_identity_id or ""


class WorkspaceRepository:
    def __init__(self, session: Session, context: WorkspaceContext) -> None:
        self._session = session
        self._context = context

    def create_workspace(
        self,
        *,
        construction_object_id: uuid.UUID,
        retention_profile_key: str,
        retention_profile_version: str,
        policy_assignment_key: str,
        policy_assignment_version: str,
        rule_set_key: str,
        rule_set_version: str,
        contract_registry_version: str = "0.1.0",
    ) -> uuid.UUID:
        values = dict(
            organization_id=self._context.organization_id,
            workspace_id=self._context.workspace_id,
            construction_object_id=construction_object_id,
            lifecycle_state="provisioned",
            revision=1,
            retention_class="workspace.canonical",
            retention_profile_key=retention_profile_key,
            retention_profile_version=retention_profile_version,
            policy_assignment_key=policy_assignment_key,
            policy_assignment_version=policy_assignment_version,
            rule_set_key=rule_set_key,
            rule_set_version=rule_set_version,
            contract_registry_version=contract_registry_version,
            created_by_identity_id=self._identity_id,
            correlation_id=self._context.correlation_id,
            created_at=sa.func.current_timestamp(),
        )
        self._session.execute(workspaces.insert().values(**values))
        version_id = uuid7()
        self._session.execute(
            workspace_revisions.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                revision=1,
                workspace_version_id=version_id,
                lifecycle_state="provisioned",
                reason_code="workspace.provisioned",
                retention_profile_key=retention_profile_key,
                retention_profile_version=retention_profile_version,
                policy_assignment_key=policy_assignment_key,
                policy_assignment_version=policy_assignment_version,
                rule_set_key=rule_set_key,
                rule_set_version=rule_set_version,
                contract_registry_version=contract_registry_version,
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                causation_id=self._context.causation_id,
                recorded_at=sa.func.current_timestamp(),
            )
        )
        return version_id

    def create_mode_execution(
        self,
        *,
        mode_execution_id: uuid.UUID,
        mode: str,
        purpose: str,
        input_manifest_ref: str,
        policy_assignment_key: str,
        policy_assignment_version: str,
        rule_set_key: str,
        rule_set_version: str,
        contract_key: str = "mode.execution-request",
        contract_version: str = "0.1.0",
        schema_id: str = "urn:asd-kontur:contracts:v0.1:schema:mode-deliverable",
        schema_version: str = "0.1.0",
    ) -> None:
        self._session.execute(
            mode_executions.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                mode_execution_id=mode_execution_id,
                mode=mode,
                purpose=purpose,
                state="requested",
                revision=1,
                input_manifest_ref=input_manifest_ref,
                contract_key=contract_key,
                contract_version=contract_version,
                schema_id=schema_id,
                schema_version=schema_version,
                policy_assignment_key=policy_assignment_key,
                policy_assignment_version=policy_assignment_version,
                rule_set_key=rule_set_key,
                rule_set_version=rule_set_version,
                retention_class="workspace.mode-execution",
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                causation_id=self._context.causation_id,
                created_at=sa.func.current_timestamp(),
                updated_at=sa.func.current_timestamp(),
            )
        )

    def update_mode_state(
        self,
        *,
        mode_execution_id: uuid.UUID,
        expected_revision: int,
        new_state: str,
    ) -> int:
        statement = (
            mode_executions.update()
            .where(
                mode_executions.c.organization_id == self._context.organization_id,
                mode_executions.c.workspace_id == self._context.workspace_id,
                mode_executions.c.mode_execution_id == mode_execution_id,
                mode_executions.c.revision == expected_revision,
            )
            .values(
                state=new_state,
                revision=expected_revision + 1,
                updated_at=sa.func.current_timestamp(),
            )
            .returning(mode_executions.c.revision)
        )
        revision = self._session.scalar(statement)
        if revision is None:
            raise OptimisticConcurrencyError(f"mode execution revision is not {expected_revision}")
        return int(revision)

    def list_mode_execution_ids(self) -> list[uuid.UUID]:
        return list(self._session.scalars(sa.select(mode_executions.c.mode_execution_id)))

    def add_object(
        self,
        *,
        object_id: uuid.UUID,
        content_digest: str,
        size_bytes: int = 0,
        object_class: str = "workspace_artifact",
    ) -> None:
        self._session.execute(
            workspace_objects.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                object_id=object_id,
                object_version=1,
                object_class=object_class,
                content_digest=content_digest,
                size_bytes=size_bytes,
                media_type="application/octet-stream",
                storage_adapter_key="test.local-object-adapter",
                storage_receipt_ref="receipt.synthetic.001",
                access_capability_ref="capability.synthetic.object-read",
                classification="workspace_restricted",
                retention_class="workspace.object",
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                created_at=sa.func.current_timestamp(),
            )
        )

    def link_objects(
        self,
        *,
        link_id: uuid.UUID,
        source_object_id: uuid.UUID,
        target_object_id: uuid.UUID,
        relation_kind: str,
    ) -> None:
        self._session.execute(
            object_links.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                link_id=link_id,
                source_object_id=source_object_id,
                target_object_id=target_object_id,
                relation_kind=relation_kind,
                created_by_identity_id=self._identity_id,
                correlation_id=self._context.correlation_id,
                created_at=sa.func.current_timestamp(),
            )
        )

    @property
    def _identity_id(self) -> str:
        return self._context.actor_identity_id or self._context.service_identity_id or ""


class AuditRepository:
    def __init__(self, session: Session, context: WorkspaceContext) -> None:
        self._session = session
        self._context = context

    def append(
        self,
        *,
        audit_record_id: uuid.UUID,
        capability: str,
        operation: str,
        outcome_code: str,
        contract_key: str,
        contract_version: str,
        policy_key: str,
        policy_version: str,
        safe_message_key: str,
        record_digest: str,
        diagnostic_reference: str | None = None,
    ) -> None:
        self._session.execute(
            workspace_audit_records.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                audit_record_id=audit_record_id,
                audit_version=1,
                recorded_at=sa.func.current_timestamp(),
                actor_identity_id=self._context.actor_identity_id,
                service_identity_id=self._context.service_identity_id,
                capability=capability,
                operation=operation,
                outcome_code=outcome_code,
                contract_key=contract_key,
                contract_version=contract_version,
                policy_key=policy_key,
                policy_version=policy_version,
                correlation_id=self._context.correlation_id,
                causation_id=self._context.causation_id,
                safe_message_key=safe_message_key,
                diagnostic_reference=diagnostic_reference,
                retention_class="workspace.audit",
                record_digest=record_digest,
            )
        )


class MessagingRepository:
    def __init__(self, session: Session, context: WorkspaceContext) -> None:
        self._session = session
        self._context = context

    def claim_idempotency(
        self,
        *,
        handler_key: str,
        idempotency_key: str,
        semantic_digest: str,
        command_id: uuid.UUID,
    ) -> IdempotencyClaim:
        statement = (
            pg_insert(idempotency_records)
            .values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                handler_key=handler_key,
                idempotency_key=idempotency_key,
                semantic_digest=semantic_digest,
                command_id=command_id,
                state="accepted_pending",
                correlation_id=self._context.correlation_id,
                created_at=sa.func.current_timestamp(),
            )
            .on_conflict_do_nothing()
            .returning(idempotency_records.c.command_id)
        )
        inserted = self._session.scalar(statement)
        if inserted is not None:
            return IdempotencyClaim(True, inserted, "accepted_pending", None)
        existing = self._session.execute(
            sa.select(
                idempotency_records.c.semantic_digest,
                idempotency_records.c.command_id,
                idempotency_records.c.state,
                idempotency_records.c.outcome_ref,
            ).where(
                idempotency_records.c.organization_id == self._context.organization_id,
                idempotency_records.c.workspace_id == self._context.workspace_id,
                idempotency_records.c.handler_key == handler_key,
                idempotency_records.c.idempotency_key == idempotency_key,
            )
        ).one()
        if existing.semantic_digest != semantic_digest:
            raise IdempotencyConflictError("idempotency key reused with a different digest")
        return IdempotencyClaim(
            False,
            existing.command_id,
            existing.state,
            existing.outcome_ref,
        )

    def complete_idempotency(
        self,
        *,
        handler_key: str,
        idempotency_key: str,
        outcome_ref: str,
    ) -> None:
        self._session.execute(
            idempotency_records.update()
            .where(
                idempotency_records.c.organization_id == self._context.organization_id,
                idempotency_records.c.workspace_id == self._context.workspace_id,
                idempotency_records.c.handler_key == handler_key,
                idempotency_records.c.idempotency_key == idempotency_key,
            )
            .values(
                state="accepted_completed",
                outcome_ref=outcome_ref,
                completed_at=sa.func.current_timestamp(),
            )
        )

    def append_outbox(
        self,
        *,
        outbox_record_id: uuid.UUID,
        event_id: uuid.UUID,
        aggregate_id: uuid.UUID,
        aggregate_version: int,
        payload: Mapping[str, Any],
        payload_digest: str,
        contract_key: str = "event.integration",
        contract_version: str = "0.1.0",
        schema_id: str = "urn:asd-kontur:contracts:v0.1:schema:message",
        schema_version: str = "0.1.0",
    ) -> None:
        self._session.execute(
            outbox_records.insert().values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                outbox_record_id=outbox_record_id,
                event_id=event_id,
                aggregate_id=aggregate_id,
                aggregate_version=aggregate_version,
                destination="status_projection.synthetic",
                state="pending",
                attempt_count=0,
                contract_key=contract_key,
                contract_version=contract_version,
                schema_id=schema_id,
                schema_version=schema_version,
                payload=dict(payload),
                payload_digest=payload_digest,
                retention_class="workspace.outbox",
                correlation_id=self._context.correlation_id,
                causation_id=self._context.causation_id,
                created_at=sa.func.current_timestamp(),
            )
        )

    def record_inbox(
        self,
        *,
        consumer_key: str,
        message_id: uuid.UUID,
        payload_digest: str,
        contract_key: str,
        contract_version: str,
        schema_id: str,
        schema_version: str,
    ) -> bool:
        statement = (
            pg_insert(inbox_receipts)
            .values(
                organization_id=self._context.organization_id,
                workspace_id=self._context.workspace_id,
                consumer_key=consumer_key,
                message_id=message_id,
                payload_digest=payload_digest,
                outcome="accepted",
                attempt_count=1,
                contract_key=contract_key,
                contract_version=contract_version,
                schema_id=schema_id,
                schema_version=schema_version,
                correlation_id=self._context.correlation_id,
                received_at=sa.func.current_timestamp(),
            )
            .on_conflict_do_nothing()
            .returning(inbox_receipts.c.message_id)
        )
        return self._session.scalar(statement) is not None
