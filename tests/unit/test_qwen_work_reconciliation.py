# ruff: noqa: RUF001 -- Russian construction fixtures are intentional.

from __future__ import annotations

import json
from typing import Any

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.qwen_work_reconciliation import QwenProjectWorkReconciler


def test_qwen_work_reconciliation_preserves_exact_rows_and_allowed_scope(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert "КНС-4" in prompt
        assert "backfill" in prompt
        assert max_tokens >= 900
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

    assert result["profile_version"] == "qwen-project-work-reconciliation-v6"


def test_qwen_work_reconciliation_classifies_linked_quantity_meaning(
    monkeypatch: Any,
) -> None:
    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        assert "quantity-volume" in prompt
        assert "quantity-depth" in prompt
        assert max_tokens >= 900
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
                                "reason": "Значение указано как объём разработки грунта.",
                            },
                            {
                                "quantity_candidate_id": "quantity-depth",
                                "status": "DIMENSION",
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
            "reason": "Значение указано как объём разработки грунта.",
        },
        {
            "quantity_candidate_id": "quantity-depth",
            "status": "DIMENSION",
            "reason": "Значение является глубиной котлована.",
        },
    ]


def test_qwen_work_reconciliation_rejects_incomplete_or_invented_output(
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

    with pytest.raises(QwenSemanticFailure, match="identity_invalid"):
        QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
            [{"candidate_id": "candidate-a", "wording": "Обратная засыпка"}],
            work_families={"backfill": "Обратная засыпка и уплотнение"},
            facilities=[],
        )


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

    with pytest.raises(QwenSemanticFailure, match="potential_work_excluded"):
        QwenProjectWorkReconciler("http://127.0.0.1:8790").reconcile(
            [{"candidate_id": "candidate-a", "wording": "Геодезическая разбивка"}],
            work_families={"surveying": "Геодезические работы"},
            facilities=[],
        )


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
