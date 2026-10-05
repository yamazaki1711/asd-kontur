# ruff: noqa: RUF001 -- Russian construction examples are intentional.

from __future__ import annotations

from asd_kontur.tender.project_engineering import build_project_engineering_model


def test_unseen_bridge_corpus_uses_same_tender_pipeline_without_project_rules() -> None:
    facility = "Мостовой переход М-1"
    model = build_project_engineering_model(
        workspace_id="controlled-unseen-bridge-workspace",
        project_definition={
            "definition": {
                "fields": {
                    "object_name": {"normalized_value": "Реконструкция мостового перехода"},
                    "purpose": {"normalized_value": "Замена пролётного строения"},
                    "object_composition": {"normalized_value": facility},
                }
            }
        },
        candidates={
            "project_fields": [],
            "work_types": [
                {
                    "candidate_id": "design-piles",
                    "version": 1,
                    "value": "Устройство буронабивных свай опоры М-1",
                    "source_role": "working_documentation",
                    "source_version_id": "source-design",
                    "source_locator_id": "locator-design",
                },
                {
                    "candidate_id": "commercial-piles",
                    "version": 1,
                    "value": "Устройство буронабивных свай опоры М-1",
                    "source_role": "bill_of_quantities",
                    "source_version_id": "source-vor",
                    "source_locator_id": "locator-vor",
                },
            ],
            "quantities": [
                {
                    "candidate_id": "quantity-design",
                    "work_candidate_id": "design-piles",
                    "value": "36",
                    "unit": "шт",
                    "source_locator_id": "locator-design",
                },
                {
                    "candidate_id": "quantity-vor",
                    "work_candidate_id": "commercial-piles",
                    "value": "30",
                    "unit": "шт",
                    "source_locator_id": "locator-vor",
                },
            ],
            "materials": [],
        },
        structure_nodes=[
            {
                "structure_node_id": "node-design",
                "node_kind": "facility",
                "raw_name": facility,
                "source_version_id": "source-design",
                "source_locator_id": "locator-design",
            },
            {
                "structure_node_id": "node-vor",
                "node_kind": "facility",
                "raw_name": facility,
                "source_version_id": "source-vor",
                "source_locator_id": "locator-vor",
            },
        ],
        identity_components=[
            {
                "identity_candidate_id": "bridge-component",
                "identity_kind": "facility",
                "canonical_label": facility,
                "candidate_labels": [facility],
                "member_structure_node_ids": ["node-design", "node-vor"],
                "source_locator_ids": ["locator-design", "locator-vor"],
            }
        ],
        pit_inventory={"candidate_pits": [], "coverage": {}},
        defects=[],
        matrix={"matrix": {"rows": []}},
        normative_profile=None,
        source_context={
            "locator-design": {
                "safe_display_name": "BRG-17-KR.pdf",
                "document_version": 1,
                "source_version_id": "source-design",
                "locator_value": {"page": 14},
            },
            "locator-vor": {
                "safe_display_name": "Commercial-schedule-03.pdf",
                "document_version": 1,
                "source_version_id": "source-vor",
                "locator_value": {"page": 2},
                "page_is_bill_of_quantities": True,
            },
        },
        work_resolutions={
            "design-piles": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v9",
                "status": "MATCHED",
                "family_key": "pile_foundation",
                "operation": "Устройство буронабивных свай",
                "facility": facility,
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "quantity-design",
                        "status": "WORK_QUANTITY",
                        "semantic_scope": "Количество буронабивных свай опоры М-1",
                        "quantity_type": "STANDALONE",
                        "relation_kind": "NONE",
                        "related_quantity_candidate_ids": [],
                        "scope_compatibility": "SAME_SCOPE",
                        "reason": "Количество относится к указанной операции.",
                    }
                ],
            },
            "commercial-piles": {
                "candidate_version": 1,
                "profile_version": "qwen-project-work-reconciliation-v9",
                "status": "MATCHED",
                "family_key": "pile_foundation",
                "operation": "Устройство буронабивных свай",
                "facility": facility,
                "quantity_reviews": [
                    {
                        "quantity_candidate_id": "quantity-vor",
                        "status": "WORK_QUANTITY",
                        "semantic_scope": "Количество буронабивных свай опоры М-1",
                        "quantity_type": "STANDALONE",
                        "relation_kind": "NONE",
                        "related_quantity_candidate_ids": [],
                        "scope_compatibility": "SAME_SCOPE",
                        "reason": "Количество относится к указанной операции.",
                    }
                ],
            },
        },
    )

    assert model["project"]["name"]["value"] == "Реконструкция мостового перехода"
    assert [row["name"] for row in model["facilities"]] == [facility]
    assert model["works"][0]["work_family"] == "Свайные работы"
    assert model["quantity_comparisons"][0]["classification"] == "QUANTITY_DIFFERENCE"
    assert model["quantity_comparisons"][0]["difference"] == "6"
    assert model["issues"][0]["kind"] == "Расхождение объёмов"
