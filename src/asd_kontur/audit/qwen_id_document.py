"""Bounded local-Qwen interpretation of an uploaded as-built document.

The model identifies the form and a possible work scope. Exact source quotes
and locator identities are validated here; the result is not an Audit Fact or
proof that a signature, inspection, test, or completed work exists.
"""

# ruff: noqa: RUF001 -- Russian production task wording is intentional.

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from asd_kontur.document_understanding.models import LayoutElement
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure, _complete

ID_DOCUMENT_INTERPRETATION_PROFILE = "qwen-id-document-interpretation-v1"
_DOCUMENT_TYPES = frozenset(
    {
        "document_register",
        "concealed_work_act",
        "critical_structure_act",
        "acceptance_act",
        "work_log",
        "as_built_drawing",
        "material_certificate",
        "laboratory_report",
        "quantity_statement",
        "transmittal_register",
        "ks2",
        "ks3",
        "other_id",
        "unknown",
    }
)
_MAX_FRAGMENTS = 12
_MAX_FRAGMENT_CHARS = 1100
_MAX_TOTAL_CHARS = 8500


def interpret_id_document(
    elements: Iterable[LayoutElement],
    *,
    source_version_id: str,
    endpoint: str,
    timeout_seconds: float,
) -> dict[str, object]:
    if not endpoint.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("qwen_id_document_endpoint_invalid")
    fragments = _bounded_fragments(elements, source_version_id=source_version_id)
    if not fragments:
        raise QwenSemanticFailure("qwen_id_document_source_text_unavailable")
    prompt = _prompt(source_version_id, fragments)
    raw = _complete(endpoint, prompt, timeout_seconds, max_tokens=700)
    try:
        interpreted = parse_id_document_interpretation(
            raw, source_version_id=source_version_id, fragments=fragments
        )
    except QwenSemanticFailure as exc:
        if exc.code not in {
            "qwen_id_document_invalid_json",
            "qwen_id_document_invalid_shape",
            "qwen_id_document_invalid_evidence",
        }:
            raise
        repaired = _complete(
            endpoint,
            prompt
            + "\nИсправь только JSON: "
            + exc.code
            + ". Не добавляй новые факты или цитаты. Предыдущий ответ:\n"
            + raw[:3000],
            timeout_seconds,
            max_tokens=700,
        )
        interpreted = parse_id_document_interpretation(
            repaired, source_version_id=source_version_id, fragments=fragments
        )
    return {
        "profile_version": ID_DOCUMENT_INTERPRETATION_PROFILE,
        "source_version_id": source_version_id,
        "input_source_locator_ids": [item["source_locator_id"] for item in fragments],
        **interpreted,
        "authority": "qwen_candidate_requires_independent_audit",
    }


def parse_id_document_interpretation(
    answer: str,
    *,
    source_version_id: str,
    fragments: tuple[dict[str, object], ...],
) -> dict[str, object]:
    try:
        value = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise QwenSemanticFailure("qwen_id_document_invalid_json") from exc
    keys = {
        "source_version_id",
        "document_type",
        "document_type_quote",
        "document_type_locator_id",
        "work_scope",
        "work_quote",
        "work_locator_id",
        "uncertainty",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise QwenSemanticFailure("qwen_id_document_invalid_shape")
    if (
        value["source_version_id"] != source_version_id
        or value["document_type"] not in _DOCUMENT_TYPES
    ):
        raise QwenSemanticFailure("qwen_id_document_invalid_shape")
    allowed = {str(item["source_locator_id"]): str(item["text"]) for item in fragments}
    type_quote = _optional_text(value["document_type_quote"])
    type_locator = _optional_text(value["document_type_locator_id"])
    work_scope = _optional_text(value["work_scope"])
    work_quote = _optional_text(value["work_quote"])
    work_locator = _optional_text(value["work_locator_id"])
    uncertainty = _optional_text(value["uncertainty"])
    if value["document_type"] == "unknown":
        if type_quote is not None or type_locator is not None or uncertainty is None:
            raise QwenSemanticFailure("qwen_id_document_invalid_evidence")
    elif not _quote_is_exact(type_quote, type_locator, allowed):
        raise QwenSemanticFailure("qwen_id_document_invalid_evidence")
    if (work_scope is None) != (work_quote is None) or (work_scope is None) != (
        work_locator is None
    ):
        raise QwenSemanticFailure("qwen_id_document_invalid_evidence")
    if work_scope is not None and not _quote_is_exact(work_quote, work_locator, allowed):
        raise QwenSemanticFailure("qwen_id_document_invalid_evidence")
    return {
        "document_type": value["document_type"],
        "document_type_quote": type_quote,
        "document_type_locator_id": type_locator,
        "work_scope": work_scope,
        "work_quote": work_quote,
        "work_locator_id": work_locator,
        "uncertainty": uncertainty,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise QwenSemanticFailure("qwen_id_document_invalid_shape")
    return value.strip()


def _quote_is_exact(quote: str | None, locator: str | None, allowed: dict[str, str]) -> bool:
    return bool(quote and locator and quote in allowed.get(locator, ""))


def _bounded_fragments(
    elements: Iterable[LayoutElement], *, source_version_id: str
) -> tuple[dict[str, object], ...]:
    by_page: dict[int, list[LayoutElement]] = defaultdict(list)
    for element in elements:
        if str(element.locator.source_version_id) != source_version_id:
            raise QwenSemanticFailure("qwen_id_document_source_scope_mismatch")
        text = (element.raw_text or element.normalized_text).strip()
        if text:
            by_page[element.locator.page_number].append(element)
    if not by_page:
        return ()
    pages = sorted(by_page)
    chosen_pages = tuple(dict.fromkeys((*pages[:2], pages[len(pages) // 2], pages[-1])))
    fragments: list[dict[str, object]] = []
    total_chars = 0
    seen_locators: set[str] = set()
    ordered_pages = [
        sorted(by_page[page], key=lambda item: item.reading_order) for page in chosen_pages
    ]
    max_page_rows = max(len(rows) for rows in ordered_pages)
    for ordinal in range(max_page_rows):
        for page, rows in zip(chosen_pages, ordered_pages, strict=True):
            if ordinal >= len(rows):
                continue
            element = rows[ordinal]
            locator_id = str(element.locator.source_locator_id)
            if locator_id in seen_locators:
                continue
            remaining = _MAX_TOTAL_CHARS - total_chars
            if remaining <= 0 or len(fragments) >= _MAX_FRAGMENTS:
                return tuple(fragments)
            text = (element.raw_text or element.normalized_text).strip()[
                : min(_MAX_FRAGMENT_CHARS, remaining)
            ]
            if not text:
                continue
            fragments.append(
                {
                    "source_locator_id": locator_id,
                    "page": page,
                    "text": text,
                }
            )
            seen_locators.add(locator_id)
            total_chars += len(text)
    return tuple(fragments)


def _prompt(source_version_id: str, fragments: tuple[dict[str, object], ...]) -> str:
    return (
        "Определи вид загруженного документа фактического выполнения и указанную в нём "
        "работу. Используй только данные CONTEXT. Не считай название файла доказательством. "
        "Верни один JSON-объект без Markdown со всеми ключами: source_version_id, "
        "document_type, document_type_quote, document_type_locator_id, work_scope, "
        "work_quote, work_locator_id, uncertainty. document_type: "
        + ", ".join(sorted(_DOCUMENT_TYPES))
        + ". Для установленного вида и работы дай дословную непрерывную цитату и точный "
        "source_locator_id из CONTEXT. work_scope — краткое нормализованное название работы; "
        "если работа не установлена, три work-поля равны null. Если вид не установлен, "
        "document_type=unknown, оба document_type-поля null, uncertainty объясняет причину. "
        "Не объявляй подпись действительной и не придумывай дату, объём, выполнение работ "
        "или соответствие НТД.\nCONTEXT:\n"
        + json.dumps(
            {"source_version_id": source_version_id, "fragments": fragments},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
