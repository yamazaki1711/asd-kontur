# ruff: noqa: RUF001 -- Cyrillic construction fixture is intentional.

import json

from asd_kontur.assistant.reasoning import SynthesizedAnswer
from asd_kontur.assistant.worker import (
    _answer_budget,
    _append_prepared_project_result,
    _direct_project_result_plan,
    _tool_results_for_prompt,
    _with_structured_project_fact_checks,
)


def test_explicit_normative_question_has_budget_for_complete_evidence_bound_answer() -> None:
    assert _answer_budget("Что требует СП 70.13330.2012?", []) == 1_100


def test_unqualified_short_question_keeps_compact_answer_budget() -> None:
    assert _answer_budget("Что это?", []) == 520


def test_prepared_project_discrepancy_question_uses_direct_professional_result() -> None:
    plan = _direct_project_result_plan(
        "Какие расхождения между проектом, ВОР и сметой установлены?"
    )

    assert plan is not None
    assert plan.intent == "workspace"
    assert [step.tool for step in plan.steps] == [
        "consultant.get_discrepancies",
        "consultant.search_workspace_documents",
    ]
    assert plan.steps[-1].arguments["limit"] == 10


def test_customer_questions_and_contractor_risks_use_prepared_project_result() -> None:
    questions = _direct_project_result_plan("Какие вопросы надо направить Заказчику?")
    risks = _direct_project_result_plan("Какие риски выявлены для Подрядчика?")

    assert questions is not None
    assert risks is not None
    assert [step.tool for step in questions.steps] == [step.tool for step in risks.steps]
    assert questions.steps[-1].arguments["query"] != risks.steps[-1].arguments["query"]


def test_sheet_pile_schedule_uses_direct_prepared_project_result() -> None:
    plan = _direct_project_result_plan(
        "Покажи все шпунтовые работы по сооружениям, включая пояса и профили."
    )

    assert plan is not None
    assert [step.tool for step in plan.steps] == [
        "consultant.get_work_packages",
        "consultant.get_discrepancies",
    ]
    assert plan.steps[0].arguments == {
        "query": "шпунтовые работы распределительные пояса",
        "limit": 20,
    }


def test_general_engineering_question_still_requires_model_planning() -> None:
    assert _direct_project_result_plan("Как выполнять бетонирование зимой?") is None


def test_prepared_discrepancies_complete_qwen_narrative_without_inventing_values() -> None:
    answer = SynthesizedAnswer(
        "Установлены расхождения по шпунту.",
        "workspace_conclusion",
        False,
        (),
        "Проверены расхождения.",
        ("ОЗЕРО",),
    )
    completed = _append_prepared_project_result(
        answer,
        [
            {
                "tool": "consultant.get_discrepancies",
                "response": {
                    "value": {
                        "project_engineering": {
                            "issues": [
                                {
                                    "location": "КНС 8.1",
                                    "subject": "Прокладка кабеля",
                                    "description": "ПД: 30 м; ВОР/Смета: 60 м.",
                                    "source_locator_ids": ["source-cable"],
                                },
                                {
                                    "location": "ЛОС 8.1",
                                    "subject": "Бетон В25",
                                    "description": "Проект F200, коммерческие документы F150.",
                                    "source_locator_ids": ["source-concrete"],
                                },
                            ]
                        }
                    },
                    "sources": [
                        {"source_id": "source-cable"},
                        {"source_id": "source-concrete"},
                    ],
                },
            }
        ],
        "Какие расхождения между проектом, ВОР и сметой установлены?",
    )

    assert "КНС 8.1 — Прокладка кабеля: ПД: 30 м; ВОР/Смета: 60 м." in completed.answer
    assert "ЛОС 8.1 — Бетон В25: Проект F200, коммерческие документы F150." in completed.answer
    assert completed.used_source_ids == ("source-cable", "source-concrete")


def test_prepared_sheet_pile_schedule_completes_qwen_narrative_with_exact_values() -> None:
    completed = _append_prepared_project_result(
        SynthesizedAnswer(
            "Шпунтовые работы предусмотрены для двух сооружений.",
            "workspace_conclusion",
            False,
            (),
            "Проверен шпунт.",
            ("ОЗЕРО",),
        ),
        [
            {
                "tool": "consultant.get_work_packages",
                "response": {
                    "value": {
                        "project_engineering": {
                            "sheet_pile_answer_facts": [
                                {
                                    "facility": "КНС 4",
                                    "pit": "котлован для КНС4",
                                    "operation": "Погружение шпунта",
                                    "profiles": ["Л5"],
                                    "quantities_by_document": {
                                        "ВОР": [{"value": "95.028", "unit": "т"}]
                                    },
                                    "source_refs": ["source-driving"],
                                },
                                {
                                    "facility": "КНС 8.1",
                                    "pit": "котлован для КНС8.1",
                                    "operation": "Устройство распределительного пояса",
                                    "waling_beams": ["30Ш2", "35Ш2"],
                                    "quantities_by_document": {
                                        "ВОР": [{"value": "9.841", "unit": "т"}]
                                    },
                                    "source_refs": ["source-belt"],
                                },
                            ]
                        }
                    },
                    "sources": [
                        {"source_id": "source-driving"},
                        {"source_id": "source-belt"},
                    ],
                },
            }
        ],
        "Покажи все шпунтовые работы по сооружениям, включая пояса и профили.",
    )

    assert "КНС 4; котлован для КНС4; Погружение шпунта" in completed.answer
    assert "профиль Л5; ВОР: 95.028 т" in completed.answer
    assert "КНС 8.1; котлован для КНС8.1; Устройство распределительного пояса" in completed.answer
    assert "балки 30Ш2, 35Ш2; ВОР: 9.841 т" in completed.answer
    assert completed.used_source_ids == ("source-driving", "source-belt")


def test_general_discrepancy_answer_does_not_require_unasked_sheet_pile_belts() -> None:
    receipt = {
        "tool": "consultant.get_discrepancies",
        "response": {
            "value": {
                "project_engineering": {
                    "sheet_pile_answer_facts": [
                        {
                            "operation": "Устройство распределительного пояса",
                            "waling_beams": ["30Ш2", "35Ш2"],
                            "quantities_by_document": {"ВОР": [{"value": "9.841", "unit": "т"}]},
                        }
                    ],
                    "issues": [
                        {
                            "location": "КНС 8.1",
                            "subject": "Прокладка кабеля",
                            "description": "ПД: 30 м; ВОР/Смета: 60 м.",
                        }
                    ],
                    "quantity_comparisons": [
                        {
                            "classification": "QUANTITY_DIFFERENCE",
                            "work": "Прокладка кабеля",
                            "professional_status": "Различается объём",
                            "left": {"document_role": "ПД", "value": "30", "unit": "м"},
                            "right": {"document_role": "ВОР", "value": "60", "unit": "м"},
                        }
                    ],
                }
            },
            "sources": [],
        },
    }
    answer = _append_prepared_project_result(
        SynthesizedAnswer(
            "Установлены расхождения.",
            "workspace_conclusion",
            False,
            (),
            "Расхождения.",
            (),
        ),
        [receipt],
        "Какие расхождения между проектом, ВОР и сметой установлены?",
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=answer,
        receipts=[receipt],
        question="Какие расхождения между проектом, ВОР и сметой установлены?",
    )

    assert checks["passed"]
    assert "30Ш2" not in answer.answer
    assert "9.841" not in answer.answer


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


def test_discrepancy_prompt_keeps_professional_issues_ahead_of_verbose_model() -> None:
    prompt = _tool_results_for_prompt(
        [
            {
                "step_sequence": 1,
                "tool": "consultant.get_discrepancies",
                "reason": "Расхождения проекта.",
                "response": {
                    "value": {
                        "project_engineering": {
                            "works": [{"payload": "x" * 30_000}],
                            "issues": [
                                {
                                    "location": "КНС 8.1",
                                    "subject": "Прокладка кабеля",
                                    "description": "ПД: 30 м; ВОР/Смета: 60 м.",
                                }
                            ],
                            "quantity_comparisons": [],
                        }
                    },
                    "sources": [],
                },
            }
        ]
    )

    assert "КНС 8.1" in prompt
    assert "ПД: 30 м; ВОР/Смета: 60 м" in prompt
    assert "xxxxxxxxxx" not in prompt
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


def test_requested_sheet_pile_profile_and_steel_cannot_be_omitted() -> None:
    receipts = [
        {
            "tool": "consultant.get_work_packages",
            "response": {
                "value": {
                    "project_engineering": {
                        "sheet_pile_answer_facts": [
                            {
                                "operation": "Погружение шпунта",
                                "profiles": ["Л5УМ"],
                                "steel": ["С255"],
                                "quantities_by_document": {"ВОР": [{"value": "41.7", "unit": "т"}]},
                            }
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "Проектом предусмотрено шпунтовое ограждение.",
        "workspace_conclusion",
        False,
        (),
        "Шпунтовое ограждение.",
        ("шпунт",),
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Какой профиль шпунта и марка стали предусмотрены?",
    )

    assert checks["passed"] is False
    assert "workspace_structured_fact_omitted" in checks["problems"]

    complete = SynthesizedAnswer(
        "В проекте указан шпунт профиля Л5УМ из стали С255.",
        "workspace_conclusion",
        False,
        (),
        "Шпунтовое ограждение.",
        ("шпунт", "Л5УМ", "С255"),
    )
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Какой профиль шпунта и марка стали предусмотрены?",
    ) == {"passed": True, "problems": []}


def test_broad_sheet_pile_scope_requires_associated_belt_quantity_and_beams() -> None:
    receipts = [
        {
            "tool": "consultant.get_work_packages",
            "response": {
                "value": {
                    "project_engineering": {
                        "sheet_pile_answer_facts": [
                            {
                                "operation": "Устройство шпунтового ограждения",
                                "waling_beams": ["30Ш2", "35Ш2"],
                                "quantities_by_document": {
                                    "Смета": [{"value": "95.028", "unit": "т"}]
                                },
                            },
                            {
                                "operation": "Устройство распределительного пояса",
                                "waling_beams": [],
                                "quantities_by_document": {
                                    "Смета": [{"value": "9.841", "unit": "т"}]
                                },
                            },
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "Предусмотрено погружение и извлечение шпунта.",
        "workspace_conclusion",
        False,
        (),
        "Шпунтовые работы.",
        ("шпунт",),
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Покажи все шпунтовые работы и где они выполняются.",
    )

    assert checks["passed"] is False
    assert "workspace_structured_fact_omitted" in checks["problems"]

    complete = SynthesizedAnswer(
        "Помимо погружения и извлечения шпунта, по смете предусмотрено 9,841 т "
        "распределительных поясов из балок 30Ш2 и 35Ш2.",
        "workspace_conclusion",
        False,
        (),
        "Шпунтовые работы.",
        ("шпунт", "распределительный пояс"),
    )
    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Покажи все шпунтовые работы и где они выполняются.",
    )

    assert checks == {"passed": True, "problems": []}


def test_requested_project_comparison_cannot_omit_validated_values() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "quantity_comparisons": [
                            {
                                "work": "Демонтаж светильников",
                                "professional_status": "Значения совпадают",
                                "left": {"document_role": "ПД", "value": "3", "unit": "шт"},
                                "right": {
                                    "document_role": "Смета",
                                    "value": "3",
                                    "unit": "шт",
                                },
                            }
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "Расхождений не найдено.",
        "workspace_conclusion",
        False,
        (),
        "Сравнение объёмов.",
        (),
    )

    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Какие объёмы расходятся между ПД и сметой?",
    )
    assert "workspace_structured_fact_omitted" in checks["problems"]

    complete = SynthesizedAnswer(
        "Для работы «Демонтаж светильников» ПД и Смета содержат 3 шт.; значения совпадают.",
        "workspace_conclusion",
        False,
        (),
        "Сравнение объёмов.",
        (),
    )
    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Какие объёмы расходятся между ПД и сметой?",
    )
    assert checks == {"passed": True, "problems": []}


def test_discrepancy_question_requires_differences_without_forcing_matches() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "quantity_comparisons": [
                            {
                                "work": "Прокладка кабеля",
                                "classification": "QUANTITY_DIFFERENCE",
                                "professional_status": "Различается объём",
                                "left": {"document_role": "ПД", "value": "30", "unit": "м"},
                                "right": {"document_role": "ВОР", "value": "60", "unit": "м"},
                            },
                            {
                                "work": "Погружение шпунта",
                                "classification": "MATCH",
                                "professional_status": "Значения совпадают",
                                "left": {"document_role": "ВОР", "value": "95.028", "unit": "т"},
                                "right": {
                                    "document_role": "Смета",
                                    "value": "95.028",
                                    "unit": "т",
                                },
                            },
                        ]
                    }
                },
            },
        }
    ]
    answer = SynthesizedAnswer(
        "Прокладка кабеля: ПД содержит 30 м, а ВОР — 60 м. Различается объём.",
        "workspace_conclusion",
        False,
        (),
        "Расхождение объёма.",
        (),
    )

    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=answer,
        receipts=receipts,
        question="Какие объёмы расходятся между ПД и ВОР?",
    ) == {"passed": True, "problems": []}


def test_project_discrepancy_question_requires_material_profile_and_omission_facts() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "issues": [
                            {
                                "kind": "Профиль шпунта требует согласования",
                                "location": "КНС 8.1",
                                "subject": "Профиль шпунта",
                                "description": "ПД: Л5УМ; ВОР: Л5-10; Смета: Л5УМ.",
                            },
                            {
                                "kind": "Возможная неучтённая работа",
                                "location": "ЛОС 8.1",
                                "subject": "Устройство шпунтового ограждения",
                                "description": "Работа отсутствует в ВОР и смете.",
                            },
                            {
                                "kind": "Различие характеристик материала",
                                "location": "ЛОС 8.1",
                                "subject": "Бетон В25",
                                "description": "Проект F200, коммерческие документы F150.",
                            },
                        ],
                        "material_comparisons": [
                            {
                                "material": "Бетон В25",
                                "description": "Проект F200, коммерческие документы F150.",
                            }
                        ],
                        "quantity_comparisons": [],
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "По КНС 8.1 есть вопрос по профилю шпунта.",
        "workspace_conclusion",
        False,
        (),
        "Расхождения.",
        (),
    )
    complete = SynthesizedAnswer(
        (
            "КНС 8.1: ПД — Л5УМ, ВОР — Л5-10. ЛОС 8.1: устройство шпунтового "
            "ограждения отсутствует в коммерческих документах; бетон В25 имеет F200 "
            "в проекте и F150 в коммерческих документах."
        ),
        "workspace_conclusion",
        False,
        (),
        "Расхождения.",
        (),
    )

    question = "Какие реальные расхождения между проектом, ВОР и сметой установлены?"
    assert not _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question=question,
    )["passed"]
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question=question,
    ) == {"passed": True, "problems": []}


def test_requested_material_difference_cannot_omit_known_grades() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "material_comparisons": [
                            {
                                "facility": "Участок 17",
                                "material": "Бетон В25",
                                "description": (
                                    "морозостойкость: проект F200, коммерческие документы F150."
                                ),
                            }
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "Материалы требуют уточнения.",
        "workspace_conclusion",
        False,
        (),
        "Сравнение материалов.",
        ("материалы",),
    )
    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Какие материалы расходятся между документами?",
    )
    assert checks["passed"] is False
    assert "workspace_structured_fact_omitted" in checks["problems"]

    complete = SynthesizedAnswer(
        "Для бетона В25 в проекте указано F200, а в ВОР — F150.",
        "workspace_conclusion",
        False,
        (),
        "Сравнение материалов.",
        ("бетон В25", "F200", "F150"),
    )
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Какие материалы расходятся между документами?",
    ) == {"passed": True, "problems": []}


def test_requested_facility_work_inventory_cannot_be_silently_shortened() -> None:
    receipts = [
        {
            "tool": "consultant.get_work_packages",
            "response": {
                "value": {
                    "project_engineering": {
                        "facility_dossiers": [
                            {
                                "facility": {"name": "КНС 17"},
                                "work_names": [
                                    "Разработка котлована",
                                    "Погружение шпунта",
                                ],
                                "work_count": 2,
                            }
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "На КНС-17 выполняется разработка котлована.",
        "workspace_conclusion",
        False,
        (),
        "Работы КНС-17.",
        (),
    )
    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Какие работы выполняются на КНС-17?",
    )
    assert checks["passed"] is False
    assert "workspace_structured_fact_omitted" in checks["problems"]

    complete = SynthesizedAnswer(
        "Установлены 2 работы: разработка котлована и погружение шпунта.",
        "workspace_conclusion",
        False,
        (),
        "Работы КНС-17.",
        (),
    )
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Какие работы выполняются на КНС-17?",
    ) == {"passed": True, "problems": []}


def test_requested_missing_commercial_work_keeps_facility_and_work() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "scope_comparisons": [
                            {
                                "classification": "WORK_MISSING_IN_COMMERCIAL",
                                "facility": "Участок 17",
                                "work": "Устройство шпунтового ограждения",
                            }
                        ]
                    }
                }
            },
        }
    ]
    incomplete = SynthesizedAnswer(
        "В коммерческих документах есть пробел.",
        "workspace_conclusion",
        False,
        (),
        "Неучтённые работы.",
        (),
    )
    checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=incomplete,
        receipts=receipts,
        question="Какие работы отсутствуют в ВОР или смете?",
    )
    assert checks["passed"] is False

    complete = SynthesizedAnswer(
        "На участке 17 в ВОР/смете отсутствует устройство шпунтового ограждения.",
        "workspace_conclusion",
        False,
        (),
        "Неучтённые работы.",
        (),
    )
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete,
        receipts=receipts,
        question="Какие работы отсутствуют в ВОР или смете?",
    ) == {"passed": True, "problems": []}


def test_project_customer_questions_and_contractor_risks_cannot_be_silently_shortened() -> None:
    receipts = [
        {
            "tool": "consultant.get_discrepancies",
            "response": {
                "value": {
                    "project_engineering": {
                        "customer_questions": [
                            {"question": "Просим распределить объём шпунта по сооружениям."},
                            {"question": "Просим подтвердить профиль Л5УМ для КНС-4."},
                        ],
                        "risks": [
                            {"risk": "Часть шпунтовых работ может остаться нерасценённой."},
                            {"risk": "Замена профиля может изменить массу ограждения."},
                        ],
                    }
                }
            },
        }
    ]
    shortened = SynthesizedAnswer(
        "Следует уточнить объём шпунта.",
        "workspace_conclusion",
        False,
        (),
        "Вопросы и риски проекта.",
        ("шпунт",),
    )

    question_checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=shortened,
        receipts=receipts,
        question="Какие вопросы надо направить Заказчику?",
    )
    risk_checks = _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=shortened,
        receipts=receipts,
        question="Какие риски для Подрядчика выявлены по проекту?",
    )

    assert "workspace_customer_question_omitted" in question_checks["problems"]
    assert "workspace_contractor_risk_omitted" in risk_checks["problems"]

    complete_questions = SynthesizedAnswer(
        "Просим распределить объём шпунта по сооружениям. "
        "Просим подтвердить профиль Л5УМ для КНС-4.",
        "workspace_conclusion",
        False,
        (),
        "Вопросы Заказчику.",
        ("шпунт",),
    )
    complete_risks = SynthesizedAnswer(
        "Часть шпунтовых работ может остаться нерасценённой. "
        "Замена профиля может изменить массу ограждения.",
        "workspace_conclusion",
        False,
        (),
        "Риски Подрядчика.",
        ("шпунт",),
    )
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete_questions,
        receipts=receipts,
        question="Какие вопросы надо направить Заказчику?",
    ) == {"passed": True, "problems": []}
    assert _with_structured_project_fact_checks(
        {"passed": True, "problems": []},
        answer=complete_risks,
        receipts=receipts,
        question="Какие риски для Подрядчика выявлены по проекту?",
    ) == {"passed": True, "problems": []}


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
                                "related_works": [
                                    {
                                        "work": "Погружение шпунта",
                                        "quantities_by_document": {
                                            "РД": [{"value": "42", "unit": "т"}]
                                        },
                                    }
                                ],
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
    assert inventory["result"]["value"]["pits"][0]["related_works"] == [
        {
            "work": "Погружение шпунта",
            "quantities_by_document": {"РД": [{"value": "42", "unit": "т"}]},
        }
    ]
    assert (
        inventory["result"]["value"]["requires_clarification"][0]["description"]
        == "Котлованы под колодцы"
    )
