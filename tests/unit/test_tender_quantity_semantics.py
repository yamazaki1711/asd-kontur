# ruff: noqa: RUF001 -- Russian construction examples are intentional.

from __future__ import annotations

from decimal import Decimal

import pytest

from asd_kontur.tender.analysis_harness import (
    TenderAnalysisTask,
    TenderHarnessTaskInput,
    bounded_task_payload,
)
from asd_kontur.tender.quantity_semantics import (
    QuantityRelation,
    QuantityRelationship,
    QuantityStatement,
    QuantityType,
    ScopeCompatibility,
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
