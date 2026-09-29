"""Practical construction-project model and Tender analysis.

This module turns already persisted extraction observations into professional
project concepts.  It deliberately keeps implementation diagnostics out of the
normal result while retaining document/page references for inspection.
"""

# ruff: noqa: RUF001 -- Russian construction language is intentional.

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest

PROJECT_ENGINEERING_MODEL_VERSION = "project-engineering-model-v50"
_QUANTITY_AWARE_WORK_PROFILES = frozenset(
    {
        "qwen-project-work-reconciliation-v5",
        "qwen-project-work-reconciliation-v6",
        "qwen-project-work-reconciliation-v7",
        "qwen-project-work-reconciliation-v8",
    }
)
_CANONICAL_SEMANTIC_OPERATION_FAMILIES = frozenset(
    {
        "sheet_piling",
        "waling_beam",
        "excavation",
        "soil_disposal",
        "pipeline",
        "pit_preparation",
        "chambers_wells",
        "electrical",
        "gabion_erosion_protection",
        "waste_management",
        "pile_foundation",
        "reinforced_concrete",
        "equipment_installation",
        "testing",
    }
)
_UNSCOPED_GENERIC_OPERATIONS = frozenset(
    {
        "Монтаж трубопровода",
        "Железобетонные конструкции",
        "Колодцы, камеры и технологические сооружения",
        "Электромонтажные работы",
        "Дорожные работы",
        "Подготовка основания",
        "Подготовка строительной площадки",
        "Монтаж технологического оборудования",
    }
)

_FACILITY_CODE = re.compile(
    r"\b(?P<kind>лос|кнс)\s*[-№nº]*\s*(?P<number>\d+(?:[.,]\d+)?[а-я]?)\b",
    re.IGNORECASE,
)
_REVERSED_FACILITY_CODE = re.compile(
    r"\b(?P<number>\d+(?:[.,]\d+)?[а-я]?)\s*[-№nº]*\s*(?P<kind>лос|кнс)\b",
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
        (
            "распорк",
            "раскреп",
            "подкос",
            "укреплен стенок транше",
            "креплен стенок транше",
        ),
    ),
    (
        "dewatering",
        "Водопонижение и водоотлив",
        (
            "водопонижен",
            "водоотлив",
            "откачк грунтов",
            "откачк вод",
            "иглофильтр",
            "водопонижающ установк",
            "водопонизительн насос",
        ),
    ),
    (
        "backfill",
        "Обратная засыпка",
        (
            "обратн засып",
            "засыпк транше",
            "засыпк вручн транш",
            "засыпк котлован",
            "засыпк пазух",
            "окончательн засып",
            "обваловк из песк",
        ),
    ),
    (
        "compaction",
        "Уплотнение грунта",
        (
            "уплотнен грунт",
            "уплотнен кажд сло",
            "уплотнен вокруг наружн поверхност колодц",
            "утрамбовк грунт",
            "трамбовк",
        ),
    ),
    (
        "excavation",
        "Разработка котлованов и земляные работы",
        (
            "котлован",
            "разработк грунт",
            "доработк грунт",
            "землян",
            "выемк грунт",
            "объем выемк",
            "отрывк транше",
            "разработк транше",
            "устройств транше",
            "срезк загрязнен грунт",
            "выемк загрязнен грунт",
            "откопк",
            "дноуглубительн работ",
            "перемещен грунт",
            "рыть транше",
            "зачистк дн откос транше",
            "замещен загрязнен грунт",
        ),
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
        "waterproofing",
        "Гидроизоляция",
        (
            "гидроизоляц",
            "водоизоляц",
            "изоляц поверхност колодц",
            "битумн мастик",
            "нанесен праймер битумн",
        ),
    ),
    (
        "pit_preparation",
        "Подготовка основания",
        (
            "бетонн подготов",
            "песчан основан",
            "подсыпк песк",
            "щебеночн основан",
            "основан под фундамент",
            "подготовк из бетон",
        ),
    ),
    (
        "reinforced_concrete",
        "Бетонные и железобетонные работы",
        (
            "железобетон",
            "бетонирован",
            "бетонн работ",
            "монолитн конструкц",
            "заполнен полост бетон",
            "заделк шв бетон",
            "бетонн обойм",
        ),
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
        "electrical",
        "Электромонтажные работы",
        (
            "электромонтаж",
            "электротехническ установ",
            "прокладк кабел",
            "монтаж силов кабел",
            "монтаж кабел",
            "монтаж шкаф управлен",
            "монтаж светильник",
            "покрыт кабел лент",
            "покрыт кабел",
            "монтаж систем электроснабжен",
            "монтаж опор освещен",
            "установк опор наружн освещен",
            "установк светильник",
            "монтаж систем наружн электроосвещен",
        ),
    ),
    (
        "pipeline",
        "Трубопроводы и сети",
        (
            "трубопровод",
            "прокладк труб",
            "укладк труб",
            "монтаж труб",
            "укладк стальн водопроводн труб",
            "ливнев канализац",
            "коллектор",
            "устройств оголовк",
            "монтаж запорно регулирующ арматур",
            "сварк пластмассов труб",
            "установк задвиж",
            "установк клапан обратн",
            "ввод инженерн сет",
        ),
    ),
    (
        "pile_foundation",
        "Свайные работы",
        (
            "свайн работ",
            "устройств свай",
            "погружен свай",
            "забивк свай",
            "закручиван винтов свай",
            "выкручиван винтов свай",
        ),
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
            "дополнительн колодц",
            "установк кругл колодц",
            "установк стеклокомпозитн колодц",
            "обрезк горловин колодц",
            "установк люк",
            "затирк цементн раствор шв",
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
        (
            "металлоконструк",
            "стальн конструкц",
            "металлическ конструкц",
            "монтаж лестниц",
            "установк лестниц из алюмин",
            "установк трубчат металлическ стоек",
        ),
    ),
    (
        "gabion_erosion_protection",
        "Габионные и берегоукрепительные работы",
        (
            "монтаж габион",
            "устройств габион",
            "габионн конструкц",
            "защит от размыв грунт",
            "берегоукреп",
        ),
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
        (
            "вывоз грунт",
            "вывоз излишк грунт",
            "вывоз загрязнен грунт",
            "погрузк грунт",
        ),
    ),
    (
        "transportation",
        "Перевозка строительных грузов и материалов",
        (
            "перевозк",
            "транспортирован",
            "транспортировк",
            "доставк оборудован",
            "доставк материал",
            "доставк перемещен на строительн площадк",
            "перемещен строительн техник",
            "привоз чист грунт",
        ),
    ),
    (
        "loading_unloading",
        "Погрузочно-разгрузочные работы",
        ("погрузочн разгрузочн работ", "погрузо разгрузочн работ"),
    ),
    (
        "waste_management",
        "Обращение со строительными отходами",
        (
            "сбор отход",
            "сбор и размещен",
            "обработк отход",
            "размещен отход",
            "размещен строительн",
            "утилизац отход",
            "захоронен отход",
            "вывоз строительн мусор",
            "вывоз промышлен отход",
            "погрузк мусор строительн",
            "погрузк в автотранспортн средств мусор",
            "временн хранен строительн бытов отход",
        ),
    ),
    (
        "demolition",
        "Демонтажные работы",
        ("демонтаж", "разборк"),
    ),
    (
        "landscaping",
        "Благоустройство и озеленение",
        (
            "благоустройств",
            "озеленен",
            "газон",
            "растительн земл",
            "посев трав",
            "засев грунт многолетн трав",
            "внесен удобрен",
        ),
    ),
    (
        "roadworks",
        "Дорожные работы",
        (
            "дорожн покрыт",
            "асфальтобетон",
            "автомобильн дорог",
            "бортов камн",
            "розлив битумн эмульс",
            "тротуарн покрыт",
            "восстановлен асфальтобетон",
            "восстановлен тротуар",
            "восстановлен бортов",
            "восстановлен экологическ троп",
            "устройств основан покрыт песчан гравийн",
            "дополнительн сло основан",
            "обработк основан цемент",
            "устройств покрыт дорожек",
        ),
    ),
    (
        "communications",
        "Сети связи и автоматизации",
        ("сет связ", "слаботочн сет", "кабел связ"),
    ),
    (
        "equipment_installation",
        "Монтаж технологического оборудования",
        (
            "монтаж технологическ оборудован",
            "монтаж оборудован",
            "монтаж насосн оборудован",
            "установк корпус",
            "установк емкост",
            "монтаж кнс",
            "монтаж лос",
            "монтаж очистн сооружен",
            "монтаж канализационн насосн станц",
            "шеф монтажн работ",
            "монтаж контейнер",
            "монтаж дополнительн соединительн элемент",
            "установк пескоуловител",
            "установк систем вентиляц",
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
            "испытан очистн сооружен герметичн",
            "промывк систем",
            "гидравлическ испытан",
            "испытан трубопровод",
            "лабораторн контроль",
            "визуальн контрол качеств",
            "входн контрол",
            "отбор проб",
        ),
    ),
    (
        "surveying",
        "Геодезические работы",
        (
            "геодезическ работ",
            "геодезическ разбив",
            "разбивочн основ",
            "камеральн работ",
        ),
    ),
    (
        "site_preparation",
        "Подготовка строительной площадки",
        (
            "подготовительн работ",
            "освобожден строительн площадк",
            "вырубк дерев",
            "валк дерев",
            "корчевк пн",
            "выкорчевыван пн",
            "расчистк площад",
            "складск площадк",
            "складск площад",
            "вертикальн планировк",
            "планировк площад",
            "устройств насыпи",
            "планировк поверхност откос",
            "планировочн работ",
            "планировк поверхност",
            "вырубк",
            "удален дерев",
            "удален кустарник",
            "снос зелен насажден",
            "вывоз лес",
            "мобильн инвентарн здан",
            "погрузк порубочн материал",
            "разделк древесин",
            "трелевк",
        ),
    ),
    (
        "reclamation",
        "Рекультивация",
        (
            "рекультивац",
            "плодородн сло",
            "псп",
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
            "строительных работ",
            "строительно монтажные работы",
            "монтажные работы",
            "монтажных работ",
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
            "сметная прибыль",
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
            "оборудования",
        ),
    ),
    (
        "Эксплуатационная операция, а не строительная работа",
        (
            "техническое обслуживание",
            "текущий ремонт",
            "визуальный осмотр",
            "поверхностный осмотр",
            "проверка состояния",
            "предварительное отстаивание",
            "пескоулавливание",
            "учет аэрации",
            "двухступенчатое фильтрование",
        ),
    ),
)

_CONSTRUCTION_OPERATION_MARKERS = (
    "устройств",
    "монтаж",
    "демонтаж",
    "разработк",
    "укладк",
    "погруж",
    "извлеч",
    "армирован",
    "бетонирован",
    "засыпк",
    "уплотнен",
    "испытан",
    "прокладк",
    "сварк",
    "изоляц",
    "вывоз",
    "погруз",
    "планировк",
    "заливк",
    "окраск",
    "бурен",
    "забивк",
    "восстановлен",
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
    work_resolutions: Mapping[str, Mapping[str, Any]] | None = None,
    structure_relationships: Iterable[Mapping[str, Any]] = (),
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
        structure_relationships,
        source_context,
        work_resolutions or {},
    )
    pits = _attach_pit_work_scopes(pits, work_model["works"])
    comparisons = _deduplicate_dicts(_validated_scope_quantity_comparisons(work_model["works"]))
    documents = _documents(source_context)
    document_composition = _document_composition(documents, source_context=source_context)
    scope_comparisons = _scope_comparisons(
        work_model["works"],
        unclassified_works=work_model["unclassified"],
        available_document_roles=document_composition["available_roles"],
    )
    sheet_pile_schedule = _sheet_pile_schedule(work_model["works"], source_context, pits=pits)
    material_comparisons = _material_comparisons(work_model["works"], source_context)
    issues = _issues(
        defects,
        comparisons,
        scope_comparisons,
        sheet_pile_schedule,
        work_model["works"],
        source_context,
        material_comparisons=material_comparisons,
    )
    requirements = _requirements(matrix, normative_profile)
    actions, risks = _actions_and_risks(issues)
    facility_cards = _facility_cards(
        facilities,
        pits,
        work_model["works"],
        comparisons,
        issues,
        candidates.get("project_fields", ()),
        structure_relationships,
        source_context,
    )
    unresolved = {
        "facility_designations": [
            item for item in facilities if item["status"] == "Требует уточнения"
        ],
        "pits": list(pits["requires_clarification"]),
        "works": list(work_model["unclassified"]),
        "quantities": [
            {
                "work_scope_id": work.get("work_scope_id"),
                "facility": work.get("facility"),
                "work": work.get("work_name"),
                **dict(value),
            }
            for work in work_model["works"]
            for value in work.get("quantity_interpretations") or ()
            if value.get("status") in {"AMBIGUOUS", "UNREVIEWED"}
        ],
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
        "material_comparisons": material_comparisons,
        "requirements": requirements,
        "issues": issues,
        "risks": risks,
        "customer_questions": actions,
        "documents": documents,
        "document_composition": document_composition,
        "unresolved": unresolved,
        "summary": {
            "facility_count": len([item for item in facilities if not item["is_alias_group"]]),
            "established_pit_count": int(pits["established_count"]),
            "pit_count_is_final": bool(pits["is_final"]),
            "work_scope_count": len(work_model["works"]),
            "unclassified_work_count": len(work_model["unclassified"]),
            "excluded_non_work_observation_count": len(work_model["excluded"]),
            "construction_scope_observation_count": work_model["classification"][
                "construction_scope_observation_count"
            ],
            "classified_work_observation_count": work_model["classification"][
                "classified_observation_count"
            ],
            "total_work_observation_count": work_model["classification"]["total_observation_count"],
            "classified_work_percent": work_model["classification"]["classified_percent"],
            "construction_scope_classified_percent": work_model["classification"][
                "construction_scope_classified_percent"
            ],
            "facility_assigned_work_observation_count": work_model["classification"][
                "facility_assigned_observation_count"
            ],
            "reviewed_quantity_observation_count": work_model["classification"][
                "reviewed_quantity_observation_count"
            ],
            "accepted_work_quantity_observation_count": work_model["classification"][
                "accepted_work_quantity_observation_count"
            ],
            "ambiguous_quantity_observation_count": work_model["classification"][
                "ambiguous_quantity_observation_count"
            ],
            "pending_quantity_observation_count": work_model["classification"][
                "pending_quantity_observation_count"
            ],
            "quantity_comparison_count": len(comparisons),
            "material_comparison_count": len(material_comparisons),
            "construction_quantity_comparison_count": len(
                [value for value in comparisons if value.get("comparison_kind") == "quantity"]
            ),
            "duration_comparison_count": len(
                [value for value in comparisons if value.get("comparison_kind") == "duration"]
            ),
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

    normalized = facility_designations(value)
    return normalized[0] if len(normalized) == 1 else None


def facility_designations(value: object) -> tuple[str, ...]:
    """Return every explicit LOS/KNS designation without merging their scopes."""

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
    return tuple(sorted(normalized))


def commercial_scope_facility_designation(value: object) -> str | None:
    """Resolve one facility named by a VOR/local-estimate section heading.

    Commercial documents commonly name a pumping station after the treatment
    facility it serves.  The served facility and the station are different, so the generic
    designation parser must not attach that scope to the LOS.  A heading that
    names more than one actual facility otherwise remains unresolved.
    """

    text = str(value or "")
    served_los = re.search(
        r"\bкнс\s+для\s+лос\s*[-№nº]*\s*(?P<number>\d+(?:[.,]\d+)?[а-я]?)\b",
        text,
        re.IGNORECASE,
    )
    if served_los is not None:
        return f"КНС {served_los.group('number').replace(',', '.').casefold()}"
    return facility_designation(text)


def _explicit_designation_alias(designation: str, aliases: Iterable[object]) -> bool:
    expected = _normalized(designation).replace("№", "")
    for alias in aliases:
        normalized = _normalized(alias).replace("№", "")
        if normalized in {expected, f"участок {expected}", f"сооружение {expected}"}:
            return True
    return False


def established_facility_designations(
    identity_components: Iterable[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return corroborated project facilities, excluding equipment model marks.

    A facility-shaped token can describe a pump-station product model.  It is
    not a project facility merely because that token was extracted.  The
    professional inventory requires an explicit alias and at least two source
    locators, matching the same rule used by facility cards.
    """

    established: set[str] = set()
    for raw in identity_components:
        component = dict(raw)
        if str(component.get("identity_kind") or "") not in {"facility", "local_area"}:
            continue
        label = str(component.get("canonical_label") or "").strip()
        designation = facility_designation(label)
        aliases = [
            str(value).strip()
            for value in component.get("candidate_labels") or (label,)
            if str(value).strip()
        ]
        if (
            designation
            and len({str(value) for value in component.get("source_locator_ids") or ()}) >= 2
            and _explicit_designation_alias(designation, aliases)
        ):
            established.add(designation)
    return tuple(sorted(established))


def classify_work_family(value: object) -> tuple[str, str] | None:
    normalized = _normalized(value)
    for key, title, terms in _WORK_FAMILIES:
        if any(_ordered_stem_phrase(normalized, term) for term in terms):
            return key, title
    return None


def work_family_catalog() -> dict[str, str]:
    """Return the reusable construction taxonomy accepted from local Qwen."""

    return {key: title for key, title, _terms in _WORK_FAMILIES}


def non_work_reason(value: object) -> str | None:
    """Identify extracted headings/resources that are not construction operations."""

    normalized = _normalized(value)
    for reason, exact_values in _NON_WORK_OBSERVATIONS:
        if normalized in exact_values or any(
            normalized.startswith((f"{item} ", f"{item},", f"{item}."))
            for item in exact_values
            if len(item) > 8
        ):
            return reason
    if re.fullmatch(r"\d+(?:[.,\s]\d+){2,}", normalized):
        return "Сметный шифр без описания строительной операции"
    if re.match(r"^\d+(?:[.-]\d+){2,}\s+", normalized):
        return "Сметный ресурс с кодом, а не отдельная строительная операция"
    if normalized.startswith(("отм зтм", "от зт", "зтм ", "зт ")):
        return "Сметный показатель трудозатрат, а не отдельная строительная операция"
    if normalized.startswith(("площадь ", "объем ", "объём ")):
        return "Проектный показатель или количество, а не отдельная строительная операция"
    if re.match(r"^бст\s+в\d", normalized):
        return "Описание бетонной смеси, а не отдельная строительная операция"
    return None


def construction_scope_exclusion_reason(document_title: object) -> str | None:
    """Keep operation/maintenance manuals out of the construction work schedule.

    Russian project documentation sections ТБЭ and СОЭ describe safe operation,
    maintenance and future repair of the completed asset.  Their verbs can look
    exactly like construction operations to a lexical classifier, but they do
    not define the contractor's current construction scope.  The observations
    remain traceable and excluded with this explicit reason instead of being
    presented as Tender works.
    """

    normalized = _normalized(document_title)
    if re.search(r"(?:^|\s)(?:тбэ|соэ)(?:[.\s]|$)", normalized):
        return (
            "Эксплуатационная/ремонтная операция из профильного раздела ПД, "
            "а не работа текущего строительства"
        )
    return None


def work_reconciliation_priority(
    value: object,
    *,
    document_role: object = None,
    nearby_context: object = None,
    has_facility_hint: bool = False,
    family_key: object = None,
    comparison_ready_scope: bool = False,
) -> tuple[int, int, int]:
    """Prioritize bounded semantic work by likely professional value.

    This does not classify a row.  It only keeps scarce local-Qwen slots from
    being consumed first by terse resource labels when descriptive construction
    operations from several project sources are waiting.  Validation and the
    model remain responsible for the actual interpretation.
    """

    wording = _normalized(value)
    context = _normalized(nearby_context)
    role = _normalized(document_role)
    operation_score = sum(marker in wording for marker in _CONSTRUCTION_OPERATION_MARKERS)
    facility_score = 48 if has_facility_hint else 0
    contextual_score = int(any(marker in context for marker in _CONSTRUCTION_OPERATION_MARKERS))
    commercial_score = int(role in {"bill of quantities", "local estimate", "object estimate"})
    priority_family_score = {
        "sheet_piling": 4,
        "waling_beam": 4,
        "bracing": 4,
        "excavation": 2,
        "reinforced_concrete": 2,
        "pipeline": 2,
        "waterproofing": 2,
    }.get(str(family_key or ""), 0)
    comparison_score = 90 if comparison_ready_scope else 0
    descriptive_score = min(len(wording.split()), 12)
    return (
        operation_score * 20
        + facility_score
        + contextual_score * 8
        + priority_family_score * 6
        + commercial_score * 3
        + comparison_score,
        # A scoped design/commercial pair can produce a professional Tender
        # comparison once its quantity meanings are checked.  Prefer it over
        # another isolated classification, without changing either row's
        # semantic decision or authority.
        descriptive_score,
        len(wording),
    )


def document_comparison_side(source_role: object, display_name: object) -> str | None:
    """Return the professional comparison side for one project source."""

    name = _normalized(display_name)
    role = str(source_role or "")
    if (
        "вор" in name
        or "ведомост объем" in name
        or "ведомост объём" in name
        or role == "bill_of_quantities"
    ):
        return "commercial"
    if (
        "смет" in name
        or re.search(r"(?:^|\s)см\d", name)
        or role in {"local_estimate", "object_estimate", "consolidated_estimate"}
    ):
        return "commercial"
    if role in {
        "project_documentation",
        "working_documentation",
        "specification",
        "explanatory_note",
        "drawing_or_scheme",
    }:
        return "design"
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
    # Allow at most two descriptive words between engineering stems.  Project
    # wording commonly inserts a material or condition (for example,
    # ``вывоз загрязненного грунта``), but an unbounded gap would turn this
    # conservative classifier into document-level keyword matching.
    separator = r"\w*(?:\s+\w+){0,2}\s+\w*"
    pattern = r"\b" + separator.join(re.escape(value) for value in stems) + r"\w*\b"
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
    if family_key == "excavation":
        if "загрязнен" in normalized:
            return "Выемка загрязнённого грунта"
        if "транше" in normalized:
            return "Разработка траншей"
        if "котлован" in normalized:
            return "Разработка котлована"
        return "Разработка грунта"
    if family_key == "backfill":
        if "транше" in normalized:
            return "Обратная засыпка траншей"
        if "котлован" in normalized or "пазух" in normalized:
            return "Обратная засыпка котлованов и пазух"
        return "Обратная засыпка"
    if family_key == "soil_disposal":
        return "Погрузка грунта" if "погруз" in normalized else "Вывоз грунта"
    if family_key == "pipeline":
        if "демонтаж" in normalized or "разбор" in normalized:
            return "Демонтаж трубопровода"
        if "испытан" in normalized or "опрессов" in normalized:
            return "Испытание трубопровода"
        if "промыв" in normalized or "очистк" in normalized:
            return "Очистка/промывка трубопровода"
        if "восстанов" in normalized or "ремонт" in normalized or "санац" in normalized:
            return "Восстановление/ремонт трубопровода"
        if "вскрыт" in normalized:
            return "Вскрытие трубопровода"
        if "изоляц" in normalized:
            return "Изоляция трубопровода"
        if "основан" in normalized or "подушк" in normalized:
            return "Устройство основания под трубопровод"
        if "подключ" in normalized or "врезк" in normalized:
            return "Подключение трубопровода"
        if "ввод" in normalized and "инженерн" in normalized:
            return "Ввод инженерных сетей"
        return "Монтаж трубопровода"
    if family_key == "pit_preparation":
        if "бетон" in normalized:
            return "Устройство бетонной подготовки"
        if "щеб" in normalized:
            return "Устройство щебёночного основания"
        if "пес" in normalized:
            return "Устройство песчаного основания"
        return "Подготовка основания"
    if family_key == "chambers_wells":
        if "люк" in normalized:
            return "Установка люка"
        if "колод" in normalized:
            return "Устройство колодца"
        if "камер" in normalized:
            return "Устройство камеры"
        if "кнс" in normalized or "насосн станц" in normalized:
            return "Монтаж КНС"
        if "лос" in normalized or "очистн сооружен" in normalized:
            return "Монтаж ЛОС"
        return "Колодцы, камеры и технологические сооружения"
    if family_key == "electrical":
        if "лент" in normalized and "кабел" in normalized:
            return "Укладка сигнальной ленты над кабелем"
        if "опор" in normalized and "освещ" in normalized:
            return "Монтаж опор освещения"
        if "светильник" in normalized:
            return "Монтаж светильников"
        if "наружн" in normalized and "освещ" in normalized:
            return "Монтаж наружного освещения"
        if "кабел" in normalized:
            return "Прокладка кабеля"
        return "Электромонтажные работы"
    if family_key == "roadworks":
        if "основан" in normalized:
            return "Устройство дорожного основания"
        if "асфальт" in normalized or "покрыт" in normalized:
            return "Устройство дорожного покрытия"
        if "бортов" in normalized:
            return "Установка бортового камня"
        if "экологическ" in normalized and "троп" in normalized:
            return "Восстановление экологической тропы"
        return "Дорожные работы"
    if family_key == "site_preparation":
        if "вертикальн" in normalized or "планиров" in normalized:
            return "Вертикальная планировка"
        if "складск" in normalized:
            return "Устройство складских площадок"
        if "мобильн" in normalized or "инвентарн здан" in normalized:
            return "Размещение временных зданий"
        if "насып" in normalized:
            return "Устройство насыпи"
        if "выруб" in normalized or "валк" in normalized or "корчев" in normalized:
            return "Вырубка деревьев и кустарников"
        if "лес" in normalized or "древес" in normalized or "порубочн" in normalized:
            return "Вывоз порубочного материала"
        if "расчист" in normalized or "освобожден" in normalized:
            return "Расчистка строительной площадки"
        return "Подготовка строительной площадки"
    if family_key == "gabion_erosion_protection":
        if "габион" in normalized:
            return "Устройство габионных конструкций"
        return "Защита грунта и откосов от размыва"
    if family_key == "waste_management":
        if "погруз" in normalized:
            return "Погрузка строительных отходов"
        if "вывоз" in normalized:
            return "Вывоз строительных отходов"
        return "Обращение со строительными отходами"
    if family_key == "pile_foundation":
        if "выкручив" in normalized or "извлеч" in normalized or "демонтаж" in normalized:
            return "Извлечение/демонтаж свай"
        if "винтов" in normalized:
            return "Устройство винтовых свай"
        return "Устройство свай"
    if family_key == "reinforced_concrete":
        if "сборн" in normalized and ("монтаж" in normalized or "установ" in normalized):
            return "Монтаж сборных железобетонных конструкций"
        if "бетонирован" in normalized or "бетонн работ" in normalized:
            return "Бетонирование"
        return "Железобетонные конструкции"
    if family_key == "structural_steel":
        if "стоек" in normalized:
            return "Установка металлических стоек"
        if "лестниц" in normalized:
            return "Монтаж лестниц и ограждений"
        return "Металлоконструкции"
    if family_key == "equipment_installation":
        if "вентиляц" in normalized:
            return "Монтаж системы вентиляции"
        if "насосн" in normalized:
            return "Монтаж насосного оборудования"
        if "емкост" in normalized or "корпус" in normalized:
            return "Монтаж технологической ёмкости"
        if "кнс" in normalized:
            return "Монтаж КНС"
        if "лос" in normalized or "очистн сооружен" in normalized:
            return "Монтаж ЛОС"
        return "Монтаж технологического оборудования"
    if family_key == "testing":
        if "входн" in normalized and "контрол" in normalized:
            return "Входной контроль"
        if "герметич" in normalized:
            return "Испытание на герметичность"
        if "промыв" in normalized:
            return "Промывка системы"
        if "отбор" in normalized and "проб" in normalized:
            return "Отбор проб"
        if "лабораторн" in normalized:
            return "Лабораторный контроль"
        return "Испытания и проверка"
    if family_key == "reclamation":
        if "обратн" in normalized and ("псп" in normalized or "плодород" in normalized):
            return "Восстановление плодородного слоя почвы"
        if "псп" in normalized or "плодород" in normalized:
            return "Снятие и складирование плодородного слоя почвы"
        return "Рекультивация"
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
    components = [dict(raw) for raw in identity_components]

    def establishes_project_container(component: Mapping[str, Any]) -> bool:
        if str(component.get("identity_kind") or "") not in {"facility", "local_area", "zone"}:
            return False
        label = str(component.get("canonical_label") or "").strip()
        source_locator_ids = {str(value) for value in component.get("source_locator_ids") or ()}
        if not label or len(source_locator_ids) < 2:
            return False
        designation = facility_designation(label)
        aliases = [
            str(value).strip()
            for value in component.get("candidate_labels") or (label,)
            if str(value).strip()
        ]
        if designation:
            return _explicit_designation_alias(designation, aliases)
        if facility_designations(label):
            return False
        return len({str(value) for value in component.get("member_structure_node_ids") or ()}) >= 2

    has_project_container = any(establishes_project_container(value) for value in components)
    for component in components:
        kind = str(component.get("identity_kind") or "")
        if kind not in {"facility", "local_area", "zone", "structure"}:
            continue
        label = str(component.get("canonical_label") or "").strip()
        if not label:
            continue
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
            member_node_ids = {
                str(value) for value in component.get("member_structure_node_ids") or ()
            }
            # A facility-shaped token rejected by the strict designation parser is
            # commonly an equipment model (for example a pump-station model mark).
            # It must not re-enter the project hierarchy through the generic path.
            if designation or facility_designations(label):
                continue
            if len(source_locator_ids) < 2 or len(member_node_ids) < 2:
                continue
            # Reconciled structures are useful as the project-level navigation root
            # when the package describes one or more structures but has no separate
            # facility/area container.  In a multi-level project they stay below the
            # established facility cards and are exposed through relationships.
            if kind == "structure" and has_project_container:
                continue
            component_identity = str(component.get("identity_candidate_id") or "").strip()
            key_payload = {
                "kind": kind,
                "identity_candidate_id": component_identity or None,
                "member_structure_node_ids": sorted(member_node_ids),
            }
            key = f"component:{semantic_digest(key_payload)}"
            status = "Установлено сопоставлением в нескольких документах"
            is_alias_group = len(candidate_labels) > 1
        current = groups.setdefault(
            key,
            {
                "facility_id": semantic_digest({"workspace_id": workspace_id, "facility_key": key}),
                "designation": designation,
                "name": designation or label,
                "kind": {
                    "facility": "Сооружение",
                    "local_area": "Участок",
                    "zone": "Зона",
                    "structure": "Конструкция",
                }[kind],
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
    commercial_designations_by_scope: dict[str, set[str]] = defaultdict(set)
    for context in source_context.values():
        scope_code = str(context.get("page_commercial_scope_code") or "").strip()
        scope_designation = commercial_scope_facility_designation(
            context.get("page_commercial_scope_header")
        )
        if scope_code and scope_designation in facilities_by_designation:
            commercial_designations_by_scope[scope_code].add(str(scope_designation))
    established_by_facility: dict[str, dict[str, Any]] = {}
    established_counted_groups: list[dict[str, Any]] = []
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
                    "aggregate_count": 1,
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
            locator_ids = sorted(str(value) for value in pit.get("source_locator_ids") or ())
            direct_commercial_designations = {
                value
                for locator_id in locator_ids
                for context in (source_context.get(locator_id),)
                if isinstance(context, Mapping)
                for value in (
                    commercial_scope_facility_designation(
                        context.get("page_commercial_scope_header")
                    ),
                )
                if value in facilities_by_designation
            }
            scope_codes = {
                str(context.get("page_commercial_scope_code") or "").strip()
                for locator_id in locator_ids
                for context in (source_context.get(locator_id),)
                if isinstance(context, Mapping)
                and str(context.get("page_commercial_scope_code") or "").strip()
            }
            commercial_designations = set(direct_commercial_designations)
            for scope_code in scope_codes:
                commercial_designations.update(commercial_designations_by_scope[scope_code])
            commercial_scope_designation = (
                next(iter(commercial_designations)) if len(commercial_designations) == 1 else None
            )
            # An explicitly counted group of pits for wells/chambers under one
            # commercial facility is a real minimum inventory even when the
            # estimate does not give individual marks.  Keep it as an aggregate
            # group; do not fabricate member identities.
            counted_distinct_structure_group = bool(
                stated_count
                and len(commercial_designations) == 1
                and any(
                    marker in _normalized(description) for marker in ("колодц", "камер", "переход")
                )
            )
            if counted_distinct_structure_group:
                group_designation = next(iter(commercial_designations))
                established_counted_groups.append(
                    {
                        "pit_id": semantic_digest(
                            {
                                "facility": group_designation,
                                "label": _normalized(description),
                                "count": stated_count,
                                "kind": "counted_excavation_pit_group",
                            }
                        ),
                        "name": description,
                        "related_facility_id": facilities_by_designation[group_designation][
                            "facility_id"
                        ],
                        "related_facility": group_designation,
                        "aliases": [description],
                        "known_parameters": [f"Количество по документу: {stated_count} шт."],
                        "related_works": [],
                        "aggregate_count": stated_count,
                        "sources": _source_refs(locator_ids, source_context),
                        "source_locator_ids": locator_ids,
                        "status": (
                            "Группа установлена по явному количеству в коммерческом "
                            "разделе; поштучные марки не указаны"
                        ),
                    }
                )
                continue
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
                    f"Коммерческий раздел относится к {commercial_scope_designation}, но "
                    "группа котлованов не содержит количества и поштучных марок."
                    if commercial_scope_designation
                    else "Указана группа котлованов без количества, поштучных марок и "
                    "однозначной привязки к сооружениям."
                )
            else:
                reason = (
                    f"Упоминание находится в коммерческом разделе {commercial_scope_designation}, "
                    "но не содержит отдельной марки; нельзя исключить повтор уже установленного "
                    "котлована."
                    if commercial_scope_designation
                    else "Упоминание отдельного котлована не содержит марки сооружения; "
                    "нельзя исключить повторное упоминание уже установленного котлована."
                )
            clarification.append(
                {
                    "description": description,
                    "related_facility": (
                        designation
                        if designation in facilities_by_designation
                        else commercial_scope_designation
                        or pit.get("associated_facility_designation")
                    ),
                    "reason": reason,
                    "stated_count": stated_count,
                    "minimum_count": 2 if paired_working_receiving else stated_count,
                    "sources": _source_refs(pit.get("source_locator_ids") or (), source_context),
                    "source_locator_ids": locator_ids,
                }
            )
    # A commercial schedule can repeat one counted group first with its
    # diameter/count and later as a generic heading.  When both mentions belong
    # to the same established facility and their construction subject is the
    # same, retain the generic wording as an alias instead of presenting it as
    # another unresolved group.  The rule deliberately requires one unique
    # counted match; it never merges groups across facilities or invents
    # individual pit identities.
    remaining_clarification: list[dict[str, Any]] = []
    for unresolved_group in clarification:
        if unresolved_group.get("stated_count") is not None:
            remaining_clarification.append(unresolved_group)
            continue
        related_facility = str(unresolved_group.get("related_facility") or "").strip()
        subject = _pit_group_subject(unresolved_group.get("description"))
        matching_counted_groups = [
            group
            for group in established_counted_groups
            if str(group.get("related_facility") or "").strip() == related_facility
            and _pit_group_subject(group.get("name")) == subject
        ]
        if not subject or len(matching_counted_groups) != 1:
            remaining_clarification.append(unresolved_group)
            continue
        counted_group = matching_counted_groups[0]
        description = str(unresolved_group.get("description") or "").strip()
        counted_group["aliases"] = sorted(
            {
                *(str(value) for value in counted_group.get("aliases") or ()),
                *([description] if description else []),
            }
        )
        counted_group["source_locator_ids"] = sorted(
            {
                *(str(value) for value in counted_group.get("source_locator_ids") or ()),
                *(str(value) for value in unresolved_group.get("source_locator_ids") or ()),
            }
        )
        counted_group["sources"] = _source_refs(counted_group["source_locator_ids"], source_context)
        counted_group["status"] = (
            "Группа установлена по явному количеству в коммерческом разделе; "
            "повторное общее обозначение учтено как алиас, поштучные марки не указаны"
        )
    clarification = remaining_clarification
    coverage = dict(pit_inventory.get("coverage") or {})
    ambiguous_count = int(dict(coverage.get("disposition_counts") or {}).get("ambiguous", 0))
    unresolved_count = len(clarification)
    established = sorted(
        [*established_by_facility.values(), *established_counted_groups],
        key=lambda value: (value["related_facility"], value["name"]),
    )
    named_established_count = len(established_by_facility)
    counted_group_pit_count = sum(
        int(value.get("aggregate_count") or 0) for value in established_counted_groups
    )
    established_count = named_established_count + counted_group_pit_count
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
        "established_count": established_count,
        "named_established_count": named_established_count,
        "counted_group_pit_count": counted_group_pit_count,
        "requires_clarification": clarification,
        "unresolved_group_count": unresolved_count,
        "quantified_unresolved_group_pit_count": quantified_group_count,
        "stated_minimum_unresolved_pit_count": stated_minimum_count,
        "ambiguous_observation_count": ambiguous_count,
        "is_final": unresolved_count == 0,
        "professional_answer": (
            f"В проекте {_russian_pit_count(established_count, established=True)}."
            if unresolved_count == 0
            else f"{_russian_pit_count(established_count, established=True).capitalize()}. "
            + (
                f"Из них {named_established_count} имеют явную привязку к сооружению, "
                f"ещё {counted_group_pit_count} указаны количеством в группах без поштучных марок. "
                if counted_group_pit_count
                else ""
            )
            + f"Ещё {unresolved_count} {_russian_group_word(unresolved_count)} обозначений "
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


def _pit_group_subject(value: object) -> str:
    """Return a stable construction subject for repeated commercial pit rows."""

    normalized = _normalized(value)
    normalized = re.sub(r"\b(?:d|д)\s*\d+(?:[.,]\d+)?\b", " ", normalized)
    normalized = re.sub(r"\b\d+(?:[.,]\d+)?\s*шт\b", " ", normalized)
    normalized = re.sub(r"[()\[\],.;:]", " ", normalized)
    return " ".join(normalized.split())


def _attach_pit_work_scopes(
    pits: Mapping[str, Any], works: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Attach conservatively scoped construction work to established pits.

    A facility-level work may be inherited by its pit only when the model has
    exactly one established pit for that facility. Multiple pits require an
    explicit lower-level association and therefore remain unassigned.
    """

    intrinsically_pit_scoped_families = {
        "pit_preparation",
        "sheet_piling",
        "waling_beam",
        "bracing",
    }
    context_dependent_families = {"excavation", "dewatering", "backfill", "compaction"}
    established = [dict(value) for value in pits.get("established") or ()]
    pits_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pit in established:
        facility_id = str(pit.get("related_facility_id") or "")
        if facility_id:
            pits_by_facility[facility_id].append(pit)
    work_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_work in works:
        work = dict(raw_work)
        facility_id = str(work.get("facility_id") or "")
        family = str(work.get("family_key") or "")
        wording = str(work.get("work_name") or "")
        is_pit_scoped = family in intrinsically_pit_scoped_families or (
            family in context_dependent_families and "котлован" in _normalized(wording)
        )
        if facility_id and is_pit_scoped:
            work_by_facility[facility_id].append(work)
    for facility_id, facility_pits in pits_by_facility.items():
        if len(facility_pits) != 1 or int(facility_pits[0].get("aggregate_count") or 1) != 1:
            continue
        facility_pits[0]["related_works"] = [
            {
                "work_scope_id": work.get("work_scope_id"),
                "work": work.get("work_name"),
                "work_family": work.get("work_family"),
                "quantities_by_document": dict(work.get("quantities_by_document") or {}),
                "materials_by_document": dict(work.get("materials_by_document") or {}),
                "source_locator_ids": list(work.get("source_locator_ids") or ()),
                "status": ("Работа связана через единственный установленный котлован сооружения"),
            }
            for work in work_by_facility.get(facility_id, ())
        ]
    return {**dict(pits), "established": established}


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


def _semantic_work_consensus(
    works: Iterable[Mapping[str, Any]],
    work_resolutions: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reuse only cross-document agreement for an identical work wording.

    Qwen often sees the same schedule description in a drawing, VOR and local
    estimate.  Repeating inference for every occurrence wastes the foreground
    model slot.  Family/operation meaning is reusable when independent active
    source versions agree, or when one reviewed wording is exact and specific
    (at least three words), and no reviewed occurrence conflicts.  The facility
    is deliberately excluded: same-named work at two structures must remain two
    scopes and is assigned from each row's own source context.
    """

    reviewed: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)
    for raw in works:
        row = dict(raw)
        candidate_id = str(row.get("candidate_id") or "")
        resolution = dict(work_resolutions.get(candidate_id) or {})
        if not resolution or int(resolution.get("candidate_version") or 0) != int(
            row.get("version") or 0
        ):
            continue
        wording = str(row.get("value") or row.get("raw_name") or "").strip()
        normalized_name = _normalized(row.get("label") or row.get("normalized_name") or wording)
        if not normalized_name:
            continue
        reviewed[normalized_name].append(
            (
                str(resolution.get("status") or ""),
                str(resolution.get("family_key") or ""),
                str(resolution.get("operation") or ""),
                str(row.get("source_version_id") or ""),
                str(resolution.get("reason") or ""),
            )
        )

    consensus: dict[str, dict[str, Any]] = {}
    catalog = work_family_catalog()
    for normalized_name, values in reviewed.items():
        statuses = {status for status, _family, _operation, _source, _reason in values}
        independent_sources = {
            source for _status, _family, _operation, source, _reason in values if source
        }
        specific_exact_wording = len(re.findall(r"[0-9a-zа-яё]+", normalized_name)) >= 3
        if len(independent_sources) < 2 and not specific_exact_wording:
            continue
        if statuses == {"NOT_A_WORK"}:
            consensus[normalized_name] = {
                "status": "NOT_A_WORK",
                "reason": (
                    "Точное описание ранее определено как не относящееся к работам "
                    "текущего строительства."
                ),
            }
            continue
        if statuses != {"MATCHED"}:
            continue
        meanings = {
            (family, professional_work_name(family, operation or normalized_name))
            for _status, family, operation, _source, _reason in values
            if family in catalog
        }
        if len(meanings) != 1:
            continue
        family, operation = next(iter(meanings))
        consensus[normalized_name] = {
            "status": "MATCHED",
            "family_key": family,
            "operation": operation,
            "reason": (
                "Значение точного описания совпало в независимых исходных "
                "документах; место работы определяется отдельно."
                if len(independent_sources) >= 2
                else "Точное специфичное описание ранее классифицировано; "
                "место работы определяется отдельно по текущему источнику."
            ),
        }
    return consensus


def _work_schedule(
    works: Iterable[Mapping[str, Any]],
    quantities: Iterable[Mapping[str, Any]],
    materials: Iterable[Mapping[str, Any]],
    facilities: Iterable[Mapping[str, Any]],
    node_to_facility: Mapping[str, str],
    structure_relationships: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
    work_resolutions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    work_rows = [dict(raw) for raw in works]
    semantic_consensus = _semantic_work_consensus(work_rows, work_resolutions)
    facility_by_designation = {
        str(item.get("designation")): dict(item) for item in facilities if item.get("designation")
    }
    facility_by_id = {str(item.get("facility_id")): dict(item) for item in facilities}
    commercial_facilities_by_scope: dict[str, set[str]] = defaultdict(set)
    for scope_context in source_context.values():
        scope_code = str(scope_context.get("page_commercial_scope_code") or "").strip()
        designation = commercial_scope_facility_designation(
            scope_context.get("page_commercial_scope_header")
        )
        facility = facility_by_designation.get(designation or "")
        if scope_code and facility is not None:
            commercial_facilities_by_scope[scope_code].add(str(facility["facility_id"]))
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
    # A resolved structural relationship on the exact same source fragment is
    # an engineering link, not mere document co-occurrence.  It lets work rows
    # inherit a facility only when the relationship has one unambiguous
    # facility endpoint; conflicting endpoints remain unresolved.
    relationship_facilities_by_locator: dict[str, set[str]] = defaultdict(set)
    for raw_relationship in structure_relationships:
        relationship = dict(raw_relationship)
        facility_ids: set[str] = set()
        for endpoint in ("subject_structure_node_id", "object_structure_node_id"):
            related_facility_id = node_to_facility.get(str(relationship.get(endpoint) or ""))
            if related_facility_id is not None:
                facility_ids.add(related_facility_id)
        locator_id = str(relationship.get("source_locator_id") or "")
        if locator_id and len(facility_ids) == 1:
            relationship_facilities_by_locator[locator_id].update(facility_ids)
    for locator_id, facility_ids in relationship_facilities_by_locator.items():
        if len(facility_ids) == 1:
            facility_ids_by_locator[locator_id].update(facility_ids)
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
    # A validated semantic resolution can establish the heading/sheet scope
    # for neighbouring schedule rows that do not repeat the facility name.
    # Propagate only when the page resolves to one established facility;
    # mixed-facility summary sheets remain deliberately unassigned.
    for row in work_rows:
        candidate_id = str(row.get("candidate_id") or "")
        resolution = dict(work_resolutions.get(candidate_id) or {})
        if (
            resolution.get("status") != "MATCHED"
            or int(resolution.get("candidate_version") or 0) != int(row.get("version") or 0)
            or not resolution.get("facility")
            or not _resolution_establishes_page_scope(resolution)
        ):
            continue
        semantic_facility = facility_by_designation.get(str(resolution["facility"]))
        context = source_context.get(str(row.get("source_locator_id") or ""))
        if semantic_facility is None or not isinstance(context, Mapping):
            continue
        locator_value = context.get("locator_value")
        page = locator_value.get("page") if isinstance(locator_value, Mapping) else None
        if page is not None:
            facility_ids_by_page[(str(context.get("source_version_id") or ""), int(page))].add(
                str(semantic_facility["facility_id"])
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
        context = dict(source_context.get(locator_id) or {})
        deterministic_non_work_reason = non_work_reason(name)
        scope_exclusion_reason = construction_scope_exclusion_reason(
            context.get("safe_display_name")
        )
        family = classify_work_family(normalized_name)
        resolution = dict(work_resolutions.get(candidate_id) or {})
        if int(resolution.get("candidate_version") or 0) != int(row.get("version") or 0):
            resolution = {}
        if not resolution and family is None:
            resolution = dict(semantic_consensus.get(_normalized(normalized_name)) or {})
        designation = facility_designation(f"{name} {row.get('scope_key') or ''}")
        facility = facility_by_designation.get(designation or "")
        assignment_basis = "Явное обозначение сооружения в описании работы"
        if facility is None:
            exact_facilities = facility_ids_by_locator.get(locator_id, set())
            if len(exact_facilities) == 1:
                facility = facility_by_id[next(iter(exact_facilities))]
                designation = str(facility.get("designation") or facility.get("name") or "")
                assignment_basis = (
                    "Работа связана с сооружением явным отношением в исходном фрагменте"
                    if locator_id in relationship_facilities_by_locator
                    else "Работа и сооружение указаны в одном исходном фрагменте"
                )
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
        if facility is None:
            document_designation = facility_designation(context.get("safe_display_name"))
            document_facility = facility_by_designation.get(document_designation or "")
            if document_facility is not None:
                facility = document_facility
                designation = document_designation
                assignment_basis = (
                    "Работа отнесена к сооружению, однозначно указанному в названии "
                    "исходного документа"
                )
        if facility is None:
            scope_code = str(context.get("page_commercial_scope_code") or "").strip()
            commercial_facility_ids = commercial_facilities_by_scope.get(scope_code, set())
            if len(commercial_facility_ids) == 1:
                facility = facility_by_id[next(iter(commercial_facility_ids))]
                designation = str(facility.get("designation") or facility.get("name") or "")
                assignment_basis = (
                    "Работа отнесена к сооружению по наименованию соответствующей "
                    f"ВОР/локальной сметы {scope_code}"
                )
        if facility is None and resolution.get("facility"):
            semantic_designation = str(resolution["facility"])
            semantic_facility = facility_by_designation.get(semantic_designation)
            if semantic_facility is not None:
                facility = semantic_facility
                designation = semantic_designation
                assignment_basis = (
                    "Сооружение установлено локальной моделью по тексту и контексту исходного листа"
                )
        role = (
            "ВОР"
            if context.get("page_is_bill_of_quantities") is True
            else _professional_document_role(
                row.get("source_role"), context.get("safe_display_name")
            )
        )
        linked_quantities = quantity_by_work.get(candidate_id, ())
        quantity_reviews = (
            {
                str(value.get("quantity_candidate_id") or ""): dict(value)
                for value in resolution.get("quantity_reviews") or ()
                if isinstance(value, Mapping) and value.get("quantity_candidate_id")
            }
            if resolution.get("profile_version") in _QUANTITY_AWARE_WORK_PROFILES
            else {}
        )
        accepted_quantities: list[dict[str, Any]] = []
        quantity_interpretations: list[dict[str, Any]] = []
        for raw_quantity in linked_quantities:
            quantity = dict(raw_quantity)
            quantity_id = str(quantity.get("candidate_id") or "")
            review = quantity_reviews.get(quantity_id)
            if review is None:
                review = {
                    "status": "UNREVIEWED",
                    "reason": ("Значение ещё не проверено как объём этой строительной операции."),
                }
            if review.get("status") in {"WORK_QUANTITY", "DURATION"}:
                accepted_quantities.append(quantity)
            quantity_interpretations.append(
                {
                    "quantity_candidate_id": quantity_id,
                    "value": quantity.get("normalized_value", quantity.get("value")),
                    "unit": quantity.get(
                        "normalized_unit",
                        quantity.get("unit", quantity.get("raw_unit")),
                    ),
                    "status": review.get("status"),
                    "reason": review.get("reason"),
                    "source_locator_id": quantity.get("source_locator_id"),
                }
            )
        observation = {
            "candidate_id": candidate_id,
            "project_wording": name,
            "normalized_work_name": normalized_name,
            "facility_id": facility.get("facility_id") if facility else None,
            # Keep facility labels authoritative to the established project
            # inventory.  An unmatched facility-shaped token can be an
            # equipment model or a partial designation; showing it as the
            # work location would create a facility that the project model
            # does not actually contain.
            "facility": designation if facility else None,
            "facility_assignment_basis": assignment_basis if facility else None,
            "document_role": role,
            "source_version_id": source_version_id,
            "source_locator_id": locator_id,
            "source": _source_ref(locator_id, source_context),
            "quantities": _unique_values(accepted_quantities, "quantity"),
            "quantity_interpretations": quantity_interpretations,
            "materials": _professional_material_values(
                _unique_values(material_by_work.get(candidate_id, ()), "material"),
                source_context,
            ),
            "semantic_resolution_status": resolution.get("status"),
            "semantic_resolution_reason": resolution.get("reason"),
        }
        # Resource codes, headings and pure quantity rows are not construction
        # operations even when their description contains a family keyword
        # (for example an estimate resource named ``Трамбовки``).  Apply the
        # same deterministic exclusion used by the Qwen scheduler before the
        # family branch, otherwise these rows inflate the professional work
        # schedule while never becoming eligible for semantic correction.
        if deterministic_non_work_reason is not None or scope_exclusion_reason is not None:
            excluded.append(
                {
                    **observation,
                    "exclusion_reason": (deterministic_non_work_reason or scope_exclusion_reason),
                }
            )
            continue
        if resolution.get("status") == "MATCHED":
            # Contextual local-Qwen interpretation may refine a broad
            # deterministic term (for example, a concrete phrase describing
            # pile construction, or pipeline wording describing demolition).
            # The family remains restricted to the canonical catalog.
            family_key = str(resolution.get("family_key") or "")
            family_name = work_family_catalog().get(family_key)
            if family_name:
                operation_name = str(resolution.get("operation") or family_name)
                family = (family_key, family_name)
        elif resolution.get("status") == "NOT_A_WORK":
            excluded.append(
                {
                    **observation,
                    "exclusion_reason": str(
                        resolution.get("reason")
                        or "Локальная модель определила, что строка не является работой"
                    ),
                }
            )
            continue
        if family is None:
            if name:
                reason = non_work_reason(name)
                if reason:
                    excluded.append({**observation, "exclusion_reason": reason})
                else:
                    unclassified.append(observation)
            continue
        family_key, family_name = family
        # Local-Qwen preserves the source meaning but may phrase the same
        # operation differently (for example ``забивка шпунта`` versus
        # ``погружение шпунта``).  Keep that wording in ``project_wording`` and
        # use the deterministic professional operation name as the schedule
        # identity.  Otherwise equivalent design and commercial rows remain
        # separate and cannot be compared.  The canonicalizer deliberately
        # retains operation distinctions implemented by each family (driving
        # versus extraction, trench versus pit, installation versus removal).
        semantic_operation = str(resolution.get("operation") or "")
        operation_name = (
            professional_work_name(family_key, f"{name} {semantic_operation}")
            if resolution.get("status") == "MATCHED"
            and semantic_operation
            and family_key in _CANONICAL_SEMANTIC_OPERATION_FAMILIES
            else semantic_operation
            if resolution.get("status") == "MATCHED" and semantic_operation
            else professional_work_name(family_key, name)
        )
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

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in exact_observations.values():
        facility_key = str(observation.get("facility_id") or "unassigned")
        # A broad operation such as ``Монтаж трубопровода`` is not an
        # engineering scope by itself.  Without a facility, merging all such
        # rows creates a project-wide pseudo-package and can attach unrelated
        # quantities to one schedule line.  Preserve the original operation
        # wording until a real location/scope relationship is established.
        # Specific operations (for example ``Демонтаж светильников``) may
        # still reconcile across roles through the validated semantic result.
        unassigned_scope = (
            _normalized(observation.get("project_wording"))
            if facility_key == "unassigned"
            and str(observation["operation_name"]) in _UNSCOPED_GENERIC_OPERATIONS
            else ""
        )
        grouped[
            (
                facility_key,
                str(observation["family_key"]),
                str(observation["operation_name"]),
                unassigned_scope,
            )
        ].append(observation)
    schedules: list[dict[str, Any]] = []
    material_rows: list[dict[str, Any]] = []
    for (
        facility_key,
        family_key,
        operation_name,
        _unassigned_scope,
    ), observations in sorted(grouped.items()):
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
        wording_by_role: dict[str, set[str]] = defaultdict(set)
        semantic_status_by_role: dict[str, set[str]] = defaultdict(set)
        grouped_quantity_interpretations: list[dict[str, Any]] = []
        for observation in observations:
            role = str(observation["document_role"])
            quantities_by_role[role].extend(observation["quantities"])
            materials_by_role[role].extend(observation["materials"])
            grouped_quantity_interpretations.extend(observation["quantity_interpretations"])
            wording_by_role[role].add(str(observation["project_wording"]))
            if observation.get("semantic_resolution_status"):
                semantic_status_by_role[role].add(str(observation["semantic_resolution_status"]))
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
            "project_wording_by_document": {
                role: sorted(values) for role, values in sorted(wording_by_role.items())
            },
            "semantic_resolution_by_document": {
                role: sorted(values) for role, values in sorted(semantic_status_by_role.items())
            },
            "quantities_by_document": quantities_by_role,
            "materials_by_document": materials_by_role,
            "quantity_interpretations": _deduplicate_dicts(grouped_quantity_interpretations),
            "quantities_semantically_validated": bool(grouped_quantity_interpretations)
            and all(
                value.get("status") != "UNREVIEWED" for value in grouped_quantity_interpretations
            ),
            "quantity_validation_status": (
                "Все связанные значения проверены по смыслу"
                if grouped_quantity_interpretations
                and all(
                    value.get("status") != "UNREVIEWED"
                    for value in grouped_quantity_interpretations
                )
                else "Часть связанных значений ещё требует смысловой проверки"
                if any(
                    value.get("status") == "UNREVIEWED"
                    for value in grouped_quantity_interpretations
                )
                else "Значения получены прежним профилем и ещё не проверены по смыслу"
            ),
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
    all_quantity_interpretations = [
        dict(review)
        for observation in exact_observations.values()
        for review in observation.get("quantity_interpretations") or ()
    ]
    total_count = classified_count + len(unclassified) + len(excluded)
    construction_scope_count = classified_count + len(unclassified)
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
            "construction_scope_observation_count": construction_scope_count,
            "classified_percent": (
                round(classified_count * 100 / total_count, 1) if total_count else 0.0
            ),
            "construction_scope_classified_percent": (
                round(classified_count * 100 / construction_scope_count, 1)
                if construction_scope_count
                else 0.0
            ),
            "facility_assigned_observation_count": assigned_count,
            "facility_unassigned_observation_count": classified_count - assigned_count,
            "reviewed_quantity_observation_count": len(
                [
                    value
                    for value in all_quantity_interpretations
                    if value.get("status") != "UNREVIEWED"
                ]
            ),
            "accepted_work_quantity_observation_count": len(
                [
                    value
                    for value in all_quantity_interpretations
                    if value.get("status") == "WORK_QUANTITY"
                ]
            ),
            "ambiguous_quantity_observation_count": len(
                [
                    value
                    for value in all_quantity_interpretations
                    if value.get("status") == "AMBIGUOUS"
                ]
            ),
            "pending_quantity_observation_count": len(
                [
                    value
                    for value in all_quantity_interpretations
                    if value.get("status") == "UNREVIEWED"
                ]
            ),
            "policy": (
                "Упорядоченные инженерные термины и явные обозначения; одинаковые слова "
                "без контекста не объединяют разные работы или сооружения."
            ),
        },
    }


def _resolution_establishes_page_scope(resolution: Mapping[str, Any]) -> bool:
    try:
        confidence = Decimal(str(resolution.get("confidence") or "0"))
    except InvalidOperation:
        return False
    reason = _normalized(resolution.get("reason"))
    return confidence >= Decimal("0.9") and any(
        marker in reason
        for marker in (
            "заголовок",
            "заголовке",
            "ведомость объемов",
            "ведомости объемов",
            "раздел смет",
            "раздел прокладк",
            "контекст явно указывает на раздел",
        )
    )


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
        vor = _one_comparable_quantity(quantities.get("ВОР") or ())
        estimate = _one_comparable_quantity(quantities.get("Смета") or ())
        if vor is not None and estimate is not None:
            if vor[1] != estimate[1]:
                comparisons.append(
                    _comparison_row(
                        work,
                        "ВОР",
                        "Смета",
                        vor,
                        estimate,
                        None,
                        "Единицы ВОР и сметы различаются",
                    )
                )
            else:
                difference = vor[0] - estimate[0]
                conclusion = (
                    "Значения ВОР и сметы совпадают"
                    if difference == 0
                    else f"Разница ВОР ↔ Смета: {_decimal_text(difference)} {vor[1]}"
                )
                comparisons.append(
                    _comparison_row(work, "ВОР", "Смета", vor, estimate, difference, conclusion)
                )
    return comparisons


def _validated_scope_quantity_comparisons(
    works: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare differently worded rows only after engineering scope is established.

    The work schedule already groups observations by facility, canonical family,
    and interpreted operation.  That grouping is safe for comparison only when
    it has a real facility and every linked numeric observation has passed the
    quantity-meaning contract.  Unassigned or partly reviewed rows remain in
    the schedule but cannot create a Tender discrepancy.
    """

    result: list[dict[str, Any]] = []
    for raw in works:
        work = dict(raw)
        if work.get("quantities_semantically_validated") is not True:
            continue
        exact_cross_role_wording = _exact_cross_role_work_wording(work)
        semantic_cross_role_operation = _semantic_cross_role_work_operation(work)
        if (
            not work.get("facility_id")
            and exact_cross_role_wording is None
            and semantic_cross_role_operation is None
        ):
            continue
        basis = (
            "Совпадают сооружение, вид работы и строительная операция; "
            "связанные числовые значения проверены по смыслу."
            if work.get("facility_id")
            else (
                "В проектном и коммерческом документах дословно совпадает операция "
                f"«{exact_cross_role_wording}»; связанные числовые значения проверены по смыслу."
            )
            if exact_cross_role_wording is not None
            else (
                "Локальная модель отнесла проектную и коммерческую позиции к одной "
                f"операции «{semantic_cross_role_operation}»; связанные числовые "
                "значения проверены по смыслу."
            )
        )
        for comparison in _comparisons([work]):
            if not work.get("facility_id") and not _isolated_unassigned_comparison(
                work, comparison
            ):
                continue
            result.append({**comparison, "scope_match_basis": basis})
    return result


def _isolated_unassigned_comparison(work: Mapping[str, Any], comparison: Mapping[str, Any]) -> bool:
    """Reject project-wide pseudo-comparisons when a location is unresolved.

    A validated semantic operation can safely connect one design row to one
    commercial row even before its facility is known.  It cannot make a scope
    out of several occurrences collected across unrelated drawings, VOR
    sections or estimate chapters.  Those rows remain visible in the work and
    quantity schedules until their location is established.
    """

    left_role = str(dict(comparison.get("left") or {}).get("document_role") or "")
    right_role = str(dict(comparison.get("right") or {}).get("document_role") or "")
    if not left_role or not right_role:
        return False
    # Two commercial rows with no facility can describe different estimate
    # chapters even when their normalized operation is identical.  A VOR ↔
    # estimate finding therefore requires a resolved location/scope.
    if {left_role, right_role}.issubset({"ВОР", "Смета"}):
        return False
    sources = dict(work.get("sources_by_document") or {})
    wordings = dict(work.get("project_wording_by_document") or {})
    return all(
        len(list(sources.get(role) or ())) == 1 and len(list(wordings.get(role) or ())) == 1
        for role in (left_role, right_role)
    )


def _exact_cross_role_work_wording(work: Mapping[str, Any]) -> str | None:
    by_role = dict(work.get("project_wording_by_document") or {})
    design = {
        _normalized(value): str(value)
        for role in ("ПД", "РД", "Спецификация")
        for value in by_role.get(role) or ()
        if _normalized(value)
    }
    commercial = {
        _normalized(value)
        for role in ("ВОР", "Смета")
        for value in by_role.get(role) or ()
        if _normalized(value)
    }
    matches = sorted(set(design).intersection(commercial))
    return design[matches[0]] if len(matches) == 1 else None


def _semantic_cross_role_work_operation(work: Mapping[str, Any]) -> str | None:
    statuses = dict(work.get("semantic_resolution_by_document") or {})
    design_matched = any(
        "MATCHED" in set(statuses.get(role) or ()) for role in ("ПД", "РД", "Спецификация")
    )
    commercial_matched = any(
        "MATCHED" in set(statuses.get(role) or ()) for role in ("ВОР", "Смета")
    )
    operation = str(work.get("work_name") or "").strip()
    family = str(work.get("work_family") or "").strip()
    if design_matched and commercial_matched and operation and operation != family:
        return operation
    return None


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
    comparison_kind = (
        "duration" if _duration_unit(left[1]) and _duration_unit(right[1]) else "quantity"
    )
    classification = (
        "UNIT_MISMATCH"
        if difference is None
        else "MATCH"
        if difference == 0
        else "QUANTITY_DIFFERENCE"
    )
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
        "comparison_kind": comparison_kind,
        "classification": classification,
        "professional_status": {
            "MATCH": "Значения совпадают",
            "QUANTITY_DIFFERENCE": (
                "Различается продолжительность"
                if comparison_kind == "duration"
                else "Различается объём"
            ),
            "UNIT_MISMATCH": "Единицы не позволяют прямое сравнение",
        }[classification],
        "conclusion": conclusion,
        "source_locator_ids": list(work.get("source_locator_ids") or ()),
    }


def _scope_comparisons(
    works: Iterable[Mapping[str, Any]],
    *,
    unclassified_works: Iterable[Mapping[str, Any]] = (),
    available_document_roles: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Classify design/commercial coverage for the same engineering family.

    This does not call a design item omitted merely because its exact wording is
    absent.  When a commercial row exists for the family but lacks a facility
    allocation, the result is explicitly an unresolved scope match.
    """

    rows = [dict(value) for value in works]
    design_roles = {"ПД", "РД", "Спецификация"}
    commercial_roles = {"ВОР", "Смета"}
    available_commercial_roles = commercial_roles.intersection(
        str(value) for value in available_document_roles
    )
    commercial_denominator = _commercial_document_phrase(available_commercial_roles)
    unresolved_commercial = [
        dict(row)
        for row in unclassified_works
        if str(row.get("document_role") or "") in commercial_roles
    ]
    unresolved_design = [
        dict(row)
        for row in unclassified_works
        if str(row.get("document_role") or "") in design_roles
    ]
    unresolved_commercial_facilities = {
        str(row.get("facility_id")) for row in unresolved_commercial if row.get("facility_id")
    }
    unresolved_design_facilities = {
        str(row.get("facility_id")) for row in unresolved_design if row.get("facility_id")
    }
    commercial_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    design_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    commercial_facilities: set[str] = set()
    for row in rows:
        roles = set(str(value) for value in row.get("document_roles") or ())
        if roles.intersection(commercial_roles):
            commercial_by_family[str(row.get("family_key") or "")].append(row)
            if row.get("facility_id"):
                commercial_facilities.add(str(row["facility_id"]))
        if roles.intersection(design_roles):
            design_by_family[str(row.get("family_key") or "")].append(row)

    result: list[dict[str, Any]] = []
    for row in rows:
        roles = set(str(value) for value in row.get("document_roles") or ())
        design = roles.intersection(design_roles)
        commercial = roles.intersection(commercial_roles)
        if not design:
            if commercial:
                possible_design = design_by_family.get(str(row.get("family_key") or ""), [])
                covered_by_design_scope = any(
                    _design_scope_covers_commercial_operation(design_row, row)
                    for design_row in possible_design
                )
                if covered_by_design_scope:
                    status = "MATCH"
                    professional_status = "Коммерческая операция имеет проектное основание"
                    conclusion = (
                        "Операция относится к установленному проектному объёму этого сооружения."
                    )
                elif possible_design:
                    status = "UNRESOLVED_SCOPE_MATCH"
                    professional_status = "Требуется связать коммерческую и проектную позиции"
                    conclusion = (
                        "Проектные позиции этого вида найдены, но их нельзя однозначно "
                        "связать с данным коммерческим объёмом."
                    )
                elif row.get("facility_id") in unresolved_design_facilities or (
                    not row.get("facility_id") and unresolved_design
                ):
                    status = "UNRESOLVED_SCOPE_MATCH"
                    professional_status = "Сопоставление проектного состава не завершено"
                    conclusion = (
                        "Основание коммерческой позиции пока не установлено: в проектных "
                        "документах остаются описания работ, которые ещё не удалось "
                        "однозначно классифицировать."
                    )
                else:
                    status = "COMMERCIAL_ONLY_WORK"
                    professional_status = "Коммерческая позиция без установленного основания"
                    conclusion = "Коммерческая позиция пока не связана с проектным объёмом."
            else:
                continue
        elif commercial:
            exact_operation = _exact_cross_role_work_wording(row)
            semantic_operation = _semantic_cross_role_work_operation(row)
            bounded_semantic_match = (
                semantic_operation is not None and len(row.get("project_wording") or ()) <= 2
            )
            if row.get("facility_id") or exact_operation or bounded_semantic_match:
                status = "MATCH"
                professional_status = "Состав сопоставлен"
                conclusion = "Проектная и коммерческая позиции найдены в одном инженерном объёме."
            else:
                status = "UNRESOLVED_SCOPE_MATCH"
                professional_status = "Требуется связать проектную и коммерческую позиции"
                conclusion = (
                    "Проектные и коммерческие позиции относятся к одному виду работ, "
                    "но место и границы объёма ещё не позволяют считать их одной работой."
                )
        else:
            possible = commercial_by_family.get(str(row.get("family_key") or ""), [])
            facility_id = str(row.get("facility_id") or "")
            possible_at_facility = [
                value
                for value in possible
                if facility_id and str(value.get("facility_id") or "") == facility_id
            ]
            possible_without_facility = [
                value for value in possible if not value.get("facility_id")
            ]
            covered_commercial = any(
                _design_scope_covers_commercial_operation(row, commercial_row)
                for commercial_row in possible_at_facility
            )
            if covered_commercial:
                status = "MATCH"
                professional_status = "Коммерческий состав найден"
                conclusion = (
                    "Проектный объём связан с соответствующей коммерческой операцией "
                    "этого сооружения."
                )
            elif possible_at_facility or possible_without_facility:
                status = "UNRESOLVED_SCOPE_MATCH"
                professional_status = "Требуется распределить коммерческий объём"
                conclusion = (
                    "Коммерческие позиции этого вида найдены, но их нельзя однозначно "
                    "распределить по сооружениям."
                )
            elif row.get("facility_id") in commercial_facilities:
                status = "WORK_MISSING_IN_COMMERCIAL"
                professional_status = "Возможная неучтённая работа"
                conclusion = (
                    "Работа установлена в проектных документах, но соответствующая позиция "
                    f"не найдена {commercial_denominator}."
                )
            elif row.get("facility_id") in unresolved_commercial_facilities or (
                not row.get("facility_id") and unresolved_commercial
            ):
                status = "UNRESOLVED_SCOPE_MATCH"
                professional_status = "Сопоставление коммерческого состава не завершено"
                conclusion = (
                    "Сопоставление пока не завершено: в ВОР/смете остаются описания работ, "
                    "которые ещё не удалось однозначно классифицировать."
                )
            else:
                status = "UNRESOLVED_SCOPE_MATCH"
                professional_status = "Коммерческий состав сооружения не установлен"
                conclusion = (
                    "Для сооружения пока не установлен достаточный коммерческий состав, "
                    "чтобы подтвердить наличие или отсутствие этой работы."
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
                "professional_status": professional_status,
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


def _design_scope_covers_commercial_operation(
    design: Mapping[str, Any], commercial: Mapping[str, Any]
) -> bool:
    """Match a bounded generic design scope to its priced construction operation."""

    if not design.get("facility_id") or design.get("facility_id") != commercial.get("facility_id"):
        return False
    if design.get("family_key") != commercial.get("family_key"):
        return False
    design_work = _normalized(design.get("work_name"))
    commercial_work = _normalized(commercial.get("work_name"))
    if design.get("family_key") == "sheet_piling":
        return "устройство шпунтового ограждения" in design_work and commercial_work in {
            "погружение шпунта",
            "устройство шпунтового ограждения",
            "шпунтовые работы",
        }
    return False


def _commercial_document_phrase(available_roles: Iterable[str]) -> str:
    roles = set(available_roles)
    if roles == {"Смета"}:
        return "в предоставленных сметах"
    if roles == {"ВОР"}:
        return "в предоставленной ВОР"
    if roles == {"ВОР", "Смета"}:
        return "в предоставленных ВОР и сметах"
    return "в доступных коммерческих документах"


def _sheet_pile_schedule(
    works: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
    *,
    pits: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return a professional sheet-pile/waling schedule without false totals."""

    result: list[dict[str, Any]] = []
    pits_by_facility: dict[str, list[str]] = defaultdict(list)
    for pit in (pits or {}).get("established") or ():
        facility_id = str(pit.get("related_facility_id") or "")
        pit_name = str(pit.get("name") or "").strip()
        if facility_id and pit_name:
            pits_by_facility[facility_id].append(pit_name)
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
        profiles = _ordered_unique(
            [
                *_sheet_pile_profiles(_normalized(" ".join(wording))),
                *(
                    profile
                    for values in materials.values()
                    for value in values or ()
                    for profile in _material_sheet_pile_profiles(value, source_context)
                ),
            ]
        )
        profiles_by_document = {
            role: _ordered_unique(
                profile
                for value in values or ()
                for profile in _material_sheet_pile_profiles(value, source_context)
            )
            for role, values in materials.items()
            if any(_material_sheet_pile_profiles(value, source_context) for value in values or ())
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
                if _material_sheet_pile_profiles(value, source_context)
                and value.get("source_locator_id")
            }
        )
        profile_wording = _ordered_unique(
            str(value.get("name") or "")
            for values in materials.values()
            for value in values or ()
            if _material_sheet_pile_profiles(value, source_context)
        )
        profile_sources_by_document = {
            role: _source_refs(
                [
                    str(value.get("source_locator_id"))
                    for value in values or ()
                    if _material_sheet_pile_profiles(value, source_context)
                    and value.get("source_locator_id")
                ],
                source_context,
            )
            for role, values in materials.items()
            if any(_material_sheet_pile_profiles(value, source_context) for value in values or ())
        }
        if unassigned_profile_observation:
            # The profile observation is useful, but the extractor associated it
            # with a non-sheet-pile work.  Keep the exact material observation and
            # its locator without inheriting unrelated excavation quantities.
            quantities = {}
            schedule_materials = {
                role: [
                    value
                    for value in values or ()
                    if _material_sheet_pile_profiles(value, source_context)
                ]
                for role, values in materials.items()
                if any(
                    _material_sheet_pile_profiles(value, source_context) for value in values or ()
                )
            }
        else:
            quantities = {
                role: _consolidate_quantity_mentions(values) for role, values in quantities.items()
            }
            schedule_materials = materials
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
                "family_key": row.get("family_key"),
                "pit": (
                    "; ".join(_ordered_unique(pits_by_facility[str(row["facility_id"])]))
                    if row.get("facility_id") and pits_by_facility.get(str(row["facility_id"]))
                    else f"Котлован {row.get('facility')} — марка требует уточнения"
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
                # Keep supplied material rows separate from work quantities.
                # A material mass may be useful to procurement while still
                # being unsafe to publish as the measured scope of the work.
                "materials_by_document": schedule_materials,
                "project_quantities": project_roles,
                "commercial_quantities": commercial_roles,
                "waling_beams": beams,
                "steel": steel,
                "project_wording": profile_wording if unassigned_profile_observation else wording,
                "source_locator_ids": (
                    profile_locator_ids
                    if unassigned_profile_observation
                    else list(row.get("source_locator_ids") or ())
                ),
                "sources_by_document": (
                    profile_sources_by_document
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
    return _merge_sheet_pile_rows(result)


def _merge_sheet_pile_rows(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Consolidate repeated descriptions of one scope without summing them."""

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in values:
        row = dict(raw)
        family_key = str(row.get("family_key") or "")
        operation = str(row.get("operation") or "")
        canonical_operation = (
            operation
            if operation.startswith("Материал шпунтового ограждения")
            else professional_work_name(family_key, operation)
            if family_key in {"sheet_piling", "waling_beam", "bracing"}
            else operation
        )
        key = (
            str(row.get("facility_id") or "unassigned"),
            family_key,
            canonical_operation,
        )
        current = grouped.get(key)
        if current is None:
            current = {
                **row,
                "operation": canonical_operation,
                "quantities_by_document": {},
                "materials_by_document": {},
                "project_quantities": {},
                "commercial_quantities": {},
                "profiles": [],
                "profiles_by_document": {},
                "pile_length": [],
                "waling_beams": [],
                "steel": [],
                "project_wording": [],
                "source_locator_ids": [],
                "sources_by_document": {},
            }
            grouped[key] = current
        for target_key in ("profiles", "pile_length", "waling_beams", "steel", "project_wording"):
            current[target_key] = _ordered_unique(
                [*current.get(target_key, ()), *row.get(target_key, ())]
            )
        current["source_locator_ids"] = sorted(
            {
                *(str(value) for value in current.get("source_locator_ids") or ()),
                *(str(value) for value in row.get("source_locator_ids") or ()),
            }
        )
        for role, profiles in dict(row.get("profiles_by_document") or {}).items():
            current["profiles_by_document"][role] = _ordered_unique(
                [
                    *current["profiles_by_document"].get(role, ()),
                    *(str(value) for value in profiles or ()),
                ]
            )
        for role, quantities in dict(row.get("quantities_by_document") or {}).items():
            current["quantities_by_document"][role] = _merge_consolidated_quantity_mentions(
                [*current["quantities_by_document"].get(role, ()), *(quantities or ())]
            )
        for role, materials in dict(row.get("materials_by_document") or {}).items():
            current["materials_by_document"][role] = _deduplicate_dicts(
                [*current["materials_by_document"].get(role, ()), *(materials or ())]
            )
        current["project_quantities"] = {
            role: quantities
            for role, quantities in current["quantities_by_document"].items()
            if role in {"ПД", "РД", "Спецификация"}
        }
        current["commercial_quantities"] = {
            role: quantities
            for role, quantities in current["quantities_by_document"].items()
            if role in {"ВОР", "Смета"}
        }
        for role, sources in dict(row.get("sources_by_document") or {}).items():
            current["sources_by_document"][role] = _deduplicate_dicts(
                [*current["sources_by_document"].get(role, ()), *(sources or ())]
            )
        if row.get("uncertainty") and not current.get("uncertainty"):
            current["uncertainty"] = row["uncertainty"]
    return [grouped[key] for key in sorted(grouped)]


def _concrete_material_spec(value: Mapping[str, Any]) -> dict[str, Any] | None:
    """Parse only explicit concrete durability properties from one material row."""

    name = str(value.get("name") or "")
    normalized = _normalized(name)
    if "бетон" not in normalized:
        return None
    strength_match = re.search(
        r"(?:класс|(?:кл\.?))?\s*[вb]\s*([0-9]+(?:[.,][0-9]+)?)",
        normalized,
    )
    if strength_match is None:
        return None
    frost_match = re.search(r"\bf\s*(?:\(\s*1\s*\)|1)?\s*([0-9]+)", normalized)
    water_match = re.search(r"\bw\s*([0-9]+)", normalized)
    return {
        "name": name,
        "strength": f"В{strength_match.group(1).replace(',', '.')}",
        "frost_value": int(frost_match.group(1)) if frost_match else None,
        "frost_label": f"F{frost_match.group(1)}" if frost_match else None,
        "water_value": int(water_match.group(1)) if water_match else None,
        "water_label": f"W{water_match.group(1)}" if water_match else None,
        "source_locator_id": value.get("source_locator_id"),
    }


def _material_comparisons(
    works: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare explicit concrete properties within the same engineering scope."""

    design_roles = {"ПД", "РД", "Спецификация"}
    commercial_roles = {"ВОР", "Смета"}
    result: list[dict[str, Any]] = []
    for raw in works:
        work = dict(raw)
        if not work.get("facility_id"):
            continue
        materials_by_role = dict(work.get("materials_by_document") or {})
        design_specs: list[tuple[str, dict[str, Any]]] = []
        commercial_specs: list[tuple[str, dict[str, Any]]] = []
        for role, values in materials_by_role.items():
            target = (
                design_specs
                if role in design_roles
                else commercial_specs
                if role in commercial_roles
                else None
            )
            if target is None:
                continue
            for value in values or ():
                if not isinstance(value, Mapping):
                    continue
                spec = _concrete_material_spec(value)
                if spec is not None:
                    target.append((str(role), spec))
        if not design_specs or not commercial_specs:
            continue
        strength_classes = {spec["strength"] for _role, spec in design_specs}.intersection(
            spec["strength"] for _role, spec in commercial_specs
        )
        for strength in sorted(strength_classes):
            design = [(role, spec) for role, spec in design_specs if spec["strength"] == strength]
            commercial = [
                (role, spec) for role, spec in commercial_specs if spec["strength"] == strength
            ]
            differences: list[dict[str, Any]] = []
            for property_key, label in (
                ("frost", "морозостойкость"),
                ("water", "водонепроницаемость"),
            ):
                design_values = {
                    int(spec[f"{property_key}_value"])
                    for _role, spec in design
                    if spec.get(f"{property_key}_value") is not None
                }
                commercial_values = {
                    int(spec[f"{property_key}_value"])
                    for _role, spec in commercial
                    if spec.get(f"{property_key}_value") is not None
                }
                if not design_values or not commercial_values or design_values == commercial_values:
                    continue
                differences.append(
                    {
                        "property": label,
                        "design": sorted(
                            {
                                str(spec[f"{property_key}_label"])
                                for _role, spec in design
                                if spec.get(f"{property_key}_label")
                            }
                        ),
                        "commercial": sorted(
                            {
                                str(spec[f"{property_key}_label"])
                                for _role, spec in commercial
                                if spec.get(f"{property_key}_label")
                            }
                        ),
                    }
                )
            if not differences:
                continue
            locator_ids = sorted(
                {
                    str(spec["source_locator_id"])
                    for _role, spec in [*design, *commercial]
                    if spec.get("source_locator_id")
                }
            )
            descriptions = [
                f"{item['property']}: проект {', '.join(item['design'])}, "
                f"коммерческие документы {', '.join(item['commercial'])}"
                for item in differences
            ]
            result.append(
                {
                    "material_comparison_id": semantic_digest(
                        {
                            "work_scope_id": work.get("work_scope_id"),
                            "strength": strength,
                            "differences": differences,
                        }
                    ),
                    "classification": "MATERIAL_DIFFERENCE",
                    "professional_status": "Характеристики бетона различаются",
                    "facility": work.get("facility"),
                    "facility_id": work.get("facility_id"),
                    "work": work.get("work_name"),
                    "material": f"Бетон {strength}",
                    "description": "; ".join(descriptions) + ".",
                    "design_roles": sorted({role for role, _spec in design}),
                    "commercial_roles": sorted({role for role, _spec in commercial}),
                    "source_locator_ids": locator_ids,
                    "sources": _source_refs(locator_ids, source_context),
                }
            )
    return _deduplicate_dicts(result)


def _issues(
    defects: Iterable[Mapping[str, Any]],
    comparisons: Iterable[Mapping[str, Any]],
    scope_comparisons: Iterable[Mapping[str, Any]],
    sheet_pile_schedule: Iterable[Mapping[str, Any]],
    works: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
    *,
    material_comparisons: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for comparison in material_comparisons:
        locators = [str(value) for value in comparison.get("source_locator_ids") or ()]
        issues.append(
            {
                "issue_id": str(comparison["material_comparison_id"]),
                "kind": "Различие характеристик материала",
                "location": comparison.get("facility"),
                "subject": f"{comparison.get('work')} — {comparison.get('material')}",
                "description": comparison.get("description"),
                "practical_consequence": (
                    "Различие характеристик влияет на состав поставки, цену и приёмку материала."
                ),
                "recommended_action": (
                    f"Просим подтвердить требуемые характеристики {comparison.get('material')} "
                    f"для {comparison.get('facility')} и привести к одному значению "
                    "проект и ВОР/смету."
                ),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Установленное расхождение маркировки",
            }
        )
    for comparison in _professional_quantity_issue_comparisons(comparisons):
        if comparison.get("difference") in {None, "0"} and "различаются" not in str(
            comparison.get("conclusion")
        ):
            continue
        comparison_kind = str(comparison.get("comparison_kind") or "quantity")
        description = str(comparison.get("conclusion") or "")
        consequence = "Объём и стоимость работ требуют согласования до подачи предложения."
        action = "Запросить у Заказчика подтверждение применяемого объёма и документа-основания."
        if comparison_kind == "quantity" and comparison.get("difference") is not None:
            description, consequence, action = _quantity_difference_professional_text(comparison)
        issues.append(
            {
                "issue_id": str(comparison["comparison_id"]),
                "kind": (
                    "Расхождение продолжительности"
                    if comparison_kind == "duration"
                    else "Расхождение объёмов"
                    if comparison.get("difference") is not None
                    else "Несопоставимые единицы"
                ),
                "location": comparison.get("facility"),
                "subject": comparison.get("work"),
                "description": description,
                "practical_consequence": (
                    "Продолжительность работ и календарные условия требуют согласования "
                    "до подачи предложения."
                    if comparison_kind == "duration"
                    else consequence
                ),
                "recommended_action": (action),
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
        "waterproofing",
        "backfill",
        "reclamation",
        "sheet_piling",
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

    profile_rows_by_facility: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in sheet_pile_schedule:
        row = dict(raw)
        if row.get("facility_id") and row.get("profiles_by_document"):
            profile_rows_by_facility[str(row["facility_id"])].append(row)
    role_order = {"ПД": 0, "РД": 1, "Спецификация": 2, "ВОР": 3, "Смета": 4}
    for facility_rows in profile_rows_by_facility.values():
        profiles_by_role: dict[str, set[str]] = defaultdict(set)
        profile_locators: set[str] = set()
        for row in facility_rows:
            for role, values in dict(row.get("profiles_by_document") or {}).items():
                profiles_by_role[str(role)].update(str(value) for value in values or ())
            profile_locators.update(str(value) for value in row.get("source_locator_ids") or ())
        distinct_profile_sets = {
            tuple(sorted(values)) for values in profiles_by_role.values() if values
        }
        if len(profiles_by_role) < 2 or len(distinct_profile_sets) < 2:
            continue
        facility = str(facility_rows[0].get("facility") or "Место требует уточнения")
        role_descriptions = [
            f"{role}: {', '.join(sorted(profiles_by_role[role]))}"
            for role in sorted(profiles_by_role, key=lambda value: role_order.get(value, 99))
        ]
        locators = sorted(profile_locators)
        issues.append(
            {
                "issue_id": semantic_digest(
                    {
                        "kind": "sheet_pile_profile_difference",
                        "facility": facility,
                        "profiles_by_role": {
                            role: sorted(values) for role, values in profiles_by_role.items()
                        },
                        "locators": locators,
                    }
                ),
                "kind": "Профиль шпунта требует согласования",
                "location": facility,
                "subject": "Профиль шпунта",
                "description": (
                    f"Для {facility} в документах указаны разные профили: "
                    f"{'; '.join(role_descriptions)}."
                ),
                "practical_consequence": (
                    "Разные профили могут изменить массу, стоимость и соответствие "
                    "принятому расчётному решению."
                ),
                "recommended_action": (
                    f"Просим подтвердить применяемый профиль шпунта для {facility} и "
                    "привести проект, ВОР и смету к одному обозначению."
                ),
                "source_locator_ids": locators,
                "sources": _source_refs(locators, source_context),
                "status": "Установлено различие обозначений в документах сооружения",
            }
        )
    commercial_sheet_pile_scope = _commercial_sheet_pile_scope_summary(sheet_pile_schedule)
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
                    + (
                        f" Найденный коммерческий объём: {commercial_sheet_pile_scope}."
                        if commercial_sheet_pile_scope
                        else ""
                    )
                ),
                "practical_consequence": (
                    "Нельзя воспроизводимо подтвердить полноту и цену этого объёма "
                    "для отдельного сооружения."
                ),
                "recommended_action": (
                    (
                        "Просим предоставить пообъектную разбивку найденных коммерческих "
                        f"объёмов ({commercial_sheet_pile_scope}) и подтвердить состав "
                        "шпунтовых работ для данного сооружения."
                    )
                    if commercial_sheet_pile_scope
                    else (
                        "Запросить у Заказчика ведомость распределения объёмов по сооружениям "
                        "и подтвердить состав работ для данного сооружения."
                    )
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


def _professional_quantity_issue_comparisons(
    comparisons: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse duplicate design-to-commercial findings, not their source comparisons.

    VOR and estimate frequently carry the same commercial quantity.  The
    comparison schedule must retain both checks, while the engineer should see
    one issue when both commercial documents agree with each other and differ
    from the same design value.
    """

    rows = [dict(value) for value in comparisons]
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for row in rows:
        left = dict(row.get("left") or {})
        right = dict(row.get("right") or {})
        if row.get("classification") != "QUANTITY_DIFFERENCE" or str(
            right.get("document_role") or ""
        ) not in {"ВОР", "Смета"}:
            passthrough.append(row)
            continue
        key = (
            str(row.get("work_scope_id") or ""),
            str(row.get("facility") or ""),
            str(row.get("work") or ""),
            str(row.get("comparison_kind") or "quantity"),
            str(left.get("document_role") or ""),
            str(left.get("value") or ""),
            str(left.get("unit") or ""),
            str(right.get("value") or ""),
            str(right.get("unit") or ""),
            str(row.get("difference") or ""),
        )
        groups[key].append(row)

    for grouped in groups.values():
        roles = {
            str(dict(value.get("right") or {}).get("document_role") or "") for value in grouped
        }
        if len(grouped) == 1 or roles != {"ВОР", "Смета"}:
            passthrough.extend(grouped)
            continue
        base = dict(grouped[0])
        left = dict(base.get("left") or {})
        right = dict(base.get("right") or {})
        right["document_role"] = "ВОР/Смета"
        base["right"] = right
        unit = str(left.get("unit") or right.get("unit") or "").strip()
        base["comparison_id"] = semantic_digest(
            {
                "kind": "consolidated_quantity_issue",
                "comparison_ids": sorted(str(value.get("comparison_id")) for value in grouped),
            }
        )
        base["conclusion"] = (
            f"Разница {left.get('document_role')} ↔ ВОР/Смета: "
            f"{base.get('difference')}{f' {unit}' if unit else ''}"
        )
        base["source_locator_ids"] = sorted(
            {
                str(locator_id)
                for value in grouped
                for locator_id in value.get("source_locator_ids") or ()
            }
        )
        passthrough.append(base)
    return passthrough


def _quantity_difference_professional_text(
    comparison: Mapping[str, Any],
) -> tuple[str, str, str]:
    left = dict(comparison.get("left") or {})
    right = dict(comparison.get("right") or {})
    difference = Decimal(str(comparison.get("difference") or "0"))
    magnitude = _decimal_text(abs(difference))
    unit = str(left.get("unit") or right.get("unit") or "").strip()
    amount = f"{magnitude} {unit}".strip()
    left_role = str(left.get("document_role") or "проект")
    right_role = str(right.get("document_role") or "коммерческие документы")
    left_value = f"{left.get('value')} {unit}".strip()
    right_value = f"{right.get('value')} {unit}".strip()
    description = f"{left_role}: {left_value}; {right_role}: {right_value}. "
    design_roles = {"ПД", "РД", "Спецификация"}
    commercial_roles = {"ВОР", "Смета", "ВОР/Смета"}
    if left_role in {"ВОР", "Смета"} and right_role in {"ВОР", "Смета"}:
        right_location = {"Смета": "смете", "ВОР": "ВОР"}.get(right_role, right_role)
        left_object = {"Смета": "смету", "ВОР": "ВОР"}.get(left_role, left_role)
        right_object = {"Смета": "смету", "ВОР": "ВОР"}.get(right_role, right_role)
        if difference > 0:
            relation = f"В {right_location} учтено на {amount} меньше, чем в {left_role}."
        else:
            relation = f"В {right_location} учтено на {amount} больше, чем в {left_role}."
        return (
            description + relation,
            "Различие между коммерческими документами создаёт неопределённость "
            "объёма для расчёта предложения и последующего закрытия работ.",
            f"Просим подтвердить согласованный объём и привести {left_object} и "
            f"{right_object} к одному значению.",
        )
    if left_role not in design_roles or right_role not in commercial_roles:
        return (
            description + f"Документы различаются на {amount}.",
            "Различие объёмов требует определения применяемого документа-основания.",
            "Просим подтвердить применяемый объём и документ-основание для расчёта предложения.",
        )
    if difference > 0:
        return (
            description + f"В коммерческих документах учтено на {amount} меньше, чем в проекте.",
            f"Объём {amount} может остаться нерасценённым и привести к росту "
            "объёма работ после заключения договора.",
            f"Просим включить недостающий объём {amount} в {right_role} либо "
            f"подтвердить изменение проектного объёма {left_role}.",
        )
    return (
        description + f"Коммерческий объём превышает проектный на {amount}.",
        f"Без подтверждённого проектного основания лишний коммерческий объём {amount} "
        "создаёт риск спора о составе и стоимости работ.",
        f"Просим подтвердить проектное основание объёма {right_value} в {right_role} "
        f"либо привести его в соответствие с {left_role} ({left_value}).",
    )


def _commercial_sheet_pile_scope_summary(
    schedule: Iterable[Mapping[str, Any]],
) -> str:
    """Describe safely consolidated commercial quantities without allocating them."""

    values: list[str] = []
    for raw in schedule:
        row = dict(raw)
        if row.get("facility_id") is not None:
            continue
        operation = str(row.get("operation") or "Шпунтовые работы")
        commercial = dict(row.get("commercial_quantities") or {})
        for role in sorted(commercial):
            for quantity in commercial[role] or ():
                value = quantity.get("value")
                unit = str(quantity.get("unit") or "").strip()
                if value is None or not unit:
                    continue
                values.append(f"{operation} — {value} {unit} ({role})")
    return "; ".join(dict.fromkeys(values))


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
    project_fields: Iterable[Mapping[str, Any]],
    structure_relationships: Iterable[Mapping[str, Any]],
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
    structures_by_facility, connections_by_facility = _facility_structure_links(
        facilities,
        structure_relationships,
        source_context,
    )
    characteristics_by_facility = _facility_characteristics(
        facilities,
        project_fields,
        source_context,
    )
    cards: list[dict[str, Any]] = []
    for raw in facilities:
        facility = dict(raw)
        facility_id = str(facility.get("facility_id") or "")
        name = str(facility.get("name") or "")
        facility_works = works_by_facility.get(facility_id, [])
        facility_pits = pit_by_facility.get(facility_id, [])
        facility_structures = structures_by_facility.get(facility_id, [])
        facility_connections = connections_by_facility.get(facility_id, [])
        facility_issues = issues_by_facility.get(name, [])
        contributing_locator_ids = sorted(
            {
                *(str(value) for value in facility.get("source_locator_ids") or ()),
                *(
                    str(value)
                    for row in [
                        *facility_pits,
                        *facility_structures,
                        *facility_connections,
                        *facility_works,
                        *facility_issues,
                    ]
                    for value in row.get("source_locator_ids") or ()
                ),
            }
        )
        cards.append(
            {
                "facility": facility,
                "purpose": None,
                "pits": facility_pits,
                "structures": facility_structures,
                "connections": facility_connections,
                "characteristics": characteristics_by_facility.get(facility_id, []),
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
                "materials": _facility_material_schedule(facility_works),
                "comparisons": comparisons_by_facility.get(name, []),
                "issues": facility_issues,
                "documents": _source_refs(contributing_locator_ids, source_context),
                "missing_information": [
                    label
                    for condition, label in (
                        (
                            not pit_by_facility.get(facility_id),
                            "Котлован не установлен или не предусмотрен",
                        ),
                        (not facility_works, "Работы не привязаны к сооружению"),
                        (
                            not structures_by_facility.get(facility_id),
                            "Состав конструкций требует дальнейшей привязки",
                        ),
                    )
                    if condition
                ],
            }
        )
    return cards


def _facility_material_schedule(works: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Consolidate repeated material mentions without merging different scopes.

    Specifications, estimates and work schedules commonly repeat the same
    material row.  A facility dossier needs one readable row for an identical
    work/role/value while retaining every source locator.  A different work,
    document role, quantity or unit remains a separate engineering row.
    """

    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for work in works:
        work_name = str(work.get("work_name") or "Работа").strip()
        materials_by_document = work.get("materials_by_document")
        if not isinstance(materials_by_document, Mapping):
            continue
        for document_role, materials in materials_by_document.items():
            if not isinstance(materials, Iterable) or isinstance(materials, (str, bytes)):
                continue
            for raw_material in materials:
                if not isinstance(raw_material, Mapping):
                    continue
                material = dict(raw_material)
                name = str(material.get("name") or "").strip()
                if not name:
                    continue
                quantity = str(material.get("quantity") or "").strip()
                unit = str(material.get("unit") or "").strip()
                role = str(document_role).strip()
                key = (_normalized(name), quantity, _normalized(unit), role, work_name)
                locator_ids = {
                    str(value)
                    for value in (
                        material.get("source_locator_id"),
                        *(material.get("source_locator_ids") or ()),
                    )
                    if value
                }
                existing = grouped.get(key)
                if existing is None:
                    material["document_role"] = role
                    material["work_name"] = work_name
                    material["source_locator_ids"] = sorted(locator_ids)
                    material.pop("source_locator_id", None)
                    grouped[key] = material
                    continue
                existing["source_locator_ids"] = sorted(
                    {
                        *(str(value) for value in existing.get("source_locator_ids") or ()),
                        *locator_ids,
                    }
                )
    return sorted(
        grouped.values(),
        key=lambda item: (
            str(item.get("work_name") or ""),
            str(item.get("document_role") or ""),
            _normalized(item.get("name")),
            str(item.get("quantity") or ""),
            _normalized(item.get("unit")),
        ),
    )


def _facility_characteristics(
    facilities: Iterable[Mapping[str, Any]],
    project_fields: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Attach fields whose label explicitly names exactly one facility.

    A value on the same page is not enough: specification pages often contain
    several LOS/KNS variants.  Requiring the designation in the field label
    gives the professional dossier useful pump composition, capacity and head
    values without leaking one installation's parameter into another.
    """

    facility_by_designation = {
        str(value.get("designation")): dict(value)
        for value in facilities
        if value.get("designation")
    }
    grouped: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for raw in project_fields:
        row = dict(raw)
        label = str(row.get("label") or "").strip()
        value = str(row.get("value") or "").strip()
        designations = [
            designation
            for designation in facility_designations(label)
            if designation in facility_by_designation
        ]
        if len(designations) != 1 or not label or not value:
            continue
        facility = facility_by_designation[designations[0]]
        facility_id = str(facility.get("facility_id") or "")
        locator_id = str(row.get("source_locator_id") or "")
        key = (_normalized(label), _normalized(value))
        characteristic = grouped[facility_id].setdefault(
            key,
            {
                "label": label,
                "value": value,
                "source_locator_ids": [],
                "sources": [],
                "status": "Установлено по явно указанному сооружению",
            },
        )
        if locator_id:
            characteristic["source_locator_ids"] = sorted(
                {*characteristic["source_locator_ids"], locator_id}
            )
            characteristic["sources"] = _source_refs(
                characteristic["source_locator_ids"], source_context
            )
    return {
        facility_id: sorted(values.values(), key=lambda value: _normalized(value["label"]))
        for facility_id, values in grouped.items()
    }


_CONSTRUCTION_COMPONENT = re.compile(
    r"(?:фундамент|плит[аы]|стен[аы]|перекрыти|резервуар|камер[аы]|колод(?:ец|цы)|"
    r"труб(?:а|опровод)|коллектор|сет[ьи]|шпунтов\w*\s+ограждени|ограждени\w*\s+котлован|"
    r"свайн\w*\s+фундамент|основани|лоток|выпуск|экран|павильон|здани|сооружени)",
    re.IGNORECASE,
)


def _facility_structure_links(
    facilities: Iterable[Mapping[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Expose only explicit, same-fragment facility components and interfaces.

    Structure extraction contains many broad geographical and functional
    relationships.  A facility dossier must not turn document co-occurrence
    into containment.  This projection therefore accepts only relationships
    resolved on the same source fragment, with exactly one established
    facility endpoint and a recognisable construction component at the other
    endpoint.  Inter-facility relationships remain separate connections.
    """

    facility_rows = [dict(value) for value in facilities]
    node_to_facility: dict[str, dict[str, Any]] = {}
    for facility in facility_rows:
        for node_id in facility.get("member_structure_node_ids") or ():
            node_to_facility.setdefault(str(node_id), facility)
    structures: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    connections: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for raw in relationships:
        relationship = dict(raw)
        if relationship.get("resolution_state") != "resolved_same_evidence":
            continue
        subject = node_to_facility.get(str(relationship.get("subject_structure_node_id") or ""))
        object_ = node_to_facility.get(str(relationship.get("object_structure_node_id") or ""))
        if bool(subject) == bool(object_):
            continue
        related_facility = subject or object_
        if related_facility is None:
            continue
        facility_is_subject = subject is not None
        other_name = str(
            relationship.get("object_raw_name")
            if facility_is_subject
            else relationship.get("subject_raw_name") or ""
        ).strip()
        if not other_name:
            continue
        relationship_kind = str(relationship.get("relationship_kind") or "")
        other_designation = facility_designation(other_name)
        target = structures
        professional_relation: str | None = None
        if other_designation and other_designation != related_facility.get("designation"):
            if relationship_kind not in {"connects_to", "serves", "depends_on"}:
                continue
            target = connections
            professional_relation = {
                "connects_to": "Связано с сооружением",
                "serves": "Функциональная связь",
                "depends_on": "Зависит от сооружения",
            }[relationship_kind]
        elif relationship_kind == "contains" and facility_is_subject:
            professional_relation = "Входит в состав сооружения"
        elif relationship_kind == "located_in" and not facility_is_subject:
            professional_relation = "Расположено в границах сооружения"
        elif relationship_kind == "serves" and not facility_is_subject:
            professional_relation = "Обслуживает сооружение"
        elif relationship_kind == "connects_to" and _CONSTRUCTION_COMPONENT.search(other_name):
            target = connections
            professional_relation = "Подключение / технологический интерфейс"
        else:
            continue
        if target is structures and not _CONSTRUCTION_COMPONENT.search(other_name):
            continue
        locator_id = str(relationship.get("source_locator_id") or "")
        facility_id = str(related_facility.get("facility_id") or "")
        key = (_normalized(other_name), professional_relation)
        row = target[facility_id].setdefault(
            key,
            {
                "name": other_name,
                "relationship": professional_relation,
                "source_locator_ids": [],
                "sources": [],
                "status": "Установлено по явной связи в исходном документе",
            },
        )
        if locator_id:
            row["source_locator_ids"] = sorted({*row["source_locator_ids"], locator_id})
            row["sources"] = _source_refs(row["source_locator_ids"], source_context)
    return (
        {
            facility_id: sorted(values.values(), key=lambda value: _normalized(value["name"]))
            for facility_id, values in structures.items()
        },
        {
            facility_id: sorted(values.values(), key=lambda value: _normalized(value["name"]))
            for facility_id, values in connections.items()
        },
    )


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


def _document_composition(
    documents: Iterable[Mapping[str, Any]],
    *,
    source_context: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    role_counts = Counter(
        str(value.get("document_role") or "Роль не установлена") for value in documents
    )
    embedded_vor_documents = {
        str(value.get("source_version_id") or "")
        for value in (source_context or {}).values()
        if value.get("page_is_bill_of_quantities") is True
    }
    if embedded_vor_documents:
        role_counts["ВОР"] = len(embedded_vor_documents)
    expected_roles = ("ПД", "РД", "Спецификация", "ВОР", "Смета", "Договор")
    available_roles = [role for role in expected_roles if role_counts.get(role)]
    missing_roles = [role for role in expected_roles if not role_counts.get(role)]
    present = "; ".join(f"{role} — {role_counts[role]}" for role in available_roles)
    unidentified = role_counts.get("Проектный документ", 0)
    if unidentified:
        present = (
            f"{present}; роль требует уточнения — {unidentified}"
            if present
            else (f"роль требует уточнения — {unidentified}")
        )
    if embedded_vor_documents:
        present = present.replace(
            f"ВОР — {len(embedded_vor_documents)}",
            f"ВОР в составе сметных файлов — {len(embedded_vor_documents)}",
        )
    return {
        "role_counts": dict(sorted(role_counts.items())),
        "available_roles": available_roles,
        "missing_roles": missing_roles,
        "embedded_vor_document_count": len(embedded_vor_documents),
        "professional_summary": (
            "В предоставленном комплекте установлены: "
            f"{present or 'профессиональные роли не установлены'}. "
            f"Отдельные документы не найдены: {', '.join(missing_roles) or 'нет'}. "
            "Отсутствующий вид документа ограничивает только соответствующее сопоставление, "
            "но не отменяет анализ имеющихся проектных материалов."
        ),
    }


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
    if "раздел пд" in name or "часть пд" in name:
        return "ПД"
    if (
        re.search(r"(?:^|[\s._-])рд(?:[\s._-]|$)", name)
        or " рр" in f" {name}"
        or "рабоч" in name
        or role == "working_documentation"
    ):
        return "РД"
    if role in {"project_documentation", "explanatory_note", "drawing_or_scheme"}:
        return "ПД"
    return "Проектный документ"


def _unique_values(values: Iterable[Mapping[str, Any]], kind: str) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in values:
        row = dict(raw)
        if kind == "quantity":
            raw_value = row.get("normalized_value", row.get("value"))
            raw_unit = row.get("normalized_unit", row.get("unit", row.get("raw_unit")))
            display_value, display_unit = _display_quantity(raw_value, raw_unit)
            payload = {
                "value": display_value,
                "unit": display_unit,
                "source_locator_id": row.get("source_locator_id"),
            }
            rendered = {
                "value": display_value,
                "unit": display_unit,
                "raw_value": row.get("value", row.get("raw_value", raw_value)),
                "raw_unit": row.get("raw_unit", raw_unit),
                "source_locator_id": row.get("source_locator_id"),
            }
        else:
            payload = {
                "name": row.get("normalized_name", row.get("value")),
                "quantity": row.get("normalized_value", row.get("raw_quantity")),
                "unit": row.get("normalized_unit", row.get("unit", row.get("raw_unit"))),
                "source_locator_id": row.get("source_locator_id"),
            }
            rendered = {
                "name": row.get("value", row.get("raw_name")),
                "quantity": row.get("normalized_value", row.get("raw_quantity")),
                "unit": row.get("normalized_unit", row.get("unit", row.get("raw_unit"))),
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
            quantity = Decimal(str(raw).replace(",", "."))
        except InvalidOperation:
            continue
        scaled = re.fullmatch(r"(?P<factor>10|100|1000)\s*(?P<unit>м[23]|м|шт)", unit)
        if scaled is not None:
            quantity *= Decimal(scaled.group("factor"))
            unit = scaled.group("unit")
        unique.add((quantity, unit))
    return next(iter(unique)) if len(unique) == 1 else None


def _display_quantity(value: object, unit_value: object) -> tuple[object, str]:
    """Render scaled estimate units as physical totals without losing raw fields."""

    unit = _normalized_unit(unit_value)
    scaled = re.fullmatch(r"(?P<factor>10|100|1000)\s*(?P<unit>м[23]|м|шт)", unit)
    if scaled is None or value is None:
        return value, unit
    try:
        quantity = Decimal(str(value).replace(",", ".")) * Decimal(scaled.group("factor"))
    except InvalidOperation:
        return value, unit
    return _decimal_text(quantity), scaled.group("unit")


def _normalized_unit(value: object) -> str:
    normalized = " ".join(str(value or "").replace("\xa0", " ").strip().casefold().split())
    normalized = normalized.rstrip(".")
    return {"m2": "м2", "m3": "м3"}.get(normalized, normalized)


def _duration_unit(value: object) -> bool:
    normalized = _normalized_unit(value)
    return normalized.startswith(("месяц", "мес", "день", "дн", "недел", "год"))


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


def _merge_consolidated_quantity_mentions(
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
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
        current["occurrence_count"] += int(row.get("occurrence_count") or 1)
        current["source_locator_ids"] = sorted(
            {
                *(str(value) for value in current.get("source_locator_ids") or ()),
                *(str(value) for value in row.get("source_locator_ids") or ()),
            }
        )
    return [grouped[key] for key in sorted(grouped)]


def _sheet_pile_profiles(normalized: str) -> list[str]:
    profiles: list[str] = []
    for match in re.finditer(r"\bл5(?:\s*ум|\s*10)?\b", normalized):
        compact = match.group(0).upper().replace(" ", "")
        value = "Л5УМ" if compact == "Л5УМ" else "Л5-10" if compact == "Л510" else "Л5"
        profiles.append(value)
    return _ordered_unique(profiles)


def _material_sheet_pile_profiles(
    material: Mapping[str, Any],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    explicit_profiles = _sheet_pile_profiles(_normalized(material.get("name")))
    if explicit_profiles:
        return explicit_profiles
    normalized_name = _normalized(material.get("name"))
    context = source_context.get(str(material.get("source_locator_id") or ""), {})
    page_profiles = [str(value) for value in context.get("page_sheet_pile_profiles") or ()]
    incomplete_sheet_pile_material = (
        normalized_name.startswith("ум из стали")
        or "шпунт" in normalized_name
        or ("профили фасонные" in normalized_name and "свай" in normalized_name)
    )
    if page_profiles and incomplete_sheet_pile_material:
        return _ordered_unique(page_profiles)
    return []


def _professional_material_values(
    materials: Iterable[Mapping[str, Any]],
    source_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in materials:
        material = dict(raw)
        original = str(material.get("name") or "")
        context = source_context.get(str(material.get("source_locator_id") or ""), {})
        page_profiles = [str(value) for value in context.get("page_sheet_pile_profiles") or ()]
        explicit_profiles = _sheet_pile_profiles(_normalized(original))
        if explicit_profiles:
            if page_profiles and set(explicit_profiles) != set(page_profiles):
                material["page_context_profiles"] = _ordered_unique(page_profiles)
                material["profile_context_note"] = (
                    "Профиль в строке материала отличается от обозначения в контексте листа."
                )
        elif len(page_profiles) == 1 and _normalized(original).startswith("ум из стали"):
            material["source_name"] = original
            material["name"] = f"Шпунт Л5-УМ {original[2:].strip()}"
        elif (
            len(page_profiles) == 1
            and "профили фасонные" in _normalized(original)
            and "шпунтов" in _normalized(original)
        ):
            material["source_name"] = original
            material["name"] = (
                f"{original} {'Л5-УМ' if page_profiles[0] == 'Л5УМ' else page_profiles[0]}"
            )
        result.append(material)
    return result


def _normalized(value: object) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё.,]+", " ", str(value or "").casefold().replace("ё", "е")).split()
    )
