from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa

from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantRepository,
)

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def test_create_conversation_persists_platform_only(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    repository = ConstructionConsultantRepository(postgres_environment.application_engine)
    conversation = repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id="platform-test-owner",
        title=" Общий   диалог  ",
    )
    assert conversation.title == "Общий диалог"
    assert conversation.message_count == 0
    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        row = (
            conn.execute(
                sa.text(
                    "SELECT conversation_id, title, created_by_identity_id "
                    "FROM platform.construction_consultant_conversations "
                    "WHERE organization_id = :o AND conversation_id = :id"
                ),
                {"o": organization_id, "id": conversation.conversation_id},
            )
            .mappings()
            .one()
        )
        assert row["conversation_id"] == conversation.conversation_id
        assert row["title"] == "Общий диалог"
        assert row["created_by_identity_id"] == "platform-test-owner"
    with postgres_environment.owner_engine.begin() as conn:
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM workspace.assistant_conversations WHERE conversation_id = :id"
            ),
            {"id": conversation.conversation_id},
        ).scalar_one()
        assert count == 0


def test_create_conversation_duplicate_identity_rolls_back(
    postgres_environment: PostgreSQLEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    conversation_id = uuid4()
    monkeypatch.setattr("asd_kontur.domain.uuid7", lambda: conversation_id)
    repository = ConstructionConsultantRepository(postgres_environment.application_engine)
    repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id="rollback-owner",
        title="Первый",
    )
    with pytest.raises(sa.exc.IntegrityError):
        repository.create_conversation(
            organization_id=organization_id,
            owner_identity_id="rollback-owner",
            title="Второй",
        )
    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM platform.construction_consultant_conversations "
                "WHERE organization_id = :o AND conversation_id = :id"
            ),
            {"o": organization_id, "id": conversation_id},
        ).scalar_one()
    assert count == 1


def test_get_conversation_re_reads_platform_identity(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    owner_identity_id = "platform-reader"
    title = "Повторное чтение"

    repository = ConstructionConsultantRepository(postgres_environment.application_engine)

    created = repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id=owner_identity_id,
        title=title,
    )

    fetched = repository.get_conversation(
        organization_id=organization_id,
        conversation_id=created.conversation_id,
        owner_identity_id=owner_identity_id,
    )

    assert fetched.conversation_id == created.conversation_id
    assert fetched.title == title
    assert fetched.created_at == created.created_at
    assert fetched.message_count == 0
