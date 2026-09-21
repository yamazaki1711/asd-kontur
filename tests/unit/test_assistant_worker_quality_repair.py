from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.models import AssistantMode, ClaimedTurn
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.reasoning import SynthesizedAnswer
from asd_kontur.assistant.worker import (
    AssistantWorker,
    _repair_prompt,
    _with_inventory_checks,
)


class _RecordingRepository:
    def __init__(self) -> None:
        self.completed: dict[str, Any] | None = None
        self.failed: str | None = None

    def start(self, claimed: ClaimedTurn) -> None:
        del claimed

    def history_for_prompt(self, claimed: ClaimedTurn) -> tuple[dict[str, str], ...]:
        del claimed
        return ()

    def dialogue_state(self, claimed: ClaimedTurn) -> None:
        del claimed
        return None

    def heartbeat(self, claimed: ClaimedTurn, lease_seconds: int) -> bool:
        del claimed, lease_seconds
        return False

    def append_delta(self, claimed: ClaimedTurn, text: str) -> None:
        del claimed, text

    def complete(self, claimed: ClaimedTurn, **kwargs: Any) -> None:
        del claimed
        self.completed = kwargs

    def fail(self, claimed: ClaimedTurn, code: str, **kwargs: Any) -> None:
        del claimed, kwargs
        self.failed = code


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


def test_inventory_candidates_cannot_be_replaced_by_generic_insufficient_answer() -> None:
    source_id = "11111111-1111-4111-8111-111111111111"
    receipts = [
        {
            "step_sequence": 1,
            "tool": "consultant.get_project_entity_inventory",
            "arguments": {"kind": "excavation_pit", "limit": 30},
            "reason": "Inventory coverage.",
            "response": {
                "outcome": "found",
                "value": {
                    "candidate_entity_count": 1,
                    "candidate_entities": [
                        {
                            "canonical_label": "Excavation Alpha",
                            "authority": "candidate_only_not_confirmed_distinct_project_entity",
                        }
                    ],
                    "coverage": {"exact_total_supported": False},
                },
                "sources": [{"source_id": source_id, "title": "Controlled source"}],
            },
        }
    ]
    answer = SynthesizedAnswer(
        "Недостаточно данных.",
        "insufficient_data",
        False,
        (),
        "Inventory requested.",
        ("excavations",),
    )

    checked = _with_inventory_checks(
        {"passed": True, "problems": []},
        answer=answer,
        receipts=receipts,
    )

    assert checked["passed"] is False
    assert checked["problems"] == [
        "workspace_inventory_candidates_ignored",
        "workspace_inventory_evidence_not_used",
    ]


def test_inventory_repair_receives_candidates_coverage_and_allowed_sources() -> None:
    source_id = "22222222-2222-4222-8222-222222222222"
    receipts = [
        {
            "step_sequence": 1,
            "tool": "consultant.get_project_entity_inventory",
            "arguments": {"kind": "facility", "limit": 30},
            "reason": "Inventory coverage.",
            "response": {
                "outcome": "found",
                "value": {
                    "candidate_entity_count": 1,
                    "candidate_entities": [{"canonical_label": "Facility Delta"}],
                    "coverage": {"exact_total_supported": False},
                },
                "sources": [{"source_id": source_id, "title": "Controlled source"}],
            },
        }
    ]
    claimed = ClaimedTurn(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        AssistantMode.TENDER,
        "List every facility.",
        "owner-a",
        1,
        1,
    )
    answer = SynthesizedAnswer(
        "Недостаточно данных.",
        "insufficient_data",
        False,
        (),
        "Facility inventory requested.",
        ("facilities",),
    )

    prompt = _repair_prompt(
        claimed,
        answer,
        {"issues": ["workspace_inventory_candidates_ignored"]},
        receipts,
    )

    assert "Facility Delta" in prompt
    assert 'exact_total_supported\\": false' in prompt
    assert source_id in prompt


def test_full_metadata_plan_executes_required_workspace_content_search(monkeypatch: Any) -> None:
    repository = _RecordingRepository()
    worker = AssistantWorker(
        cast(AssistantRepository, repository),
        cast(ProfessionalAssistantKnowledgeQuery, object()),
        identity="test-worker",
    )
    claimed = ClaimedTurn(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        AssistantMode.TENDER,
        "Сколько котлованов в этом проекте?",
        "owner-a",
        1,
        1,
    )
    source_id = "11111111-1111-4111-8111-111111111111"
    responses = iter(
        (
            json.dumps(
                {
                    "intent": "workspace",
                    "needs_clarification": False,
                    "clarifying_question": None,
                    "steps": [
                        {
                            "tool": "consultant.get_workspace_overview",
                            "arguments": {},
                            "reason": "Обзор.",
                        },
                        {
                            "tool": "consultant.get_work_packages",
                            "arguments": {},
                            "reason": "Пакеты.",
                        },
                        {
                            "tool": "consultant.get_requirement_matrix",
                            "arguments": {},
                            "reason": "Матрица.",
                        },
                        {
                            "tool": "consultant.get_information_gaps",
                            "arguments": {},
                            "reason": "Пробелы.",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "answer": (
                        "По найденному фрагменту требуется дальнейшая сверка полного реестра "
                        "котлованов."
                    ),
                    "answer_type": "workspace_conclusion",
                    "needs_clarification": False,
                    "used_source_ids": [source_id],
                    "dialogue_summary": "Проверяется перечень котлованов.",
                    "active_subjects": ["котлованы"],
                },
                ensure_ascii=False,
            ),
            "PASS",
        )
    )
    executed: list[str] = []

    monkeypatch.setattr(worker, "_model_complete", lambda *_args, **_kwargs: next(responses))

    def execute(step: Any, sequence: int) -> dict[str, Any]:
        executed.append(step.tool)
        sources: list[dict[str, Any]] = []
        if step.tool == "consultant.search_workspace_documents":
            sources = [
                {
                    "source_id": source_id,
                    "authority_layer": "workspace_fact",
                    "title": "Проектный лист",
                    "locator_label": "лист 1",
                }
            ]
        return {
            "step_sequence": sequence,
            "tool": step.tool,
            "arguments": step.arguments,
            "reason": step.reason,
            "response": {"sources": sources},
        }

    monkeypatch.setattr(
        worker, "_execute_tool", lambda _claimed, step, sequence: execute(step, sequence)
    )

    worker._run(claimed)

    assert executed == [
        "consultant.search_workspace_documents",
        "consultant.get_project_entity_inventory",
        "consultant.get_requirement_matrix",
        "consultant.get_information_gaps",
    ]
    assert repository.failed is None
    assert repository.completed is not None
