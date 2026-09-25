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

PROJECT_ENGINEERING_MODEL_VERSION = "project-engineering-model-v2"

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
        "bracing",
        "Распорки и раскрепление",
        ("распорк", "раскреп", "подкос"),
    ),
    (
        "dewatering",
        "Водопонижение и водоотлив",
        ("водопонижен", "водоотлив", "откачк грунтов", "откачк вод"),
    ),
    (
        "backfill",
        "Обратная засыпка",
        ("обратн засып", "засыпк транше", "засыпк котлован", "засыпк пазух"),
    ),
    (
        "compaction",
        "Уплотнение грунта",
        ("уплотнен грунт", "трамбовк"),
    ),
    (
        "excavation",
        "Разработка котлованов и земляные работы",
        ("котлован", "разработк грунт", "землян", "выемк грунт"),
    ),
    (
        "reinforcement",
        "Армирование",
        ("армирован", "арматурн каркас", "арматурн сетк", "установк арматур"),
    ),
    (
        "formwork",
        "Опалубочные работы",
        ("опалуб",),
    ),
    (
        "pit_preparation",
        "Подготовка основания",
        (
            "бетонн подготов",
            "песчан основан",
            "щебеночн основан",
            "основан под фундамент",
            "подготовк из бетон",
        ),
    ),
    (
        "reinforced_concrete",
        "Бетонные и железобетонные работы",
        ("железобетон", "бетонирован", "бетонн работ", "монолитн конструкц"),
    ),
    (
        "foundation_slab",
        "Фундаменты и плиты",
        ("фундамент", "фундаментн плит", "плит основан", "монолитн плит"),
    ),
    (
        "walls",
        "Стены и перегородки",
        ("кладк стен", "кладк перегород", "возведен стен", "кирпич и блок"),
    ),
    (
        "pipeline",
        "Трубопроводы и сети",
        (
            "трубопровод",
            "прокладк труб",
            "укладк стальн водопроводн труб",
            "ливнев канализац",
            "коллектор",
        ),
    ),
    (
        "pile_foundation",
        "Свайные работы",
        ("свайн работ", "устройств свай", "погружен свай", "забивк свай"),
    ),
    (
        "chambers_wells",
        "Колодцы, камеры и технологические сооружения",
        (
            "монтаж колодц",
            "устройств колодц",
            "монтаж камер",
            "устройств камер",
            "установк канализационн насосн станц",
            "монтаж очистн сооружен",
            "устройств локальн очистн сооружен",
            "строительств локальн очистн сооружен",
        ),
    ),
    (
        "embedded_parts",
        "Закладные детали",
        ("закладн детал", "закладн издел", "закладн част"),
    ),
    (
        "structural_steel",
        "Металлоконструкции",
        ("металлоконструк", "стальн конструкц", "металлическ конструкц"),
    ),
    (
        "waterproofing",
        "Гидроизоляция",
        ("гидроизоляц", "водоизоляц", "изоляц поверхност колодц", "битумн мастик"),
    ),
    (
        "temporary_works",
        "Временные сооружения и крепления",
        (
            "временн креплен",
            "временн огражден",
            "временн дорог",
            "временн сооружен",
            "строительн городок",
        ),
    ),
    (
        "soil_disposal",
        "Погрузка и вывоз грунта",
        ("вывоз грунт", "вывоз излишк грунт", "погрузк грунт"),
    ),
    (
        "demolition",
        "Демонтажные работы",
        ("демонтаж", "разборк"),
    ),
    (
        "landscaping",
        "Благоустройство и озеленение",
        ("благоустройств", "озеленен", "газон", "растительн земл"),
    ),
    (
        "roadworks",
        "Дорожные работы",
        ("дорожн покрыт", "асфальтобетон", "автомобильн дорог"),
    ),
    (
        "electrical",
        "Электромонтажные работы",
        ("электромонтаж", "электротехническ установ", "прокладк кабел"),
    ),
    (
        "equipment_installation",
        "Монтаж технологического оборудования",
        (
            "монтаж технологическ оборудован",
            "монтаж оборудован",
            "установк корпус",
            "монтаж кнс",
            "монтаж очистн сооружен",
        ),
    ),
    (
        "commissioning",
        "Пусконаладочные работы",
        ("пусконаладочн работ", "пуско наладочн работ"),
    ),
    (
        "testing",
        "Испытания и проверка",
        (
            "испытан на герметичн",
            "промывк систем",
            "гидравлическ испытан",
            "испытан трубопровод",
        ),
    ),
    (
        "surveying",
        "Геодезические работы",
        ("геодезическ разбив", "разбивочн основ", "камеральн работ"),
    ),
    (
        "site_preparation",
        "Подготовка строительной площадки",
        (
            "подготовительн работ",
            "освобожден строительн площадк",
            "вырубк дерев",
            "валк дерев",
            "складск площадк",
        ),
    ),
    (
        "reclamation",
        "Рекультивация",
        (
            "рекультивац",
            "плодородн сло",
            "восстановлен травян",
            "растительн грунт",
        ),
    ),
)

_NON_WORK_OBSERVATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Обобщённый заголовок без конкретной строительной операции",
        (
            "строительные работы",
            "строительно монтажные работы",
            "монтажные работы",
            "строительство",
            "монтаж",
            "материалы",
        ),
    ),
    (
        "Сметный ресурс или начисление, а не отдельная работа",
        (
            "оплата труда",
            "эксплуатация машин",
            "накладные расходы",
            "автомобили бортовые",
            "вода",
        ),
    ),
    (
        "Описание материала, а не строительной операции",
        (
            "смеси бетонные",
            "сталь арматурная",
            "песок природный",
            "щиты настила",
        ),
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
        _exact_work_comparisons(
            candidates.get("work_types", ()),
            candidates.get("quantities", ()),
            source_context,
        )
    )
    scope_comparisons = _scope_comparisons(work_model["works"])
    sheet_pile_schedule = _sheet_pile_schedule(work_model["works"])
    issues = _issues(
        defects,
        comparisons,
        scope_comparisons,
        sheet_pile_schedule,
        work_model["works"],
        source_context,
    )
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
        "excluded_non_work_observations": work_model["excluded"],
        "work_classification": work_model["classification"],
        "quantity_comparisons": comparisons,
        "scope_comparisons": scope_comparisons,
        "sheet_pile_schedule": sheet_pile_schedule,
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
            "excluded_non_work_observation_count": len(work_model["excluded"]),
            "classified_work_observation_count": work_model["classification"][
                "classified_observation_count"
            ],
            "total_work_observation_count": work_model["classification"]["total_observation_count"],
            "classified_work_percent": work_model["classification"]["classified_percent"],
            "facility_assigned_work_observation_count": work_model["classification"][
                "facility_assigned_observation_count"
            ],
            "quantity_comparison_count": len(comparisons),
            "scope_comparison_count": len(scope_comparisons),
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
        if any(_ordered_stem_phrase(normalized, term) for term in terms):
            return key, title
    return None


def non_work_reason(value: object) -> str | None:
    """Identify extracted headings/resources that are not construction operations."""

    normalized = _normalized(value)
    for reason, exact_values in _NON_WORK_OBSERVATIONS:
        if normalized in exact_values or any(
            normalized.startswith(f"{item} ") for item in exact_values if len(item) > 8
        ):
            return reason
    if re.fullmatch(r"\d+(?:[.-]\d+){2,}", normalized):
        return "Сметный шифр без описания строительной операции"
    return None


def _ordered_stem_phrase(normalized: str, phrase: str) -> bool:
    """Match a short engineering phrase by ordered Russian word stems.

    Extraction preserves inflection (``разработка``/``разработке``), while the
    compact work-family contract deliberately stores stable stems.  Requiring
    every stem in order is more conservative than an unordered keyword bag and
    still groups inflected wording without an OZERO-specific dictionary.
    """

    stems = tuple(value for value in phrase.split() if value)
    if not stems:
        return False
    pattern = r"\b" + r"\w*\s+\w*".join(re.escape(value) for value in stems) + r"\w*\b"
    return re.search(pattern, normalized) is not None


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
            description = str(pit.get("display_name") or pit.get("canonical_label") or "Котлован")
            stated_count_match = re.search(r"\b(\d+)\s*шт", _normalized(description))
            stated_count = int(stated_count_match.group(1)) if stated_count_match else None
            paired_working_receiving = "рабоч" in _normalized(
                description
            ) and "приемн" in _normalized(description)
            if stated_count is not None:
                reason = (
                    f"В документе указано {stated_count} шт., но нет поштучных марок и "
                    "привязки, позволяющих исключить пересечение с другими группами."
                )
            elif paired_working_receiving:
                reason = (
                    "Указаны рабочие и приёмные котлованы переходов (не менее двух), "
                    "но число переходов и их поштучные марки не установлены."
                )
            elif any("котлованы" in _normalized(value) for value in aliases):
                reason = (
                    "Указана группа котлованов без количества, поштучных марок и "
                    "однозначной привязки к сооружениям."
                )
            else:
                reason = (
                    "Упоминание отдельного котлована не содержит марки сооружения; "
                    "нельзя исключить повторное упоминание уже установленного котлована."
                )
            clarification.append(
                {
                    "description": description,
                    "related_facility": pit.get("associated_facility_designation"),
                    "reason": reason,
                    "stated_count": stated_count,
                    "minimum_count": 2 if paired_working_receiving else stated_count,
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
    quantified_group_count = sum(
        int(value["stated_count"])
        for value in clarification
        if value.get("stated_count") is not None
    )
    stated_minimum_count = sum(
        int(value["minimum_count"])
        for value in clarification
        if value.get("minimum_count") is not None
    )
    return {
        "established": established,
        "established_count": len(established),
        "requires_clarification": clarification,
        "unresolved_group_count": unresolved_count,
        "quantified_unresolved_group_pit_count": quantified_group_count,
        "stated_minimum_unresolved_pit_count": stated_minimum_count,
        "ambiguous_observation_count": ambiguous_count,
        "is_final": unresolved_count == 0,
        "professional_answer": (
            f"В проекте {_russian_pit_count(len(established), established=True)}."
            if unresolved_count == 0
            else f"{_russian_pit_count(len(established), established=True).capitalize()}. "
            f"Ещё {unresolved_count} {_russian_group_word(unresolved_count)} обозначений "
            + ("требует уточнения. " if unresolved_count == 1 else "требуют уточнения. ")
            + (
                f"В двух группах прямо указано суммарно {quantified_group_count} шт., "
                "но их пересечение с другими обозначениями не исключено. "
                if quantified_group_count
                else ""
            )
            + (
                f"С учётом явно названной пары рабочих и приёмных котлованов в "
                f"неразрешённых группах описано не менее {stated_minimum_count} котлованов, "
                "однако часть из них может повторять уже установленные объекты. "
                if stated_minimum_count > quantified_group_count
                else ""
            )
            + "Поэтому окончательное количество по имеющимся данным пока не установлено."
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
    work_rows = [dict(raw) for raw in works]
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
    # A unique explicit designation elsewhere on the same drawing/estimate page
    # is a stronger engineering basis than document co-occurrence.  Pages that
    # mention several facilities remain unassigned.
    for row in work_rows:
        name = str(row.get("value") or row.get("raw_name") or "")
        designation = facility_designation(f"{name} {row.get('scope_key') or ''}")
        facility = facility_by_designation.get(designation or "")
        context = source_context.get(str(row.get("source_locator_id") or ""))
        if facility is None or not isinstance(context, Mapping):
            continue
        locator_value = context.get("locator_value")
        page = locator_value.get("page") if isinstance(locator_value, Mapping) else None
        if page is not None:
            facility_ids_by_page[(str(context.get("source_version_id") or ""), int(page))].add(
                str(facility["facility_id"])
            )
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
    excluded: list[dict[str, Any]] = []
    for row in work_rows:
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
                assignment_basis = (
                    "Работа отнесена к единственному явно обозначенному сооружению на листе"
                )
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
                reason = non_work_reason(name)
                if reason:
                    excluded.append({**observation, "exclusion_reason": reason})
                else:
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
        sources_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for observation in observations:
            role = str(observation["document_role"])
            quantities_by_role[role].extend(observation["quantities"])
            materials_by_role[role].extend(observation["materials"])
            if observation.get("source"):
                sources_by_role[role].append(dict(observation["source"]))
        quantities_by_role = {
            key: _deduplicate_dicts(value) for key, value in quantities_by_role.items()
        }
        materials_by_role = {
            key: _deduplicate_dicts(value) for key, value in materials_by_role.items()
        }
        sources_by_role = {key: _deduplicate_dicts(value) for key, value in sources_by_role.items()}
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
            "document_roles": sorted({str(item["document_role"]) for item in observations}),
            "sources_by_document": sources_by_role,
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
    excluded = _deduplicate_dicts(excluded)
    classified_count = len(exact_observations)
    assigned_count = len(
        [value for value in exact_observations.values() if value.get("facility_id")]
    )
    total_count = classified_count + len(unclassified) + len(excluded)
    return {
        "works": schedules,
        "materials": material_rows,
        "unclassified": unclassified,
        "excluded": excluded,
        "classification": {
            "total_observation_count": total_count,
            "classified_observation_count": classified_count,
            "unclassified_observation_count": len(unclassified),
            "excluded_non_work_observation_count": len(excluded),
            "classified_percent": (
                round(classified_count * 100 / total_count, 1) if total_count else 0.0
            ),
            "facility_assigned_observation_count": assigned_count,
            "facility_unassigned_observation_count": classified_count - assigned_count,
            "policy": (
                "Упорядоченные инженерные термины и явные обозначения; одинаковые слова "
                "без контекста не объединяют разные работы или сооружения."
            ),
        },
    }


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


def _scope_comparisons(works: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Classify design/commercial coverage for the same engineering family.

    This does not call a design item omitted merely because its exact wording is
    absent.  When a commercial row exists for the family but lacks a facility
    allocation, the result is explicitly an unresolved scope match.
    """

    rows = [dict(value) for value in works]
    design_roles = {"ПД", "РД", "Спецификация"}
    commercial_roles = {"ВОР", "Смета"}
    commercial_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        roles = set(str(value) for value in row.get("document_roles") or ())
        if roles.intersection(commercial_roles):
            commercial_by_family[str(row.get("family_key") or "")].append(row)

    result: list[dict[str, Any]] = []
    for row in rows:
        roles = set(str(value) for value in row.get("document_roles") or ())
        design = roles.intersection(design_roles)
        commercial = roles.intersection(commercial_roles)
        if not design:
            if commercial:
                status = "COMMERCIAL_ONLY_WORK"
                conclusion = "Коммерческая позиция пока не связана с проектным объёмом."
            else:
                continue
        elif commercial:
            status = "MATCH"
            conclusion = "Проектная и коммерческая позиции найдены в одном инженерном объёме."
        else:
            possible = commercial_by_family.get(str(row.get("family_key") or ""), [])
            if possible:
                status = "UNRESOLVED_SCOPE_MATCH"
                conclusion = (
                    "Коммерческие позиции этого вида найдены, но их нельзя однозначно "
                    "распределить по сооружениям."
                )
            else:
                status = "WORK_MISSING_IN_COMMERCIAL"
                conclusion = (
                    "Работа установлена в проектных документах, но соответствующая позиция "
                    "не найдена в имеющихся ВОР/сметах."
                )
        result.append(
            {
                "scope_comparison_id": semantic_digest(
                    {
                        "work_scope_id": row.get("work_scope_id"),
                        "status": status,
                    }
                ),
                "classification": status,
                "professional_status": {
                    "MATCH": "Состав сопоставлен",
                    "WORK_MISSING_IN_COMMERCIAL": "Возможная неучтённая работа",
                    "COMMERCIAL_ONLY_WORK": "Коммерческая позиция без установленного основания",
                    "UNRESOLVED_SCOPE_MATCH": "Требуется распределить коммерческий объём",
                }[status],
                "facility": row.get("facility"),
                "facility_id": row.get("facility_id"),
                "family_key": row.get("family_key"),
                "work": row.get("work_name"),
                "design_roles": sorted(design),
                "commercial_roles": sorted(commercial),
                "conclusion": conclusion,
                "source_locator_ids": list(row.get("source_locator_ids") or ()),
            }
        )
    return _deduplicate_dicts(result)


def _sheet_pile_schedule(works: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a professional sheet-pile/waling schedule without false totals."""

    result: list[dict[str, Any]] = []
    relevant_families = {"sheet_piling", "waling_beam", "bracing"}
    for raw in works:
        row = dict(raw)
        materials = dict(row.get("materials_by_document") or {})
        wording = [str(value) for value in row.get("project_wording") or ()]
        material_names = [
            str(value.get("name") or "") for values in materials.values() for value in values or ()
        ]
        combined = " ".join([*wording, *material_names])
        normalized = _normalized(combined)
        unassigned_profile_observation = row.get("family_key") not in relevant_families and bool(
            re.search(r"\bл5(?:ум|\s*10)?\b", normalized)
        )
        if row.get("family_key") not in relevant_families and not unassigned_profile_observation:
            continue
        profiles = _sheet_pile_profiles(normalized)
        profiles_by_document = {
            role: _sheet_pile_profiles(
                _normalized(" ".join(str(value.get("name") or "") for value in values or ()))
            )
            for role, values in materials.items()
            if _sheet_pile_profiles(
                _normalized(" ".join(str(value.get("name") or "") for value in values or ()))
            )
        }
        beams = _ordered_unique(
            match.group(0).upper() for match in re.finditer(r"\b(?:30ш2|35ш2)\b", normalized)
        )
        steel = _ordered_unique(
            match.group(0).upper() for match in re.finditer(r"\bс\s*255\b", normalized)
        )
        lengths = _ordered_unique(
            f"{match.group(1)}–{match.group(2)} м"
            for match in re.finditer(r"длин\w*\s+(?:свыше\s+)?(\d+)\s+до\s+(\d+)\s*м", normalized)
        )
        quantities = dict(row.get("quantities_by_document") or {})
        profile_locator_ids = sorted(
            {
                str(value.get("source_locator_id"))
                for values in materials.values()
                for value in values or ()
                if _sheet_pile_profiles(_normalized(value.get("name")))
                and value.get("source_locator_id")
            }
        )
        if unassigned_profile_observation:
            # The profile observation is useful, but the extractor associated it
            # with a non-sheet-pile work.  Keep the exact material observation and
            # its locator without inheriting unrelated excavation quantities.
            quantities = {}
        else:
            quantities = {
                role: _consolidate_quantity_mentions(values) for role, values in quantities.items()
            }
        project_roles = {
            key: value for key, value in quantities.items() if key in {"ПД", "РД", "Спецификация"}
        }
        commercial_roles = {
            key: value for key, value in quantities.items() if key in {"ВОР", "Смета"}
        }
        result.append(
            {
                "sheet_pile_scope_id": semantic_digest(
                    {"work_scope_id": row.get("work_scope_id"), "kind": "sheet_pile_schedule"}
                ),
                "facility": row.get("facility"),
                "facility_id": row.get("facility_id"),
                "pit": (
                    f"Котлован {row.get('facility')}"
                    if row.get("facility_id")
                    else "Требует привязки"
                ),
                "operation": (
                    "Материал шпунтового ограждения — привязка требует уточнения"
                    if unassigned_profile_observation
                    else row.get("work_name")
                ),
                "profiles": profiles,
                "profiles_by_document": profiles_by_document,
                "pile_length": lengths,
                "quantities_by_document": quantities,
                "project_quantities": project_roles,
                "commercial_quantities": commercial_roles,
                "waling_beams": beams,
                "steel": steel,
                "project_wording": wording,
                "source_locator_ids": (
                    profile_locator_ids
                    if unassigned_profile_observation
                    else list(row.get("source_locator_ids") or ())
                ),
                "sources_by_document": (
                    {}
                    if unassigned_profile_observation
                    else dict(row.get("sources_by_document") or {})
                ),
                "uncertainty": (
                    "Наблюдение о профиле найдено, но связь с конкретной шпунтовой работой "
                    "и сооружением не установлена."
                    if unassigned_profile_observation
                    else "Коммерческий объём не распределён по сооружениям."
                    if row.get("facility_id") is None and commercial_roles
                    else "Место выполнения требует уточнения."
                    if row.get("facility_id") is None
                    else None
                ),
            }
        )
    return result


def _issues(
    defects: Iterable[Mapping[str, Any]],
    comparisons: Iterable[Mapping[str, Any]],
    scope_comparisons: Iterable[Mapping[str, Any]],
    sheet_pile_schedule: Iterable[Mapping[str, Any]],
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
    omission_families = {
        "waling_beam",
        "bracing",
        "dewatering",
        "pit_preparation",
        "formwork",
        "reinforcement",
        "waterproofing",
        "backfill",
    }
    for comparison in scope_comparisons:
        if comparison.get("classification") != "WORK_MISSING_IN_COMMERCIAL":
            continue
        if comparison.get("family_key") not in omission_families:
            continue
        if not comparison.get("facility_id"):
            continue
        locators = [str(value) for value in comparison.get("source_locator_ids") or ()]
        issues.append(
            {
                "issue_id": str(comparison["scope_comparison_id"]),
                "kind": "Возможная неучтённая работа",
                "location": comparison.get("facility"),
                "subject": comparison.get("work"),
                "description": str(comparison.get("conclusion") or ""),
                "practical_consequence": (
                    "При отсутствии этой позиции в коммерческом объёме работа может остаться "
                    "нерасценённой и потребовать дополнительного согласования."
                ),
                "recommended_action": (
                    f"Просим подтвердить включение работы «{comparison.get('work')}» для "
                    f"{comparison.get('facility')} в ВОР/смету либо выдать отдельную позицию."
                ),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Возможное отсутствие — требуется подтверждение Заказчика",
            }
        )

    design_profiles: dict[str, set[str]] = defaultdict(set)
    commercial_profiles: dict[str, set[str]] = defaultdict(set)
    profile_locators: set[str] = set()
    for row in sheet_pile_schedule:
        for role, values in dict(row.get("profiles_by_document") or {}).items():
            target = commercial_profiles if role in {"ВОР", "Смета"} else design_profiles
            target[str(role)].update(str(value) for value in values or ())
            profile_locators.update(str(value) for value in row.get("source_locator_ids") or ())
    design_values = sorted({value for values in design_profiles.values() for value in values})
    commercial_values = sorted(
        {value for values in commercial_profiles.values() for value in values}
    )
    if design_values and commercial_values and set(design_values) != set(commercial_values):
        locators = sorted(profile_locators)
        issues.append(
            {
                "issue_id": semantic_digest(
                    {
                        "kind": "sheet_pile_profile_scope_unresolved",
                        "design_profiles": design_values,
                        "commercial_profiles": commercial_values,
                        "locators": locators,
                    }
                ),
                "kind": "Профиль шпунта требует согласования",
                "location": "Шпунтовые ограждения проекта",
                "subject": "Профиль шпунта",
                "description": (
                    f"В проектных разделах найдено обозначение {', '.join(design_values)}, "
                    f"а в сметных позициях — {', '.join(commercial_values)}. Коммерческие "
                    "позиции не распределены по сооружениям, поэтому это пока не доказанная "
                    "замена, а существенная неопределённость соответствия."
                ),
                "practical_consequence": (
                    "Без пообъектной увязки профиля нельзя подтвердить массу, стоимость, "
                    "возможность повторного использования и соответствие расчётному решению."
                ),
                "recommended_action": (
                    "Просим подтвердить применяемый профиль шпунта по каждому котловану и "
                    "увязать обозначения Л5УМ, Л5 и Л5-10 с расчётами и сметными позициями."
                ),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Требуется пообъектная увязка проектных и сметных обозначений",
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


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _consolidate_quantity_mentions(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated document mentions without summing overlapping scopes."""

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in values:
        row = dict(raw)
        key = (str(row.get("value") or ""), str(row.get("unit") or ""))
        current = grouped.setdefault(
            key,
            {
                "value": row.get("value"),
                "unit": row.get("unit"),
                "occurrence_count": 0,
                "source_locator_ids": [],
            },
        )
        current["occurrence_count"] += 1
        if row.get("source_locator_id"):
            current["source_locator_ids"] = sorted(
                {
                    *current["source_locator_ids"],
                    str(row["source_locator_id"]),
                }
            )
    return [grouped[key] for key in sorted(grouped)]


def _sheet_pile_profiles(normalized: str) -> list[str]:
    profiles: list[str] = []
    for match in re.finditer(r"\bл5(?:ум|\s*10)?\b", normalized):
        value = match.group(0).upper().replace(" ", "-")
        profiles.append(value)
    return _ordered_unique(profiles)


def _normalized(value: object) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё.,]+", " ", str(value or "").casefold().replace("ё", "е")).split()
    )
