from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.models import AssistantMode, ClaimedTurn
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.reasoning import SynthesizedAnswer
from asd_kontur.assistant.worker import AssistantWorker


def test_quality_check_accepts_bounded_publish_verdict(monkeypatch: Any) -> None:
    worker = AssistantWorker(
        cast(AssistantRepository, object()),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="test-worker",
    )
    monkeypatch.setattr(worker, "_model_complete", lambda *_args, **_kwargs: "PASS")
    claimed = ClaimedTurn(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        AssistantMode.SUPPORT,
        "Какие требования к уходу за бетоном?",
        "owner-a",
        1,
        1,
    )
    answer = SynthesizedAnswer(
        "Обеспечьте установленный проектом режим ухода за бетоном.",
        "direct",
        False,
        (),
        "Уход за бетоном.",
        ("бетон",),
    )

    assert worker._model_quality_check(claimed, answer, []) == {"passed": True, "issues": []}


def test_quality_check_fails_closed_for_non_protocol_response(monkeypatch: Any) -> None:
    worker = AssistantWorker(
        cast(AssistantRepository, object()),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="test-worker",
    )
    monkeypatch.setattr(worker, "_model_complete", lambda *_args, **_kwargs: "публикуйте")
    claimed = ClaimedTurn(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        AssistantMode.SUPPORT,
        "Какие требования к уходу за бетоном?",
        "owner-a",
        1,
        1,
    )
    answer = SynthesizedAnswer(
        "Обеспечьте установленный проектом режим ухода за бетоном.",
        "direct",
        False,
        (),
        "Уход за бетоном.",
        ("бетон",),
    )

    assert worker._model_quality_check(claimed, answer, []) == {
        "passed": False,
        "issues": ["model_quality_response_invalid"],
    }
