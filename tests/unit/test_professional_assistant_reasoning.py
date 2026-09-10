from __future__ import annotations

# ruff: noqa: RUF001 -- Russian characterization copy is intentional.
import json
from collections import Counter
from pathlib import Path

import pytest

from asd_kontur.assistant.reasoning import (
    MAX_TOOL_STEPS,
    PlannedToolCall,
    SearchPlan,
    compact_history,
    ensure_workspace_content_search,
    parse_adequacy_decision,
    parse_search_plan,
    parse_synthesized_answer,
    validate_answer,
)


def test_plan_accepts_bounded_granular_tools_and_rejects_megapack() -> None:
    plan = parse_search_plan(
        json.dumps(
            {
                "intent": "mixed",
                "needs_clarification": False,
                "clarifying_question": None,
                "steps": [
                    {
                        "tool": "consultant.get_work_packages",
                        "arguments": {},
                        "reason": "Нужен конкретный вид работ объекта",
                    },
                    {
                        "tool": "consultant.search_ntd",
                        "arguments": {"query": "контроль бетонных работ", "limit": 3},
                        "reason": "Нужны применимые положения",
                    },
                ],
            },
            ensure_ascii=False,
        )
    )
    assert [item.tool for item in plan.steps] == [
        "consultant.get_work_packages",
        "consultant.search_ntd",
    ]
    with pytest.raises(ValueError, match="assistant_plan_tool_invalid"):
        parse_search_plan(
            '{"intent":"mixed","needs_clarification":false,"clarifying_question":null,'
            '"steps":[{"tool":"knowledge.get_professional_assistant_context",'
            '"arguments":{},"reason":"весь контекст"}]}'
        )


def test_clarification_required_intent_requires_one_clarification_without_tools() -> None:
    plan = parse_search_plan(
        '{"intent":"clarification_required","needs_clarification":true,'
        '"clarifying_question":"Какой именно вид работ вы имеете в виду?","steps":[]}'
    )
    assert plan.needs_clarification is True
    assert plan.steps == ()


def test_adequacy_may_add_only_one_valid_search_step() -> None:
    decision = parse_adequacy_decision(
        '{"sufficient":false,"reason":"Не найден точный пункт",'
        '"additional_step":{"tool":"consultant.get_ntd_section_context",'
        '"arguments":{"search_document_id":"11111111-1111-4111-8111-111111111111",'
        '"page_number":17,"radius":2},'
        '"reason":"Нужны соседние пункты"},"needs_clarification":false,'
        '"clarifying_question":null}'
    )
    assert decision.additional_step is not None
    assert decision.additional_step.tool == "consultant.get_ntd_section_context"
    assert decision.additional_step.arguments["page_number"] == 17


def test_adequacy_normalizes_qwen_params_alias() -> None:
    decision = parse_adequacy_decision(
        '{"sufficient":false,"reason":"Нужен уточнённый поиск",'
        '"additional_step":{"tool":"consultant.search_ntd",'
        '"params":{"query":"набор прочности бетона","limit":5}},'
        '"needs_clarification":false,"clarifying_question":null}'
    )
    assert decision.additional_step is not None
    assert decision.additional_step.arguments["query"] == "набор прочности бетона"


def test_initial_plan_drops_only_impossible_dependent_placeholder() -> None:
    plan = parse_search_plan(
        '{"intent":"normative","needs_clarification":false,"clarifying_question":null,'
        '"steps":[{"tool":"consultant.search_practice","arguments":{"query":"АОСР",'
        '"limit":5},"reason":"Найти рекомендации"},{"tool":'
        '"consultant.get_practice_fragment","arguments":{"source_id":'
        '"uuid_placeholder_from_step_1"},"reason":"Получить фрагмент"}]}'
    )
    assert [step.tool for step in plan.steps] == ["consultant.search_practice"]


def test_answer_can_be_direct_and_selects_only_relevant_sources() -> None:
    source = {
        "source_id": "11111111-1111-4111-8111-111111111111",
        "authority_layer": "workspace_fact",
    }
    answer = parse_synthesized_answer(
        '{"answer":"В смете отсутствует работа по устройству плиты.",'
        '"answer_type":"workspace_conclusion","needs_clarification":false,'
        '"used_source_ids":["11111111-1111-4111-8111-111111111111"],'
        '"dialogue_summary":"Сопоставляются ВОР и смета.",'
        '"active_subjects":["устройство монолитной плиты"]}',
        {source["source_id"]},
    )
    receipt = validate_answer(
        answer,
        intent="workspace",
        tool_names=("consultant.get_discrepancies",),
        sources=(source,),
    )
    assert receipt["passed"] is True
    assert receipt["selected_source_count"] == 1


def test_answer_rejects_source_that_was_not_retrieved() -> None:
    with pytest.raises(ValueError, match="assistant_answer_unknown_source"):
        parse_synthesized_answer(
            '{"answer":"Текст","answer_type":"direct","needs_clarification":false,'
            '"used_source_ids":["22222222-2222-4222-8222-222222222222"],'
            '"dialogue_summary":"Обсуждается термин.","active_subjects":[]}',
            set(),
        )


def test_clarification_may_explain_that_normative_source_was_not_found() -> None:
    answer = parse_synthesized_answer(
        '{"answer":"В доступной нормативной памяти значение не найдено. Уточните класс бетона?",'
        '"answer_type":"clarification","needs_clarification":true,"used_source_ids":[],'
        '"dialogue_summary":"Уточняется ранняя прочность бетона.",'
        '"active_subjects":["прочность бетона"]}',
        set(),
    )
    receipt = validate_answer(answer, intent="general", tool_names=(), sources=())
    assert receipt["passed"] is True


def test_clarification_rejects_unverified_numeric_estimate_and_requires_question() -> None:
    answer = parse_synthesized_answer(
        '{"answer":"Обычно бетон набирает 30–40% прочности.",'
        '"answer_type":"clarification","needs_clarification":true,"used_source_ids":[],'
        '"dialogue_summary":"Уточняется ранняя прочность бетона.",'
        '"active_subjects":["прочность бетона"]}',
        set(),
    )
    receipt = validate_answer(answer, intent="general", tool_names=(), sources=())
    assert receipt["passed"] is False
    assert "clarification_without_question" in receipt["problems"]
    assert "clarification_has_unverified_numeric_estimate" in receipt["problems"]


def test_insufficient_answer_must_tell_user_what_to_supply() -> None:
    answer = parse_synthesized_answer(
        '{"answer":"Данных недостаточно для точного ответа.",'
        '"answer_type":"insufficient_data","needs_clarification":false,"used_source_ids":[],'
        '"dialogue_summary":"Не хватает параметров.","active_subjects":[]}',
        set(),
    )
    receipt = validate_answer(answer, intent="general", tool_names=(), sources=())
    assert "insufficient_without_next_question" in receipt["problems"]


def test_project_enumeration_cannot_use_metadata_only_workspace_overview() -> None:
    plan = SearchPlan(
        "workspace",
        False,
        None,
        (PlannedToolCall("consultant.get_workspace_overview", {}, "Обзор объекта."),),
    )

    required = ensure_workspace_content_search(plan, "Сколько котлованов в этом проекте?")

    assert [step.tool for step in required.steps] == [
        "consultant.get_workspace_overview",
        "consultant.search_workspace_documents",
    ]
    assert required.steps[-1].arguments["query"] == "Сколько котлованов в этом проекте?"


def test_project_enumeration_replaces_metadata_when_plan_is_at_tool_budget() -> None:
    plan = SearchPlan(
        "workspace",
        False,
        None,
        (
            PlannedToolCall("consultant.get_workspace_overview", {}, "Обзор объекта."),
            PlannedToolCall("consultant.get_work_packages", {}, "Пакеты работ."),
            PlannedToolCall("consultant.get_requirement_matrix", {}, "Матрица."),
            PlannedToolCall("consultant.get_information_gaps", {}, "Пробелы."),
        ),
    )

    required = ensure_workspace_content_search(plan, "Сколько котлованов в этом проекте?")

    assert len(required.steps) == MAX_TOOL_STEPS
    assert [step.tool for step in required.steps] == [
        "consultant.search_workspace_documents",
        "consultant.get_work_packages",
        "consultant.get_requirement_matrix",
        "consultant.get_information_gaps",
    ]


def test_workspace_answer_cannot_declare_uploaded_documents_empty_after_retrieval() -> None:
    answer = parse_synthesized_answer(
        json.dumps(
            {
                "answer": " ".join(
                    (
                        "В загруженных документах отсутствует информация о котлованах.",
                        "Уточните вопрос?",
                    )
                ),
                "answer_type": "insufficient_data",
                "needs_clarification": False,
                "used_source_ids": [],
                "dialogue_summary": "Проверяется число котлованов.",
                "active_subjects": ["котлованы"],
            },
            ensure_ascii=False,
        ),
        set(),
    )

    receipt = validate_answer(
        answer,
        intent="workspace",
        tool_names=("consultant.search_workspace_documents",),
        sources=(),
    )

    assert "workspace_documents_incorrectly_declared_absent" in receipt["problems"]


def test_project_metadata_question_does_not_force_document_search() -> None:
    plan = SearchPlan(
        "workspace",
        False,
        None,
        (PlannedToolCall("consultant.get_workspace_overview", {}, "Обзор объекта."),),
    )

    assert ensure_workspace_content_search(plan, "Как называется этот объект?") == plan


def test_history_window_is_bounded_and_preserves_latest_reference() -> None:
    messages = tuple(
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"сообщение {index} " * 300}
        for index in range(20)
    )
    compact = compact_history(messages)
    assert len(compact) <= 8
    assert sum(len(item["content"]) for item in compact) <= 6_000
    assert "сообщение 19" in compact[-1]["content"]


def test_professional_quality_matrix_has_exact_unmemorized_denominator(
    repository_root: Path,
) -> None:
    matrix = json.loads(
        (
            repository_root / "tests" / "fixtures" / "professional_assistant_quality_matrix_v1.json"
        ).read_text(encoding="utf-8")
    )
    cases = matrix["cases"]
    assert len(cases) == 30
    assert Counter(item["category"] for item in cases) == {
        "direct": 5,
        "practice-synthesis": 5,
        "workspace": 5,
        "document-conflict": 4,
        "follow-up": 3,
        "clarification": 3,
        "missing-data": 3,
        "no-retrieval": 2,
    }
    assert sum(bool(item.get("characterization")) for item in cases) >= 2
    assert len({item["question"] for item in cases}) == 30


def test_engineering_plan_accepts_valid_b20_age3() -> None:
    plan = parse_search_plan(
        json.dumps(
            {
                "intent": "general_engineering",
                "needs_clarification": False,
                "clarifying_question": None,
                "steps": [
                    {
                        "tool": "consultant.estimate_concrete_early_strength",
                        "arguments": {
                            "concrete_class": "B20",
                            "age_days": 3,
                        },
                        "reason": "Оценка ранней прочности",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "consultant.estimate_concrete_early_strength"


def test_engineering_plan_rejects_workspace_tool() -> None:
    with pytest.raises(ValueError, match="assistant_plan_general_engineering_tools_invalid"):
        parse_search_plan(
            json.dumps(
                {
                    "intent": "general_engineering",
                    "needs_clarification": False,
                    "clarifying_question": None,
                    "steps": [
                        {
                            "tool": "consultant.get_workspace_overview",
                            "arguments": {},
                            "reason": "Неверный инструмент",
                        }
                    ],
                },
            )
        )
