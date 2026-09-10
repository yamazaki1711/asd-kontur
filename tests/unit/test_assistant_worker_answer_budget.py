# ruff: noqa: RUF001 -- Cyrillic construction fixture is intentional.

from asd_kontur.assistant.worker import _answer_budget, _tool_results_for_prompt


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
