# ruff: noqa: RUF001 -- Russian construction examples are intentional.

from __future__ import annotations

from decimal import Decimal

import pytest

from asd_kontur.tender.analysis_harness import (
    TenderAnalysisTask,
    TenderHarnessTaskInput,
    bounded_task_payload,
    validate_task_result,
)
from asd_kontur.tender.quantity_semantics import (
    ComponentTotalClassification,
    QuantityRelation,
    QuantityRelationship,
    QuantityStatement,
    QuantityType,
    ScopeCompatibility,
    assess_component_total,
    evaluate_component_total,
)


@pytest.mark.parametrize(
    ("scope", "unit", "values", "stated", "expected_difference"),
    [
        ("Монолитные конструкции корпуса А", "м3", ("100", "25"), "90", "-35"),
        ("Металлокаркас пролёта Б", "т", ("5.2", "3.1"), "7.0", "-1.3"),
        ("Участки водовода В", "м", ("120", "80"), "150", "-50"),
    ],
)
def test_component_total_is_generic_across_work_and_measure(
    scope: str,
    unit: str,
    values: tuple[str, str],
    stated: str,
    expected_difference: str,
) -> None:
    statements = [
        QuantityStatement(
            statement_id="total",
            value=Decimal(stated),
            unit=unit,
            semantic_scope=scope,
            quantity_type=QuantityType.TOTAL,
            project_entity="entity-a",
        ),
        *[
            QuantityStatement(
                statement_id=f"component-{index}",
                value=Decimal(value),
                unit=unit,
                semantic_scope=f"{scope}: часть {index}",
                quantity_type=QuantityType.COMPONENT,
                project_entity="entity-a",
            )
            for index, value in enumerate(values, start=1)
        ],
    ]
    relation = QuantityRelationship(
        subject_id="total",
        relation=QuantityRelation.TOTAL_FOR,
        object_ids=("component-1", "component-2"),
        compatibility=ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    result = evaluate_component_total(statements, relation)

    assert result is not None
    assert result.classification == "COMPONENT_TOTAL_MISMATCH"
    assert result.difference == Decimal(expected_difference)


def test_arithmetic_is_not_inferred_without_explicit_scope_relationship() -> None:
    statements = [
        QuantityStatement("a", Decimal("10"), "т", "Сталь", QuantityType.TOTAL),
        QuantityStatement("b", Decimal("4"), "т", "Арматура", QuantityType.COMPONENT),
        QuantityStatement("c", Decimal("6"), "т", "Шпунт", QuantityType.COMPONENT),
    ]
    relation = QuantityRelationship(
        subject_id="a",
        relation=QuantityRelation.INCOMPARABLE_TO,
        object_ids=("b", "c"),
        compatibility=ScopeCompatibility.DIFFERENT_SCOPE,
    )

    assert evaluate_component_total(statements, relation) is None


def test_component_total_rejects_incompatible_units_and_entities() -> None:
    statements = [
        QuantityStatement(
            "total", Decimal("10"), "т", "Общий объём", QuantityType.TOTAL, "facility-a"
        ),
        QuantityStatement(
            "component", Decimal("10"), "м3", "Часть", QuantityType.COMPONENT, "facility-b"
        ),
    ]
    relation = QuantityRelationship(
        subject_id="total",
        relation=QuantityRelation.TOTAL_FOR,
        object_ids=("component",),
        compatibility=ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    assert evaluate_component_total(statements, relation) is None


@pytest.mark.parametrize("dimension", ["work", "material", "revision"])
def test_component_total_rejects_conflicting_engineering_scope(dimension: str) -> None:
    shared = {
        "project_entity": "structure-a",
        "work": "reinforcement",
        "material": "A500C",
        "revision": "rev-2",
    }
    conflicting = dict(shared)
    conflicting[dimension] = f"different-{dimension}"
    statements = [
        QuantityStatement(
            "total",
            Decimal("10"),
            "т",
            "Общий объём",
            QuantityType.TOTAL,
            **shared,
        ),
        QuantityStatement(
            "component",
            Decimal("10"),
            "т",
            "Составляющая",
            QuantityType.COMPONENT,
            **conflicting,
        ),
    ]
    relation = QuantityRelationship(
        subject_id="total",
        relation=QuantityRelation.TOTAL_FOR,
        object_ids=("component",),
        compatibility=ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    assert evaluate_component_total(statements, relation) is None


def test_component_total_rejects_conflicting_explicit_diameters() -> None:
    statements = [
        QuantityStatement(
            "total",
            Decimal("109"),
            "м",
            "Демонтаж трубопровода",
            QuantityType.TOTAL,
            scope_qualifiers=("diameter:300mm",),
        ),
        QuantityStatement(
            "component",
            Decimal("1"),
            "м",
            "Демонтаж трубопровода",
            QuantityType.COMPONENT,
            scope_qualifiers=("diameter:50mm",),
        ),
    ]
    relation = QuantityRelationship(
        subject_id="total",
        relation=QuantityRelation.TOTAL_FOR,
        object_ids=("component",),
        compatibility=ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    assert evaluate_component_total(statements, relation) is None


def test_component_total_allows_explicit_cross_document_relationship() -> None:
    statements = [
        QuantityStatement(
            "total",
            Decimal("10"),
            "т",
            "Общий объём",
            QuantityType.TOTAL,
            project_entity="structure-a",
            source_role="working_documentation",
        ),
        QuantityStatement(
            "component",
            Decimal("10"),
            "т",
            "Составляющая",
            QuantityType.COMPONENT,
            project_entity="structure-a",
            source_role="bill_of_quantities",
        ),
    ]
    relation = QuantityRelationship(
        subject_id="total",
        relation=QuantityRelation.TOTAL_FOR,
        object_ids=("component",),
        compatibility=ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    result = evaluate_component_total(statements, relation)

    assert result is not None
    assert result.classification == "MATCH"


def test_component_total_reports_rounding_match_at_stated_precision() -> None:
    statements = [
        QuantityStatement("total", Decimal("10.0"), "м3", "Корпус", QuantityType.TOTAL),
        QuantityStatement("a", Decimal("4.96"), "м3", "Часть А", QuantityType.COMPONENT),
        QuantityStatement("b", Decimal("5.03"), "м3", "Часть Б", QuantityType.COMPONENT),
    ]
    relation = QuantityRelationship(
        "total",
        QuantityRelation.TOTAL_FOR,
        ("a", "b"),
        ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    result = assess_component_total(statements, relation)

    assert result.classification == ComponentTotalClassification.ROUNDING_MATCH
    assert result.calculated_total == Decimal("9.99")
    assert result.difference == Decimal("0.01")


def test_component_total_reports_incomplete_relationship_without_arithmetic() -> None:
    total = QuantityStatement("total", Decimal("200"), "м", "Сеть", QuantityType.TOTAL)
    relation = QuantityRelationship(
        "total",
        QuantityRelation.TOTAL_FOR,
        ("segment-a", "segment-b"),
        ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    result = assess_component_total([total], relation)

    assert result.classification == ComponentTotalClassification.INCOMPLETE_COMPONENT_SET
    assert result.calculated_total is None
    assert result.difference is None


@pytest.mark.parametrize(
    ("total_scope", "component_scope"),
    [
        (
            {"project_entity": "building-a", "work": "monolithic-concrete"},
            {"project_entity": "building-a", "work": "precast-concrete"},
        ),
        (
            {"project_entity": "revision-2", "revision": "2"},
            {"project_entity": "revision-2", "revision": "1"},
        ),
        (
            {"project_entity": "facility-a"},
            {"project_entity": "facility-b"},
        ),
    ],
)
def test_component_total_explains_false_positive_scope_rejection(
    total_scope: dict[str, str], component_scope: dict[str, str]
) -> None:
    statements = [
        QuantityStatement(
            "total", Decimal("10"), "м3", "Общий объём", QuantityType.TOTAL, **total_scope
        ),
        QuantityStatement(
            "part", Decimal("10"), "м3", "Часть", QuantityType.COMPONENT, **component_scope
        ),
    ]
    relationship = QuantityRelationship(
        "total",
        QuantityRelation.TOTAL_FOR,
        ("part",),
        ScopeCompatibility.COMPONENT_VS_TOTAL,
    )

    result = assess_component_total(statements, relationship)

    assert result.classification == ComponentTotalClassification.INCOMPATIBLE_SCOPE
    assert result.difference is None


def test_harness_payload_is_project_independent_and_bounded() -> None:
    payload = bounded_task_payload(
        TenderHarnessTaskInput(
            task=TenderAnalysisTask.QUANTITY_RELATIONSHIP_ANALYSIS,
            input_identity="batch-17",
            context={"statements": [{"id": "q-1", "text": "Общий объём"}]},
        )
    )

    assert '"task":"QUANTITY_RELATIONSHIP_ANALYSIS"' in payload
    assert '"input_identity":"batch-17"' in payload
    assert "OZERO" not in payload


def test_harness_rejects_silent_context_truncation() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        bounded_task_payload(
            TenderHarnessTaskInput(
                task=TenderAnalysisTask.PROJECT_ENTITY_EXTRACTION,
                input_identity="batch-18",
                context={"text": "x" * 1_500},
            ),
            max_chars=1_000,
        )


def test_harness_validates_shared_structured_result_envelope() -> None:
    task = TenderHarnessTaskInput(
        task=TenderAnalysisTask.STRUCTURE_RELATIONSHIP_RESOLUTION,
        input_identity="entities-7",
        context={"entities": ["a", "b"]},
    )

    result = validate_task_result(
        task,
        {
            "input_identity": "entities-7",
            "decision": "PROBABLE",
            "normalized_interpretation": {"relationship": "serves"},
            "relationships": [{"subject": "a", "object": "b"}],
            "confidence": "MODERATE",
            "ambiguity": "Designation is present on only one drawing.",
            "source_references": ["locator-a", "locator-b"],
        },
    )

    assert result["task"] == "STRUCTURE_RELATIONSHIP_RESOLUTION"
    assert result["decision"] == "PROBABLE"


def test_harness_rejects_ambiguous_result_without_explanation() -> None:
    task = TenderHarnessTaskInput(
        task=TenderAnalysisTask.CROSS_DOCUMENT_SCOPE_MATCHING,
        input_identity="scope-8",
        context={},
    )

    with pytest.raises(ValueError, match="requires an explanation"):
        validate_task_result(
            task,
            {
                "input_identity": "scope-8",
                "decision": "AMBIGUOUS",
                "normalized_interpretation": None,
                "confidence": "LOW",
                "source_references": ["locator-a"],
            },
        )
