from __future__ import annotations

import threading
from uuid import uuid4

import pytest
import sqlalchemy as sa

from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantMessage,
    ConstructionConsultantPersistenceError,
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


def test_append_message_persists_and_retrieves(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    owner_identity_id = "platform-reader"
    title = "Тест добавления сообщения"
    content = "Проверка хранения"
    sources = ({"kind": "test"},)
    model_identity = "local-test"
    model_profile_version = "v1"

    repository = ConstructionConsultantRepository(postgres_environment.application_engine)

    created = repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id=owner_identity_id,
        title=title,
    )

    message = repository.append_message(
        organization_id=organization_id,
        conversation_id=created.conversation_id,
        owner_identity_id=owner_identity_id,
        role="user",
        content=content,
        sources=sources,
        model_identity=model_identity,
        model_profile_version=model_profile_version,
    )

    assert message.message_id is not None
    assert message.conversation_id == created.conversation_id
    assert message.ordinal == 1
    assert message.role == "user"
    assert message.content == content
    assert message.sources == sources
    assert message.model_identity == model_identity
    assert message.model_profile_version == model_profile_version
    assert message.created_at is not None

    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        row = (
            conn.execute(
                sa.text(
                    "SELECT organization_id, message_id, conversation_id, message_ordinal, role, content, sources, model_identity, model_profile_version, created_at "  # noqa: E501
                    "FROM platform.construction_consultant_messages "
                    "WHERE organization_id = :o AND message_id = :id"
                ),
                {"o": organization_id, "id": message.message_id},
            )
            .mappings()
            .one()
        )

    assert row["organization_id"] == organization_id
    assert row["message_id"] == message.message_id
    assert row["conversation_id"] == created.conversation_id
    assert row["message_ordinal"] == 1
    assert row["role"] == "user"
    assert row["content"] == content
    assert tuple(row["sources"]) == sources
    assert row["model_identity"] == model_identity
    assert row["model_profile_version"] == model_profile_version
    assert row["created_at"] is not None

    fetched = repository.get_conversation(
        organization_id=organization_id,
        conversation_id=created.conversation_id,
        owner_identity_id=owner_identity_id,
    )

    assert fetched.message_count == 1


def test_construction_consultant_message_isolation(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    owner_identity_id = "message-owner"

    repository = ConstructionConsultantRepository(postgres_environment.application_engine)

    created = repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id=owner_identity_id,
        title="Изоляция сообщений",
    )

    with pytest.raises(ConstructionConsultantPersistenceError) as exc_info_foreign:
        repository.append_message(
            organization_id=organization_id,
            conversation_id=created.conversation_id,
            owner_identity_id="other-owner",
            role="user",
            content="Проверка доступа",
        )
    assert exc_info_foreign.value.code == "construction_consultant_conversation_not_found"

    missing_conversation_id = uuid4()
    with pytest.raises(ConstructionConsultantPersistenceError) as exc_info_missing:
        repository.append_message(
            organization_id=organization_id,
            conversation_id=missing_conversation_id,
            owner_identity_id=owner_identity_id,
            role="user",
            content="Проверка доступа",
        )
    assert exc_info_missing.value.code == "construction_consultant_conversation_not_found"

    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM platform.construction_consultant_messages "
                "WHERE organization_id = :o AND conversation_id = :c"
            ),
            {"o": organization_id, "c": created.conversation_id},
        ).scalar_one()

    assert count == 0


def test_append_message_integrity_error_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    repository = ConstructionConsultantRepository(postgres_environment.application_engine)
    conversation = repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id="rollback-owner",
        title="Откат сообщения",
    )
    first_message = repository.append_message(
        organization_id=organization_id,
        conversation_id=conversation.conversation_id,
        owner_identity_id="rollback-owner",
        role="user",
        content="Первое сообщение",
    )
    monkeypatch.setattr("asd_kontur.domain.uuid7", lambda: first_message.message_id)
    with pytest.raises(sa.exc.IntegrityError):
        repository.append_message(
            organization_id=organization_id,
            conversation_id=conversation.conversation_id,
            owner_identity_id="rollback-owner",
            role="user",
            content="Дубликат",
        )
    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM platform.construction_consultant_messages "
                "WHERE organization_id = :o AND conversation_id = :c"
            ),
            {"o": organization_id, "c": conversation.conversation_id},
        ).scalar_one()
    assert count == 1


def test_concurrent_append_message_locking_protocol(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    application_repository = ConstructionConsultantRepository(
        postgres_environment.application_engine
    )
    document_worker_repository = ConstructionConsultantRepository(
        postgres_environment.document_worker_engine
    )

    organization_id = uuid4()
    conversation = application_repository.create_conversation(
        organization_id=organization_id,
        owner_identity_id="concurrent-owner",
        title="Конкурентная запись",
    )

    barrier = threading.Barrier(3)
    results: list[ConstructionConsultantMessage] = []
    errors: list[Exception] = []

    def worker(
        repo: ConstructionConsultantRepository,
        content: str,
    ) -> None:
        try:
            barrier.wait()
            msg = repo.append_message(
                organization_id=organization_id,
                conversation_id=conversation.conversation_id,
                owner_identity_id="concurrent-owner",
                role="user",
                content=content,
            )
            results.append(msg)
        except Exception as e:
            errors.append(e)

    with postgres_environment.owner_engine.begin() as conn:
        conn.execute(
            sa.text(
                "SELECT 1 FROM platform.construction_consultant_conversations "
                "WHERE organization_id = :org_id "
                "AND conversation_id = :conv_id "
                "AND created_by_identity_id = :owner_id "
                "FOR UPDATE"
            ),
            {
                "org_id": organization_id,
                "conv_id": conversation.conversation_id,
                "owner_id": "concurrent-owner",
            },
        )

        thread_app = threading.Thread(
            target=worker,
            args=(application_repository, "app-content"),
        )
        thread_doc = threading.Thread(
            target=worker,
            args=(document_worker_repository, "doc-content"),
        )

        thread_app.start()
        thread_doc.start()

        barrier.wait()
        threading.Event().wait(0.2)

        assert len(results) == 0, "Appends should be blocked by lock"
        assert len(errors) == 0, "No errors should occur while blocked"

    thread_app.join(timeout=5.0)
    thread_doc.join(timeout=5.0)

    assert not thread_app.is_alive(), "Application thread did not finish"
    assert not thread_doc.is_alive(), "Document worker thread did not finish"
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"

    ordinals = sorted(msg.ordinal for msg in results)
    assert ordinals == [1, 2], f"Expected ordinals [1, 2], got {ordinals}"

    with postgres_environment.application_engine.begin() as conn:
        conn.execute(
            sa.select(sa.func.set_config("asd.organization_id", str(organization_id), True))
        )
        rows = conn.execute(
            sa.text(
                "SELECT message_ordinal FROM platform.construction_consultant_messages "
                "WHERE organization_id = :o AND conversation_id = :c "
                "ORDER BY message_ordinal"
            ),
            {"o": organization_id, "c": conversation.conversation_id},
        ).fetchall()

    stored_ordinals = [row[0] for row in rows]
    assert stored_ordinals == [1, 2], f"Expected stored ordinals [1, 2], got {stored_ordinals}"


def test_message_history_read_and_authorization(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    organization_id = uuid4()
    repo = ConstructionConsultantRepository(postgres_environment.application_engine)
    conversation = repo.create_conversation(
        organization_id=organization_id,
        owner_identity_id="history-owner",
        title="История",
    )
    empty = repo.messages(organization_id, conversation.conversation_id, "history-owner")
    assert empty == ()

    repo.append_message(
        organization_id,
        conversation.conversation_id,
        "history-owner",
        "user",
        "Первое",
    )
    repo.append_message(
        organization_id,
        conversation.conversation_id,
        "history-owner",
        "assistant",
        "Второе",
    )

    messages = repo.messages(organization_id, conversation.conversation_id, "history-owner")
    assert len(messages) == 2
    assert [m.ordinal for m in messages] == [1, 2]
    assert messages[0].role == "user"
    assert messages[0].content == "Первое"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Второе"

    with pytest.raises(ConstructionConsultantPersistenceError) as exc_info:
        repo.messages(organization_id, conversation.conversation_id, "foreign-owner")
    assert exc_info.value.code == "construction_consultant_conversation_not_found"

    foreign_org_id = uuid4()
    with pytest.raises(ConstructionConsultantPersistenceError) as exc_info:
        repo.messages(foreign_org_id, conversation.conversation_id, "history-owner")
    assert exc_info.value.code == "construction_consultant_conversation_not_found"


def test_list_conversations_filters_by_owner_and_org_with_deterministic_ordering(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    """Test list filtering by owner/org and deterministic sorting."""
    repository = ConstructionConsultantRepository(postgres_environment.application_engine)

    # Создаем идентификаторы организаций и владельцев
    org_a_id = uuid4()
    org_b_id = uuid4()
    owner_a_id = "owner-a"
    owner_b_id = "owner-b"

    # 1. Создаем диалоги
    # Владелец A в Организации A: два диалога
    conv_a1 = repository.create_conversation(
        organization_id=org_a_id,
        owner_identity_id=owner_a_id,
        title="Диалог A1",
    )
    conv_a2 = repository.create_conversation(
        organization_id=org_a_id,
        owner_identity_id=owner_a_id,
        title="Диалог A2",
    )

    # Владелец B в Организации A: один диалог
    conv_b1 = repository.create_conversation(
        organization_id=org_a_id,
        owner_identity_id=owner_b_id,
        title="Диалог B1",
    )

    # Владелец A в Организации B: один диалог
    conv_a_org_b = repository.create_conversation(
        organization_id=org_b_id,
        owner_identity_id=owner_a_id,
        title="Диалог A в Org B",
    )

    # 2. Добавляем сообщения в диалоги владельца A в Организации A
    repository.append_message(
        organization_id=org_a_id,
        conversation_id=conv_a1.conversation_id,
        owner_identity_id=owner_a_id,
        role="user",
        content="Сообщение 1",
    )
    repository.append_message(
        organization_id=org_a_id,
        conversation_id=conv_a2.conversation_id,
        owner_identity_id=owner_a_id,
        role="user",
        content="Сообщение 2",
    )

    # 3. Получаем список диалогов для владельца A в Организации A
    values = repository.list_conversations(
        organization_id=org_a_id,
        owner_identity_id=owner_a_id,
    )

    # Проверка количества
    assert len(values) == 2, f"Ожидалось 2 диалога, получено {len(values)}"

    # Проверка содержимого: только диалоги владельца A в Организации A
    returned_ids = {v.conversation_id for v in values}
    expected_ids = {conv_a1.conversation_id, conv_a2.conversation_id}
    assert returned_ids == expected_ids, (
        f"Неверный набор диалогов. Ожидалось {expected_ids}, получено {returned_ids}"
    )

    # Проверка отсутствия чужих диалогов
    assert conv_b1.conversation_id not in returned_ids
    assert conv_a_org_b.conversation_id not in returned_ids

    # Проверка количества сообщений
    for v in values:
        assert v.message_count == 1, f"Диалог {v.conversation_id} должен иметь 1 сообщение"

    # Проверка детерминированной сортировки
    # Контракт: created_at DESC, conversation_id
    # Так как created_at генерируется БД и может совпасть при быстром создании,
    # мы проверяем, что порядок соответствует сортировке по (created_at DESC, conversation_id).
    # Use conversation_id as secondary key for determinism when created_at is equal.

    # Сортируем ожидаемые значения по контракту
    # Так как мы не знаем точных created_at заранее, мы проверяем, что возвращенный список
    # является отсортированным по (created_at DESC, conversation_id ASC).

    # Проверяем, что список отсортирован правильно
    for index in range(len(values) - 1):
        current = values[index]
        next_val = values[index + 1]

        # Если created_at равны, то conversation_id должен быть в порядке возрастания
        if current.created_at == next_val.created_at:
            assert current.conversation_id < next_val.conversation_id, (
                f"При равных created_at, conversation_id должен быть в порядке возрастания. "
                f"Текущий: {current.conversation_id}, Следующий: {next_val.conversation_id}"
            )
        else:
            # Если created_at не равны, то текущий должен быть новее (больше)
            assert current.created_at > next_val.created_at, (
                f"Список должен быть отсортирован по created_at DESC. "
                f"Текущий: {current.created_at}, Следующий: {next_val.created_at}"
            )
