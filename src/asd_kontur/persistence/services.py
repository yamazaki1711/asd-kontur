"""Narrow transactional services required by the G-04 gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Engine

from .repositories import IdempotencyClaim
from .scope import WorkspaceContext
from .uow import WorkspaceUnitOfWork


@dataclass(frozen=True, slots=True)
class ObjectAdmission:
    object_id: uuid.UUID
    content_digest: str
    size_bytes: int
    command_id: uuid.UUID
    idempotency_key: str
    semantic_digest: str
    outbox_record_id: uuid.UUID
    event_id: uuid.UUID


class ObjectAdmissionService:
    """Atomically record a scoped object, idempotency claim, and outbox event."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def admit(
        self,
        *,
        context: WorkspaceContext,
        admission: ObjectAdmission,
    ) -> IdempotencyClaim:
        with WorkspaceUnitOfWork(self._engine, context) as unit:
            assert unit.workspaces is not None
            assert unit.messaging is not None
            claim = unit.messaging.claim_idempotency(
                handler_key="object.admit",
                idempotency_key=admission.idempotency_key,
                semantic_digest=admission.semantic_digest,
                command_id=admission.command_id,
            )
            if not claim.is_new:
                return claim
            unit.workspaces.add_object(
                object_id=admission.object_id,
                content_digest=admission.content_digest,
                size_bytes=admission.size_bytes,
            )
            unit.messaging.append_outbox(
                outbox_record_id=admission.outbox_record_id,
                event_id=admission.event_id,
                aggregate_id=admission.object_id,
                aggregate_version=1,
                payload={
                    "event_type": "object.admitted",
                    "object_id": str(admission.object_id),
                },
                payload_digest=admission.semantic_digest,
            )
            unit.messaging.complete_idempotency(
                handler_key="object.admit",
                idempotency_key=admission.idempotency_key,
                outcome_ref=f"workspace-object:{admission.object_id}:1",
            )
            return IdempotencyClaim(
                is_new=True,
                command_id=admission.command_id,
                state="accepted_completed",
                outcome_ref=f"workspace-object:{admission.object_id}:1",
            )
