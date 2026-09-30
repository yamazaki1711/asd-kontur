"""Generic quantity scope and deterministic component/total arithmetic."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class QuantityRelation(StrEnum):
    COMPONENT_OF = "COMPONENT_OF"
    SUBTOTAL_OF = "SUBTOTAL_OF"
    TOTAL_FOR = "TOTAL_FOR"
    ALTERNATIVE_TO = "ALTERNATIVE_TO"
    DUPLICATE_OF = "DUPLICATE_OF"
    REVISION_OF = "REVISION_OF"
    INCOMPARABLE_TO = "INCOMPARABLE_TO"
    NONE = "NONE"


class ScopeCompatibility(StrEnum):
    SAME_SCOPE = "SAME_SCOPE"
    OVERLAPPING_SCOPE = "OVERLAPPING_SCOPE"
    COMPONENT_VS_TOTAL = "COMPONENT_VS_TOTAL"
    DIFFERENT_SCOPE = "DIFFERENT_SCOPE"
    ALTERNATIVE_DESIGN = "ALTERNATIVE_DESIGN"
    REVISION_DIFFERENCE = "REVISION_DIFFERENCE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


class QuantityType(StrEnum):
    TOTAL = "TOTAL"
    SUBTOTAL = "SUBTOTAL"
    COMPONENT = "COMPONENT"
    STANDALONE = "STANDALONE"
    DIMENSION = "DIMENSION"
    DURATION = "DURATION"
    RESOURCE_OR_RATE = "RESOURCE_OR_RATE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class QuantityStatement:
    statement_id: str
    value: Decimal
    unit: str
    semantic_scope: str
    quantity_type: QuantityType
    project_entity: str | None = None
    work: str | None = None
    material: str | None = None
    source_role: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        if not self.statement_id or not self.unit or not self.semantic_scope:
            raise ValueError("quantity statement requires identity, unit, and semantic scope")


@dataclass(frozen=True, slots=True)
class QuantityRelationship:
    subject_id: str
    relation: QuantityRelation
    object_ids: tuple[str, ...]
    compatibility: ScopeCompatibility

    def __post_init__(self) -> None:
        if not self.subject_id or not self.object_ids:
            raise ValueError("quantity relationship requires subject and objects")
        if self.subject_id in self.object_ids or len(set(self.object_ids)) != len(self.object_ids):
            raise ValueError("quantity relationship identities are invalid")


@dataclass(frozen=True, slots=True)
class ComponentTotalResult:
    total_id: str
    component_ids: tuple[str, ...]
    unit: str
    stated_total: Decimal
    calculated_total: Decimal | None
    difference: Decimal | None
    classification: str
    explanation: str


class ComponentTotalClassification(StrEnum):
    MATCH = "MATCH"
    ROUNDING_MATCH = "ROUNDING_MATCH"
    MISMATCH = "MISMATCH"
    INCOMPLETE_COMPONENT_SET = "INCOMPLETE_COMPONENT_SET"
    INCOMPATIBLE_SCOPE = "INCOMPATIBLE_SCOPE"


def assess_component_total(
    statements: Iterable[QuantityStatement],
    relationship: QuantityRelationship,
) -> ComponentTotalResult:
    """Return a typed deterministic assessment of one semantic relationship."""

    by_id = {statement.statement_id: statement for statement in statements}
    total = by_id.get(relationship.subject_id)
    components = [by_id.get(component_id) for component_id in relationship.object_ids]
    if total is None or any(component is None for component in components):
        return _component_result(
            total,
            relationship,
            ComponentTotalClassification.INCOMPLETE_COMPONENT_SET,
            "Not every statement referenced by the semantic relationship is available.",
        )
    resolved = [component for component in components if component is not None]
    if (
        relationship.relation is not QuantityRelation.TOTAL_FOR
        or relationship.compatibility is not ScopeCompatibility.COMPONENT_VS_TOTAL
        or total.quantity_type is not QuantityType.TOTAL
        or any(
            component.quantity_type not in {QuantityType.COMPONENT, QuantityType.SUBTOTAL}
            for component in resolved
        )
        or not _component_scope_is_compatible(total, resolved)
    ):
        return _component_result(
            total,
            relationship,
            ComponentTotalClassification.INCOMPATIBLE_SCOPE,
            "The semantic relationship, units, document role, revision, "
            "or engineering scope is incompatible.",
        )
    calculated = sum((component.value for component in resolved), Decimal("0"))
    difference = total.value - calculated
    if difference == 0:
        classification = ComponentTotalClassification.MATCH
    elif calculated.quantize(_reported_quantum(total.value)) == total.value:
        classification = ComponentTotalClassification.ROUNDING_MATCH
    else:
        classification = ComponentTotalClassification.MISMATCH
    return ComponentTotalResult(
        total_id=total.statement_id,
        component_ids=relationship.object_ids,
        unit=total.unit,
        stated_total=total.value,
        calculated_total=calculated,
        difference=difference,
        classification=classification.value,
        explanation="The arithmetic was evaluated with Decimal after semantic scope validation.",
    )


def evaluate_component_total(
    statements: Iterable[QuantityStatement],
    relationship: QuantityRelationship,
) -> ComponentTotalResult | None:
    """Verify an explicit model relationship; never infer one from similar numbers."""

    assessed = assess_component_total(statements, relationship)
    if assessed.classification in {
        ComponentTotalClassification.INCOMPLETE_COMPONENT_SET.value,
        ComponentTotalClassification.INCOMPATIBLE_SCOPE.value,
    }:
        return None
    if assessed.classification == ComponentTotalClassification.MISMATCH.value:
        return ComponentTotalResult(
            total_id=assessed.total_id,
            component_ids=assessed.component_ids,
            unit=assessed.unit,
            stated_total=assessed.stated_total,
            calculated_total=assessed.calculated_total,
            difference=assessed.difference,
            classification="COMPONENT_TOTAL_MISMATCH",
            explanation=assessed.explanation,
        )
    return assessed


def _component_scope_is_compatible(
    total: QuantityStatement,
    components: list[QuantityStatement],
) -> bool:
    if any(component.unit != total.unit for component in components):
        return False
    for attribute in ("project_entity", "work", "material", "revision", "source_role"):
        total_value = getattr(total, attribute)
        if any(
            total_value is not None
            and getattr(component, attribute) is not None
            and getattr(component, attribute) != total_value
            for component in components
        ):
            return False
    return True


def _component_result(
    total: QuantityStatement | None,
    relationship: QuantityRelationship,
    classification: ComponentTotalClassification,
    explanation: str,
) -> ComponentTotalResult:
    return ComponentTotalResult(
        total_id=relationship.subject_id,
        component_ids=relationship.object_ids,
        unit=total.unit if total else "",
        stated_total=total.value if total else Decimal("0"),
        calculated_total=None,
        difference=None,
        classification=classification.value,
        explanation=explanation,
    )


def _reported_quantum(value: Decimal) -> Decimal:
    """Return the decimal resolution explicitly reported by the stated total."""

    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("non-finite quantity total is invalid")
    return Decimal(1).scaleb(exponent)
