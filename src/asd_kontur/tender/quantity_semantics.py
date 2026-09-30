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
    calculated_total: Decimal
    difference: Decimal
    classification: str


def evaluate_component_total(
    statements: Iterable[QuantityStatement],
    relationship: QuantityRelationship,
) -> ComponentTotalResult | None:
    """Verify an explicit model relationship; never infer one from similar numbers."""

    if (
        relationship.relation is not QuantityRelation.TOTAL_FOR
        or relationship.compatibility is not ScopeCompatibility.COMPONENT_VS_TOTAL
    ):
        return None
    by_id = {statement.statement_id: statement for statement in statements}
    total = by_id.get(relationship.subject_id)
    components = [by_id.get(component_id) for component_id in relationship.object_ids]
    if total is None or any(component is None for component in components):
        return None
    resolved_components = [component for component in components if component is not None]
    if total.quantity_type is not QuantityType.TOTAL:
        return None
    if any(
        component.quantity_type not in {QuantityType.COMPONENT, QuantityType.SUBTOTAL}
        for component in resolved_components
    ):
        return None
    if any(component.unit != total.unit for component in resolved_components):
        return None
    if any(
        total.project_entity is not None
        and component.project_entity is not None
        and component.project_entity != total.project_entity
        for component in resolved_components
    ):
        return None
    if any(
        total.work is not None and component.work is not None and component.work != total.work
        for component in resolved_components
    ):
        return None
    if any(
        total.material is not None
        and component.material is not None
        and component.material != total.material
        for component in resolved_components
    ):
        return None
    if any(
        total.revision is not None
        and component.revision is not None
        and component.revision != total.revision
        for component in resolved_components
    ):
        return None
    if any(
        total.source_role is not None
        and component.source_role is not None
        and component.source_role != total.source_role
        for component in resolved_components
    ):
        return None
    calculated = sum((component.value for component in resolved_components), Decimal("0"))
    difference = total.value - calculated
    return ComponentTotalResult(
        total_id=total.statement_id,
        component_ids=relationship.object_ids,
        unit=total.unit,
        stated_total=total.value,
        calculated_total=calculated,
        difference=difference,
        classification="MATCH" if difference == 0 else "COMPONENT_TOTAL_MISMATCH",
    )
