# ruff: noqa: RUF001 -- Cyrillic construction fixture is intentional.

import json

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
