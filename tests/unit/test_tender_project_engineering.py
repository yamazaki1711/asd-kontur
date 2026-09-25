# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

from asd_kontur.application_spine.postgres import _application_engineering_projection
from asd_kontur.tender.project_engineering import build_project_engineering_model


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
                "value": "Погружение шпунтовых свай КНС-2",
                "label": "погружение шпунтовых свай кнс 2",
                "source_version_id": "source-rd",
                "source_locator_id": "work-rd",
                "source_role": "working_documentation",
                "scope_key": "КНС-2",
            },
            {
                "candidate_id": "work-vor",
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
    )


def test_model_exposes_professional_project_pits_and_sheet_pile_schedule() -> None:
    model = _model()

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


def test_model_calculates_real_role_comparison_and_hides_technical_defects() -> None:
    model = _model()

    assert len(model["quantity_comparisons"]) == 1
    comparison = model["quantity_comparisons"][0]
    assert comparison["left"] == {"document_role": "РД", "value": "438", "unit": "т"}
    assert comparison["right"] == {"document_role": "ВОР", "value": "361", "unit": "т"}
    assert comparison["difference"] == "77"
    assert model["issues"][0]["kind"] == "Расхождение объёмов"
    assert all(item["issue_id"] != "technical" for item in model["issues"])
    assert model["customer_questions"][0]["question"].startswith("Запросить у Заказчика")


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
