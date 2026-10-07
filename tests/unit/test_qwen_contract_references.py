"""Contract-reference semantics are source-bound and project-independent."""

from __future__ import annotations

import json

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.tender.qwen_contract_references import (
    QwenContractReferenceReviewer,
    parse_contract_references,
    reference_context_candidate,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Работы выполнить по приложению № 4 к договору.", True),
        ("The drawings are attached as Annex C.", True),
        ("Подрядчик выполняет работы надлежащим образом.", False),
    ],
)
def test_reference_gate_only_routes_context(text: str, expected: bool) -> None:
    assert reference_context_candidate(text) is expected


def test_reviewer_persists_only_exact_citation_and_admitted_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        requests.append(prompt)
        assert max_tokens >= 2_000
        return json.dumps(
            {
                "references": [
                    {
                        "source_locator_id": "loc-1",
                        "source_quote": "Appendix C — delivery timetable",
                        "target_description": "delivery timetable",
                        "kind": "schedule",
                        "match_decision": "matched",
                        "matched_source_version_id": "source-2",
                        "confidence": 0.91,
                        "uncertainty": None,
                    }
                ]
            }
        )

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    result = QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
        [
            {
                "source_locator_id": "loc-1",
                "page": 3,
                "text": "Perform deliveries under Appendix C — delivery timetable.",
            }
        ],
        admitted_sources=[
            {"source_version_id": "source-1", "safe_display_name": "Building contract"},
            {"source_version_id": "source-2", "safe_display_name": "Delivery timetable"},
        ],
    )
    assert len(requests) == 1
    assert result["references"][0]["matched_source_name"] == "Delivery timetable"
    assert result["result_digest"].startswith("sha256:")


def test_reviewer_receives_bounded_source_excerpt_when_filename_is_opaque(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        prompts.append(prompt)
        return '{"references":[]}'

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
        [{"source_locator_id": "contract-line", "text": "See Appendix B for bridge sections."}],
        admitted_sources=[
            {
                "source_version_id": "source-b",
                "safe_display_name": "scan-018.pdf",
                "first_page_excerpt": "Appendix B. Bridge section schedule",
                "excerpt_source_locator_ids": ["source-title-line"],
            }
        ],
    )
    assert len(prompts) == 1
    assert "Appendix B. Bridge section schedule" in prompts[0]
    assert "source-title-line" in prompts[0]
    assert "обычным упоминанием" in prompts[0]


@pytest.mark.parametrize(
    "mutation",
    [
        {"source_locator_id": "other"},
        {"source_quote": "invented appendix number"},
        {"matched_source_version_id": "other"},
        {"match_decision": "unresolved"},
        {"kind": "unsafe_project_special_case"},
    ],
)
def test_reference_validator_rejects_ungrounded_or_inconsistent_output(
    mutation: dict[str, object],
) -> None:
    item: dict[str, object] = {
        "source_locator_id": "loc-1",
        "source_quote": "Appendix C",
        "target_description": "delivery timetable",
        "kind": "schedule",
        "match_decision": "matched",
        "matched_source_version_id": "source-2",
        "confidence": 0.8,
    }
    item.update(mutation)
    with pytest.raises(QwenSemanticFailure):
        parse_contract_references(
            json.dumps({"references": [item]}),
            allowed_text={"loc-1": "See Appendix C for delivery dates."},
            inventory={"source-2": "Delivery timetable"},
        )


def test_unresolved_reference_is_not_declared_missing() -> None:
    result = parse_contract_references(
        json.dumps(
            {
                "references": [
                    {
                        "source_locator_id": "loc-9",
                        "source_quote": "technical assignment approved by the Customer",
                        "target_description": "Customer technical assignment",
                        "kind": "technical_assignment",
                        "match_decision": "unresolved",
                        "matched_source_version_id": None,
                        "confidence": 0.7,
                    }
                ]
            }
        ),
        allowed_text={
            "loc-9": "The contractor follows the technical assignment approved by the Customer."
        },
        inventory={"source-a": "Construction contract"},
    )
    assert result[0]["match_decision"] == "unresolved"
    assert result[0]["matched_source_name"] is None


def test_output_exhaustion_splits_only_the_bounded_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            raise QwenSemanticFailure("qwen_semantic_response_output_exhausted")
        return '{"references":[]}'

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    result = QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
        [
            {"source_locator_id": "a", "text": "Appendix A is incorporated."},
            {"source_locator_id": "b", "text": "Annex B is incorporated."},
        ],
        admitted_sources=[{"source_version_id": "source-c", "safe_display_name": "Contract"}],
    )
    assert len(calls) == 3
    assert result["references"] == []


def test_invalid_multi_locator_output_splits_without_accepting_an_invented_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def complete(_endpoint: str, prompt: str, _timeout: float, *, max_tokens: int) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps(
                {
                    "references": [
                        {
                            "source_locator_id": "a",
                            "source_quote": "Invented Annex Z",
                            "target_description": "invented appendix",
                            "kind": "attachment",
                            "match_decision": "unresolved",
                            "matched_source_version_id": None,
                            "confidence": 0.5,
                        }
                    ]
                }
            )
        return '{"references":[]}'

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    result = QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
        [
            {"source_locator_id": "a", "text": "Appendix A is incorporated."},
            {"source_locator_id": "b", "text": "Annex B is incorporated."},
        ],
        admitted_sources=[{"source_version_id": "source-c", "safe_display_name": "Contract"}],
    )
    assert len(calls) == 3
    assert result["references"] == []


def test_invalid_single_locator_stays_failed_after_bounded_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        nonlocal calls
        calls += 1
        return '{"references":[{"source_locator_id":"missing"}]}'

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    with pytest.raises(QwenSemanticFailure, match="qwen_contract_reference_invalid_item"):
        QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
            [{"source_locator_id": "a", "text": "Appendix A is incorporated."}],
            admitted_sources=[{"source_version_id": "source-c", "safe_display_name": "Contract"}],
        )
    assert calls == 2


def test_invalid_json_keeps_one_bounded_repair_before_splitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def complete(_endpoint: str, _prompt: str, _timeout: float, *, max_tokens: int) -> str:
        nonlocal calls
        calls += 1
        return "not-json" if calls == 1 else '{"references":[]}'

    monkeypatch.setattr("asd_kontur.tender.qwen_contract_references._complete", complete)
    result = QwenContractReferenceReviewer("http://127.0.0.1:8765/v1").review(
        [
            {"source_locator_id": "a", "text": "Appendix A is incorporated."},
            {"source_locator_id": "b", "text": "Annex B is incorporated."},
        ],
        admitted_sources=[{"source_version_id": "source-c", "safe_display_name": "Contract"}],
    )
    assert calls == 2
    assert result["references"] == []
