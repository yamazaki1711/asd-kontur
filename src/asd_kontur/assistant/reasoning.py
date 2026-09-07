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
        "description": "Получить виды работ, пакеты, связанные МТР и объёмы текущего объекта.",
        "schema": {},
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
        "consultant.get_work_packages",
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
    normalized_words = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", answer.answer.casefold())
    for index in range(len(normalized_words) - 2):
        if normalized_words[index] == normalized_words[index + 2] and normalized_words[
            index + 1
        ] in {"и", "или"}:
            problems.append("repeated_phrase")
            break
    citation_ratio = len(selected) / max(1, len(sources))
    return {
        "passed": not problems,
        "problems": problems,
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
