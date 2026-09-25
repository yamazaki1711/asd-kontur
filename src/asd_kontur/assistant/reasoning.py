"""Bounded professional-assistant planning and answer quality contracts."""

# ruff: noqa: E501, RUF001 -- schemas and Russian professional terms stay readable.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from asd_kontur.ntd.search_corpus import normalize_designation

MAX_TOOL_STEPS = 4
MAX_HISTORY_MESSAGES = 8
MAX_HISTORY_CHARS = 6_000


TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "consultant.search_practice",
        "description": "Найти методические рекомендации в Пособии по исполнительной документации.",
        "schema": {"query": "string", "limit": "integer 1..8"},
    },
    {
        "name": "consultant.get_practice_fragment",
        "description": "Получить полный точный фрагмент Пособия по найденному source_id.",
        "schema": {"source_id": "uuid"},
    },
    {
        "name": "consultant.get_ntd_inventory",
        "description": "Получить сводное состояние нормативной памяти без поиска по содержанию.",
        "schema": {},
    },
    {
        "name": "consultant.resolve_ntd_designation",
        "description": "Точно разрешить явно названное обозначение СП, ГОСТ, приказа или инструкции.",
        "schema": {"designation": "string"},
    },
    {
        "name": "consultant.search_ntd_documents",
        "description": "Найти нормативные документы по обозначению, названию и области применения.",
        "schema": {"query": "string", "limit": "integer 1..10"},
    },
    {
        "name": "consultant.search_ntd_content",
        "description": "Найти страницы в исходном тексте уже имеющихся нормативных документов.",
        "schema": {
            "query": "string",
            "limit": "integer 1..8",
            "search_document_id": "uuid optional",
        },
    },
    {
        "name": "consultant.get_ntd_page",
        "description": "Получить точную страницу найденного нормативного документа.",
        "schema": {"search_document_id": "uuid", "page_number": "integer >=1"},
    },
    {
        "name": "consultant.get_ntd_section_context",
        "description": "Получить соседние страницы вокруг точной страницы нормативного документа.",
        "schema": {
            "search_document_id": "uuid",
            "page_number": "integer >=1",
            "radius": "integer 1..2",
        },
    },
    {
        "name": "consultant.get_verified_provisions",
        "description": "Получить проверенные структурированные положения указанного документа, если они опубликованы.",
        "schema": {
            "search_document_id": "uuid",
            "query": "string optional",
            "limit": "integer 1..10",
        },
    },
    {
        "name": "consultant.get_ntd_processing_status",
        "description": "Получить раздельные статусы bytes, страниц, текста, структуры и проверки редакции.",
        "schema": {"search_document_id": "uuid"},
    },
    {
        "name": "consultant.find_applicability_candidates",
        "description": "Найти кандидатов применимости НТД с учётом вопроса и подтверждённой модели текущего ОКС; результат не является окончательным решением.",
        "schema": {"query": "string", "limit": "integer 1..8"},
    },
    {
        "name": "consultant.search_ntd",
        "description": "Совместимый поиск только по проверенным положениям НТД.",
        "schema": {"query": "string", "limit": "integer 1..8"},
    },
    {
        "name": "consultant.get_ntd_provision",
        "description": "Совместимое получение точного проверенного нормативного положения.",
        "schema": {"source_id": "uuid"},
    },
    {
        "name": "consultant.get_workspace_overview",
        "description": "Получить краткую общую модель текущего объекта строительства.",
        "schema": {},
    },
    {
        "name": "consultant.get_project_entity_inventory",
        "description": "Получить покрытие и сверенный перечень кандидатов объектов/сооружений текущего ОКС; использовать для полного подсчёта ЛОС, КНС, котлованов, зон и сооружений.",
        "schema": {
            "kind": "local_area|facility|excavation_pit|structure|zone optional",
            "query": "string optional",
            "limit": "integer 1..30",
        },
    },
    {
        "name": "consultant.search_workspace_documents",
        "description": "Найти релевантные фрагменты документов только текущего объекта.",
        "schema": {"query": "string", "limit": "integer 1..10"},
    },
    {
        "name": "consultant.get_workspace_fragment",
        "description": "Получить полный точный фрагмент документа текущего объекта.",
        "schema": {"source_id": "uuid"},
    },
    {
        "name": "consultant.get_work_packages",
        "description": "Найти относящиеся к вопросу наблюдения работ, связанные МТР и объёмы текущего объекта, а также доказательные кандидаты связи работ с площадками и сооружениями; результат содержит покрытие выборки и не является полным перечнем без явного признака полноты.",
        "schema": {"query": "string", "limit": "integer 1..20"},
    },
    {
        "name": "consultant.get_requirement_matrix",
        "description": "Получить матрицу требований к контролю и исполнительной документации.",
        "schema": {},
    },
    {
        "name": "consultant.get_discrepancies",
        "description": "Получить материализованные расхождения и конфликты документов объекта.",
        "schema": {},
    },
    {
        "name": "consultant.get_id_package",
        "description": "Получить состав и комплектность исполнительной документации.",
        "schema": {},
    },
    {
        "name": "consultant.get_mode_result",
        "description": "Получить сформированный профессиональный результат текущего режима.",
        "schema": {},
    },
    {
        "name": "consultant.get_information_gaps",
        "description": "Получить отсутствующие, конфликтные и требующие уточнения сведения.",
        "schema": {},
    },
    {
        "name": "consultant.estimate_concrete_early_strength",
        "description": "Оценить раннюю прочность бетона по классу, возрасту и условиям твердения.",
        "schema": {
            "concrete_class": "string optional",
            "age_days": "integer",
            "temperature_c": "number optional",
            "curing_condition": "string optional",
        },
    },
)

TOOL_NAMES = frozenset(item["name"] for item in TOOL_DEFINITIONS)
_NO_ARGUMENT_TOOLS = frozenset(
    {
        "consultant.get_workspace_overview",
        "consultant.get_ntd_inventory",
        "consultant.get_requirement_matrix",
        "consultant.get_discrepancies",
        "consultant.get_id_package",
        "consultant.get_mode_result",
        "consultant.get_information_gaps",
    }
)
_DEPENDENT_SOURCE_TOOLS = {
    "consultant.get_practice_fragment": ("consultant.search_practice", "source_id"),
    "consultant.get_ntd_provision": ("consultant.search_ntd", "source_id"),
    "consultant.get_workspace_fragment": ("consultant.search_workspace_documents", "source_id"),
    "consultant.get_ntd_page": ("consultant.resolve_ntd_designation", "search_document_id"),
    "consultant.get_ntd_section_context": (
        "consultant.resolve_ntd_designation",
        "search_document_id",
    ),
    "consultant.get_verified_provisions": (
        "consultant.resolve_ntd_designation",
        "search_document_id",
    ),
    "consultant.get_ntd_processing_status": (
        "consultant.resolve_ntd_designation",
        "search_document_id",
    ),
}

# These tools describe derived workspace metadata.  They can be deferred when a
# project-content question has exhausted the bounded tool budget: document
# evidence is a prerequisite for an answer about an object fact, while none of
# these calls establishes that fact by itself.
_WORKSPACE_METADATA_TOOLS = frozenset(
    {
        "consultant.get_workspace_overview",
        "consultant.get_work_packages",
        "consultant.get_requirement_matrix",
        "consultant.get_discrepancies",
        "consultant.get_id_package",
        "consultant.get_mode_result",
        "consultant.get_information_gaps",
    }
)


@dataclass(frozen=True, slots=True)
class PlannedToolCall:
    tool: str
    arguments: dict[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class SearchPlan:
    intent: str
    needs_clarification: bool
    clarifying_question: str | None
    steps: tuple[PlannedToolCall, ...]


@dataclass(frozen=True, slots=True)
class AdequacyDecision:
    sufficient: bool
    reason: str
    additional_step: PlannedToolCall | None
    needs_clarification: bool
    clarifying_question: str | None


@dataclass(frozen=True, slots=True)
class SynthesizedAnswer:
    answer: str
    answer_type: str
    needs_clarification: bool
    used_source_ids: tuple[str, ...]
    dialogue_summary: str
    active_subjects: tuple[str, ...]


def _required_step_replacement_index(
    steps: tuple[PlannedToolCall, ...],
    *,
    preferred_leaf_tools: frozenset[str] = frozenset(),
    protected_tools: frozenset[str] = frozenset(),
) -> int:
    """Select a leaf step that can be replaced without orphaning dependencies."""

    prerequisite_tools = {
        _DEPENDENT_SOURCE_TOOLS[step.tool][0]
        for step in steps
        if step.tool in _DEPENDENT_SOURCE_TOOLS
    }
    replaceable = [
        index
        for index, step in enumerate(steps)
        if step.tool not in prerequisite_tools and step.tool not in protected_tools
    ]
    preferred = [index for index in replaceable if steps[index].tool in preferred_leaf_tools]
    if preferred:
        return preferred[-1]
    if replaceable:
        return replaceable[-1]
    raise ValueError("assistant_plan_required_workspace_step_unavailable")


def ensure_explicit_designation_resolution(plan: SearchPlan, question: str) -> SearchPlan:
    """Make exact inventory resolution the first read when the user names an NTD."""

    if plan.needs_clarification:
        return plan

    matches = re.finditer(
        r"\b(?:СП\s*\d+(?:\.\d+){0,3}|ГОСТ(?:\s+Р)?\s*\d+(?:[.\-]\d+)*|"
        r"приказ(?:а|у|ом)?(?:\s+[^№\n]{0,60})?\s*№\s*[0-9]+(?:/пр)?)",
        question,
        re.IGNORECASE,
    )
    designations: list[str] = []
    seen_normalized: set[str] = set()
    for match in matches:
        raw_designation = " ".join(match.group(0).split())
        normalized = normalize_designation(raw_designation)
        if normalized not in seen_normalized:
            seen_normalized.add(normalized)
            designations.append(raw_designation)

    if not designations:
        return plan

    resolutions = [
        PlannedToolCall(
            "consultant.resolve_ntd_designation",
            {"designation": designation},
            "Пользователь явно назвал нормативный документ; сначала проверяется canonical inventory.",
        )
        for designation in designations
    ]
    remaining = [step for step in plan.steps if step.tool != "consultant.resolve_ntd_designation"]
    return SearchPlan(
        plan.intent,
        False,
        None,
        tuple([*resolutions, *remaining][:MAX_TOOL_STEPS]),
    )


def ensure_workspace_content_search(plan: SearchPlan, question: str) -> SearchPlan:
    """Require a content read for a project question that asks for project facts.

    A workspace overview is useful for project metadata, but it cannot establish
    enumeration, location, or other facts that must be read from source documents.
    """

    if plan.needs_clarification or plan.intent not in {"workspace", "mixed"}:
        return plan
    if not requires_workspace_document_content(question):
        return plan
    content_tools = {
        "consultant.search_workspace_documents",
        "consultant.get_workspace_fragment",
    }
    if any(step.tool in content_tools for step in plan.steps):
        return plan
    content_step = PlannedToolCall(
        "consultant.search_workspace_documents",
        {"query": question, "limit": 10},
        "Вопрос запрашивает факт, перечень или расположение по проекту; требуется поиск по содержимому документов, а не только обзор объекта.",
    )
    if len(plan.steps) < MAX_TOOL_STEPS:
        steps = (*plan.steps, content_step)
    else:
        # A full planner budget must not silently erase the required content
        # read.  Replace only a metadata call; dependent retrieval and explicit
        # designation resolution keep their ordering and prerequisites.
        replace_index = next(
            (
                index
                for index, step in enumerate(plan.steps)
                if step.tool in _WORKSPACE_METADATA_TOOLS
            ),
            None,
        )
        if replace_index is None:
            replace_index = _required_step_replacement_index(plan.steps)
        steps = (
            *plan.steps[:replace_index],
            content_step,
            *plan.steps[replace_index + 1 :],
        )
    return SearchPlan(plan.intent, False, None, tuple(steps))


def ensure_workspace_entity_inventory(plan: SearchPlan, question: str) -> SearchPlan:
    """Require structured inventory coverage for project-wide entity questions."""

    if plan.needs_clarification or plan.intent not in {"workspace", "mixed"}:
        return plan
    normalized = " ".join(question.casefold().split())
    if not re.search(r"\b(?:сколько|перечисл\w*|полный\s+перечень|все)\b", normalized):
        return plan
    kind: str | None = None
    if re.search(r"\bкотлован\w*\b", normalized):
        kind = "excavation_pit"
    elif re.search(r"\b(?:лос|кнс)\b", normalized):
        kind = "facility"
    elif re.search(r"\b(?:зон\w*|участ\w*)\b", normalized):
        kind = "local_area"
    elif re.search(r"\bсооружен\w*\b", normalized):
        kind = "structure"
    if kind is None:
        return plan
    if any(step.tool == "consultant.get_project_entity_inventory" for step in plan.steps):
        return plan
    inventory_step = PlannedToolCall(
        "consultant.get_project_entity_inventory",
        {"kind": kind, "limit": 30},
        "Для полного перечня или подсчёта требуется структурированный инвентарь и его покрытие, а не число поисковых совпадений.",
    )
    if len(plan.steps) < MAX_TOOL_STEPS:
        steps = (*plan.steps, inventory_step)
    else:
        replace_index = next(
            (
                index
                for index, step in enumerate(plan.steps)
                if step.tool in _WORKSPACE_METADATA_TOOLS
            ),
            None,
        )
        if replace_index is None:
            replace_index = _required_step_replacement_index(
                plan.steps,
                preferred_leaf_tools=frozenset({"consultant.get_workspace_fragment"}),
                protected_tools=frozenset({"consultant.search_workspace_documents"}),
            )
        steps = (
            *plan.steps[:replace_index],
            inventory_step,
            *plan.steps[replace_index + 1 :],
        )
    return SearchPlan(plan.intent, False, None, tuple(steps))


def bind_workspace_work_query(plan: SearchPlan, question: str) -> SearchPlan:
    """Bind work-observation retrieval to the actual user question.

    Qwen plans created before the query-aware tool contract can still emit an
    empty argument object.  Leaving that plan unchanged would expose an
    arbitrary membership prefix when a workspace contains more observations
    than the bounded assistant context.  The deterministic binding preserves
    the bounded result while making its selection reproducible and relevant.
    """

    if plan.needs_clarification:
        return plan
    bounded_query = " ".join(question.split())
    steps = tuple(
        PlannedToolCall(
            step.tool,
            (
                {"query": bounded_query, "limit": 20}
                if step.tool == "consultant.get_work_packages" and not step.arguments
                else step.arguments
            ),
            step.reason,
        )
        for step in plan.steps
    )
    return SearchPlan(plan.intent, plan.needs_clarification, plan.clarifying_question, steps)


def requires_workspace_document_content(question: str) -> bool:
    normalized = " ".join(question.casefold().split())
    # Mentioning documents alone does not identify the current workspace: e.g.
    # "Which documents are needed for an AOSR?" is a general practice question.
    if not re.search(
        r"\b(?:проект\w*|пд|рд|чертеж\w*|лист\w*|объект\w*)\b|"
        r"\b(?:в|из|по|согласно)\s+(?:(?:этих|этом|данных|данном|наших|"
        r"загруженн\w*|предоставленн\w*|имеющ\w*)\s+)*документ\w*\b|"
        r"\b(?:загруженн\w*|предоставленн\w*)\s+документ\w*\b|"
        r"\bдокумент\w*\s+(?:(?:я|мы|были|уже)\s+)*(?:загруз\w*|предостав\w*)\b",
        normalized,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:сколько|перечисл\w*|где|на\s+каких|на\s+каком|"
            r"какие|какой|какова|каковы|обознач\w*|располож\w*)",
            normalized,
        )
    )


def parse_search_plan(raw: str) -> SearchPlan:
    value = _json_object(raw)
    intent = str(value.get("intent", ""))
    if intent not in {
        "general_engineering",
        "normative",
        "workspace",
        "mixed",
        "clarification_required",
    }:
        raise ValueError("assistant_plan_intent_invalid")
    needs_clarification = value.get("needs_clarification")
    if not isinstance(needs_clarification, bool):
        raise ValueError("assistant_plan_clarification_flag_invalid")
    question = value.get("clarifying_question")
    if question is not None:
        question = " ".join(str(question).split())
        if not 5 <= len(question) <= 500:
            raise ValueError("assistant_plan_clarifying_question_invalid")
    raw_steps = value.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) > MAX_TOOL_STEPS:
        raise ValueError("assistant_plan_steps_invalid")
    steps: list[PlannedToolCall] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("assistant_plan_step_invalid")
        tool = str(raw_step.get("tool", ""))
        arguments = _tool_arguments(raw_step)
        reason = " ".join(str(raw_step.get("reason", "")).split())
        if tool not in TOOL_NAMES or not isinstance(arguments, dict) or not reason:
            raise ValueError("assistant_plan_tool_invalid")
        dependency = _DEPENDENT_SOURCE_TOOLS.get(tool)
        if (
            dependency is not None
            and not _is_uuid(str(arguments.get(dependency[1], "")))
            and any(step.tool == dependency[0] for step in steps)
        ):
            # Qwen sometimes emits an impossible dependent step with a UUID
            # placeholder.  The initial plan keeps the valid search; adequacy
            # may request the exact fragment only after a real identity exists.
            continue
        _validate_arguments(tool, arguments)
        steps.append(PlannedToolCall(tool, dict(arguments), reason[:500]))
    if needs_clarification and (not question or steps):
        raise ValueError("assistant_plan_clarification_invalid")
    if not needs_clarification:
        if intent == "general_engineering":
            if steps:
                allowed_tools = {
                    "consultant.search_practice",
                    "consultant.get_practice_fragment",
                    "consultant.get_ntd_inventory",
                    "consultant.resolve_ntd_designation",
                    "consultant.search_ntd_documents",
                    "consultant.search_ntd_content",
                    "consultant.get_ntd_page",
                    "consultant.get_ntd_section_context",
                    "consultant.get_verified_provisions",
                    "consultant.get_ntd_processing_status",
                    "consultant.search_ntd",
                    "consultant.get_ntd_provision",
                    "consultant.estimate_concrete_early_strength",
                }
                for step in steps:
                    if step.tool not in allowed_tools:
                        raise ValueError("assistant_plan_general_engineering_tools_invalid")
        else:
            if not steps:
                raise ValueError("assistant_plan_empty")
    return SearchPlan(intent, needs_clarification, question, tuple(steps))


def parse_synthesized_answer(raw: str, available_source_ids: set[str]) -> SynthesizedAnswer:
    value = _json_object(raw)
    answer = str(value.get("answer", "")).strip()
    answer_type = str(value.get("answer_type", ""))
    needs_clarification = value.get("needs_clarification")
    raw_sources = value.get("used_source_ids", [])
    summary = " ".join(str(value.get("dialogue_summary", "")).split())
    subjects = value.get("active_subjects", [])
    if not 2 <= len(answer) <= 12_000:
        raise ValueError("assistant_answer_invalid")
    if answer_type not in {
        "direct",
        "explanation",
        "procedure",
        "comparison",
        "workspace_conclusion",
        "clarification",
        "insufficient_data",
    }:
        raise ValueError("assistant_answer_type_invalid")
    if not isinstance(needs_clarification, bool):
        raise ValueError("assistant_answer_clarification_invalid")
    if not isinstance(raw_sources, list) or not all(isinstance(item, str) for item in raw_sources):
        raise ValueError("assistant_answer_sources_invalid")
    source_ids = tuple(dict.fromkeys(raw_sources))
    if not set(source_ids) <= available_source_ids:
        raise ValueError("assistant_answer_unknown_source")
    if not 1 <= len(summary) <= 1_000:
        raise ValueError("assistant_dialogue_summary_invalid")
    if not isinstance(subjects, list) or len(subjects) > 12:
        raise ValueError("assistant_active_subjects_invalid")
    normalized_subjects = tuple(
        " ".join(str(item).split())[:160] for item in subjects if str(item).strip()
    )
    if needs_clarification and answer_type != "clarification":
        raise ValueError("assistant_clarification_answer_type_invalid")
    return SynthesizedAnswer(
        answer,
        answer_type,
        needs_clarification,
        source_ids,
        summary,
        normalized_subjects,
    )


def parse_adequacy_decision(raw: str) -> AdequacyDecision:
    value = _json_object(raw)
    sufficient = value.get("sufficient")
    needs_clarification = value.get("needs_clarification", False)
    reason = " ".join(str(value.get("reason", "")).split())
    clarifying_question = value.get("clarifying_question")
    if not isinstance(sufficient, bool) or not isinstance(needs_clarification, bool) or not reason:
        raise ValueError("assistant_adequacy_invalid")
    if clarifying_question is not None:
        clarifying_question = " ".join(str(clarifying_question).split())
    raw_step = value.get("additional_step")
    step = None
    if raw_step is not None:
        if not isinstance(raw_step, dict):
            raise ValueError("assistant_adequacy_step_invalid")
        tool = str(raw_step.get("tool", ""))
        arguments = _tool_arguments(raw_step)
        step_reason = " ".join(str(raw_step.get("reason", reason)).split())
        if tool not in TOOL_NAMES or not isinstance(arguments, dict) or not step_reason:
            raise ValueError("assistant_adequacy_step_invalid")
        _validate_arguments(tool, arguments)
        step = PlannedToolCall(tool, dict(arguments), step_reason[:500])
    if sufficient and (step is not None or needs_clarification):
        raise ValueError("assistant_adequacy_conflict")
    if needs_clarification and not clarifying_question:
        raise ValueError("assistant_adequacy_clarification_invalid")
    if not sufficient and not needs_clarification and step is None:
        raise ValueError("assistant_adequacy_missing_action")
    return AdequacyDecision(
        sufficient,
        reason[:500],
        step,
        needs_clarification,
        clarifying_question,
    )


def validate_answer(
    answer: SynthesizedAnswer,
    *,
    intent: str,
    tool_names: tuple[str, ...],
    sources: tuple[dict[str, Any], ...],
    question: str | None = None,
) -> dict[str, Any]:
    selected = [item for item in sources if str(item.get("source_id")) in answer.used_source_ids]
    selected_layers = {str(item.get("authority_layer")) for item in selected}
    problems: list[str] = []
    if answer.needs_clarification and answer.used_source_ids:
        problems.append("clarification_has_sources")
    if answer.needs_clarification and "?" not in answer.answer:
        problems.append("clarification_without_question")
    if answer.needs_clarification and re.search(r"\d+\s*%", answer.answer):
        problems.append("clarification_has_unverified_numeric_estimate")
    if answer.answer_type == "insufficient_data" and not (
        "?" in answer.answer
        or re.search(
            r"\b(?:добавьте|предоставьте|укажите|уточните)\b",
            answer.answer,
            re.IGNORECASE,
        )
    ):
        problems.append("insufficient_without_next_question")
    workspace_tools = {
        "consultant.get_workspace_overview",
        "consultant.search_workspace_documents",
        "consultant.get_workspace_fragment",
        "consultant.get_work_packages",
        "consultant.get_requirement_matrix",
        "consultant.get_discrepancies",
        "consultant.get_id_package",
        "consultant.get_mode_result",
        "consultant.get_information_gaps",
    }
    if intent == "workspace" and not workspace_tools.intersection(tool_names):
        problems.append("workspace_answer_without_workspace_tool")
    content_tools = {
        "consultant.search_workspace_documents",
        "consultant.get_workspace_fragment",
    }
    if (
        question is not None
        and requires_workspace_document_content(question)
        and not content_tools.intersection(tool_names)
    ):
        problems.append("workspace_content_question_without_content_retrieval")
    if (
        intent in {"workspace", "mixed"}
        and workspace_tools.intersection(tool_names)
        and re.search(
            r"\b(?:в\s+(?:загруженн\w*|предоставленн\w*|доступн\w*)\s+"
            r"документ\w*\s+(?:нет|отсутствует|не\s+содерж\w*)|"
            r"документ\w*\s+не\s+содерж\w*|отсутствует\s+информац\w*)\b",
            answer.answer,
            re.IGNORECASE,
        )
    ):
        problems.append("workspace_documents_incorrectly_declared_absent")
    exact_normative_claim = re.search(
        r"\b(?:СП|ГОСТ(?:\s+Р)?|СНиП)\s*\d|\bпункт(?:а|ом|у)?\s+\d",
        answer.answer,
        re.IGNORECASE,
    )
    if (
        answer.answer_type not in {"clarification", "insufficient_data"}
        and exact_normative_claim
        and "normative_authority" not in selected_layers
    ):
        problems.append("normative_claim_without_source")
    if len(answer.used_source_ids) != len(selected):
        problems.append("source_selection_inconsistent")
    if len(selected) > 10:
        problems.append("too_many_sources")
    if re.search(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}\b", answer.answer):
        problems.append("internal_contract_token_exposed")
    normalized_words = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", answer.answer.casefold())
    for index in range(len(normalized_words) - 2):
        if normalized_words[index] == normalized_words[index + 2] and normalized_words[
            index + 1
        ] in {"и", "или"}:
            problems.append("repeated_phrase")
            break
    # A repeated ``X и X`` phrase is a presentation defect, not a factual or
    # citation defect.  Keep it visible in the quality receipt, but do not
    # replace an otherwise grounded engineering answer with the generic
    # insufficient-data fallback.  The model quality check still evaluates
    # readability, while all authority, source-selection and non-fabrication
    # failures remain blocking.
    blocking_problems = [item for item in problems if item != "repeated_phrase"]
    citation_ratio = len(selected) / max(1, len(sources))
    return {
        "passed": not blocking_problems,
        "problems": problems,
        "warnings": [item for item in problems if item == "repeated_phrase"],
        "selected_source_count": len(selected),
        "retrieved_source_count": len(sources),
        "source_selection_ratio": round(citation_ratio, 4),
        "answer_type": answer.answer_type,
    }


def parse_model_quality(raw: str) -> dict[str, Any]:
    value = _json_object(raw)
    passed = value.get("passed")
    issues = value.get("issues", [])
    if not isinstance(passed, bool) or not isinstance(issues, list):
        raise ValueError("assistant_model_quality_invalid")
    normalized = [" ".join(str(item).split())[:300] for item in issues if str(item).strip()]
    return {"passed": passed and not normalized, "issues": normalized}


def compact_history(messages: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    kept: list[dict[str, str]] = []
    remaining = MAX_HISTORY_CHARS
    for item in reversed(messages[-MAX_HISTORY_MESSAGES:]):
        content = " ".join(str(item.get("content", "")).split())
        if not content:
            continue
        content = content[: min(1_200, remaining)]
        if not content:
            break
        kept.append({"role": str(item.get("role", "")), "content": content})
        remaining -= len(content)
        if remaining <= 0:
            break
    return tuple(reversed(kept))


def _validate_arguments(tool: str, arguments: dict[str, Any]) -> None:
    if tool in _NO_ARGUMENT_TOOLS:
        if arguments:
            raise ValueError("assistant_plan_unexpected_arguments")
        return
    if tool in {
        "consultant.search_practice",
        "consultant.search_ntd",
        "consultant.search_ntd_documents",
        "consultant.search_ntd_content",
        "consultant.find_applicability_candidates",
        "consultant.search_workspace_documents",
    }:
        allowed_keys = {"query", "limit"}
        if tool == "consultant.search_ntd_content":
            allowed_keys.add("search_document_id")

        if set(arguments) - allowed_keys:
            raise ValueError("assistant_plan_search_arguments_invalid")
        query = " ".join(str(arguments.get("query", "")).split())
        limit = arguments.get("limit", 5)
        if not 2 <= len(query) <= 500 or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("assistant_plan_search_arguments_invalid")
        if "search_document_id" in arguments:
            if not _is_uuid(str(arguments["search_document_id"])):
                raise ValueError("assistant_plan_search_arguments_invalid")
        return
    if tool == "consultant.get_work_packages":
        if set(arguments) - {"query", "limit"}:
            raise ValueError("assistant_plan_work_packages_arguments_invalid")
        query = " ".join(str(arguments.get("query", "")).split())
        limit = arguments.get("limit", 20)
        if query and not 2 <= len(query) <= 500:
            raise ValueError("assistant_plan_work_packages_arguments_invalid")
        if not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("assistant_plan_work_packages_arguments_invalid")
        return
    if tool == "consultant.get_project_entity_inventory":
        if set(arguments) - {"kind", "query", "limit"}:
            raise ValueError("assistant_plan_entity_inventory_arguments_invalid")
        kind = arguments.get("kind")
        if kind is not None and kind not in {
            "local_area",
            "facility",
            "excavation_pit",
            "structure",
            "zone",
        }:
            raise ValueError("assistant_plan_entity_inventory_arguments_invalid")
        query = " ".join(str(arguments.get("query", "")).split())
        if query and not 2 <= len(query) <= 160:
            raise ValueError("assistant_plan_entity_inventory_arguments_invalid")
        limit = arguments.get("limit", 30)
        if not isinstance(limit, int) or not 1 <= limit <= 30:
            raise ValueError("assistant_plan_entity_inventory_arguments_invalid")
        return
    if tool == "consultant.resolve_ntd_designation":
        if set(arguments) != {"designation"}:
            raise ValueError("assistant_plan_designation_arguments_invalid")
        designation = " ".join(str(arguments.get("designation", "")).split())
        if not 2 <= len(designation) <= 160:
            raise ValueError("assistant_plan_designation_arguments_invalid")
        return
    if tool in {"consultant.get_ntd_processing_status"}:
        if set(arguments) != {"search_document_id"} or not _is_uuid(
            str(arguments.get("search_document_id", ""))
        ):
            raise ValueError("assistant_plan_ntd_document_arguments_invalid")
        return
    if tool == "consultant.get_ntd_page":
        if set(arguments) != {"search_document_id", "page_number"} or not _is_uuid(
            str(arguments.get("search_document_id", ""))
        ):
            raise ValueError("assistant_plan_ntd_page_arguments_invalid")
        page = arguments.get("page_number")
        if not isinstance(page, int) or page < 1:
            raise ValueError("assistant_plan_ntd_page_arguments_invalid")
        return
    if tool == "consultant.get_verified_provisions":
        if set(arguments) - {"search_document_id", "query", "limit"} or not _is_uuid(
            str(arguments.get("search_document_id", ""))
        ):
            raise ValueError("assistant_plan_ntd_provisions_arguments_invalid")
        limit = arguments.get("limit", 5)
        query = " ".join(str(arguments.get("query", "")).split())
        if query and len(query) > 500:
            raise ValueError("assistant_plan_ntd_provisions_arguments_invalid")
        if not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("assistant_plan_ntd_provisions_arguments_invalid")
        return
    if tool in {
        "consultant.get_practice_fragment",
        "consultant.get_ntd_provision",
        "consultant.get_workspace_fragment",
    }:
        if set(arguments) != {"source_id"} or not _is_uuid(str(arguments["source_id"])):
            raise ValueError("assistant_plan_identity_arguments_invalid")
        return
    if tool == "consultant.get_ntd_section_context":
        if set(arguments) - {"search_document_id", "page_number", "radius"} or not _is_uuid(
            str(arguments.get("search_document_id", ""))
        ):
            raise ValueError("assistant_plan_section_arguments_invalid")
        page = arguments.get("page_number")
        radius = arguments.get("radius", 1)
        if (
            not isinstance(page, int)
            or page < 1
            or not isinstance(radius, int)
            or not 1 <= radius <= 2
        ):
            raise ValueError("assistant_plan_section_arguments_invalid")
        return
    if tool == "consultant.estimate_concrete_early_strength":
        allowed_keys = {
            "concrete_class",
            "age_days",
            "temperature_c",
            "curing_condition",
        }
        if set(arguments) - allowed_keys:
            raise ValueError("assistant_plan_engineering_arguments_invalid")
        if "concrete_class" not in arguments or "age_days" not in arguments:
            raise ValueError("assistant_plan_engineering_arguments_invalid")
        concrete_class = arguments["concrete_class"]
        age_days = arguments["age_days"]
        if not isinstance(concrete_class, str):
            raise ValueError("assistant_plan_engineering_arguments_invalid")
        if not re.fullmatch(r"B\d+(?:\.\d+)?", concrete_class.strip().upper()):
            raise ValueError("assistant_plan_engineering_arguments_invalid")
        if isinstance(age_days, bool) or not isinstance(age_days, int) or age_days < 1:
            raise ValueError("assistant_plan_engineering_arguments_invalid")
        if "temperature_c" in arguments:
            temp = arguments["temperature_c"]
            if isinstance(temp, bool) or not isinstance(temp, (int, float)):
                raise ValueError("assistant_plan_engineering_arguments_invalid")
        if "curing_condition" in arguments:
            curing = arguments["curing_condition"]
            if not isinstance(curing, str) or not curing.strip():
                raise ValueError("assistant_plan_engineering_arguments_invalid")
        return
    raise ValueError("assistant_plan_tool_invalid")


def _tool_arguments(raw_step: dict[str, Any]) -> Any:
    keys = [key for key in ("arguments", "parameters", "params", "args") if key in raw_step]
    if len(keys) > 1:
        raise ValueError("assistant_plan_duplicate_arguments")
    return raw_step.get(keys[0], {}) if keys else {}


def _json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start : end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("assistant_json_object_required")
    return value


def _is_uuid(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            value,
        )
    )
