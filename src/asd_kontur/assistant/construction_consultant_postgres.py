from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest


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
    request_id: UUID | None
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

    def get_conversation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
    ) -> ConstructionConsultantConversation:
        if not owner_identity_id or not owner_identity_id.strip():
            raise ValueError("owner_identity_id must not be blank")

        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)
            row = session.execute(
                sa.text(
                    """
                    SELECT
                        c.conversation_id,
                        c.title,
                        c.created_at,
                        (
                            SELECT count(*)
                            FROM platform.construction_consultant_messages m
                            WHERE m.organization_id = :organization_id
                              AND m.conversation_id = c.conversation_id
                        ) AS message_count
                    FROM platform.construction_consultant_conversations c
                    WHERE c.organization_id = :organization_id
                      AND c.conversation_id = :conversation_id
                      AND c.created_by_identity_id = :owner_identity_id
                    """
                ),
                {
                    "organization_id": organization_id,
                    "conversation_id": conversation_id,
                    "owner_identity_id": owner_identity_id,
                },
            ).fetchone()

        if row is None:
            raise ConstructionConsultantPersistenceError(
                "construction_consultant_conversation_not_found",
                "construction_consultant_conversation_not_found",
            )

        return ConstructionConsultantConversation(
            conversation_id=row[0],
            title=row[1],
            created_at=row[2],
            message_count=row[3],
        )

    def list_conversations(
        self,
        organization_id: UUID,
        owner_identity_id: str,
    ) -> tuple[ConstructionConsultantConversation, ...]:
        if not owner_identity_id or not owner_identity_id.strip():
            raise ValueError("owner_identity_id must not be blank")

        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)
            sql = sa.text(
                """
                SELECT
                    c.conversation_id,
                    c.title,
                    c.created_at,
                    (
                        SELECT COUNT(*)
                        FROM platform.construction_consultant_messages m
                        WHERE m.organization_id = :organization_id
                          AND m.conversation_id = c.conversation_id
                    ) AS message_count
                FROM platform.construction_consultant_conversations c
                WHERE c.organization_id = :organization_id
                  AND c.created_by_identity_id = :owner_identity_id
                ORDER BY c.created_at DESC, c.conversation_id
                """
            )
            rows = (
                session.execute(
                    sql,
                    {
                        "organization_id": organization_id,
                        "owner_identity_id": owner_identity_id,
                    },
                )
                .mappings()
                .all()
            )

        return tuple(
            ConstructionConsultantConversation(
                conversation_id=row["conversation_id"],
                title=row["title"],
                created_at=row["created_at"],
                message_count=row["message_count"],
            )
            for row in rows
        )

    def append_message(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        role: str,
        content: str,
        sources: tuple[dict[str, Any], ...] = (),
        model_identity: str | None = None,
        model_profile_version: str | None = None,
        request_id: UUID | None = None,
    ) -> ConstructionConsultantMessage:
        if not owner_identity_id or not owner_identity_id.strip():
            raise ValueError("construction_consultant_owner_identity_invalid")
        if role not in ("user", "assistant"):
            raise ValueError("construction_consultant_role_invalid")
        if not content or not content.strip():
            raise ValueError("construction_consultant_content_invalid")
        if not isinstance(sources, tuple) or not all(isinstance(s, dict) for s in sources):
            raise ValueError("construction_consultant_sources_invalid")
        if request_id is not None and not isinstance(request_id, UUID):
            raise ValueError("construction_consultant_request_id_invalid")

        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)

            conv_row = (
                session.execute(
                    sa.text(
                        """
                    SELECT conversation_id
                    FROM platform.construction_consultant_conversations
                    WHERE organization_id = :org_id
                      AND conversation_id = :conv_id
                      AND created_by_identity_id = :owner_id
                    FOR UPDATE
                    """
                    ),
                    {
                        "org_id": organization_id,
                        "conv_id": conversation_id,
                        "owner_id": owner_identity_id,
                    },
                )
                .mappings()
                .one_or_none()
            )

            if conv_row is None:
                raise ConstructionConsultantPersistenceError(
                    "construction_consultant_conversation_not_found",
                    "construction_consultant_conversation_not_found",
                )

            ordinal_row = session.execute(
                sa.text(
                    """
                    SELECT COALESCE(MAX(message_ordinal), 0) + 1
                    FROM platform.construction_consultant_messages
                    WHERE organization_id = :org_id
                      AND conversation_id = :conv_id
                    """
                ),
                {
                    "org_id": organization_id,
                    "conv_id": conversation_id,
                },
            ).scalar_one()

            ordinal = int(ordinal_row)

            from asd_kontur.domain import uuid7

            message_id = uuid7()

            digest_input = {
                "conversation_id": str(conversation_id),
                "ordinal": ordinal,
                "role": role,
                "content": content,
                "sources": sources,
            }
            content_digest = semantic_digest(digest_input)

            session.execute(
                sa.text(
                    """
                    INSERT INTO platform.construction_consultant_messages (
                        organization_id,
                        message_id,
                        conversation_id,
                        request_id,
                        message_ordinal,
                        role,
                        content,
                        sources,
                        model_identity,
                        model_profile_version,
                        content_digest
                    )
                    VALUES (
                        :org_id,
                        :msg_id,
                        :conv_id,
                        :request_id,
                        :ordinal,
                        :role,
                        :content,
                        CAST(:sources AS jsonb),
                        :model_identity,
                        :model_profile_version,
                        :content_digest
                    )
                    """
                ),
                {
                    "org_id": organization_id,
                    "msg_id": message_id,
                    "conv_id": conversation_id,
                    "request_id": request_id,
                    "ordinal": ordinal,
                    "role": role,
                    "content": content,
                    "sources": json.dumps(sources, ensure_ascii=False),
                    "model_identity": model_identity,
                    "model_profile_version": model_profile_version,
                    "content_digest": content_digest,
                },
            )

            msg_row = (
                session.execute(
                    sa.text(
                        """
                    SELECT
                        message_id,
                        conversation_id,
                        request_id,
                        message_ordinal,
                        role,
                        content,
                        sources,
                        model_identity,
                        model_profile_version,
                        created_at
                    FROM platform.construction_consultant_messages
                    WHERE organization_id = :org_id
                      AND message_id = :msg_id
                    """
                    ),
                    {
                        "org_id": organization_id,
                        "msg_id": message_id,
                    },
                )
                .mappings()
                .one()
            )

            return ConstructionConsultantMessage(
                message_id=msg_row["message_id"],
                conversation_id=msg_row["conversation_id"],
                request_id=msg_row["request_id"],
                ordinal=int(msg_row["message_ordinal"]),
                role=msg_row["role"],
                content=msg_row["content"],
                sources=tuple(msg_row["sources"]),
                model_identity=msg_row["model_identity"],
                model_profile_version=msg_row["model_profile_version"],
                created_at=msg_row["created_at"],
            )

    def messages(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
    ) -> tuple[ConstructionConsultantMessage, ...]:
        self.get_conversation(organization_id, conversation_id, owner_identity_id)
        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)
            rows = (
                session.execute(
                    sa.text(
                        """
                        SELECT
                            organization_id,
                            message_id,
                            conversation_id,
                            request_id,
                            message_ordinal,
                            role,
                            content,
                            sources,
                            model_identity,
                            model_profile_version,
                            created_at
                        FROM platform.construction_consultant_messages
                        WHERE organization_id = :organization_id
                          AND conversation_id = :conversation_id
                        ORDER BY message_ordinal ASC
                        """
                    ),
                    {
                        "organization_id": organization_id,
                        "conversation_id": conversation_id,
                    },
                )
                .mappings()
                .all()
            )
            return tuple(
                ConstructionConsultantMessage(
                    message_id=row["message_id"],
                    conversation_id=row["conversation_id"],
                    request_id=row["request_id"],
                    ordinal=int(row["message_ordinal"]),
                    role=row["role"],
                    content=row["content"],
                    sources=tuple(row["sources"]),
                    model_identity=row["model_identity"],
                    model_profile_version=row["model_profile_version"],
                    created_at=row["created_at"],
                )
                for row in rows
            )

    def messages_for_request(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
        request_id: UUID,
    ) -> tuple[ConstructionConsultantMessage, ...]:
        self.get_conversation(organization_id, conversation_id, owner_identity_id)
        with Session(self._engine) as session, session.begin():
            self._scope(session, organization_id)
            rows = (
                session.execute(
                    sa.text(
                        "SELECT message_id, conversation_id, request_id, message_ordinal, role, "
                        "content, sources, model_identity, model_profile_version, created_at "
                        "FROM platform.construction_consultant_messages "
                        "WHERE organization_id=:organization_id "
                        "AND conversation_id=:conversation_id "
                        "AND request_id=:request_id ORDER BY message_ordinal"
                    ),
                    {
                        "organization_id": organization_id,
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                    },
                )
                .mappings()
                .all()
            )
        return tuple(
            ConstructionConsultantMessage(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                request_id=row["request_id"],
                ordinal=int(row["message_ordinal"]),
                role=row["role"],
                content=row["content"],
                sources=tuple(row["sources"]),
                model_identity=row["model_identity"],
                model_profile_version=row["model_profile_version"],
                created_at=row["created_at"],
            )
            for row in rows
        )
