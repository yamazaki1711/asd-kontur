"""Transport-neutral professional assistant values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AssistantMode(StrEnum):
    TENDER = "Tender"
    SUPPORT = "Support"
    AUDIT = "Audit"
    RESTORATION = "Restoration"


class TurnState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class Conversation:
    conversation_id: UUID
    workspace_id: UUID
    title: str
    created_at: datetime
    latest_mode: AssistantMode | None
    message_count: int


@dataclass(frozen=True, slots=True)
class Message:
    message_id: UUID
    conversation_id: UUID
    turn_id: UUID
    ordinal: int
    role: str
    content: str
    sources: tuple[dict[str, Any], ...]
    action_proposals: tuple[dict[str, Any], ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Turn:
    turn_id: UUID
    conversation_id: UUID
    ordinal: int
    mode: AssistantMode
    question: str
    state: TurnState
    failure_code: str | None
    project_definition_id: UUID | None
    project_definition_version: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ClaimedTurn:
    organization_id: UUID
    workspace_id: UUID
    turn_id: UUID
    conversation_id: UUID
    mode: AssistantMode
    question: str
    requested_by_identity_id: str
    attempt_number: int
    lease_generation: int


@dataclass(frozen=True, slots=True)
class TurnEvent:
    sequence: int
    event_type: str
    payload: dict[str, Any]
    recorded_at: datetime
