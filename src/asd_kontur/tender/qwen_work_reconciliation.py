"""Bounded local-Qwen interpretation of unresolved construction work descriptions."""

# ruff: noqa: E501, RUF001 -- bounded Russian JSON prompts are intentionally literal.

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

from .analysis_harness import TenderAnalysisTask, TenderHarnessTaskInput, bounded_task_payload
from .quantity_semantics import QuantityRelation, QuantityType, ScopeCompatibility

PROJECT_WORK_RECONCILIATION_PROFILE = "qwen-project-work-reconciliation-v24"
PROJECT_WORK_RECONCILIATION_COMPATIBLE_PROFILES = (
    "qwen-project-work-reconciliation-v3",
    "qwen-project-work-reconciliation-v4",
    "qwen-project-work-reconciliation-v5",
    "qwen-project-work-reconciliation-v6",
    "qwen-project-work-reconciliation-v7",
    "qwen-project-work-reconciliation-v8",
    "qwen-project-work-reconciliation-v9",
    "qwen-project-work-reconciliation-v10",
    "qwen-project-work-reconciliation-v11",
    "qwen-project-work-reconciliation-v12",
    "qwen-project-work-reconciliation-v13",
    "qwen-project-work-reconciliation-v14",
    "qwen-project-work-reconciliation-v15",
    "qwen-project-work-reconciliation-v16",
    "qwen-project-work-reconciliation-v17",
    "qwen-project-work-reconciliation-v18",
    "qwen-project-work-reconciliation-v19",
    "qwen-project-work-reconciliation-v20",
    "qwen-project-work-reconciliation-v21",
    "qwen-project-work-reconciliation-v22",
    "qwen-project-work-reconciliation-v23",
    PROJECT_WORK_RECONCILIATION_PROFILE,
)
WORK_RECONCILIATION_CONTRACT = "project-work-reconciliation-result@17.0.0"
_STATUSES = frozenset({"MATCHED", "AMBIGUOUS", "UNCLASSIFIED", "NOT_A_WORK"})
_QUANTITY_STATUSES = frozenset(
    {
        "WORK_QUANTITY",
        "DIMENSION",
        "DURATION",
        "RESOURCE_OR_RATE",
        "UNRELATED",
        "AMBIGUOUS",
    }
)
_MATERIAL_PROPERTY_KINDS = frozenset(
    {"GRADE", "CLASS", "PROFILE", "THICKNESS", "DIAMETER", "TYPE", "OTHER"}
)
_POTENTIAL_WORK_AT_START = re.compile(
    r"^(?:перевоз\w*|транспортирован\w*|погруз\w*|разгруз\w*|испытан\w*|"
    r"монтаж\w*|демонтаж\w*|установ\w*|устройств\w*|проклад\w*|"
    r"[\w-]*монтажн\w*\s+работ\w*|геодез\w*|пусконалад\w*)\b",
    re.IGNORECASE,
)
_WEAK_FACILITY_REASON = re.compile(
    r"(?:близост|в том же (?:абзац|контекст)|контекст.*упомина|косвен|предполож|вероятн)",
    re.IGNORECASE,
)
_RECOVERABLE_RESPONSE_FAILURES = frozenset(
    {
        "qwen_work_reconciliation_invalid_json",
        "qwen_work_reconciliation_invalid_shape",
        "qwen_work_reconciliation_incomplete_output",
        "qwen_work_reconciliation_identity_invalid",
        "qwen_work_reconciliation_observation_invalid",
        "qwen_work_reconciliation_family_invalid",
        "qwen_work_reconciliation_unresolved_family_invalid",
        "qwen_work_reconciliation_confidence_invalid",
        "qwen_work_reconciliation_facility_invalid",
        "qwen_work_reconciliation_potential_work_excluded",
        "qwen_work_reconciliation_quantity_output_unexpected",
        "qwen_work_reconciliation_quantity_output_incomplete",
        "qwen_work_reconciliation_quantity_output_invalid",
        "qwen_work_reconciliation_component_completeness_invalid",
        "qwen_work_reconciliation_material_output_invalid",
        "qwen_semantic_response_incomplete",
        "qwen_semantic_response_output_exhausted",
    }
)


class QwenProjectWorkReconciler:
    """Interpret only bounded unresolved rows; deterministic code owns validation."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_work_reconciliation_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def reconcile(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        work_families: Mapping[str, str],
        facilities: Iterable[str],
    ) -> dict[str, Any]:
        input_rows = [dict(row) for row in rows]
        if not 1 <= len(input_rows) <= 16:
            raise QwenSemanticFailure("qwen_work_reconciliation_batch_size_invalid")
        input_ids = [str(row.get("candidate_id") or "") for row in input_rows]
        if any(not value for value in input_ids) or len(set(input_ids)) != len(input_ids):
            raise QwenSemanticFailure("qwen_work_reconciliation_input_identity_invalid")
        allowed_facilities = tuple(dict.fromkeys(str(value) for value in facilities if value))
        relationship_review = all(
            str(row.get("analysis_task") or "")
            == TenderAnalysisTask.QUANTITY_RELATIONSHIP_ANALYSIS.value
            for row in input_rows
        )
        observations, call_count, recovery_codes = self._reconcile_rows(
            input_rows,
            work_families=work_families,
            facilities=allowed_facilities,
            relationship_review=relationship_review,
        )
        manifest = {
            "contract": WORK_RECONCILIATION_CONTRACT,
            "profile_version": PROJECT_WORK_RECONCILIATION_PROFILE,
            "observations": observations,
            "inference_call_count": call_count,
            "recovery_codes": recovery_codes,
        }
        manifest["result_digest"] = semantic_digest(manifest)
        return manifest

    def _reconcile_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        work_families: Mapping[str, str],
        facilities: tuple[str, ...],
        relationship_review: bool,
        single_retry_available: bool = True,
        relationship_context_complete: bool = True,
        expanded_relationship_budget: bool = False,
        relationship_schema_retry_available: bool = True,
        relationship_repair_code: str | None = None,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        input_ids = tuple(str(row["candidate_id"]) for row in rows)
        quantity_ids_by_work = {
            str(row["candidate_id"]): tuple(
                str(value.get("quantity_candidate_id") or "")
                for value in row.get("quantity_observations") or ()
                if isinstance(value, Mapping)
            )
            for row in rows
        }
        quantity_context_by_id = {
            str(value.get("quantity_candidate_id") or ""): " ".join(
                str(item or "")
                for item in (
                    value.get("unit"),
                    value.get("nearby_context"),
                )
            )
            for row in rows
            for value in row.get("quantity_observations") or ()
            if isinstance(value, Mapping) and value.get("quantity_candidate_id")
        }
        try:
            quantity_count = sum(len(row.get("quantity_observations") or ()) for row in rows)
            output_budget = (
                5_000
                if relationship_review and expanded_relationship_budget
                else max(1_600, min(5_000, len(rows) * 360 + quantity_count * 180))
                if relationship_review
                else max(1_400, min(4_000, len(rows) * 320 + quantity_count * 140))
            )
            raw = _complete(
                self._endpoint,
                _prompt(
                    rows,
                    work_families,
                    facilities,
                    relationship_review=relationship_review,
                    relationship_repair_code=relationship_repair_code,
                ),
                self._timeout_seconds,
                # Representative twelve-row construction batches repeatedly
                # exhausted the old 170-token-per-row allowance even when every
                # observation was valid. Budget the complete required JSON shape while
                # retaining a bounded task-specific ceiling and recursive split
                # recovery for genuinely verbose or malformed output.
                max_tokens=output_budget,
            )
            return (
                _parse(
                    raw,
                    input_ids=input_ids,
                    wording_by_id={
                        str(row["candidate_id"]): str(row.get("wording") or "").casefold()
                        for row in rows
                    },
                    quantity_ids_by_work=quantity_ids_by_work,
                    quantity_context_by_id=quantity_context_by_id,
                    work_families=work_families,
                    facilities=facilities,
                    relationship_review=relationship_review,
                    mark_relationship_reviewed=(
                        relationship_review and relationship_context_complete
                    ),
                ),
                1,
                [],
            )
        except QwenSemanticFailure as exc:
            if exc.code not in _RECOVERABLE_RESPONSE_FAILURES:
                raise
            # A relationship review loses its cross-row authority when recursive
            # recovery splits the batch.  Real project observations showed that a
            # valid three/four-row relationship response can exhaust the compact
            # first-pass budget.  Retry that exact bounded context once with the
            # established ceiling before falling back to the safe, uncertified
            # split path.
            if (
                relationship_review
                and relationship_context_complete
                and not expanded_relationship_budget
                and exc.code == "qwen_semantic_response_output_exhausted"
            ):
                observations, call_count, codes = self._reconcile_rows(
                    rows,
                    work_families=work_families,
                    facilities=facilities,
                    relationship_review=relationship_review,
                    single_retry_available=single_retry_available,
                    relationship_context_complete=True,
                    expanded_relationship_budget=True,
                    relationship_schema_retry_available=relationship_schema_retry_available,
                )
                return observations, call_count + 1, [exc.code, *codes]
            if (
                relationship_review
                and relationship_context_complete
                and relationship_schema_retry_available
                and exc.code
                in {
                    "qwen_work_reconciliation_component_completeness_invalid",
                    "qwen_work_reconciliation_quantity_output_incomplete",
                    "qwen_work_reconciliation_quantity_output_invalid",
                }
            ):
                observations, call_count, codes = self._reconcile_rows(
                    rows,
                    work_families=work_families,
                    facilities=facilities,
                    relationship_review=relationship_review,
                    single_retry_available=single_retry_available,
                    relationship_context_complete=True,
                    expanded_relationship_budget=True,
                    relationship_schema_retry_available=False,
                    relationship_repair_code=exc.code,
                )
                return observations, call_count + 1, [exc.code, *codes]
            if len(rows) == 1:
                if not single_retry_available:
                    return (
                        [_unresolved_observation(rows[0], failure_code=exc.code)],
                        1,
                        [exc.code, "qwen_work_reconciliation_observation_unresolved"],
                    )
                observations, call_count, codes = self._reconcile_rows(
                    rows,
                    work_families=work_families,
                    facilities=facilities,
                    relationship_review=relationship_review,
                    single_retry_available=False,
                    relationship_context_complete=relationship_context_complete,
                )
                return observations, call_count + 1, [exc.code, *codes]
            midpoint = len(rows) // 2
            left, left_calls, left_codes = self._reconcile_rows(
                rows[:midpoint],
                work_families=work_families,
                facilities=facilities,
                relationship_review=relationship_review,
                relationship_context_complete=False,
            )
            right, right_calls, right_codes = self._reconcile_rows(
                rows[midpoint:],
                work_families=work_families,
                facilities=facilities,
                relationship_review=relationship_review,
                relationship_context_complete=False,
            )
            return (
                [*left, *right],
                1 + left_calls + right_calls,
                [exc.code, *left_codes, *right_codes],
            )


def _unresolved_observation(row: Mapping[str, Any], *, failure_code: str) -> dict[str, Any]:
    """Preserve one rejected interpretation without losing valid sibling rows."""

    observation: dict[str, Any] = {
        "candidate_id": str(row["candidate_id"]),
        "status": "UNCLASSIFIED",
        "family_key": None,
        "operation": None,
        "facility": None,
        "confidence": "0",
        "reason": (
            "Интерпретация не принята после ограниченного повтора; описание сохранено "
            f"для последующего уточнения ({failure_code})."
        ),
    }
    quantity_reviews = [
        {
            "quantity_candidate_id": str(value.get("quantity_candidate_id") or ""),
            "status": "AMBIGUOUS",
            "semantic_scope": "Не установлено после ограниченного повтора",
            "quantity_type": QuantityType.UNKNOWN,
            "relation_kind": QuantityRelation.NONE,
            "related_quantity_candidate_ids": [],
            "scope_compatibility": ScopeCompatibility.INSUFFICIENT_INFORMATION,
            "reason": (
                "Значение сохранено без назначения: интерпретация связанной работы "
                "не прошла проверку."
            ),
        }
        for value in row.get("quantity_observations") or ()
        if isinstance(value, Mapping) and value.get("quantity_candidate_id")
    ]
    if quantity_reviews:
        observation["quantity_reviews"] = quantity_reviews
    return observation


def _prompt(
    rows: list[dict[str, Any]],
    work_families: Mapping[str, str],
    facilities: tuple[str, ...],
    *,
    relationship_review: bool,
    relationship_repair_code: str | None = None,
) -> str:
    all_quantity_candidate_ids = [
        str(value.get("quantity_candidate_id") or "")
        for row in rows
        for value in row.get("quantity_observations") or ()
        if isinstance(value, Mapping) and value.get("quantity_candidate_id")
    ]
    safe_rows = [
        {
            "candidate_id": str(row["candidate_id"]),
            "wording": str(row.get("wording") or ""),
            "document_role": str(row.get("document_role") or "не определена"),
            "document": str(row.get("document") or "")[:180],
            "page": row.get("page"),
            "scope": str(row.get("scope") or "")[:240],
            "facility_hints": list(row.get("facility_hints") or ())[:6],
            "deterministic_family_hint": row.get("deterministic_family_hint"),
            "nearby_context": str(row.get("nearby_context") or ""),
            "nearby_context_locator_ids": list(row.get("nearby_context_locator_ids") or ()),
            "available_quantity_candidate_ids": [
                str(value.get("quantity_candidate_id") or "")
                for value in row.get("quantity_observations") or ()
                if isinstance(value, Mapping) and value.get("quantity_candidate_id")
            ],
            "quantity_observations": [
                {
                    "quantity_candidate_id": str(value.get("quantity_candidate_id") or ""),
                    "value": value.get("value"),
                    "unit": value.get("unit"),
                    "source_locator_id": value.get("source_locator_id"),
                    "nearby_context": str(value.get("nearby_context") or ""),
                    "prior_semantic_scope": value.get("prior_semantic_scope"),
                    "prior_quantity_type": value.get("prior_quantity_type"),
                    "prior_status": value.get("prior_status"),
                    "peer_quantity_candidate_ids": [
                        candidate_id
                        for candidate_id in all_quantity_candidate_ids
                        if candidate_id != str(value.get("quantity_candidate_id") or "")
                    ],
                }
                for value in row.get("quantity_observations") or ()
                if isinstance(value, Mapping)
            ],
        }
        for row in rows
    ]
    task_payload = bounded_task_payload(
        TenderHarnessTaskInput(
            task=(
                TenderAnalysisTask.QUANTITY_RELATIONSHIP_ANALYSIS
                if relationship_review
                else TenderAnalysisTask.WORK_CLASSIFICATION
            ),
            input_identity=semantic_digest(safe_rows),
            context={
                "work_families": dict(work_families),
                "facilities": facilities,
                "rows": safe_rows,
                "all_quantity_candidate_ids": all_quantity_candidate_ids,
            },
        ),
        max_chars=50_000,
    )
    relationship_instruction = (
        "Это отдельный проход смысловых связей числовых значений. Классификацию работы "
        "сохраните по переданным подсказкам; определите, какие значения описывают один "
        "инженерный объём, общий итог, составляющую, дубль, альтернативу или другую редакцию. "
        "Для каждого числа обязательно повторно установите semantic_scope по исходному контексту."
        if relationship_review
        else ""
    )
    relationship_repair_instruction = ""
    if relationship_repair_code:
        relationship_repair_instruction = (
            "Предыдущий ответ для ТОГО ЖЕ полного пакета отклонён валидатором схемы с кодом "
            f"{relationship_repair_code}. Не сокращайте и не разбивайте пакет. Верните все строки "
            "заново. Для TOTAL_FOR укажите непустые related_quantity_candidate_ids и булево "
            "component_set_complete. Для COMPONENT_OF/SUBTOTAL_OF укажите связанный итог и "
            "component_set_complete=null. Для NONE список связей должен быть пустым."
        )
    return f"""Вы анализируете извлечённые описания российского строительного проекта.
Для КАЖДОЙ входной строки определите, является ли она строительной операцией, к какому виду работ
относится и можно ли привязать её к одному сооружению. Не придумывайте отсутствующие работы,
сооружения, объёмы или материалы. Совпадение по одному слову недостаточно. Перевозка, погрузка,
испытание и временная операция могут быть отдельной коммерческой работой; материал, заголовок,
техническая характеристика и функция оборудования не являются работой.
{relationship_instruction}
{relationship_repair_instruction}

Структурированная задача: {task_payload}

Верните только JSON:
{{"observations":[{{"candidate_id":"...","status":"MATCHED|AMBIGUOUS|UNCLASSIFIED|NOT_A_WORK",
"family_key":"ключ или null","operation":"краткое профессиональное название или null",
"facility":"одно допустимое сооружение или null","confidence":"0.00..1.00",
"reason":"краткая инженерная причина","quantity_reviews":[{{
"quantity_candidate_id":"...","status":"WORK_QUANTITY|DIMENSION|DURATION|RESOURCE_OR_RATE|UNRELATED|AMBIGUOUS",
"source_value":"точное числовое значение из источника или null",
"source_unit":"точная единица из источника, включая масштаб 10/100/1000, или null",
"semantic_scope":"что именно измеряет значение","quantity_type":"TOTAL|SUBTOTAL|COMPONENT|STANDALONE|DIMENSION|DURATION|RESOURCE_OR_RATE|UNKNOWN",
"relation_kind":"COMPONENT_OF|SUBTOTAL_OF|TOTAL_FOR|ALTERNATIVE_TO|DUPLICATE_OF|REVISION_OF|INCOMPARABLE_TO|NONE",
"related_quantity_candidate_ids":["..."],"scope_compatibility":"SAME_SCOPE|OVERLAPPING_SCOPE|COMPONENT_VS_TOTAL|DIFFERENT_SCOPE|ALTERNATIVE_DESIGN|REVISION_DIFFERENCE|INSUFFICIENT_INFORMATION",
"component_set_complete":true|false|null,
"reason":"что именно означает значение в данном фрагменте"}}],
"material_reviews":[{{"material_name":"точное наименование без размера/марки",
"material_kind":"краткий общий вид материала","associated_work_family_key":"ключ или null",
"properties":[{{"kind":"GRADE|CLASS|PROFILE|THICKNESS|DIAMETER|TYPE|OTHER",
"value":"значение","unit":"единица или null"}}],
"quantity_candidate_ids":["..."],"confidence":"0.00..1.00",
"reason":"почему материал относится к строке"}}]}}]}}
Верните ровно одну запись для каждого candidate_id, без новых идентификаторов. MATCHED требует один
family_key. AMBIGUOUS/UNCLASSIFIED не должны угадывать family_key. Facility допустим только при
явной привязке из текста или контекста; нахождение в одном документе недостаточно.
Верните ровно одну quantity_reviews для каждого переданного quantity_candidate_id. WORK_QUANTITY
означает объём именно этой строительной операции. Размер, отметка, мощность, расход, процент,
продолжительность, цена и ресурс нормы не являются объёмом работы. Если табличная связь нарушена
или значение нельзя отнести без догадки, используйте AMBIGUOUS, а не WORK_QUANTITY.
source_unit копируйте из ближайшего исходного контекста дословно. Сохраняйте масштаб единицы:
`100 м2`, `10 м3` и `1000 м3` нельзя сокращать до `м2` или `м3`. Если ближайший контекст не
показывает более точную единицу, повторите переданную unit; не вычисляйте физический объём.
source_value указывайте только когда переданное value ошибочно захватило число из единицы или
соседнего столбца, а правильное значение этой же строки дословно присутствует в ближайшем
контексте. Копируйте один исходный числовой токен без арифметики; иначе укажите null.
Отношение TOTAL_FOR/COMPONENT_OF/SUBTOTAL_OF допустимо только между переданными идентификаторами,
когда текст явно устанавливает общий объём и его части в одной роли документа и редакции.
Связанные значения могут находиться в разных строках переданного пакета. Не выводите отношение
из близости чисел.
Все доступные для этого прохода идентификаторы перечислены в all_quantity_candidate_ids,
available_quantity_candidate_ids и peer_quantity_candidate_ids. Если нужный связанный идентификатор
есть в этих полях, используйте его; нельзя утверждать, что идентификатор не передан. Если контекст
явно называет значение итогом, а другие переданные значения — его составляющими, отразите связь
TOTAL_FOR/COMPONENT_OF, не выполняя арифметику самостоятельно.
Для TOTAL_FOR обязательно укажите component_set_complete=true только если переданные связанные
quantity_candidate_id перечисляют ВСЕ составляющие итога. Если передана лишь часть состава,
пропущена вычисляемая/упомянутая составляющая либо полнота неизвестна, укажите false. Во всех
остальных quantity_reviews укажите component_set_complete=null. relation_kind всегда должен быть
одним из перечисленных значений; когда связи нет, используйте NONE. Нельзя объявлять расхождение
между итогом и неполным набором частей.
Пакет может содержать проектные и коммерческие строки одного сооружения из разных документов.
Если они описывают один инженерный объём, используйте одинаковое нормализованное operation. Если
одна строка является частью, включённой работой, альтернативой, другой редакцией или иным объёмом,
не объединяйте их только из-за одинакового deterministic_family_hint; отразите различие в reason.
Для каждой пары переданных чисел по одной инженерной операции примите явное решение о
сопоставимости. Если значения измеряют один и тот же инженерный объём, даже когда сами числа
различаются, укажите SAME_SCOPE для обеих строк и используйте для них дословно одинаковый краткий
semantic_scope. relation_kind при этом может оставаться NONE: одинаковый объём не обязательно
является повтором одной записи. DUPLICATE_OF означает именно повтор одного утверждения, а не просто
сопоставимые строки. REVISION_OF допустимо только при установленной связи редакций, а не потому,
что строки находятся в двух похожих документах. Если область различается, укажите DIFFERENT_SCOPE,
OVERLAPPING_SCOPE либо другую точную причину. INSUFFICIENT_INFORMATION используйте лишь когда
переданного контекста действительно недостаточно для такого решения.
Для NONE верните пустой related_quantity_candidate_ids. Для сравнения укажите одну точную
scope_compatibility; DIFFERENT_SCOPE и INSUFFICIENT_INFORMATION не создают расхождение объёмов.
deterministic_family_hint получен воспроизводимым словарём и может быть принят как family_key, если
контекст ему не противоречит; сооружение всё равно требует явной привязки.
material_reviews содержит только явно названные в строке или ближайшем контексте материалы,
изделия и их характеристики. Для строки без материала верните пустой список. Материальная позиция
может иметь status=NOT_A_WORK и при этом обязана остаться в material_reviews. material_name — точное
наименование без марки, класса, профиля, толщины и диаметра; material_kind — общий инженерный вид,
нормализованный одинаково для проектной и коммерческой формулировки одного материала. Не объединяйте
разные материалы только по общей работе. Свяжите quantity_candidate_ids только с количеством ресурса,
не с объёмом строительной операции. associated_work_family_key допустим только из переданного каталога.
Размеры и обозначения сохраняйте в properties; числовые значения не сравнивайте самостоятельно.
Явная строительная работа, исключённая из ВОР, сметы, договора или цены предложения, остаётся
работой: используйте MATCHED либо AMBIGUOUS и отразите коммерческое исключение в reason. Нельзя
помечать такую работу NOT_A_WORK только потому, что она не включена в предложение.
"""


def potential_work_description(wording: str) -> bool:
    """Return whether a source wording explicitly starts as a construction operation."""

    return bool(_POTENTIAL_WORK_AT_START.search(wording.strip()))


def _parse(
    raw: str,
    *,
    input_ids: tuple[str, ...],
    wording_by_id: Mapping[str, str],
    quantity_ids_by_work: Mapping[str, tuple[str, ...]],
    quantity_context_by_id: Mapping[str, str],
    work_families: Mapping[str, str],
    facilities: tuple[str, ...],
    relationship_review: bool,
    mark_relationship_reviewed: bool,
) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_work_reconciliation_invalid_json") from exc
    values = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise QwenSemanticFailure("qwen_work_reconciliation_invalid_shape")
    if len(values) != len(input_ids):
        raise QwenSemanticFailure("qwen_work_reconciliation_incomplete_output")
    allowed_ids = set(input_ids)
    all_quantity_ids = {
        quantity_id
        for candidate_id in input_ids
        for quantity_id in quantity_ids_by_work.get(candidate_id, ())
    }
    allowed_families = set(work_families)
    allowed_facilities = set(facilities)
    observations: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise QwenSemanticFailure("qwen_work_reconciliation_invalid_shape")
        candidate_id = str(value.get("candidate_id") or "")
        status = str(value.get("status") or "")
        family = value.get("family_key")
        family_key = str(family) if family is not None else None
        operation = str(value.get("operation") or "").strip() or None
        facility = str(value.get("facility") or "").strip() or None
        reason = " ".join(str(value.get("reason") or "").split())
        raw_quantity_reviews = value.get("quantity_reviews")
        raw_material_reviews = value.get("material_reviews", [])
        try:
            confidence = Decimal(str(value.get("confidence")))
        except (InvalidOperation, TypeError) as exc:
            raise QwenSemanticFailure("qwen_work_reconciliation_confidence_invalid") from exc
        if candidate_id not in allowed_ids or candidate_id in observations:
            raise QwenSemanticFailure("qwen_work_reconciliation_identity_invalid")
        if status not in _STATUSES or not Decimal("0") <= confidence <= Decimal("1") or not reason:
            raise QwenSemanticFailure("qwen_work_reconciliation_observation_invalid")
        if status == "MATCHED":
            if family_key not in allowed_families or operation is None:
                raise QwenSemanticFailure("qwen_work_reconciliation_family_invalid")
        elif family_key is not None:
            raise QwenSemanticFailure("qwen_work_reconciliation_unresolved_family_invalid")
        if status == "NOT_A_WORK" and potential_work_description(
            wording_by_id.get(candidate_id, "")
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_potential_work_excluded")
        if facility is not None and facility not in allowed_facilities:
            facility = None
            reason = (
                f"{reason} Привязка к сооружению не принята: указанное обозначение отсутствует "
                "в установленном составе объекта."
            )
        if facility is not None and _WEAK_FACILITY_REASON.search(reason):
            facility = None
            reason = (
                f"{reason} Привязка к сооружению не принята: близость упоминаний без явной "
                "инженерной связи недостаточна."
            )
        quantity_ids = quantity_ids_by_work.get(candidate_id, ())
        quantity_reviews = _parse_quantity_reviews(
            raw_quantity_reviews,
            quantity_ids,
            source_context_by_id=quantity_context_by_id,
            allowed_related_ids=all_quantity_ids,
            relationship_review=mark_relationship_reviewed,
        )
        material_reviews = _parse_material_reviews(
            raw_material_reviews,
            allowed_quantity_ids=set(quantity_ids),
            work_families=allowed_families,
        )
        observation: dict[str, Any] = {
            "candidate_id": candidate_id,
            "status": status,
            "family_key": family_key,
            "operation": operation,
            "facility": facility,
            "confidence": format(confidence, "f"),
            "reason": reason[:500],
        }
        if quantity_ids:
            observation["quantity_reviews"] = quantity_reviews
        if material_reviews:
            observation["material_reviews"] = material_reviews
        observations[candidate_id] = observation
    if set(observations) != allowed_ids:
        raise QwenSemanticFailure("qwen_work_reconciliation_incomplete_output")
    return [observations[candidate_id] for candidate_id in input_ids]


def _parse_material_reviews(
    raw: object,
    *,
    allowed_quantity_ids: set[str],
    work_families: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > 4:
        raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for value in raw:
        if not isinstance(value, dict):
            raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
        material_name = " ".join(str(value.get("material_name") or "").split())
        material_kind = " ".join(str(value.get("material_kind") or "").split())
        family = value.get("associated_work_family_key")
        family_key = str(family) if family is not None else None
        reason = " ".join(str(value.get("reason") or "").split())
        try:
            confidence = Decimal(str(value.get("confidence")))
        except (InvalidOperation, TypeError) as exc:
            raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid") from exc
        raw_quantity_ids = value.get("quantity_candidate_ids")
        raw_properties = value.get("properties")
        if (
            not material_name
            or not material_kind
            or (family_key is not None and family_key not in work_families)
            or not Decimal("0") <= confidence <= Decimal("1")
            or not reason
            or not isinstance(raw_quantity_ids, list)
            or not isinstance(raw_properties, list)
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
        quantity_ids = tuple(str(item) for item in raw_quantity_ids)
        if len(set(quantity_ids)) != len(quantity_ids) or not set(quantity_ids).issubset(
            allowed_quantity_ids
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
        properties: list[dict[str, str | None]] = []
        for raw_property in raw_properties:
            if not isinstance(raw_property, dict):
                raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
            kind = str(raw_property.get("kind") or "")
            property_value = " ".join(str(raw_property.get("value") or "").split())
            unit_value = " ".join(str(raw_property.get("unit") or "").split()) or None
            if kind not in _MATERIAL_PROPERTY_KINDS or not property_value:
                raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
            properties.append({"kind": kind, "value": property_value[:160], "unit": unit_value})
        identity = (material_kind.casefold(), material_name.casefold())
        if identity in seen:
            raise QwenSemanticFailure("qwen_work_reconciliation_material_output_invalid")
        seen.add(identity)
        result.append(
            {
                "material_name": material_name[:300],
                "material_kind": material_kind[:200],
                "associated_work_family_key": family_key,
                "properties": properties,
                "quantity_candidate_ids": list(quantity_ids),
                "confidence": format(confidence, "f"),
                "reason": reason[:500],
            }
        )
    return result


def _parse_quantity_reviews(
    raw: object,
    input_ids: tuple[str, ...],
    *,
    source_context_by_id: Mapping[str, str] | None = None,
    allowed_related_ids: set[str] | None = None,
    relationship_review: bool = False,
) -> list[dict[str, Any]]:
    if not input_ids:
        if raw not in (None, []):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_unexpected")
        return []
    if not isinstance(raw, list) or len(raw) != len(input_ids):
        raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_incomplete")
    allowed_ids = set(input_ids)
    relation_ids = allowed_related_ids if allowed_related_ids is not None else allowed_ids
    reviews: dict[str, dict[str, Any]] = {}
    for value in raw:
        if not isinstance(value, dict):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        candidate_id = str(value.get("quantity_candidate_id") or "")
        status = str(value.get("status") or "")
        source_value = " ".join(str(value.get("source_value") or "").split()) or None
        source_unit = " ".join(str(value.get("source_unit") or "").split()) or None
        semantic_scope = " ".join(str(value.get("semantic_scope") or "").split())
        quantity_type = str(value.get("quantity_type") or "")
        relation_kind = str(value.get("relation_kind") or "")
        scope_compatibility = str(value.get("scope_compatibility") or "")
        related = value.get("related_quantity_candidate_ids")
        component_set_complete = value.get("component_set_complete")
        reason = " ".join(str(value.get("reason") or "").split())
        if (
            candidate_id not in allowed_ids
            or candidate_id in reviews
            or status not in _QUANTITY_STATUSES
            or quantity_type not in QuantityType
            or relation_kind not in QuantityRelation
            or scope_compatibility not in ScopeCompatibility
            or not semantic_scope
            or not isinstance(related, list)
            or not reason
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        if source_unit is not None:
            context = (source_context_by_id or {}).get(candidate_id, "")
            normalized_context = _normalized_unit_evidence(context)
            normalized_source_unit = _normalized_unit_evidence(source_unit)
            if (
                len(source_unit) > 40
                or not normalized_source_unit
                or normalized_source_unit not in normalized_context
            ):
                raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        if source_value is not None:
            context = (source_context_by_id or {}).get(candidate_id, "")
            if len(source_value) > 80 or not _source_numeric_token_present(source_value, context):
                raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        if relationship_review:
            if relation_kind == QuantityRelation.TOTAL_FOR:
                if not isinstance(component_set_complete, bool):
                    raise QwenSemanticFailure(
                        "qwen_work_reconciliation_component_completeness_invalid"
                    )
            elif component_set_complete not in (None, False):
                raise QwenSemanticFailure("qwen_work_reconciliation_component_completeness_invalid")
            else:
                # Models occasionally emit false rather than null for a component.
                # Both mean that completeness is not asserted by this non-total row;
                # normalize the harmless schema variation without changing any
                # semantic relationship.
                component_set_complete = None
        related_ids = tuple(str(item) for item in related)
        if (
            len(set(related_ids)) != len(related_ids)
            or candidate_id in related_ids
            or not set(related_ids).issubset(relation_ids)
            or (relation_kind == QuantityRelation.NONE and related_ids)
            or (relation_kind != QuantityRelation.NONE and not related_ids)
        ):
            raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_invalid")
        reviews[candidate_id] = {
            "quantity_candidate_id": candidate_id,
            "status": status,
            "semantic_scope": semantic_scope[:500],
            "quantity_type": quantity_type,
            "relation_kind": relation_kind,
            "related_quantity_candidate_ids": list(related_ids),
            "scope_compatibility": scope_compatibility,
            "reason": reason[:500],
        }
        if source_unit is not None:
            reviews[candidate_id]["source_unit"] = source_unit
        if source_value is not None:
            reviews[candidate_id]["source_value"] = source_value
        if relationship_review:
            reviews[candidate_id]["relationship_reviewed"] = True
            reviews[candidate_id]["component_set_complete"] = component_set_complete
    if set(reviews) != allowed_ids:
        raise QwenSemanticFailure("qwen_work_reconciliation_quantity_output_incomplete")
    return [reviews[candidate_id] for candidate_id in input_ids]


def _normalized_unit_evidence(value: object) -> str:
    normalized = " ".join(
        str(value or "").casefold().replace("²", "2").replace("³", "3").replace("\xa0", " ").split()
    )
    # Native PDF extraction and OCR commonly separate glyphs inside compact
    # Russian units (``ш т``, ``м 2`` and ``м 3``).  Qwen correctly returns the
    # professional spelling; normalize only these established unit tokens so
    # source evidence remains strict without rejecting an orthographic repair.
    normalized = re.sub(r"\bш\s+т\b", "шт", normalized)
    normalized = re.sub(r"\b([мm])\s+([23])\b", r"\1\2", normalized)
    return normalized


def _source_numeric_token_present(value: object, context: object) -> bool:
    """Require a copied source number; model-derived arithmetic is never accepted."""

    candidate = str(value or "").strip().replace("\xa0", " ")
    token_pattern = r"[-+]?(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d+)?"
    if not re.fullmatch(token_pattern, candidate):
        return False
    try:
        expected = Decimal(candidate.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return False
    for token in re.findall(rf"(?<![\w]){token_pattern}(?![\w])", str(context or "")):
        try:
            observed = Decimal(token.replace("\xa0", "").replace(" ", "").replace(",", "."))
        except InvalidOperation:
            continue
        if observed == expected:
            return True
    return False
