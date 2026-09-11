# ruff: noqa: E501, RUF001 -- bounded Russian JSON prompts are intentionally literal.
"""Bounded, evidence-bound Qwen semantic document classification."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any
from uuid import UUID

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import deterministic_uuid

from .models import (
    CandidateDecision,
    DocumentRole,
    ExactLocator,
    LayoutElement,
    MappingStatus,
    MaterialCandidate,
    ProjectFieldCandidate,
    QuantityCandidate,
    RoleCandidate,
    RoleDecision,
    StructureNodeCandidate,
    WorkTypeCandidate,
)
from .semantic import StructuredCandidates

QWEN_SEMANTIC_CLASSIFICATION_PROFILE = "qwen-document-semantic-v1"
QWEN_ENGINEERING_EXTRACTION_PROFILE = "qwen-engineering-extraction-v2"
_MAX_PAGES = 6
_MAX_CHARS_PER_PAGE = 800
_MAX_PROMPT_CHARS = 4_800


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


@dataclass(frozen=True, slots=True)
class QwenEngineeringBatch:
    ordinal: int
    digest: str
    fragments: tuple[_SemanticFragment, ...]

    @property
    def locator_ids(self) -> tuple[UUID, ...]:
        return tuple(item.locator.source_locator_id for item in self.fragments)


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

    def extract_engineering(
        self,
        elements: Iterable[LayoutElement],
        *,
        accepted_batches: Mapping[str, dict[str, object]] | None = None,
        on_accepted_batch: Callable[[QwenEngineeringBatch, dict[str, object]], None] | None = None,
    ) -> StructuredCandidates:
        """Extract evidence-bound engineering candidates from every bounded locator batch."""
        batches = _engineering_batches(elements)
        if not batches:
            raise QwenSemanticFailure("qwen_engineering_input_unavailable")
        accepted = accepted_batches or {}
        extracted: list[tuple[dict[str, _SemanticFragment], dict[str, list[tuple[str, ...]]]]] = []
        for batch in batches:
            allowed = {str(item.locator.source_locator_id): item for item in batch.fragments}
            persisted = accepted.get(batch.digest)
            if persisted is None:
                payload = _complete(
                    self._endpoint,
                    _engineering_prompt(batch.fragments),
                    self._timeout_seconds,
                    max_tokens=1_200,
                )
                parsed = _parse_engineering(payload, allowed)
                if on_accepted_batch is not None:
                    on_accepted_batch(batch, _engineering_manifest(parsed))
            else:
                parsed = _parse_engineering_manifest(persisted, allowed)
            extracted.append((allowed, parsed))
        fields: list[ProjectFieldCandidate] = []
        structures: list[StructureNodeCandidate] = []
        works: list[WorkTypeCandidate] = []
        quantities: list[QuantityCandidate] = []
        materials: list[MaterialCandidate] = []
        parsed_quantities: list[tuple[str, str, str, ExactLocator]] = []
        parsed_materials: list[tuple[str, str, str, str, ExactLocator]] = []
        work_by_normalized_name: dict[str, WorkTypeCandidate] = {}
        for allowed, parsed in extracted:
            for name, locator_id in parsed["works"]:
                locator = allowed[locator_id].locator
                normalized = " ".join(name.casefold().split())
                value = WorkTypeCandidate(
                    deterministic_uuid(
                        f"qwen-work:{locator.source_version_id}:{locator_id}:{normalized}"
                    ),
                    name,
                    normalized,
                    f"page:{locator.page_number}",
                    locator,
                    DocumentRole.PROJECT_DOCUMENTATION,
                    MappingStatus.UNRESOLVED,
                )
                work_by_normalized_name[normalized] = value
                works.append(value)
            for key, raw, locator_id in parsed["fields"]:
                locator = allowed[locator_id].locator
                fields.append(
                    ProjectFieldCandidate(
                        deterministic_uuid(
                            f"qwen-field:{locator.source_version_id}:{locator_id}:{key}:{raw}"
                        ),
                        key,
                        raw,
                        raw,
                        "text",
                        locator,
                        QWEN_SEMANTIC_CLASSIFICATION_PROFILE,
                        ("qwen_semantic_candidate",),
                    )
                )
            for kind, name, locator_id in parsed["structures"]:
                locator = allowed[locator_id].locator
                normalized = " ".join(name.casefold().split())
                structures.append(
                    StructureNodeCandidate(
                        deterministic_uuid(
                            f"qwen-structure:{locator.source_version_id}:{locator_id}:{kind}:{normalized}"
                        ),
                        kind,
                        name,
                        normalized,
                        locator,
                    )
                )
            for work_name, raw, unit, locator_id in parsed["quantities"]:
                locator = allowed[locator_id].locator
                parsed_quantities.append((work_name, raw, unit, locator))
            for work_name, name, raw, unit, locator_id in parsed["materials"]:
                locator = allowed[locator_id].locator
                parsed_materials.append((work_name, name, raw, unit, locator))
        for work_name, raw, unit, locator in parsed_quantities:
            work = work_by_normalized_name.get(" ".join(work_name.casefold().split()))
            if work is None:
                continue
            try:
                parsed_value = Decimal(raw.replace(",", "."))
            except InvalidOperation:
                parsed_value = None
            quantities.append(
                QuantityCandidate(
                    deterministic_uuid(
                        f"qwen-quantity:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{work.candidate_id}:{raw}:{unit}"
                    ),
                    work.candidate_id,
                    raw,
                    parsed_value,
                    unit,
                    parsed_value,
                    unit if parsed_value is not None else None,
                    None,
                    work.scope_key,
                    locator,
                    CandidateDecision.CANDIDATE,
                )
            )
        for work_name, name, raw, unit, locator in parsed_materials:
            work = work_by_normalized_name.get(" ".join(work_name.casefold().split()))
            if work is None:
                continue
            try:
                parsed_value = Decimal(raw.replace(",", "."))
            except InvalidOperation:
                parsed_value = None
            materials.append(
                MaterialCandidate(
                    deterministic_uuid(
                        f"qwen-material:{locator.source_version_id}:{locator.source_locator_id}:"
                        f"{work.candidate_id}:{name}"
                    ),
                    work.candidate_id,
                    name,
                    " ".join(name.casefold().split()),
                    raw or None,
                    parsed_value,
                    unit or None,
                    unit or None,
                    locator,
                    CandidateDecision.CANDIDATE,
                )
            )
        return StructuredCandidates(
            tuple(fields),
            tuple(works),
            tuple(quantities),
            tuple(materials),
            (),
            (),
            tuple(structures),
        )


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


def _fragments(elements: Iterable[LayoutElement]) -> tuple[_SemanticFragment, ...]:
    fragments: list[_SemanticFragment] = []
    for item in elements:
        text = item.normalized_text
        for offset in range(0, len(text), 2_400):
            fragments.append(_SemanticFragment(item.locator, text[offset : offset + 2_400]))
    return tuple(fragments)


def _engineering_batches(elements: Iterable[LayoutElement]) -> tuple[QwenEngineeringBatch, ...]:
    fragments = _fragments(elements)
    batches: list[QwenEngineeringBatch] = []
    for ordinal, offset in enumerate(range(0, len(fragments), 24), start=1):
        batch = fragments[offset : offset + 24]
        batch_payload = [
            {
                "locator_id": str(item.locator.source_locator_id),
                "evidence_digest": item.locator.evidence_digest,
                "text": item.text,
            }
            for item in batch
        ]
        digest = semantic_digest(
            {
                "profile_version": QWEN_ENGINEERING_EXTRACTION_PROFILE,
                "fragments": batch_payload,
            }
        )
        batches.append(QwenEngineeringBatch(ordinal, digest, batch))
    return tuple(batches)


def _engineering_manifest(parsed: dict[str, list[tuple[str, ...]]]) -> dict[str, object]:
    return {key: [list(item) for item in values] for key, values in parsed.items()}


def _engineering_prompt(elements: tuple[_SemanticFragment, ...]) -> str:
    fragments = [
        {
            "locator_id": str(item.locator.source_locator_id),
            "page": item.locator.page_number,
            "text": item.text,
        }
        for item in elements
    ]
    return (
        "Извлеки только явно подтверждённые инженерные кандидаты. Верни один JSON: "
        '{"fields":[{"key":"...","value":"...","locator_id":"..."}],'
        '"structures":[{"kind":"excavation_pit|structure|zone","name":"...","locator_id":"..."}],'
        '"works":[{"name":"...","locator_id":"..."}],'
        '"quantities":[{"work_name":"...","value":"...","unit":"...","locator_id":"..."}],'
        '"materials":[{"work_name":"...","name":"...","quantity":"...","unit":"...","locator_id":"..."}]}. '
        "Все пять ключей JSON обязательны, даже если соответствующий массив пуст. "
        "quantity и unit материала могут быть пустыми строками, если источник их не указывает. "
        "Каждый locator_id только из входа; если нет факта, массив пуст.\nФРАГМЕНТЫ:\n"
        + json.dumps(fragments, ensure_ascii=False, separators=(",", ":"))
    )


def _parse_engineering(
    answer: str, allowed: dict[str, _SemanticFragment]
) -> dict[str, list[tuple[str, ...]]]:
    try:
        value = _json_object(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_engineering_response_invalid_json") from exc
    if not isinstance(value, dict) or set(value) != {
        "fields",
        "structures",
        "works",
        "quantities",
        "materials",
    }:
        raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
    result: dict[str, list[tuple[str, ...]]] = {
        "fields": [],
        "structures": [],
        "works": [],
        "quantities": [],
        "materials": [],
    }
    specs = {
        "fields": ("key", "value", "locator_id"),
        "structures": ("kind", "name", "locator_id"),
        "works": ("name", "locator_id"),
        "quantities": ("work_name", "value", "unit", "locator_id"),
        "materials": ("work_name", "name", "quantity", "unit", "locator_id"),
    }
    for key, names in specs.items():
        rows = value.get(key, [])
        if not isinstance(rows, list) or len(rows) > 64:
            raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
        for row in rows:
            if not isinstance(row, dict):
                raise QwenSemanticFailure("qwen_engineering_response_invalid_shape")
            item = tuple(" ".join(str(row.get(name, "")).split()) for name in names)
            required = item[:-3] + item[-1:] if key == "materials" else item
            if not all(required) or item[-1] not in allowed:
                raise QwenSemanticFailure("qwen_engineering_response_invalid_evidence")
            if key == "structures" and item[0] not in {"excavation_pit", "structure", "zone"}:
                raise QwenSemanticFailure("qwen_engineering_response_invalid_kind")
            result[key].append(item)
    return result


def _parse_engineering_manifest(
    manifest: dict[str, object], allowed: dict[str, _SemanticFragment]
) -> dict[str, list[tuple[str, ...]]]:
    result: dict[str, list[tuple[str, ...]]] = {
        "fields": [],
        "structures": [],
        "works": [],
        "quantities": [],
        "materials": [],
    }
    specs = {
        "fields": ("key", "value", "locator_id"),
        "structures": ("kind", "name", "locator_id"),
        "works": ("name", "locator_id"),
        "quantities": ("work_name", "value", "unit", "locator_id"),
        "materials": ("work_name", "name", "quantity", "unit", "locator_id"),
    }
    for key, names in specs.items():
        rows = manifest.get(key, [])
        if not isinstance(rows, list) or len(rows) > 64:
            raise QwenSemanticFailure("qwen_engineering_manifest_invalid_shape")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(names):
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_shape")
            item = tuple(" ".join(str(value).split()) for value in row)
            if not all(item) or item[-1] not in allowed:
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_evidence")
            if key == "structures" and item[0] not in {"excavation_pit", "structure", "zone"}:
                raise QwenSemanticFailure("qwen_engineering_manifest_invalid_kind")
            result[key].append(item)
    return result


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
        "Используй только приведённые фрагменты. Верни первой и единственной строкой JSON "
        "без Markdown: "
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


def _complete(endpoint: str, prompt: str, timeout_seconds: float, *, max_tokens: int = 350) -> str:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {"prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}, ensure_ascii=False
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
