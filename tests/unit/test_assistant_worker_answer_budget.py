# ruff: noqa: RUF001 -- Cyrillic construction fixture is intentional.

import json

from asd_kontur.assistant.reasoning import SynthesizedAnswer
from asd_kontur.assistant.worker import (
    _answer_budget,
    _tool_results_for_prompt,
    _with_structured_project_fact_checks,
)


def test_explicit_normative_question_has_budget_for_complete_evidence_bound_answer() -> None:
    assert _answer_budget("Что требует СП 70.13330.2012?", []) == 1_100


def test_unqualified_short_question_keeps_compact_answer_budget() -> None:
    assert _answer_budget("Что это?", []) == 520


def test_prompt_budget_keeps_evidence_identity_after_long_metadata() -> None:
    prompt = _tool_results_for_prompt(
        [
            {
                "step_sequence": 1,
                "tool": "consultant.get_workspace_overview",
                "reason": "Обзор.",
                "response": {
                    "metadata": "x" * 20_000,
                    "sources": [
                        {
                            "source_id": "evidence-1",
                            "source_version_id": "version-1",
                            "title": "Лист котлована",
                            "locator_label": "страница 17",
                            "page": 17,
                            "fragment": "Котлован К-1.",
                        }
                    ],
                },
            }
        ]
    )

    assert "evidence-1" in prompt
    assert "страница 17" in prompt
    assert "Котлован К-1" in prompt


def test_prompt_budget_prioritizes_structured_sheet_pile_facts_over_verbose_overview() -> None:
    prompt = _tool_results_for_prompt(
        [
            {
                "step_sequence": 1,
                "tool": "consultant.get_workspace_overview",
                "reason": "Общий обзор.",
                "response": {"metadata": "x" * 40_000, "sources": []},
            },
            {
                "step_sequence": 2,
                "tool": "consultant.get_work_packages",
                "reason": "Шпунтовые работы.",
                "response": {
                    "value": {
                        "project_engineering": {
                            "sheet_pile_answer_facts": [
                                {
                                    "operation": "Устройство распределительного пояса",
                                    "waling_beams": ["30Ш2", "35Ш2"],
                                    "quantities_by_document": {
                                        "Смета": [{"value": "9.841", "unit": "т"}]
                                    },
                                }
                            ],
                            "verbose_tail": "y" * 20_000,
                        }
                    },
                    "sources": [
                        {
                            "source_id": "waling-source",
                            "source_version_id": "waling-version",
                            "title": "Смета",
                            "locator_label": "страница 32",
                            "page": 32,
                            "fragment": "Распределительный пояс 9,841 т.",
                        }
                    ],
                },
            },
        ]
    )

    assert prompt.index("9.841") < prompt.index("xxxxxxxxxx")
    assert "30Ш2" in prompt
    assert "35Ш2" in prompt
    assert "waling-source" in prompt
    assert len(prompt) <= 14_000


def test_requested_structured_waling_facts_cannot_be_omitted_or_contradicted() -> None:
    receipts = [
        {
            "tool": "consultant.get_work_packages",
            "response": {
                "value": {
                    "project_engineering": {
                        "sheet_pile_answer_facts": [
                            {
                                "operation": "Устройство распределительного пояса",
                                "waling_beams": ["30Ш2", "35Ш2"],
                                "quantities_by_document": {
                                    "Смета": [{"value": "9.841", "unit": "т"}]
                                },
                            }
                        ]
                    }
                }
            },
        }
    ]
    answer = SynthesizedAnswer(
        "Профили балок в документах не указаны.",
        "workspace_conclusion",
        False,
        (),
        "Пояса шпунтового ограждения.",
        ("распределительный пояс",),
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=answer,
        receipts=receipts,
        question="Каковы объём и профили распределительного пояса?",
    )

    assert checks["passed"] is False
    assert "workspace_structured_fact_omitted" in checks["problems"]
    assert "workspace_structured_fact_contradicted" in checks["problems"]


def test_requested_structured_waling_facts_pass_when_answered() -> None:
    receipts = [
        {
            "tool": "consultant.get_work_packages",
            "response": {
                "value": {
                    "project_engineering": {
                        "sheet_pile_answer_facts": [
                            {
                                "operation": "Устройство обвязочного пояса",
                                "waling_beams": ["30Ш2", "35Ш2"],
                                "quantities_by_document": {
                                    "Смета": [{"value": "9.841", "unit": "т"}]
                                },
                            }
                        ]
                    }
                }
            },
        }
    ]
    answer = SynthesizedAnswer(
        "По смете учтено 9,841 т поясов из балок 30Ш2 и 35Ш2.",
        "workspace_conclusion",
        False,
        (),
        "Пояса шпунтового ограждения.",
        ("обвязочный пояс",),
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=answer,
        receipts=receipts,
        question="Каковы объём и профили обвязочного пояса?",
    )

    assert checks == {"passed": True, "problems": []}


def test_inventory_prompt_preserves_all_candidates_as_structured_json() -> None:
    candidates = [
        {
            "canonical_label": f"Котлован К-{index}",
            "associated_facility_designation": f"ЛОС-{index}",
            "status": "требует подтверждения",
            "authority": "candidate_only_not_confirmed_distinct_project_entity",
            "source_ids": [f"source-{index}"],
        }
        for index in range(1, 31)
    ]
    sources = [
        {
            "source_id": f"source-{index}",
            "source_version_id": f"version-{index}",
            "title": f"Рабочий чертёж {index}",
            "locator_label": f"лист {index}",
            "page": index,
            "fragment": "Привязка котлована. " * 100,
        }
        for index in range(1, 31)
    ]
    prompt = _tool_results_for_prompt(
        [
            {
                "step_sequence": 1,
                "tool": "consultant.get_workspace_overview",
                "reason": "Verbose metadata first.",
                "response": {"metadata": "x" * 40_000, "sources": []},
            },
            {
                "step_sequence": 2,
                "tool": "consultant.get_project_entity_inventory",
                "reason": "Complete inventory.",
                "response": {
                    "contract": "construction-consultant-tools@2.8.0",
                    "outcome": "found",
                    "value": {
                        "candidate_entity_count": 30,
                        "returned_candidate_entity_count": 30,
                        "candidate_entities": candidates,
                        "candidate_dossiers": [{"payload": "y" * 20_000}],
                        "unresolved_observations": [{"payload": "z" * 20_000}],
                        "coverage": {
                            "candidate_page_complete": True,
                            "exact_total_supported": False,
                        },
                    },
                    "sources": sources,
                    "gaps": [],
                },
            },
        ]
    )

    parsed = json.loads(prompt)
    inventory = next(
        item for item in parsed if item["tool"] == "consultant.get_project_entity_inventory"
    )
    assert isinstance(inventory["result"], dict)
    assert inventory["result"]["prompt_projection"] == "project-entity-inventory-v1"
    returned = inventory["result"]["value"]["candidate_entities"]
    assert [item["canonical_label"] for item in returned] == [
        item["canonical_label"] for item in candidates
    ]
    assert returned[-1]["source_ids"] == ["source-30"]
    assert len(prompt) <= 14_000
    assert prompt.index("Котлован К-30") < prompt.index("xxxxxxxxxx")
    assert "yyyyyyyyyy" not in prompt
    assert "zzzzzzzzzz" not in prompt


def test_professional_pit_inventory_survives_prompt_projection() -> None:
    prompt = _tool_results_for_prompt(
        [
            {
                "step_sequence": 1,
                "tool": "consultant.get_project_entity_inventory",
                "reason": "Project pit inventory.",
                "response": {
                    "contract": "construction-consultant-tools@2.8.0",
                    "outcome": "found",
                    "value": {
                        "answer": (
                            "Подтверждены 2 отдельных котлована. Ещё одна группа требует уточнения."
                        ),
                        "established_count": 2,
                        "count_is_final": False,
                        "pits": [
                            {
                                "name": "котлован для ЛОС-3",
                                "related_facility": "ЛОС-3",
                                "source_locator_ids": ["source-a"],
                            },
                            {
                                "name": "котлован для КНС-7",
                                "related_facility": "КНС-7",
                                "source_locator_ids": ["source-b"],
                            },
                        ],
                        "requires_clarification": [
                            {
                                "description": "Котлованы под колодцы",
                                "reason": "Количество не указано поштучно",
                                "source_locator_ids": ["source-c"],
                            }
                        ],
                        "returned_pit_count": 2,
                        "total_established_pit_count": 2,
                        "returned_unresolved_group_count": 1,
                        "total_unresolved_group_count": 1,
                        "professional_scope": "project_excavation_pit_inventory",
                    },
                    "sources": [
                        {
                            "source_id": source_id,
                            "source_version_id": "version-1",
                            "title": "ПОС",
                            "locator_label": "лист 4",
                            "page": 4,
                            "fragment": "Размер котлована",
                        }
                        for source_id in ("source-a", "source-b", "source-c")
                    ],
                    "gaps": [],
                },
            }
        ]
    )

    inventory = json.loads(prompt)[0]
    assert inventory["result"]["prompt_projection"] == "project-pit-inventory-v1"
    assert inventory["result"]["value"]["established_count"] == 2
    assert [item["name"] for item in inventory["result"]["value"]["pits"]] == [
        "котлован для ЛОС-3",
        "котлован для КНС-7",
    ]
    assert (
        inventory["result"]["value"]["requires_clarification"][0]["description"]
        == "Котлованы под колодцы"
    )
