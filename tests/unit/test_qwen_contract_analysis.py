# ruff: noqa: RUF001 -- Russian contract examples are intentional.

from __future__ import annotations

import json

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.qwen_contract_analysis import (
    QwenContractAnalyzer,
    _contract_output_token_budget,
    parse_contract_analysis,
)


def test_contract_output_budget_scales_for_long_bounded_context() -> None:
    assert _contract_output_token_budget(500) == 1_800
    assert _contract_output_token_budget(4_000) == 3_200
    assert _contract_output_token_budget(10_000) == 5_000
    assert _contract_output_token_budget(12_000) == 5_000


def test_contract_analysis_accepts_risk_and_leaves_benign_clause_unflagged() -> None:
    source = {
        "loc-a": (
            "5.2. Заказчик оплачивает работы в течение 30 дней после подписания "
            "акта обеими сторонами."
        ),
        "loc-b": (
            "7.4. Подрядчик отвечает за задержку, включая задержку передачи "
            "Заказчиком рабочей документации."
        ),
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "5.2",
                    "section": "Оплата",
                    "source_text": source["loc-a"],
                    "source_locator_ids": ["loc-a"],
                    "category": "payment",
                    "customer_obligation": "Оплатить принятые работы в течение 30 дней.",
                    "contractor_obligation": None,
                    "condition": "После подписания акта обеими сторонами.",
                },
                {
                    "clause_ref": "7.4",
                    "section": "Ответственность",
                    "source_text": source["loc-b"],
                    "source_locator_ids": ["loc-b"],
                    "category": "liability",
                    "customer_obligation": None,
                    "contractor_obligation": "Нести ответственность за любую задержку.",
                    "condition": None,
                },
            ],
            "risks": [
                {
                    "clause_ref": "7.4",
                    "kind": "customer_input_dependency",
                    "basis": "explicit_clause_text",
                    "trigger_text": "включая задержку передачи Заказчиком рабочей документации",
                    "severity": "high",
                    "description": "Ответственность включает задержку исходных данных Заказчика.",
                    "practical_consequence": "Подрядчик несёт риск срока по неуправляемой причине.",
                    "recommended_action": (
                        "Предусмотреть продление срока при задержке документации."
                    ),
                    "proposed_contractor_wording": (
                        "Срок продлевается на период задержки передачи рабочей "
                        "документации Заказчиком."
                    ),
                    "disagreement_required": True,
                    "confidence": 0.94,
                    "uncertainty": None,
                }
            ],
        },
        ensure_ascii=False,
    )

    result = parse_contract_analysis(raw, allowed_text_by_locator=source)

    assert len(result["clauses"]) == 2
    assert [risk["clause_ref"] for risk in result["risks"]] == ["7.4"]
    assert result["risks"][0]["authority"] == "contract_commercial_risk"


def test_contract_analysis_rejects_invented_source_text() -> None:
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "9.1",
                    "source_text": "Подрядчик уплачивает штраф 50 процентов.",
                    "source_locator_ids": ["loc-x"],
                    "category": "liability",
                }
            ],
            "risks": [],
        }
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_clause_source_not_exact"):
        parse_contract_analysis(
            raw,
            allowed_text_by_locator={"loc-x": "Подрядчик уплачивает пеню 0,1 процента."},
        )


def test_contract_analysis_resolves_typographic_variant_to_exact_admitted_text() -> None:
    source = {
        "loc-typography": (
            "Подрядчик выполняет работы в соответствии с разделом «Проект» — без "
            "изменения исходного объёма."
        )
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "1.2",
                    "section": "Предмет",
                    "source_text": (
                        'Подрядчик выполняет работы в соответствии с разделом "Проект" - без '
                        "изменения исходного объёма."
                    ),
                    "source_locator_ids": ["loc-typography"],
                    "category": "scope",
                    "customer_obligation": None,
                    "contractor_obligation": "Выполнить работы",
                    "condition": None,
                }
            ],
            "risks": [],
        },
        ensure_ascii=False,
    )

    result = parse_contract_analysis(raw, allowed_text_by_locator=source)

    assert result["clauses"][0]["source_text"] == source["loc-typography"]


def test_contract_analysis_requires_wording_for_disagreement() -> None:
    source = {"loc-z": "10.2. Заказчик вправе отказаться от договора в любое время."}
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "10.2",
                    "source_text": source["loc-z"],
                    "source_locator_ids": ["loc-z"],
                    "category": "termination",
                }
            ],
            "risks": [
                {
                    "clause_ref": "10.2",
                    "kind": "asymmetric_termination",
                    "basis": "explicit_clause_text",
                    "trigger_text": "Заказчик вправе отказаться от договора в любое время",
                    "severity": "medium",
                    "description": "Односторонний отказ не содержит компенсационного механизма.",
                    "practical_consequence": "Подрядчик может понести неподтверждённые затраты.",
                    "recommended_action": "Согласовать компенсацию подтверждённых затрат.",
                    "proposed_contractor_wording": None,
                    "disagreement_required": True,
                    "confidence": 0.8,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_revision_invalid"):
        parse_contract_analysis(raw, allowed_text_by_locator=source)


def test_contract_analysis_rejects_missing_term_inference_from_bounded_context() -> None:
    source = {"loc-q": "Объём демонтажа конструкций составляет 36 м3."}
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "2",
                    "source_text": source["loc-q"],
                    "source_locator_ids": ["loc-q"],
                    "category": "scope",
                }
            ],
            "risks": [
                {
                    "clause_ref": "2",
                    "kind": "missing_price_adjustment",
                    "basis": "missing_term_candidate",
                    "trigger_text": "Объём демонтажа конструкций составляет 36 м3",
                    "severity": "medium",
                    "description": "В ограниченном контексте не найден порядок изменения цены.",
                    "practical_consequence": "Возможен спор об оплате.",
                    "recommended_action": "Проверить договор целиком.",
                    "proposed_contractor_wording": "Оплачивать фактический объём.",
                    "disagreement_required": True,
                    "confidence": 0.8,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_invalid"):
        parse_contract_analysis(raw, allowed_text_by_locator=source)


def test_contract_analysis_splits_output_exhausted_batch_and_preserves_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def complete(
        endpoint: str,
        prompt: str,
        timeout_seconds: float,
        *,
        max_tokens: int,
    ) -> str:
        del endpoint, timeout_seconds, max_tokens
        calls.append(prompt)
        if '"loc-a"' in prompt and '"loc-b"' in prompt:
            raise QwenSemanticFailure("qwen_semantic_response_output_exhausted")
        locator = "loc-a" if '"loc-a"' in prompt else "loc-b"
        text = "1.1. Условие А." if locator == "loc-a" else "1.1. Условие Б."
        return json.dumps(
            {
                "clauses": [
                    {
                        "clause_ref": "1.1",
                        "section": "Условия",
                        "source_text": text,
                        "source_locator_ids": [locator],
                        "category": "other",
                        "customer_obligation": None,
                        "contractor_obligation": None,
                        "condition": None,
                    }
                ],
                "risks": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_analysis._complete", complete)
    analyzer = QwenContractAnalyzer("http://127.0.0.1:8790/v1/chat/completions")

    result = analyzer.analyze(
        [
            {"source_locator_id": "loc-a", "page": 1, "text": "1.1. Условие А."},
            {"source_locator_id": "loc-b", "page": 2, "text": "1.1. Условие Б."},
        ]
    )

    assert len(calls) == 3
    assert [item["source_text"] for item in result["clauses"]] == [
        "1.1. Условие А.",
        "1.1. Условие Б.",
    ]
    assert len({item["clause_ref"] for item in result["clauses"]}) == 2
