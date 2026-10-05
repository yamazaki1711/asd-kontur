# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

from decimal import Decimal

import pytest

from asd_kontur.application_spine.postgres import _application_engineering_projection
from asd_kontur.tender.project_engineering import (
    _attach_pit_work_scopes,
    _comparison_has_reviewed_quantity_identity,
    _comparison_row,
    _comparisons,
    _component_total_analysis,
    _component_total_comparisons,
    _cross_work_quantity_pair_analysis,
    _display_quantity,
    _document_composition,
    _documents,
    _explicit_work_locations_compatible,
    _facility_material_schedule,
    _isolated_unassigned_comparison,
    _issues,
    _material_comparisons,
    _material_sheet_pile_profiles,
    _merge_sheet_pile_rows,
    _one_comparable_quantity,
    _pits,
    _professional_document_role,
    _professional_material_values,
    _professional_quantity_issue_comparisons,
    _project_scope_facility_label,
    _qualified_participant_context,
    _resolution_establishes_page_scope,
    _reviewed_cross_work_quantity_comparisons,
    _reviewed_scaled_quantity_unit,
    _reviewed_source_quantity_value,
    _scope_comparisons,
    _semantic_material_values,
    _semantic_work_consensus,
    _sheet_pile_profiles,
    _tender_context,
    _tender_context_comparisons,
    _unique_values,
    _validated_scope_quantity_comparisons,
    _work_schedule,
    build_project_engineering_model,
    classify_work_family,
    commercial_scope_facility_designation,
    construction_scope_exclusion_reason,
    document_comparison_side,
    established_facility_designations,
    facility_designation,
    facility_designations,
    mentioned_established_facilities,
    non_work_reason,
    professional_source_role,
    professional_work_name,
    work_reconciliation_priority,
)
from asd_kontur.tender.qwen_work_reconciliation import PROJECT_WORK_RECONCILIATION_PROFILE


def test_page_role_decision_overrides_fragment_local_document_role() -> None:
    assert (
        professional_source_role(
            "project_documentation",
            {
                "safe_display_name": "C63_scope.pdf",
                "selected_roles": ["unknown", "bill_of_quantities"],
            },
        )
        == "ВОР"
    )
    assert (
        professional_source_role(
            "project_documentation",
            {
                "safe_display_name": "D41_design.pdf",
                "selected_roles": ["working_documentation"],
            },
        )
        == "РД"
    )


def test_tender_context_is_generic_and_keeps_source_bound_commercial_facts() -> None:
    source_context = dict([_source("contract", "Проект контракта.pdf", 4)])

    context = _tender_context(
        [
            {"label": "customer", "value": "АО Заказчик", "source_locator_id": "contract"},
            {"label": "contract_price", "value": "125000000 руб.", "source_locator_id": "contract"},
            {"label": "contract_duration", "value": "18 месяцев", "source_locator_id": "contract"},
            {"label": "warranty_period", "value": "60 месяцев", "source_locator_id": "contract"},
            {
                "label": "unrelated_project_fact",
                "value": "Не входит",
                "source_locator_id": "contract",
            },
        ],
        source_context,
    )

    assert context["participants"][0]["value"] == "АО Заказчик"
    assert context["commercial_conditions"][0]["value"] == "125 000 000,00 руб."
    assert context["time_requirements"][0]["value"] == "18 месяцев"
    assert context["contract_conditions"][0]["value"] == "60 месяцев"
    assert all("Не входит" not in str(values) for values in context.values())


def test_tender_context_collapses_equivalent_price_basis_wording_without_losing_sources() -> None:
    source_context = dict(
        [
            _source("design", "Project section.pdf", 2),
            _source("estimate", "Cost schedule.pdf", 4),
            _source("later", "Price letter.pdf", 1),
        ]
    )
    context = _tender_context(
        [
            {
                "label": "price_basis",
                "value": "Prices for Q3. 2026",
                "source_locator_id": "design",
            },
            {
                "label": "price_basis",
                "value": "Prices for Q3 2026.",
                "source_locator_id": "estimate",
            },
            {
                "label": "price_basis",
                "value": "Prices for Q4 2026",
                "source_locator_id": "later",
            },
            {
                "label": "price_basis",
                "value": "Index 1.5",
                "source_locator_id": "design",
            },
            {
                "label": "price_basis",
                "value": "Index 15",
                "source_locator_id": "estimate",
            },
        ],
        source_context,
    )

    assert len(context["commercial_conditions"]) == 4
    q3 = next(
        row for row in context["commercial_conditions"] if "Q3" in row["value"]
    )
    assert q3["source_locator_ids"] == ["design", "estimate"]
    assert len(q3["sources"]) == 2


def test_tender_context_rejects_false_price_fields_and_deduplicates_money() -> None:
    source_context = dict(
        [
            _source("nmck-a", "Обоснование НМЦК.pdf", 2),
            _source("nmck-b", "Обоснование НМЦК.pdf", 3),
            _source("estimate", "Локальная смета.pdf", 1),
        ]
    )
    context = _tender_context(
        [
            {
                "label": "initial_contract_price",
                "value": "57 812 903,44",
                "source_locator_id": "nmck-a",
            },
            {
                "label": "initial_contract_price",
                "value": "57812903.44",
                "source_locator_id": "nmck-b",
            },
            {
                "label": "nmck",
                "value": "проектно-сметный метод",
                "source_locator_id": "nmck-a",
            },
            {
                "label": "initial_contract_price",
                "value": "887,58",
                "source_locator_id": "estimate",
            },
        ],
        source_context,
    )

    assert [(row["field"], row["value"]) for row in context["commercial_conditions"]] == [
        ("initial_contract_price", "57 812 903,44 руб.")
    ]


def test_tender_context_rejects_signatories_and_non_schedule_dates() -> None:
    source_context = dict(
        [
            _source("design", "Раздел ПД.pdf", 3),
            _source("estimate", "ЛСР 04-01-02.pdf", 1),
            _source("contract", "Проект контракта.pdf", 6),
        ]
    )
    context = _tender_context(
        [
            {"label": "customer", "value": "Сидоров", "source_locator_id": "design"},
            {
                "label": "general_designer",
                "value": "Петров А.Б.",
                "source_locator_id": "design",
            },
            {
                "label": "designer",
                "value": "ООО «Геопроект»",
                "source_locator_id": "design",
            },
            {
                "label": "developer",
                "value": "АО Мостпроект",
                "source_locator_id": "design",
            },
            {
                "label": "developer",
                "value": "АО «Мостпроект»",
                "source_locator_id": "contract",
            },
            {
                "label": "customer",
                "value": "Муниципальное учреждение «Дорожная дирекция»",
                "source_locator_id": "contract",
            },
            {"label": "start_date", "value": "01.01.2001", "source_locator_id": "estimate"},
            {"label": "completion_date", "value": "7.14", "source_locator_id": "design"},
            {
                "label": "start_date",
                "value": "с даты подписания договора",
                "source_locator_id": "contract",
            },
            {
                "label": "completion_date",
                "value": "30 ноября 2028 года",
                "source_locator_id": "contract",
            },
            {"label": "vat", "value": "22 процентов", "source_locator_id": "contract"},
            {"label": "vat", "value": "22%", "source_locator_id": "design"},
            {"label": "vat", "value": "с НДС", "source_locator_id": "estimate"},
        ],
        source_context,
    )

    assert [(row["field"], row["value"]) for row in context["participants"]] == [
        ("customer", "Муниципальное учреждение «Дорожная дирекция»"),
        ("developer", "АО «Мостпроект»"),
        ("designer", "ООО «Геопроект»"),
    ]
    assert len(context["participants"][1]["source_locator_ids"]) == 2
    assert [(row["field"], row["value"]) for row in context["time_requirements"]] == [
        ("start_date", "с даты подписания договора"),
        ("completion_date", "30 ноября 2028 года"),
    ]
    assert [(row["label"], row["value"]) for row in context["commercial_conditions"]] == [
        ("Ставка НДС", "22%")
    ]


def test_participant_context_localizes_uncorroborated_role_conflicts() -> None:
    established, ambiguities = _qualified_participant_context(
        [
            {
                "field": "customer",
                "label": "Заказчик",
                "value": "АО «Северная дирекция»",
                "source_locator_ids": ["contract", "procurement", "design-title"],
            },
            {
                "field": "customer",
                "label": "Заказчик",
                "value": "ГУП «Городские сети»",
                "source_locator_ids": ["utility-note"],
            },
            {
                "field": "designer",
                "label": "Проектировщик",
                "value": "ООО «Мостинжпроект»",
                "source_locator_ids": ["design-title"],
            },
        ]
    )

    assert [(row["field"], row["value"]) for row in established] == [
        ("customer", "АО «Северная дирекция»"),
        ("designer", "ООО «Мостинжпроект»"),
    ]
    assert [(row["field"], row["value"]) for row in ambiguities] == [
        ("customer", "ГУП «Городские сети»")
    ]
    assert "требует уточнения" in ambiguities[0]["reason"]


def test_contract_estimate_filename_is_not_reduced_to_ordinary_estimate() -> None:
    assert _professional_document_role(None, "Проект сметы контракта.docx") == ("Смета контракта")


def test_tender_context_compares_typed_vat_and_active_work_duration() -> None:
    source_context = dict(
        [
            _source("estimate", "Локальная смета.xlsx", 1),
            _source("contract", "Проект контракта.pdf", 4),
            _source("pos", "Раздел ПД. ПОС.pdf", 12),
            _source("procurement", "Обоснование НМЦК.pdf", 2),
        ]
    )
    comparisons = _tender_context_comparisons(
        {
            "commercial_conditions": [
                {
                    "field": "vat",
                    "value": "20%",
                    "source_locator_ids": ["estimate"],
                },
                {
                    "field": "vat",
                    "value": "22%",
                    "source_locator_ids": ["contract"],
                },
            ],
            "time_requirements": [
                {
                    "field": "construction_duration",
                    "value": "3,5 месяца",
                    "source_locator_ids": ["pos"],
                },
                {
                    "field": "work_duration",
                    "value": "4 месяца",
                    "source_locator_ids": ["procurement"],
                },
                {
                    "field": "contract_duration",
                    "value": "10 месяцев",
                    "source_locator_ids": ["contract"],
                },
            ],
        },
        source_context,
    )

    assert [(row["comparison_kind"], row["classification"]) for row in comparisons] == [
        ("commercial_condition", "COMMERCIAL_CONDITION_MISMATCH"),
        ("duration", "DURATION_MISMATCH"),
    ]
    assert comparisons[0]["left"]["document_role"] == "Смета"
    assert comparisons[0]["right"]["document_role"] == "Договор"
    assert comparisons[1]["left"]["value"] == "3.5"
    assert comparisons[1]["right"]["value"] == "4"


def test_facility_material_schedule_consolidates_repeated_mentions_by_scope() -> None:
    schedule = _facility_material_schedule(
        [
            {
                "work_name": "Погружение шпунта",
                "materials_by_document": {
                    "ВОР": [
                        {
                            "name": "Шпунт Л5",
                            "quantity": "9.5",
                            "unit": "т",
                            "source_locator_id": "vor-a",
                        },
                        {
                            "name": "Шпунт Л5",
                            "quantity": "9.5",
                            "unit": "т",
                            "source_locator_id": "vor-b",
                        },
                    ],
                    "РД": [
                        {
                            "name": "Шпунт Л5",
                            "quantity": "9.5",
                            "unit": "т",
                            "source_locator_id": "design",
                        }
                    ],
                },
            },
            {
                "work_name": "Устройство пояса",
                "materials_by_document": {
                    "ВОР": [
                        {
                            "name": "Шпунт Л5",
                            "quantity": "9.5",
                            "unit": "т",
                            "source_locator_id": "belt",
                        }
                    ]
                },
            },
        ]
    )

    assert len(schedule) == 3
    driving_vor = next(
        row
        for row in schedule
        if row["work_name"] == "Погружение шпунта" and row["document_role"] == "ВОР"
    )
    assert driving_vor["source_locator_ids"] == ["vor-a", "vor-b"]
    assert "source_locator_id" not in driving_vor


def test_explicit_vor_heading_resolution_establishes_page_scope() -> None:
    assert _resolution_establishes_page_scope(
        {
            "confidence": "0.90",
            "reason": (
                "Контекст относится к ведомости объемов работ ЛОС 8.1, "
                "что обеспечивает явную привязку к сооружению."
            ),
        }
    )
    assert not _resolution_establishes_page_scope(
        {
            "confidence": "0.95",
            "reason": "Сооружение вероятно упоминается рядом с этой работой.",
        }
    )


def test_semantic_work_consensus_reuses_meaning_but_never_facility() -> None:
    works = [
        {
            "candidate_id": "reviewed-a",
            "version": 1,
            "source_version_id": "source-a",
            "value": "Вибропогружение шпунта",
        },
        {
            "candidate_id": "reviewed-b",
            "version": 1,
            "source_version_id": "source-b",
            "value": "Вибропогружение шпунта",
        },
        {
            "candidate_id": "unreviewed-c",
            "version": 1,
            "source_version_id": "source-c",
            "value": "Вибропогружение шпунта",
        },
    ]
    resolutions = {
        "reviewed-a": {
            "candidate_version": 1,
            "status": "MATCHED",
            "family_key": "sheet_piling",
            "operation": "Погружение шпунта",
            "facility": "Участок 4",
        },
        "reviewed-b": {
            "candidate_version": 1,
            "status": "MATCHED",
            "family_key": "sheet_piling",
            "operation": "Погружение шпунта",
            "facility": "Участок 9",
        },
    }

    consensus = _semantic_work_consensus(works, resolutions)

    reused = consensus["вибропогружение шпунта"]
    assert reused["family_key"] == "sheet_piling"
    assert reused["operation"] == "Погружение шпунта"
    assert "facility" not in reused


def test_semantic_work_consensus_rejects_conflict_and_one_source_repetition() -> None:
    works = [
        {
            "candidate_id": "a",
            "version": 1,
            "source_version_id": "same-source",
            "value": "Монтаж элемента",
        },
        {
            "candidate_id": "b",
            "version": 1,
            "source_version_id": "same-source",
            "value": "Монтаж элемента",
        },
    ]
    one_source = {
        candidate: {
            "candidate_version": 1,
            "status": "MATCHED",
            "family_key": "structural_steel",
            "operation": "Монтаж металлоконструкций",
        }
        for candidate in ("a", "b")
    }
    assert _semantic_work_consensus(works, one_source) == {}

    works[1]["source_version_id"] = "other-source"
    conflict = {
        **one_source,
        "b": {**one_source["b"], "status": "AMBIGUOUS"},
    }
    assert _semantic_work_consensus(works, conflict) == {}


def test_semantic_work_consensus_reuses_exact_non_work_decision() -> None:
    works = [
        {
            "candidate_id": "reviewed",
            "version": 2,
            "source_version_id": "source-a",
            "value": "Промывка коалесцентного модуля",
        },
        {
            "candidate_id": "unreviewed",
            "version": 1,
            "source_version_id": "source-b",
            "value": "Промывка коалесцентного модуля",
        },
    ]

    consensus = _semantic_work_consensus(
        works,
        {
            "reviewed": {
                "candidate_version": 2,
                "status": "NOT_A_WORK",
                "reason": "Операция относится к эксплуатации оборудования.",
            }
        },
    )

    assert consensus["промывка коалесцентного модуля"] == {
        "status": "NOT_A_WORK",
        "reason": (
            "Точное описание ранее определено как не относящееся к работам текущего строительства."
        ),
    }


def test_facility_designations_preserve_multiple_explicit_project_scopes() -> None:
    assert facility_designations("КНС-4, ЛОС 8.1 и 2-КНС") == (
        "КНС 2",
        "КНС 4",
        "ЛОС 8.1",
    )
    assert facility_designation("Работы КНС-4") == "КНС 4"
    assert facility_designation("КНС-4 и ЛОС 8.1") is None


def test_commercial_scope_heading_distinguishes_station_from_served_los() -> None:
    assert commercial_scope_facility_designation("Строительство КНС для ЛОС4") == "КНС 4"
    assert commercial_scope_facility_designation("Строительство КНС8.1") == "КНС 8.1"


def test_vor_and_estimate_sections_assign_identical_work_to_distinct_facilities() -> None:
    source_context = dict(
        [
            _source("facility-4", "КР2. КНС4.pdf", 1),
            _source("facility-4b", "КР2. КНС4.pdf", 2),
            _source("facility-8-1", "КР1. КНС8.1.pdf", 1),
            _source("facility-8-1b", "КР1. КНС8.1.pdf", 2),
            _source("vor-4", "Сводный ВОР.pdf", 32),
            _source("estimate-4", "Локальные сметы.pdf", 64),
            _source("vor-8-1", "Сводный ВОР.pdf", 36),
            _source("estimate-8-1", "Локальные сметы.pdf", 77),
        ]
    )
    source_context["vor-4"].update(
        page_is_bill_of_quantities=True,
        page_commercial_scope_code="02-01-16",
        page_commercial_scope_header="ведомость объемов работ № вор 02-01-16",
    )
    source_context["estimate-4"].update(
        page_commercial_scope_code="02-01-16",
        page_commercial_scope_header=(
            "локальный сметный расчет № лср 02-01-16 строительство кнс для лос4"
        ),
    )
    source_context["vor-8-1"].update(
        page_is_bill_of_quantities=True,
        page_commercial_scope_code="02-01-17",
        page_commercial_scope_header="ведомость объемов работ № вор 02-01-17",
    )
    source_context["estimate-8-1"].update(
        page_commercial_scope_code="02-01-17",
        page_commercial_scope_header=(
            "локальный сметный расчет № лср 02-01-17 строительство кнс8.1"
        ),
    )
    identity_components = [
        {
            "identity_kind": "facility",
            "canonical_label": "КНС 4",
            "candidate_labels": ["КНС 4"],
            "member_structure_node_ids": ["facility-4-node"],
            "source_locator_ids": ["facility-4", "facility-4b"],
        },
        {
            "identity_kind": "facility",
            "canonical_label": "КНС 8.1",
            "candidate_labels": ["КНС 8.1"],
            "member_structure_node_ids": ["facility-8-1-node"],
            "source_locator_ids": ["facility-8-1", "facility-8-1b"],
        },
    ]
    work_types = []
    for locator in ("vor-4", "estimate-4", "vor-8-1", "estimate-8-1"):
        work_types.append(
            {
                "candidate_id": locator,
                "version": 1,
                "value": "Погружение шпунта",
                "label": "погружение шпунта",
                "source_version_id": source_context[locator]["source_version_id"],
                "source_locator_id": locator,
                "source_role": "local_estimate",
            }
        )
    model = build_project_engineering_model(
        workspace_id="workspace-commercial-sections",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": work_types,
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=identity_components,
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
    )

    sheet_pile_works = [row for row in model["works"] if row["family_key"] == "sheet_piling"]
    assert {row["facility"] for row in sheet_pile_works} == {"КНС 4", "КНС 8.1"}
    assert all("02-01-1" in row["status"] for row in sheet_pile_works)


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


def test_vor_role_continues_after_heading_within_same_commercial_scope() -> None:
    source_context = dict([_source("vor-row", "Смешанный том.pdf", 3)])
    source_context["vor-row"].update(
        page_is_bill_of_quantities=False,
        page_commercial_scope_code="02-01-01",
        page_commercial_scope_header="ведомость объемов работ вор 02-01-01 подпорная стена",
    )
    model = build_project_engineering_model(
        workspace_id="workspace-commercial-role",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "wall",
                    "version": 1,
                    "value": "Устройство подпорной стены из бетона",
                    "source_version_id": "source-vor",
                    "source_locator_id": "vor-row",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [
                {
                    "candidate_id": "wall-quantity",
                    "work_candidate_id": "wall",
                    "value": "211.3",
                    "unit": "м3",
                    "source_locator_id": "vor-row",
                    "review_status": "ACCEPTED",
                }
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
        work_resolutions={
            "wall": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "reinforced_concrete",
                "operation": "Устройство подпорной стены",
                "quantity_reviews": [
                    {"quantity_candidate_id": "wall-quantity", "status": "WORK_QUANTITY"}
                ],
            }
        },
    )

    assert model["works"][0]["quantities_by_document"] == {
        "ВОР": [
            {
                "value": "211.3",
                "unit": "м3",
                "raw_value": "211.3",
                "raw_unit": "м3",
                "source_locator_id": "vor-row",
            }
        ]
    }
    assert model["document_composition"]["available_roles"] == ["ВОР"]


def test_local_estimate_role_overrides_coarse_container_role() -> None:
    source_context = dict([_source("estimate-row", "Смешанный том.pdf", 31)])
    source_context["estimate-row"].update(
        page_commercial_scope_code="02-01-01",
        page_commercial_scope_header=(
            "локальный сметный расчет лср 02-01-01 конструктивные решения"
        ),
    )
    model = build_project_engineering_model(
        workspace_id="workspace-estimate-role",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "wall",
                    "version": 1,
                    "value": "Устройство подпорной стены из бетона",
                    "source_version_id": "source-estimate",
                    "source_locator_id": "estimate-row",
                    "source_role": "project_documentation",
                }
            ],
            "quantities": [
                {
                    "candidate_id": "wall-quantity",
                    "work_candidate_id": "wall",
                    "value": "211.3",
                    "unit": "м3",
                    "source_locator_id": "estimate-row",
                }
            ],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
        work_resolutions={
            "wall": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v5",
                "status": "MATCHED",
                "family_key": "reinforced_concrete",
                "operation": "Устройство подпорной стены",
                "quantity_reviews": [
                    {"quantity_candidate_id": "wall-quantity", "status": "WORK_QUANTITY"}
                ],
            }
        },
    )

    assert list(model["works"][0]["quantities_by_document"]) == ["Смета"]
    assert model["works"][0]["quantities_by_document"]["Смета"][0]["value"] == "211.3"


def test_document_register_uses_complete_inventory_before_candidates_exist() -> None:
    documents = _documents(
        {
            "design-locator": {
                "safe_display_name": "Project.pdf",
                "document_version": 1,
                "source_version_id": "design-version",
            }
        },
        document_inventory=[
            {
                "safe_display_name": "Project.pdf",
                "document_version": 1,
                "source_version_id": "design-version",
                "selected_roles": ["project_documentation"],
            },
            {
                "safe_display_name": "Commercial scope.pdf",
                "document_version": 1,
                "source_version_id": "vor-version",
                "selected_roles": ["bill_of_quantities"],
            },
            {
                "safe_display_name": "Customer package.pdf",
                "document_version": 2,
                "source_version_id": "customer-version",
                "selected_roles": ["customer_regulation"],
            },
        ],
    )

    assert {(row["name"], row["document_role"]) for row in documents} == {
        ("Project.pdf", "ПД"),
        ("Commercial scope.pdf", "ВОР"),
        ("Customer package.pdf", "Требования Заказчика"),
    }


def test_document_roles_keep_procurement_correspondence_and_pos_out_of_generic_bucket() -> None:
    assert (
        _professional_document_role(
            "contract",
            "ТРЕБОВАНИЯ К СОДЕРЖАНИЮ, СОСТАВУ ЗАЯВКИ И ИНСТРУКЦИЯ.docx",
        )
        == "Закупочная документация"
    )
    assert (
        _professional_document_role(
            "correspondence_administrative",
            "30.07.26 - о согласовании изменений.pdf",
        )
        == "Переписка/согласования"
    )
    assert _professional_document_role(None, "22.467 - ПОС.pdf") == "ПД"
    assert (
        _professional_document_role("project_documentation", "Ведомость объемов работ.pdf") == "ВОР"
    )
    assert _professional_document_role(None, "Ведомость объёмов работ.pdf") == "ВОР"
    assert _professional_document_role("project_documentation", "22.467-СМ.Изм7.pdf") == "Смета"
    assert _professional_document_role("project_documentation", "ЛСР 02-01-01.pdf") == "Смета"
    assert _professional_document_role(None, "ОСР-04 Наружные сети.pdf") == "Смета"
    assert _professional_document_role(None, "ССР-01.xlsx") == "Смета"
    assert _professional_document_role(None, "Криптоконтейнер_41.xml") == "Электронный контейнер"


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


def test_contract_estimate_is_a_commercial_quantity_source() -> None:
    comparisons = _comparisons(
        [
            {
                "work_scope_id": "changed-scope",
                "facility": "Сооружение Z-17",
                "work_name": "Устройство основания",
                "quantities_by_document": {
                    "РД": [
                        {
                            "value": "82.5",
                            "unit": "м3",
                            "semantic_scope": "Объём основания сооружения Z-17",
                            "scope_compatibility": "SAME_SCOPE",
                        }
                    ],
                    "Смета контракта": [
                        {
                            "value": "76.0",
                            "unit": "м3",
                            "semantic_scope": "Объём основания сооружения Z-17",
                            "scope_compatibility": "SAME_SCOPE",
                        }
                    ],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "QUANTITY_DIFFERENCE"
    assert comparisons[0]["left"] == {"document_role": "РД", "value": "82.5", "unit": "м3"}
    assert comparisons[0]["right"] == {
        "document_role": "Смета контракта",
        "value": "76",
        "unit": "м3",
    }
    assert comparisons[0]["difference"] == "6.5"


def test_reviewed_quantity_identity_allows_unlocated_multirow_scope_comparison() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "foundation-preparation-z17",
                "facility_id": None,
                "facility": "Location unresolved",
                "family_key": "pit_preparation",
                "work_family": "Foundation preparation",
                "work_name": "Prepare crushed-stone base",
                "semantic_resolution_by_document": {
                    "ПД": ["MATCHED"],
                    "ВОР": ["MATCHED"],
                    "Смета": ["MATCHED"],
                },
                "sources_by_document": {
                    "ПД": [{"source_locator_id": "design-a"}, {"source_locator_id": "design-b"}],
                    "ВОР": [{"source_locator_id": "vor"}],
                    "Смета": [{"source_locator_id": "estimate"}],
                },
                "project_wording_by_document": {
                    "ПД": ["Base under structure", "Base around piles"],
                    "ВОР": ["Crushed-stone base"],
                    "Смета": ["Crushed-stone base"],
                },
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "design-area",
                            "value": "240",
                            "unit": "м2",
                            "semantic_scope": "Base area",
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        },
                        {
                            "quantity_candidate_id": "design-volume",
                            "value": "68.4",
                            "unit": "м3",
                            "semantic_scope": "Crushed-stone base volume",
                            "relation_kind": "DUPLICATE_OF",
                            "related_quantity_candidate_ids": ["estimate-volume"],
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "estimate-volume",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same crushed-stone base volume.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        },
                    ],
                    "Смета": [
                        {
                            "quantity_candidate_id": "estimate-volume",
                            "value": "61.2",
                            "unit": "м3",
                            "semantic_scope": "Crushed-stone base volume",
                            "relation_kind": "DUPLICATE_OF",
                            "related_quantity_candidate_ids": ["design-volume"],
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "design-volume",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same crushed-stone base volume.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "QUANTITY_DIFFERENCE"
    assert comparisons[0]["left"] == {"document_role": "ПД", "value": "68.4", "unit": "м3"}
    assert comparisons[0]["right"] == {
        "document_role": "Смета",
        "value": "61.2",
        "unit": "м3",
    }
    assert comparisons[0]["difference"] == "7.2"


@pytest.mark.parametrize(
    (
        "work_name",
        "design_value",
        "design_unit",
        "commercial_value",
        "commercial_unit",
        "quantity_type",
        "expected",
    ),
    [
        ("Install pipe", "125", "м", "0.125", "1000 м", "COMPONENT", "0"),
        ("Install steel", "8.2", "т", "7.7", "т", "COMPONENT", "0.5"),
        ("Excavate ground", "140", "м3", "110", "м3", "COMPONENT", "30"),
        ("Install earth anchors", "36", "шт", "34", "шт", "STANDALONE", "2"),
    ],
)
def test_exact_reviewed_quantity_pair_compares_across_broad_work_rows(
    work_name: str,
    design_value: str,
    design_unit: str,
    commercial_value: str,
    commercial_unit: str,
    quantity_type: str,
    expected: str,
) -> None:
    def work(
        *,
        work_id: str,
        candidate_id: str,
        peer_candidate_id: str,
        quantity_id: str,
        peer_quantity_id: str,
        role: str,
        value: str,
        unit: str,
    ) -> dict[str, object]:
        return {
            "work_scope_id": work_id,
            "candidate_ids": [candidate_id, f"unrelated-{candidate_id}"],
            "facility_id": "facility-z",
            "facility": "Facility Z",
            "work_name": work_name,
            "work_scope_assertions": [
                {
                    "source_candidate_id": candidate_id,
                    "related_candidate_id": peer_candidate_id,
                    "scope_compatibility": "SAME_SCOPE",
                    "normalized_operation": work_name,
                    "reason": "The exact operations match.",
                }
            ],
            "quantities_by_document": {
                role: [
                    {
                        "quantity_candidate_id": quantity_id,
                        "value": value,
                        "unit": unit,
                        "quantity_type": quantity_type,
                        "semantic_scope": work_name,
                        "relationship_reviewed": True,
                        "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        "scope_assertions": [
                            {
                                "related_quantity_candidate_id": peer_quantity_id,
                                "scope_compatibility": "SAME_SCOPE",
                            }
                        ],
                        "source_locator_id": f"source-{quantity_id}",
                    }
                ]
            },
        }

    design = work(
        work_id="broad-design-row",
        candidate_id="design-work",
        peer_candidate_id="commercial-work",
        quantity_id="design-quantity",
        peer_quantity_id="commercial-quantity",
        role="ПД",
        value=design_value,
        unit=design_unit,
    )
    commercial = work(
        work_id="broad-commercial-row",
        candidate_id="commercial-work",
        peer_candidate_id="design-work",
        quantity_id="commercial-quantity",
        peer_quantity_id="design-quantity",
        role="Смета",
        value=commercial_value,
        unit=commercial_unit,
    )
    comparisons = _reviewed_cross_work_quantity_comparisons([design, commercial])

    assert len(comparisons) == 1
    assert comparisons[0]["difference"] == expected
    assert comparisons[0]["classification"] == (
        "MATCH" if expected == "0" else "QUANTITY_DIFFERENCE"
    )
    assert comparisons[0]["source_locator_ids"] == [
        "source-commercial-quantity",
        "source-design-quantity",
    ]

    # Pair-specific scope review remains authoritative when a later bounded
    # component/total pass has not marked that separate relationship complete.
    design["quantities_by_document"]["ПД"][0].pop("relationship_reviewed")  # type: ignore[index]
    commercial["quantities_by_document"]["Смета"][0].pop("relationship_reviewed")  # type: ignore[index]
    assert len(_reviewed_cross_work_quantity_comparisons([design, commercial])) == 1

    # A one-sided semantic decision, a distinct facility, or a component/total
    # boundary cannot be promoted into a commercial discrepancy.
    commercial["work_scope_assertions"] = []
    assert _reviewed_cross_work_quantity_comparisons([design, commercial]) == []
    commercial["work_scope_assertions"] = [
        {
            "source_candidate_id": "commercial-work",
            "related_candidate_id": "design-work",
            "scope_compatibility": "SAME_SCOPE",
            "normalized_operation": work_name,
            "reason": "The exact operations match.",
        }
    ]
    commercial["facility_id"] = "different-facility"
    assert _reviewed_cross_work_quantity_comparisons([design, commercial]) == []
    commercial["facility_id"] = "facility-z"
    commercial["quantities_by_document"]["Смета"][0]["quantity_type"] = "TOTAL"  # type: ignore[index]
    assert _reviewed_cross_work_quantity_comparisons([design, commercial]) == []


def test_one_commercial_quantity_with_two_reviewed_design_scopes_requires_allocation() -> None:
    def work(
        *,
        work_id: str,
        candidate_id: str,
        peer_work_ids: list[str],
        quantity_id: str,
        peer_quantity_ids: list[str],
        role: str,
        value: str,
    ) -> dict[str, object]:
        return {
            "work_scope_id": work_id,
            "candidate_ids": [candidate_id],
            "facility_id": "bridge-pier-z",
            "facility": "Bridge pier Z",
            "work_name": "Install facing panels",
            "work_scope_assertions": [
                {
                    "source_candidate_id": candidate_id,
                    "related_candidate_id": peer_id,
                    "scope_compatibility": "SAME_SCOPE",
                    "normalized_operation": "Install facing panels",
                    "reason": "The exact work scopes correspond.",
                }
                for peer_id in peer_work_ids
            ],
            "quantities_by_document": {
                role: [
                    {
                        "quantity_candidate_id": quantity_id,
                        "value": value,
                        "unit": "м2",
                        "quantity_type": "STANDALONE",
                        "semantic_scope": "Facing panels at bridge pier Z",
                        "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        "scope_assertions": [
                            {
                                "related_quantity_candidate_id": peer_id,
                                "scope_compatibility": "SAME_SCOPE",
                            }
                            for peer_id in peer_quantity_ids
                        ],
                        "source_locator_id": f"source-{quantity_id}",
                    }
                ]
            },
        }

    design_a = work(
        work_id="design-a",
        candidate_id="design-work-a",
        peer_work_ids=["commercial-work"],
        quantity_id="design-quantity-a",
        peer_quantity_ids=["commercial-quantity"],
        role="РД",
        value="45",
    )
    design_b = work(
        work_id="design-b",
        candidate_id="design-work-b",
        peer_work_ids=["commercial-work"],
        quantity_id="design-quantity-b",
        peer_quantity_ids=["commercial-quantity"],
        role="РД",
        value="47",
    )
    commercial = work(
        work_id="commercial",
        candidate_id="commercial-work",
        peer_work_ids=["design-work-a", "design-work-b"],
        quantity_id="commercial-quantity",
        peer_quantity_ids=["design-quantity-a", "design-quantity-b"],
        role="Смета",
        value="45",
    )

    comparisons, unresolved = _cross_work_quantity_pair_analysis([design_a, design_b, commercial])

    assert comparisons == []
    assert len(unresolved) == 1
    assert unresolved[0]["unresolved_kind"] == "cross_document_quantity_allocation"
    assert [row["value"] for row in unresolved[0]["design_quantities"]] == ["45", "47"]
    assert [row["value"] for row in unresolved[0]["commercial_quantities"]] == ["45"]
    assert len(unresolved[0]["source_locator_ids"]) == 3
    assert "числовое сравнение пока не выполняется" in unresolved[0]["reason"]

    commercial["quantities_by_document"]["Смета"][0]["unit"] = "т"  # type: ignore[index]
    assert _cross_work_quantity_pair_analysis([design_a, design_b, commercial]) == ([], [])


def test_reviewed_same_scope_allows_one_to_one_commercial_comparison_without_relation_ids() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "waterproofing-scope",
                "facility_id": None,
                "facility": "Location unresolved",
                "work_name": "Apply waterproofing",
                "project_wording_by_document": {
                    "ВОР": ["Apply waterproofing"],
                    "Смета": ["Apply waterproofing"],
                },
                "semantic_resolution_by_document": {"ВОР": ["MATCHED"], "Смета": ["MATCHED"]},
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "quantity_candidate_id": "vor-area",
                            "value": "833.9",
                            "unit": "м2",
                            "semantic_scope": "Waterproofed surface area",
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "estimate-area",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same waterproofed surface area.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                    "Смета": [
                        {
                            "quantity_candidate_id": "estimate-area",
                            "value": "8.339",
                            "unit": "100 м2",
                            "semantic_scope": "Waterproofed surface area",
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "vor-area",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same waterproofed surface area.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATCH"
    assert comparisons[0]["left"]["value"] == "833.9"
    assert comparisons[0]["right"]["value"] == "833.9"


def test_current_profile_top_level_same_scope_does_not_authorize_exact_pair() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "unasserted-current-profile",
                "facility_id": None,
                "facility": "Location unresolved",
                "work_name": "Install pipeline",
                "project_wording_by_document": {
                    "ПД": ["Install pipeline"],
                    "ВОР": ["Install pipeline"],
                },
                "semantic_resolution_by_document": {"ПД": ["MATCHED"], "ВОР": ["MATCHED"]},
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "design-length",
                            "value": "120",
                            "unit": "м",
                            "semantic_scope": "Pipeline length",
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                    "ВОР": [
                        {
                            "quantity_candidate_id": "vor-length",
                            "value": "120",
                            "unit": "м",
                            "semantic_scope": "Pipeline length",
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert comparisons == []


def test_pair_specific_same_scope_survives_later_unrelated_scope_decision() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "manual-excavation",
                "facility_id": None,
                "facility": "Location unresolved",
                "work_name": "Manual excavation",
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "quantity_candidate_id": "vor-manual",
                            "value": "42.5",
                            "unit": "м3",
                            "semantic_scope": "Manual excavation volume",
                            "scope_compatibility": "DIFFERENT_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "estimate-manual",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same manual excavation scope.",
                                },
                                {
                                    "related_quantity_candidate_id": "mechanized",
                                    "scope_compatibility": "DIFFERENT_SCOPE",
                                    "reason": "Different excavation method.",
                                },
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                    "Смета": [
                        {
                            "quantity_candidate_id": "estimate-manual",
                            "value": "42.5",
                            "unit": "м3",
                            "semantic_scope": "Manual excavation volume",
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "vor-manual",
                                    "scope_compatibility": "SAME_SCOPE",
                                    "reason": "Same manual excavation scope.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATCH"


def test_pair_specific_different_scope_rejects_equal_value_false_positive() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "mixed-excavation",
                "facility_id": "facility-a",
                "facility": "Facility A",
                "work_name": "Excavation",
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "design-manual",
                            "value": "51",
                            "unit": "м3",
                            "semantic_scope": "Excavation volume",
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "estimate-mechanized",
                                    "scope_compatibility": "DIFFERENT_SCOPE",
                                    "reason": "Different excavation method and boundary.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                    "Смета": [
                        {
                            "quantity_candidate_id": "estimate-mechanized",
                            "value": "51",
                            "unit": "м3",
                            "semantic_scope": "Excavation volume",
                            "scope_compatibility": "SAME_SCOPE",
                            "scope_assertions": [
                                {
                                    "related_quantity_candidate_id": "design-manual",
                                    "scope_compatibility": "DIFFERENT_SCOPE",
                                    "reason": "Different excavation method and boundary.",
                                }
                            ],
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert comparisons == []


def test_explicit_project_scope_allows_same_scope_vor_estimate_comparison() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "project-drainage-scope",
                "facility_id": None,
                "location_scope_kind": "project",
                "facility": "Project as a whole (North section; South section)",
                "work_name": "Install drainage collector",
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "quantity_candidate_id": "vor-length",
                            "value": "184",
                            "unit": "m",
                            "semantic_scope": "Drainage collector length",
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": "qwen-project-work-reconciliation-v20",
                        }
                    ],
                    "Смета": [
                        {
                            "quantity_candidate_id": "estimate-length",
                            "value": "184",
                            "unit": "м",
                            "semantic_scope": "Drainage collector length",
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": "qwen-project-work-reconciliation-v24",
                        }
                    ],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATCH"
    assert "объекта в целом" in comparisons[0]["scope_match_basis"]


def test_component_and_total_are_not_directly_compared_without_relationship() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "facade-repair-scope",
                "facility_id": None,
                "location_scope_kind": "project",
                "facility": "Project as a whole",
                "work_name": "Repair brick facade",
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "west-facade-area",
                            "value": "210",
                            "unit": "м2",
                            "semantic_scope": "Facade repair area",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "NONE",
                            "related_quantity_candidate_ids": [],
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                    "ВОР": [
                        {
                            "quantity_candidate_id": "all-facades-area",
                            "value": "520",
                            "unit": "м2",
                            "semantic_scope": "Facade repair area",
                            "quantity_type": "TOTAL",
                            "relation_kind": "NONE",
                            "related_quantity_candidate_ids": [],
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "semantic_review_profile": PROJECT_WORK_RECONCILIATION_PROFILE,
                        }
                    ],
                },
            }
        ]
    )

    assert comparisons == []


def test_explicit_project_scope_rejects_different_quantity_meanings() -> None:
    comparisons = _validated_scope_quantity_comparisons(
        [
            {
                "work_scope_id": "project-pipeline-scope",
                "facility_id": None,
                "location_scope_kind": "project",
                "facility": "Project as a whole (Block A; Block B)",
                "work_name": "Install pipeline",
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "value": "96",
                            "unit": "m",
                            "semantic_scope": "Carrier pipe length",
                            "scope_compatibility": "SAME_SCOPE",
                        }
                    ],
                    "Смета": [
                        {
                            "value": "96",
                            "unit": "м",
                            "semantic_scope": "Protective casing length",
                            "scope_compatibility": "SAME_SCOPE",
                        }
                    ],
                },
            }
        ]
    )

    assert comparisons == []


def test_legacy_quantity_review_cannot_authorize_new_unlocated_comparison() -> None:
    quantity = {
        "quantity_candidate_id": "legacy-area",
        "value": "8.339",
        "unit": "м2",
        "semantic_scope": "Coated surface area",
        "scope_compatibility": "SAME_SCOPE",
        "relationship_reviewed": True,
        "semantic_review_profile": "qwen-project-work-reconciliation-v20",
    }
    work = {
        "quantities_by_document": {
            "ВОР": [{**quantity, "quantity_candidate_id": "legacy-vor"}],
            "Смета": [quantity],
        }
    }

    assert not _comparison_has_reviewed_quantity_identity(
        work,
        {"semantic_scope": "Coated surface area"},
        "ВОР",
        "Смета",
    )


def test_reviewed_scaled_unit_requires_source_value_when_extraction_is_unscaled() -> None:
    assert (
        _reviewed_scaled_quantity_unit(
            {"normalized_unit": "m2"},
            {"source_unit": "100 м²"},
        )
        is None
    )


def test_reviewed_scaled_unit_accepts_validated_source_value() -> None:
    assert (
        _reviewed_scaled_quantity_unit(
            {"normalized_unit": "m2"},
            {"source_unit": "100 м²", "source_value": "3,27"},
        )
        == "100 м2"
    )


def test_reviewed_scaled_unit_retains_already_scaled_extraction() -> None:
    assert (
        _reviewed_scaled_quantity_unit(
            {"normalized_unit": "m2", "raw_unit": "100 м²"},
            {"source_unit": "100 м²"},
        )
        == "100 м2"
    )


def test_reviewed_exact_base_unit_repairs_truncated_candidate_dimension() -> None:
    from asd_kontur.tender.project_engineering import _reviewed_quantity_unit

    assert (
        _reviewed_quantity_unit(
            {"normalized_unit": "m"},
            {"source_unit": "м³"},
        )
        == "м3"
    )
    assert (
        _reviewed_quantity_unit(
            {"normalized_unit": "m3"},
            {"source_unit": "100 м²"},
        )
        is None
    )
    assert (
        _reviewed_quantity_unit(
            {"normalized_unit": "piece"},
            {"source_unit": "%"},
        )
        is None
    )


def test_reviewed_source_value_is_normalized_without_arithmetic() -> None:
    assert _reviewed_source_quantity_value({"source_value": "2,113"}) == "2.113"
    assert _reviewed_source_quantity_value({"source_value": "1 250,50"}) == "1250.5"
    assert _reviewed_source_quantity_value({}) is None
    assert (
        _reviewed_scaled_quantity_unit(
            {"normalized_unit": "m3"},
            {"source_unit": "100 м²"},
        )
        is None
    )
    assert (
        _reviewed_scaled_quantity_unit(
            {"normalized_unit": "piece"},
            {"source_unit": "100 шт", "source_value": "7,4"},
        )
        == "100 шт"
    )


def test_quantity_comparison_normalizes_russian_unit_inflections() -> None:
    comparisons = _comparisons(
        [
            {
                "work_scope_id": "pile-length",
                "facility": "Подпорная стена ПС-1",
                "work_name": "Устройство свай",
                "quantities_by_document": {
                    "РД": [{"value": "4,0", "unit": "метра"}],
                    "ВОР": [{"value": "4", "unit": "м"}],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATCH"
    assert comparisons[0]["left"]["unit"] == "м"
    assert comparisons[0]["right"]["unit"] == "м"


def test_quantity_comparison_keeps_count_and_concrete_volume_as_separate_measures() -> None:
    comparisons = _comparisons(
        [
            {
                "work_scope_id": "bored-piles",
                "facility": "Подпорная стена ПС-1",
                "work_name": "Устройство свай",
                "quantities_by_document": {
                    "РД": [
                        {"value": "124", "unit": "шт"},
                        {"value": "15.5", "unit": "м3"},
                    ],
                    "ВОР": [{"value": "15.5", "unit": "м3"}],
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATCH"
    assert comparisons[0]["left"] == {
        "document_role": "РД",
        "value": "15.5",
        "unit": "м3",
    }
    assert comparisons[0]["right"] == {
        "document_role": "ВОР",
        "value": "15.5",
        "unit": "м3",
    }


def test_quantity_comparison_does_not_call_different_measure_dimensions_a_discrepancy() -> None:
    comparisons = _comparisons(
        [
            {
                "work_scope_id": "bored-piles",
                "facility": "Подпорная стена ПС-1",
                "work_name": "Устройство свай",
                "quantities_by_document": {
                    "РД": [{"value": "124", "unit": "шт"}],
                    "ВОР": [{"value": "15.5", "unit": "м3"}],
                },
            }
        ]
    )

    assert comparisons == []


def test_component_total_comparison_requires_explicit_semantic_relationship() -> None:
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-a",
                "facility_id": "facility-a",
                "facility": "Корпус А",
                "work_name": "Монтаж металлоконструкций",
                "quantities_by_document": {
                    "РД": [
                        {
                            "quantity_candidate_id": "total",
                            "value": "7.0",
                            "unit": "т",
                            "semantic_scope": "Общая масса каркаса",
                            "quantity_type": "TOTAL",
                            "relation_kind": "TOTAL_FOR",
                            "related_quantity_candidate_ids": ["part-a", "part-b"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "component_set_complete": True,
                            "source_locator_id": "locator-total",
                        },
                        {
                            "quantity_candidate_id": "part-a",
                            "value": "5.2",
                            "unit": "т",
                            "semantic_scope": "Колонны",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "source_locator_id": "locator-a",
                        },
                        {
                            "quantity_candidate_id": "part-b",
                            "value": "3.1",
                            "unit": "т",
                            "semantic_scope": "Балки",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "source_locator_id": "locator-b",
                        },
                    ]
                },
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "COMPONENT_TOTAL_MISMATCH"
    assert comparisons[0]["difference"] == "-1.3"
    assert comparisons[0]["source_locator_ids"] == [
        "locator-a",
        "locator-b",
        "locator-total",
    ]


def test_complete_total_rejects_additional_reviewed_component_not_in_declared_set() -> None:
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-earthworks",
                "facility_id": None,
                "facility": "Объект в целом",
                "work_name": "Разработка грунта",
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "total",
                            "value": "125",
                            "unit": "м3",
                            "semantic_scope": "Общий объём разработки грунта",
                            "quantity_type": "TOTAL",
                            "relation_kind": "TOTAL_FOR",
                            "related_quantity_candidate_ids": ["mechanized"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "component_set_complete": True,
                            "source_locator_id": "locator-total",
                        },
                        {
                            "quantity_candidate_id": "mechanized",
                            "value": "100",
                            "unit": "м3",
                            "semantic_scope": "Механизированная разработка грунта",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "source_locator_id": "locator-mechanized",
                        },
                        {
                            "quantity_candidate_id": "manual",
                            "value": "25",
                            "unit": "м3",
                            "semantic_scope": "Ручная разработка грунта",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "DUPLICATE_OF",
                            "related_quantity_candidate_ids": ["commercial-manual"],
                            "scope_compatibility": "SAME_SCOPE",
                            "relationship_reviewed": True,
                            "relationship_assertions": [
                                {
                                    "relation_kind": "COMPONENT_OF",
                                    "related_quantity_candidate_ids": ["total"],
                                    "scope_compatibility": "COMPONENT_VS_TOTAL",
                                    "relationship_reviewed": True,
                                },
                                {
                                    "relation_kind": "DUPLICATE_OF",
                                    "related_quantity_candidate_ids": ["commercial-manual"],
                                    "scope_compatibility": "SAME_SCOPE",
                                    "relationship_reviewed": True,
                                },
                            ],
                            "source_locator_id": "locator-manual",
                        },
                    ]
                },
            }
        ]
    )

    assert comparisons == []


@pytest.mark.parametrize("conflict", ["second_complete_set", "component_cycle"])
def test_component_total_comparison_rejects_conflicting_review_history(
    conflict: str,
) -> None:
    total = {
        "quantity_candidate_id": "total",
        "value": "125",
        "unit": "м3",
        "semantic_scope": "Total excavation",
        "quantity_type": "TOTAL",
        "relation_kind": "TOTAL_FOR",
        "related_quantity_candidate_ids": ["part-a", "part-b"],
        "scope_compatibility": "COMPONENT_VS_TOTAL",
        "relationship_reviewed": True,
        "component_set_complete": True,
    }
    part_a = {
        "quantity_candidate_id": "part-a",
        "value": "100",
        "unit": "м3",
        "semantic_scope": "Excavation zone A",
        "quantity_type": "COMPONENT",
    }
    part_b = {
        "quantity_candidate_id": "part-b",
        "value": "25",
        "unit": "м3",
        "semantic_scope": "Excavation zone B",
        "quantity_type": "COMPONENT",
    }
    if conflict == "second_complete_set":
        total["relationship_assertions"] = [
            {
                "relation_kind": "TOTAL_FOR",
                "related_quantity_candidate_ids": ["part-a"],
                "scope_compatibility": "COMPONENT_VS_TOTAL",
                "relationship_reviewed": True,
                "component_set_complete": True,
            }
        ]
    else:
        part_a.update(
            {
                "relation_kind": "TOTAL_FOR",
                "related_quantity_candidate_ids": ["total"],
                "scope_compatibility": "COMPONENT_VS_TOTAL",
                "relationship_reviewed": True,
                "component_set_complete": True,
            }
        )
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "excavation-scope",
                "facility_id": "facility-one",
                "work_name": "Excavation",
                "quantities_by_document": {"RD": [total, part_a, part_b]},
            }
        ]
    )

    assert comparisons == []


def test_quantity_schedule_preserves_review_authority_for_component_arithmetic() -> None:
    raw_values = [
        {
            "candidate_id": "total",
            "value": "86",
            "unit": "m3",
            "semantic_scope": "Общий объём железобетона",
            "quantity_type": "TOTAL",
            "relation_kind": "TOTAL_FOR",
            "related_quantity_candidate_ids": ["part-a", "part-b"],
            "scope_compatibility": "COMPONENT_VS_TOTAL",
            "relationship_reviewed": True,
            "component_set_complete": True,
            "source_locator_id": "locator-total",
        },
        {
            "candidate_id": "part-a",
            "value": "48",
            "unit": "m3",
            "semantic_scope": "Плита",
            "quantity_type": "COMPONENT",
            "relation_kind": "COMPONENT_OF",
            "related_quantity_candidate_ids": ["total"],
            "scope_compatibility": "COMPONENT_VS_TOTAL",
            "relationship_reviewed": True,
            "component_set_complete": None,
            "source_locator_id": "locator-a",
        },
        {
            "candidate_id": "part-b",
            "value": "32",
            "unit": "m3",
            "semantic_scope": "Бортовые стенки",
            "quantity_type": "COMPONENT",
            "relation_kind": "COMPONENT_OF",
            "related_quantity_candidate_ids": ["total"],
            "scope_compatibility": "COMPONENT_VS_TOTAL",
            "relationship_reviewed": True,
            "component_set_complete": None,
            "source_locator_id": "locator-b",
        },
    ]

    scheduled_values = _unique_values(raw_values, "quantity")
    total = next(value for value in scheduled_values if value["quantity_candidate_id"] == "total")
    assert total["relationship_reviewed"] is True
    assert total["component_set_complete"] is True
    assert all(value.get("relationship_reviewed") is True for value in scheduled_values)
    assert all(
        "component_set_complete" not in value
        for value in scheduled_values
        if value["quantity_candidate_id"] != "total"
    )

    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-total",
                "facility_id": "facility-a",
                "facility": "Погрузочная платформа",
                "work_name": "Железобетонные конструкции",
                "quantities_by_document": {"РД": scheduled_values},
            }
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "COMPONENT_TOTAL_MISMATCH"
    assert comparisons[0]["left"]["value"] == "86"
    assert comparisons[0]["right"]["value"] == "80"


def test_component_total_comparison_can_join_separate_schedule_rows() -> None:
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-total",
                "facility_id": "facility-a",
                "facility": "Мостовой переход",
                "work_name": "Общая длина трубопровода",
                "quantities_by_document": {
                    "РД": [
                        {
                            "quantity_candidate_id": "total",
                            "value": "150",
                            "unit": "м",
                            "semantic_scope": "Общая длина трубопровода",
                            "quantity_type": "TOTAL",
                            "relation_kind": "TOTAL_FOR",
                            "related_quantity_candidate_ids": ["section-a", "section-b"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "component_set_complete": True,
                            "source_locator_id": "locator-total",
                        }
                    ]
                },
            },
            {
                "work_scope_id": "scope-a",
                "facility_id": "facility-a",
                "facility": "Мостовой переход",
                "work_name": "Участок трубопровода А",
                "quantities_by_document": {
                    "РД": [
                        {
                            "quantity_candidate_id": "section-a",
                            "value": "120",
                            "unit": "м",
                            "semantic_scope": "Длина участка А",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "source_locator_id": "locator-a",
                        }
                    ]
                },
            },
            {
                "work_scope_id": "scope-b",
                "facility_id": "facility-a",
                "facility": "Мостовой переход",
                "work_name": "Участок трубопровода Б",
                "quantities_by_document": {
                    "РД": [
                        {
                            "quantity_candidate_id": "section-b",
                            "value": "80",
                            "unit": "м",
                            "semantic_scope": "Длина участка Б",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "source_locator_id": "locator-b",
                        }
                    ]
                },
            },
        ]
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "COMPONENT_TOTAL_MISMATCH"
    assert comparisons[0]["difference"] == "-50"
    assert comparisons[0]["source_locator_ids"] == [
        "locator-a",
        "locator-b",
        "locator-total",
    ]


def test_component_total_comparison_rejects_explicitly_incomplete_component_set() -> None:
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-earthworks",
                "facility_id": "facility-a",
                "facility": "Сооружение А",
                "work_name": "Разработка грунта",
                "quantities_by_document": {
                    "ПД": [
                        {
                            "quantity_candidate_id": "total",
                            "value": "250",
                            "unit": "м3",
                            "semantic_scope": "Общий объём разработки грунта",
                            "quantity_type": "TOTAL",
                            "relation_kind": "TOTAL_FOR",
                            "related_quantity_candidate_ids": ["manual-part"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "component_set_complete": False,
                        },
                        {
                            "quantity_candidate_id": "manual-part",
                            "value": "40",
                            "unit": "м3",
                            "semantic_scope": "Ручная разработка грунта",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                            "component_set_complete": None,
                        },
                    ]
                },
            }
        ]
    )

    assert comparisons == []


def test_component_total_comparison_rejects_different_explicit_pipe_diameters() -> None:
    comparisons = _component_total_comparisons(
        [
            {
                "work_scope_id": "scope-total",
                "facility_id": None,
                "facility": "Место выполнения не установлено",
                "work_name": "Демонтаж трубопровода",
                "project_wording": ["Демонтаж трубопровода диаметром 300 мм"],
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "quantity_candidate_id": "total",
                            "value": "109",
                            "unit": "м",
                            "semantic_scope": "Общая длина демонтируемого трубопровода",
                            "quantity_type": "TOTAL",
                            "relation_kind": "TOTAL_FOR",
                            "related_quantity_candidate_ids": ["component"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                        }
                    ]
                },
            },
            {
                "work_scope_id": "scope-component",
                "facility_id": None,
                "facility": "Место выполнения не установлено",
                "work_name": "Демонтаж трубопровода",
                "project_wording": ["Демонтаж трубопровода диметром 50 мм"],
                "quantities_by_document": {
                    "ВОР": [
                        {
                            "quantity_candidate_id": "component",
                            "value": "1",
                            "unit": "м",
                            "semantic_scope": "Длина демонтируемого трубопровода",
                            "quantity_type": "COMPONENT",
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["total"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                        }
                    ]
                },
            },
        ]
    )

    assert comparisons == []


def test_component_total_rounding_match_is_not_a_professional_issue() -> None:
    works = [
        {
            "work_scope_id": "scope-total",
            "facility_id": "facility-a",
            "facility": "Резервуар Р-1",
            "work_name": "Защитное покрытие",
            "quantities_by_document": {
                "РД": [
                    {
                        "quantity_candidate_id": "total",
                        "value": "10.0",
                        "unit": "м2",
                        "semantic_scope": "Общая площадь",
                        "quantity_type": "TOTAL",
                        "relation_kind": "TOTAL_FOR",
                        "related_quantity_candidate_ids": ["part-a", "part-b"],
                        "scope_compatibility": "COMPONENT_VS_TOTAL",
                        "relationship_reviewed": True,
                        "component_set_complete": True,
                    },
                    {
                        "quantity_candidate_id": "part-a",
                        "value": "4.96",
                        "unit": "м2",
                        "semantic_scope": "Стена",
                        "quantity_type": "COMPONENT",
                        "relation_kind": "COMPONENT_OF",
                        "related_quantity_candidate_ids": ["total"],
                        "scope_compatibility": "COMPONENT_VS_TOTAL",
                    },
                    {
                        "quantity_candidate_id": "part-b",
                        "value": "5.03",
                        "unit": "м2",
                        "semantic_scope": "Днище",
                        "quantity_type": "COMPONENT",
                        "relation_kind": "COMPONENT_OF",
                        "related_quantity_candidate_ids": ["total"],
                        "scope_compatibility": "COMPONENT_VS_TOTAL",
                    },
                ]
            },
        }
    ]

    comparisons = _component_total_comparisons(works)
    issues = _professional_quantity_issue_comparisons(comparisons)

    assert comparisons[0]["classification"] == "ROUNDING_MATCH"
    assert comparisons[0]["professional_status"] == (
        "Расхождение находится в пределах точности округления"
    )
    assert issues == []


def test_conflicting_component_graph_is_visible_as_unresolved_not_discrepancy() -> None:
    work = {
        "work_scope_id": "scope-a",
        "facility_id": "facility-a",
        "facility": "Корпус А",
        "work_name": "Монтаж металлоконструкций",
        "quantities_by_document": {
            "РД": [
                {
                    "quantity_candidate_id": "total",
                    "value": "12",
                    "unit": "т",
                    "semantic_scope": "Общая масса",
                    "quantity_type": "TOTAL",
                    "relation_kind": "TOTAL_FOR",
                    "related_quantity_candidate_ids": ["part-a", "part-b"],
                    "scope_compatibility": "COMPONENT_VS_TOTAL",
                    "relationship_reviewed": True,
                    "component_set_complete": True,
                    "source_locator_id": "locator-total",
                },
                {
                    "quantity_candidate_id": "part-a",
                    "value": "5",
                    "unit": "т",
                    "semantic_scope": "Масса секции А",
                    "quantity_type": "COMPONENT",
                    "relation_kind": "COMPONENT_OF",
                    "related_quantity_candidate_ids": ["total"],
                    "scope_compatibility": "COMPONENT_VS_TOTAL",
                    "relationship_reviewed": True,
                },
                {
                    "quantity_candidate_id": "part-b",
                    "value": "7",
                    "unit": "т",
                    "semantic_scope": "Масса секции Б",
                    "quantity_type": "COMPONENT",
                    "relation_kind": "COMPONENT_OF",
                    "related_quantity_candidate_ids": ["total"],
                    "scope_compatibility": "COMPONENT_VS_TOTAL",
                    "relationship_reviewed": True,
                    "relationship_assertions": [
                        {
                            "relation_kind": "COMPONENT_OF",
                            "related_quantity_candidate_ids": ["part-a"],
                            "scope_compatibility": "COMPONENT_VS_TOTAL",
                            "relationship_reviewed": True,
                        }
                    ],
                },
            ]
        },
    }
    work["quantities_by_document"]["РД"][1]["relationship_assertions"] = [
        {
            "relation_kind": "COMPONENT_OF",
            "related_quantity_candidate_ids": ["part-b"],
            "scope_compatibility": "COMPONENT_VS_TOTAL",
            "relationship_reviewed": True,
        }
    ]

    comparisons, unresolved = _component_total_analysis([work])

    assert comparisons == []
    assert len(unresolved) == 1
    assert unresolved[0]["quantity_candidate_id"] == "total"
    assert unresolved[0]["unresolved_kind"] == "component_total_relationship"
    assert unresolved[0]["source_locator_id"] == "locator-total"
    assert "противоречат" in unresolved[0]["reason"]


def test_material_schedule_normalizes_unit_but_keeps_source_spelling() -> None:
    values = _unique_values(
        [
            {
                "raw_name": "Арматура А400",
                "normalized_name": "арматура а400",
                "raw_quantity": "2,0",
                "normalized_value": "2.0",
                "raw_unit": "тонны",
                "normalized_unit": "тонны",
                "source_locator_id": "material-row",
            }
        ],
        "material",
    )

    assert values == [
        {
            "name": "Арматура А400",
            "quantity": "2.0",
            "unit": "т",
            "raw_unit": "тонны",
            "source_locator_id": "material-row",
        }
    ]


def test_explicit_material_profile_is_not_overwritten_by_page_context() -> None:
    values = _professional_material_values(
        [
            {
                "name": "Профили фасонные для шпунтовых свай Л5-10",
                "quantity": "9.597828",
                "unit": "т",
                "source_locator_id": "material-row",
            }
        ],
        {
            "material-row": {
                "page_sheet_pile_profiles": ["Л5УМ"],
            }
        },
    )

    assert values[0]["name"] == "Профили фасонные для шпунтовых свай Л5-10"
    assert values[0]["page_context_profiles"] == ["Л5УМ"]
    assert "отличается" in values[0]["profile_context_note"]


def test_page_text_profile_repairs_only_genuinely_split_material_wording() -> None:
    values = _professional_material_values(
        [
            {
                "name": "УМ из стали марки С255",
                "source_locator_id": "material-row",
            }
        ],
        {"material-row": {"page_sheet_pile_profiles": ["Л5УМ"]}},
    )

    assert values[0]["name"] == "Шпунт Л5-УМ из стали марки С255"
    assert values[0]["source_name"] == "УМ из стали марки С255"


def test_sheet_pile_profile_parser_is_not_limited_to_one_project_profile() -> None:
    assert _sheet_pile_profiles("Шпунт Л4-АУ; Л7-12 и Л8") == ["Л4АУ", "Л7-12", "Л8"]


def test_page_text_profile_repair_uses_the_profile_suffix_from_context() -> None:
    values = _professional_material_values(
        [{"name": "АУ из стали марки С345", "source_locator_id": "material-row"}],
        {"material-row": {"page_sheet_pile_profiles": ["Л4АУ"]}},
    )

    assert values[0]["name"] == "Шпунт Л4-АУ из стали марки С345"


def test_page_profile_is_not_attached_to_unrelated_waling_material() -> None:
    assert (
        _material_sheet_pile_profiles(
            {
                "name": "Двутавры с параллельными гранями полок № 20Ш-50Ш",
                "source_locator_id": "waling-row",
            },
            {"waling-row": {"page_sheet_pile_profiles": ["Л5УМ"]}},
        )
        == []
    )


def test_sheet_pile_profile_difference_is_reported_for_each_facility() -> None:
    issues = _issues(
        defects=[],
        comparisons=[],
        scope_comparisons=[],
        sheet_pile_schedule=[
            {
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "profiles_by_document": {"ВОР": ["Л5"]},
                "source_locator_ids": ["vor-kns-4"],
            },
            {
                "facility_id": "kns-4",
                "facility": "КНС 4",
                "profiles_by_document": {"Смета": ["Л5УМ"]},
                "source_locator_ids": ["estimate-kns-4"],
            },
            {
                "facility_id": "kns-8-1",
                "facility": "КНС 8.1",
                "profiles_by_document": {"ВОР": ["Л5-10"], "Смета": ["Л5-10"]},
                "source_locator_ids": ["commercial-kns-8-1"],
            },
        ],
        works=[],
        source_context={},
    )

    profile_issue = next(issue for issue in issues if issue["subject"] == "Профиль шпунта")
    assert profile_issue["finding_kind"] == "MATERIAL_MISMATCH"
    assert profile_issue["location"] == "КНС 4"
    assert profile_issue["description"] == (
        "Для КНС 4 в документах указаны разные профили: ВОР: Л5; Смета: Л5УМ."
    )
    assert all(issue["location"] != "КНС 8.1" for issue in issues)


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


def test_contract_estimate_defines_commercial_scope_for_omission_analysis() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-waterproofing",
                "facility_id": "reservoir-z17",
                "facility": "Reservoir Z-17",
                "family_key": "waterproofing",
                "work_name": "Apply waterproofing membrane",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-waterproofing"],
            },
            {
                "work_scope_id": "commercial-concrete",
                "facility_id": "reservoir-z17",
                "facility": "Reservoir Z-17",
                "family_key": "reinforced_concrete",
                "work_name": "Cast reservoir slab",
                "document_roles": ["Смета контракта"],
                "source_locator_ids": ["contract-estimate-concrete"],
            },
        ]
    )

    waterproofing = next(value for value in comparisons if value["family_key"] == "waterproofing")
    assert waterproofing["classification"] == "WORK_MISSING_IN_COMMERCIAL"


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


def test_same_family_commercial_work_at_other_facilities_does_not_cover_design_scope() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-enclosure-area-a",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work_name": "Устройство шпунтового ограждения",
                "document_roles": ["ПД"],
                "source_locator_ids": ["design-a"],
            },
            {
                "work_scope_id": "commercial-enclosure-area-b",
                "facility_id": "area-b",
                "facility": "Участок Б",
                "family_key": "sheet_piling",
                "work_name": "Погружение шпунта",
                "document_roles": ["ВОР", "Смета"],
                "source_locator_ids": ["commercial-b"],
            },
            {
                "work_scope_id": "commercial-concrete-area-a",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "reinforced_concrete",
                "work_name": "Бетонирование стен",
                "document_roles": ["ВОР"],
                "source_locator_ids": ["commercial-a"],
            },
        ],
        available_document_roles=["ПД", "ВОР", "Смета"],
    )

    enclosure = next(
        value
        for value in comparisons
        if value["facility"] == "Участок А" and value["family_key"] == "sheet_piling"
    )
    assert enclosure["classification"] == "WORK_MISSING_IN_COMMERCIAL"
    assert enclosure["facility"] == "Участок А"


@pytest.mark.parametrize(
    ("reciprocal", "design_facility", "commercial_facility", "expected"),
    [
        (True, None, None, "MATCH"),
        (False, None, None, "UNRESOLVED_SCOPE_MATCH"),
        (True, "depot-a", "depot-b", "UNRESOLVED_SCOPE_MATCH"),
    ],
)
def test_exact_reviewed_work_pair_is_symmetric_without_overriding_location(
    reciprocal: bool,
    design_facility: str | None,
    commercial_facility: str | None,
    expected: str,
) -> None:
    operation = "Монтаж несущего стального каркаса"
    reason = "Обе позиции описывают один и тот же монтаж каркаса"
    design = {
        "work_scope_id": "design-frame",
        "candidate_ids": ["design-frame-candidate"],
        "family_key": "structural_steel",
        "work_name": "Установка каркаса склада",
        "facility_id": design_facility,
        "location_scope_kind": "facility" if design_facility else "unresolved",
        "document_roles": ["ПД"],
        "source_locator_ids": ["design-frame-source"],
        "work_scope_assertions": [
            {
                "source_candidate_id": "design-frame-candidate",
                "related_candidate_id": "commercial-frame-candidate",
                "scope_compatibility": "SAME_SCOPE",
                "normalized_operation": operation,
                "reason": reason,
            }
        ],
    }
    commercial = {
        "work_scope_id": "commercial-frame",
        "candidate_ids": ["commercial-frame-candidate"],
        "family_key": "structural_steel",
        "work_name": "Монтаж металлоконструкций склада",
        "facility_id": commercial_facility,
        "location_scope_kind": "facility" if commercial_facility else "unresolved",
        "document_roles": ["Смета"],
        "source_locator_ids": ["commercial-frame-source"],
        "work_scope_assertions": [
            {
                "source_candidate_id": "commercial-frame-candidate",
                "related_candidate_id": "design-frame-candidate",
                "scope_compatibility": "SAME_SCOPE",
                "normalized_operation": operation,
                "reason": reason,
            }
        ]
        if reciprocal
        else [],
    }
    comparisons = _scope_comparisons([design, commercial], available_document_roles=["ПД", "Смета"])

    assert [row["classification"] for row in comparisons] == [expected, expected]
    if expected == "MATCH":
        for comparison in comparisons:
            assert comparison["design_work"] == design["work_name"]
            assert comparison["commercial_work"] == commercial["work_name"]
            assert comparison["design_roles"] == ["ПД"]
            assert comparison["commercial_roles"] == ["Смета"]
            assert comparison["source_locator_ids"] == [
                "commercial-frame-source",
                "design-frame-source",
            ]


def test_commercial_work_with_two_project_bases_remains_unresolved() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": f"design-{facility}",
                "facility_id": facility,
                "family_key": "waterproofing",
                "work_name": "Apply waterproofing",
                "document_roles": ["РД"],
                "source_locator_ids": [f"design-source-{facility}"],
            }
            for facility in ("zone-a", "zone-b")
        ]
        + [
            {
                "work_scope_id": "commercial-project-wide",
                "location_scope_kind": "project",
                "location_scope_member_ids": ["zone-a", "zone-b"],
                "family_key": "waterproofing",
                "work_name": "Apply waterproofing",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-source"],
            }
        ],
        available_document_roles=["РД", "Смета"],
    )

    commercial = next(
        row
        for row in comparisons
        if row["commercial_roles"] == ["Смета"] and not row["design_roles"]
    )
    assert commercial["classification"] == "UNRESOLVED_SCOPE_MATCH"


def test_reviewed_work_pair_cannot_bridge_disjoint_explicit_project_areas() -> None:
    assert not _explicit_work_locations_compatible(
        {"location_scope_kind": "project", "location_scope_member_ids": ["area-a"]},
        {"location_scope_kind": "project", "location_scope_member_ids": ["area-b"]},
    )


def test_unallocated_same_family_commercial_work_keeps_design_scope_unresolved() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-enclosure-area-a",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work_name": "Устройство шпунтового ограждения",
                "document_roles": ["ПД"],
                "source_locator_ids": ["design-a"],
            },
            {
                "work_scope_id": "commercial-enclosure-unallocated",
                "facility_id": None,
                "facility": "Место выполнения не установлено",
                "family_key": "sheet_piling",
                "work_name": "Погружение шпунта",
                "document_roles": ["ВОР"],
                "source_locator_ids": ["commercial-unallocated"],
            },
            {
                "work_scope_id": "commercial-concrete-area-a",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "reinforced_concrete",
                "work_name": "Бетонирование стен",
                "document_roles": ["ВОР"],
                "source_locator_ids": ["commercial-a"],
            },
        ]
    )

    enclosure = next(
        value
        for value in comparisons
        if value["facility"] == "Участок А" and value["family_key"] == "sheet_piling"
    )
    assert enclosure["classification"] == "UNRESOLVED_SCOPE_MATCH"


def test_project_wide_commercial_scope_covers_only_its_exact_member_facilities() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-waterproofing-a",
                "facility_id": "building-a",
                "facility": "Building A",
                "family_key": "waterproofing",
                "work_name": "Apply foundation waterproofing",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-a"],
            },
            {
                "work_scope_id": "design-waterproofing-c",
                "facility_id": "building-c",
                "facility": "Building C",
                "family_key": "waterproofing",
                "work_name": "Apply foundation waterproofing",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-c"],
            },
            {
                "work_scope_id": "commercial-waterproofing-project",
                "facility_id": None,
                "facility": "Project total (Building A; Building B)",
                "location_scope_kind": "project",
                "location_scope_member_ids": ["building-a", "building-b"],
                "family_key": "waterproofing",
                "work_name": "Apply foundation waterproofing",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-project"],
            },
        ]
    )

    building_a = next(row for row in comparisons if row["facility"] == "Building A")
    building_c = next(row for row in comparisons if row["facility"] == "Building C")
    assert building_a["classification"] == "MATCH"
    assert building_a["professional_status"] == ("Коммерческий состав найден в общем объёме")
    assert "распределение количества" in building_a["conclusion"]
    assert building_c["classification"] == "UNRESOLVED_SCOPE_MATCH"

    project_row = next(row for row in comparisons if row["location_scope_kind"] == "project")
    assert project_row["classification"] == "MATCH"
    assert "коммерческий объём по сооружениям не распределён" in project_row["conclusion"]


def test_unclassified_project_wide_commercial_scope_blocks_false_omission() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-formwork-a",
                "facility_id": "building-a",
                "facility": "Building A",
                "family_key": "formwork",
                "work_name": "Install wall formwork",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-formwork"],
            },
            {
                "work_scope_id": "commercial-concrete-project",
                "facility_id": None,
                "facility": "Project total (Building A; Building B)",
                "location_scope_kind": "project",
                "location_scope_member_ids": ["building-a", "building-b"],
                "family_key": "reinforced_concrete",
                "work_name": "Cast concrete walls",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-concrete"],
            },
        ],
        unclassified_works=[
            {
                "project_wording": "Unresolved project-wide commercial row",
                "document_role": "Смета",
                "location_scope_kind": "project",
                "location_scope_member_ids": ["building-a", "building-b"],
            }
        ],
    )

    formwork = next(row for row in comparisons if row["family_key"] == "formwork")
    assert formwork["classification"] == "UNRESOLVED_SCOPE_MATCH"
    assert formwork["professional_status"] == ("Сопоставление коммерческого состава не завершено")


def test_generic_sheet_pile_design_scope_covers_driving_at_same_facility_only() -> None:
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-enclosure",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work_name": "Устройство шпунтового ограждения",
                "document_roles": ["ПД"],
                "source_locator_ids": ["design-a"],
            },
            {
                "work_scope_id": "commercial-driving",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work_name": "Погружение шпунта",
                "document_roles": ["ВОР"],
                "source_locator_ids": ["commercial-a"],
            },
            {
                "work_scope_id": "commercial-extraction",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work_name": "Извлечение шпунта",
                "document_roles": ["ВОР"],
                "source_locator_ids": ["commercial-extraction-a"],
            },
        ]
    )

    driving = next(row for row in comparisons if row["work"] == "Погружение шпунта")
    extraction = next(row for row in comparisons if row["work"] == "Извлечение шпунта")
    enclosure = next(row for row in comparisons if row["design_roles"] == ["ПД"])
    assert driving["classification"] == "MATCH"
    assert enclosure["classification"] == "MATCH"
    assert extraction["classification"] == "UNRESOLVED_SCOPE_MATCH"


def test_reciprocal_exact_work_pair_authorizes_different_source_wording() -> None:
    reason = "Обе строки описывают один объём монтажа ферм."
    comparisons = _scope_comparisons(
        [
            {
                "work_scope_id": "design-trusses",
                "candidate_ids": ["design-row"],
                "work_scope_assertions": [
                    {
                        "source_candidate_id": "design-row",
                        "related_candidate_id": "commercial-row",
                        "scope_compatibility": "SAME_SCOPE",
                        "normalized_operation": "Монтаж стальных ферм",
                        "reason": reason,
                    }
                ],
                "facility_id": "gallery-b",
                "facility": "Gallery B",
                "family_key": "structural_steel",
                "work_name": "Устройство несущего покрытия",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-locator"],
            },
            {
                "work_scope_id": "commercial-trusses",
                "candidate_ids": ["commercial-row"],
                "work_scope_assertions": [
                    {
                        "source_candidate_id": "commercial-row",
                        "related_candidate_id": "design-row",
                        "scope_compatibility": "SAME_SCOPE",
                        "normalized_operation": "Монтаж стальных ферм",
                        "reason": reason,
                    }
                ],
                "facility_id": "gallery-b",
                "facility": "Gallery B",
                "family_key": "structural_steel",
                "work_name": "Монтаж ферм покрытия",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-locator"],
            },
        ]
    )

    assert {value["classification"] for value in comparisons} == {"MATCH"}


def test_reciprocal_different_scope_rejects_false_work_match() -> None:
    reason = "Проектная строка описывает фермы, коммерческая — связи покрытия."
    common = {
        "facility_id": "gallery-b",
        "facility": "Gallery B",
        "family_key": "structural_steel",
    }
    comparisons = _scope_comparisons(
        [
            {
                **common,
                "work_scope_id": "design-trusses",
                "candidate_ids": ["design-row"],
                "work_scope_assertions": [
                    {
                        "source_candidate_id": "design-row",
                        "related_candidate_id": "commercial-row",
                        "scope_compatibility": "DIFFERENT_SCOPE",
                        "normalized_operation": None,
                        "reason": reason,
                    }
                ],
                "work_name": "Монтаж металлоконструкций",
                "document_roles": ["РД"],
                "source_locator_ids": ["design-locator"],
            },
            {
                **common,
                "work_scope_id": "commercial-bracing",
                "candidate_ids": ["commercial-row"],
                "work_scope_assertions": [
                    {
                        "source_candidate_id": "commercial-row",
                        "related_candidate_id": "design-row",
                        "scope_compatibility": "DIFFERENT_SCOPE",
                        "normalized_operation": None,
                        "reason": reason,
                    }
                ],
                "work_name": "Монтаж металлоконструкций",
                "document_roles": ["Смета"],
                "source_locator_ids": ["commercial-locator"],
            },
        ]
    )

    assert {value["classification"] for value in comparisons} == {"UNRESOLVED_SCOPE_MATCH"}


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
    assert issue["finding_kind"] == "DESIGN_SCOPE_MISSING_COMMERCIAL"
    assert issue["kind"] == "Возможная неучтённая работа"
    assert issue["location"] == "КНС 8.1"
    assert "Рекультивация" in issue["recommended_action"]


def test_commercial_only_work_becomes_a_project_basis_question() -> None:
    issues = _issues(
        defects=[],
        comparisons=[],
        scope_comparisons=[
            {
                "scope_comparison_id": "commercial-only-loading",
                "classification": "COMMERCIAL_ONLY_WORK",
                "facility_id": "wall-z17",
                "facility": "Retaining wall Z-17",
                "family_key": "soil_disposal",
                "work": "Load excavated soil",
                "conclusion": "The commercial item is not linked to an established design scope.",
                "source_locator_ids": ["contract-estimate-loading"],
            }
        ],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )

    assert len(issues) == 1
    assert issues[0]["finding_kind"] == "COMMERCIAL_SCOPE_WITHOUT_DESIGN_BASIS"
    assert issues[0]["location"] == "Retaining wall Z-17"
    assert "проектный документ-основание" in issues[0]["recommended_action"]


def test_sheet_pile_omission_becomes_an_issue_but_embedded_operations_do_not() -> None:
    issues = _issues(
        defects=[],
        comparisons=[],
        scope_comparisons=[
            {
                "scope_comparison_id": "sheet-pile-gap",
                "classification": "WORK_MISSING_IN_COMMERCIAL",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "sheet_piling",
                "work": "Устройство шпунтового ограждения",
                "conclusion": "Работа не найдена в предоставленной ВОР.",
                "source_locator_ids": ["sheet-pile-design"],
            },
            {
                "scope_comparison_id": "formwork-gap",
                "classification": "WORK_MISSING_IN_COMMERCIAL",
                "facility_id": "area-a",
                "facility": "Участок А",
                "family_key": "formwork",
                "work": "Опалубочные работы",
                "conclusion": "Отдельная строка не найдена в предоставленной ВОР.",
                "source_locator_ids": ["formwork-design"],
            },
        ],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )

    assert [issue["subject"] for issue in issues] == ["Устройство шпунтового ограждения"]


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

    assert model["model_version"] == "project-engineering-model-v83"
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
    assert model["sheet_pile_schedule"][0]["pit"] == (
        "приёмный котлован для КНС-2; рабочий котлован для КНС-2"
    )
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


def test_project_overview_consolidates_professional_field_aliases() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-overview",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [
                {
                    "candidate_id": "name-project",
                    "label": "project_name",
                    "value": "Реконструкция водопропускной трубы",
                    "source_version_id": "source-a",
                    "source_locator_id": "name-a",
                },
                {
                    "candidate_id": "name-construction",
                    "label": "construction_name",
                    "value": "Реконструкция водопропускной трубы",
                    "source_version_id": "source-b",
                    "source_locator_id": "name-b",
                },
                {
                    "candidate_id": "description",
                    "label": "object_description",
                    "value": "Водопропускная труба из сборных секций длиной 48 м",
                    "source_version_id": "source-a",
                    "source_locator_id": "description",
                },
                {
                    "candidate_id": "location",
                    "label": "location",
                    "value": "г. Новоград, ул. Речная",
                    "source_version_id": "source-b",
                    "source_locator_id": "location",
                },
                {
                    "candidate_id": "foundation",
                    "label": "foundation_type",
                    "value": "Сборная труба на щебёночном основании",
                    "source_version_id": "source-a",
                    "source_locator_id": "foundation",
                },
            ],
            "work_types": [],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert model["project"]["name"] == {
        "value": "Реконструкция водопропускной трубы",
        "status": "Установлено по нескольким документам",
        "source_count": 2,
        "source_locator_ids": ["name-a", "name-b"],
    }
    assert model["project"]["description"]["value"].startswith("Водопропускная труба")
    assert model["project"]["purpose"] == {
        "value": "Реконструкция водопропускной трубы",
        "status": "Назначение установлено из наименования объекта",
        "source_locator_ids": ["name-a", "name-b"],
    }
    assert model["project"]["location"]["value"].startswith("г. Новоград")
    assert model["project"]["foundation"]["value"] == ("Сборная труба на щебёночном основании")


def test_project_status_becomes_established_after_composition_is_assembled() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-overview-composition",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [
                {
                    "candidate_id": "name",
                    "label": "project_name",
                    "value": "Реконструкция водопропускного сооружения",
                    "source_version_id": "source-a",
                    "source_locator_id": "name",
                }
            ],
            "work_types": [],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "Водопропускное сооружение ВС-1",
                "candidate_labels": ["Водопропускное сооружение ВС-1"],
                "member_structure_node_ids": ["facility-node-a", "facility-node-b"],
                "source_locator_ids": ["facility-a", "facility-b"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert model["project"]["composition"]["value"] == "Водопропускное сооружение ВС-1"
    assert model["project"]["status"] == "Установлено"
    assert model["project"]["missing_information"] == []


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
                },
                {
                    "candidate_id": "unrelated-material",
                    "work_candidate_id": "excavation",
                    "value": "Песок природный",
                    "normalized_name": "песок природный",
                    "source_locator_id": "unrelated-material",
                },
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
                _source("unrelated-material", "Спецификация.pdf", 5),
            ]
        ),
    )

    sheet_row = model["sheet_pile_schedule"][0]
    assert sheet_row["profiles"] == ["Л5УМ"]
    assert sheet_row["project_wording"] == ["Шпунт Л5-УМ, сталь С255"]
    assert sheet_row["quantities_by_document"] == {}
    assert [
        value["name"] for values in sheet_row["materials_by_document"].values() for value in values
    ] == ["Шпунт Л5-УМ, сталь С255"]
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
        "Монтаж кабеля в проложенных трубах": "electrical",
        "Монтаж шкафа управления": "electrical",
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
        "Сварка встык пластмассовых труб диаметром 250 мм": "pipeline",
        "Установка круглых стеклокомпозитных пескоуловителей": "equipment_installation",
        "Транспортировка конструкций и материалов": "transportation",
        "Планировочные работы на строительной площадке": "site_preparation",
        "Зачистка дна и откосов траншеи вручную": "excavation",
        "Визуальный контроль качества сварных соединений": "testing",
        "Укрепление стенок траншеи инвентарными щитами": "bracing",
        "Утрамбовка грунта вокруг колодца": "compaction",
        "Подсыпка песком средней крупности": "pit_preparation",
        "Монтаж габионов для защиты откоса": "gabion_erosion_protection",
        "Геодезические работы по разбивке осей": "surveying",
        "Удаление кустарников на строительной площадке": "site_preparation",
        "Доставка (перемещение) на строительную площадку": "transportation",
        "Перемещение строительной техники": "transportation",
        "Установка трубчатых металлических стоек": "structural_steel",
        "Установка лестницы из алюминия": "structural_steel",
        "Входной контроль поступивших изделий": "testing",
        "Установка системы вентиляции с дефлектором": "equipment_installation",
        "Временное хранение строительных и бытовых отходов": "waste_management",
        "Снятие и складывание ПСП": "reclamation",
        "Обратная надвижка снятого ПСП": "reclamation",
        "Ввод инженерных сетей": "pipeline",
        "Перекладка участка стального водопровода 300 мм": "pipeline",
        "Перенос сетей водоснабжения": "pipeline",
        "Врезка в существующие сети стального патрубка диаметром 50 мм": "pipeline",
        "Протаскивание в футляр стальных труб диаметром 300 мм": "pipeline",
        "Заполнение свай бетоном": "pile_foundation",
        "Устройство подпорной стены из бетона В25, W6, F100": "reinforced_concrete",
        "Втрамбовка щебня в грунт основания": "pit_preparation",
        "Устройство дренажного лотка Л1-8": "drainage",
        "Установка трубок водоотводных ПП 50 мм": "drainage",
        "Усиление участка стены упорными контрфорсами": "structural_repair",
        "Укладка геотекстиля": "geosynthetics",
        "Устройство деформационных швов": "movement_joints",
        "Огрунтовка металлических поверхностей грунтовкой ГФ-021": "protective_coating",
        "Отделка поверхности стены цементным раствором": "finishing",
        "Устройство металлического ограждения высотой 1,05 м": "fencing",
        "Пробивка отверстий в бетонной стене": "openings",
        "Монтаж задвижки клиновой Ду 300": "pipeline",
        "Доставка груза на строительную площадку": "transportation",
        "Вывоз мусора": "waste_management",
    }

    for wording, family_key in expected.items():
        result = classify_work_family(wording)
        assert result is not None
        assert result[0] == family_key

    assert classify_work_family("Вывоз после приемки со склада готового оборудования") is None


def test_project_titles_section_headings_and_material_rows_are_not_work_scopes() -> None:
    expected = {
        "Капитальный ремонт подпорной стены по ул. Примерная, 10": "Наименование объекта",
        (
            "Выполнение работ по реконструкции путепровода по адресу Примерный проезд, 7"
        ): "Наименование объекта",
        "Конструктивные решения": "Заголовок раздела",
        "ЛСР №04-02-03 Наружное освещение": "Заголовок локального сметного раздела",
        "Сооружения (надземная часть корпуса)": "Заголовок конструкции",
        "Прочие работы и затраты": "Обобщённый сметный раздел",
        (
            "Наружные сети водопровода, канализации, теплоснабжения, "
            "газопроводы для районов Крайнего Севера"
        ): "Заголовок раздела",
        "Трубы стальные бесшовные горячедеформированные диаметром 325 мм": "материала или изделия",
        "Плиты перекрытия 2ПП15-1": "материала или изделия",
        "Кольца для колодцев сборные железобетонные": "материала или изделия",
        "Мастика битумная": "материала или изделия",
        "Каркасы арматурные": "материала или изделия",
        "Люк чугунный тяжелый Т(С250)": "материала или изделия",
        "Щебень из плотных горных пород": "материала или изделия",
        "Инженерно-геодезические изыскания": "Проектная/расчётная работа",
        "Разработка проектной документации": "Проектная/расчётная работа",
    }

    for wording, reason_fragment in expected.items():
        reason = non_work_reason(wording)
        assert reason is not None
        assert reason_fragment.casefold() in reason.casefold()


def test_specific_operation_wins_over_broad_material_family() -> None:
    expected = {
        "Разборка железобетонных конструкций объемом более 1 м³": "demolition",
        (
            "Устройство железобетонных буронабивных свай с бурением скважин вращательным способом"
        ): "pile_foundation",
        "Устройство круглых колодцев из сборного железобетона": "chambers_wells",
        "Устройство дренажного коллектора за стеной": "drainage",
    }

    for wording, family_key in expected.items():
        result = classify_work_family(wording)
        assert result is not None
        assert result[0] == family_key


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


def test_current_reviewed_scope_connects_unassigned_work_wording_one_to_one() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-alpha",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "design-wall",
                    "version": 1,
                    "value": "Монолитная стена из бетона класса В30",
                    "source_version_id": "source-design",
                    "source_locator_id": "design-work",
                    "source_role": "project_documentation",
                },
                {
                    "candidate_id": "commercial-wall",
                    "version": 1,
                    "value": "Устройство железобетонной стены",
                    "source_version_id": "source-commercial",
                    "source_locator_id": "commercial-work",
                    "source_role": "bill_of_quantities",
                },
                {
                    "candidate_id": "commercial-foundation",
                    "version": 1,
                    "value": "Устройство железобетонного фундамента",
                    "source_version_id": "source-foundation",
                    "source_locator_id": "foundation-work",
                    "source_role": "bill_of_quantities",
                },
            ],
            "quantities": [
                {
                    "candidate_id": "design-wall-volume",
                    "work_candidate_id": "design-wall",
                    "normalized_value": "142.6",
                    "normalized_unit": "м3",
                    "source_locator_id": "design-quantity",
                },
                {
                    "candidate_id": "commercial-wall-volume",
                    "work_candidate_id": "commercial-wall",
                    "normalized_value": "137.4",
                    "normalized_unit": "м3",
                    "source_locator_id": "commercial-quantity",
                },
                {
                    "candidate_id": "commercial-foundation-volume",
                    "work_candidate_id": "commercial-foundation",
                    "normalized_value": "55.2",
                    "normalized_unit": "м3",
                    "source_locator_id": "foundation-quantity",
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
                _source("design-work", "Design.pdf", 12),
                _source("commercial-work", "Quantities.pdf", 4),
                _source("foundation-work", "Quantities.pdf", 7),
                _source("design-quantity", "Design.pdf", 12),
                _source("commercial-quantity", "Quantities.pdf", 4),
                _source("foundation-quantity", "Quantities.pdf", 7),
            ]
        ),
        work_resolutions={
            "design-wall": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v30",
                "status": "MATCHED",
                "family_key": "reinforced_concrete",
                "operation": "Железобетонные конструкции",
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "design-wall-volume",
                        "status": "WORK_QUANTITY",
                        "semantic_scope": "Объём бетона стены секции R-4",
                        "quantity_type": "TOTAL",
                        "relation_kind": "NONE",
                        "scope_compatibility": "SAME_SCOPE",
                        "scope_assertions": [
                            {
                                "related_quantity_candidate_id": "commercial-wall-volume",
                                "scope_compatibility": "SAME_SCOPE",
                                "reason": "Same wall concrete scope.",
                            }
                        ],
                        "relationship_reviewed": True,
                    }
                ],
            },
            "commercial-wall": {
                "candidate_version": 1,
                "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
                "status": "MATCHED",
                "family_key": "reinforced_concrete",
                "operation": "Железобетонные конструкции",
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "commercial-wall-volume",
                        "status": "WORK_QUANTITY",
                        "semantic_scope": "Объём бетона стены секции R-4",
                        "quantity_type": "TOTAL",
                        "relation_kind": "NONE",
                        "scope_compatibility": "SAME_SCOPE",
                        "scope_assertions": [
                            {
                                "related_quantity_candidate_id": "design-wall-volume",
                                "scope_compatibility": "SAME_SCOPE",
                                "reason": "Same wall concrete scope.",
                            }
                        ],
                        "relationship_reviewed": True,
                    }
                ],
            },
            "commercial-foundation": {
                "candidate_version": 1,
                "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
                "status": "MATCHED",
                "family_key": "reinforced_concrete",
                "operation": "Железобетонные конструкции",
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "commercial-foundation-volume",
                        "status": "WORK_QUANTITY",
                        "semantic_scope": "Объём бетона фундамента секции R-4",
                        "quantity_type": "TOTAL",
                        "relation_kind": "NONE",
                        "scope_compatibility": "SAME_SCOPE",
                        "relationship_reviewed": True,
                    }
                ],
            },
        },
    )

    assert len(model["works"]) == 2
    assert len(model["quantity_comparisons"]) == 1
    comparison = model["quantity_comparisons"][0]
    assert comparison["left"] == {"document_role": "ПД", "value": "142.6", "unit": "м3"}
    assert comparison["right"] == {"document_role": "ВОР", "value": "137.4", "unit": "м3"}
    assert comparison["difference"] == "5.2"
    compared_work = next(
        work for work in model["works"] if set(work["document_roles"]) == {"ПД", "ВОР"}
    )
    assert {
        value["semantic_review_profile"]
        for values in compared_work["quantities_by_document"].values()
        for value in values
    } == {"qwen-project-work-reconciliation-v30", PROJECT_WORK_RECONCILIATION_PROFILE}


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
    assert non_work_reason("ОТм(Зтм) Средний разряд машинистов 6") == (
        "Сметный показатель трудозатрат, а не отдельная строительная операция"
    )


@pytest.mark.parametrize(
    ("wording", "reason_fragment"),
    [
        ("Итого по расценке 412,60", "итог"),
        ("Всего по позиции 7 980,00", "итог"),
        ("Материальные ресурсы", "стоимости"),
        ("Средства на оплату труда", "стоимости"),
        ("2 ЭМ 315,40 0,8 252,32", "эксплуатации машин"),
        ("3 в т.ч. ОТМ 184,25", "эксплуатации машин"),
        ("К.С. 812/пр-025.0 НР - Монтаж оборудования", "норматив"),
        ("774/пр-031.02 СП - Автомобильные дороги", "норматив"),
    ],
)
def test_generic_estimate_accounting_rows_are_not_construction_works(
    wording: str, reason_fragment: str
) -> None:
    reason = non_work_reason(wording)

    assert reason is not None
    assert reason_fragment in reason.casefold()


@pytest.mark.parametrize(
    ("wording", "reason_fragment"),
    [
        ("7 91.05.05-015 Mobile crane, lifting capacity 20 t", "resource"),
        ("Normative labour input of operators", "labour"),
        ("Labour input of construction workers; grade 4.2", "labour"),
        ("FOT 42.80 3100", "cost"),
        ("Reserve for unforeseen work and costs — 1.5%", "reserve"),
    ],
)
def test_generic_numbered_resource_and_accounting_grammar_is_not_work(
    wording: str, reason_fragment: str
) -> None:
    translations = {
        "Normative labour input of operators": "Нормативные затраты труда машинистов",
        "Labour input of construction workers; grade 4.2": (
            "Затраты труда рабочих-строителей; разряд: 4,2"
        ),
        "FOT 42.80 3100": "ФОТ 42,80 3100",
        "Reserve for unforeseen work and costs — 1.5%": (
            "Резерв на непредвиденные работы и затраты — 1,5%"
        ),
    }

    reason = non_work_reason(translations.get(wording, wording))

    assert reason is not None
    expected = {
        "resource": "ресурс",
        "labour": "трудозатрат",
        "cost": "стоимости",
        "reserve": "резерв",
    }[reason_fragment]
    assert expected in reason.casefold()


def test_linked_material_is_not_a_work_without_an_explicit_operation() -> None:
    assert (
        non_work_reason(
            "Polymer membrane 2.0 mm",
            linked_material=True,
        )
        == "Материальная позиция, а не отдельная строительная операция"
    )
    assert (
        non_work_reason(
            "Устройство полимерной мембраны толщиной 2,0 мм",
            linked_material=True,
        )
        is None
    )


@pytest.mark.parametrize(
    "wording",
    [
        "Устройство монолитной плиты",
        "Монтаж технологического трубопровода",
        "Итоговое бетонирование захватки",
        "Сталь листовая С345 толщиной 12 мм",
    ],
)
def test_estimate_accounting_grammar_does_not_exclude_work_or_material_rows(
    wording: str,
) -> None:
    assert non_work_reason(wording) is None


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


def test_reconciliation_prioritizes_vor_denominator_before_estimate_tail() -> None:
    vor = work_reconciliation_priority(
        "Устройство основания",
        document_role="ВОР",
        nearby_context="Общие объёмы",
    )
    estimate = work_reconciliation_priority(
        "Устройство основания",
        document_role="Смета",
        nearby_context="Общие объёмы",
    )

    assert vor > estimate


@pytest.mark.parametrize("role", ("ПД", "РД", "КР", "АР", "Спецификация", "Расчёт"))
def test_professional_design_roles_are_comparison_inputs(role: str) -> None:
    assert document_comparison_side(role, "generic-source.bin") == "design"


@pytest.mark.parametrize("role", ("ВОР", "Смета", "Смета контракта"))
def test_professional_commercial_roles_are_comparison_inputs(role: str) -> None:
    assert document_comparison_side(role, "generic-source.bin") == "commercial"


def test_specific_commercial_filename_overrides_broad_design_role() -> None:
    assert document_comparison_side("ПД", "Локальная смета № 7.pdf") == "commercial"


def test_document_composition_exposes_contract_and_customer_requirements() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-procurement",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=[],
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={
            "contract": {
                "safe_display_name": "Проект контракта.docx",
                "source_version_id": "contract-source",
                "document_version": 1,
            },
            "requirements": {
                "safe_display_name": "Требования к описанию объекта закупки.docx",
                "source_version_id": "requirements-source",
                "document_version": 1,
            },
        },
    )

    assert model["document_composition"]["role_counts"]["Договор"] == 1
    assert model["document_composition"]["role_counts"]["Требования Заказчика"] == 1
    assert "Договор" in model["document_composition"]["available_roles"]
    assert "Требования Заказчика" in model["document_composition"]["available_roles"]


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


def test_generic_project_structures_are_navigation_roots_without_facility_container() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-retaining-structure",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=[],
        identity_components=[
            {
                "identity_candidate_id": "structure-north",
                "identity_kind": "structure",
                "canonical_label": "Подпорная конструкция Северная",
                "candidate_labels": [
                    "Подпорная конструкция Северная",
                    "Северная подпорная конструкция",
                ],
                "member_structure_node_ids": ["north-rd", "north-pz"],
                "source_locator_ids": ["north-rd-locator", "north-pz-locator"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert [(row["name"], row["kind"]) for row in model["facilities"]] == [
        ("Подпорная конструкция Северная", "Конструкция")
    ]
    assert model["facilities"][0]["status"] == (
        "Установлено сопоставлением в нескольких документах"
    )


def test_generic_identity_components_preserve_distinct_same_named_facilities() -> None:
    components = [
        {
            "identity_candidate_id": suffix,
            "identity_kind": "facility",
            "canonical_label": "Технологическая площадка",
            "candidate_labels": ["Технологическая площадка"],
            "member_structure_node_ids": [f"{suffix}-rd", f"{suffix}-pz"],
            "source_locator_ids": [f"{suffix}-rd-locator", f"{suffix}-pz-locator"],
        }
        for suffix in ("east", "west")
    ]
    model = build_project_engineering_model(
        workspace_id="workspace-same-names",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=[],
        identity_components=components,
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert len(model["facilities"]) == 2
    assert {row["name"] for row in model["facilities"]} == {"Технологическая площадка"}
    assert len({row["facility_id"] for row in model["facilities"]}) == 2
    assert established_facility_designations(components) == ()


def test_repeated_addressed_structures_form_distinct_incremental_project_cards() -> None:
    nodes = [
        {
            "structure_node_id": f"wall-{address}-{source}",
            "node_kind": "structure",
            "raw_name": f"Пешеходная эстакада по ул. Садовая, {address}",
            "source_version_id": source,
            "source_locator_id": f"locator-{address}-{source}",
        }
        for address in ("14/2", "16/2")
        for source in ("pz", "kr")
    ]
    nodes.extend(
        {
            "structure_node_id": f"combined-{source}",
            "node_kind": "structure",
            "raw_name": "Пешеходные эстакады по ул. Садовая, 14/2, ул. Садовая, 16/2",
            "source_version_id": source,
            "source_locator_id": f"combined-locator-{source}",
        }
        for source in ("pz", "kr")
    )
    model = build_project_engineering_model(
        workspace_id="workspace-addressed-walls",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=nodes,
        identity_components=[],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert len(model["facilities"]) == 2
    assert {row["name"] for row in model["facilities"]} == {
        "Пешеходная эстакада по ул. Садовая, 14/2",
        "Пешеходная эстакада по ул. Садовая, 16/2",
    }
    assert {row["status"] for row in model["facilities"]} == {
        "Установлено по одинаковому адресу в нескольких документах"
    }
    assert all(len(row["member_structure_node_ids"]) == 2 for row in model["facilities"])
    assert established_facility_designations([], structure_nodes=nodes) == (
        "Пешеходная эстакада по ул. Садовая, 14/2",
        "Пешеходная эстакада по ул. Садовая, 16/2",
    )


def test_address_alias_components_do_not_duplicate_project_facilities() -> None:
    nodes = [
        {
            "structure_node_id": f"wall-{address}-{source}",
            "node_kind": "structure",
            "raw_name": f"Подпорная стена по ул. Северная, {address}",
            "source_version_id": source,
            "source_locator_id": f"locator-{address}-{source}",
        }
        for address in ("10/1", "12/1")
        for source in ("pz", "kr")
    ]
    components = [
        {
            "identity_candidate_id": f"full-{address}",
            "identity_kind": "structure",
            "canonical_label": f"Подпорная стена по ул. Северная, {address}",
            "candidate_labels": [f"Подпорная стена по ул. Северная, {address}"],
            "member_structure_node_ids": [f"full-{address}-pz", f"full-{address}-kr"],
            "source_locator_ids": [f"full-{address}-pz-loc", f"full-{address}-kr-loc"],
        }
        for address in ("10/1", "12/1")
    ]
    components.extend(
        {
            "identity_candidate_id": f"address-{address}",
            "identity_kind": "structure",
            "canonical_label": f"ул. Северная, {address}",
            "candidate_labels": [f"ул. Северная, {address}"],
            "member_structure_node_ids": [f"address-{address}-pz", f"address-{address}-kr"],
            "source_locator_ids": [f"address-{address}-pz-loc", f"address-{address}-kr-loc"],
        }
        for address in ("10/1", "12/1")
    )
    components.extend(
        [
            {
                "identity_candidate_id": "generic",
                "identity_kind": "facility",
                "canonical_label": "Подпорные стены",
                "candidate_labels": ["Подпорные стены"],
                "member_structure_node_ids": ["generic-pz", "generic-kr"],
                "source_locator_ids": ["generic-pz-loc", "generic-kr-loc"],
            },
            {
                "identity_candidate_id": "combined",
                "identity_kind": "facility",
                "canonical_label": ("Подпорные стены по ул. Северная, 10/1 и ул. Северная, 12/1"),
                "candidate_labels": ["Подпорные стены по ул. Северная, 10/1 и ул. Северная, 12/1"],
                "member_structure_node_ids": ["combined-pz", "combined-kr"],
                "source_locator_ids": ["combined-pz-loc", "combined-kr-loc"],
            },
        ]
    )

    model = build_project_engineering_model(
        workspace_id="workspace-address-aliases",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=nodes,
        identity_components=components,
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert {row["name"] for row in model["facilities"]} == {
        "Подпорная стена по ул. Северная, 10/1",
        "Подпорная стена по ул. Северная, 12/1",
    }
    assert len(model["facilities"]) == 2


def test_project_scope_requires_explicit_reference_to_every_addressed_facility() -> None:
    facilities = [
        {"name": "Подпорная стена по ул. Северная, 10/1"},
        {"name": "Подпорная стена по ул. Северная, 12/1"},
        {"name": "Участок производства работ"},
    ]

    assert _project_scope_facility_label(
        "Подпорные стены по ул. Северная, 10/1 и ул. Северная, 12/1",
        facilities,
    ) == (
        "Объект в целом (Подпорная стена по ул. Северная, 10/1; "
        "Подпорная стена по ул. Северная, 12/1)"
    )
    assert (
        _project_scope_facility_label("Подпорная стена по ул. Северная, 10/1", facilities) is None
    )
    assert _project_scope_facility_label("Подпорные стены", facilities) is None
    assert _project_scope_facility_label(
        (
            "Ведомость объемов конструктивных решений (элементов) и комплексов "
            "(видов) работ. Капитальный ремонт подпорных стен по ул. Северная, "
            "10/1 и ул. Северная, 12/1"
        ),
        facilities,
    ) == (
        "Объект в целом (Подпорная стена по ул. Северная, 10/1; "
        "Подпорная стена по ул. Северная, 12/1)"
    )


def test_commercial_heading_assigns_work_to_explicit_multi_facility_project_scope() -> None:
    source_context = dict([_source("estimate-earthwork", "Estimate Q-42.pdf", 2)])
    source_context["estimate-earthwork"].update(
        page_commercial_scope_code="04-02-03",
        page_commercial_scope_header=(
            "Local estimate 04-02-03. Repair of retaining walls at "
            "ул. Северная, 10/1 and ул. Северная, 12/1"
        ),
    )
    model = build_project_engineering_model(
        workspace_id="workspace-project-commercial-scope",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "estimate-earthwork",
                    "version": 1,
                    "value": "Разработка грунта экскаватором",
                    "source_version_id": "estimate-version",
                    "source_locator_id": "estimate-earthwork",
                    "source_role": "local_estimate",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=[
            {
                "identity_kind": "facility",
                "canonical_label": "Подпорная стена по ул. Северная, 10/1",
                "candidate_labels": ["Подпорная стена по ул. Северная, 10/1"],
                "member_structure_node_ids": ["wall-10-pz", "wall-10-kr"],
                "source_locator_ids": ["wall-10-pz-source", "wall-10-kr-source"],
            },
            {
                "identity_kind": "facility",
                "canonical_label": "Подпорная стена по ул. Северная, 12/1",
                "candidate_labels": ["Подпорная стена по ул. Северная, 12/1"],
                "member_structure_node_ids": ["wall-12-pz", "wall-12-kr"],
                "source_locator_ids": ["wall-12-pz-source", "wall-12-kr-source"],
            },
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=source_context,
    )

    assert model["works"][0]["facility"] == (
        "Объект в целом (Подпорная стена по ул. Северная, 10/1; "
        "Подпорная стена по ул. Северная, 12/1)"
    )
    assert model["works"][0]["location_scope_kind"] == "project"
    assert set(model["works"][0]["location_scope_member_ids"]) == {
        row["facility_id"] for row in model["facilities"]
    }
    assert "всем установленным сооружениям" in model["works"][0]["status"]


def test_repeated_equipment_model_does_not_enter_generic_facility_hierarchy() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-equipment-model",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=[],
        identity_components=[
            {
                "identity_candidate_id": "equipment",
                "identity_kind": "facility",
                "canonical_label": "КНС-270/12С/3,0-9,1/4,82",
                "candidate_labels": ["КНС-270/12С/3,0-9,1/4,82"],
                "member_structure_node_ids": ["equipment-rd", "equipment-spec"],
                "source_locator_ids": ["equipment-rd-locator", "equipment-spec-locator"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert model["facilities"] == []


def test_equipment_model_does_not_hide_reconciled_project_structure() -> None:
    model = build_project_engineering_model(
        workspace_id="workspace-equipment-and-structure",
        project_definition={"definition": {"fields": {}}},
        candidates={"project_fields": [], "work_types": [], "quantities": [], "materials": []},
        structure_nodes=[],
        identity_components=[
            {
                "identity_candidate_id": "equipment",
                "identity_kind": "facility",
                "canonical_label": "КНС-270/12С/3,0-9,1/4,82",
                "candidate_labels": ["КНС-270/12С/3,0-9,1/4,82"],
                "member_structure_node_ids": ["equipment-rd", "equipment-spec"],
                "source_locator_ids": ["equipment-rd-locator", "equipment-spec-locator"],
            },
            {
                "identity_candidate_id": "structure",
                "identity_kind": "structure",
                "canonical_label": "Берегоукрепительное сооружение",
                "candidate_labels": ["Берегоукрепительное сооружение"],
                "member_structure_node_ids": ["structure-rd", "structure-pz"],
                "source_locator_ids": ["structure-rd-locator", "structure-pz-locator"],
            },
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={},
    )

    assert [(row["name"], row["kind"]) for row in model["facilities"]] == [
        ("Берегоукрепительное сооружение", "Конструкция")
    ]


def test_generic_project_location_is_available_to_bounded_work_resolution() -> None:
    components = [
        {
            "identity_candidate_id": "retaining-structure",
            "identity_kind": "structure",
            "canonical_label": "Берегоукрепительное сооружение",
            "candidate_labels": ["Берегоукрепительное сооружение"],
            "member_structure_node_ids": ["structure-rd", "structure-pz"],
            "source_locator_ids": ["structure-rd-locator", "structure-pz-locator"],
        }
    ]
    facilities = established_facility_designations(components)

    assert facilities == ("Берегоукрепительное сооружение",)
    assert mentioned_established_facilities(
        "Армирование берегоукрепительного сооружения", facilities
    ) == ("Берегоукрепительное сооружение",)

    model = build_project_engineering_model(
        workspace_id="workspace-generic-location-work",
        project_definition={"definition": {"fields": {}}},
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "reinforcement",
                    "version": 1,
                    "value": "Установка арматурных каркасов",
                    "source_version_id": "work-source",
                    "source_locator_id": "work-locator",
                    "source_role": "working_documentation",
                }
            ],
            "quantities": [],
            "materials": [],
        },
        structure_nodes=[],
        identity_components=components,
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context=dict([_source("work-locator", "КР.pdf", 7)]),
        work_resolutions={
            "reinforcement": {
                "candidate_version": 1,
                "status": "MATCHED",
                "family_key": "reinforcement",
                "operation": "Армирование",
                "facility": "Берегоукрепительное сооружение",
                "confidence": "0.92",
                "reason": "Сооружение явно указано в контексте работы.",
            }
        },
    )

    assert model["works"][0]["facility"] == "Берегоукрепительное сооружение"
    assert model["works"][0]["status"].startswith("Сооружение установлено локальной моделью")


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
    assert model["issues"][0]["finding_kind"] == "QUANTITY_MISMATCH"
    assert model["issues"][0]["kind"] == "Расхождение объёмов"
    assert all(item["issue_id"] != "technical" for item in model["issues"])
    assert model["customer_questions"][0]["question"].startswith(
        "Просим включить недостающий объём 77 т"
    )


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


def test_identical_vor_and_estimate_difference_is_one_professional_issue() -> None:
    comparisons = [
        _comparison_row(
            {
                "work_scope_id": "cable-kns-8-1",
                "facility": "КНС 8.1",
                "work_name": "Прокладка кабеля",
                "source_locator_ids": ["design", "vor"],
            },
            "ПД",
            "ВОР",
            (Decimal("30"), "м"),
            (Decimal("60"), "м"),
            Decimal("-30"),
            "Разница ПД ↔ ВОР: -30 м",
        ),
        _comparison_row(
            {
                "work_scope_id": "cable-kns-8-1",
                "facility": "КНС 8.1",
                "work_name": "Прокладка кабеля",
                "source_locator_ids": ["design", "estimate"],
            },
            "ПД",
            "Смета",
            (Decimal("30"), "м"),
            (Decimal("60"), "м"),
            Decimal("-30"),
            "Разница ПД ↔ Смета: -30 м",
        ),
    ]

    issues = _issues(
        defects=[],
        comparisons=comparisons,
        scope_comparisons=[],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )

    assert len(comparisons) == 2
    assert len(issues) == 1
    assert issues[0]["description"] == (
        "ПД: 30 м; ВОР/Смета: 60 м. Коммерческий объём превышает проектный на 30 м."
    )
    assert "лишний коммерческий объём 30 м" in issues[0]["practical_consequence"]
    assert "проектное основание объёма 60 м" in issues[0]["recommended_action"]
    assert issues[0]["source_locator_ids"] == ["design", "estimate", "vor"]


def test_design_quantity_above_commercial_is_described_as_unpriced_scope() -> None:
    comparison = _comparison_row(
        {
            "work_scope_id": "sheet-pile-los-4",
            "facility": "ЛОС 4",
            "work_name": "Погружение шпунта",
            "source_locator_ids": ["design", "vor"],
        },
        "РД",
        "ВОР",
        (Decimal("438"), "т"),
        (Decimal("361"), "т"),
        Decimal("77"),
        "Разница РД ↔ ВОР: 77 т",
    )

    issue = _issues(
        defects=[],
        comparisons=[comparison],
        scope_comparisons=[],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )[0]

    assert issue["description"] == (
        "РД: 438 т; ВОР: 361 т. В коммерческих документах учтено на 77 т меньше, чем в проекте."
    )
    assert "может остаться нерасценённым" in issue["practical_consequence"]
    assert "включить недостающий объём 77 т" in issue["recommended_action"]


def test_vor_estimate_difference_is_not_described_as_project_difference() -> None:
    comparison = _comparison_row(
        {
            "work_scope_id": "commercial-excavation",
            "facility": "ЛОС 4",
            "work_name": "Разработка котлована",
            "source_locator_ids": ["vor", "estimate"],
        },
        "ВОР",
        "Смета",
        (Decimal("174.0204"), "м3"),
        (Decimal("4.365"), "м3"),
        Decimal("169.6554"),
        "Разница ВОР ↔ Смета: 169.6554 м3",
    )

    issue = _issues(
        defects=[],
        comparisons=[comparison],
        scope_comparisons=[],
        sheet_pile_schedule=[],
        works=[],
        source_context={},
    )[0]

    assert issue["description"] == (
        "ВОР: 174.0204 м3; Смета: 4.365 м3. В смете учтено на 169.6554 м3 меньше, чем в ВОР."
    )
    assert "между коммерческими документами" in issue["practical_consequence"]
    assert "привести ВОР и смету к одному значению" in issue["recommended_action"]
    assert "проект" not in issue["description"].casefold()


def test_unassigned_comparison_requires_one_source_context_per_side() -> None:
    comparison = {
        "left": {"document_role": "ПД"},
        "right": {"document_role": "Смета"},
    }
    isolated = {
        "sources_by_document": {"ПД": [{"page": 1}], "Смета": [{"page": 2}]},
        "project_wording_by_document": {
            "ПД": ["Разработка котлована"],
            "Смета": ["Разработка котлована"],
        },
    }
    project_wide = {
        **isolated,
        "sources_by_document": {
            "ПД": [{"page": 1}, {"page": 17}],
            "Смета": [{"page": 2}],
        },
    }

    assert _isolated_unassigned_comparison(isolated, comparison)
    assert not _isolated_unassigned_comparison(project_wide, comparison)
    assert not _isolated_unassigned_comparison(
        isolated,
        {"left": {"document_role": "ВОР"}, "right": {"document_role": "Смета"}},
    )


def test_concrete_material_comparison_is_scoped_by_facility_work_and_strength_class() -> None:
    source_context = dict(
        [
            _source("design-concrete", "КР.pdf", 14),
            _source("commercial-concrete", "ВОР.pdf", 21),
        ]
    )
    comparisons = _material_comparisons(
        [
            {
                "work_scope_id": "scope-17",
                "facility_id": "facility-17",
                "facility": "Участок 17",
                "work_name": "Железобетонные конструкции",
                "materials_by_document": {
                    "РД": [
                        {
                            "name": "Бетон кл. В25, F200, W6",
                            "source_locator_id": "design-concrete",
                        }
                    ],
                    "ВОР": [
                        {
                            "name": "Смесь бетонная, класс В25, F(1)150, W6",
                            "source_locator_id": "commercial-concrete",
                        }
                    ],
                },
            }
        ],
        source_context,
    )

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison["classification"] == "MATERIAL_DIFFERENCE"
    assert comparison["facility"] == "Участок 17"
    assert comparison["material"] == "Бетон В25"
    assert "F200" in comparison["description"]
    assert "F150" in comparison["description"]
    assert "W6" not in comparison["description"]
    assert comparison["source_locator_ids"] == [
        "commercial-concrete",
        "design-concrete",
    ]


def test_unassigned_exact_material_match_requires_isolated_source_rows() -> None:
    source_context = dict(
        [
            _source("design-a", "Design A.pdf", 3),
            _source("design-b", "Design B.pdf", 7),
            _source("commercial", "Commercial schedule.pdf", 2),
        ]
    )
    base_work = {
        "work_scope_id": "unassigned-drainage",
        "facility_id": None,
        "facility": "Location unresolved",
        "work_name": "Drainage bedding",
    }

    isolated = _material_comparisons(
        [
            {
                **base_work,
                "materials_by_document": {
                    "РД": [{"name": "Washed gravel", "source_locator_id": "design-a"}],
                    "ВОР": [{"name": "Washed gravel", "source_locator_id": "commercial"}],
                },
            }
        ],
        source_context,
    )
    assert len(isolated) == 1
    assert isolated[0]["classification"] == "MATERIAL_MATCH"

    aggregated = _material_comparisons(
        [
            {
                **base_work,
                "materials_by_document": {
                    "РД": [
                        {"name": "Washed gravel", "source_locator_id": "design-a"},
                        {"name": "Washed gravel", "source_locator_id": "design-b"},
                    ],
                    "ВОР": [{"name": "Washed gravel", "source_locator_id": "commercial"}],
                },
            }
        ],
        source_context,
    )
    assert aggregated == []


def test_semantic_material_resource_comparison_survives_non_work_source_rows() -> None:
    source_context = dict(
        [
            _source("design-membrane", "R14_materials.pdf", 3),
            _source("commercial-membrane", "C22_offer.pdf", 5),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "location_scope_id": "project:test",
                "facility": "Project scope",
                "work": "Waterproofing",
                "document_role": "Спецификация",
                "name": "Polymer membrane",
                "material_kind": "polymer membrane",
                "associated_work_family_key": "waterproofing",
                "properties": [{"kind": "THICKNESS", "value": "2.4", "unit": "mm"}],
                "source_locator_id": "design-membrane",
            },
            {
                "location_scope_id": "project:test",
                "facility": "Project scope",
                "work": "Waterproofing",
                "document_role": "ВОР",
                "name": "Polymer membrane",
                "material_kind": "polymer membrane",
                "associated_work_family_key": "waterproofing",
                "properties": [{"kind": "THICKNESS", "value": "1.8", "unit": "mm"}],
                "source_locator_id": "commercial-membrane",
            },
            {
                "location_scope_id": "project:test",
                "facility": "Project scope",
                "work": "Primer application",
                "document_role": "ВОР",
                "name": "Primer",
                "material_kind": "primer",
                "associated_work_family_key": "waterproofing",
                "properties": [{"kind": "TYPE", "value": "epoxy", "unit": None}],
                "source_locator_id": "commercial-membrane",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATERIAL_DIFFERENCE"
    assert comparisons[0]["property_differences"] == [
        {"property": "THICKNESS", "design": ["2.4 mm"], "commercial": ["1.8 mm"]}
    ]
    assert "2.4 mm" in comparisons[0]["description"]
    assert "1.8 mm" in comparisons[0]["description"]


def test_contract_estimate_material_participates_in_design_comparison() -> None:
    source_context = dict(
        [
            _source("design-pipe", "Hydraulic design.pdf", 11),
            _source("contract-estimate-pipe", "Commercial schedule.docx", 4),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "location_scope_id": "facility:z17",
                "facility": "Facility Z-17",
                "work": "Install drainage pipe",
                "document_role": "ПД",
                "name": "Drainage pipe",
                "material_kind": "pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "160", "unit": "mm"}],
                "source_locator_id": "design-pipe",
            },
            {
                "location_scope_id": "facility:z17",
                "facility": "Facility Z-17",
                "work": "Install drainage pipe",
                "document_role": "Смета контракта",
                "name": "Drainage pipe",
                "material_kind": "pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "225", "unit": "mm"}],
                "source_locator_id": "contract-estimate-pipe",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATERIAL_DIFFERENCE"
    assert comparisons[0]["commercial_roles"] == ["Смета контракта"]
    assert comparisons[0]["property_differences"] == [
        {"property": "DIAMETER", "design": ["160 mm"], "commercial": ["225 mm"]}
    ]


def test_pipe_diameter_comparison_does_not_treat_wall_thickness_as_diameter() -> None:
    source_context = dict(
        [
            _source("design-pipe", "Utility design.pdf", 7),
            _source("commercial-pipe", "Quantity schedule.pdf", 2),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "location_scope_id": "facility:q42",
                "facility": "Utility crossing Q-42",
                "work": "Install carrier pipe",
                "document_role": "РД",
                "name": "Polyethylene pipe 273x8.0",
                "material_kind": "pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "273x8,0", "unit": None}],
                "source_locator_id": "design-pipe",
            },
            {
                "location_scope_id": "facility:q42",
                "facility": "Utility crossing Q-42",
                "work": "Install carrier pipe",
                "document_role": "ВОР",
                "name": "Polyethylene pipe DN 273",
                "material_kind": "pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "273", "unit": "мм"}],
                "source_locator_id": "commercial-pipe",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATERIAL_SCOPE_UNRESOLVED"
    assert comparisons[0]["property_differences"] == []
    assert comparisons[0]["missing_commercial_properties"] == [
        {"property": "THICKNESS", "design": ["8 mm"]}
    ]
    assert "не указано" in comparisons[0]["description"]


def test_pipe_composite_designation_still_detects_different_diameter() -> None:
    source_context = dict(
        [
            _source("design-pipe", "Utility design.pdf", 7),
            _source("commercial-pipe", "Quantity schedule.pdf", 2),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "location_scope_id": "facility:q43",
                "facility": "Utility crossing Q-43",
                "work": "Install carrier pipe",
                "document_role": "РД",
                "name": "Steel pipe 273x8",
                "material_kind": "steel pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "273×8", "unit": None}],
                "source_locator_id": "design-pipe",
            },
            {
                "location_scope_id": "facility:q43",
                "facility": "Utility crossing Q-43",
                "work": "Install carrier pipe",
                "document_role": "Смета",
                "name": "Steel pipe DN 325",
                "material_kind": "steel pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "325", "unit": "mm"}],
                "source_locator_id": "commercial-pipe",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["property_differences"] == [
        {"property": "DIAMETER", "design": ["273 mm"], "commercial": ["325 mm"]}
    ]


def test_non_pipe_composite_dimension_is_not_reinterpreted_as_pipe_diameter() -> None:
    source_context = dict(
        [
            _source("design-profile", "Steel design.pdf", 9),
            _source("commercial-profile", "Steel schedule.pdf", 3),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "location_scope_id": "facility:s8",
                "facility": "Steel frame S-8",
                "work": "Install steel framing",
                "document_role": "РД",
                "name": "Rectangular section 200x100",
                "material_kind": "rectangular steel section",
                "associated_work_family_key": "structural_steel",
                "properties": [{"kind": "DIAMETER", "value": "200x100", "unit": "mm"}],
                "source_locator_id": "design-profile",
            },
            {
                "location_scope_id": "facility:s8",
                "facility": "Steel frame S-8",
                "work": "Install steel framing",
                "document_role": "ВОР",
                "name": "Steel section 200",
                "material_kind": "rectangular steel section",
                "associated_work_family_key": "structural_steel",
                "properties": [{"kind": "DIAMETER", "value": "200", "unit": "mm"}],
                "source_locator_id": "commercial-profile",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["property_differences"] == [
        {"property": "DIAMETER", "design": ["200x100 mm"], "commercial": ["200 mm"]}
    ]


def test_project_level_material_comparison_requires_isolated_sources() -> None:
    source_context = dict(
        [
            _source("design-a", "Specification.pdf", 3),
            _source("design-b", "Specification.pdf", 8),
            _source("commercial", "Offer.pdf", 5),
        ]
    )

    isolated = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "document_role": "Спецификация",
                "name": "Mineral wool",
                "material_kind": "mineral wool",
                "associated_work_family_key": "thermal_insulation",
                "properties": [{"kind": "THICKNESS", "value": "150", "unit": "mm"}],
                "source_locator_id": "design-a",
            },
            {
                "document_role": "ВОР",
                "name": "Mineral wool",
                "material_kind": "mineral wool",
                "associated_work_family_key": "thermal_insulation",
                "properties": [{"kind": "THICKNESS", "value": "120", "unit": "mm"}],
                "source_locator_id": "commercial",
            },
        ],
    )
    assert len(isolated) == 1

    ambiguous = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "document_role": "Спецификация",
                "name": "Mineral wool",
                "material_kind": "mineral wool",
                "associated_work_family_key": "thermal_insulation",
                "properties": [{"kind": "THICKNESS", "value": "150", "unit": "mm"}],
                "source_locator_id": "design-a",
            },
            {
                "document_role": "Спецификация",
                "name": "Mineral wool",
                "material_kind": "mineral wool",
                "associated_work_family_key": "thermal_insulation",
                "properties": [{"kind": "THICKNESS", "value": "80", "unit": "mm"}],
                "source_locator_id": "design-b",
            },
            {
                "document_role": "ВОР",
                "name": "Mineral wool",
                "material_kind": "mineral wool",
                "associated_work_family_key": "thermal_insulation",
                "properties": [{"kind": "THICKNESS", "value": "120", "unit": "mm"}],
                "source_locator_id": "commercial",
            },
        ],
    )
    assert ambiguous == []


def test_unresolved_material_kind_does_not_merge_different_material_items() -> None:
    source_context = dict(
        [
            _source("design-carrier", "Pipeline design.pdf", 5),
            _source("commercial-sleeve", "Estimate.pdf", 8),
        ]
    )
    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "document_role": "ПД",
                "name": "Steel carrier pipe",
                "material_kind": "steel pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "530", "unit": "mm"}],
                "source_locator_id": "design-carrier",
            },
            {
                "document_role": "Смета",
                "name": "Steel wall sleeve",
                "material_kind": "steel pipe",
                "associated_work_family_key": "pipeline",
                "properties": [{"kind": "DIAMETER", "value": "100", "unit": "mm"}],
                "source_locator_id": "commercial-sleeve",
            },
        ],
    )

    assert comparisons == []


def test_project_material_comparison_collapses_repeated_same_page_assertion() -> None:
    source_context = {
        "design-east": {
            "source_version_id": "source-design",
            "document_version": 1,
            "safe_display_name": "Steel design.pdf",
            "locator_value": {"page": 6},
        },
        "design-west": {
            "source_version_id": "source-design",
            "document_version": 1,
            "safe_display_name": "Steel design.pdf",
            "locator_value": {"page": 6},
        },
        "commercial": {
            "source_version_id": "source-commercial",
            "document_version": 1,
            "safe_display_name": "Commercial scope.pdf",
            "locator_value": {"page": 2},
        },
    }
    common = {
        "material_kind": "structural steel",
        "associated_work_family_key": "structural_steel",
    }

    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                **common,
                "document_role": "РД",
                "name": "steel",
                "properties": [{"kind": "GRADE", "value": "S420", "unit": None}],
                "source_locator_id": "design-east",
            },
            {
                **common,
                "document_role": "РД",
                "name": "steel structures",
                "properties": [{"kind": "GRADE", "value": "S420", "unit": None}],
                "source_locator_id": "design-west",
            },
            {
                **common,
                "document_role": "ВОР",
                "name": "fabricated steel",
                "properties": [{"kind": "GRADE", "value": "S355", "unit": None}],
                "source_locator_id": "commercial",
            },
        ],
    )

    assert len(comparisons) == 1
    assert comparisons[0]["classification"] == "MATERIAL_DIFFERENCE"
    assert comparisons[0]["property_differences"] == [
        {"property": "GRADE", "design": ["S420"], "commercial": ["S355"]}
    ]


def test_project_material_comparison_keeps_distinct_same_page_properties_ambiguous() -> None:
    source_context = {
        "design-a": {
            "source_version_id": "source-design",
            "document_version": 1,
            "locator_value": {"page": 4},
        },
        "design-b": {
            "source_version_id": "source-design",
            "document_version": 1,
            "locator_value": {"page": 4},
        },
        "commercial": {
            "source_version_id": "source-commercial",
            "document_version": 1,
            "locator_value": {"page": 3},
        },
    }
    common = {
        "material_kind": "pipe",
        "associated_work_family_key": "pipeline",
    }

    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                **common,
                "document_role": "ПД",
                "name": "pipe A",
                "properties": [{"kind": "DIAMETER", "value": "160", "unit": "mm"}],
                "source_locator_id": "design-a",
            },
            {
                **common,
                "document_role": "ПД",
                "name": "pipe B",
                "properties": [{"kind": "DIAMETER", "value": "225", "unit": "mm"}],
                "source_locator_id": "design-b",
            },
            {
                **common,
                "document_role": "Смета",
                "name": "pipe",
                "properties": [{"kind": "DIAMETER", "value": "180", "unit": "mm"}],
                "source_locator_id": "commercial",
            },
        ],
    )

    assert comparisons == []


def test_material_comparison_deduplicates_same_source_pages_across_kind_aliases() -> None:
    source_context = {
        "design-a": {
            "source_version_id": "source-design",
            "document_version": 1,
            "locator_value": {"page": 8},
        },
        "design-b": {
            "source_version_id": "source-design",
            "document_version": 1,
            "locator_value": {"page": 8},
        },
        "specification": {
            "source_version_id": "source-specification",
            "document_version": 1,
            "locator_value": {"page": 2},
        },
        "commercial": {
            "source_version_id": "source-commercial",
            "document_version": 1,
            "locator_value": {"page": 3},
        },
    }

    comparisons = _material_comparisons(
        [],
        source_context,
        material_rows=[
            {
                "document_role": "РД",
                "name": "steel",
                "material_kind": "structural steel",
                "associated_work_family_key": "structural_steel",
                "work": "Steel erection",
                "properties": [{"kind": "GRADE", "value": "S460", "unit": None}],
                "source_locator_id": "design-a",
            },
            {
                "document_role": "РД",
                "name": "steelwork",
                "material_kind": "steelwork",
                "associated_work_family_key": "structural_steel",
                "work": "Steel erection",
                "properties": [{"kind": "GRADE", "value": "S460", "unit": None}],
                "source_locator_id": "design-b",
            },
            {
                "document_role": "Спецификация",
                "name": "steel",
                "material_kind": "structural steel",
                "associated_work_family_key": "structural_steel",
                "work": "Steel erection",
                "properties": [{"kind": "GRADE", "value": "S460", "unit": None}],
                "source_locator_id": "specification",
            },
            {
                "document_role": "ВОР",
                "name": "fabricated steel",
                "material_kind": "structural steel",
                "associated_work_family_key": "structural_steel",
                "work": "Steel erection",
                "properties": [{"kind": "GRADE", "value": "S355", "unit": None}],
                "source_locator_id": "commercial",
            },
            {
                "document_role": "ВОР",
                "name": "steel structures",
                "material_kind": "steelwork",
                "associated_work_family_key": "structural_steel",
                "work": "Steel erection",
                "properties": [{"kind": "GRADE", "value": "S355", "unit": None}],
                "source_locator_id": "commercial",
            },
        ],
    )

    assert len(comparisons) == 2
    assert {tuple(comparison["design_roles"]) for comparison in comparisons} == {
        ("РД",),
        ("Спецификация",),
    }


def test_non_work_material_resource_is_projected_into_material_schedule() -> None:
    source_context = dict([_source("material-row", "Specification R14.pdf", 3)])
    result = _work_schedule(
        [
            {
                "candidate_id": "work-material-row",
                "version": 1,
                "value": "Polymer membrane, thickness 2.4 mm",
                "label": "polymer membrane thickness 2.4 mm",
                "source_version_id": "source-material-row",
                "source_locator_id": "material-row",
                "source_role": "specification",
            }
        ],
        [
            {
                "candidate_id": "quantity-material-row",
                "work_candidate_id": "work-material-row",
                "normalized_value": "760",
                "normalized_unit": "m2",
                "source_locator_id": "material-row",
            }
        ],
        [
            {
                "candidate_id": "material-candidate-row",
                "work_candidate_id": "work-material-row",
                "name": "Polymer membrane, thickness 2.4 mm",
                "source_locator_id": "material-row",
            }
        ],
        [],
        {},
        [],
        source_context,
        {
            "work-material-row": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v18",
                "status": "NOT_A_WORK",
                "reason": "Material resource, not a construction operation.",
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "quantity-material-row",
                        "status": "RESOURCE_OR_RATE",
                        "semantic_scope": "Membrane area",
                        "quantity_type": "RESOURCE_OR_RATE",
                        "relation_kind": "NONE",
                        "related_quantity_candidate_ids": [],
                        "scope_compatibility": "INSUFFICIENT_INFORMATION",
                        "reason": "Material quantity.",
                    }
                ],
                "material_reviews": [
                    {
                        "material_name": "Polymer membrane",
                        "material_kind": "polymer membrane",
                        "associated_work_family_key": "waterproofing",
                        "properties": [{"kind": "THICKNESS", "value": "2.4", "unit": "mm"}],
                        "quantity_candidate_ids": ["quantity-material-row"],
                        "confidence": "0.94",
                        "reason": "Material and thickness are explicit.",
                    }
                ],
            }
        },
    )

    assert result["works"] == []
    assert result["classification"]["excluded_non_work_observation_count"] == 1
    assert len(result["materials"]) == 1
    assert result["materials"][0]["material_kind"] == "polymer membrane"
    assert result["materials"][0]["quantity"] == "760"
    assert result["materials"][0]["document_role"] == "Спецификация"


def test_natural_object_acted_on_is_not_projected_as_construction_material() -> None:
    materials = _semantic_material_values(
        [
            {
                "material_name": "деревья",
                "material_kind": "деревья",
                "associated_work_family_key": "site_preparation",
                "properties": [{"kind": "DIAMETER", "value": "14-18", "unit": "см"}],
                "quantity_candidate_ids": [],
                "confidence": "0.94",
                "reason": "Диаметр указан для вырубаемых деревьев.",
            }
        ],
        linked_quantities=[],
        source_locator_id="tree-felling-source",
        source_context={},
    )

    assert materials == []


def test_deterministic_material_row_is_preserved_without_becoming_work() -> None:
    source_context = dict([_source("material-row", "Estimate Q8.pdf", 6)])
    result = _work_schedule(
        [
            {
                "candidate_id": "material-as-work-row",
                "version": 1,
                "value": "Geotextile 420 g/m2",
                "label": "geotextile 420 g/m2",
                "source_version_id": "source-estimate-q8",
                "source_locator_id": "material-row",
                "source_role": "local_estimate",
            }
        ],
        [],
        [
            {
                "candidate_id": "material-q8",
                "work_candidate_id": "material-as-work-row",
                "value": "Geotextile 420 g/m2",
                "normalized_name": "geotextile",
                "normalized_value": "840",
                "normalized_unit": "m2",
                "source_locator_id": "material-row",
            }
        ],
        [],
        {},
        [],
        source_context,
        {},
    )

    assert result["works"] == []
    assert result["unclassified"] == []
    assert result["excluded"][0]["candidate_id"] == "material-as-work-row"
    assert "Материальная позиция" in result["excluded"][0]["exclusion_reason"]
    assert result["materials"] == [
        {
            "work_scope_id": None,
            "location_scope_id": None,
            "facility": "Место применения не установлено",
            "work": "Связанная работа требует уточнения",
            "document_role": "Смета",
            "name": "Geotextile 420 g/m2",
            "quantity": "840",
            "unit": "м2",
            "raw_unit": "m2",
            "source_locator_id": "material-row",
        }
    ]


def test_validated_semantic_work_wins_over_material_only_heuristic() -> None:
    source_context = dict([_source("scope-row", "Design section Q8.pdf", 9)])
    result = _work_schedule(
        [
            {
                "candidate_id": "validated-scope",
                "version": 1,
                "value": "Polymer membrane 2.0 mm",
                "label": "polymer membrane 2.0 mm",
                "source_version_id": "source-design-q8",
                "source_locator_id": "scope-row",
                "source_role": "working_documentation",
            }
        ],
        [],
        [
            {
                "candidate_id": "material-q8",
                "work_candidate_id": "validated-scope",
                "value": "Polymer membrane 2.0 mm",
                "normalized_name": "polymer membrane",
                "source_locator_id": "scope-row",
            }
        ],
        [],
        {},
        [],
        source_context,
        {
            "validated-scope": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v18",
                "status": "MATCHED",
                "family_key": "waterproofing",
                "operation": "Apply polymer waterproofing membrane",
                "facility": None,
            }
        },
    )

    assert len(result["works"]) == 1
    assert result["works"][0]["family_key"] == "waterproofing"
    assert result["unclassified"] == []
    assert result["excluded"] == []


def test_pit_groups_keep_explicit_counts_without_inventing_final_total() -> None:
    model = _model()
    group = model["pits"]["requires_clarification"][0]

    assert group["reason"].startswith("Указана группа котлованов без количества")
    assert model["pits"]["is_final"] is False
    assert "окончательное количество" in model["pits"]["professional_answer"]


def test_counted_well_pit_group_contributes_to_minimum_without_fabricated_members() -> None:
    source_context = dict([_source("pit-group", "ВОР.pdf", 12)])
    source_context["pit-group"].update(
        page_commercial_scope_header="ВОР 03-02. Строительство ЛОС 17",
    )
    facilities = [
        {
            "facility_id": "facility-17",
            "designation": "ЛОС 17",
            "name": "ЛОС 17",
        }
    ]

    result = _pits(
        {
            "candidate_pits": [
                {
                    "display_name": "Котлованы под колодцы D1800 (3 шт)",
                    "aliases": ["Котлованы под колодцы D1800 (3 шт)"],
                    "source_locator_ids": ["pit-group"],
                },
                {
                    "display_name": "Котлованы перехода",
                    "aliases": ["Котлованы перехода"],
                    "source_locator_ids": [],
                },
            ],
            "coverage": {"disposition_counts": {"ambiguous": 1}},
        },
        facilities,
        source_context,
    )

    assert result["established_count"] == 3
    assert result["named_established_count"] == 0
    assert result["counted_group_pit_count"] == 3
    assert len(result["established"]) == 1
    assert result["established"][0]["aggregate_count"] == 3
    assert result["established"][0]["related_facility"] == "ЛОС 17"
    assert result["unresolved_group_count"] == 1
    assert "поштучных марок" in result["professional_answer"]


def test_uncounted_pit_group_inherits_facility_from_matching_commercial_scope() -> None:
    source_context = dict(
        [
            _source("pit-group", "Сводный ВОР.pdf", 29),
            _source("estimate-heading", "Локальные сметы.pdf", 56),
        ]
    )
    source_context["pit-group"].update(
        page_commercial_scope_code="02-01-15",
        page_commercial_scope_header="ВОР 02-01-15",
    )
    source_context["estimate-heading"].update(
        page_commercial_scope_code="02-01-15",
        page_commercial_scope_header=(
            "Локальный сметный расчёт ЛСР 02-01-15. Строительство ЛОС 8.1"
        ),
    )
    facilities = [
        {
            "facility_id": "facility-8-1",
            "designation": "ЛОС 8.1",
            "name": "ЛОС 8.1",
        }
    ]

    result = _pits(
        {
            "candidate_pits": [
                {
                    "display_name": "Котлованы с креплениями инвентарными щитами",
                    "aliases": ["Котлованы с креплениями инвентарными щитами"],
                    "source_locator_ids": ["pit-group"],
                }
            ],
            "coverage": {"disposition_counts": {"ambiguous": 1}},
        },
        facilities,
        source_context,
    )

    assert result["established_count"] == 0
    assert result["unresolved_group_count"] == 1
    unresolved = result["requires_clarification"][0]
    assert unresolved["related_facility"] == "ЛОС 8.1"
    assert unresolved["reason"].startswith("Коммерческий раздел относится к ЛОС 8.1")


def test_uncounted_generic_pit_row_is_alias_of_unique_counted_group_in_same_scope() -> None:
    source_context = dict(
        [
            _source("counted", "Сводный ВОР.pdf", 20),
            _source("generic", "Сводный ВОР.pdf", 21),
        ]
    )
    for locator_id in ("counted", "generic"):
        source_context[locator_id].update(
            page_commercial_scope_code="02-01-17",
            page_commercial_scope_header="ВОР 02-01-17. Строительство ЛОС 7",
        )
    facilities = [
        {
            "facility_id": "facility-7",
            "designation": "ЛОС 7",
            "name": "ЛОС 7",
        }
    ]

    result = _pits(
        {
            "candidate_pits": [
                {
                    "display_name": "Котлованы под колодцы D2000 (1 шт)",
                    "aliases": ["Котлованы под колодцы D2000 (1 шт)"],
                    "source_locator_ids": ["counted"],
                },
                {
                    "display_name": "Котлованы под колодцы",
                    "aliases": ["Котлованы под колодцы"],
                    "source_locator_ids": ["generic"],
                },
            ],
            "coverage": {"disposition_counts": {"ambiguous": 1}},
        },
        facilities,
        source_context,
    )

    assert result["established_count"] == 1
    assert result["unresolved_group_count"] == 0
    assert result["is_final"] is True
    established = result["established"][0]
    assert established["aliases"] == [
        "Котлованы под колодцы",
        "Котлованы под колодцы D2000 (1 шт)",
    ]
    assert established["source_locator_ids"] == ["counted", "generic"]
    assert "повторное общее обозначение" in established["status"]


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
