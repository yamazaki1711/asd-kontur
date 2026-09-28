# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

from decimal import Decimal

from asd_kontur.application_spine.postgres import _application_engineering_projection
from asd_kontur.tender.project_engineering import (
    _attach_pit_work_scopes,
    _comparison_row,
    _merge_sheet_pile_rows,
    _one_comparable_quantity,
    _scope_comparisons,
    build_project_engineering_model,
    classify_work_family,
    document_comparison_side,
    established_facility_designations,
    facility_designation,
    facility_designations,
    non_work_reason,
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
    assert "ещё не удалось однозначно классифицировать" in comparisons[0]["conclusion"]


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

    assert model["model_version"] == "project-engineering-model-v16"
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
                "subject_structure_node_id": "pipeline-node",
                "object_structure_node_id": "facility-node",
                "source_locator_id": "related-work",
            }
        ],
    )

    related = next(row for row in model["works"] if row["facility_id"] is not None)
    unrelated = next(row for row in model["works"] if row["facility_id"] is None)
    assert related["facility"] == "КНС 4"
    assert related["status"].startswith("Работа связана с сооружением")
    assert unrelated["facility"] == "Место выполнения не установлено"


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
    }

    for wording, family_key in expected.items():
        result = classify_work_family(wording)
        assert result is not None
        assert result[0] == family_key

    assert classify_work_family("Вывоз после приемки со склада готового оборудования") is None


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
                    "source_role": "estimate",
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


def test_obvious_estimate_resources_do_not_consume_qwen_reconciliation() -> None:
    assert non_work_reason("4-100-060") == "Сметный шифр без описания строительной операции"
    assert non_work_reason("Щиты настила, толщина 25 мм") == (
        "Описание материала, а не строительной операции"
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
    assert [item["candidate_id"] for item in works["unclassified_works"]] == [
        "candidate-3",
        "candidate-4",
        "candidate-5",
    ]
