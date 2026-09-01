# ruff: noqa: RUF001 -- exact Russian construction terms are intentional.

from __future__ import annotations

import pytest

from asd_kontur.ntd.query_routing import QueryScope, route_consultant_query


@pytest.mark.parametrize(
    ("question", "scope"),
    [
        ("Есть ли у тебя СП 70?", QueryScope.EXACT_DESIGNATION),
        ("Найди в корпусе СП 999.99999.2099.", QueryScope.EXACT_DESIGNATION),
        ("Как выполняют уход за бетоном?", QueryScope.PLATFORM_NTD),
        (
            "Какой класс бетона указан для фундамента демонстрационного объекта?",
            QueryScope.WORKSPACE,
        ),
        (
            "Покажи результаты лабораторных испытаний бетона конкретной захватки.",
            QueryScope.WORKSPACE,
        ),
        (
            "Кто подписал АОСР по работам текущего объекта?",
            QueryScope.WORKSPACE,
        ),
        (
            "Какой паспорт качества выдан на бетонную смесь партии Б-17 текущего объекта?",
            QueryScope.WORKSPACE,
        ),
        (
            "Что требует СП 70 для бетонной стены этого объекта?",
            QueryScope.MIXED,
        ),
    ],
)
def test_route_consultant_query(question: str, scope: QueryScope) -> None:
    assert route_consultant_query(question).scope is scope


def test_route_extracts_full_designations() -> None:
    route = route_consultant_query("Сравни СП70.13330.2012 и ГОСТ Р 51872-2024")

    assert route.explicit_designations == (
        "сп70133302012",
        "гостр518722024",
    )


def test_route_rejects_empty_question() -> None:
    with pytest.raises(ValueError, match="ntd_query_empty"):
        route_consultant_query("  ")
