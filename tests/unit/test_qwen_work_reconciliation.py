# ruff: noqa: RUF001 -- Russian construction fixtures are intentional.

from __future__ import annotations

import json
from typing import Any

from asd_kontur.tender.qwen_work_reconciliation import (
    QwenProjectWorkReconciler,
    potential_work_description,
)


def test_qwen_work_reconciliation_preserves_exact_rows_and_allowed_scope(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert "КНС-4" in prompt
        assert "backfill" in prompt
        assert max_tokens >= 1_400
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-a",
                        "status": "MATCHED",
                        "family_key": "backfill",
                        "operation": "Послойное уплотнение обратной засыпки",
                        "facility": "КНС-4",
                        "confidence": "0.91",
                        "reason": "Работа и сооружение указаны явно.",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [{"candidate_id": "candidate-a", "wording": "Уплотнение засыпки КНС-4"}],
        work_families={"backfill": "Обратная засыпка и уплотнение"},
        facilities=["КНС-4"],
    )

    assert result["observations"] == [
        {
            "candidate_id": "candidate-a",
            "status": "MATCHED",
            "family_key": "backfill",
            "operation": "Послойное уплотнение обратной засыпки",
            "facility": "КНС-4",
            "confidence": "0.91",
            "reason": "Работа и сооружение указаны явно.",
        }
    ]


def test_qwen_work_reconciliation_preserves_full_wording_and_context_locators(
    monkeypatch: Any,
) -> None:
    long_tail = "конец полного описания после прежней границы"
    wording = "Устройство специальной конструкции " + ("очень подробно " * 70) + long_tail

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert long_tail in prompt
        assert "locator-before" in prompt
        assert "КНС 4" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-long",
                        "status": "UNCLASSIFIED",
                        "family_key": None,
                        "operation": None,
                        "facility": None,
                        "confidence": "0.55",
                        "reason": "Семейство не установлено без догадки.",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "candidate-long",
                "wording": wording,
                "nearby_context": "КНС 4. Рабочий чертёж.",
                "nearby_context_locator_ids": ["locator-before", "locator-current"],
            }
        ],
        work_families={"temporary_works": "Временные сооружения"},
        facilities=["КНС 4"],
    )

    assert result["profile_version"] == "qwen-project-work-reconciliation-v16"


def test_quantity_relationship_prompt_requires_explicit_same_scope_decision(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "даже когда сами числа" in prompt
        assert "дословно одинаковый краткий" in prompt
        assert "DUPLICATE_OF означает именно повтор" in prompt
        assert "relation_kind всегда должен быть одним" in prompt
        assert "relation_kind верните null" not in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "design",
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Обмазочная гидроизоляция",
                        "facility": None,
                        "confidence": "0.93",
                        "reason": "Проектная строка.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "design-q",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь обмазочной гидроизоляции",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": "Тот же инженерный объём.",
                            }
                        ],
                    },
                    {
                        "candidate_id": "commercial",
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Обмазочная гидроизоляция",
                        "facility": None,
                        "confidence": "0.93",
                        "reason": "Коммерческая строка.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "commercial-q",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь обмазочной гидроизоляции",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": "Тот же инженерный объём.",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    rows = [
        {
            "candidate_id": "design",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Площадь обмазочной гидроизоляции",
            "document_role": "ПД",
            "quantity_observations": [
                {"quantity_candidate_id": "design-q", "value": "830.4", "unit": "m2"}
            ],
        },
        {
            "candidate_id": "commercial",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Обмазочная гидроизоляция",
            "document_role": "ВОР",
            "quantity_observations": [
                {"quantity_candidate_id": "commercial-q", "value": "833.9", "unit": "m2"}
            ],
        },
    ]

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    reviews = [observation["quantity_reviews"][0] for observation in result["observations"]]
    assert {review["semantic_scope"] for review in reviews} == {"Площадь обмазочной гидроизоляции"}
    assert {review["scope_compatibility"] for review in reviews} == {"SAME_SCOPE"}


def test_qwen_work_reconciliation_budgets_complete_twelve_row_json(
    monkeypatch: Any,
) -> None:
    rows = [
        {"candidate_id": f"candidate-{index}", "wording": f"Монтаж конструкции {index}"}
        for index in range(12)
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert max_tokens == 3_840
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "UNCLASSIFIED",
                        "family_key": None,
                        "operation": None,
                        "facility": None,
                        "confidence": "0.5",
                        "reason": "Недостаточно контекста для классификации.",
                    }
                    for row in rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"structural_steel": "Металлоконструкции"},
        facilities=[],
    )

    assert result["inference_call_count"] == 1
    assert result["recovery_codes"] == []


def test_quantity_relationship_review_uses_relationship_sized_output_budget(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": f"candidate-{index}",
            "wording": f"Устройство участка {index}",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "quantity_observations": [
                {
                    "quantity_candidate_id": f"quantity-{index}",
                    "value": str(index + 1),
                    "unit": "m",
                }
            ],
        }
        for index in range(8)
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert max_tokens == 4_320
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "pipeline",
                        "operation": "Монтаж участка трубопровода",
                        "facility": None,
                        "confidence": "0.9",
                        "reason": "Строка прямо описывает монтаж участка.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина отдельного участка трубопровода",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": None,
                                "reason": "Итоговый объём в пакете не указан.",
                            }
                        ],
                    }
                    for row in rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"pipeline": "Трубопроводы"},
        facilities=[],
    )

    assert result["inference_call_count"] == 1
    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_qwen_work_reconciliation_classifies_linked_quantity_meaning(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert "quantity-volume" in prompt
        assert "quantity-depth" in prompt
        assert max_tokens >= 1_400
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-excavation",
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка котлована",
                        "facility": "КНС-4",
                        "confidence": "0.94",
                        "reason": "Операция и сооружение указаны явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-volume",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Объём разработки грунта в котловане",
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "reason": "Значение указано как объём разработки грунта.",
                            },
                            {
                                "quantity_candidate_id": "quantity-depth",
                                "status": "DIMENSION",
                                "semantic_scope": "Глубина котлована",
                                "quantity_type": "DIMENSION",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "DIFFERENT_SCOPE",
                                "reason": "Значение является глубиной котлована.",
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "candidate-excavation",
                "wording": "Разработка котлована КНС-4",
                "quantity_observations": [
                    {"quantity_candidate_id": "quantity-volume", "value": "827.5", "unit": "м3"},
                    {"quantity_candidate_id": "quantity-depth", "value": "5", "unit": "м"},
                ],
            }
        ],
        work_families={"excavation": "Разработка котлованов и земляные работы"},
        facilities=["КНС-4"],
    )

    assert result["observations"][0]["quantity_reviews"] == [
        {
            "quantity_candidate_id": "quantity-volume",
            "status": "WORK_QUANTITY",
            "semantic_scope": "Объём разработки грунта в котловане",
            "quantity_type": "STANDALONE",
            "relation_kind": "NONE",
            "related_quantity_candidate_ids": [],
            "scope_compatibility": "SAME_SCOPE",
            "reason": "Значение указано как объём разработки грунта.",
        },
        {
            "quantity_candidate_id": "quantity-depth",
            "status": "DIMENSION",
            "semantic_scope": "Глубина котлована",
            "quantity_type": "DIMENSION",
            "relation_kind": "NONE",
            "related_quantity_candidate_ids": [],
            "scope_compatibility": "DIFFERENT_SCOPE",
            "reason": "Значение является глубиной котлована.",
        },
    ]


def test_qwen_work_reconciliation_allows_explicit_cross_row_quantity_relation(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": "candidate-total",
            "wording": "Общая длина трубопровода",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-total", "value": "150", "unit": "м"}
            ],
        },
        {
            "candidate_id": "candidate-section",
            "wording": "Длина участка А",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-section", "value": "120", "unit": "м"}
            ],
        },
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-total",
                        "status": "MATCHED",
                        "family_key": "pipeline_installation",
                        "operation": "Общая длина трубопровода",
                        "facility": "Переход А",
                        "confidence": "0.92",
                        "reason": "Итог и сооружение указаны явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общая длина трубопровода",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": ["quantity-section"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": True,
                                "reason": "Таблица обозначает значение как общий итог.",
                            }
                        ],
                    },
                    {
                        "candidate_id": "candidate-section",
                        "status": "MATCHED",
                        "family_key": "pipeline_installation",
                        "operation": "Монтаж участка трубопровода",
                        "facility": "Переход А",
                        "confidence": "0.91",
                        "reason": "Участок и сооружение указаны явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-section",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина участка А",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": None,
                                "reason": "Строка является частью общего итога.",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"pipeline_installation": "Монтаж трубопроводов"},
        facilities=["Переход А"],
    )

    total_review = result["observations"][0]["quantity_reviews"][0]
    assert total_review["related_quantity_candidate_ids"] == ["quantity-section"]


def test_quantity_relationship_task_marks_dedicated_review(monkeypatch: Any) -> None:
    rows = [
        {
            "candidate_id": "candidate-total",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Общий объём разработки грунта",
            "deterministic_family_hint": "excavation",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "quantity-total",
                    "value": "125",
                    "unit": "м3",
                    "prior_semantic_scope": "Объём разработки грунта",
                    "prior_quantity_type": "STANDALONE",
                    "prior_status": "WORK_QUANTITY",
                }
            ],
        },
        {
            "candidate_id": "candidate-component",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Механизированная разработка грунта",
            "deterministic_family_hint": "excavation",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "quantity-component",
                    "value": "100",
                    "unit": "м3",
                    "prior_semantic_scope": "Механизированная разработка грунта",
                    "prior_quantity_type": "STANDALONE",
                    "prior_status": "WORK_QUANTITY",
                }
            ],
        },
    ]

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "QUANTITY_RELATIONSHIP_ANALYSIS" in prompt
        assert "prior_semantic_scope" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-total",
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка грунта",
                        "facility": "Сооружение 7",
                        "confidence": "0.93",
                        "reason": "Переданная операция сохранена.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общий объём разработки грунта",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": ["quantity-component"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": True,
                                "reason": "Значение обозначено как общий итог.",
                            }
                        ],
                    },
                    {
                        "candidate_id": "candidate-component",
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка грунта",
                        "facility": "Сооружение 7",
                        "confidence": "0.92",
                        "reason": "Переданная операция сохранена.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-component",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Механизированная разработка грунта",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": None,
                                "reason": "Строка является составляющей общего объёма.",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"excavation": "Земляные работы"},
        facilities=["Сооружение 7"],
    )

    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_quantity_relationship_task_preserves_incomplete_component_set(monkeypatch: Any) -> None:
    rows = [
        {
            "candidate_id": "candidate-total",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Общий объём земляных работ",
            "deterministic_family_hint": "excavation",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-total", "value": "250", "unit": "м3"}
            ],
        },
        {
            "candidate_id": "candidate-part",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Ручная разработка грунта",
            "deterministic_family_hint": "excavation",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-part", "value": "40", "unit": "м3"}
            ],
        },
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-total",
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка грунта",
                        "facility": None,
                        "confidence": "0.91",
                        "reason": "Указан общий объём.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общий объём разработки грунта",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": ["quantity-part"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": False,
                                "reason": (
                                    "Передана только ручная часть; механизированная часть "
                                    "отсутствует."
                                ),
                            }
                        ],
                    },
                    {
                        "candidate_id": "candidate-part",
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка грунта",
                        "facility": None,
                        "confidence": "0.91",
                        "reason": "Указана ручная часть.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-part",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Ручная разработка грунта",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": None,
                                "reason": "Это одна из составляющих общего объёма.",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"excavation": "Земляные работы"},
        facilities=[],
    )

    total_review = result["observations"][0]["quantity_reviews"][0]
    assert total_review["relationship_reviewed"] is True
    assert total_review["component_set_complete"] is False


def test_split_quantity_batch_is_not_certified_as_complete_relationship_review(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "excavation",
            "quantity_observations": [
                {
                    "quantity_candidate_id": quantity_id,
                    "value": value,
                    "unit": "м3",
                }
            ],
        }
        for candidate_id, quantity_id, wording, value in (
            ("candidate-total", "quantity-total", "Общий объём грунта", "125"),
            ("candidate-part", "quantity-part", "Разработка грунта на участке", "100"),
        )
    ]

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        present = [row for row in rows if row["candidate_id"] in prompt]
        if len(present) == 2:
            return '{"observations": ['
        row = present[0]
        quantity = row["quantity_observations"][0]
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "excavation",
                        "operation": "Разработка грунта",
                        "facility": None,
                        "confidence": "0.85",
                        "reason": (
                            "Строительная операция установлена, связь требует полного пакета."
                        ),
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": quantity["quantity_candidate_id"],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": row["wording"],
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "reason": "В разделённом контексте связь не установлена.",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"excavation": "Земляные работы"},
        facilities=[],
    )

    assert result["inference_call_count"] == 3
    assert all(
        "relationship_reviewed" not in review
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_qwen_work_reconciliation_rejects_invented_cross_row_quantity_identity(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_work_reconciliation._complete",
        lambda *_args, **_kwargs: json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-total",
                        "status": "MATCHED",
                        "family_key": "pipeline_installation",
                        "operation": "Общая длина трубопровода",
                        "facility": None,
                        "confidence": "0.9",
                        "reason": "Общий итог указан явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общая длина трубопровода",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": ["invented-quantity"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "reason": "Связь заявлена моделью.",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "candidate-total",
                "wording": "Общая длина трубопровода",
                "quantity_observations": [
                    {"quantity_candidate_id": "quantity-total", "value": "150", "unit": "м"}
                ],
            }
        ],
        work_families={"pipeline_installation": "Монтаж трубопроводов"},
        facilities=[],
    )

    assert result["observations"][0]["status"] == "UNCLASSIFIED"
    assert result["observations"][0]["quantity_reviews"][0]["relation_kind"] == "NONE"
    assert result["observations"][0]["quantity_reviews"][0]["related_quantity_candidate_ids"] == []
    assert "qwen_work_reconciliation_quantity_output_invalid" in result["recovery_codes"]


def test_qwen_work_reconciliation_preserves_input_when_model_invents_identity(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_work_reconciliation._complete",
        lambda *_args, **_kwargs: json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "invented",
                        "status": "MATCHED",
                        "family_key": "backfill",
                        "operation": "Обратная засыпка",
                        "facility": None,
                        "confidence": "0.8",
                        "reason": "Описание похоже на работу.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [{"candidate_id": "candidate-a", "wording": "Обратная засыпка"}],
        work_families={"backfill": "Обратная засыпка и уплотнение"},
        facilities=[],
    )

    assert result["observations"][0]["candidate_id"] == "candidate-a"
    assert result["observations"][0]["status"] == "UNCLASSIFIED"
    assert "invented" not in json.dumps(result, ensure_ascii=False)
    assert result["recovery_codes"][-1] == ("qwen_work_reconciliation_observation_unresolved")


def test_qwen_work_reconciliation_cannot_hide_potential_commercial_work(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_work_reconciliation._complete",
        lambda *_args, **_kwargs: json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-a",
                        "status": "NOT_A_WORK",
                        "family_key": None,
                        "operation": None,
                        "facility": None,
                        "confidence": "0.95",
                        "reason": "Недостаточно контекста.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [{"candidate_id": "candidate-a", "wording": "Геодезическая разбивка"}],
        work_families={"surveying": "Геодезические работы"},
        facilities=[],
    )

    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_potential_work_excluded",
        "qwen_work_reconciliation_potential_work_excluded",
        "qwen_work_reconciliation_observation_unresolved",
    ]
    assert result["observations"] == [
        {
            "candidate_id": "candidate-a",
            "status": "UNCLASSIFIED",
            "family_key": None,
            "operation": None,
            "facility": None,
            "confidence": "0",
            "reason": (
                "Интерпретация не принята после ограниченного повтора; описание сохранено "
                "для последующего уточнения "
                "(qwen_work_reconciliation_potential_work_excluded)."
            ),
        }
    ]


def test_explicit_installation_and_excluded_commercial_work_remain_work_candidates() -> None:
    assert potential_work_description("установка трубопровода откачки из нержавеющей стали")
    assert potential_work_description("Электромонтажные работы по прокладке кабеля")
    assert potential_work_description("Шеф-монтажные работы")
    assert not potential_work_description("Напорный трубопровод с задвижками")


def test_qwen_work_reconciliation_allows_component_with_mounting_attribute(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_work_reconciliation._complete",
        lambda *_args, **_kwargs: json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-a",
                        "status": "NOT_A_WORK",
                        "family_key": None,
                        "operation": None,
                        "facility": None,
                        "confidence": "0.95",
                        "reason": "Направляющие являются компонентом оборудования.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "candidate-a",
                "wording": "Направляющие для насоса погружного монтажа",
            }
        ],
        work_families={"equipment_installation": "Монтаж технологического оборудования"},
        facilities=[],
    )

    assert result["observations"][0]["status"] == "NOT_A_WORK"


def test_qwen_work_reconciliation_discards_weak_facility_proximity_but_keeps_work(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "asd_kontur.tender.qwen_work_reconciliation._complete",
        lambda *_args, **_kwargs: json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-a",
                        "status": "MATCHED",
                        "family_key": "demolition",
                        "operation": "Демонтаж трубы",
                        "facility": "ЛОС 8.1",
                        "confidence": "0.82",
                        "reason": (
                            "ЛОС 8.1 упомянута в том же абзаце, и близость объектов "
                            "позволяет связать работу."
                        ),
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [{"candidate_id": "candidate-a", "wording": "Демонтаж трубы"}],
        work_families={"demolition": "Демонтажные работы"},
        facilities=["ЛОС 8.1"],
    )

    observation = result["observations"][0]
    assert observation["status"] == "MATCHED"
    assert observation["facility"] is None


def test_qwen_work_reconciliation_discards_unestablished_facility_but_keeps_semantics(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "steel-columns",
                        "status": "MATCHED",
                        "family_key": "structural_steel",
                        "operation": "Монтаж стальных колонн",
                        "facility": "Навес N-12",
                        "confidence": "0.94",
                        "reason": "Работа относится к каркасу навеса.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "steel-columns-q",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Масса стальных колонн",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "reason": "Значение относится к колоннам.",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "steel-columns",
                "wording": "Монтаж стальных колонн",
                "quantity_observations": [
                    {"quantity_candidate_id": "steel-columns-q", "value": "7.6", "unit": "t"}
                ],
            }
        ],
        work_families={"structural_steel": "Металлоконструкции"},
        facilities=[],
    )

    observation = result["observations"][0]
    assert observation["status"] == "MATCHED"
    assert observation["family_key"] == "structural_steel"
    assert observation["facility"] is None
    assert observation["quantity_reviews"][0]["semantic_scope"] == "Масса стальных колонн"
    assert "отсутствует в установленном составе объекта" in observation["reason"]
    assert "Привязка к сооружению не принята" in observation["reason"]


def test_qwen_work_reconciliation_subdivides_only_a_malformed_batch(
    monkeypatch: Any,
) -> None:
    calls: list[list[str]] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        ids = [value for value in ("candidate-a", "candidate-b") if value in prompt]
        calls.append(ids)
        if len(ids) == 2:
            return '{"observations": ['
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": ids[0],
                        "status": "MATCHED",
                        "family_key": "backfill",
                        "operation": "Обратная засыпка",
                        "facility": None,
                        "confidence": "0.9",
                        "reason": "Описание прямо называет работу.",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {"candidate_id": "candidate-a", "wording": "Обратная засыпка"},
            {"candidate_id": "candidate-b", "wording": "Засыпка траншеи"},
        ],
        work_families={"backfill": "Обратная засыпка"},
        facilities=[],
    )

    assert [item["candidate_id"] for item in result["observations"]] == [
        "candidate-a",
        "candidate-b",
    ]
    assert result["inference_call_count"] == 3
    assert result["recovery_codes"] == ["qwen_work_reconciliation_invalid_json"]
    assert calls == [
        ["candidate-a", "candidate-b"],
        ["candidate-a"],
        ["candidate-b"],
    ]
