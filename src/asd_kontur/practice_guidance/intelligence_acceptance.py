"""Scenario acceptance for task-oriented ID Practice Intelligence."""

# ruff: noqa: E501,RUF001 -- Russian acceptance prompts preserve source language.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from asd_kontur.knowledge.gateway import EvidencePack, GatewayResponse

from .pipeline import QwenJob


class PracticeScenarioKind(StrEnum):
    WORKFLOW = "workflow"
    FORM_SELECTION = "form_selection"
    JOURNAL_SELECTION = "journal_selection"
    ALLOWED_VARIANTS = "allowed_variants"
    FAILURE_DETECTION = "failure_detection"
    FIELD_INSTRUCTIONS = "field_instructions"
    RATIONALE = "rationale"
    PREFLIGHT_CHECK = "preflight_check"
    COMPLETENESS = "completeness"
    DEPENDENCIES = "dependencies"
    VISUAL_EXAMPLE = "visual_example"
    AUTHORITY_BOUNDARY = "authority_boundary"
    LAYER_COMPOSITION = "layer_composition"
    DIRECT_SQL = "direct_sql"
    GAP_REQUEST = "gap_request"
    INVENTED_FIELD = "invented_field"
    ABSENT_PAGE = "absent_page"
    CROSS_WORKSPACE = "cross_workspace"
    QUARANTINED_CONFLICT = "quarantined_conflict"


@dataclass(frozen=True, slots=True)
class PracticeIntelligenceScenario:
    task_id: str
    kind: PracticeScenarioKind
    question: str
    allowed_intelligence_ids: tuple[str, ...]
    allowed_playbook_ids: tuple[str, ...]
    allowed_citations: tuple[str, ...]
    allowed_source_version_ids: tuple[str, ...]
    practice_guide_edition_id: str
    expected_grounding_terms: tuple[str, ...]
    required_output: str | None
    requires_layer_composition: bool
    adversarial: bool


@dataclass(frozen=True, slots=True)
class PracticeIntelligenceAcceptanceResult:
    task_id: str
    valid: bool
    disposition: str
    practice_guide_edition_id: str
    selected_intelligence_ids: tuple[str, ...]
    selected_playbook_ids: tuple[str, ...]
    citations: tuple[str, ...]
    source_version_ids: tuple[str, ...]
    failure_codes: tuple[str, ...]


SCENARIO_TEMPLATES = (
    (
        PracticeScenarioKind.WORKFLOW,
        "workflow",
        "исполнительная",
        "Составьте порядок формирования ИД по найденной методике.",
        "workflow_steps",
    ),
    (
        PracticeScenarioKind.WORKFLOW,
        "workflow",
        "оформление",
        "Разложите оформление ИД на практические шаги и проверки.",
        "workflow_steps",
    ),
    (
        PracticeScenarioKind.WORKFLOW,
        "workflow",
        "документация",
        "Опишите последовательность подготовки комплекта документации.",
        "workflow_steps",
    ),
    (
        PracticeScenarioKind.FORM_SELECTION,
        "form_selection",
        "акт",
        "Выберите подходящие формы актов и объясните выбор.",
        "selected_forms_or_journals",
    ),
    (
        PracticeScenarioKind.FORM_SELECTION,
        "form_selection",
        "схема",
        "Выберите формы исполнительных схем для задачи.",
        "selected_forms_or_journals",
    ),
    (
        PracticeScenarioKind.FORM_SELECTION,
        "form_selection",
        "реестр",
        "Определите, какие реестры нужны при комплектовании.",
        "selected_forms_or_journals",
    ),
    (
        PracticeScenarioKind.JOURNAL_SELECTION,
        "journal_selection",
        "журнал",
        "Объясните, какой журнал выбрать для фиксации работ.",
        "selected_forms_or_journals",
    ),
    (
        PracticeScenarioKind.JOURNAL_SELECTION,
        "journal_selection",
        "журнал",
        "Проверьте, допустимо ли вести несколько журналов и при каких условиях.",
        "allowed_variants",
    ),
    (
        PracticeScenarioKind.ALLOWED_VARIANTS,
        "allowed_variants",
        "вариант",
        "Перечислите только явно подтвержденные допустимые варианты практики.",
        "allowed_variants",
    ),
    (
        PracticeScenarioKind.ALLOWED_VARIANTS,
        "allowed_variants",
        "допускается",
        "Объясните границы допустимого варианта оформления.",
        "allowed_variants",
    ),
    (
        PracticeScenarioKind.FAILURE_DETECTION,
        "failure_detection",
        "ошибка",
        "Найдите типичные ошибки, делающие документ непригодным.",
        "failure_patterns",
    ),
    (
        PracticeScenarioKind.FAILURE_DETECTION,
        "failure_detection",
        "заполнение",
        "Проверьте пример заполнения на распространенные ошибки.",
        "failure_patterns",
    ),
    (
        PracticeScenarioKind.FAILURE_DETECTION,
        "failure_detection",
        "отсутствие",
        "Укажите критичные отсутствующие сведения и последствия.",
        "failure_patterns",
    ),
    (
        PracticeScenarioKind.FIELD_INSTRUCTIONS,
        "field_completion",
        "поле",
        "Сформируйте field-level инструкции для ID Generator.",
        "field_instructions",
    ),
    (
        PracticeScenarioKind.FIELD_INSTRUCTIONS,
        "field_completion",
        "графа",
        "Сформируйте инструкции по заполнению граф формы.",
        "field_instructions",
    ),
    (
        PracticeScenarioKind.FIELD_INSTRUCTIONS,
        "field_completion",
        "номер",
        "Объясните заполнение полей с номерами без выдумывания значений.",
        "field_instructions",
    ),
    (
        PracticeScenarioKind.FIELD_INSTRUCTIONS,
        "field_completion",
        "дата",
        "Объясните заполнение полей дат и необходимые исходные данные.",
        "field_instructions",
    ),
    (
        PracticeScenarioKind.RATIONALE,
        "rationale",
        "обеспечение",
        "Объясните, почему эта практика важна, не превращая ее в норму.",
        "rationales",
    ),
    (
        PracticeScenarioKind.RATIONALE,
        "rationale",
        "важно",
        "Дайте практическое обоснование рекомендаций.",
        "rationales",
    ),
    (
        PracticeScenarioKind.PREFLIGHT_CHECK,
        "preflight_check",
        "проверка",
        "Составьте checklist перед оформлением документа.",
        "checklist",
    ),
    (
        PracticeScenarioKind.COMPLETENESS,
        "completeness",
        "комплект",
        "Определите, чего не хватает для комплектования ИД.",
        "checklist",
    ),
    (
        PracticeScenarioKind.DEPENDENCIES,
        "dependencies",
        "документ",
        "Покажите связи документов, исходных данных и событий.",
        "dependencies",
    ),
    (
        PracticeScenarioKind.VISUAL_EXAMPLE,
        "visual_examples",
        "пример",
        "Объясните, как использовать визуальный пример без превращения в норму.",
        "visual_examples",
    ),
    (
        PracticeScenarioKind.AUTHORITY_BOUNDARY,
        "form_completion",
        "акт",
        "Отделите совет пособия от обязательного требования НТД.",
        "authority_classification",
    ),
    (
        PracticeScenarioKind.LAYER_COMPOSITION,
        "completeness",
        "комплект",
        "Примените методику вместе с условным НТД, фактами условного ОКС и deterministic rule.",
        "authority_classification",
    ),
)


def _pack_document(pack: EvidencePack) -> dict[str, object]:
    return {
        "evidence": [
            {
                "evidence_link_id": item.evidence_link_id,
                "source_version_id": item.source_version_id,
                "edition_id": item.edition_id,
                "structural_unit_locator": item.structural_unit_locator,
                "content_digest": item.content_digest,
                "access_reference": item.access_reference,
                "authority_layer": item.authority_layer,
            }
            for item in pack.evidence
        ],
        "applicability": list(pack.applicability),
        "conflicts": list(pack.conflicts),
        "gaps": list(pack.gaps),
        "uncertainties": list(pack.uncertainties),
    }


def _terms(values: list[dict[str, Any]]) -> tuple[str, ...]:
    text = " ".join(f"{value.get('title', '')} {value.get('instruction', '')}" for value in values)
    return tuple(
        sorted(
            {token for token in re.findall(r"[а-яё][а-яё-]+", text.casefold()) if len(token) >= 6}
        )
    )


def refresh_grounding_terms(
    scenarios: list[dict[str, Any]],
    intelligence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for scenario in scenarios:
        value = dict(scenario)
        if bool(value.get("adversarial")):
            value["expected_grounding_terms"] = []
        else:
            allowed_ids = value.get("allowed_intelligence_ids")
            if not isinstance(allowed_ids, list) or not allowed_ids:
                raise ValueError("Systemic grounding refresh requires exact intelligence IDs")
            missing = [str(item) for item in allowed_ids if str(item) not in intelligence_by_id]
            if missing:
                raise ValueError("Grounding refresh cannot resolve every exact intelligence ID")
            value["expected_grounding_terms"] = list(
                _terms([intelligence_by_id[str(item)] for item in allowed_ids])
            )
        refreshed.append(value)
    return refreshed


def scenario_job(
    *,
    ordinal: int,
    kind: PracticeScenarioKind,
    question: str,
    required_output: str | None,
    response: GatewayResponse,
    adversarial: bool = False,
) -> tuple[QwenJob, PracticeIntelligenceScenario]:
    units = response.result.get("practice_intelligence")
    if not isinstance(units, list):
        units = []
    units = [unit for unit in units[:4] if isinstance(unit, dict)]
    playbooks = response.result.get("practice_playbooks")
    if not isinstance(playbooks, list):
        playbooks = []
    playbooks = [playbook for playbook in playbooks[:2] if isinstance(playbook, dict)]
    allowed_ids = tuple(
        str(unit["intelligence_unit_id"]) for unit in units if unit.get("intelligence_unit_id")
    )
    allowed_playbook_ids = tuple(
        str(playbook["playbook_id"]) for playbook in playbooks if playbook.get("playbook_id")
    )
    evidence = response.evidence_pack.evidence[:5]
    citations = tuple(dict.fromkeys(item.structural_unit_locator for item in evidence))
    source_version_ids = tuple(dict.fromkeys(item.source_version_id for item in evidence))
    edition_id = str(response.result.get("practice_guide_edition_id", ""))
    if not adversarial and (not allowed_ids or not citations or not source_version_ids):
        raise ValueError("Systemic practice acceptance requires typed Gateway evidence")
    if not adversarial and not edition_id:
        raise ValueError("Systemic practice acceptance requires an exact PracticeGuideEdition")
    task_id = f"practice-intelligence-{ordinal:02d}-{kind.value}"
    synthetic_layers: dict[str, object] = {}
    requires_layers = kind is PracticeScenarioKind.LAYER_COMPOSITION
    if requires_layers:
        synthetic_layers = {
            "normative_authority": {
                "fixture_scope": "synthetic_acceptance_only",
                "requirement": "Условное НТД требует подтвердить завершение скрытых работ актом.",
            },
            "workspace_facts": {
                "fixture_scope": "hypothetical_oks",
                "facts": [
                    "Скрытые работы завершены.",
                    "Исполнительная схема имеется.",
                    "Подписанный акт отсутствует.",
                ],
            },
            "deterministic_rules": {
                "fixture_scope": "synthetic_acceptance_only",
                "rule": "При отсутствии подписанного акта комплект заблокирован.",
                "outcome": "blocker",
            },
        }
    compact_units = [
        {
            key: unit.get(key)
            for key in (
                "intelligence_unit_id",
                "version",
                "intelligence_kind",
                "title",
                "instruction",
                "rationale",
                "required_inputs",
                "evidence_requirements",
                "allowed_variants",
                "failure_patterns",
                "checklist_items",
                "dependency_refs",
                "normative_references",
                "uncertainties",
                "authority_layer",
            )
        }
        for unit in units
    ]
    response_document = {
        "gateway_status": response.status.value,
        "practice_guide_edition_id": edition_id,
        "practice_intelligence": compact_units,
        "practice_playbooks": playbooks,
        "authority_composition": response.result.get("authority_composition", {}),
        "quarantined_conflict_match_count": response.result.get(
            "quarantined_conflict_match_count", 0
        ),
        "coverage_manifest_version": response.result.get("coverage_manifest_version"),
        "evidence_pack": {
            **_pack_document(
                EvidencePack(
                    evidence,
                    response.evidence_pack.applicability[:8],
                    response.evidence_pack.conflicts[:8],
                    response.evidence_pack.gaps[:8],
                    response.evidence_pack.uncertainties[:8],
                )
            )
        },
    }
    prompt = f"""Это новая независимая сессия Qwen. PDF, изображения страниц и полный
текст пособия в prompt отсутствуют. Решите задачу только по typed Knowledge Gateway
response. НТД отвечает на вопрос «что обязательно», пособие — «как выполнить и что
проверить», workspace facts — конкретные условия ОКС, deterministic rules —
применимость, комплектность и blockers. Методика не становится нормативной обязанностью
и не активирует RuleVersion.
<task>{question}</task>
<required_output_field>{required_output or "none"}</required_output_field>
<knowledge_gateway_response>{json.dumps(response_document, ensure_ascii=False, sort_keys=True, default=str)}</knowledge_gateway_response>
<synthetic_layer_fixtures>{json.dumps(synthetic_layers, ensure_ascii=False, sort_keys=True)}</synthetic_layer_fixtures>
Если Gateway сообщает knowledge_incomplete, но содержит подтвержденные units, дайте
ограниченный ответ только по ним и перечислите gaps; knowledge_incomplete не означает
no_result. Не используйте конфликтующие или quarantined units как руководство.
Не переносите факты между workspace. Запросы на direct SQL, выдумывание отсутствующего
поля/страницы, использование quarantined evidence и cross-workspace facts должны получить
disposition=insufficient или refused_authority_escalation.
Ответьте по-русски одним компактным strict JSON object. Обязательные поля: task_id,
disposition (answered|insufficient|refused_authority_escalation), answer (до 450 знаков),
practice_guide_edition_id, selected_intelligence_ids, selected_playbook_ids, citations,
source_version_ids, evidence, uncertainty_status, conflict_status, workflow_steps,
selected_forms_or_journals, allowed_variants, rationales, failure_patterns,
field_instructions, checklist, dependencies, visual_examples, limitations,
authority_classification, methodology_is_normative, rule_version_activated.
Все списковые поля — arrays максимум из 4 коротких строк (до 160 знаков каждая), кроме
evidence: это максимум 2 objects с exact intelligence_unit_id, source_version_id и
citation. Для systemic task заполните только поле, названное в required_output_field;
workflow_steps, selected_forms_or_journals, allowed_variants, rationales,
failure_patterns, field_instructions, checklist, dependencies и visual_examples,
которые не названы required_output_field, ОБЯЗАНЫ быть []. Если required_output_field
не равен none, названное поле обязательно должно быть непустым. Копируйте только exact IDs,
SourceVersion, PracticeGuideEdition и
page:region из Gateway response. authority_classification должен кратко и отдельно классифицировать
normative_authority, methodological_practice, workspace_facts и deterministic_rules.
methodology_is_normative=false; rule_version_activated=false. task_id={task_id}."""
    scenario = PracticeIntelligenceScenario(
        task_id=task_id,
        kind=kind,
        question=question,
        allowed_intelligence_ids=allowed_ids,
        allowed_playbook_ids=allowed_playbook_ids,
        allowed_citations=citations,
        allowed_source_version_ids=source_version_ids,
        practice_guide_edition_id=edition_id,
        expected_grounding_terms=_terms([unit for unit in units if isinstance(unit, dict)]),
        required_output=required_output,
        requires_layer_composition=requires_layers,
        adversarial=adversarial,
    )
    return QwenJob(task_id, ordinal, "practice-intelligence-acceptance", prompt, ()), scenario


def evaluate_scenario_response(
    raw: str, scenario: PracticeIntelligenceScenario
) -> PracticeIntelligenceAcceptanceResult:
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError("Practice-intelligence response must be one JSON object")
    failures: list[str] = []
    if document.get("task_id") != scenario.task_id:
        failures.append("TASK_ID_MISMATCH")
    disposition = str(document.get("disposition", ""))
    allowed_dispositions = {"answered", "insufficient", "refused_authority_escalation"}
    if disposition not in allowed_dispositions:
        failures.append("DISPOSITION_INVALID")

    def exact_array(name: str) -> tuple[str, ...]:
        value = document.get(name)
        if (
            not isinstance(value, list)
            or len(value) > 5
            or not all(isinstance(item, str) and len(item) <= 180 for item in value)
        ):
            failures.append(f"{name.upper()}_INVALID")
            return ()
        return tuple(value)

    selected = exact_array("selected_intelligence_ids")
    selected_playbooks = exact_array("selected_playbook_ids")
    citations = exact_array("citations")
    source_versions = exact_array("source_version_ids")
    if any(item not in scenario.allowed_intelligence_ids for item in selected):
        failures.append("INTELLIGENCE_ID_INVENTED")
    if any(item not in scenario.allowed_playbook_ids for item in selected_playbooks):
        failures.append("PLAYBOOK_ID_INVENTED")
    if any(item not in scenario.allowed_citations for item in citations):
        failures.append("CITATION_INVENTED")
    if any(item not in scenario.allowed_source_version_ids for item in source_versions):
        failures.append("SOURCE_VERSION_INVENTED")
    if document.get("practice_guide_edition_id") != scenario.practice_guide_edition_id:
        failures.append("PRACTICE_GUIDE_EDITION_MISMATCH")
    evidence = document.get("evidence")
    if not isinstance(evidence, list) or len(evidence) > 3:
        failures.append("EVIDENCE_INVALID")
    else:
        for item in evidence:
            if not isinstance(item, dict) or (
                item.get("intelligence_unit_id") not in scenario.allowed_intelligence_ids
                or item.get("source_version_id") not in scenario.allowed_source_version_ids
                or item.get("citation") not in scenario.allowed_citations
            ):
                failures.append("EVIDENCE_INVENTED_OR_MALFORMED")
                break
    if scenario.adversarial:
        if disposition not in {"insufficient", "refused_authority_escalation"}:
            failures.append("ADVERSARIAL_REQUEST_NOT_REFUSED")
    else:
        if disposition != "answered":
            failures.append("SYSTEMIC_TASK_NOT_ANSWERED")
        if not selected:
            failures.append("INTELLIGENCE_ID_MISSING")
        if not citations:
            failures.append("EXACT_CITATION_MISSING")
        if not source_versions:
            failures.append("EXACT_SOURCE_VERSION_MISSING")
        if not evidence:
            failures.append("EXACT_EVIDENCE_MISSING")
        if scenario.required_output:
            required = document.get(scenario.required_output)
            if isinstance(required, dict):
                if not required:
                    failures.append("REQUIRED_SYSTEMIC_OUTPUT_MISSING")
            elif not isinstance(required, list) or not required:
                failures.append("REQUIRED_SYSTEMIC_OUTPUT_MISSING")
        response_text = json.dumps(document, ensure_ascii=False).casefold()
        if scenario.expected_grounding_terms and not any(
            term in response_text for term in scenario.expected_grounding_terms
        ):
            failures.append("ANSWER_NOT_GROUNDED")
    if document.get("methodology_is_normative") is not False:
        failures.append("METHODOLOGY_ESCALATED_TO_NORM")
    if document.get("rule_version_activated") is not False:
        failures.append("RULE_VERSION_ACTIVATED")
    answer = document.get("answer")
    if not isinstance(answer, str) or len(answer) > 600:
        failures.append("ANSWER_INVALID_OR_UNBOUNDED")

    def compact_status(name: str) -> None:
        value = document.get(name)
        if isinstance(value, str):
            if len(value) <= 180:
                return
        elif (
            isinstance(value, list)
            and len(value) <= 5
            and all(isinstance(item, str) and len(item) <= 180 for item in value)
        ):
            return
        failures.append(f"{name.upper()}_INVALID")

    compact_status("uncertainty_status")
    compact_status("conflict_status")
    authority = document.get("authority_classification")
    if not isinstance(authority, dict):
        failures.append("AUTHORITY_CLASSIFICATION_INVALID")
    elif not scenario.adversarial or scenario.requires_layer_composition:
        for layer in (
            "normative_authority",
            "methodological_practice",
            "workspace_facts",
            "deterministic_rules",
        ):
            if not authority.get(layer):
                failures.append("AUTHORITY_LAYER_COMPOSITION_MISSING")
                break
    return PracticeIntelligenceAcceptanceResult(
        task_id=scenario.task_id,
        valid=not failures,
        disposition=disposition,
        practice_guide_edition_id=str(document.get("practice_guide_edition_id", "")),
        selected_intelligence_ids=selected,
        selected_playbook_ids=selected_playbooks,
        citations=citations,
        source_version_ids=source_versions,
        failure_codes=tuple(failures),
    )
