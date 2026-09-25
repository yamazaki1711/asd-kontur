"""Practical construction-project model and Tender analysis.

This module turns already persisted extraction observations into professional
project concepts.  It deliberately keeps implementation diagnostics out of the
normal result while retaining document/page references for inspection.
"""

# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

PROJECT_ENGINEERING_MODEL_VERSION = "project-engineering-model-v1"

_FACILITY_CODE = re.compile(
    r"\b(?P<kind>лос|кнс)\s*[-№nº]*\s*(?P<number>\d+(?:[.,]\d+)?[а-я]?)\b",
    re.IGNORECASE,
)
_REVERSED_FACILITY_CODE = re.compile(
    r"\b(?P<number>\d+(?:[.,]\d+)?[а-я]?)\s*(?P<kind>лос|кнс)\b",
    re.IGNORECASE,
)

_WORK_FAMILIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "sheet_piling",
        "Шпунтовые работы",
        ("шпунт", "ларсен", "шпунтов"),
    ),
    (
        "waling_beam",
        "Распределительные и обвязочные пояса",
        (
            "распределительн пояс",
            "обвязочн пояс",
            "обвязочн балк",
            "пояс из двутавр",
            "поясов из двутавр",
            "пояса крепи",
            "монтаж поясов",
            "верхнего и нижнего поясов",
        ),
    ),
    (
        "excavation",
        "Разработка котлованов и земляные работы",
        ("котлован", "разработк грунт", "землян", "выемк грунт"),
    ),
    (
        "reinforced_concrete",
        "Железобетонные работы",
        ("железобетон", "армирован", "бетонирован", "бетонн работ", "арматур"),
    ),
    (
        "foundation_slab",
        "Фундаменты и плиты",
        ("фундамент", "фундаментн плит", "плит основан", "монолитн плит"),
    ),
    (
        "pipeline",
        "Трубопроводы и сети",
        ("трубопровод", "прокладк труб", "ливнев канализац", "коллектор"),
    ),
    (
        "waterproofing",
        "Гидроизоляция",
        ("гидроизоляц", "водоизоляц"),
    ),
    (
        "backfill",
        "Обратная засыпка и уплотнение",
        ("обратн засып", "засыпк грунт", "уплотнен грунт"),
    ),
)

_PROFESSIONAL_DEFECT_KINDS = frozenset(
    {
        "project_work_missing_in_estimate",
        "quantity_mismatch",
        "project_material_missing_in_estimate",
        "estimate_position_unsupported_by_project",
        "incompatible_units",
        "material_quantity_mismatch",
        "estimate_comparison_input_unavailable",
        "estimate_material_comparison_input_unavailable",
        "material_quantity_comparison_input_unavailable",
        "drawing_intelligence_required",
        "normative_authority_unavailable",
        "rule_coverage_unavailable",
    }
)


def build_project_engineering_model(
    *,
    workspace_id: str,
    project_definition: Mapping[str, Any],
    candidates: Mapping[str, Iterable[Mapping[str, Any]]],
    structure_nodes: Iterable[Mapping[str, Any]],
    identity_components: Iterable[Mapping[str, Any]],
    pit_inventory: Mapping[str, Any],
    defects: Iterable[Mapping[str, Any]],
    matrix: Mapping[str, Any],
    normative_profile: Mapping[str, Any] | None,
    source_context: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the project-first model consumed by UI, report and assistant."""

    project = _project_overview(project_definition, candidates.get("project_fields", ()))
    facilities, node_to_facility = _facilities(
        workspace_id,
        structure_nodes,
        identity_components,
    )
    if project.get("composition") is None and facilities:
        project["composition"] = {
            "value": ", ".join(str(item["name"]) for item in facilities),
            "status": "Составлено по повторяющимся обозначениям сооружений",
            "source_locator_ids": sorted(
                {
                    str(locator_id)
                    for item in facilities
                    for locator_id in item.get("source_locator_ids") or ()
                }
            ),
        }
        project["missing_information"] = [
            value for value in project.get("missing_information") or () if value != "Состав объекта"
        ]
    pits = _pits(pit_inventory, facilities, source_context)
    work_model = _work_schedule(
        candidates.get("work_types", ()),
        candidates.get("quantities", ()),
        candidates.get("materials", ()),
        facilities,
        node_to_facility,
        source_context,
    )
    comparisons = _deduplicate_dicts(
        [
            *_comparisons(work_model["works"]),
            *_exact_work_comparisons(
                candidates.get("work_types", ()),
                candidates.get("quantities", ()),
                source_context,
            ),
        ]
    )
    issues = _issues(defects, comparisons, work_model["works"], source_context)
    requirements = _requirements(matrix, normative_profile)
    actions, risks = _actions_and_risks(issues)
    facility_cards = _facility_cards(
        facilities,
        pits,
        work_model["works"],
        comparisons,
        issues,
        source_context,
    )
    documents = _documents(source_context)
    unresolved = {
        "facility_designations": [
            item for item in facilities if item["status"] == "Требует уточнения"
        ],
        "pits": list(pits["requires_clarification"]),
        "works": list(work_model["unclassified"]),
        "requirements": list(requirements["unresolved"]),
    }
    model = {
        "model_version": PROJECT_ENGINEERING_MODEL_VERSION,
        "project": project,
        "facilities": facilities,
        "facility_cards": facility_cards,
        "pits": pits,
        "works": work_model["works"],
        "unclassified_works": work_model["unclassified"],
        "quantity_comparisons": comparisons,
        "materials": work_model["materials"],
        "requirements": requirements,
        "issues": issues,
        "risks": risks,
        "customer_questions": actions,
        "documents": documents,
        "unresolved": unresolved,
        "summary": {
            "facility_count": len([item for item in facilities if not item["is_alias_group"]]),
            "established_pit_count": int(pits["established_count"]),
            "pit_count_is_final": bool(pits["is_final"]),
            "work_scope_count": len(work_model["works"]),
            "unclassified_work_count": len(work_model["unclassified"]),
            "quantity_comparison_count": len(comparisons),
            "issue_count": len(issues),
            "risk_count": len(risks),
            "customer_question_count": len(actions),
        },
    }
    model["model_fingerprint"] = semantic_digest(model)
    return model


def facility_designation(value: object) -> str | None:
    """Return one exact LOS/KNS designation, rejecting compound/range labels."""

    text = str(value or "")
    matches = list(_FACILITY_CODE.finditer(text))
    normalized = {
        f"{match.group('kind').upper()} {match.group('number').replace(',', '.').casefold()}"
        for match in matches
    }
    normalized.update(
        f"{match.group('kind').upper()} {match.group('number').replace(',', '.').casefold()}"
        for match in _REVERSED_FACILITY_CODE.finditer(text)
    )
    return next(iter(normalized)) if len(normalized) == 1 else None


def _explicit_designation_alias(designation: str, aliases: Iterable[object]) -> bool:
    expected = _normalized(designation).replace("№", "")
    for alias in aliases:
        normalized = _normalized(alias).replace("№", "")
        if normalized in {expected, f"участок {expected}", f"сооружение {expected}"}:
            return True
    return False


def classify_work_family(value: object) -> tuple[str, str] | None:
    normalized = _normalized(value)
    for key, title, terms in _WORK_FAMILIES:
        if any(term in normalized for term in terms):
            return key, title
    return None


def professional_work_name(family_key: str, wording: object) -> str:
    normalized = _normalized(wording)
    if family_key == "sheet_piling":
        if "извлеч" in normalized or "демонтаж" in normalized:
            return "Извлечение шпунта"
        if "погруж" in normalized or "забив" in normalized:
            return "Погружение шпунта"
        if "устройств" in normalized or "огражден" in normalized:
            return "Устройство шпунтового ограждения"
    if family_key == "waling_beam":
        if "демонтаж" in normalized or "разбор" in normalized:
            return "Демонтаж распределительного/обвязочного пояса"
        return "Устройство распределительного/обвязочного пояса"
    return next(title for key, title, _terms in _WORK_FAMILIES if key == family_key)


def _project_overview(
    project_definition: Mapping[str, Any], fields: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    definition = project_definition.get("definition")
    definition = dict(definition) if isinstance(definition, Mapping) else {}
    verified = definition.get("fields")
    verified = dict(verified) if isinstance(verified, Mapping) else {}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for raw in fields:
        row = dict(raw)
        key = str(row.get("label") or row.get("field_key") or "")
        value = str(row.get("normalized_value") or row.get("value") or "").strip()
        if key and value:
            grouped[key][_normalized(value)].append(row)

    def select(key: str) -> dict[str, Any] | None:
        confirmed = verified.get(key)
        if isinstance(confirmed, Mapping):
            return {
                "value": confirmed.get("normalized_value", confirmed.get("raw_value")),
                "status": "Установлено",
                "source_locator_ids": [str(confirmed.get("source_locator_id"))]
                if confirmed.get("source_locator_id")
                else [],
            }
        values = grouped.get(key, {})
        if not values:
            return None
        _normalized_value, rows = max(
            values.items(),
            key=lambda item: (
                len({str(row.get("source_version_id")) for row in item[1]}),
                len(item[1]),
                max(
                    len(str(row.get("normalized_value") or row.get("value") or ""))
                    for row in item[1]
                ),
            ),
        )
        representative = max(
            rows,
            key=lambda row: len(str(row.get("normalized_value") or row.get("value") or "")),
        )
        independent_sources = len({str(row.get("source_version_id")) for row in rows})
        return {
            "value": representative.get("normalized_value", representative.get("value")),
            "status": (
                "Установлено по нескольким документам"
                if independent_sources >= 2
                else "Требует подтверждения по другому разделу проекта"
            ),
            "source_count": independent_sources,
            "source_locator_ids": sorted(
                {str(row.get("source_locator_id")) for row in rows if row.get("source_locator_id")}
            ),
        }

    name = select("object_name")
    purpose = select("purpose")
    composition = select("object_composition")
    return {
        "name": name,
        "purpose": purpose,
        "composition": composition,
        "status": "Установлено частично"
        if not (name and purpose and composition)
        else "Установлено",
        "missing_information": [
            label
            for value, label in (
                (name, "Наименование объекта"),
                (purpose, "Назначение объекта"),
                (composition, "Состав объекта"),
            )
            if value is None
        ],
    }


def _facilities(
    workspace_id: str,
    structure_nodes: Iterable[Mapping[str, Any]],
    identity_components: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    del structure_nodes
    groups: dict[str, dict[str, Any]] = {}
    node_to_facility: dict[str, str] = {}
    for raw in identity_components:
        component = dict(raw)
        kind = str(component.get("identity_kind") or "")
        if kind not in {"facility", "local_area", "zone", "structure"}:
            continue
        label = str(component.get("canonical_label") or "").strip()
        designation = facility_designation(label)
        candidate_labels = [
            str(value).strip()
            for value in component.get("candidate_labels") or (label,)
            if str(value).strip()
        ]
        source_locator_ids = {str(value) for value in component.get("source_locator_ids") or ()}
        if (
            designation
            and len(source_locator_ids) >= 2
            and _explicit_designation_alias(designation, candidate_labels)
        ):
            key = f"designation:{designation.casefold()}"
            status = "Установлено по обозначению в документах"
            is_alias_group = False
        else:
            continue
        current = groups.setdefault(
            key,
            {
                "facility_id": semantic_digest({"workspace_id": workspace_id, "facility_key": key}),
                "designation": designation,
                "name": designation or label,
                "kind": "Сооружение" if kind == "facility" else "Участок",
                "aliases": set(),
                "member_structure_node_ids": set(),
                "source_locator_ids": set(),
                "status": status,
                "is_alias_group": is_alias_group,
            },
        )
        current["aliases"].update(candidate_labels)
        current["member_structure_node_ids"].update(
            str(value) for value in component.get("member_structure_node_ids") or ()
        )
        current["source_locator_ids"].update(source_locator_ids)
    facilities: list[dict[str, Any]] = []
    for value in groups.values():
        value["aliases"] = sorted(value["aliases"])
        value["member_structure_node_ids"] = sorted(value["member_structure_node_ids"])
        value["source_locator_ids"] = sorted(value["source_locator_ids"])
        facilities.append(value)
        for node_id in value["member_structure_node_ids"]:
            node_to_facility.setdefault(node_id, value["facility_id"])
    facilities.sort(key=lambda item: (item["is_alias_group"], item["name"], item["facility_id"]))
    return facilities, node_to_facility


def _pits(
    pit_inventory: Mapping[str, Any],
    facilities: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    facilities_by_designation = {
        str(value.get("designation")): dict(value)
        for value in facilities
        if value.get("designation")
    }
    established_by_facility: dict[str, dict[str, Any]] = {}
    clarification: list[dict[str, Any]] = []
    for raw in pit_inventory.get("candidate_pits") or ():
        pit = dict(raw)
        designation = facility_designation(pit.get("associated_facility_designation"))
        aliases = [str(value) for value in pit.get("aliases") or ()]
        is_singular = not any(
            "котлован" in _normalized(value) and "котлованы" in _normalized(value)
            for value in aliases
        )
        if designation and designation in facilities_by_designation and is_singular:
            locator_ids = sorted(str(value) for value in pit.get("source_locator_ids") or ())
            canonical_label = str(pit.get("canonical_label") or pit.get("display_name") or "")
            pit_key = f"{designation}:{_normalized(canonical_label)}"
            current = established_by_facility.setdefault(
                pit_key,
                {
                    "pit_id": semantic_digest(
                        {
                            "facility": designation,
                            "label": _normalized(canonical_label),
                            "kind": "excavation_pit",
                        }
                    ),
                    "name": canonical_label or f"Котлован {designation}",
                    "related_facility_id": facilities_by_designation[designation]["facility_id"],
                    "related_facility": designation,
                    "aliases": [],
                    "known_parameters": [],
                    "related_works": [],
                    "sources": [],
                    "source_locator_ids": [],
                    "status": "Установлен по явной привязке к сооружению",
                },
            )
            current["aliases"] = sorted({*current["aliases"], *aliases})
            current["source_locator_ids"] = sorted({*current["source_locator_ids"], *locator_ids})
            current["sources"] = _source_refs(current["source_locator_ids"], source_context)
        else:
            clarification.append(
                {
                    "description": str(
                        pit.get("display_name") or pit.get("canonical_label") or "Котлован"
                    ),
                    "related_facility": pit.get("associated_facility_designation"),
                    "reason": (
                        "В документах указана группа или несколько котлованов "
                        "без поштучного обозначения"
                        if any("котлованы" in _normalized(value) for value in aliases)
                        else "Не установлена однозначная привязка к отдельному сооружению"
                    ),
                    "sources": _source_refs(pit.get("source_locator_ids") or (), source_context),
                    "source_locator_ids": sorted(
                        str(value) for value in pit.get("source_locator_ids") or ()
                    ),
                }
            )
    coverage = dict(pit_inventory.get("coverage") or {})
    ambiguous_count = int(dict(coverage.get("disposition_counts") or {}).get("ambiguous", 0))
    unresolved_count = len(clarification)
    established = sorted(established_by_facility.values(), key=lambda value: value["name"])
    return {
        "established": established,
        "established_count": len(established),
        "requires_clarification": clarification,
        "unresolved_group_count": unresolved_count,
        "ambiguous_observation_count": ambiguous_count,
        "is_final": unresolved_count == 0,
        "professional_answer": (
            f"В проекте {_russian_pit_count(len(established), established=True)}."
            if unresolved_count == 0
            else f"{_russian_pit_count(len(established), established=True).capitalize()}. "
            f"Ещё {unresolved_count} {_russian_group_word(unresolved_count)} обозначений "
            "требуют уточнения; "
            "поэтому окончательное количество по имеющимся данным пока не установлено."
        ),
    }


def _russian_pit_count(value: int, *, established: bool) -> str:
    singular = "подтверждён" if established else "установлен"
    plural = "подтверждены" if established else "установлены"
    many = "подтверждено" if established else "установлено"
    if value % 10 == 1 and value % 100 != 11:
        return f"{singular} {value} отдельный котлован"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return f"{plural} {value} отдельных котлована"
    return f"{many} {value} отдельных котлованов"


def _russian_group_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "группа"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "группы"
    return "групп"


def _work_schedule(
    works: Iterable[Mapping[str, Any]],
    quantities: Iterable[Mapping[str, Any]],
    materials: Iterable[Mapping[str, Any]],
    facilities: Iterable[Mapping[str, Any]],
    node_to_facility: Mapping[str, str],
    source_context: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    del node_to_facility  # Exact relationship assignment can extend the locator rule later.
    facility_by_designation = {
        str(item.get("designation")): dict(item) for item in facilities if item.get("designation")
    }
    facility_by_id = {str(item.get("facility_id")): dict(item) for item in facilities}
    facility_ids_by_locator: dict[str, set[str]] = defaultdict(set)
    facility_ids_by_page: dict[tuple[str, int], set[str]] = defaultdict(set)
    for item in facilities:
        facility_id = str(item.get("facility_id") or "")
        for locator_id in item.get("source_locator_ids") or ():
            locator_key = str(locator_id)
            facility_ids_by_locator[locator_key].add(facility_id)
            context = source_context.get(locator_key)
            if isinstance(context, Mapping):
                locator_value = context.get("locator_value")
                page = locator_value.get("page") if isinstance(locator_value, Mapping) else None
                if page is not None:
                    facility_ids_by_page[
                        (str(context.get("source_version_id") or ""), int(page))
                    ].add(facility_id)
    quantity_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    material_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in quantities:
        row = dict(raw)
        quantity_by_work[str(row.get("work_candidate_id") or "")].append(row)
    for raw in materials:
        row = dict(raw)
        material_by_work[str(row.get("work_candidate_id") or "")].append(row)

    exact_observations: dict[tuple[str, str, str], dict[str, Any]] = {}
    unclassified: list[dict[str, Any]] = []
    for raw in works:
        row = dict(raw)
        candidate_id = str(row.get("candidate_id") or "")
        name = str(row.get("value") or row.get("raw_name") or "").strip()
        normalized_name = str(row.get("label") or row.get("normalized_name") or _normalized(name))
        locator_id = str(row.get("source_locator_id") or "")
        source_version_id = str(row.get("source_version_id") or "")
        family = classify_work_family(normalized_name)
        designation = facility_designation(f"{name} {row.get('scope_key') or ''}")
        facility = facility_by_designation.get(designation or "")
        assignment_basis = "Явное обозначение сооружения в описании работы"
        if facility is None:
            exact_facilities = facility_ids_by_locator.get(locator_id, set())
            if len(exact_facilities) == 1:
                facility = facility_by_id[next(iter(exact_facilities))]
                designation = str(facility.get("designation") or facility.get("name") or "")
                assignment_basis = "Работа и сооружение указаны в одном исходном фрагменте"
        context = dict(source_context.get(locator_id) or {})
        if facility is None:
            locator_value = context.get("locator_value")
            page = locator_value.get("page") if isinstance(locator_value, Mapping) else None
            page_facilities = (
                facility_ids_by_page.get(
                    (str(context.get("source_version_id") or ""), int(page)), set()
                )
                if page is not None
                else set()
            )
            if len(page_facilities) == 1:
                facility = facility_by_id[next(iter(page_facilities))]
                designation = str(facility.get("designation") or facility.get("name") or "")
                assignment_basis = "Работа и сооружение указаны на одном листе"
        role = _professional_document_role(row.get("source_role"), context.get("safe_display_name"))
        observation = {
            "candidate_id": candidate_id,
            "project_wording": name,
            "normalized_work_name": normalized_name,
            "facility_id": facility.get("facility_id") if facility else None,
            "facility": designation,
            "facility_assignment_basis": assignment_basis if facility else None,
            "document_role": role,
            "source_version_id": source_version_id,
            "source_locator_id": locator_id,
            "source": _source_ref(locator_id, source_context),
            "quantities": _unique_values(quantity_by_work.get(candidate_id, ()), "quantity"),
            "materials": _unique_values(material_by_work.get(candidate_id, ()), "material"),
        }
        if family is None:
            if name:
                unclassified.append(observation)
            continue
        family_key, family_name = family
        operation_name = professional_work_name(family_key, name)
        exact_key = (source_version_id, locator_id, normalized_name)
        exact_observations.setdefault(
            exact_key,
            {
                **observation,
                "family_key": family_key,
                "family_name": family_name,
                "operation_name": operation_name,
            },
        )

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in exact_observations.values():
        facility_key = str(observation.get("facility_id") or "unassigned")
        grouped[
            (
                facility_key,
                str(observation["family_key"]),
                str(observation["operation_name"]),
            )
        ].append(observation)
    schedules: list[dict[str, Any]] = []
    material_rows: list[dict[str, Any]] = []
    for (facility_key, family_key, operation_name), observations in sorted(grouped.items()):
        observations.sort(
            key=lambda item: (
                str(item.get("document_role")),
                str(item.get("source_version_id")),
                str(item.get("source_locator_id")),
            )
        )
        facility_name = next(
            (str(item.get("facility")) for item in observations if item.get("facility")),
            "Место выполнения не установлено",
        )
        quantities_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
        materials_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for observation in observations:
            role = str(observation["document_role"])
            quantities_by_role[role].extend(observation["quantities"])
            materials_by_role[role].extend(observation["materials"])
        quantities_by_role = {
            key: _deduplicate_dicts(value) for key, value in quantities_by_role.items()
        }
        materials_by_role = {
            key: _deduplicate_dicts(value) for key, value in materials_by_role.items()
        }
        schedule_id = semantic_digest(
            {
                "facility": facility_key,
                "family": family_key,
                "operation": operation_name,
                "observations": sorted(str(item["candidate_id"]) for item in observations),
            }
        )
        schedule = {
            "work_scope_id": schedule_id,
            "facility_id": None if facility_key == "unassigned" else facility_key,
            "facility": facility_name,
            "family_key": family_key,
            "work_name": operation_name,
            "work_family": observations[0]["family_name"],
            "project_wording": sorted(
                {str(item["project_wording"]) for item in observations if item["project_wording"]}
            ),
            "quantities_by_document": quantities_by_role,
            "materials_by_document": materials_by_role,
            "sources": [item["source"] for item in observations if item.get("source")],
            "source_locator_ids": sorted(
                {
                    str(item["source_locator_id"])
                    for item in observations
                    if item["source_locator_id"]
                }
            ),
            "status": (
                str(observations[0].get("facility_assignment_basis"))
                if facility_key != "unassigned"
                else "Место выполнения требует уточнения"
            ),
        }
        schedules.append(schedule)
        for role, role_materials in materials_by_role.items():
            for material in role_materials:
                material_rows.append(
                    {
                        "work_scope_id": schedule_id,
                        "facility": facility_name,
                        "work": schedule["work_name"],
                        "document_role": role,
                        **material,
                    }
                )
    unclassified = _deduplicate_dicts(unclassified)
    return {"works": schedules, "materials": material_rows, "unclassified": unclassified}


def _comparisons(works: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    design_roles = ("РД", "Спецификация", "ПД")
    commercial_roles = ("ВОР", "Смета")
    for raw in works:
        work = dict(raw)
        quantities = dict(work.get("quantities_by_document") or {})
        for design_role in design_roles:
            for commercial_role in commercial_roles:
                left = _one_comparable_quantity(quantities.get(design_role) or ())
                right = _one_comparable_quantity(quantities.get(commercial_role) or ())
                if left is None or right is None:
                    continue
                if left[1] != right[1]:
                    comparisons.append(
                        _comparison_row(
                            work,
                            design_role,
                            commercial_role,
                            left,
                            right,
                            None,
                            "Единицы измерения различаются",
                        )
                    )
                    continue
                difference = left[0] - right[0]
                if difference == 0:
                    conclusion = "Значения совпадают"
                else:
                    conclusion = (
                        f"Разница {design_role} ↔ {commercial_role}: "
                        f"{_decimal_text(difference)} {left[1]}"
                    )
                comparisons.append(
                    _comparison_row(
                        work, design_role, commercial_role, left, right, difference, conclusion
                    )
                )
    return comparisons


def _exact_work_comparisons(
    works: Iterable[Mapping[str, Any]],
    quantities: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    quantity_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in quantities:
        row = dict(raw)
        quantity_by_work[str(row.get("work_candidate_id") or "")].append(row)
    grouped: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for raw in works:
        row = dict(raw)
        candidate_id = str(row.get("candidate_id") or "")
        values = quantity_by_work.get(candidate_id, [])
        if not values:
            continue
        wording = str(row.get("value") or row.get("raw_name") or "").strip()
        normalized_name = str(
            row.get("label") or row.get("normalized_name") or _normalized(wording)
        )
        if classify_work_family(normalized_name) is not None:
            continue
        locator_id = str(row.get("source_locator_id") or "")
        context = dict(source_context.get(locator_id) or {})
        grouped[
            (normalized_name, facility_designation(f"{wording} {row.get('scope_key') or ''}"))
        ].append(
            {
                "candidate_id": candidate_id,
                "wording": wording,
                "role": _professional_document_role(
                    row.get("source_role"), context.get("safe_display_name")
                ),
                "quantities": values,
                "source_locator_id": locator_id,
            }
        )
    comparisons: list[dict[str, Any]] = []
    for (normalized_name, facility), observations in grouped.items():
        by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for observation in observations:
            by_role[str(observation["role"])].extend(observation["quantities"])
        for design_role in ("РД", "Спецификация", "ПД"):
            for commercial_role in ("ВОР", "Смета"):
                left = _one_comparable_quantity(by_role.get(design_role) or ())
                right = _one_comparable_quantity(by_role.get(commercial_role) or ())
                if left is None or right is None or left[1] != right[1]:
                    continue
                difference = left[0] - right[0]
                conclusion = (
                    "Значения совпадают"
                    if difference == 0
                    else (
                        f"Разница {design_role} ↔ {commercial_role}: "
                        f"{_decimal_text(difference)} {left[1]}"
                    )
                )
                comparisons.append(
                    _comparison_row(
                        {
                            "work_scope_id": semantic_digest(
                                {
                                    "normalized_name": normalized_name,
                                    "facility": facility,
                                }
                            ),
                            "facility": facility or "Место выполнения требует уточнения",
                            "work_name": observations[0]["wording"],
                            "source_locator_ids": sorted(
                                {
                                    str(item["source_locator_id"])
                                    for item in observations
                                    if item["source_locator_id"]
                                }
                            ),
                        },
                        design_role,
                        commercial_role,
                        left,
                        right,
                        difference,
                        conclusion,
                    )
                )
    return comparisons


def _comparison_row(
    work: Mapping[str, Any],
    left_role: str,
    right_role: str,
    left: tuple[Decimal, str],
    right: tuple[Decimal, str],
    difference: Decimal | None,
    conclusion: str,
) -> dict[str, Any]:
    return {
        "comparison_id": semantic_digest(
            {
                "work_scope_id": work.get("work_scope_id"),
                "left_role": left_role,
                "right_role": right_role,
                "left": [str(left[0]), left[1]],
                "right": [str(right[0]), right[1]],
            }
        ),
        "work_scope_id": work.get("work_scope_id"),
        "facility": work.get("facility"),
        "work": work.get("work_name"),
        "left": {"document_role": left_role, "value": _decimal_text(left[0]), "unit": left[1]},
        "right": {"document_role": right_role, "value": _decimal_text(right[0]), "unit": right[1]},
        "difference": _decimal_text(difference) if difference is not None else None,
        "conclusion": conclusion,
        "source_locator_ids": list(work.get("source_locator_ids") or ()),
    }


def _issues(
    defects: Iterable[Mapping[str, Any]],
    comparisons: Iterable[Mapping[str, Any]],
    works: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for comparison in comparisons:
        if comparison.get("difference") in {None, "0"} and "различаются" not in str(
            comparison.get("conclusion")
        ):
            continue
        issues.append(
            {
                "issue_id": str(comparison["comparison_id"]),
                "kind": "Расхождение объёмов"
                if comparison.get("difference") is not None
                else "Несопоставимые единицы",
                "location": comparison.get("facility"),
                "subject": comparison.get("work"),
                "description": comparison.get("conclusion"),
                "practical_consequence": (
                    "Объём и стоимость работ требуют согласования до подачи предложения."
                ),
                "recommended_action": (
                    "Запросить у Заказчика подтверждение применяемого объёма и документа-основания."
                ),
                "source_locator_ids": list(comparison.get("source_locator_ids") or ()),
                "sources": _source_refs(comparison.get("source_locator_ids") or (), source_context),
                "status": "Установленное расхождение"
                if comparison.get("difference") is not None
                else "Требует уточнения",
            }
        )
    work_rows = [dict(row) for row in works]
    commercial_unassigned: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for work in work_rows:
        roles = set(dict(work.get("quantities_by_document") or {})) | set(
            dict(work.get("materials_by_document") or {})
        )
        if work.get("facility_id") is None and roles.intersection({"ВОР", "Смета"}):
            commercial_unassigned[str(work.get("family_key") or "")].append(work)
    for work in work_rows:
        family = str(work.get("family_key") or "")
        if family not in {"sheet_piling", "waling_beam"} or not work.get("facility_id"):
            continue
        roles = set(dict(work.get("quantities_by_document") or {})) | set(
            dict(work.get("materials_by_document") or {})
        )
        if not roles.intersection({"ПД", "РД", "Спецификация"}):
            continue
        unmatched = commercial_unassigned.get(family, [])
        if not unmatched:
            continue
        locators = sorted(
            {
                *(str(value) for value in work.get("source_locator_ids") or ()),
                *(
                    str(value)
                    for item in unmatched
                    for value in item.get("source_locator_ids") or ()
                ),
            }
        )
        issue_id = semantic_digest(
            {
                "kind": "commercial_scope_allocation_unresolved",
                "facility": work.get("facility"),
                "family": family,
                "locators": locators,
            }
        )
        issues.append(
            {
                "issue_id": issue_id,
                "kind": "Коммерческий объём не распределён по сооружениям",
                "location": work.get("facility"),
                "subject": work.get("work_name"),
                "description": (
                    "Проектное решение привязано к сооружению, а найденные позиции ВОР/сметы "
                    "не содержат однозначной разбивки по сооружениям."
                ),
                "practical_consequence": (
                    "Нельзя воспроизводимо подтвердить полноту и цену этого объёма "
                    "для отдельного сооружения."
                ),
                "recommended_action": (
                    "Запросить у Заказчика ведомость распределения объёмов по сооружениям "
                    "и подтвердить состав работ для данного сооружения."
                ),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Требует уточнения до подачи предложения",
            }
        )
    for raw in defects:
        row = dict(raw)
        kind = str(row.get("defect_kind") or "")
        if kind not in _PROFESSIONAL_DEFECT_KINDS or kind == "ambiguous_source_match":
            continue
        parameters = dict(row.get("parameters") or {})
        locators = [str(value) for value in row.get("source_locator_ids") or ()]
        issues.append(
            {
                "issue_id": str(row.get("defect_id") or semantic_digest(row)),
                "kind": _issue_title(kind),
                "location": parameters.get("location") or "Место требует уточнения",
                "subject": parameters.get("work_name")
                or str(row.get("subject_identity") or "Работа"),
                "description": _issue_description(kind, parameters),
                "practical_consequence": str(
                    parameters.get("consequence")
                    or "Вопрос влияет на определение состава или объёма предложения."
                ),
                "recommended_action": _issue_action(kind),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Требует уточнения",
            }
        )
    return _deduplicate_dicts(issues)


def _requirements(matrix: Mapping[str, Any], profile: Mapping[str, Any] | None) -> dict[str, Any]:
    matrix_value = matrix.get("matrix")
    matrix_value = dict(matrix_value) if isinstance(matrix_value, Mapping) else dict(matrix)
    rows = [dict(value) for value in matrix_value.get("rows") or () if isinstance(value, Mapping)]
    applicable = [
        row for row in rows if row.get("rule_version_id") or row.get("normative_edition_id")
    ]
    profile_value = dict(profile) if isinstance(profile, Mapping) else {}
    unresolved: list[str] = []
    if not applicable:
        unresolved.append(
            "Применимые требования НТД ещё не связаны с установленными видами работ проекта."
        )
    if not profile_value.get("applicable_on"):
        unresolved.append("Для проверки редакций НТД требуется дата применимости проекта.")
    return {
        "applicable": applicable,
        "unresolved": unresolved,
        "professional_summary": (
            f"Для работ установлено {len(applicable)} применимых требований."
            if applicable
            else (
                "Применимые нормы для работ проекта требуют уточнения; это не блокирует "
                "описание проекта и сравнение документов."
            )
        ),
    }


def _actions_and_risks(
    issues: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    for issue in issues:
        issue_id = str(issue.get("issue_id") or "")
        actions.append(
            {
                "action_id": semantic_digest({"issue_id": issue_id, "kind": "customer_question"}),
                "issue_id": issue_id,
                "question": str(
                    issue.get("recommended_action") or "Запросить уточнение у Заказчика."
                ),
                "location": issue.get("location"),
                "source_locator_ids": list(issue.get("source_locator_ids") or ()),
            }
        )
        risks.append(
            {
                "risk_id": semantic_digest({"issue_id": issue_id, "kind": "contractor_risk"}),
                "issue_id": issue_id,
                "risk": str(
                    issue.get("practical_consequence") or "Неопределённость состава работ."
                ),
                "mitigation": str(
                    issue.get("recommended_action") or "Получить письменное уточнение."
                ),
                "location": issue.get("location"),
            }
        )
    return actions, risks


def _facility_cards(
    facilities: Iterable[Mapping[str, Any]],
    pits: Mapping[str, Any],
    works: Iterable[Mapping[str, Any]],
    comparisons: Iterable[Mapping[str, Any]],
    issues: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pit_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    works_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    comparisons_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    issues_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pit in pits.get("established") or ():
        pit_by_facility[str(pit.get("related_facility_id") or "")].append(dict(pit))
    for work in works:
        works_by_facility[str(work.get("facility_id") or "")].append(dict(work))
    for comparison in comparisons:
        comparisons_by_facility[str(comparison.get("facility") or "")].append(dict(comparison))
    for issue in issues:
        issues_by_facility[str(issue.get("location") or "")].append(dict(issue))
    cards: list[dict[str, Any]] = []
    for raw in facilities:
        facility = dict(raw)
        facility_id = str(facility.get("facility_id") or "")
        name = str(facility.get("name") or "")
        facility_works = works_by_facility.get(facility_id, [])
        cards.append(
            {
                "facility": facility,
                "purpose": None,
                "pits": pit_by_facility.get(facility_id, []),
                "structures": [],
                "works": facility_works,
                "sheet_piling": [
                    work for work in facility_works if work.get("family_key") == "sheet_piling"
                ],
                "reinforced_concrete": [
                    work
                    for work in facility_works
                    if work.get("family_key") == "reinforced_concrete"
                ],
                "pipelines": [
                    work for work in facility_works if work.get("family_key") == "pipeline"
                ],
                "materials": [
                    material
                    for work in facility_works
                    for values in dict(work.get("materials_by_document") or {}).values()
                    for material in values
                ],
                "comparisons": comparisons_by_facility.get(name, []),
                "issues": issues_by_facility.get(name, []),
                "documents": _source_refs(facility.get("source_locator_ids") or (), source_context),
                "missing_information": [
                    label
                    for condition, label in (
                        (
                            not pit_by_facility.get(facility_id),
                            "Котлован не установлен или не предусмотрен",
                        ),
                        (not facility_works, "Работы не привязаны к сооружению"),
                    )
                    if condition
                ],
            }
        )
    return cards


def _documents(source_context: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for value in source_context.values():
        name = str(value.get("safe_display_name") or "")
        version = int(value.get("document_version") or 1)
        if not name:
            continue
        unique.setdefault(
            (name, version),
            {
                "name": name,
                "version": version,
                "source_version_id": str(value.get("source_version_id") or ""),
                "document_role": _professional_document_role(None, name),
            },
        )
    return sorted(unique.values(), key=lambda value: (value["document_role"], value["name"]))


def _professional_document_role(source_role: object, display_name: object) -> str:
    name = _normalized(display_name)
    role = str(source_role or "")
    if "вор" in name or "ведомост объем" in name or "ведомост объём" in name:
        return "ВОР"
    if "смет" in name or re.search(r"(?:^|\s)см\d", name):
        return "Смета"
    if "спецификац" in name:
        return "Спецификация"
    if role == "bill_of_quantities":
        return "ВОР"
    if role in {"local_estimate", "object_estimate", "consolidated_estimate"}:
        return "Смета"
    if role == "specification":
        return "Спецификация"
    if " рр" in f" {name}" or "рабоч" in name or role == "working_documentation":
        return "РД"
    if role in {"project_documentation", "explanatory_note", "drawing_or_scheme"}:
        return "ПД"
    return "Проектный документ"


def _unique_values(values: Iterable[Mapping[str, Any]], kind: str) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in values:
        row = dict(raw)
        if kind == "quantity":
            payload = {
                "value": row.get("normalized_value", row.get("value")),
                "unit": row.get("normalized_unit", row.get("raw_unit")),
                "source_locator_id": row.get("source_locator_id"),
            }
            rendered = {
                "value": row.get("normalized_value", row.get("value")),
                "unit": row.get("normalized_unit", row.get("raw_unit")),
                "raw_value": row.get("value", row.get("raw_value")),
                "raw_unit": row.get("raw_unit"),
                "source_locator_id": row.get("source_locator_id"),
            }
        else:
            payload = {
                "name": row.get("normalized_name", row.get("value")),
                "quantity": row.get("normalized_value", row.get("raw_quantity")),
                "unit": row.get("normalized_unit", row.get("raw_unit")),
                "source_locator_id": row.get("source_locator_id"),
            }
            rendered = {
                "name": row.get("value", row.get("raw_name")),
                "quantity": row.get("normalized_value", row.get("raw_quantity")),
                "unit": row.get("normalized_unit", row.get("raw_unit")),
                "source_locator_id": row.get("source_locator_id"),
            }
        result.setdefault(semantic_digest(payload), rendered)
    return [result[key] for key in sorted(result)]


def _one_comparable_quantity(values: Iterable[Mapping[str, Any]]) -> tuple[Decimal, str] | None:
    unique: set[tuple[Decimal, str]] = set()
    for value in values:
        raw = value.get("normalized_value", value.get("value"))
        unit = _normalized_unit(
            value.get("normalized_unit", value.get("unit", value.get("raw_unit")))
        )
        if raw is None or not unit:
            continue
        try:
            unique.add((Decimal(str(raw).replace(",", ".")), unit))
        except InvalidOperation:
            continue
    return next(iter(unique)) if len(unique) == 1 else None


def _normalized_unit(value: object) -> str:
    return str(value or "").strip().casefold().rstrip(".")


def _source_ref(
    locator_id: str, source_context: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any] | None:
    value = source_context.get(locator_id)
    if not isinstance(value, Mapping):
        return None
    locator = value.get("locator_value")
    page = locator.get("page") if isinstance(locator, Mapping) else value.get("page_number")
    return {
        "document": value.get("safe_display_name"),
        "version": value.get("document_version"),
        "page": page,
        "source_version_id": value.get("source_version_id"),
        "source_locator_id": locator_id,
    }


def _source_refs(
    locator_ids: Iterable[object], source_context: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    refs = [_source_ref(str(value), source_context) for value in locator_ids]
    return _deduplicate_dicts([value for value in refs if value is not None])


def _deduplicate_dicts(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        row = dict(value)
        result.setdefault(semantic_digest(row), row)
    return [result[key] for key in sorted(result)]


def _issue_title(kind: str) -> str:
    return {
        "project_work_missing_in_estimate": "Работа не найдена в коммерческих документах",
        "quantity_mismatch": "Расхождение объёмов",
        "project_material_missing_in_estimate": "Материал не найден в коммерческих документах",
        "estimate_position_unsupported_by_project": (
            "Позиция сметы без установленного проектного основания"
        ),
        "incompatible_units": "Несопоставимые единицы измерения",
        "material_quantity_mismatch": "Расхождение количества материала",
        "estimate_comparison_input_unavailable": "Сравнение со сметой или ВОР невозможно",
        "drawing_intelligence_required": "Требуется проверка чертежа",
        "normative_authority_unavailable": "Требование НТД требует уточнения",
        "rule_coverage_unavailable": "Автоматическая проверка требования недоступна",
    }.get(kind, "Инженерный вопрос")


def _issue_description(kind: str, parameters: Mapping[str, Any]) -> str:
    if kind == "estimate_comparison_input_unavailable":
        return "Для этой части проекта не найден пригодный ВОР или сметный документ для сравнения."
    if kind == "incompatible_units":
        return (
            "Проектный и коммерческий объёмы указаны в разных единицах без "
            "подтверждённого коэффициента пересчёта."
        )
    return str(parameters.get("description") or _issue_title(kind))


def _issue_action(kind: str) -> str:
    if kind in {"quantity_mismatch", "material_quantity_mismatch", "incompatible_units"}:
        return (
            "Запросить у Заказчика подтверждение применяемого значения, единицы "
            "и документа-основания."
        )
    if kind in {"project_work_missing_in_estimate", "project_material_missing_in_estimate"}:
        return "Уточнить включение работы или материала в ВОР/смету и договорную цену."
    if kind == "estimate_position_unsupported_by_project":
        return (
            "Запросить проектное основание сметной позиции или исключить её из объёма предложения."
        )
    return (
        "Запросить недостающие исходные данные и зафиксировать границу ответственности "
        "в предложении."
    )


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _normalized(value: object) -> str:
    return " ".join(re.sub(r"[^0-9a-zа-яё.,]+", " ", str(value or "").casefold()).split())
