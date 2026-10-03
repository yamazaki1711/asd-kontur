# ruff: noqa: RUF001 -- Russian construction fixtures are intentional.

from __future__ import annotations

import json
from typing import Any

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.qwen_work_reconciliation import (
    PROJECT_WORK_RECONCILIATION_PROFILE,
    QwenProjectWorkReconciler,
    _source_measure_options,
    _source_numeric_token_present,
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


def test_cross_document_scope_task_asks_for_semantic_operation_without_arithmetic(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert '"task":"CROSS_DOCUMENT_SCOPE_MATCHING"' in prompt
        assert "Не объявляйте отсутствие работы и не выполняйте арифметику" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "structural_steel",
                        "operation": "Монтаж стальных ферм",
                        "facility": "Gallery B",
                        "confidence": "0.92",
                        "reason": "Обе строки описывают монтаж ферм одного сооружения.",
                        "work_scope_assertions": [
                            {
                                "related_candidate_id": (
                                    "commercial-row"
                                    if candidate_id == "design-row"
                                    else "design-row"
                                ),
                                "scope_compatibility": "SAME_SCOPE",
                                "normalized_operation": "Roof trusses",
                                "reason": "Обе строки описывают один объём монтажа ферм.",
                            }
                        ],
                    }
                    for candidate_id in ("design-row", "commercial-row")
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-row",
                "wording": "Install roof trusses",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-row",
                "wording": "Erect steel roof trusses",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"structural_steel": "Structural steel"},
        facilities=["Gallery B"],
    )

    assert [value["operation"] for value in result["observations"]] == [
        "Монтаж стальных ферм",
        "Монтаж стальных ферм",
    ]
    assert all(
        value["work_scope_assertions"][0]["scope_compatibility"] == "SAME_SCOPE"
        for value in result["observations"]
    )


def test_cross_document_scope_schema_repair_keeps_exact_pair_intact(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        assertions_required = len(prompts) > 1
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "pipeline",
                        "operation": "Монтаж водовода",
                        "facility": "Участок 7",
                        "confidence": "0.91",
                        "reason": "Строки относятся к одному водоводу.",
                        **(
                            {
                                "work_scope_assertions": [
                                    {
                                        "related_candidate_id": (
                                            "commercial-pipe"
                                            if candidate_id == "design-pipe"
                                            else "design-pipe"
                                        ),
                                        "scope_compatibility": "SAME_SCOPE",
                                        "normalized_operation": "Монтаж водовода / трубопровода",
                                        "reason": "Один объём монтажа водовода.",
                                    }
                                ]
                            }
                            if assertions_required
                            else {}
                        ),
                    }
                    for candidate_id in ("design-pipe", "commercial-pipe")
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-pipe",
                "wording": "Устройство водовода",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-pipe",
                "wording": "Монтаж трубопровода",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"pipeline": "Трубопроводы"},
        facilities=["Участок 7"],
    )

    assert len(prompts) == 2
    assert "qwen_work_reconciliation_work_scope_assertions_invalid" in prompts[1]
    assert "design-pipe" in prompts[1]
    assert "commercial-pipe" in prompts[1]
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_work_scope_assertions_invalid"]
    assert all(value.get("work_scope_assertions") for value in result["observations"])


def test_cross_document_scope_repairs_two_distinct_validation_failures(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        response_number = len(prompts)
        compatibility = "SAME_SCOPE"
        normalized_operation = (
            "Восстановление покрытия моста" if response_number == 2 else "Bridge deck resurfacing"
        )
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "roadworks",
                        "operation": "Восстановление покрытия моста",
                        "facility": None,
                        "confidence": "0.93",
                        "reason": "Обе строки описывают восстановление покрытия моста.",
                        **(
                            {
                                "work_scope_assertions": [
                                    {
                                        "related_candidate_id": (
                                            "commercial-deck"
                                            if candidate_id == "design-deck"
                                            else "design-deck"
                                        ),
                                        "scope_compatibility": compatibility,
                                        "normalized_operation": normalized_operation,
                                        "reason": (
                                            "Обе строки описывают один объём восстановления."
                                        ),
                                    }
                                ]
                            }
                            if response_number > 1
                            else {}
                        ),
                    }
                    for candidate_id in ("design-deck", "commercial-deck")
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-deck",
                "wording": "Bridge deck resurfacing",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-deck",
                "wording": "Renew bridge deck surface",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"roadworks": "Road works"},
        facilities=[],
    )

    assert len(prompts) == 3
    assert "qwen_work_reconciliation_work_scope_assertions_invalid" in prompts[1]
    assert "qwen_work_reconciliation_work_scope_operation_ungrounded" in prompts[2]
    assert result["inference_call_count"] == 3
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_work_scope_assertions_invalid",
        "qwen_work_reconciliation_work_scope_operation_ungrounded",
    ]
    assert {
        value["work_scope_assertions"][0]["scope_compatibility"] for value in result["observations"]
    } == {"SAME_SCOPE"}


def test_cross_document_scope_does_not_repeat_same_rejected_schema(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "structural_steel",
                        "operation": "Монтаж стальных связей",
                        "facility": None,
                        "confidence": "0.90",
                        "reason": "Обе строки относятся к стальным связям.",
                    }
                    for candidate_id in ("design-bracing", "commercial-bracing")
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-bracing",
                "wording": "Steel cross bracing",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-bracing",
                "wording": "Install steel diagonal bracing",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"structural_steel": "Structural steel"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_work_scope_assertions_invalid",
        "qwen_work_reconciliation_work_scope_assertions_invalid",
        "qwen_work_reconciliation_scope_pair_unresolved",
    ]
    assert all(value["status"] == "UNCLASSIFIED" for value in result["observations"])


def test_cross_document_scope_rejects_operation_taken_only_from_nearby_context(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        same_scope = len(prompts) == 1
        compatibility = "SAME_SCOPE" if same_scope else "DIFFERENT_SCOPE"
        normalized_operation = "Устройство асфальтобетонного покрытия" if same_scope else None
        reason = (
            "Обе строки описывают устройство покрытия."
            if same_scope
            else "Проектная строка описывает покрытие, коммерческая — дорожную разметку."
        )
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "roadworks",
                        "operation": wording,
                        "facility": None,
                        "confidence": "0.93",
                        "reason": reason,
                        "work_scope_assertions": [
                            {
                                "related_candidate_id": (
                                    "commercial-marking"
                                    if candidate_id == "design-paving"
                                    else "design-paving"
                                ),
                                "scope_compatibility": compatibility,
                                "normalized_operation": normalized_operation,
                                "reason": reason,
                            }
                        ],
                    }
                    for candidate_id, wording in (
                        ("design-paving", "Устройство асфальтобетонного покрытия"),
                        ("commercial-marking", "Нанесение дорожной разметки"),
                    )
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-paving",
                "wording": "Проектная общая площадь асфальтобетонного покрытия типа Б",
                "nearby_context": "Покрытие 4600 м²; далее приведена дорожная разметка.",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-marking",
                "wording": "Нанесение дорожной разметки",
                "nearby_context": "В соседней строке указано устройство покрытия.",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"roadworks": "Дорожные работы"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert "qwen_work_reconciliation_work_scope_operation_ungrounded" in prompts[1]
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_work_scope_operation_ungrounded"]
    assert {
        value["work_scope_assertions"][0]["scope_compatibility"] for value in result["observations"]
    } == {"DIFFERENT_SCOPE"}


def test_cross_document_scope_output_exhaustion_never_splits_exact_pair(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []
    budgets: list[int] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        prompts.append(prompt)
        budgets.append(max_tokens)
        assert "design-road" in prompt
        assert "commercial-road" in prompt
        if len(prompts) == 1:
            raise QwenSemanticFailure("qwen_semantic_response_output_exhausted")
        assertions_required = len(prompts) == 3
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": candidate_id,
                        "status": "MATCHED",
                        "family_key": "roadworks",
                        "operation": "Устройство асфальтобетонного покрытия",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": "Обе строки описывают устройство нового покрытия.",
                        **(
                            {
                                "work_scope_assertions": [
                                    {
                                        "related_candidate_id": (
                                            "commercial-road"
                                            if candidate_id == "design-road"
                                            else "design-road"
                                        ),
                                        "scope_compatibility": "SAME_SCOPE",
                                        "normalized_operation": (
                                            "Устройство асфальтобетонного покрытия"
                                        ),
                                        "reason": "Один вид работ на сопоставимом объекте.",
                                    }
                                ]
                            }
                            if assertions_required
                            else {}
                        ),
                    }
                    for candidate_id in ("design-road", "commercial-road")
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "design-road",
                "wording": "Устройство нового асфальтобетонного покрытия",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
            {
                "candidate_id": "commercial-road",
                "wording": "Устройство асфальтобетонного покрытия",
                "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            },
        ],
        work_families={"roadworks": "Дорожные работы"},
        facilities=[],
    )

    assert len(prompts) == 3
    assert budgets == [3_200, 5_000, 5_000]
    assert "qwen_semantic_response_output_exhausted" in prompts[1]
    assert "qwen_work_reconciliation_work_scope_assertions_invalid" in prompts[2]
    assert result["inference_call_count"] == 3
    assert result["recovery_codes"] == [
        "qwen_semantic_response_output_exhausted",
        "qwen_work_reconciliation_work_scope_assertions_invalid",
    ]
    assert all(value.get("work_scope_assertions") for value in result["observations"])


def test_cross_document_scope_repairs_revision_inferred_only_from_different_values(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": "design-waterproofing",
            "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            "wording": "Устройство мембранной гидроизоляции",
            "document_role": "РД",
            "nearby_context": "Общая площадь мембранной гидроизоляции 740 м².",
        },
        {
            "candidate_id": "commercial-waterproofing",
            "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            "wording": "Устройство мембранной гидроизоляции",
            "document_role": "ВОР",
            "nearby_context": "Устройство мембранной гидроизоляции 700 м².",
        },
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        repaired = "qwen_work_reconciliation_revision_evidence_missing" in prompt
        compatibility = "SAME_SCOPE" if repaired else "REVISION_DIFFERENCE"
        normalized_operation = "Устройство мембранной гидроизоляции" if repaired else None
        reason = (
            "Обе строки описывают общую площадь мембранной гидроизоляции."
            if repaired
            else "Разные значения указывают на разные редакции."
        )
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Устройство мембранной гидроизоляции",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": reason,
                        "work_scope_assertions": [
                            {
                                "related_candidate_id": (
                                    "commercial-waterproofing"
                                    if row["candidate_id"] == "design-waterproofing"
                                    else "design-waterproofing"
                                ),
                                "scope_compatibility": compatibility,
                                "normalized_operation": normalized_operation,
                                "reason": reason,
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
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert "Различие значений, марок, толщин или объёмов" in prompts[1]
    assert result["recovery_codes"] == ["qwen_work_reconciliation_revision_evidence_missing"]
    assert {
        value["work_scope_assertions"][0]["scope_compatibility"] for value in result["observations"]
    } == {"SAME_SCOPE"}


def test_cross_document_scope_accepts_explicit_revision_relationship(monkeypatch: Any) -> None:
    rows = [
        {
            "candidate_id": "revision-one",
            "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            "wording": "Устройство мембранной гидроизоляции",
            "document_role": "РД",
            "nearby_context": "Редакция 1: площадь гидроизоляции 740 м².",
        },
        {
            "candidate_id": "revision-two",
            "analysis_task": "CROSS_DOCUMENT_SCOPE_MATCHING",
            "wording": "Устройство мембранной гидроизоляции",
            "document_role": "РД",
            "nearby_context": "Изм. 2 заменяет редакцию 1: площадь 700 м².",
        },
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Устройство мембранной гидроизоляции",
                        "facility": None,
                        "confidence": "0.97",
                        "reason": "Источник прямо связывает редакцию 1 и изменение 2.",
                        "work_scope_assertions": [
                            {
                                "related_candidate_id": (
                                    "revision-two"
                                    if row["candidate_id"] == "revision-one"
                                    else "revision-one"
                                ),
                                "scope_compatibility": "REVISION_DIFFERENCE",
                                "normalized_operation": None,
                                "reason": "Источник прямо связывает редакцию 1 и изменение 2.",
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
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    assert result["inference_call_count"] == 1
    assert result["recovery_codes"] == []
    assert {
        value["work_scope_assertions"][0]["scope_compatibility"] for value in result["observations"]
    } == {"REVISION_DIFFERENCE"}


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

    assert result["profile_version"] == PROJECT_WORK_RECONCILIATION_PROFILE


def test_quantity_review_preserves_scaled_source_unit_without_model_arithmetic(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "100 м2" in prompt
        assert "нельзя сокращать" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "waterproofing-row",
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Обмазочная гидроизоляция",
                        "facility": None,
                        "confidence": "0.96",
                        "reason": "Работа и единица указаны в строке сметы.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "waterproofing-area",
                                "status": "WORK_QUANTITY",
                                "source_unit": "100 м2",
                                "semantic_scope": "Площадь обмазочной гидроизоляции",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": "Сметная строка измеряется сотнями квадратных метров.",
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "waterproofing-row",
                "wording": "Гидроизоляция боковая обмазочная",
                "nearby_context": "Гидроизоляция боковая обмазочная 100 м2 8,339",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "waterproofing-area",
                        "value": "8.339",
                        "unit": "м2",
                        "nearby_context": "Формула объема = 833,9:100; единица 100 м2",
                    }
                ],
            }
        ],
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    assert result["observations"][0]["quantity_reviews"][0]["source_unit"] == "100 м2"


def test_qwen_work_reconciliation_accepts_professional_unit_spelling_from_split_ocr(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "foundation-blocks",
                        "status": "MATCHED",
                        "family_key": "foundation_slab",
                        "operation": "Укладка фундаментных блоков",
                        "facility": None,
                        "confidence": "0.96",
                        "reason": "Сметная строка содержит физическую строительную работу.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "foundation-block-count",
                                "status": "WORK_QUANTITY",
                                "source_unit": "100 шт",
                                "semantic_scope": "Количество фундаментных блоков",
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": None,
                                "reason": "Количество задано в сотнях штук.",
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "foundation-blocks",
                "wording": "Укладка фундаментных блоков",
                "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                "nearby_context": "Укладка блоков 100 ш т 0,6 1 0,6",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "foundation-block-count",
                        "value": "0.6",
                        "unit": "piece",
                        "nearby_context": "Укладка блоков 100 ш т 0,6 1 0,6",
                    }
                ],
            }
        ],
        work_families={"foundation_slab": "Фундаменты и плиты"},
        facilities=[],
    )

    review = result["observations"][0]["quantity_reviews"][0]
    assert review["source_unit"] == "100 шт"
    assert review["relationship_reviewed"] is True


def test_quantity_review_can_correct_a_misaligned_estimate_value_from_exact_source(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "source_value" in prompt
        assert "100 м 3 2,113" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "wall-row",
                        "status": "MATCHED",
                        "family_key": "reinforced_concrete",
                        "operation": "Устройство железобетонных стен",
                        "facility": None,
                        "confidence": "0.97",
                        "reason": "Строка содержит физическую работу и её сметный объём.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "wall-volume",
                                "status": "WORK_QUANTITY",
                                "source_value": "2,113",
                                "source_unit": "100 м3",
                                "semantic_scope": "Объём железобетонных стен",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": (
                                    "Число 100 относится к единице, объём строки равен 2,113."
                                ),
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "wall-row",
                "wording": "Устройство железобетонных стен",
                "analysis_task": "QUANTITY_SCOPE_INTERPRETATION",
                "nearby_context": "Устройство стен 100 м 3 2,113 1 2,113",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "wall-volume",
                        "value": "100",
                        "unit": "м3",
                        "nearby_context": "Устройство стен 100 м 3 2,113 1 2,113",
                    }
                ],
            }
        ],
        work_families={"reinforced_concrete": "Бетонные и железобетонные работы"},
        facilities=[],
    )

    review = result["observations"][0]["quantity_reviews"][0]
    assert review["source_value"] == "2,113"
    assert review["source_unit"] == "100 м3"


def test_source_value_evidence_rejects_model_arithmetic() -> None:
    context = "Устройство стен 100 м3 2,113 1 2,113"

    assert _source_numeric_token_present("2,113", context)
    assert not _source_numeric_token_present("211,3", context)


def test_quantity_review_can_select_one_exact_measure_from_compound_source_cell(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "площадь/объём" in prompt
        assert "420,6/21,03" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "surface-total-row",
                        "status": "MATCHED",
                        "family_key": "demolition",
                        "operation": "Разборка покрытия",
                        "facility": None,
                        "confidence": "0.96",
                        "reason": "Строка содержит площадь и производный объём покрытия.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "surface-total",
                                "status": "WORK_QUANTITY",
                                "source_value": "420,6",
                                "source_unit": "м2",
                                "semantic_scope": "Общая площадь разбираемого покрытия",
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": None,
                                "reason": "Источник явно связывает 420,6 с площадью м2.",
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "surface-total-row",
                "wording": "Разборка покрытия, площадь/объём",
                "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                "nearby_context": "Итого площадь/объём 420,6/21,03 м2/м3",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "surface-total",
                        "value": "420,6/21,03",
                        "unit": "м2/м3",
                        "nearby_context": "Итого площадь/объём 420,6/21,03 м2/м3",
                        "peer_quantity_candidate_ids": [],
                    }
                ],
            }
        ],
        work_families={"demolition": "Демонтажные работы"},
        facilities=[],
    )

    review = result["observations"][0]["quantity_reviews"][0]
    assert review["source_value"] == "420,6"
    assert review["source_unit"] == "м2"


def test_compound_source_measure_options_preserve_exact_scalar_pairs() -> None:
    assert _source_measure_options("83,4/4,17", "м2 / м 3") == [
        {"source_value": "83,4", "source_unit": "м2"},
        {"source_value": "4,17", "source_unit": "м 3"},
    ]
    assert _source_measure_options("12 / 7", "шт") == [
        {"source_value": "12", "source_unit": "шт"},
        {"source_value": "7", "source_unit": "шт"},
    ]
    assert _source_measure_options("83,4+17,2", "м2") == []


def test_quantity_source_value_repair_offers_exact_compound_measure_choices(
    monkeypatch: Any,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        source_value = "83,4/4,17" if len(prompts) == 1 else "83,4"
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "coating-row",
                        "status": "MATCHED",
                        "family_key": "demolition",
                        "operation": "Разборка покрытия",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": "Источник содержит площадь и производный объём.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "coating-measures",
                                "status": "WORK_QUANTITY",
                                "source_value": source_value,
                                "source_unit": "м2",
                                "semantic_scope": "Площадь разбираемого покрытия",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": False,
                                "reason": "Для площади выбрана исходная мера в м2.",
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "coating-row",
                "wording": "Разборка покрытия",
                "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                "nearby_context": "Разборка покрытия м2/м3 83,4/4,17",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "coating-measures",
                        "value": "83,4/4,17",
                        "unit": "м2/м3",
                        "nearby_context": "Разборка покрытия м2/м3 83,4/4,17",
                    }
                ],
            }
        ],
        work_families={"demolition": "Демонтажные работы"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert '"available_source_measures"' in prompts[0]
    assert '"source_value":"83,4"' in prompts[0]
    assert '"source_value":"4,17"' in prompts[0]
    assert "Не возвращайте составную ячейку целиком" in prompts[1]
    assert result["recovery_codes"] == ["qwen_work_reconciliation_quantity_source_value_invalid"]
    assert result["observations"][0]["quantity_reviews"][0]["source_value"] == "83,4"


def test_compound_measure_choice_is_validated_against_the_source_value_cell(
    monkeypatch: Any,
) -> None:
    """The extracted value cell is source evidence even when nearby text omits it."""

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del prompt, max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "compound-row",
                        "status": "MATCHED",
                        "family_key": "demolition",
                        "operation": "Разборка покрытия",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": "Источник содержит площадь и объём.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "compound-measure",
                                "status": "WORK_QUANTITY",
                                "source_value": "274,7",
                                "source_unit": "м2",
                                "semantic_scope": "Площадь разбираемого покрытия",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": False,
                                "reason": "Выбрана исходная площадь.",
                            }
                        ],
                        "material_reviews": [],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        [
            {
                "candidate_id": "compound-row",
                "wording": "Разборка покрытия",
                "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
                "nearby_context": "Демонтаж асфальтобетонного покрытия",
                "quantity_observations": [
                    {
                        "quantity_candidate_id": "compound-measure",
                        "value": "274,7/13,76",
                        "unit": "м2 / м 3",
                        "nearby_context": "Демонтаж асфальтобетонного покрытия",
                    }
                ],
            }
        ],
        work_families={"demolition": "Демонтажные работы"},
        facilities=[],
    )

    review = result["observations"][0]["quantity_reviews"][0]
    assert review["source_value"] == "274,7"
    assert review["source_unit"] == "м2"


def test_qwen_work_reconciliation_preserves_material_resource_semantics(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "material_reviews" in prompt
        assert "Материальная позиция" in prompt
        assert "до 180 знаков" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "material-row",
                        "status": "NOT_A_WORK",
                        "family_key": None,
                        "operation": None,
                        "facility": None,
                        "confidence": "0.96",
                        "reason": "Строка является материальной позицией.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "material-q",
                                "status": "RESOURCE_OR_RATE",
                                "semantic_scope": "Площадь мембранного покрытия",
                                "quantity_type": "RESOURCE_OR_RATE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "INSUFFICIENT_INFORMATION",
                                "component_set_complete": None,
                                "reason": "Количество материала.",
                            }
                        ],
                        "material_reviews": [
                            {
                                "material_name": "Полимерная мембрана",
                                "material_kind": "полимерная мембрана",
                                "associated_work_family_key": "waterproofing",
                                "properties": [{"kind": "THICKNESS", "value": "2.4", "unit": "mm"}],
                                "quantity_candidate_ids": ["material-q"],
                                "confidence": "0.94",
                                "reason": "Материал и толщина названы явно.",
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
                "candidate_id": "material-row",
                "wording": "Полимерная мембрана толщиной 2,4 мм",
                "quantity_observations": [
                    {"quantity_candidate_id": "material-q", "value": "760", "unit": "m2"}
                ],
            }
        ],
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    assert result["observations"][0]["material_reviews"] == [
        {
            "material_name": "Полимерная мембрана",
            "material_kind": "полимерная мембрана",
            "associated_work_family_key": "waterproofing",
            "properties": [{"kind": "THICKNESS", "value": "2.4", "unit": "mm"}],
            "quantity_candidate_ids": ["material-q"],
            "confidence": "0.94",
            "reason": "Материал и толщина названы явно.",
        }
    ]


def test_quantity_relationship_prompt_requires_explicit_same_scope_decision(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        assert "даже когда сами числа" in prompt
        assert "дословно одинаковый краткий" in prompt
        assert "DUPLICATE_OF означает именно повтор" in prompt
        assert "relation_kind всегда должен быть" in prompt
        assert "одним из перечисленных значений" in prompt
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
                                "scope_assertions": [
                                    {
                                        "related_quantity_candidate_id": "commercial-q",
                                        "scope_compatibility": "SAME_SCOPE",
                                        "reason": "Обе строки измеряют одну площадь.",
                                    }
                                ],
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
                                "scope_assertions": [
                                    {
                                        "related_quantity_candidate_id": "design-q",
                                        "scope_compatibility": "SAME_SCOPE",
                                        "reason": "Обе строки измеряют одну площадь.",
                                    }
                                ],
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
    assert reviews[0]["scope_assertions"][0]["related_quantity_candidate_id"] == "commercial-q"
    assert reviews[1]["scope_assertions"][0]["related_quantity_candidate_id"] == "design-q"


def test_quantity_relationship_repairs_unsupported_numeric_alternative(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": "design",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Монтаж несущих рам перехода",
            "document_role": "РД",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "design-q",
                    "value": "24.6",
                    "unit": "т",
                    "nearby_context": "Общая масса несущих рам 24,6 т",
                }
            ],
        },
        {
            "candidate_id": "commercial",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Монтаж несущих рам перехода",
            "document_role": "ВОР",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "commercial-q",
                    "value": "21.9",
                    "unit": "т",
                    "nearby_context": "Монтаж несущих рам 21,9 т",
                }
            ],
        },
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        repaired = "qwen_work_reconciliation_alternative_evidence_missing" in prompt
        observations = []
        for row in rows:
            peer = "commercial-q" if row["candidate_id"] == "design" else "design-q"
            observations.append(
                {
                    "candidate_id": row["candidate_id"],
                    "status": "MATCHED",
                    "family_key": "structural_steel",
                    "operation": "Монтаж несущих рам",
                    "facility": None,
                    "confidence": "0.94",
                    "reason": "Обе строки относятся к рамам перехода.",
                    "quantity_reviews": [
                        {
                            "quantity_candidate_id": row["quantity_observations"][0][
                                "quantity_candidate_id"
                            ],
                            "status": "WORK_QUANTITY",
                            "semantic_scope": "Масса несущих рам перехода",
                            "quantity_type": "TOTAL",
                            "relation_kind": "NONE" if repaired else "ALTERNATIVE_TO",
                            "related_quantity_candidate_ids": [] if repaired else [peer],
                            "scope_compatibility": (
                                "SAME_SCOPE" if repaired else "ALTERNATIVE_DESIGN"
                            ),
                            "component_set_complete": None,
                            "reason": "Один инженерный объём." if repaired else "Разные значения.",
                        }
                    ],
                    "material_reviews": [],
                }
            )
        return json.dumps({"observations": observations}, ensure_ascii=False)

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"structural_steel": "Металлоконструкции"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert "Различие значений само по себе не является альтернативой" in prompts[1]
    assert result["recovery_codes"] == ["qwen_work_reconciliation_alternative_evidence_missing"]
    assert {
        review["scope_compatibility"]
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    } == {"SAME_SCOPE"}


def test_quantity_relationship_accepts_explicit_alternative_design(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "document_role": "РД",
            "quantity_observations": [
                {
                    "quantity_candidate_id": quantity_id,
                    "value": value,
                    "unit": "м",
                    "nearby_context": wording,
                }
            ],
        }
        for candidate_id, quantity_id, value, wording in (
            ("base", "base-q", "180", "Основной вариант: трубопровод длиной 180 м"),
            ("option", "option-q", "165", "Альтернативный вариант трассы длиной 165 м"),
        )
    ]

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "pipeline_installation",
                        "operation": (
                            "Монтаж основной трассы"
                            if row["candidate_id"] == "base"
                            else "Монтаж альтернативной трассы"
                        ),
                        "facility": None,
                        "confidence": "0.95",
                        "reason": "Источник прямо называет основной и альтернативный варианты.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина соответствующего варианта трассы",
                                "quantity_type": "TOTAL",
                                "relation_kind": "ALTERNATIVE_TO",
                                "related_quantity_candidate_ids": [
                                    "option-q" if row["candidate_id"] == "base" else "base-q"
                                ],
                                "scope_compatibility": "ALTERNATIVE_DESIGN",
                                "component_set_complete": None,
                                "reason": "Два явно названных варианта не суммируются.",
                            }
                        ],
                        "material_reviews": [],
                    }
                    for row in rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"pipeline_installation": "Монтаж трубопроводов"},
        facilities=[],
    )

    assert result["inference_call_count"] == 1
    assert result["recovery_codes"] == []
    assert all(
        review["scope_compatibility"] == "ALTERNATIVE_DESIGN"
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_quantity_relationship_ignores_unauthorized_work_scope_assertions(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "pipeline",
            "quantity_observations": [
                {"quantity_candidate_id": quantity_id, "value": "180", "unit": "m"}
            ],
        }
        for candidate_id, quantity_id, wording in (
            ("design-network", "design-length", "Проектная длина тепловой сети"),
            ("commercial-network", "commercial-length", "Прокладка тепловой сети"),
        )
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "pipeline",
                        "operation": "Прокладка тепловой сети",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": "Оба значения относятся к длине одной сети.",
                        # This malformed, out-of-task assertion must neither
                        # authorize scope identity nor reject the quantity result.
                        "work_scope_assertions": [{"unexpected": "model drift"}],
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина тепловой сети",
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "scope_assertions": [
                                    {
                                        "related_quantity_candidate_id": (
                                            "commercial-length"
                                            if row["candidate_id"] == "design-network"
                                            else "design-length"
                                        ),
                                        "scope_compatibility": "SAME_SCOPE",
                                        "reason": "Один инженерный объём длины сети.",
                                    }
                                ],
                                "component_set_complete": None,
                                "reason": "Значения измеряют одну длину.",
                            }
                        ],
                        "material_reviews": [],
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

    assert "work_scope_assertions должен быть пустым списком" in prompts[0]
    assert result["inference_call_count"] == 1
    assert result["recovery_codes"] == []
    assert all("work_scope_assertions" not in value for value in result["observations"])
    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_quantity_relationship_repairs_revision_inferred_only_from_quantity_difference(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": "design",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Устройство защитного покрытия",
            "document_role": "РД",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "design-q",
                    "value": "740",
                    "unit": "м2",
                    "nearby_context": "Общая площадь защитного покрытия 740 м².",
                }
            ],
        },
        {
            "candidate_id": "commercial",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Устройство защитного покрытия",
            "document_role": "ВОР",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "commercial-q",
                    "value": "700",
                    "unit": "м2",
                    "nearby_context": "Устройство защитного покрытия 700 м².",
                }
            ],
        },
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        repaired = "qwen_work_reconciliation_revision_evidence_missing" in prompt
        observations = []
        for row in rows:
            quantity_id = row["quantity_observations"][0]["quantity_candidate_id"]
            peer = "commercial-q" if quantity_id == "design-q" else "design-q"
            observations.append(
                {
                    "candidate_id": row["candidate_id"],
                    "status": "MATCHED",
                    "family_key": "protective_coating",
                    "operation": "Устройство защитного покрытия",
                    "facility": None,
                    "confidence": "0.94",
                    "reason": "Обе строки описывают защитное покрытие.",
                    "quantity_reviews": [
                        {
                            "quantity_candidate_id": quantity_id,
                            "status": "WORK_QUANTITY",
                            "semantic_scope": "Площадь защитного покрытия",
                            "quantity_type": "TOTAL",
                            "relation_kind": "NONE" if repaired else "REVISION_OF",
                            "related_quantity_candidate_ids": [] if repaired else [peer],
                            "scope_compatibility": (
                                "SAME_SCOPE" if repaired else "REVISION_DIFFERENCE"
                            ),
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": peer,
                                    "scope_compatibility": (
                                        "SAME_SCOPE" if repaired else "REVISION_DIFFERENCE"
                                    ),
                                    "reason": (
                                        "Один инженерный объём."
                                        if repaired
                                        else "Разные значения означают разные редакции."
                                    ),
                                }
                            ],
                            "component_set_complete": None,
                            "reason": (
                                "Один инженерный объём."
                                if repaired
                                else "Разные значения означают разные редакции."
                            ),
                        }
                    ],
                    "material_reviews": [],
                }
            )
        return json.dumps({"observations": observations}, ensure_ascii=False)

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"protective_coating": "Защитные покрытия"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_revision_evidence_missing"]
    assert {
        review["scope_compatibility"]
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    } == {"SAME_SCOPE"}


def test_quantity_relationship_repairs_same_scope_operation_mismatch(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "quantity_observations": [
                {"quantity_candidate_id": quantity_id, "value": value, "unit": "м2"}
            ],
        }
        for candidate_id, quantity_id, value, wording in (
            ("design", "design-q", "510", "Гидроизоляция перекрытия"),
            ("commercial", "commercial-q", "480", "Устройство гидроизоляции перекрытия"),
        )
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        repaired = "qwen_work_reconciliation_same_scope_operation_mismatch" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": (
                            "Гидроизоляция перекрытия"
                            if repaired or row["candidate_id"] == "design"
                            else "Устройство рулонной изоляции"
                        ),
                        "facility": None,
                        "confidence": "0.93",
                        "reason": "Строки описывают одну операцию.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь гидроизоляции перекрытия",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": "Один инженерный объём.",
                            }
                        ],
                        "material_reviews": [],
                    }
                    for row in rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_same_scope_operation_mismatch"]
    assert {observation["operation"] for observation in result["observations"]} == {
        "Гидроизоляция перекрытия"
    }


def test_quantity_relationship_repairs_component_total_without_relation(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "quantity_observations": [
                {
                    "quantity_candidate_id": quantity_id,
                    "value": value,
                    "unit": "м2",
                }
            ],
        }
        for candidate_id, quantity_id, value, wording in (
            ("component", "component-q", "210", "Ремонт западного фасада"),
            ("total", "total-q", "520", "Ремонт фасадов"),
        )
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        repaired = "qwen_work_reconciliation_component_total_relation_missing" in prompt
        observations = []
        for row in rows:
            component = row["candidate_id"] == "component"
            observations.append(
                {
                    "candidate_id": row["candidate_id"],
                    "status": "MATCHED",
                    "family_key": "structural_repair",
                    "operation": "Ремонт кладки фасада",
                    "facility": None,
                    "confidence": "0.92",
                    "reason": "Описана одна группа фасадных работ.",
                    "quantity_reviews": [
                        {
                            "quantity_candidate_id": row["quantity_observations"][0][
                                "quantity_candidate_id"
                            ],
                            "status": "WORK_QUANTITY",
                            "semantic_scope": (
                                "Площадь западного фасада"
                                if repaired and component
                                else "Площадь ремонта фасадов"
                            ),
                            "quantity_type": "COMPONENT" if component else "TOTAL",
                            "relation_kind": "NONE",
                            "related_quantity_candidate_ids": [],
                            "scope_compatibility": (
                                "DIFFERENT_SCOPE" if repaired else "SAME_SCOPE"
                            ),
                            "component_set_complete": None,
                            "reason": (
                                "Один фасад является только частью общего объёма."
                                if repaired
                                else "Значения относятся к фасадам."
                            ),
                        }
                    ],
                    "material_reviews": [],
                }
            )
        return json.dumps({"observations": observations}, ensure_ascii=False)

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"structural_repair": "Ремонт конструкций"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_component_total_relation_missing"]
    reviews = [observation["quantity_reviews"][0] for observation in result["observations"]]
    assert {review["scope_compatibility"] for review in reviews} == {"DIFFERENT_SCOPE"}


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


def test_quantity_relationship_prompt_makes_same_row_peer_identities_explicit(
    monkeypatch: Any,
) -> None:
    quantity_ids = ("quantity-total", "quantity-north", "quantity-south")
    rows = [
        {
            "candidate_id": "candidate-waterproofing",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Устройство мембранной гидроизоляции",
            "deterministic_family_hint": "waterproofing",
            "nearby_context": ("Северная зона 510 м2. Южная зона 290 м2. Общая площадь 835 м2."),
            "quantity_observations": [
                {"quantity_candidate_id": quantity_ids[0], "value": "835", "unit": "м2"},
                {"quantity_candidate_id": quantity_ids[1], "value": "510", "unit": "м2"},
                {"quantity_candidate_id": quantity_ids[2], "value": "290", "unit": "м2"},
            ],
        }
    ]

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        payload = prompt.split("Структурированная задача: ", 1)[1].split("\n\n", 1)[0]
        task = json.loads(payload)
        assert task["context"]["all_quantity_candidate_ids"] == list(quantity_ids)
        safe_row = task["context"]["rows"][0]
        assert safe_row["available_quantity_candidate_ids"] == list(quantity_ids)
        assert safe_row["quantity_observations"][0]["peer_quantity_candidate_ids"] == [
            "quantity-north",
            "quantity-south",
        ]
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-waterproofing",
                        "status": "MATCHED",
                        "family_key": "waterproofing",
                        "operation": "Устройство мембранной гидроизоляции",
                        "facility": None,
                        "confidence": "0.96",
                        "reason": "Общий объём и обе зоны указаны явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общая площадь гидроизоляции",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": [
                                    "quantity-north",
                                    "quantity-south",
                                ],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": True,
                                "reason": "Текст обозначает значение общим итогом двух зон.",
                            },
                            {
                                "quantity_candidate_id": "quantity-north",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь гидроизоляции северной зоны",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": None,
                                "reason": "Северная зона является частью общего итога.",
                            },
                            {
                                "quantity_candidate_id": "quantity-south",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь гидроизоляции южной зоны",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": None,
                                "reason": "Южная зона является частью общего итога.",
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"waterproofing": "Гидроизоляция"},
        facilities=[],
    )

    total = result["observations"][0]["quantity_reviews"][0]
    assert total["related_quantity_candidate_ids"] == [
        "quantity-north",
        "quantity-south",
    ]


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


def test_two_row_quantity_batch_is_not_split_after_repeated_invalid_json(
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

    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_invalid_json",
        "qwen_work_reconciliation_invalid_json",
        "qwen_work_reconciliation_quantity_pair_unresolved",
    ]
    assert all(
        "relationship_reviewed" not in review
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_output_exhausted_relationship_batch_retries_complete_context_with_expanded_budget(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "roadworks",
            "quantity_observations": [
                {
                    "quantity_candidate_id": quantity_id,
                    "value": value,
                    "unit": "m2",
                }
            ],
        }
        for candidate_id, quantity_id, wording, value in (
            ("candidate-total", "quantity-total", "Общая площадь покрытия", "1375"),
            ("candidate-north", "quantity-north", "Покрытие северного участка", "825"),
            ("candidate-south", "quantity-south", "Покрытие южного участка", "550"),
        )
    ]
    budgets: list[int] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        budgets.append(max_tokens)
        if len(budgets) == 1:
            raise QwenSemanticFailure("qwen_semantic_response_output_exhausted")
        assert all(row["candidate_id"] in prompt for row in rows)
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "roadworks",
                        "operation": "Устройство покрытия",
                        "facility": None,
                        "confidence": "0.95",
                        "reason": "Объём покрытия установлен из полного контекста.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Площадь нового покрытия",
                                "quantity_type": (
                                    "TOTAL"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT"
                                ),
                                "relation_kind": (
                                    "TOTAL_FOR"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT_OF"
                                ),
                                "related_quantity_candidate_ids": (
                                    ["quantity-north", "quantity-south"]
                                    if row["candidate_id"] == "candidate-total"
                                    else ["quantity-total"]
                                ),
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": (
                                    True if row["candidate_id"] == "candidate-total" else None
                                ),
                                "reason": "Итог и все составляющие явно перечислены.",
                            }
                        ],
                        "material_reviews": [],
                    }
                    for row in rows
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"roadworks": "Дорожные работы"},
        facilities=[],
    )

    assert budgets == [1_620, 5_000]
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == ["qwen_semantic_response_output_exhausted"]
    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_relationship_review_normalizes_false_component_completeness_to_null(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": "candidate-total",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Общая длина кабельной трассы",
            "deterministic_family_hint": "electrical",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-total", "value": "310", "unit": "m"}
            ],
        },
        {
            "candidate_id": "candidate-part",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Участок кабельной трассы в галерее",
            "deterministic_family_hint": "electrical",
            "quantity_observations": [
                {"quantity_candidate_id": "quantity-part", "value": "130", "unit": "m"}
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
                        "family_key": "electrical",
                        "operation": "Прокладка кабельной трассы",
                        "facility": None,
                        "confidence": "0.94",
                        "reason": "Указана общая длина.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Общая длина кабельной трассы",
                                "quantity_type": "TOTAL",
                                "relation_kind": "TOTAL_FOR",
                                "related_quantity_candidate_ids": ["quantity-part"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": False,
                                "reason": "Передана только одна из составляющих.",
                            }
                        ],
                        "material_reviews": [],
                    },
                    {
                        "candidate_id": "candidate-part",
                        "status": "MATCHED",
                        "family_key": "electrical",
                        "operation": "Прокладка кабельной трассы",
                        "facility": None,
                        "confidence": "0.93",
                        "reason": "Указана часть трассы.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-part",
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина трассы в галерее",
                                "quantity_type": "COMPONENT",
                                "relation_kind": "COMPONENT_OF",
                                "related_quantity_candidate_ids": ["quantity-total"],
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": False,
                                "reason": "Это одна составляющая общего итога.",
                            }
                        ],
                        "material_reviews": [],
                    },
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_work_reconciliation._complete", complete)
    result = QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
        rows,
        work_families={"electrical": "Электромонтажные работы"},
        facilities=[],
    )

    component = result["observations"][1]["quantity_reviews"][0]
    assert component["component_set_complete"] is None
    assert result["inference_call_count"] == 1


def test_relationship_schema_failure_retries_same_complete_context_once(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "structural_steel",
            "quantity_observations": [
                {"quantity_candidate_id": quantity_id, "value": value, "unit": "t"}
            ],
        }
        for candidate_id, quantity_id, wording, value in (
            ("candidate-total", "quantity-total", "Общая масса металлоконструкций", "18.4"),
            ("candidate-east", "quantity-east", "Металлоконструкции восточной секции", "10.1"),
            ("candidate-west", "quantity-west", "Металлоконструкции западной секции", "8.3"),
        )
    ]
    calls: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        calls.append(prompt)
        repaired = "qwen_work_reconciliation_component_completeness_invalid" in prompt
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "structural_steel",
                        "operation": "Монтаж металлоконструкций",
                        "facility": None,
                        "confidence": "0.95",
                        "reason": "Итог и секции названы явно.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Масса металлоконструкций",
                                "quantity_type": (
                                    "TOTAL"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT"
                                ),
                                "relation_kind": (
                                    "TOTAL_FOR"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT_OF"
                                ),
                                "related_quantity_candidate_ids": (
                                    ["quantity-east", "quantity-west"]
                                    if row["candidate_id"] == "candidate-total"
                                    else ["quantity-total"]
                                ),
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": (
                                    True
                                    if repaired and row["candidate_id"] == "candidate-total"
                                    else None
                                ),
                                "reason": "Установлена связь итога и составляющих.",
                            }
                        ],
                        "material_reviews": [],
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

    assert len(calls) == 2
    assert all(row["candidate_id"] in calls[1] for row in rows)
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == ["qwen_work_reconciliation_component_completeness_invalid"]
    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_two_row_quantity_relationship_repairs_two_distinct_failures_without_split(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "pipeline",
            "quantity_observations": [
                {"quantity_candidate_id": quantity_id, "value": value, "unit": "m"}
            ],
        }
        for candidate_id, quantity_id, wording, value in (
            ("candidate-total", "quantity-total", "Общая длина теплотрассы", "240"),
            ("candidate-section", "quantity-section", "Длина участка теплотрассы", "140"),
        )
    ]
    calls: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        calls.append(prompt)
        call_number = len(calls)
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "pipeline",
                        "operation": "Прокладка теплотрассы",
                        "facility": None,
                        "confidence": "0.92",
                        "reason": "Переданы общий объём и один участок.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Длина теплотрассы",
                                "quantity_type": (
                                    "TOTAL"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT"
                                ),
                                "relation_kind": (
                                    "TOTAL_FOR"
                                    if row["candidate_id"] == "candidate-total"
                                    else "COMPONENT_OF"
                                ),
                                "related_quantity_candidate_ids": (
                                    ["invented-id"]
                                    if call_number == 1
                                    else [
                                        "quantity-section"
                                        if row["candidate_id"] == "candidate-total"
                                        else "quantity-total"
                                    ]
                                ),
                                "scope_compatibility": "COMPONENT_VS_TOTAL",
                                "component_set_complete": (
                                    False
                                    if row["candidate_id"] == "candidate-total" and call_number != 2
                                    else None
                                ),
                                "reason": "Участок является частью общей длины.",
                            }
                        ],
                        "material_reviews": [],
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

    assert len(calls) == 3
    assert all(all(row["candidate_id"] in prompt for row in rows) for prompt in calls)
    assert result["inference_call_count"] == 3
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_quantity_relation_ids_invalid",
        "qwen_work_reconciliation_component_completeness_invalid",
    ]
    assert all(
        review["relationship_reviewed"] is True
        for observation in result["observations"]
        for review in observation["quantity_reviews"]
    )


def test_two_row_quantity_relationship_stops_after_repeated_failure_without_split(
    monkeypatch: Any,
) -> None:
    rows = [
        {
            "candidate_id": candidate_id,
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": wording,
            "deterministic_family_hint": "structural_steel",
            "quantity_observations": [
                {"quantity_candidate_id": quantity_id, "value": value, "unit": "t"}
            ],
        }
        for candidate_id, quantity_id, wording, value in (
            ("candidate-a", "quantity-a", "Масса ферм блока A", "8.1"),
            ("candidate-b", "quantity-b", "Масса ферм блока B", "7.4"),
        )
    ]
    calls: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        calls.append(prompt)
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": row["candidate_id"],
                        "status": "MATCHED",
                        "family_key": "structural_steel",
                        "operation": "Монтаж ферм",
                        "facility": None,
                        "confidence": "0.88",
                        "reason": "Строки относятся к разным блокам.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": row["quantity_observations"][0][
                                    "quantity_candidate_id"
                                ],
                                "status": "WORK_QUANTITY",
                                "semantic_scope": "Масса ферм",
                                "quantity_type": "STANDALONE",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": ["invented-id"],
                                "scope_compatibility": "DIFFERENT_SCOPE",
                                "component_set_complete": None,
                                "reason": "Разные конструктивные блоки.",
                            }
                        ],
                        "material_reviews": [],
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

    assert len(calls) == 2
    assert all(all(row["candidate_id"] in prompt for row in rows) for prompt in calls)
    assert result["inference_call_count"] == 2
    assert result["recovery_codes"] == [
        "qwen_work_reconciliation_quantity_relation_ids_invalid",
        "qwen_work_reconciliation_quantity_relation_ids_invalid",
        "qwen_work_reconciliation_quantity_pair_unresolved",
    ]
    assert all(value["status"] == "UNCLASSIFIED" for value in result["observations"])


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
    assert "qwen_work_reconciliation_quantity_relation_ids_invalid" in result["recovery_codes"]


def test_quantity_relationship_repair_names_invalid_source_unit(monkeypatch: Any) -> None:
    rows = [
        {
            "candidate_id": "candidate-total",
            "analysis_task": "QUANTITY_RELATIONSHIP_ANALYSIS",
            "wording": "Общая площадь покрытия",
            "deterministic_family_hint": "roadworks",
            "quantity_observations": [
                {
                    "quantity_candidate_id": "quantity-total",
                    "value": "45,0/2,25",
                    "unit": "м2/м3",
                    "nearby_context": "Общая площадь покрытия м2/м3 45,0/2,25",
                }
            ],
        }
    ]
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        del max_tokens
        prompts.append(prompt)
        source_unit = "тонн" if len(prompts) == 1 else "м2"
        return json.dumps(
            {
                "observations": [
                    {
                        "candidate_id": "candidate-total",
                        "status": "MATCHED",
                        "family_key": "roadworks",
                        "operation": "Устройство покрытия",
                        "facility": None,
                        "confidence": "0.9",
                        "reason": "Переданная операция сохранена.",
                        "quantity_reviews": [
                            {
                                "quantity_candidate_id": "quantity-total",
                                "status": "WORK_QUANTITY",
                                "source_value": "45,0",
                                "source_unit": source_unit,
                                "semantic_scope": "Общая площадь покрытия",
                                "quantity_type": "TOTAL",
                                "relation_kind": "NONE",
                                "related_quantity_candidate_ids": [],
                                "scope_compatibility": "SAME_SCOPE",
                                "component_set_complete": None,
                                "reason": "Источник явно указывает площадь.",
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
        work_families={"roadworks": "Дорожные работы"},
        facilities=[],
    )

    assert len(prompts) == 2
    assert "qwen_work_reconciliation_quantity_source_unit_invalid" in prompts[1]
    assert "source_unit либо дословно скопируйте" in prompts[1]
    assert result["recovery_codes"] == ["qwen_work_reconciliation_quantity_source_unit_invalid"]
    assert result["observations"][0]["quantity_reviews"][0]["source_unit"] == "м2"


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
