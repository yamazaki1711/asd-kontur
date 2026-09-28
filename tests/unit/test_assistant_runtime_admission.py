from __future__ import annotations

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
