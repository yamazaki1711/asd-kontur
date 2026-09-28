# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

from decimal import Decimal

from asd_kontur.application_spine.postgres import _application_engineering_projection
from asd_kontur.tender.project_engineering import (
    _attach_pit_work_scopes,
    _comparison_row,
    _comparisons,
    _display_quantity,
    _document_composition,
    _issues,
    _merge_sheet_pile_rows,
    _one_comparable_quantity,
    _scope_comparisons,
    build_project_engineering_model,
    classify_work_family,
    construction_scope_exclusion_reason,
    document_comparison_side,
    established_facility_designations,
    facility_designation,
    facility_designations,
    non_work_reason,
    professional_work_name,
    work_reconciliation_priority,
)


def test_facility_designations_preserve_multiple_explicit_project_scopes() -> None:
    assert facility_designations("КНС-4, ЛОС 8.1 и 2-КНС") == (
        "КНС 2",
        "КНС 4",
        "ЛОС 8.1",
    )
    assert facility_designation("Работы КНС-4") == "КНС 4"
    assert facility_designation("КНС-4 и ЛОС 8.1") is None


def test_document_composition_recognizes_vor_embedded_in_estimate_pdf() -> None:
    composition = _document_composition(
        [
            {
                "document_role": "ПД",
                "source_version_id": "project-version",
            },
            {
                "document_role": "Смета",
                "source_version_id": "estimate-version",
            },
        ],
        source_context={
            "vor-page": {
                "source_version_id": "estimate-version",
                "page_is_bill_of_quantities": True,
            }
        },
    )

    assert composition["available_roles"] == ["ПД", "ВОР", "Смета"]
    assert composition["embedded_vor_document_count"] == 1
    assert "ВОР в составе сметных файлов — 1" in composition["professional_summary"]


def test_vor_and_estimate_quantities_are_compared_for_the_same_scope() -> None:
    comparisons = _comparisons(
        [
            {
                "work_scope_id": "sheet-driving",
                "facility": "Место выполнения не установлено",
                "work_name": "Погружение шпунта",
                "quantities_by_document": {
                    "ВОР": [{"value": "95.028", "unit": "т"}],
                    "Смета": [{"value": "95.028", "unit": "т"}],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["left"]["document_role"] == "ВОР"
    assert comparisons[0]["right"]["document_role"] == "Смета"
    assert comparisons[0]["classification"] == "MATCH"
    assert comparisons[0]["conclusion"] == "Значения ВОР и сметы совпадают"


def test_pit_inherits_relevant_work_only_for_one_established_pit_per_facility() -> None:
    works = [
        {
            "work_scope_id": "sheet-pile-scope",
            "facility_id": "facility-kns-4",
            "family_key": "sheet_piling",
            "work_name": "Погружение шпунта",
            "work_family": "Шпунтовые работы",
            "quantities_by_document": {"РД": [{"value": "42", "unit": "т"}]},
            "materials_by_document": {},
            "source_locator_ids": ["work-locator"],
        },
        {
            "work_scope_id": "pipeline-scope",
            "facility_id": "facility-kns-4",
            "family_key": "pipeline",
            "work_name": "Монтаж трубопровода",
            "source_locator_ids": ["pipeline-locator"],
        },
        {
            "work_scope_id": "generic-excavation",
            "facility_id": "facility-kns-4",
            "family_key": "excavation",
            "work_name": "Разработка траншеи",
            "project_wording": ["Разработка грунта в траншее"],
            "source_locator_ids": ["trench-locator"],
        },
        {
            "work_scope_id": "pit-excavation",
            "facility_id": "facility-kns-4",
            "family_key": "excavation",
            "work_name": "Разработка котлована",
            "project_wording": ["Разработка грунта котлована"],
            "source_locator_ids": ["pit-excavation-locator"],
        },
    ]
    result = _attach_pit_work_scopes(
        {
            "established": [
                {
                    "pit_id": "pit-kns-4",
                    "related_facility_id": "facility-kns-4",
                    "related_works": [],
                }
            ]
        },
        works,
    )

    assert [value["work"] for value in result["established"][0]["related_works"]] == [
        "Погружение шпунта",
        "Разработка котлована",
    ]

    ambiguous = _attach_pit_work_scopes(
        {
            "established": [
                {"pit_id": "pit-a", "related_facility_id": "facility-kns-4"},
                {"pit_id": "pit-b", "related_facility_id": "facility-kns-4"},
            ]
        },
        works,
    )
    assert all(not value.get("related_works") for value in ambiguous["established"])


def test_project_work_is_not_called_omitted_while_commercial_rows_are_unclassified() -> None:
    works = [
        {
            "work_scope_id": "design-formwork",
            "facility_id": "kns-4",
            "facility": "КНС 4",
            "family_key": "formwork",
            "work_name": "Опалубочные работы",
            "document_roles": ["РД"],
            "source_locator_ids": ["design-locator"],
        }
    ]

    comparisons = _scope_comparisons(
        works,
        unclassified_works=[
            {
                "project_wording": "Неоднозначная позиция коммерческого документа",
                "document_role": "Смета",
            }
        ],
    )

    assert comparisons[0]["classification"] == "UNRESOLVED_SCOPE_MATCH"
    assert "не установлен достаточный коммерческий состав" in comparisons[0]["conclusion"]


def test_project_work_is_called_omitted_only_after_commercial_scope_is_classified() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-formwork",
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "family_key": "formwork",
                "work_name": "Опалубочные работы",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-locator"],
            },
            {
                "work_scope_id": "commercial-concrete",
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "family_key": "concrete",
                "work_name": "Бетонирование",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-locator"],
            },
        ]
    )

    formwork = next(value for value in comparisons if value["family_key"] == "formwork")
    assert formwork["classification"] == "WORK_MISSING_IN_COMMERCIAL"


def test_unclassified_commercial_row_at_another_facility_does_not_block_omission() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-formwork",
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "family_key": "formwork",
                "work_name": "Опалубочные работы",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-locator"],
            },
            {
                "work_scope_id": "commercial-concrete",
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "family_key": "reinforced_concrete",
                "work_name": "Бетонирование",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-locator"],
            },
        ],
        unclassified_works=[
            {
                "project_wording": "Неоднозначная коммерческая операция",
                "document_role": "Смета",
                "facility_id": "los-7",
                "facility": "ЛОС 7",
            }
        ],
    )

    formwork = next(value for value in comparisons if value["family_key"] == "formwork")
    assert formwork["classification"] == "WORK_MISSING_IN_COMMERCIAL"


def test_commercial_work_is_not_called_unsupported_while_design_rows_are_unclassified() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "commercial-pipeline",
                "facility_id": None,
                "facility": "Место выполнения не установлено",
                "family_key": "pipeline",
                "work_name": "Монтаж трубопровода",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-locator"],
            }
        ],
        unclassified_works=[
            {
                "project_wording": "Неоднозначная проектная операция",
                "document_role": "РД",
            }
        ],
    )

    assert comparisons[0]["classification"] == "UNRESOLVED_SCOPE_MATCH"
    assert comparisons[0]["professional_status"] == (
        "Сопоставление проектного состава не завершено"
    )


def test_comparable_quantity_normalizes_scaled_estimate_units() -> None:
    value = _one_comparable_quantity(
        (
            {"value": "0.8275", "unit": "1000 м3"},
            {"value": "827.5", "unit": "м3"},
        )
    )

    assert value == (Decimal("827.5000"), "м3")


def test_quantity_schedule_renders_scaled_estimate_units_as_physical_totals() -> None:
    assert _display_quantity("2.15", "10 м3") == ("21.5", "м3")
    assert _display_quantity("0.96", "100 шт") == ("96", "шт")
    assert _display_quantity("95.028", "т") == ("95.028", "т")


def test_sheet_pile_schedule_consolidates_repeated_commercial_scope_without_summing() -> None:
    rows = _merge_sheet_pile_rows(
        (
            {
                "facility": "Место выполнения не установлено",
                "facility_id": None,
                "family_key": "sheet_piling",
                "operation": "Погружение шпунтовых свай",
                "profiles": ["Л5"],
                "profiles_by_document": {"Смета": ["Л5"]},
                "pile_length": [],
                "quantities_by_document": {
                    "Смета": [
                        {
                            "value": "95.028",
                            "unit": "т",
                            "occurrence_count": 1,
                            "source_locator_ids": ["locator-a"],
                        }
                    ]
                },
                "waling_beams": [],
                "steel": [],
                "project_wording": ["Погружение шпунтовых свай"],
                "source_locator_ids": ["locator-a"],
                "sources_by_document": {},
                "uncertainty": "Коммерческий объём не распределён по сооружениям.",
            },
            {
                "facility": "Место выполнения не установлено",
                "facility_id": None,
                "family_key": "sheet_piling",
                "operation": "Погружение шпунта",
                "profiles": ["Л5-10"],
                "profiles_by_document": {"Смета": ["Л5-10"]},
                "pile_length": [],
                "quantities_by_document": {
                    "Смета": [
                        {
                            "value": "95.028",
                            "unit": "т",
                            "occurrence_count": 1,
                            "source_locator_ids": ["locator-b"],
                        }
                    ]
                },
                "waling_beams": [],
                "steel": [],
                "project_wording": ["Погружение шпунта"],
                "source_locator_ids": ["locator-b"],
                "sources_by_document": {},
                "uncertainty": "Коммерческий объём не распределён по сооружениям.",
            },
        )
    )

    assert len(rows) == 1
    assert rows[0]["operation"] == "Погружение шпунта"
    assert rows[0]["profiles"] == ["Л5", "Л5-10"]
    assert rows[0]["quantities_by_document"]["Смета"] == [
        {
            "value": "95.028",
            "unit": "т",
            "occurrence_count": 2,
            "source_locator_ids": ["locator-a", "locator-b"],
        }
    ]


def test_sheet_pile_allocation_question_names_known_commercial_quantities() -> None:
    issues = _issues(
        defects=[],
        comparisons=[],
        scope_comparisons=[],
        sheet_pile_schedule=[
            {
                "facility_id": None,
                "operation": "Погружение шпунта",
                "commercial_quantities": {"Смета": [{"value": "95.028", "unit": "т"}]},
            },
            {
                "facility_id": None,
                "operation": "Извлечение шпунта",
                "commercial_quantities": {"Смета": [{"value": "104.869", "unit": "т"}]},
            },
        ],
        works=[
            {
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "family_key": "sheet_piling",
                "work_name": "Устройство шпунтового ограждения",
                "quantities_by_document": {"РД": []},
                "materials_by_document": {},
                "source_locator_ids": ["design-locator"],
            },
            {
                "facility_id": None,
                "facility": "Место выполнения не установлено",
                "family_key": "sheet_piling",
                "work_name": "Погружение шпунта",
                "quantities_by_document": {"Смета": [{"value": "95.028", "unit": "т"}]},
                "materials_by_document": {},
                "source_locator_ids": ["estimate-locator"],
            },
        ],
        source_context={},
    )

    allocation = next(
        issue
        for issue in issues
        if issue["kind"] == "Коммерческий объём не распределён по сооружениям"
    )
    assert "Погружение шпунта — 95.028 т (Смета)" in allocation["recommended_action"]
    assert "Извлечение шпунта — 104.869 т (Смета)" in allocation["recommended_action"]


def test_facility_reclamation_omission_becomes_a_customer_action() -> None:
    issues = _issues(
        defects=[],
        comparisons=[],
        scope_comparisons=[
            {
                "scope_comparison_id": "reclamation-gap",
                "classification": "WORK_MISSING_IN_COMMERCIAL",
                "facility_id": "kns-8-1",
                "facility": "КНС 8.1",
                "family_key": "reclamation",
                "work": "Рекультивация",
                "conclusion": (
                    "Работа установлена в проектных документах, но соответствующая "
                    "позиция не найдена в имеющихся ВОР/сметах."
                ),
                "source_locator_ids": ["design-reclamation"],
            }
        ],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )

    issue = issues[0]
    assert issue["kind"] == "Возможная неучтённая работа"
    assert issue["location"] == "КНС 8.1"
    assert "Рекультивация" in issue["recommended_action"]


def _source(locator: str, document: str, page: int) -> tuple[str, dict[str, object]]:
    return locator, {
        "source_version_id": f"source-{locator}",
        "document_version": 2,
        "safe_display_name": document,
        "locator_value": {"page": page},
    }


def _model() -> dict[str, object]:
    source_context = dict(
        [
            _source("facility", "КР. Лист 8.pdf", 8),
            _source("pit-a", "КР. Лист 8.pdf", 8),
            _source("pit-b", "КР. Лист 9.pdf", 9),
            _source("work-rd", "РД КР.pdf", 12),
            _source("work-vor", "ВОР.xlsx.pdf", 4),
            _source("q-rd", "РД КР.pdf", 12),
            _source("q-vor", "ВОР.xlsx.pdf", 4),
            _source("material", "Спецификация.pdf", 3),
        ]
    )
    facilities = [
        {
            "identity_candidate_id": "facility-group",
            "identity_kind": "facility",
            "canonical_label": "КНС-2",
            "candidate_labels": ["КНС-2", "КНС 2"],
            "member_structure_node_ids": ["facility-node"],
            "source_locator_ids": ["facility", "work-rd", "work-vor"],
        }
    ]
    candidates = {
        "project_fields": [
            {
                "label": "object_name",
                "value": "Система водоотведения испытательного объекта",
                "source_version_id": "source-a",
                "source_locator_id": "facility",
            },
            {
                "label": "purpose",
                "value": "Отведение поверхностных сточных вод",
                "source_version_id": "source-a",
                "source_locator_id": "facility",
            },
            {
                "label": "Производительность КНС-2",
                "value": "75 л/с",
                "source_version_id": "source-a",
                "source_locator_id": "facility",
            },
        ],
        "work_types": [
            {
                "candidate_id": "work-rd",
                "version": 1,
                "value": "Погружение шпунтовых свай КНС-2",
                "label": "погружение шпунтовых свай кнс 2",
                "source_version_id": "source-rd",
                "source_locator_id": "work-rd",
                "source_role": "working_documentation",
                "scope_key": "КНС-2",
            },
            {
                "candidate_id": "work-vor",
                "version": 1,
                "value": "Погружение шпунтовых свай КНС-2",
                "label": "погружение шпунтовых свай кнс 2",
                "source_version_id": "source-vor",
                "source_locator_id": "work-vor",
                "source_role": "bill_of_quantities",
                "scope_key": "КНС-2",
            },
            {
                "candidate_id": "unclassified",
                "value": "Особая технологическая операция",
                "label": "особая технологическая операция",
                "source_version_id": "source-rd",
                "source_locator_id": "work-rd",
            },
            {
                "candidate_id": "heading",
                "value": "Строительные работы",
                "label": "строительные работы",
                "source_version_id": "source-vor",
                "source_locator_id": "work-vor",
            },
        ],
        "quantities": [
            {
                "candidate_id": "quantity-rd",
                "work_candidate_id": "work-rd",
                "normalized_value": "438",
                "normalized_unit": "т",
                "source_locator_id": "q-rd",
            },
            {
                "candidate_id": "quantity-vor",
                "work_candidate_id": "work-vor",
                "normalized_value": "361",
                "normalized_unit": "т",
                "source_locator_id": "q-vor",
            },
        ],
        "materials": [
            {
                "candidate_id": "material",
                "work_candidate_id": "work-rd",
                "value": "Шпунт Л5-УМ, сталь С255",
                "normalized_name": "шпунт л5 ум сталь с255",
                "source_locator_id": "material",
            }
        ],
    }
    pit_inventory = {
        "candidate_pits": [
            {
                "canonical_label": "рабочий котлован для КНС-2",
                "associated_facility_designation": "КНС 2",
                "aliases": ["Рабочий котлован для КНС-2"],
                "source_locator_ids": ["pit-a"],
            },
            {
                "canonical_label": "приёмный котлован для КНС-2",
                "associated_facility_designation": "КНС 2",
                "aliases": ["Приёмный котлован для КНС-2"],
                "source_locator_ids": ["pit-b"],
            },
            {
                "canonical_label": "котлованы на участке",
                "associated_facility_designation": None,
                "aliases": ["котлованы на участке"],
                "source_locator_ids": ["pit-b"],
            },
        ],
        "coverage": {"disposition_counts": {"ambiguous": 1}},
    }
    return build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates=candidates,
        structure_nodes=[],
        identity_components=facilities,
        pit_inventory=pit_inventory,
        defects=[{"defect_id": "technical", "defect_kind": "ambiguous_source_match"}],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
        work_resolutions={
            "work-rd": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "sheet_piling",
                "operation": "Погружение шпунта",
                "facility": "КНС 2",
                "quantity_reviews": [
                    {"quantity_candidate_id": "quantity-rd", "status": "WORK_QUANTITY"}
                ],
            },
            "work-vor": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "sheet_piling",
                "operation": "Погружение шпунта",
                "facility": "КНС 2",
                "quantity_reviews": [
                    {"quantity_candidate_id": "quantity-vor", "status": "WORK_QUANTITY"}
                ],
            },
        },
    )


def test_model_exposes_professional_project_pits_and_sheet_pile_schedule() -> None:
    model = _model()

    assert model["model_version"] == "project-engineering-model-v33"
    assert model["project"]["name"]["value"] == ("Система водоотведения испытательного объекта")
    assert [item["name"] for item in model["facilities"]] == ["КНС 2"]
    assert model["pits"]["established_count"] == 2
    assert model["pits"]["is_final"] is False
    assert "окончательное количество" in model["pits"]["professional_answer"]

    works = model["works"]
    assert len(works) == 1
    assert works[0]["facility"] == "КНС 2"
    assert works[0]["work_name"] == "Погружение шпунта"
    assert works[0]["materials_by_document"]["РД"][0]["name"] == ("Шпунт Л5-УМ, сталь С255")
    assert model["unclassified_works"][0]["project_wording"] == ("Особая технологическая операция")
    assert model["excluded_non_work_observations"][0]["project_wording"] == ("Строительные работы")
    assert model["work_classification"]["excluded_non_work_observation_count"] == 1
    assert model["scope_comparisons"][0]["classification"] == "MATCH"
    assert model["sheet_pile_schedule"][0]["operation"] == "Погружение шпунта"
    assert model["facility_cards"][0]["characteristics"] == [
        {
            "label": "Производительность КНС-2",
            "value": "75 л/с",
            "source_locator_ids": ["facility"],
            "sources": [
                {
                    "document": "КР. Лист 8.pdf",
                    "version": 2,
                    "page": 8,
                    "source_version_id": "source-facility",
                    "source_locator_id": "facility",
                }
            ],
            "status": "Установлено по явно указанному сооружению",
        }
    ]
    assert model["document_composition"]["available_roles"] == [
        "РД",
        "Спецификация",
        "ВОР",
    ]


def test_omission_names_only_the_supplied_commercial_denominator() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-reclamation",
                "facility_id": "kns-8-1",
                "facility": "КНС 8.1",
                "family_key": "reclamation",
                "work_name": "Рекультивация",
                "document_roles": ["ПД"],
                "source_locator_ids": ["design-locator"],
            },
            {
                "work_scope_id": "commercial-concrete",
                "facility_id": "kns-8-1",
                "facility": "КНС 8.1",
                "family_key": "reinforced_concrete",
                "work_name": "Бетонирование",
                "document_roles": ["Смета"],
                "source_locator_ids": ["estimate-locator"],
            },
        ],
        available_document_roles=["ПД", "Смета"],
    )

    reclamation = next(row for row in comparisons if row["family_key"] == "reclamation")
    assert reclamation["classification"] == "WORK_MISSING_IN_COMMERCIAL"
    assert reclamation["conclusion"].endswith("не найдена в предоставленных сметах.")


def test_exact_structural_relationship_assigns_work_without_document_wide_guessing() -> None:
    source_context = dict(
        [
            _source("facility-a", "КР.pdf", 1),
            _source("facility-b", "КР.pdf", 2),
            _source("related-work", "КР.pdf", 17),
            _source("unrelated-work", "КР.pdf", 18),
        ]
    )
    identity_components = [
        {
            "identity_kind": "facility",
            "canonical_label": "КНС-4",
            "candidate_labels": ["КНС-4", "КНС 4"],
            "member_structure_node_ids": ["facility-node"],
            "source_locator_ids": ["facility-a", "facility-b"],
        }
    ]
    candidates = {
        "project_fields": [],
        "work_types": [
            {
                "candidate_id": "related",
                "version": 1,
                "value": "Прокладка трубопровода",
                "source_version_id": "source-related-work",
                "source_locator_id": "related-work",
                "source_role": "working_documentation",
            },
            {
                "candidate_id": "unrelated",
                "version": 1,
                "value": "Прокладка трубопровода",
                "source_version_id": "source-unrelated-work",
                "source_locator_id": "unrelated-work",
                "source_role": "working_documentation",
            },
        ],
        "quantities": [],
        "materials": [],
    }
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates=candidates,
        structure_nodes=[],
        identity_components=identity_components,
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
        structure_relationships=[
            {
                "relationship_kind": "serves",
                "subject_raw_name": "Напорный трубопровод",
                "object_raw_name": "КНС-4",
                "subject_structure_node_id": "pipeline-node",
                "object_structure_node_id": "facility-node",
                "source_locator_id": "related-work",
                "resolution_state": "resolved_same_evidence",
            }
        ],
    )

    related = next(row for row in model["works"] if row["facility_id"] is not None)
    unrelated = next(row for row in model["works"] if row["facility_id"] is None)
    assert related["facility"] == "КНС 4"
    assert related["status"].startswith("Работа связана с сооружением")
    assert unrelated["facility"] == "Место выполнения не установлено"
    assert model["facility_cards"][0]["structures"] == [
        {
            "name": "Напорный трубопровод",
            "relationship": "Обслуживает сооружение",
            "source_locator_ids": ["related-work"],
            "sources": [
                {
                    "document": "КР.pdf",
                    "version": 2,
                    "page": 17,
                    "source_version_id": "source-related-work",
                    "source_locator_id": "related-work",
                }
            ],
            "status": "Установлено по явной связи в исходном документе",
        }
    ]


def test_unassigned_sheet_pile_material_does_not_inherit_unrelated_work_wording() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "excavation",
                    "version": 1,
                    "value": "Разработка грунта",
                    "source_version_id": "source-work",
                    "source_locator_id": "work",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [],
            "materials": [
                {
                    "candidate_id": "sheet-material",
                    "work_candidate_id": "excavation",
                    "value": "Шпунт Л5-УМ, сталь С255",
                    "normalized_name": "шпунт л5 ум сталь с255",
                    "source_locator_id": "material",
                }
            ],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("work", "ПОС.pdf", 10),
                _source("material", "Спецификация.pdf", 4),
            ]
        ),
    )

    sheet_row = model["sheet_pile_schedule"][0]
    assert sheet_row["profiles"] == ["Л5УМ"]
    assert sheet_row["project_wording"] == ["Шпунт Л5-УМ, сталь С255"]
    assert sheet_row["quantities_by_document"] == {}
    assert sheet_row["sources_by_document"]["ПД"][0]["document"] == "Спецификация.pdf"


def test_contextual_resolution_can_refine_broad_deterministic_family() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "collector-demolition",
                    "version": 3,
                    "value": "Демонтаж существующего железобетонного коллектора",
                    "source_version_id": "source-work",
                    "source_locator_id": "work",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict([_source("work", "ПОС.pdf", 12)]),
        work_resolutions={
            "collector-demolition": {
                "candidate_version": 3,
                "status": "MATCHED",
                "family_key": "demolition",
                "operation": "Демонтаж железобетонного коллектора",
                "facility": None,
                "reason": "Операция является демонтажем существующего сооружения.",
            }
        },
    )

    assert model["works"][0]["family_key"] == "demolition"
    assert model["works"][0]["work_name"] == "Демонтаж железобетонного коллектора"


def test_transport_and_waste_operations_remain_visible_as_commercial_work() -> None:
    assert classify_work_family("Перевозка строительных грузов") == (
        "transportation",
        "Перевозка строительных грузов и материалов",
    )
    assert classify_work_family("Сбор и размещение строительных отходов") == (
        "waste_management",
        "Обращение со строительными отходами",
    )
    assert classify_work_family("Доработка грунта вручную") == (
        "excavation",
        "Разработка котлованов и земляные работы",
    )


def test_common_project_operations_use_reusable_construction_families() -> None:
    expected = {
        "Гидравлическое погружение иглофильтров": "dewatering",
        "Засыпка вручную траншей местным грунтом": "backfill",
        "Укладка труб на песчаную подушку": "pipeline",
        "Устройство дополнительных колодцев": "chambers_wells",
        "Нанесение праймера битумного": "waterproofing",
        "Установка бортовых камней": "roadworks",
        "Прокладка и монтаж сетей связи": "communications",
        "Лабораторный контроль качества очистки стоков": "testing",
        "Вертикальная планировка участка": "site_preparation",
        "Вывоз загрязненного нефтепродуктами грунта": "soil_disposal",
        "Погрузочно-разгрузочные работы на площадке": "loading_unloading",
        "Отрывка траншеи экскаватором": "excavation",
        "Закручивание винтовых свай": "pile_foundation",
        "Монтаж насосного оборудования": "equipment_installation",
        "Испытание очистного сооружения на герметичность": "testing",
        "Монтаж силовых кабелей вручную": "electrical",
        "Посев многолетних трав": "landscaping",
        "Корчевка пней на строительной площадке": "site_preparation",
        "Устройство насыпи из ранее разработанного грунта": "site_preparation",
        "Заполнение полости бетоном В7,5": "reinforced_concrete",
        "Затирка цементным раствором швов колодца": "chambers_wells",
        "Монтаж лестницы КЛ-1": "structural_steel",
        "Восстановление асфальтобетонного покрытия": "roadworks",
        "Восстановление экологической тропы": "roadworks",
        "Вывоз строительного мусора": "waste_management",
        "Монтаж канализационных насосных станций": "equipment_installation",
        "Шеф-монтажные работы": "equipment_installation",
        "Устройство складских площадок": "site_preparation",
        "Размещение мобильных инвентарных зданий": "site_preparation",
        "Вырубка": "site_preparation",
        "Вывоз леса": "site_preparation",
        "Дноуглубительные работы": "excavation",
        "Установка круглых стеклокомпозитных колодцев для ЛОС": "chambers_wells",
        "Погрузка в автотранспортное средство: мусор строительный": "waste_management",
        "Покрытие кабеля, проложенного в траншее, лентой сигнальной": "electrical",
        "Монтаж системы наружного электроосвещения": "electrical",
        "Устройство дополнительного слоя основания из щебеночно-песчаной смеси": "roadworks",
        "Рытье траншеи экскаватором": "excavation",
        "Установка задвижек стальных диаметром 250 мм": "pipeline",
        "Погрузка порубочного материала в автотранспорт": "site_preparation",
        "Монтаж водопонизительных насосов": "dewatering",
        "Укрепление стенок траншеи инвентарными щитами": "bracing",
        "Утрамбовка грунта вокруг колодца": "compaction",
        "Подсыпка песком средней крупности": "pit_preparation",
        "Монтаж габионов для защиты откоса": "gabion_erosion_protection",
        "Геодезические работы по разбивке осей": "surveying",
        "Удаление кустарников на строительной площадке": "site_preparation",
    }

    for wording, family_key in expected.items():
        result = classify_work_family(wording)
        assert result is not None
        assert result[0] == family_key

    assert classify_work_family("Вывоз после приемки со склада готового оборудования") is None


def test_estimate_resource_code_does_not_become_a_construction_work_scope() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "resource-row",
                    "version": 1,
                    "value": "91.08.09-024 Трамбовки пневматические",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "resource-locator",
                    "source_role": "local_estimate",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict([_source("resource-locator", "Смета.pdf", 8)]),
    )

    assert model["works"] == []
    assert model["unclassified_works"] == []
    assert len(model["excluded_non_work_observations"]) == 1
    assert "ресурс" in model["excluded_non_work_observations"][0]["exclusion_reason"].casefold()


def test_operation_sections_do_not_inflate_the_current_construction_schedule() -> None:
    assert construction_scope_exclusion_reason("Раздел ПД №10 005-ТБЭ.pdf") is not None
    assert construction_scope_exclusion_reason("Раздел ПД №13 005-СОЭ.pdf") is not None
    assert construction_scope_exclusion_reason("Раздел ПД №4 005-КР1.pdf") is None

    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "future-repair",
                    "version": 1,
                    "value": "Ремонт трубопровода",
                    "source_version_id": "source-operation",
                    "source_locator_id": "operation-locator",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict([_source("operation-locator", "Раздел ПД №10 005-ТБЭ.pdf", 8)]),
    )

    assert model["works"] == []
    assert model["unclassified_works"] == []
    assert len(model["excluded_non_work_observations"]) == 1
    assert (
        "текущего строительства" in model["excluded_non_work_observations"][0]["exclusion_reason"]
    )
    assert model["work_classification"]["construction_scope_observation_count"] == 0
    assert model["work_classification"]["construction_scope_classified_percent"] == 0.0


def test_professional_work_names_keep_materially_different_operations_separate() -> None:
    expected = {
        ("roadworks", "Устройство основания из щебеночно-песчаной смеси"): (
            "Устройство дорожного основания"
        ),
        ("roadworks", "Восстановление асфальтобетонного покрытия"): (
            "Устройство дорожного покрытия"
        ),
        ("roadworks", "Восстановление экологической тропы"): ("Восстановление экологической тропы"),
        ("chambers_wells", "Установка круглого колодца"): "Устройство колодца",
        ("chambers_wells", "Монтаж корпуса КНС"): "Монтаж КНС",
        ("electrical", "Монтаж опор наружного освещения"): "Монтаж опор освещения",
        ("electrical", "Прокладка силового кабеля"): "Прокладка кабеля",
        ("pit_preparation", "Бетонная подготовка под плиту"): ("Устройство бетонной подготовки"),
        ("pit_preparation", "Песчаное основание под трубопровод"): (
            "Устройство песчаного основания"
        ),
        ("pipeline", "Гидравлические испытания трубопровода"): ("Испытание трубопровода"),
        ("pipeline", "Промывка трубопровода перед вводом"): ("Очистка/промывка трубопровода"),
        ("pipeline", "Восстановление участка трубопровода"): ("Восстановление/ремонт трубопровода"),
        ("pipeline", "Вскрытие демонтируемого трубопровода"): "Вскрытие трубопровода",
        ("pipeline", "Изоляция стального трубопровода"): "Изоляция трубопровода",
        ("gabion_erosion_protection", "Монтаж габионов"): ("Устройство габионных конструкций"),
    }

    for (family_key, wording), work_name in expected.items():
        assert professional_work_name(family_key, wording) == work_name


def test_same_family_operations_remain_distinct_engineering_scopes() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "trench",
                    "version": 1,
                    "value": "Разработка траншеи для КНС-2",
                    "source_version_id": "source-design",
                    "source_locator_id": "trench-locator",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "pit",
                    "version": 1,
                    "value": "Разработка котлована КНС-2",
                    "source_version_id": "source-design",
                    "source_locator_id": "pit-locator",
                    "source_role": "working_documentation",
                },
            ],
            "quantities": [
                {
                    "candidate_id": "trench-quantity",
                    "work_candidate_id": "trench",
                    "value": "120",
                    "normalized_value": "120",
                    "unit": "м3",
                    "source_locator_id": "trench-locator",
                },
                {
                    "candidate_id": "pit-quantity",
                    "work_candidate_id": "pit",
                    "value": "450",
                    "normalized_value": "450",
                    "unit": "м3",
                    "source_locator_id": "pit-locator",
                },
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-2",
                "candidate_labels": ["КНС-2"],
                "member_structure_node_ids": [],
                "source_locator_ids": [],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("trench-locator", "КР.pdf", 3),
                _source("pit-locator", "КР.pdf", 4),
            ]
        ),
        work_resolutions={
            "trench": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "excavation",
                "operation": "Разработка траншей",
                "quantity_reviews": [
                    {"quantity_candidate_id": "trench-quantity", "status": "WORK_QUANTITY"}
                ],
            },
            "pit": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "excavation",
                "operation": "Разработка котлована",
                "quantity_reviews": [
                    {"quantity_candidate_id": "pit-quantity", "status": "WORK_QUANTITY"}
                ],
            },
        },
    )

    by_name = {row["work_name"]: row for row in model["works"]}
    assert set(by_name) == {"Разработка траншей", "Разработка котлована"}
    assert by_name["Разработка траншей"]["quantities_by_document"]["РД"][0]["value"] == ("120")
    assert by_name["Разработка котлована"]["quantities_by_document"]["РД"][0]["value"] == ("450")


def test_unassigned_generic_operations_do_not_form_one_project_wide_scope() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "steel-pipeline",
                    "version": 1,
                    "value": "Монтаж трубопровода из стальных труб",
                    "source_version_id": "source-a",
                    "source_locator_id": "steel-pipeline-locator",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "polymer-pipeline",
                    "version": 1,
                    "value": "Монтаж полиэтиленового трубопровода",
                    "source_version_id": "source-b",
                    "source_locator_id": "polymer-pipeline-locator",
                    "source_role": "bill_of_quantities",
                },
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("steel-pipeline-locator", "РД.pdf", 4),
                _source("polymer-pipeline-locator", "ВОР.xlsx", 8),
            ]
        ),
    )

    assert len(model["works"]) == 2
    assert {work["work_name"] for work in model["works"]} == {"Монтаж трубопровода"}
    assert {tuple(work["project_wording"]) for work in model["works"]} == {
        ("Монтаж полиэтиленового трубопровода",),
        ("Монтаж трубопровода из стальных труб",),
    }


def test_broad_unassigned_family_is_not_reported_as_a_commercial_match() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "design-backfill",
                    "version": 1,
                    "value": "Засыпка котлована песком",
                    "source_version_id": "source-design",
                    "source_locator_id": "design-backfill-locator",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "commercial-backfill",
                    "version": 1,
                    "value": "Обратная засыпка пазух",
                    "source_version_id": "source-vor",
                    "source_locator_id": "commercial-backfill-locator",
                    "source_role": "bill_of_quantities",
                },
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("design-backfill-locator", "РД.pdf", 4),
                _source("commercial-backfill-locator", "ВОР.xlsx", 8),
            ]
        ),
    )

    assert len(model["scope_comparisons"]) == 1
    comparison = model["scope_comparisons"][0]
    assert comparison["classification"] == "UNRESOLVED_SCOPE_MATCH"
    assert comparison["professional_status"] == (
        "Требуется связать проектную и коммерческую позиции"
    )


def test_facility_specific_document_title_assigns_same_named_works_to_distinct_facilities() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "work-kns-2",
                    "version": 1,
                    "value": "Разработка котлована",
                    "source_version_id": "source-kns-2",
                    "source_locator_id": "work-kns-2-locator",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "work-kns-4",
                    "version": 1,
                    "value": "Разработка котлована",
                    "source_version_id": "source-kns-4",
                    "source_locator_id": "work-kns-4-locator",
                    "source_role": "working_documentation",
                },
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-2",
                "candidate_labels": ["КНС-2"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["kns-2-a", "kns-2-b"],
            },
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-4",
                "candidate_labels": ["КНС-4"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["kns-4-a", "kns-4-b"],
            },
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={
            "work-kns-2-locator": {
                "source_version_id": "source-kns-2",
                "document_version": 1,
                "safe_display_name": "КНС-2. Конструктивные решения.pdf",
                "locator_value": {"page": 12},
            },
            "work-kns-4-locator": {
                "source_version_id": "source-kns-4",
                "document_version": 1,
                "safe_display_name": "КНС-4. Конструктивные решения.pdf",
                "locator_value": {"page": 12},
            },
        },
    )

    assert {(value["facility"], value["work_name"]) for value in model["works"]} == {
        ("КНС 2", "Разработка котлована"),
        ("КНС 4", "Разработка котлована"),
    }
    assert all("названии исходного документа" in value["status"] for value in model["works"])


def test_quantity_meaning_review_keeps_dimensions_out_of_work_volume() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "pit-work",
                    "version": 2,
                    "value": "Разработка котлована КНС-2",
                    "source_version_id": "source-design",
                    "source_locator_id": "work-locator",
                    "source_role": "working_documentation",
                }
            ],
            "quantities": [
                {
                    "candidate_id": "pit-volume",
                    "work_candidate_id": "pit-work",
                    "value": "450",
                    "normalized_value": "450",
                    "unit": "м3",
                    "source_locator_id": "volume-locator",
                },
                {
                    "candidate_id": "pit-depth",
                    "work_candidate_id": "pit-work",
                    "value": "5",
                    "normalized_value": "5",
                    "unit": "м",
                    "source_locator_id": "depth-locator",
                },
                {
                    "candidate_id": "pit-width",
                    "work_candidate_id": "pit-work",
                    "value": "12",
                    "normalized_value": "12",
                    "unit": "м",
                    "source_locator_id": "width-locator",
                },
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-2",
                "candidate_labels": ["КНС-2"],
                "member_structure_node_ids": [],
                "source_locator_ids": [],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("work-locator", "КР.pdf", 3),
                _source("volume-locator", "КР.pdf", 3),
                _source("depth-locator", "КР.pdf", 3),
                _source("width-locator", "КР.pdf", 3),
            ]
        ),
        work_resolutions={
            "pit-work": {
                "candidate_version": 2,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "excavation",
                "operation": "Разработка котлована",
                "facility": "КНС 2",
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "pit-volume",
                        "status": "WORK_QUANTITY",
                        "reason": "Объём разработки грунта.",
                    },
                    {
                        "quantity_candidate_id": "pit-depth",
                        "status": "DIMENSION",
                        "reason": "Глубина котлована.",
                    },
                ],
            }
        },
    )

    work = model["works"][0]
    assert [(value["value"], value["unit"]) for value in work["quantities_by_document"]["РД"]] == [
        ("450", "м3")
    ]
    assert {value["status"] for value in work["quantity_interpretations"]} == {
        "WORK_QUANTITY",
        "DIMENSION",
        "UNREVIEWED",
    }
    assert model["summary"]["reviewed_quantity_observation_count"] == 2
    assert model["summary"]["accepted_work_quantity_observation_count"] == 1
    assert model["summary"]["pending_quantity_observation_count"] == 1
    assert work["quantity_validation_status"] == (
        "Часть связанных значений ещё требует смысловой проверки"
    )


def test_reviewed_synonyms_compare_only_within_same_facility_and_operation() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "design-driving",
                    "version": 1,
                    "value": "Погружение шпунтовых свай КНС-2",
                    "source_version_id": "source-design",
                    "source_locator_id": "design-work",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "estimate-driving",
                    "version": 1,
                    "value": "Забивка стального шпунта для КНС-2",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "estimate-work",
                    "source_role": "local_estimate",
                },
            ],
            "quantities": [
                {
                    "candidate_id": "design-mass",
                    "work_candidate_id": "design-driving",
                    "normalized_value": "438",
                    "normalized_unit": "т",
                    "source_locator_id": "design-quantity",
                },
                {
                    "candidate_id": "estimate-mass",
                    "work_candidate_id": "estimate-driving",
                    "normalized_value": "361",
                    "normalized_unit": "т",
                    "source_locator_id": "estimate-quantity",
                },
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_candidate_id": "scope-comparison-facility-kns-2",
                "identity_kind": "facility",
                "canonical_label": "КНС-2",
                "candidate_labels": ["КНС-2"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["design-work", "estimate-work"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("design-work", "КР.pdf", 11),
                _source("estimate-work", "Смета.pdf", 7),
                _source("design-quantity", "КР.pdf", 11),
                _source("estimate-quantity", "Смета.pdf", 7),
            ]
        ),
        work_resolutions={
            "design-driving": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "sheet_piling",
                "operation": "Погружение шпунта",
                "facility": "КНС 2",
                "quantity_reviews": [
                    {"quantity_candidate_id": "design-mass", "status": "WORK_QUANTITY"}
                ],
            },
            "estimate-driving": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "sheet_piling",
                "operation": "Забивка стального шпунта",
                "facility": "КНС 2",
                "quantity_reviews": [
                    {"quantity_candidate_id": "estimate-mass", "status": "WORK_QUANTITY"}
                ],
            },
        },
    )

    comparisons = [
        value for value in model["quantity_comparisons"] if value.get("scope_match_basis")
    ]
    assert len(comparisons) == 1, model["works"]
    assert comparisons[0]["facility"] == "КНС 2"
    assert comparisons[0]["work"] == "Погружение шпунта"
    assert comparisons[0]["left"] == {"document_role": "РД", "value": "438", "unit": "т"}
    assert comparisons[0]["right"] == {
        "document_role": "Смета",
        "value": "361",
        "unit": "т",
    }
    assert comparisons[0]["difference"] == "77"


def test_exact_cross_document_operation_compares_without_inventing_facility() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "design-light-removal",
                    "version": 1,
                    "value": "Демонтаж светильников",
                    "source_version_id": "source-design",
                    "source_locator_id": "design-work",
                    "source_role": "project_documentation",
                },
                {
                    "candidate_id": "estimate-light-removal",
                    "version": 1,
                    "value": "Демонтаж: светильников для люминесцентных ламп",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "estimate-work",
                    "source_role": "local_estimate",
                },
            ],
            "quantities": [
                {
                    "candidate_id": "design-count",
                    "work_candidate_id": "design-light-removal",
                    "normalized_value": "3",
                    "normalized_unit": "шт.",
                    "source_locator_id": "design-quantity",
                },
                {
                    "candidate_id": "estimate-count",
                    "work_candidate_id": "estimate-light-removal",
                    "normalized_value": "0.03",
                    "normalized_unit": "100 шт",
                    "source_locator_id": "estimate-quantity",
                },
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict(
            [
                _source("design-work", "Проект.pdf", 4),
                _source("estimate-work", "Смета.pdf", 8),
                _source("design-quantity", "Проект.pdf", 4),
                _source("estimate-quantity", "Смета.pdf", 8),
            ]
        ),
        work_resolutions={
            "design-light-removal": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v6",
                "status": "MATCHED",
                "family_key": "demolition",
                "operation": "Демонтаж светильников",
                "facility": None,
                "quantity_reviews": [
                    {"quantity_candidate_id": "design-count", "status": "WORK_QUANTITY"}
                ],
            },
            "estimate-light-removal": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v6",
                "status": "MATCHED",
                "family_key": "demolition",
                "operation": "Демонтаж светильников",
                "facility": None,
                "quantity_reviews": [
                    {"quantity_candidate_id": "estimate-count", "status": "WORK_QUANTITY"}
                ],
            },
        },
    )

    assert len(model["quantity_comparisons"]) == 1
    comparison = model["quantity_comparisons"][0]
    assert comparison["left"] == {"document_role": "ПД", "value": "3", "unit": "шт"}
    assert comparison["right"] == {"document_role": "Смета", "value": "3", "unit": "шт"}
    assert comparison["classification"] == "MATCH"
    assert "к одной операции" in comparison["scope_match_basis"]


def test_obvious_estimate_resources_do_not_consume_qwen_reconciliation() -> None:
    assert non_work_reason("4-100-060") == "Сметный шифр без описания строительной операции"
    assert non_work_reason("Щиты настила, толщина 25 мм") == (
        "Описание материала, а не строительной операции"
    )
    assert non_work_reason("Техническое обслуживание оборудования") == (
        "Эксплуатационная операция, а не строительная работа"
    )
    assert non_work_reason("Предварительное отстаивание сточных вод") == (
        "Эксплуатационная операция, а не строительная работа"
    )
    assert non_work_reason("строительных работ") == (
        "Обобщённый заголовок без конкретной строительной операции"
    )
    assert non_work_reason("01.7.03.01-0001 Вода") == (
        "Сметный ресурс с кодом, а не отдельная строительная операция"
    )
    assert non_work_reason("Объем насыпи") == (
        "Проектный показатель или количество, а не отдельная строительная операция"
    )
    assert non_work_reason("БСТ В7,5 П2 W2 (заделка швов)") == (
        "Описание бетонной смеси, а не отдельная строительная операция"
    )


def test_reconciliation_prioritizes_descriptive_construction_operations() -> None:
    operation = work_reconciliation_priority(
        "Укладка труб на песчаную подушку",
        document_role="working_documentation",
        nearby_context="КНС-4. Монтаж трубопровода",
        has_facility_hint=True,
    )
    resource = work_reconciliation_priority(
        "Техническое обслуживание",
        document_role="project_documentation",
        nearby_context="Общие данные",
    )

    assert operation > resource


def test_reconciliation_prioritizes_critical_known_family_for_location_resolution() -> None:
    sheet_pile = work_reconciliation_priority(
        "Устройство ограждения",
        document_role="project_documentation",
        nearby_context="Котлован сооружения",
        family_key="sheet_piling",
    )
    generic = work_reconciliation_priority(
        "Устройство ограждения",
        document_role="project_documentation",
        nearby_context="Котлован сооружения",
    )

    assert sheet_pile > generic


def test_reconciliation_prioritizes_explicit_facility_context_over_unscoped_quantity_work() -> None:
    scoped = work_reconciliation_priority(
        "Устройство основания",
        document_role="project_documentation",
        nearby_context="КНС-4",
        has_facility_hint=True,
    )
    unscoped = work_reconciliation_priority(
        "Разработка и перемещение грунта",
        document_role="estimate",
        nearby_context="Общие объёмы",
        family_key="excavation",
    )

    assert scoped > unscoped


def test_reconciliation_prioritizes_scoped_design_commercial_pair() -> None:
    comparison_scope = work_reconciliation_priority(
        "Устройство основания",
        document_role="project_documentation",
        nearby_context="КНС-4",
        has_facility_hint=True,
        comparison_ready_scope=True,
    )
    isolated_scope = work_reconciliation_priority(
        "Устройство основания",
        document_role="project_documentation",
        nearby_context="КНС-4",
        has_facility_hint=True,
    )

    assert comparison_scope > isolated_scope
    assert document_comparison_side("project_documentation", "КР.pdf") == "design"
    assert document_comparison_side("project_documentation", "005.2-2025-СМ4.pdf") == "commercial"
    assert document_comparison_side("bill_of_quantities", "ВОР.xlsx") == "commercial"


def test_established_facilities_exclude_equipment_model_designations() -> None:
    assert established_facility_designations(
        [
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-4",
                "candidate_labels": ["КНС-4"],
                "source_locator_ids": ["facility-a", "facility-b"],
            },
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-270/12С/3,0-9,1/4,82",
                "candidate_labels": ["КНС-270/12С/3,0-9,1/4,82"],
                "source_locator_ids": ["equipment-row"],
            },
        ]
    ) == ("КНС 4",)


def test_unmatched_facility_shaped_token_does_not_create_work_location() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "pipeline-model-mark",
                    "version": 1,
                    "value": "Монтаж трубопровода для ЛОС 8",
                    "source_version_id": "source-work",
                    "source_locator_id": "work-locator",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "ЛОС 8.1",
                "candidate_labels": ["ЛОС 8.1"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["facility-a", "facility-b"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict([_source("work-locator", "Общие данные.pdf", 2)]),
    )

    assert model["works"][0]["facility_id"] is None
    assert model["works"][0]["facility"] == "Место выполнения не установлено"


def test_validated_facility_heading_scopes_sibling_work_on_same_page() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "pipeline-heading-work",
                    "version": 1,
                    "value": "Прокладка трубопровода",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "pipeline-work",
                    "source_role": "local_estimate",
                },
                {
                    "candidate_id": "pipeline-base-work",
                    "version": 1,
                    "value": "Устройство основания под трубопровод",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "base-work",
                    "source_role": "local_estimate",
                },
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-4",
                "candidate_labels": ["КНС-4"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["facility-a", "facility-b"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={
            "pipeline-work": {
                "source_version_id": "source-estimate",
                "document_version": 1,
                "safe_display_name": "Смета трубопровода.pdf",
                "locator_value": {"page": 18},
            },
            "base-work": {
                "source_version_id": "source-estimate",
                "document_version": 1,
                "safe_display_name": "Смета трубопровода.pdf",
                "locator_value": {"page": 18},
            },
        },
        work_resolutions={
            "pipeline-heading-work": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v6",
                "status": "MATCHED",
                "family_key": "pipeline",
                "operation": "Прокладка трубопровода",
                "facility": "КНС 4",
                "confidence": "0.95",
                "reason": "Заголовок сметы явно относится к КНС 4.",
            }
        },
    )

    assert {(work["facility"], work["work_name"]) for work in model["works"]} == {
        ("КНС 4", "Монтаж трубопровода"),
        ("КНС 4", "Устройство основания под трубопровод"),
    }
    assert all("единственному" in work["status"] for work in model["works"])


def test_model_calculates_real_role_comparison_and_hides_technical_defects() -> None:
    model = _model()

    assert len(model["quantity_comparisons"]) == 1
    comparison = model["quantity_comparisons"][0]
    assert comparison["left"] == {"document_role": "РД", "value": "438", "unit": "т"}
    assert comparison["right"] == {"document_role": "ВОР", "value": "361", "unit": "т"}
    assert comparison["difference"] == "77"
    assert comparison["comparison_kind"] == "quantity"
    assert comparison["classification"] == "QUANTITY_DIFFERENCE"
    assert model["issues"][0]["kind"] == "Расхождение объёмов"
    assert all(item["issue_id"] != "technical" for item in model["issues"])
    assert model["customer_questions"][0]["question"].startswith("Запросить у Заказчика")


def test_duration_comparison_is_not_presented_as_construction_quantity() -> None:
    comparison = _comparison_row(
        {"work_scope_id": "scope", "facility": "ЛОС 4", "work_name": "Строительство ЛОС"},
        "ПД",
        "Смета",
        (Decimal("4.5"), "месяцев"),
        (Decimal("3"), "месяца"),
        Decimal("1.5"),
        "Разница ПД ↔ Смета: 1.5 месяца",
    )

    assert comparison["comparison_kind"] == "duration"
    assert comparison["professional_status"] == "Различается продолжительность"


def test_pit_groups_keep_explicit_counts_without_inventing_final_total() -> None:
    model = _model()
    group = model["pits"]["requires_clarification"][0]

    assert group["reason"].startswith("Указана группа котлованов без количества")
    assert model["pits"]["is_final"] is False
    assert "окончательное количество" in model["pits"]["professional_answer"]


def test_model_ids_are_workspace_scoped_and_repeatable() -> None:
    first = _model()
    second = _model()
    assert first["model_fingerprint"] == second["model_fingerprint"]

    changed = _model()
    # The fixture helper intentionally creates one workspace; changing the model's
    # project ID through the public builder proves identifiers cannot cross scopes.
    rebuilt = build_project_engineering_model(
        workspace_id="workspace-beta",
        project_definition={"definition": {"fields": {}}},
        candidates={},
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "КНС-2",
                "candidate_labels": ["КНС-2", "КНС 2"],
                "member_structure_node_ids": [],
                "source_locator_ids": ["locator-one", "locator-two"],
            }
        ],
        pit_inventory={},
        defects=[],
        matrix={},
        normative_profile=None,
        source_context={},
    )
    assert changed["facilities"][0]["facility_id"] != rebuilt["facilities"][0]["facility_id"]


def test_semantic_work_resolution_materializes_without_manual_candidate_approval() -> None:
    source_context = dict([_source("work", "Технологическая карта.pdf", 17)])
    model = build_project_engineering_model(
        workspace_id="workspace-semantic",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "work-ambiguous",
                    "version": 3,
                    "value": "Послойное уплотнение обратной засыпки",
                    "label": "нестандартное описание операции",
                    "source_version_id": "source-work",
                    "source_locator_id": "work",
                    "source_role": "working_documentation",
                },
                {
                    "candidate_id": "not-work",
                    "version": 1,
                    "value": "Технические характеристики",
                    "label": "нестандартный раздел",
                    "source_version_id": "source-work",
                    "source_locator_id": "work",
                    "source_role": "working_documentation",
                },
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={},
        defects=[],
        matrix={},
        normative_profile=None,
        source_context=source_context,
        work_resolutions={
            "work-ambiguous": {
                "candidate_version": 3,
                "status": "MATCHED",
                "family_key": "backfill",
                "operation": "Послойное уплотнение обратной засыпки",
                "reason": "В описании явно указана строительная операция.",
            },
            "not-work": {
                "candidate_version": 1,
                "status": "NOT_A_WORK",
                "reason": "Заголовок раздела без строительной операции.",
            },
        },
    )

    assert model["works"][0]["work_name"] == "Послойное уплотнение обратной засыпки"
    assert model["works"][0]["family_key"] == "backfill"
    assert model["unclassified_works"] == []
    assert model["excluded_non_work_observations"][0]["candidate_id"] == "not-work"


def test_semantic_work_resolution_is_invalidated_by_candidate_version_change() -> None:
    source_context = dict([_source("work", "Технологическая карта.pdf", 17)])
    model = build_project_engineering_model(
        workspace_id="workspace-semantic",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "work-ambiguous",
                    "version": 4,
                    "value": "Неопределённая операция",
                    "label": "неопределенная операция",
                    "source_version_id": "source-work",
                    "source_locator_id": "work",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={},
        defects=[],
        matrix={},
        normative_profile=None,
        source_context=source_context,
        work_resolutions={
            "work-ambiguous": {
                "candidate_version": 3,
                "status": "MATCHED",
                "family_key": "backfill",
                "operation": "Обратная засыпка",
                "reason": "Старая версия.",
            }
        },
    )

    assert model["works"] == []
    assert model["unclassified_works"][0]["candidate_id"] == "work-ambiguous"


def test_application_projection_hides_bulk_unclassified_rows_outside_work_view() -> None:
    model = _model()
    model["unclassified_works"] = [
        {"candidate_id": f"candidate-{index}", "project_wording": f"Описание {index}"}
        for index in range(8)
    ]
    model["unresolved"]["works"] = list(model["unclassified_works"])

    general = _application_engineering_projection(
        model, section="general", page_offset=0, page_limit=3
    )
    works = _application_engineering_projection(model, section="works", page_offset=3, page_limit=3)

    assert general["unclassified_works"] == []
    assert general["unresolved"]["works"] == []
    assert general["unresolved"]["work_description_count"] == 8
    projected_work = general["facility_cards"][0]["works"][0]
    assert projected_work["quantities_by_document"]["РД"] == [
        {
            "value": "438",
            "unit": "т",
            "raw_value": "438",
            "raw_unit": "т",
            "source_locator_id": "q-rd",
        }
    ]
    assert projected_work["materials_by_document"]["РД"][0]["name"] == ("Шпунт Л5-УМ, сталь С255")
    assert "work-rd" in projected_work["source_locator_ids"]
    assert {row["document"] for row in general["facility_cards"][0]["documents"]} >= {
        "РД КР.pdf",
        "ВОР.xlsx.pdf",
    }
    assert [item["candidate_id"] for item in works["unclassified_works"]] == [
        "candidate-3",
        "candidate-4",
        "candidate-5",
    ]
