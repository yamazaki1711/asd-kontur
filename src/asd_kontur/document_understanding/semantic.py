"""Deterministic classification and structured candidate extraction.

Filename and directory names never participate in the decisions below.  Model
classification may add candidates through the same schema, but cannot bypass
the exact EvidencePack membership validator.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from asd_kontur.domain import deterministic_uuid

from .models import (
    CLASSIFICATION_PROFILE_VERSION,
    PROJECT_EXTRACTION_PROFILE_VERSION,
    WORK_EXTRACTION_PROFILE_VERSION,
    CandidateDecision,
    DocumentRole,
    EstimatePositionCandidate,
    ExactLocator,
    LayoutElement,
    MappingStatus,
    MaterialCandidate,
    ProjectFieldCandidate,
    QuantityCandidate,
    ReconciliationDefect,
    ReconciliationDefectKind,
    RoleCandidate,
    RoleDecision,
    StructureNodeCandidate,
    StructureRelationshipCandidate,
    WorkTypeCandidate,
)

ROLE_SIGNALS: dict[DocumentRole, tuple[str, ...]] = {
    DocumentRole.EXPLANATORY_NOTE: (
        "пояснительная записка",
        "назначение объекта",
        "состав объекта",
        "основные технические показатели",
    ),
    DocumentRole.PROJECT_DOCUMENTATION: (
        "проектная документация",
        "раздел проектной документации",
        "проектные решения",
    ),
    DocumentRole.WORKING_DOCUMENTATION: (
        "рабочая документация",
        "рабочие чертежи",
        "комплект рабочих чертежей",
    ),
    DocumentRole.BILL_OF_QUANTITIES: (
        "ведомость объемов работ",
        "ведомость объёмов работ",
        "вид работ",
        "объем работ",
        "объём работ",
    ),
    DocumentRole.LOCAL_ESTIMATE: ("локальная смета", "локальный сметный расчет"),
    DocumentRole.OBJECT_ESTIMATE: ("объектная смета", "объектный сметный расчет"),
    DocumentRole.CONSOLIDATED_ESTIMATE: (
        "сводный сметный расчет",
        "сводная смета",
    ),
    DocumentRole.SPECIFICATION: (
        "спецификация оборудования",
        "спецификация материалов",
        "марка материала",
    ),
    DocumentRole.CONTRACT: ("договор строительного подряда", "предмет договора"),
    DocumentRole.CUSTOMER_REGULATION: ("регламент заказчика", "требования заказчика"),
    DocumentRole.NORMATIVE_REFERENCE_LIST: (
        "нормативные ссылки",
        "перечень нормативных документов",
        "гост",
        "сп ",
    ),
    DocumentRole.EXECUTIVE_DOCUMENTATION: (
        "исполнительная документация",
        "акт освидетельствования",
        "общий журнал работ",
    ),
    DocumentRole.DRAWING_OR_SCHEME: ("масштаб 1:", "экспликация", "условные обозначения"),
    DocumentRole.CORRESPONDENCE_ADMINISTRATIVE: (
        "исходящий номер",
        "служебная записка",
        "уважаемый",
    ),
}

FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "object_name": (
        re.compile(r"(?:наименование|название)\s+(?:объекта|окс)\s*[:—-]\s*(.+)", re.I),
    ),
    "purpose": (re.compile(r"назначение\s+(?:объекта|окс)\s*[:—-]\s*(.+)", re.I),),
    "location": (re.compile(r"(?:местоположение|адрес)\s+(?:объекта|окс)?\s*[:—-]\s*(.+)", re.I),),
    "object_composition": (re.compile(r"состав\s+(?:объекта|окс)\s*[:—-]\s*(.+)", re.I),),
    "object_parts": (re.compile(r"части\s+(?:объекта|окс)\s*[:—-]\s*(.+)", re.I),),
    "zones": (re.compile(r"(?:зоны|участки)\s+(?:работ)?\s*[:—-]\s*(.+)", re.I),),
    "levels": (re.compile(r"(?:уровни|отметки)\s*[:—-]\s*(.+)", re.I),),
    "work_fronts": (re.compile(r"фронты\s+работ\s*[:—-]\s*(.+)", re.I),),
    "work_dependencies": (re.compile(r"зависимости\s+работ\s*[:—-]\s*(.+)", re.I),),
    "construction_stage": (
        re.compile(r"(?:очередь|этап)\s+(?:строительства)?\s*[:—-]\s*(.+)", re.I),
    ),
    "responsibility_level_printed": (
        re.compile(r"уровень\s+ответственности\s*[:—-]\s*(.+)", re.I),
    ),
    "printed_class": (re.compile(r"класс\s*[:—-]\s*(.+)", re.I),),
    "printed_category": (re.compile(r"категория\s*[:—-]\s*(.+)", re.I),),
}

WORK_HEADERS = {
    "work": {"вид работ", "наименование работ", "работа", "описание работ"},
    "quantity": {"объем", "объём", "количество", "объем работ", "объём работ"},
    "unit": {"ед. изм.", "ед изм", "единица", "единица измерения"},
    "material": {"материал", "мтр", "наименование материала"},
    "material_quantity": {"количество материала", "объем материала", "объём материала"},
    "material_unit": {"ед. изм. материала", "единица материала"},
    "position": {"позиция", "шифр", "обоснование"},
}

UNIT_ALIASES = {
    "м2": "m2",
    "м²": "m2",
    "м3": "m3",
    "м³": "m3",
    "м": "m",
    "мм": "mm",
    "т": "t",
    "кг": "kg",
    "шт": "piece",
    "шт.": "piece",
}


@dataclass(frozen=True, slots=True)
class ClassificationBundle:
    candidates: tuple[RoleCandidate, ...]
    decisions: tuple[RoleDecision, ...]


@dataclass(frozen=True, slots=True)
class StructuredCandidates:
    project_fields: tuple[ProjectFieldCandidate, ...]
    works: tuple[WorkTypeCandidate, ...]
    quantities: tuple[QuantityCandidate, ...]
    materials: tuple[MaterialCandidate, ...]
    estimates: tuple[EstimatePositionCandidate, ...]
    defects: tuple[ReconciliationDefect, ...]
    structures: tuple[StructureNodeCandidate, ...] = ()
    structure_relationships: tuple[StructureRelationshipCandidate, ...] = ()


def classify_pages(elements: Iterable[LayoutElement]) -> ClassificationBundle:
    by_page: dict[int, list[LayoutElement]] = defaultdict(list)
    for element in elements:
        by_page[element.locator.page_number].append(element)
    candidates: list[RoleCandidate] = []
    decisions: list[RoleDecision] = []
    for page_number, page_elements in sorted(by_page.items()):
        text = " ".join(item.normalized_text.casefold() for item in page_elements)
        scores: list[tuple[DocumentRole, Decimal, tuple[str, ...]]] = []
        for role, phrases in ROLE_SIGNALS.items():
            matched = tuple(phrase for phrase in phrases if phrase in text)
            if matched:
                score = min(Decimal("0.99"), Decimal("0.55") + Decimal("0.12") * len(matched))
                scores.append((role, score, matched))
        if not scores:
            scores.append((DocumentRole.UNKNOWN, Decimal("1"), ("no_content_role_signal",)))
        selected = tuple(
            sorted(
                (item for item in scores if item[1] >= Decimal("0.67")),
                key=lambda item: (-item[1], item[0].value),
            )
        ) or (max(scores, key=lambda item: item[1]),)
        page_candidate_ids: list[UUID] = []
        locators = tuple(item.locator for item in page_elements[:8])
        if not locators:
            continue
        for role, score, signals in selected:
            candidate_id = deterministic_uuid(
                f"page-role:{locators[0].source_version_id}:{page_number}:{role.value}:"
                f"{CLASSIFICATION_PROFILE_VERSION}"
            )
            page_candidate_ids.append(candidate_id)
            candidates.append(
                RoleCandidate(
                    candidate_id,
                    role,
                    f"page:{page_number}",
                    score,
                    tuple(f"content:{signal}" for signal in signals),
                    locators,
                    CLASSIFICATION_PROFILE_VERSION,
                )
            )
        decision_id = deterministic_uuid(
            f"page-role-decision:{locators[0].source_version_id}:{page_number}:"
            f"{CLASSIFICATION_PROFILE_VERSION}"
        )
        decisions.append(
            RoleDecision(
                decision_id,
                1,
                f"page:{page_number}",
                tuple(item[0] for item in selected),
                tuple(page_candidate_ids),
                "deterministic_content_signals",
                CLASSIFICATION_PROFILE_VERSION,
                locators,
            )
        )
    return ClassificationBundle(tuple(candidates), tuple(decisions))


def extract_structured_candidates(
    elements: Iterable[LayoutElement], decisions: Iterable[RoleDecision]
) -> StructuredCandidates:
    values = tuple(elements)
    roles_by_page = {
        int(decision.scope.split(":", 1)[1]): decision.selected_roles for decision in decisions
    }
    fields = _extract_fields(values, roles_by_page)
    works, quantities, materials, estimates = _extract_rows(values, roles_by_page)
    defects = reconcile_sources(works, quantities, materials, estimates)
    return StructuredCandidates(fields, works, quantities, materials, estimates, defects)


def _extract_fields(
    elements: tuple[LayoutElement, ...], roles_by_page: dict[int, tuple[DocumentRole, ...]]
) -> tuple[ProjectFieldCandidate, ...]:
    fields: list[ProjectFieldCandidate] = []
    for element in elements:
        roles = roles_by_page.get(element.locator.page_number, ())
        if not set(roles).intersection(
            {DocumentRole.EXPLANATORY_NOTE, DocumentRole.PROJECT_DOCUMENTATION}
        ):
            continue
        for key, patterns in FIELD_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(element.raw_text)
                if match is None:
                    continue
                raw = match.group(1).strip()
                candidate_id = deterministic_uuid(
                    f"project-field:{element.locator.source_version_id}:{element.locator.source_locator_id}:"
                    f"{key}:{PROJECT_EXTRACTION_PROFILE_VERSION}"
                )
                fields.append(
                    ProjectFieldCandidate(
                        candidate_id,
                        key,
                        raw,
                        " ".join(raw.split()),
                        "printed_text",
                        element.locator,
                        "native_or_qualified_ocr",
                        (),
                        CandidateDecision.VERIFIED,
                    )
                )
                break
    unique = {item.candidate_id: item for item in fields}
    return tuple(sorted(unique.values(), key=lambda item: (item.field_key, str(item.candidate_id))))


def _extract_rows(
    elements: tuple[LayoutElement, ...], roles_by_page: dict[int, tuple[DocumentRole, ...]]
) -> tuple[
    tuple[WorkTypeCandidate, ...],
    tuple[QuantityCandidate, ...],
    tuple[MaterialCandidate, ...],
    tuple[EstimatePositionCandidate, ...],
]:
    table_rows: dict[tuple[UUID, int, int], list[LayoutElement]] = defaultdict(list)
    for item in elements:
        if item.row_index is not None:
            table_rows[
                (item.locator.source_version_id, item.locator.page_number, item.row_index)
            ].append(item)
    by_page_rows: dict[tuple[UUID, int], list[list[LayoutElement]]] = defaultdict(list)
    for (source, page, _row), items in sorted(table_rows.items(), key=lambda pair: pair[0]):
        by_page_rows[(source, page)].append(sorted(items, key=lambda item: item.column_index or 0))
    works: list[WorkTypeCandidate] = []
    quantities: list[QuantityCandidate] = []
    materials: list[MaterialCandidate] = []
    estimates: list[EstimatePositionCandidate] = []
    for (_source, page), rows in by_page_rows.items():
        if not rows:
            continue
        roles = roles_by_page.get(page, ())
        header_index, header_map = _find_header(rows)
        if header_index is None or "work" not in header_map:
            continue
        for row in rows[header_index + 1 :]:
            cells = {item.column_index or 0: item for item in row}
            work_element = cells.get(header_map["work"])
            if work_element is None or not work_element.normalized_text:
                continue
            work_name = work_element.normalized_text
            source_role = _source_role(roles)
            work_id = deterministic_uuid(
                f"work-candidate:{work_element.locator.source_version_id}:"
                f"{work_element.locator.source_locator_id}:{WORK_EXTRACTION_PROFILE_VERSION}"
            )
            work = WorkTypeCandidate(
                work_id,
                work_element.raw_text,
                _normalize_semantic_name(work_name),
                "project",
                work_element.locator,
                source_role,
                MappingStatus.UNRESOLVED,
                None,
            )
            works.append(work)
            quantity_element = cells.get(header_map.get("quantity", -1))
            unit_element = cells.get(header_map.get("unit", -1))
            if quantity_element is not None:
                raw_unit = unit_element.raw_text.strip() if unit_element else ""
                parsed = parse_exact_decimal(quantity_element.raw_text)
                normalized_unit = UNIT_ALIASES.get(raw_unit.casefold())
                status = (
                    CandidateDecision.VERIFIED
                    if parsed is not None and normalized_unit is not None
                    else CandidateDecision.NEEDS_EVIDENCE
                )
                quantities.append(
                    QuantityCandidate(
                        deterministic_uuid(
                            f"quantity:{work_id}:{quantity_element.locator.source_locator_id}"
                        ),
                        work_id,
                        quantity_element.raw_text,
                        parsed,
                        raw_unit,
                        parsed,
                        normalized_unit,
                        "unit-normalization-v0.1" if normalized_unit else None,
                        "project",
                        quantity_element.locator,
                        status,
                    )
                )
            material_element = cells.get(header_map.get("material", -1))
            if material_element is not None and material_element.normalized_text:
                material_quantity_element = cells.get(header_map.get("material_quantity", -1))
                material_unit_element = cells.get(header_map.get("material_unit", -1))
                raw_quantity = (
                    material_quantity_element.raw_text if material_quantity_element else None
                )
                parsed_material = parse_exact_decimal(raw_quantity) if raw_quantity else None
                raw_material_unit = (
                    material_unit_element.raw_text if material_unit_element else None
                )
                normalized_material_unit = (
                    UNIT_ALIASES.get(raw_material_unit.casefold()) if raw_material_unit else None
                )
                material_status = (
                    CandidateDecision.VERIFIED
                    if raw_quantity is None
                    or (parsed_material is not None and normalized_material_unit is not None)
                    else CandidateDecision.NEEDS_EVIDENCE
                )
                materials.append(
                    MaterialCandidate(
                        deterministic_uuid(
                            f"material:{work_id}:{material_element.locator.source_locator_id}"
                        ),
                        work_id,
                        material_element.raw_text,
                        _normalize_semantic_name(material_element.normalized_text),
                        raw_quantity,
                        parsed_material,
                        raw_material_unit,
                        normalized_material_unit,
                        material_element.locator,
                        material_status,
                    )
                )
            if source_role in {
                DocumentRole.LOCAL_ESTIMATE,
                DocumentRole.OBJECT_ESTIMATE,
                DocumentRole.CONSOLIDATED_ESTIMATE,
            }:
                estimates.append(
                    EstimatePositionCandidate(
                        deterministic_uuid(f"estimate-position:{work_id}"),
                        cells.get(header_map.get("position", -1), work_element).raw_text,
                        _normalize_semantic_name(work_name),
                        quantity_element.raw_text if quantity_element else None,
                        parse_exact_decimal(quantity_element.raw_text)
                        if quantity_element
                        else None,
                        unit_element.raw_text if unit_element else None,
                        work_element.locator,
                    )
                )
    return tuple(works), tuple(quantities), tuple(materials), tuple(estimates)


def reconcile_sources(
    works: tuple[WorkTypeCandidate, ...],
    quantities: tuple[QuantityCandidate, ...],
    materials: tuple[MaterialCandidate, ...],
    estimates: tuple[EstimatePositionCandidate, ...],
) -> tuple[ReconciliationDefect, ...]:
    project_works = [
        item
        for item in works
        if item.source_role
        not in {
            DocumentRole.LOCAL_ESTIMATE,
            DocumentRole.OBJECT_ESTIMATE,
            DocumentRole.CONSOLIDATED_ESTIMATE,
        }
    ]
    project_works_by_name: dict[str, list[WorkTypeCandidate]] = defaultdict(list)
    for work in project_works:
        project_works_by_name[work.normalized_name].append(work)
    estimates_by_name: dict[str, list[EstimatePositionCandidate]] = defaultdict(list)
    for estimate in estimates:
        estimates_by_name[estimate.normalized_description].append(estimate)
    quantities_by_work: dict[UUID, list[QuantityCandidate]] = defaultdict(list)
    for quantity_candidate in quantities:
        quantities_by_work[quantity_candidate.work_candidate_id].append(quantity_candidate)
    materials_by_work: dict[UUID, list[MaterialCandidate]] = defaultdict(list)
    for item in materials:
        materials_by_work[item.work_candidate_id].append(item)
    estimate_roles = {
        DocumentRole.LOCAL_ESTIMATE,
        DocumentRole.OBJECT_ESTIMATE,
        DocumentRole.CONSOLIDATED_ESTIMATE,
    }
    estimate_work_by_locator: dict[tuple[UUID, str], list[WorkTypeCandidate]] = defaultdict(list)
    for work in works:
        if work.source_role in estimate_roles:
            estimate_work_by_locator[(work.locator.source_locator_id, work.normalized_name)].append(
                work
            )
    defects: list[ReconciliationDefect] = []
    matched_estimates: set[UUID] = set()
    ambiguous_estimates: set[UUID] = set()
    if project_works and not estimates:
        first = min(project_works, key=lambda item: str(item.candidate_id))
        defects.append(
            _defect(
                ReconciliationDefectKind.ESTIMATE_COMPARISON_INPUT_UNAVAILABLE,
                "project_estimate_comparison",
                None,
                (first.locator,),
                {
                    "missing_input": "parsed_estimate_or_bill_of_quantities_positions",
                    "consequence": "project_work_omissions_and_quantity_deltas_not_evaluated",
                },
            )
        )
        return tuple(defects)
    for normalized_name, works_with_name in sorted(project_works_by_name.items()):
        matched = estimates_by_name.get(normalized_name, [])
        if not matched:
            for work in works_with_name:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.PROJECT_WORK_MISSING_IN_ESTIMATE,
                        str(work.candidate_id),
                        None,
                        (work.locator,),
                        {"work": work.raw_name},
                    )
                )
            continue

        # A label is not an identity.  A one-to-one normalized-name match is
        # usable only when each side has exactly one observation.  In
        # particular, two same-named works in different local scopes must not
        # both inherit the quantity or material basis of one estimate row.
        if len(works_with_name) != 1 or len(matched) != 1:
            ambiguous_estimates.update(item.candidate_id for item in matched)
            code = (
                "multiple_project_work_observations_with_same_normalized_name"
                if len(works_with_name) != 1
                else "multiple_estimate_positions_with_same_normalized_description"
            )
            for work in works_with_name:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
                        str(work.candidate_id),
                        str(matched[0].candidate_id) if len(matched) == 1 else None,
                        (
                            *(item.locator for item in works_with_name),
                            *(item.locator for item in matched),
                        ),
                        {"code": code, "work": work.raw_name},
                    )
                )
            continue

        work = works_with_name[0]
        estimate = matched[0]
        matched_estimates.add(estimate.candidate_id)
        work_quantities = quantities_by_work.get(work.candidate_id, [])
        quantity: QuantityCandidate | None = (
            work_quantities[0] if len(work_quantities) == 1 else None
        )
        if len(work_quantities) > 1:
            defects.append(
                _defect(
                    ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
                    str(work.candidate_id),
                    str(estimate.candidate_id),
                    (work.locator, *(item.locator for item in work_quantities), estimate.locator),
                    {
                        "code": "multiple_quantity_observations_for_work",
                        "work": work.raw_name,
                    },
                )
            )
        if quantity and quantity.parsed_value is not None and estimate.parsed_quantity is not None:
            estimate_unit = UNIT_ALIASES.get((estimate.raw_unit or "").casefold())
            if quantity.normalized_unit != estimate_unit:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.INCOMPATIBLE_UNITS,
                        str(quantity.candidate_id),
                        str(estimate.candidate_id),
                        (quantity.locator, estimate.locator),
                        {
                            "project_unit": quantity.raw_unit,
                            "estimate_unit": estimate.raw_unit or "",
                        },
                    )
                )
            elif quantity.parsed_value != estimate.parsed_quantity:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.QUANTITY_MISMATCH,
                        str(quantity.candidate_id),
                        str(estimate.candidate_id),
                        (quantity.locator, estimate.locator),
                        {
                            "project": str(quantity.parsed_value),
                            "estimate": str(estimate.parsed_quantity),
                            "unit": quantity.normalized_unit or "",
                        },
                    )
                )
        for material in materials_by_work.get(work.candidate_id, []):
            estimate_work_candidates = estimate_work_by_locator.get(
                (estimate.locator.source_locator_id, estimate.normalized_description), []
            )
            estimate_resources = (
                materials_by_work.get(estimate_work_candidates[0].candidate_id, [])
                if len(estimate_work_candidates) == 1
                else []
            )
            if not estimate_resources:
                # A work/quantity estimate row alone is not evidence about its
                # resources.  Keep this explicit rather than inventing a
                # material omission from the absence of a parsed resource row.
                defects.append(
                    _defect(
                        ReconciliationDefectKind.ESTIMATE_MATERIAL_COMPARISON_INPUT_UNAVAILABLE,
                        str(material.candidate_id),
                        str(estimate.candidate_id),
                        (material.locator, estimate.locator),
                        {
                            "material": material.raw_name,
                            "missing_input": "parsed_estimate_material_or_resource_positions",
                            "consequence": "project_material_scope_not_evaluated_against_estimate",
                        },
                    )
                )
                continue
            matching_resources = [
                resource
                for resource in estimate_resources
                if resource.normalized_name == material.normalized_name
            ]
            if not matching_resources:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.PROJECT_MATERIAL_MISSING_IN_ESTIMATE,
                        str(material.candidate_id),
                        str(estimate.candidate_id),
                        (material.locator, *(item.locator for item in estimate_resources)),
                        {"material": material.raw_name},
                    )
                )
                continue
            if len(matching_resources) > 1:
                defects.append(
                    _defect(
                        ReconciliationDefectKind.AMBIGUOUS_SOURCE_MATCH,
                        str(material.candidate_id),
                        str(estimate.candidate_id),
                        (material.locator, *(item.locator for item in matching_resources)),
                        {
                            "code": (
                                "multiple_estimate_material_resources_with_same_normalized_name"
                            ),
                            "material": material.raw_name,
                        },
                    )
                )
                continue
    for estimate in estimates:
        if (
            estimate.candidate_id not in matched_estimates
            and estimate.candidate_id not in ambiguous_estimates
        ):
            defects.append(
                _defect(
                    ReconciliationDefectKind.ESTIMATE_POSITION_UNSUPPORTED_BY_PROJECT,
                    str(estimate.candidate_id),
                    None,
                    (estimate.locator,),
                    {"position": estimate.raw_position},
                )
            )
    return tuple(sorted(defects, key=lambda item: str(item.defect_id)))


def parse_exact_decimal(raw: str) -> Decimal | None:
    value = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"[+-]?\d+(?:[,.]\d+)?", value):
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def _find_header(rows: list[list[LayoutElement]]) -> tuple[int | None, dict[str, int]]:
    for index, row in enumerate(rows[:20]):
        mapping: dict[str, int] = {}
        for item in row:
            normalized = _normalize_header(item.normalized_text)
            for key, aliases in WORK_HEADERS.items():
                if normalized in {_normalize_header(alias) for alias in aliases}:
                    mapping[key] = item.column_index or 0
        if "work" in mapping and ("quantity" in mapping or "material" in mapping):
            return index, mapping
    return None, {}


def _source_role(roles: tuple[DocumentRole, ...]) -> DocumentRole:
    preferred = (
        DocumentRole.LOCAL_ESTIMATE,
        DocumentRole.OBJECT_ESTIMATE,
        DocumentRole.CONSOLIDATED_ESTIMATE,
        DocumentRole.BILL_OF_QUANTITIES,
        DocumentRole.SPECIFICATION,
        DocumentRole.WORKING_DOCUMENTATION,
        DocumentRole.PROJECT_DOCUMENTATION,
    )
    return next((role for role in preferred if role in roles), DocumentRole.UNKNOWN)


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip(" .:—-")  # noqa: RUF001


def _normalize_semantic_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("ё", "е")).strip(" .:—-")  # noqa: RUF001


def _defect(
    kind: ReconciliationDefectKind,
    subject: str,
    related: str | None,
    locators: tuple[ExactLocator, ...],
    parameters: dict[str, str],
) -> ReconciliationDefect:
    identity = deterministic_uuid(f"reconciliation-defect:{kind.value}:{subject}:{related or '-'}")
    return ReconciliationDefect(identity, kind, subject, related, locators, parameters, True)
