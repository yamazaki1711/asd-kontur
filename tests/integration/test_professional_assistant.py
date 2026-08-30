# ruff: noqa: RUF001

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from asd_kontur.application_spine.config import SessionProfile, SpineSettings
from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.worker import AssistantWorker
from asd_kontur.web_app import create_app

from .conftest import PostgreSQLEnvironment

pytestmark = pytest.mark.postgres


def _settings(environment: PostgreSQLEnvironment, root: Path) -> SpineSettings:
    objects = root / "objects"
    archives = root / "archives"
    objects.mkdir()
    archives.mkdir()
    return SpineSettings(
        database_url=environment.application_engine.url.render_as_string(
            hide_password=False
        ),
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
        monkeypatch.setattr(
            worker,
            "_generate",
            lambda claimed, prompt: (
                "### Краткий ответ\nПодготовьте АОСР и связанные документы комплекта.\n"
                "### Ограничения и недостающие сведения\nПроверьте исходные данные."
            ),
        )
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
        assert "Подготовьте АОСР" in messages[1]["content"]
        assert client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/turns/{turn_id}"
        ).status_code == 404
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
        assert client.get(
            f"/api/v1/workspaces/{workspace_a['workspace_id']}/assistant/conversations"
        ).status_code == 404
        remaining_b = client.get(
            f"/api/v1/workspaces/{workspace_b['workspace_id']}/assistant/conversations"
        ).json()
        assert [item["conversation_id"] for item in remaining_b] == [
            conversation_b.json()["conversation_id"]
        ]


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
        monkeypatch.setattr(worker, "_generate", lambda *_: (_ for _ in ()).throw(URLError("down")))
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
