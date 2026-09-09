# ruff: noqa: RUF001

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from urllib.error import URLError
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.worker import AssistantWorker
from asd_kontur.knowledge.gateway import GatewayContext
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def test_ntd_inventory_distinguishes_searchable_text_from_verified_provisions(
    postgres_environment: PostgreSQLEnvironment,
) -> None:
    search_document_id = uuid4()
    fingerprint = "sha256:" + "1" * 64
    page_fingerprint = "sha256:" + "2" * 64
    digest = "sha256:" + "3" * 64
    with postgres_environment.owner_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_search_documents("
                "search_document_id,version,authority_class,stable_designation,"
                "normalized_designation,alternative_designations,title,edition_label,artifact_digest,"
                "bytes_status,page_inventory_status,text_status,search_status,structure_status,"
                "edition_currency_status,page_count,searchable_page_count,native_text_characters,"
                "ocr_page_count,ocr_text_characters,"
                "structured_fragment_count,verified_provision_count,source_metadata,"
                "index_profile_version,document_fingerprint,search_text) VALUES ("
                ":id,1,'legacy_reference','СП 70.13330.2012','сп70133302012',"
                "ARRAY['СП 70','СП70','СП 70.13330','СП 70.13330.2012'],"
                "'Несущие и ограждающие конструкции','2012',:digest,'present','inventoried',"
                "'complete','searchable','not_structured','not_checked',1,1,96,0,0,0,0,"
                '\'{"authority_statement":"legacy_reference_not_active_authority"}\'::jsonb,'
                "'ntd-consultant-search-index@1.0.0',:fingerprint,"
                "'СП 70.13330.2012 несущие ограждающие бетонные конструкции')"
            ),
            {"id": search_document_id, "digest": digest, "fingerprint": fingerprint},
        )
        connection.execute(
            sa.text(
                "INSERT INTO platform.ntd_search_pages(search_document_id,search_document_version,"
                "page_number,page_text,page_text_digest,text_status,extraction_method,"
                "page_fingerprint) "
                "VALUES (:id,1,1,'Контроль качества бетона: входной, операционный и приемочный.',"
                ":digest,'searchable','recovered_legacy_native_pdf',:fingerprint)"
            ),
            {"id": search_document_id, "digest": digest, "fingerprint": page_fingerprint},
        )
    query = ProfessionalAssistantKnowledgeQuery(postgres_environment.application_engine)
    context = GatewayContext(
        "synthetic-owner",
        "assistant.chat.test",
        "ntd-consultant-corpus-test@1.0.0",
        uuid4(),
        uuid4(),
        uuid4(),
    )

    resolved = query.execute(
        "consultant.resolve_ntd_designation",
        {"mode": "Support", "designation": "СП70"},
        context,
    ).result

    assert resolved["outcome"] == "document_present_searchable"
    assert resolved["items"][0]["verified_provision_count"] == 0
    assert {item["code"] for item in resolved["gaps"]} == {
        "verified_provisions_unavailable",
        "edition_currency_not_checked",
    }
    with pytest.raises(sa.exc.DBAPIError):
        with postgres_environment.owner_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE platform.ntd_search_documents SET title='changed' "
                    "WHERE search_document_id=:id"
                ),
                {"id": search_document_id},
            )


def _settings(environment: PostgreSQLEnvironment, root: Path) -> SpineSettings:
    objects = root / "objects"
    archives = root / "archives"
    objects.mkdir()
    archives.mkdir()
    return SpineSettings(
        database_url=environment.application_engine.url.render_as_string(hide_password=False),
        lifecycle_database_url=environment.lifecycle_engine.url.render_as_string(
            hide_password=False
        ),
        worker_database_url=environment.document_worker_engine.url.render_as_string(
            hide_password=False
        ),
        destruction_database_url=environment.destruction_engine.url.render_as_string(
            hide_password=False
        ),
        object_store_root=objects,
        archive_store_root=archives,
        session_profile=SessionProfile.DEVELOPMENT_LOOPBACK,
        audit_pepper="synthetic-assistant-integration-pepper",
    )


def _csrf(client: TestClient) -> dict[str, str]:
    value = client.cookies.get("asd_csrf")
    assert value
    return {"X-CSRF-Token": value}


def test_conversation_is_workspace_scoped_durable_and_streamed(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(
        engine=postgres_environment.application_engine,
        settings=_settings(postgres_environment, tmp_path),
    )
    app.state.container.auth.bootstrap_owner(
        username="assistant-owner",
        password="Synthetic-Assistant-Password-42!",
        display_name="Assistant owner",
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/session/login",
            json={
                "username": "assistant-owner",
                "password": "Synthetic-Assistant-Password-42!",
            },
        )
        assert login.status_code == 200
        csrf = _csrf(client)
        workspace_a = cast(
            dict[str, Any],
            client.post(
                "/api/v1/workspaces",
                json={"display_name": "Assistant workspace A"},
                headers=csrf,
            ).json(),
        )
        workspace_b = cast(
            dict[str, Any],
            client.post(
                "/api/v1/workspaces",
                json={"display_name": "Assistant workspace B"},
                headers=csrf,
            ).json(),
        )
        conversation = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/conversations",
            json={"title": "АОСР и комплект"},
            headers=csrf,
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["conversation_id"]
        asked = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/conversations/"
            f"{conversation_id}/turns",
            json={"mode": "Support", "question": "Какие документы нужны для АОСР?"},
            headers=csrf,
        )
        assert asked.status_code == 202
        turn_id = asked.json()["turn_id"]
        assert asked.json()["state"] == "queued"
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/conversations"
            ).json()
            == []
        )

        worker = AssistantWorker(
            AssistantRepository(postgres_environment.document_worker_engine),
            ProfessionalAssistantKnowledgeQuery(postgres_environment.application_engine),
            identity="assistant-test-worker",
        )
        model_outputs = iter(
            (
                '{"intent":"general_engineering","needs_clarification":false,'
                '"clarifying_question":null,"steps":[]}',
                '{"answer":"Подготовьте АОСР и связанные документы комплекта.",'
                '"answer_type":"direct","needs_clarification":false,'
                '"used_source_ids":[],"dialogue_summary":"Обсуждается комплект АОСР.",'
                '"active_subjects":["АОСР"]}',
                '{"passed":true,"issues":[]}',
            )
        )
        monkeypatch.setattr(worker, "_model_complete", lambda *args, **kwargs: next(model_outputs))
        claimed = worker._repository.claim("assistant-test-worker", 900)
        assert claimed is not None
        worker._run(claimed)
        turn = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/turns/{turn_id}"
        ).json()
        assert turn["state"] == "succeeded"
        messages = client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/conversations/"
            f"{conversation_id}/messages"
        ).json()
        assert [item["role"] for item in messages] == ["user", "assistant"]
        assert messages[1]["content"] == "Подготовьте АОСР и связанные документы комплекта."
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/turns/{turn_id}"
            ).status_code
            == 404
        )
        conversation_b = client.post(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/conversations",
            json={"title": "История второго объекта"},
            headers=csrf,
        )
        assert conversation_b.status_code == 201
        prepared = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/lifecycle/reset/prepare",
            json={"confirmation": "PREPARE_WORKSPACE_RESET"},
            headers=csrf,
        )
        assert prepared.status_code == 200, prepared.text
        challenge = prepared.json()
        reset = client.post(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/lifecycle/reset/execute",
            json={
                "challenge_id": challenge["challenge_id"],
                "confirmation_text": challenge["confirmation_text"],
            },
            headers=csrf,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["outcome"] == "verified"
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/conversations"
            ).status_code
            == 404
        )
        remaining_b = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/conversations"
        ).json()
        assert [item["conversation_id"] for item in remaining_b] == [
            conversation_b.json()["conversation_id"]
        ]


def test_platform_history_owner_isolation_and_no_workspace_fields(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    app = create_app(
        engine=postgres_environment.application_engine,
        settings=_settings(postgres_environment, tmp_path),
    )
    app.state.container.auth.bootstrap_owner(
        username="owner-a",
        password="Owner-A-Pass-123!",
        display_name="Owner A",
    )
    app.state.container.auth.bootstrap_owner(
        username="owner-b",
        password="Owner-B-Pass-123!",
        display_name="Owner B",
    )

    with TestClient(app) as client:
        # Owner A login
        login_a = client.post(
            "/api/v1/session/login",
            json={"username": "owner-a", "password": "Owner-A-Pass-123!"},
        )
        assert login_a.status_code == 200
        csrf_a = _csrf(client)

        # Create conversation
        create_resp = client.post(
            "/api/v1/construction-consultant/conversations",
            json={"title": "Test Conversation"},
            headers=csrf_a,
        )
        assert create_resp.status_code == 201
        conv_data = create_resp.json()
        assert "workspace_id" not in conv_data
        assert conv_data["title"] == "Test Conversation"
        assert "conversation_id" in conv_data
        assert "created_at" in conv_data
        assert "message_count" in conv_data
        conv_id = conv_data["conversation_id"]

        # Get list
        list_resp = client.get("/api/v1/construction-consultant/conversations")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) == 1
        assert list_data[0]["conversation_id"] == conv_id

        # Get messages
        msg_resp = client.get(f"/api/v1/construction-consultant/conversations/{conv_id}/messages")
        assert msg_resp.status_code == 200
        assert msg_resp.json() == []

        # Logout A
        logout_a = client.post("/api/v1/session/logout", headers=csrf_a)
        assert logout_a.status_code == 204

        # Owner B login
        login_b = client.post(
            "/api/v1/session/login",
            json={"username": "owner-b", "password": "Owner-B-Pass-123!"},
        )
        assert login_b.status_code == 200
        # Get list for B
        list_resp_b = client.get("/api/v1/construction-consultant/conversations")
        assert list_resp_b.status_code == 200
        assert list_resp_b.json() == []

        # Try to access A's messages
        msg_resp_b = client.get(f"/api/v1/construction-consultant/conversations/{conv_id}/messages")
        assert msg_resp_b.status_code == 404


def test_platform_consultant_question_is_persisted_idempotently_and_isolated(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    app = create_app(
        engine=postgres_environment.application_engine,
        settings=_settings(postgres_environment, tmp_path),
    )
    app.state.container.auth.bootstrap_owner(
        username="consultant-owner-a",
        password="Consultant-Owner-A-42!",
        display_name="Consultant owner A",
    )
    app.state.container.auth.bootstrap_owner(
        username="consultant-owner-b",
        password="Consultant-Owner-B-42!",
        display_name="Consultant owner B",
    )

    class StubConstructionModel:
        calls = 0

        def complete(self, prompt: str) -> str:
            assert "Вопрос: Что проверяют при входном контроле?" in prompt
            self.calls += 1
            return "Проверяют документы качества, маркировку и соответствие поставке."

    model = StubConstructionModel()
    app.state.container.construction_consultant_questions._model = model

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/session/login",
                json={"username": "consultant-owner-a", "password": "Consultant-Owner-A-42!"},
            ).status_code
            == 200
        )
        csrf_a = _csrf(client)
        created = client.post(
            "/api/v1/construction-consultant/conversations",
            json={"title": "Входной контроль"},
            headers=csrf_a,
        )
        assert created.status_code == 201
        conversation_id = created.json()["conversation_id"]
        request_id = str(uuid4())
        body = {"request_id": request_id, "question": "Что проверяют при входном контроле?"}

        answer = client.post(
            f"/api/v1/construction-consultant/conversations/{conversation_id}/questions",
            json=body,
            headers=csrf_a,
        )
        assert answer.status_code == 200, answer.text
        payload = answer.json()
        assert payload["user_message"]["role"] == "user"
        assert payload["assistant_message"]["role"] == "assistant"
        assert payload["user_message"]["request_id"] == request_id
        assert payload["assistant_message"]["request_id"] == request_id
        assert model.calls == 1

        repeated = client.post(
            f"/api/v1/construction-consultant/conversations/{conversation_id}/questions",
            json=body,
            headers=csrf_a,
        )
        assert repeated.status_code == 200, repeated.text
        assert (
            repeated.json()["assistant_message"]["message_id"]
            == payload["assistant_message"]["message_id"]
        )
        assert model.calls == 1
        messages = client.get(
            f"/api/v1/construction-consultant/conversations/{conversation_id}/messages"
        )
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()] == ["user", "assistant"]

        assert client.post("/api/v1/session/logout", headers=csrf_a).status_code == 204
        assert (
            client.post(
                "/api/v1/session/login",
                json={"username": "consultant-owner-b", "password": "Consultant-Owner-B-42!"},
            ).status_code
            == 200
        )
        forbidden = client.post(
            f"/api/v1/construction-consultant/conversations/{conversation_id}/questions",
            json={"request_id": str(uuid4()), "question": "Чужой вопрос"},
            headers=_csrf(client),
        )
        assert forbidden.status_code == 404


def test_worker_outage_is_a_typed_terminal_outcome(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(
        engine=postgres_environment.application_engine,
        settings=_settings(postgres_environment, tmp_path),
    )
    app.state.container.auth.bootstrap_owner(
        username="assistant-outage-owner",
        password="Synthetic-Assistant-Outage-42!",
        display_name="Assistant outage owner",
    )
    with TestClient(app) as client:
        client.post(
            "/api/v1/session/login",
            json={
                "username": "assistant-outage-owner",
                "password": "Synthetic-Assistant-Outage-42!",
            },
        )
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Assistant outage workspace"},
            headers=csrf,
        ).json()
        conversation = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/conversations",
            json={"title": "Проверка восстановления"},
            headers=csrf,
        ).json()
        turn = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/conversations/"
            f"{conversation['conversation_id']}/turns",
            json={"mode": "Restoration", "question": "Что можно восстановить?"},
            headers=csrf,
        ).json()
        worker = AssistantWorker(
            AssistantRepository(postgres_environment.document_worker_engine),
            ProfessionalAssistantKnowledgeQuery(postgres_environment.application_engine),
            identity="assistant-outage-worker",
        )
        monkeypatch.setattr(
            worker,
            "_model_complete",
            lambda *args, **kwargs: (_ for _ in ()).throw(URLError("down")),
        )
        claimed = worker._repository.claim("assistant-outage-worker", 900)
        assert claimed is not None
        worker._run(claimed)
        outcome = client.get(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/turns/{turn['turn_id']}"
        ).json()
        assert outcome["state"] == "reconciliation_required"
        assert outcome["failure_code"] == "qwen_stream_interrupted"


def test_queued_turn_can_be_stopped_without_leaving_an_orphan_job(
    postgres_environment: PostgreSQLEnvironment,
    tmp_path: Path,
) -> None:
    app = create_app(
        engine=postgres_environment.application_engine,
        settings=_settings(postgres_environment, tmp_path),
    )
    app.state.container.auth.bootstrap_owner(
        username="assistant-stop-owner",
        password="Synthetic-Assistant-Stop-42!",
        display_name="Assistant stop owner",
    )
    with TestClient(app) as client:
        client.post(
            "/api/v1/session/login",
            json={
                "username": "assistant-stop-owner",
                "password": "Synthetic-Assistant-Stop-42!",
            },
        )
        csrf = _csrf(client)
        workspace = client.post(
            "/api/v1/workspaces",
            json={"display_name": "Assistant stop workspace"},
            headers=csrf,
        ).json()
        conversation = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/conversations",
            json={"title": "Остановка"},
            headers=csrf,
        ).json()
        turn = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/conversations/"
            f"{conversation['conversation_id']}/turns",
            json={"mode": "Audit", "question": "Какие пробелы найдены?"},
            headers=csrf,
        ).json()
        stopped = client.post(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/turns/"
            f"{turn['turn_id']}/cancel",
            json={"confirmation": "STOP_ASSISTANT_RESPONSE"},
            headers=csrf,
        )
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "cancelled"
        events = client.get(
            f"/api/v1/workspaces/{workspace['workspace_id']}/assistant/turns/"
            f"{turn['turn_id']}/events"
        )
        assert events.status_code == 200
        assert "event: cancelled" in events.text
        assert "Формирование ответа остановлено" in events.text
