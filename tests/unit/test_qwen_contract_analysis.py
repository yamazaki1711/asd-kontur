from __future__ import annotations

import json

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.qwen_contract_analysis import (
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
