# ruff: noqa: RUF001 -- mixed-alphabet designation forms are the subject under test.

from __future__ import annotations

from asd_kontur.assistant.reasoning import (
    PlannedToolCall,
    SearchPlan,
    ensure_explicit_designation_resolution,
)
from asd_kontur.ntd.search_corpus import normalize_designation


def test_explicit_sp_is_resolved_before_general_search() -> None:
    original = SearchPlan(
        "mixed",
        False,
        None,
        (
            PlannedToolCall(
                "consultant.search_ntd_content",
                {"query": "бетонные работы", "limit": 4},
                "Найти текст",
            ),
        ),
    )

    result = ensure_explicit_designation_resolution(original, "Почему не СП 70?")

    assert result.steps[0].tool == "consultant.resolve_ntd_designation"
    assert result.steps[0].arguments == {"designation": "СП 70"}
    assert result.steps[1] == original.steps[0]


def test_designation_normalization_handles_expected_sp70_forms() -> None:
    values = {
        normalize_designation(value)
        for value in ("СП 70", "СП70", "СП 70.13330", "СП 70.13330.2012")
    }
    assert values == {"сп70", "сп7013330", "сп70133302012"}


def test_general_construction_question_does_not_force_normative_lookup() -> None:
    original = SearchPlan("general", False, None, ())
    assert (
        ensure_explicit_designation_resolution(original, "Что такое железнение бетона?") == original
    )
