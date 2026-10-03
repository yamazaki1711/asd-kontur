# ruff: noqa: RUF001 -- exact Russian construction terms are intentional.

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from asd_kontur.ntd.search_corpus import normalize_designation


class QueryScope(StrEnum):
    EXACT_DESIGNATION = "exact_designation"
    PLATFORM_NTD = "platform_ntd"
    WORKSPACE = "workspace"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class NtdQueryRoute:
    scope: QueryScope
    explicit_designations: tuple[str, ...]
    reason: str


_DESIGNATION_RE = re.compile(
    r"\b(ГОСТ\s+Р|ГОСТ|СП|приказ|инструкция)\s*№?\s*"
    r"([0-9]+(?:[.\-/][0-9A-ZА-ЯЁа-яё]+)*)",
    re.IGNORECASE,
)
_WORKSPACE_OBJECT_CUES = (
    "текущего объекта",
    "текущем объекте",
    "этого объекта",
    "этом объекте",
    "демонстрационного объекта",
    "конкретной захватки",
    "партии",
)
_WORKSPACE_FACT_CUES = (
    "указан",
    "выдан",
    "подписал",
    "результат",
    "паспорт",
    "класс",
    "состояние",
    "статус",
)
_PLATFORM_CUES = (
    "нтд",
    "норм",
    "требован",
    "технолог",
    "контрол",
    "приёмк",
    "приемк",
    "методик",
    "стандарт",
)


def route_consultant_query(question: str) -> NtdQueryRoute:
    text = " ".join(question.split())
    if not text:
        raise ValueError("ntd_query_empty")
    lowered = text.casefold()
    designations = _extract_designations(text)
    has_workspace_reference = any(cue in lowered for cue in _WORKSPACE_OBJECT_CUES)
    has_workspace_fact = any(cue in lowered for cue in _WORKSPACE_FACT_CUES)
    has_platform_context = bool(designations) or any(cue in lowered for cue in _PLATFORM_CUES)
    if has_workspace_reference and has_platform_context:
        scope = QueryScope.MIXED
        reason = "workspace_and_platform_context"
    elif has_workspace_reference and has_workspace_fact:
        scope = QueryScope.WORKSPACE
        reason = "workspace_factual_request"
    elif designations:
        scope = QueryScope.EXACT_DESIGNATION
        reason = "explicit_designation"
    else:
        scope = QueryScope.PLATFORM_NTD
        reason = "platform_construction_default"
    return NtdQueryRoute(scope, designations, reason)


def _extract_designations(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for prefix, identifier in _DESIGNATION_RE.findall(text):
        normalized = normalize_designation(f"{prefix} {identifier}")
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)
