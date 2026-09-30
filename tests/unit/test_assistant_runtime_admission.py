from __future__ import annotations

import io
import json
from typing import Any, cast

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.worker import AssistantWorker


def test_busy_qwen_runtime_is_detected_without_using_proxy(monkeypatch: Any) -> None:
    worker = AssistantWorker(
        cast(AssistantRepository, object()),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="assistant-test",
    )

    class Opener:
        def open(self, request: Any, *, timeout: float) -> Any:
            assert request.full_url == "http://127.0.0.1:8790/health"
            assert timeout == 1.0
            raise TimeoutError

    monkeypatch.setattr("urllib.request.build_opener", lambda *_args: Opener())

    assert worker._qwen_runtime_available() is False


def test_generating_qwen_is_healthy_but_not_claimable_by_assistant(monkeypatch: Any) -> None:
    worker = AssistantWorker(
        cast(AssistantRepository, object()),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="assistant-test",
    )

    class Response(io.BytesIO):
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    class Opener:
        def open(self, _request: Any, *, timeout: float) -> Response:
            assert timeout == 1.0
            return Response(json.dumps({"status": "QWEN_GENERATING"}).encode())

    monkeypatch.setattr("urllib.request.build_opener", lambda *_args: Opener())

    assert worker._qwen_runtime_available() is False


def test_idle_qwen_is_available_to_assistant(monkeypatch: Any) -> None:
    worker = AssistantWorker(
        cast(AssistantRepository, object()),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="assistant-test",
    )

    class Response(io.BytesIO):
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    class Opener:
        def open(self, _request: Any, *, timeout: float) -> Response:
            assert timeout == 1.0
            return Response(json.dumps({"status": "QWEN_READY_IDLE"}).encode())

    monkeypatch.setattr("urllib.request.build_opener", lambda *_args: Opener())

    assert worker._qwen_runtime_available() is True
