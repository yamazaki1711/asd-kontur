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
                    "risk_mechanism": "contractor_bears_customer_cause",
                    "trigger_text": "включая задержку передачи Заказчиком рабочей документации",
                    "adverse_effect_text": "Подрядчик отвечает за задержку",
                    "severity": "high",
                    "description": "Ответственность включает задержку исходных данных Заказчика.",
                    "practical_consequence": "Подрядчик несёт риск срока по неуправляемой причине.",
                    "recommended_action": (
                        "Предусмотреть продление срока при задержке документации."
                    ),
                    "replacement_source_text": source["loc-b"],
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


def test_contract_analysis_falls_back_to_exact_locator_text_for_high_overlap_quote() -> None:
    source = {
        "loc-source": (
            "6.3. Подрядчик обязан передать исполнительную документацию Заказчику "
            "в течение пяти рабочих дней после завершения работ."
        )
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "6.3",
                    "source_text": (
                        "Подрядчик должен передать исполнительную документацию Заказчику "
                        "в течение пяти рабочих дней после завершения работ"
                    ),
                    "source_locator_ids": ["loc-source"],
                    "category": "documentation",
                }
            ],
            "risks": [],
        },
        ensure_ascii=False,
    )

    result = parse_contract_analysis(raw, allowed_text_by_locator=source)

    assert result["clauses"][0]["source_text"] == source["loc-source"]


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
                    "risk_mechanism": "asymmetric_remedy",
                    "trigger_text": "Заказчик вправе отказаться от договора в любое время",
                    "adverse_effect_text": "Заказчик вправе отказаться от договора в любое время",
                    "severity": "medium",
                    "description": "Односторонний отказ не содержит компенсационного механизма.",
                    "practical_consequence": "Подрядчик может понести неподтверждённые затраты.",
                    "recommended_action": "Согласовать компенсацию подтверждённых затрат.",
                    "replacement_source_text": source["loc-z"],
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
                    "adverse_effect_text": "Объём демонтажа конструкций составляет 36 м3",
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


def test_contract_analysis_requires_exact_adverse_effect_text() -> None:
    source = {
        "loc-customer-duty": (
            "3.2. Заказчик передаёт площадку Подрядчику в течение трёх рабочих дней."
        )
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "3.2",
                    "source_text": source["loc-customer-duty"],
                    "source_locator_ids": ["loc-customer-duty"],
                    "category": "customer_obligation",
                }
            ],
            "risks": [
                {
                    "clause_ref": "3.2",
                    "kind": "deadline_exposure",
                    "basis": "explicit_clause_text",
                    "risk_mechanism": "customer_controlled_deadline",
                    "trigger_text": "в течение трёх рабочих дней",
                    "adverse_effect_text": "Подрядчик отвечает за задержку Заказчика",
                    "severity": "high",
                    "description": "Заказчик может задержать передачу площадки.",
                    "practical_consequence": "Подрядчик может поздно начать работы.",
                    "recommended_action": "Предусмотреть продление срока.",
                    "replacement_source_text": source["loc-customer-duty"],
                    "proposed_contractor_wording": "Срок продлевается при задержке Заказчика.",
                    "disagreement_required": True,
                    "confidence": 0.9,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_invalid"):
        parse_contract_analysis(raw, allowed_text_by_locator=source)


def test_contract_analysis_rejects_unsupported_customer_control_over_ordinary_act() -> None:
    source = {
        "loc-hidden-work": (
            "Последующие работы допускаются после оформления и подписания акта "
            "освидетельствования скрытых работ."
        )
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "4.6",
                    "source_text": source["loc-hidden-work"],
                    "source_locator_ids": ["loc-hidden-work"],
                    "category": "acceptance",
                }
            ],
            "risks": [
                {
                    "clause_ref": "4.6",
                    "kind": "deadline_exposure",
                    "basis": "explicit_clause_text",
                    "risk_mechanism": "customer_controlled_deadline",
                    "trigger_text": "после оформления и подписания акта",
                    "adverse_effect_text": (
                        "Последующие работы допускаются после оформления и подписания акта"
                    ),
                    "severity": "medium",
                    "description": "Подписание якобы полностью контролируется Заказчиком.",
                    "practical_consequence": "Предполагается простой.",
                    "recommended_action": "Ввести одностороннюю приёмку.",
                    "replacement_source_text": source["loc-hidden-work"],
                    "proposed_contractor_wording": "Акт считается подписанным автоматически.",
                    "disagreement_required": True,
                    "confidence": 0.9,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_controller_not_grounded"):
        parse_contract_analysis(raw, allowed_text_by_locator=source)


def test_contract_analysis_rejects_optional_mutual_early_payment_as_risk() -> None:
    source = {
        "loc-early": (
            "При наличии финансирования Заказчик по согласованию с Подрядчиком "
            "принимает досрочно выполненные работы и оплачивает их."
        )
    }
    raw = json.dumps(
        {
            "clauses": [
                {
                    "clause_ref": "4.2",
                    "source_text": source["loc-early"],
                    "source_locator_ids": ["loc-early"],
                    "category": "payment",
                }
            ],
            "risks": [
                {
                    "clause_ref": "4.2",
                    "kind": "payment_dependency",
                    "basis": "explicit_clause_text",
                    "risk_mechanism": "customer_controlled_payment",
                    "trigger_text": "При наличии финансирования",
                    "adverse_effect_text": (
                        "Заказчик по согласованию с Подрядчиком принимает досрочно "
                        "выполненные работы и оплачивает их"
                    ),
                    "severity": "medium",
                    "description": "Досрочная оплата якобы ограничивает обычную оплату.",
                    "practical_consequence": "Предполагается задержка обычной оплаты.",
                    "recommended_action": "Обязать Заказчика оплачивать работы досрочно.",
                    "replacement_source_text": source["loc-early"],
                    "proposed_contractor_wording": "Заказчик всегда оплачивает работы досрочно.",
                    "disagreement_required": True,
                    "confidence": 0.9,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_controller_not_grounded"):
        parse_contract_analysis(raw, allowed_text_by_locator=source)


def test_contract_analysis_rejects_two_replacement_proposals_for_one_clause() -> None:
    source = {"loc-one": "8.1. Заказчик единолично устанавливает срок устранения недостатков."}
    clause = {
        "clause_ref": "8.1",
        "source_text": source["loc-one"],
        "source_locator_ids": ["loc-one"],
        "category": "warranty",
    }
    risk = {
        "clause_ref": "8.1",
        "kind": "uncontrolled_obligation",
        "basis": "explicit_clause_text",
        "risk_mechanism": "customer_controlled_deadline",
        "trigger_text": "Заказчик единолично устанавливает срок устранения недостатков",
        "adverse_effect_text": "Заказчик единолично устанавливает срок устранения недостатков",
        "severity": "medium",
        "description": "Срок определяется одной стороной.",
        "practical_consequence": "Срок может быть технически неисполнимым.",
        "recommended_action": "Согласовать объективный срок.",
        "replacement_source_text": source["loc-one"],
        "proposed_contractor_wording": "Стороны согласовывают разумный срок устранения.",
        "disagreement_required": True,
        "confidence": 0.9,
    }
    raw = json.dumps({"clauses": [clause], "risks": [risk, risk]}, ensure_ascii=False)

    with pytest.raises(QwenSemanticFailure, match="qwen_contract_risk_revision_invalid"):
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


def test_contract_analysis_splits_multi_source_batch_after_exact_quote_repair_fails(
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
            source_text = "Перефразированный общий текст."
            locator = "loc-a"
        else:
            locator = "loc-a" if '"loc-a"' in prompt else "loc-b"
            source_text = "2.1. Условие А." if locator == "loc-a" else "2.2. Условие Б."
        return json.dumps(
            {
                "clauses": [
                    {
                        "clause_ref": "2.1" if locator == "loc-a" else "2.2",
                        "section": "Условия",
                        "source_text": source_text,
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
            {"source_locator_id": "loc-a", "page": 1, "text": "2.1. Условие А."},
            {"source_locator_id": "loc-b", "page": 2, "text": "2.2. Условие Б."},
        ]
    )

    assert len(calls) == 4
    assert [item["source_text"] for item in result["clauses"]] == [
        "2.1. Условие А.",
        "2.2. Условие Б.",
    ]


def test_contract_analysis_splits_batch_after_revision_shape_repair_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    source_by_locator = {
        "loc-a": "7.1. Заказчик устанавливает срок устранения недостатков.",
        "loc-b": "7.2. Заказчик единолично устанавливает срок замены элемента.",
    }

    def complete(
        endpoint: str,
        prompt: str,
        timeout_seconds: float,
        *,
        max_tokens: int,
    ) -> str:
        del endpoint, timeout_seconds, max_tokens
        calls.append(prompt)
        combined = '"loc-a"' in prompt and '"loc-b"' in prompt
        locator = "loc-a" if '"loc-a"' in prompt else "loc-b"
        clause_ref = "7.1" if locator == "loc-a" else "7.2"
        source_text = source_by_locator[locator]
        risk = {
            "clause_ref": clause_ref,
            "kind": "uncontrolled_obligation",
            "basis": "explicit_clause_text",
            "risk_mechanism": "customer_controlled_deadline",
            "trigger_text": source_text,
            "adverse_effect_text": source_text,
            "severity": "medium",
            "description": "Срок определяется одной стороной.",
            "practical_consequence": "Срок может быть технически неисполнимым.",
            "recommended_action": "Согласовать объективный срок.",
            "replacement_source_text": source_text,
            "proposed_contractor_wording": "Стороны согласовывают разумный срок.",
            "disagreement_required": True,
            "confidence": 0.9,
        }
        risks = [risk, dict(risk)] if combined else [risk]
        return json.dumps(
            {
                "clauses": [
                    {
                        "clause_ref": clause_ref,
                        "section": "Гарантии",
                        "source_text": source_text,
                        "source_locator_ids": [locator],
                        "category": "warranty",
                        "customer_obligation": None,
                        "contractor_obligation": None,
                        "condition": None,
                    }
                ],
                "risks": risks,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_analysis._complete", complete)
    analyzer = QwenContractAnalyzer("http://127.0.0.1:8790/v1/chat/completions")

    result = analyzer.analyze(
        [
            {"source_locator_id": locator, "page": index, "text": text}
            for index, (locator, text) in enumerate(source_by_locator.items(), start=1)
        ]
    )

    assert len(calls) == 4
    assert [item["clause_ref"] for item in result["clauses"]] == ["7.1", "7.2"]
    assert [item["clause_ref"] for item in result["risks"]] == ["7.1", "7.2"]
