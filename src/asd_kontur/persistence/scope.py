"""Explicit transaction scopes and provenance propagated to repositories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrganizationContext:
    organization_id: uuid.UUID
    actor_identity_id: str | None
    service_identity_id: str | None
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.actor_identity_id is None and self.service_identity_id is None:
            raise ValueError("actor_identity_id or service_identity_id is required")


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    actor_identity_id: str | None
    service_identity_id: str | None
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.actor_identity_id is None and self.service_identity_id is None:
            raise ValueError("actor_identity_id or service_identity_id is required")
