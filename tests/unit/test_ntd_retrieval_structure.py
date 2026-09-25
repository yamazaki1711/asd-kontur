# ruff: noqa: RUF001 -- Russian normative headings are intentional test input.

from asd_kontur.ntd.retrieval_qualification import (
    QualificationCorpusEntry,
    _scope_context,
    _work_context,
    qualification_document_from_pages,
)


def test_table_of_contents_labels_are_not_promoted_to_provisions() -> None:
    entry = QualificationCorpusEntry(
        "СП 70.13330.2012",
        "Несущие и ограждающие конструкции",
        "sha256:" + "a" * 64,
        "official",
        3,
        None,
        ("multi-level",),
    )
    document = qualification_document_from_pages(
        entry,
        (
            "Содержание\n5 Бетонные работы .... 39\n5.4 Выдерживание и уход .... 44",
            "6 Монтаж сборных конструкций .... 71\nПриложение А .... 140",
            (
                "Дата введения 2013-07-01\n"
                "1 Область применения\n"
                "1.1 Настоящий свод правил распространяется на производство и приемку "
                "работ при возведении монолитных бетонных конструкций в строительстве."
            ),
        ),
    )

    contents = [unit for unit in document.units if unit.kind == "table_of_contents"]
    provisions = [unit for unit in document.units if unit.kind != "table_of_contents"]

    assert [unit.pages for unit in contents] == [(1,), (2,)]
    assert all(unit.clause_label is None for unit in contents)
    assert not any(unit.clause_label == "5.4" for unit in provisions)
    assert any(unit.clause_label == "1.1" for unit in provisions)


def test_context_fallback_is_deterministic_for_full_corpus_documents() -> None:
    entry = QualificationCorpusEntry(
        "ГОСТ 12345-2020",
        "Материалы строительные. Методы контроля",
        "sha256:" + "b" * 64,
        "legacy_reference",
        1,
        None,
        (),
    )

    assert _scope_context(entry) == (
        "Материалы строительные. Методы контроля; область применения требует уточнения"
    )
    assert _work_context(entry) == ("работы и конструкции, регулируемые документом ГОСТ 12345-2020")
