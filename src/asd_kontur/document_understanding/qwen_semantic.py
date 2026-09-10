# ruff: noqa: RUF001 -- Russian bounded prompt is intentional.
"""Bounded, evidence-bound Qwen semantic document classification."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid

from .models import (
    DocumentRole,
    ExactLocator,
    LayoutElement,
    RoleCandidate,
    RoleDecision,
    StructureNodeCandidate,
)

QWEN_SEMANTIC_CLASSIFICATION_PROFILE = "qwen-document-semantic-v1"
_MAX_PAGES = 18
_MAX_CHARS_PER_PAGE = 1_600
_MAX_PROMPT_CHARS = 24_000


class QwenSemanticFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class QwenSemanticClassification:
    candidates: tuple[RoleCandidate, ...]
    decisions: tuple[RoleDecision, ...]


@dataclass(frozen=True, slots=True)
class _SemanticFragment:
    locator: ExactLocator
    text: str


class QwenDocumentSemanticAdapter:
    """Call loopback Qwen with bounded extracted text and exact locators only."""

    def __init__(self, endpoint: str, *, timeout_seconds: float = 900.0) -> None:
        if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("qwen_semantic_endpoint_invalid")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def classify(self, elements: Iterable[LayoutElement]) -> QwenSemanticClassification:
        pages = _sample_pages(elements)
        if not pages:
            raise QwenSemanticFailure("qwen_semantic_input_unavailable")
        prompt = _prompt(pages)
        payload = _complete(self._endpoint, prompt, self._timeout_seconds)
        roles, locator_ids = _parse(
            payload, {str(item.locator.source_locator_id): item for item in pages}
        )
        locators = tuple(
            {str(item.locator.source_locator_id): item.locator for item in pages}[item]
            for item in locator_ids
        )
        source_version_id = locators[0].source_version_id
        scope = f"page:{locators[0].page_number}"
        role_candidates: list[RoleCandidate] = []
        candidate_ids: list[UUID] = []
        for role in roles:
            candidate_id = deterministic_uuid(
                f"qwen-document-role:{source_version_id}:{role.value}:"
                f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
            )
            candidate_ids.append(candidate_id)
            role_candidates.append(
                RoleCandidate(
                    candidate_id=candidate_id,
                    role=role,
                    scope=scope,
                    score=Decimal("0.80"),
                    signal_codes=("qwen:bounded_document_semantic",),
                    locators=locators,
                    extraction_profile_version=QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                    model_attempt_id=deterministic_uuid(
                        f"qwen-document-role-attempt:{source_version_id}:"
                        f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
                    ),
                )
            )
        decision_id = deterministic_uuid(
            f"qwen-document-role-decision:{source_version_id}:"
            f"{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
        )
        decision = RoleDecision(
            decision_id=decision_id,
            decision_version=1,
            scope=scope,
            selected_roles=roles,
            candidate_ids=tuple(candidate_ids),
            decision_code="qwen_bounded_document_semantic",
            validator_version=QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
            locators=locators,
        )
        return QwenSemanticClassification(tuple(role_candidates), (decision,))

    def extract_structures(
        self, elements: Iterable[LayoutElement]
    ) -> tuple[StructureNodeCandidate, ...]:
        pages = _sample_pages(elements)
        if not pages:
            raise QwenSemanticFailure("qwen_structure_input_unavailable")
        payload = _complete(self._endpoint, _structure_prompt(pages), self._timeout_seconds)
        allowed = {str(item.locator.source_locator_id): item for item in pages}
        observations = _parse_structures(payload, allowed)
        values: list[StructureNodeCandidate] = []
        for kind, name, locator_id in observations:
            locator = allowed[locator_id].locator
            normalized = " ".join(name.casefold().split())
            values.append(
                StructureNodeCandidate(
                    structure_node_id=deterministic_uuid(
                        f"qwen-structure:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{kind}:{normalized}:{QWEN_SEMANTIC_CLASSIFICATION_PROFILE}"
                    ),
                    node_kind=kind,
                    raw_name=name,
                    normalized_name=normalized,
                    locator=locator,
                )
            )
        return tuple(values)


def _sample_pages(elements: Iterable[LayoutElement]) -> tuple[_SemanticFragment, ...]:
    by_page: dict[int, list[LayoutElement]] = defaultdict(list)
    for element in elements:
        if element.normalized_text:
            by_page[element.locator.page_number].append(element)
    sampled: list[_SemanticFragment] = []
    used = 0
    for page_number in sorted(by_page)[:_MAX_PAGES]:
        page_elements = by_page[page_number]
        text = " ".join(item.normalized_text for item in page_elements)
        if not text:
            continue
        if used + min(len(text), _MAX_CHARS_PER_PAGE) > _MAX_PROMPT_CHARS:
            break
        sampled.append(_SemanticFragment(page_elements[0].locator, text[:_MAX_CHARS_PER_PAGE]))
        used += min(len(text), _MAX_CHARS_PER_PAGE)
    return tuple(sampled)


def _prompt(elements: tuple[_SemanticFragment, ...]) -> str:
    pages = [
        {
            "page": item.locator.page_number,
            "locator_id": str(item.locator.source_locator_id),
            "text": item.text,
        }
        for item in elements
    ]
    return (
        "Ты выполняешь ограниченную классификацию строительного документа. "
        "Используй только приведённые фрагменты. Верни только JSON без Markdown: "
        '{"roles":["..."],"locator_ids":["..."]}. '
        "roles — от одного до трёх точных значений из: explanatory_note, "
        "project_documentation, working_documentation, bill_of_quantities, local_estimate, "
        "object_estimate, consolidated_estimate, specification, contract, customer_regulation, "
        "normative_reference_list, executive_documentation, drawing_or_scheme, "
        "correspondence_administrative, unknown. locator_ids должны ссылаться только на "
        "фрагменты, подтверждающие выбранные roles. Не придумывай данные.\nФРАГМЕНТЫ:\n"
        + json.dumps(pages, ensure_ascii=False, separators=(",", ":"))
    )


def _structure_prompt(elements: tuple[_SemanticFragment, ...]) -> str:
    pages = [
        {
            "page": item.locator.page_number,
            "locator_id": str(item.locator.source_locator_id),
            "text": item.text,
        }
        for item in elements
    ]
    return (
        "Извлеки только явно обозначенные элементы структуры строительного объекта из фрагментов. "
        'Верни только JSON без Markdown: {"structures":[{"kind":"...","name":"...",'
        '"locator_id":"..."}]}. Допустимые kind: excavation_pit, structure, zone. '
        "Котлован включай только если фрагмент прямо устанавливает отдельный экземпляр, "
        "а не типовое решение или общее слово. locator_id обязан быть одним из входных. "
        "Не придумывай геометрию, количество, связи или имена. Если подтверждённых "
        "элементов нет, верни пустой массив.\nФРАГМЕНТЫ:\n"
        + json.dumps(pages, ensure_ascii=False, separators=(",", ":"))
    )


def _complete(endpoint: str, prompt: str, timeout_seconds: float) -> str:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {"prompt": prompt, "max_tokens": 350, "temperature": 0.0}, ensure_ascii=False
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    parts: list[str] = []
    completed = False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            while line := response.readline():
                event = json.loads(line)
                if event.get("event") == "delta":
                    parts.append(str(event.get("text", "")))
                elif event.get("event") == "completed":
                    completed = True
                    break
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        IncompleteRead,
        RemoteDisconnected,
        json.JSONDecodeError,
    ) as exc:
        raise QwenSemanticFailure("qwen_semantic_runtime_unavailable") from exc
    answer = "".join(parts).strip()
    if not completed or not answer:
        raise QwenSemanticFailure("qwen_semantic_response_incomplete")
    return answer


def _parse(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> tuple[tuple[DocumentRole, ...], tuple[str, ...]]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_semantic_response_invalid_json") from exc
    if not isinstance(value, dict):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_shape")
    raw_roles = value.get("roles")
    raw_locator_ids = value.get("locator_ids")
    if not isinstance(raw_roles, list) or not isinstance(raw_locator_ids, list):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_shape")
    try:
        roles = tuple(DocumentRole(str(item)) for item in raw_roles)
    except ValueError as exc:
        raise QwenSemanticFailure("qwen_semantic_response_invalid_role") from exc
    locator_ids = tuple(str(item) for item in raw_locator_ids)
    if not 1 <= len(roles) <= 3 or len(set(roles)) != len(roles):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_role")
    if not locator_ids or len(set(locator_ids)) != len(locator_ids):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_locator")
    if any(item not in allowed for item in locator_ids):
        raise QwenSemanticFailure("qwen_semantic_response_invalid_locator")
    return roles, locator_ids


def _parse_structures(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> tuple[tuple[str, str, str], ...]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_structure_response_invalid_json") from exc
    rows = value.get("structures") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) > 32:
        raise QwenSemanticFailure("qwen_structure_response_invalid_shape")
    observed: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise QwenSemanticFailure("qwen_structure_response_invalid_shape")
        kind = str(row.get("kind", ""))
        name = " ".join(str(row.get("name", "")).split())
        locator_id = str(row.get("locator_id", ""))
        if kind not in {"excavation_pit", "structure", "zone"}:
            raise QwenSemanticFailure("qwen_structure_response_invalid_kind")
        if not 2 <= len(name) <= 500 or locator_id not in allowed:
            raise QwenSemanticFailure("qwen_structure_response_invalid_evidence")
        item = (kind, name, locator_id)
        if item in seen:
            continue
        seen.add(item)
        observed.append(item)
    return tuple(observed)


def _json_object(answer: str) -> Any:
    """Accept one JSON object even when the local model wraps it in harmless prose."""
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise json.JSONDecodeError("JSON object not found", text, 0)
