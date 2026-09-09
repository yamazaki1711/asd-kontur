from uuid import uuid5

import pytest
import sqlalchemy as sa

from asd_kontur.application_spine.postgres import OWNER_ORGANIZATION_NAMESPACE
from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantPersistenceError,
    ConstructionConsultantRepository,
)
from asd_kontur.assistant.construction_consultant_service import ConstructionConsultantService

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def test_construction_consultant_service_flow(postgres_environment: PostgreSQLEnvironment) -> None:
    owner_a = "platform-service-owner-a"
    owner_b = "platform-service-owner-b"

    repository = ConstructionConsultantRepository(postgres_environment.application_engine)
    service = ConstructionConsultantService(repository)

    conversation = service.create_conversation(owner_a, " Общая   история  ")
    expected_organization = uuid5(OWNER_ORGANIZATION_NAMESPACE, owner_a)

    repository.append_message(
        expected_organization,
        conversation.conversation_id,
        owner_a,
        "assistant",
        "Подтверждённый ответ",
    )

    listed_conversations = service.list_conversations(owner_a)
    assert len(listed_conversations) == 1
    listed_conversation = listed_conversations[0]
    assert listed_conversation.conversation_id == conversation.conversation_id
    assert listed_conversation.title == "Общая история"
    assert listed_conversation.message_count == 1

    messages = service.messages(owner_a, conversation.conversation_id)
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "Подтверждённый ответ"

    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(expected_organization), True))
        )
        row = (
            conn.execute(
                sa.text(
                    "SELECT organization_id, created_by_identity_id "
                    "FROM platform.construction_consultant_conversations "
                    "WHERE organization_id = :organization_id "
                    "AND conversation_id = :conversation_id"
                ),
                {
                    "organization_id": expected_organization,
                    "conversation_id": conversation.conversation_id,
                },
            )
            .mappings()
            .one()
        )

    assert row is not None
    assert row["organization_id"] == expected_organization
    assert row["created_by_identity_id"] == owner_a

    assert service.list_conversations(owner_b) == ()

    with pytest.raises(ConstructionConsultantPersistenceError) as exc_info:
        service.messages(owner_b, conversation.conversation_id)
    assert exc_info.value.code == "construction_consultant_conversation_not_found"
