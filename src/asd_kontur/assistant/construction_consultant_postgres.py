from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session


class ConstructionConsultantPersistenceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ConstructionConsultantConversation:
    conversation_id: UUID
    title: str
    created_at: datetime
    message_count: int


@dataclass(frozen=True, slots=True)
class ConstructionConsultantMessage:
    message_id: UUID
    conversation_id: UUID
    ordinal: int
    role: str
    content: str
    sources: tuple[dict[str, Any], ...]
    model_identity: str | None
    model_profile_version: str | None
    created_at: datetime


class ConstructionConsultantRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine

    def _scope(self, session: Session, organization_id: UUID) -> None:
        if not isinstance(organization_id, UUID):
            raise ValueError("construction_consultant_invalid_organization_id")
        session.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )

    def create_conversation(
        self,
        organization_id: UUID,
        owner_identity_id: str,
        title: str,
    ) -> ConstructionConsultantConversation:
        from asd_kontur.domain import uuid7

        if not owner_identity_id or not owner_identity_id.strip():
            raise ValueError("owner_identity_id must not be blank")

        normalized_title = " ".join(title.split())
        if not 1 <= len(normalized_title) <= 160:
            raise ValueError("title must between 1 and 160 characters")

        conversation_id = uuid7()

        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)
            session.execute(
                sa.text(
                    "INSERT INTO platform.construction_consultant_conversations "
                    "(organization_id, conversation_id, created_by_identity_id, title) "
                    "VALUES (:o, :id, :owner, :title)"
                ),
                {
                    "o": organization_id,
                    "id": conversation_id,
                    "owner": owner_identity_id,
                    "title": normalized_title,
                },
            )
            row = (
                session.execute(
                    sa.text(
                        "SELECT c.created_at "
                        "FROM platform.construction_consultant_conversations c "
                        "WHERE c.organization_id = :o "
                        "AND c.conversation_id = :id "
                        "AND c.created_by_identity_id = :owner"
                    ),
                    {
                        "o": organization_id,
                        "id": conversation_id,
                        "owner": owner_identity_id,
                    },
                )
                .mappings()
                .one_or_none()
            )

        if row is None:
            raise ConstructionConsultantPersistenceError(
                "construction_consultant_conversation_not_found",
                "construction_consultant_conversation_not_found",
            )

        return ConstructionConsultantConversation(
            conversation_id=conversation_id,
            title=normalized_title,
            created_at=row["created_at"],
            message_count=0,
        )
