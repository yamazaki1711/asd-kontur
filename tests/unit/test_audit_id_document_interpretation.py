"""Source-bound ID classification is a candidate, never an audit conclusion."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from asd_kontur.audit.qwen_id_document import (
    _bounded_fragments,
    parse_id_document_interpretation,
)
from asd_kontur.document_understanding.models import ExactLocator, LayoutElement
from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure

SOURCE = UUID("10000000-0000-4000-8000-000000000001")
DOCUMENT = UUID("20000000-0000-4000-8000-000000000001")
LOCATOR = UUID("30000000-0000-4000-8000-000000000001")


def _fragments(source: UUID = SOURCE) -> tuple[dict[str, object], ...]:
    element = LayoutElement(
        UUID("40000000-0000-4000-8000-000000000001"),
        "native_text",
        "Акт освидетельствования скрытых работ. Монтаж кабельной линии.",
        "Акт освидетельствования скрытых работ. Монтаж кабельной линии.",
        1,
        ExactLocator(
            source,
            LOCATOR,
            DOCUMENT,
            1,
            1,
            (0.0, 0.0, 1.0, 1.0),
            "sha256:" + "a" * 64,
        ),
    )
    return _bounded_fragments((element,), source_version_id=str(source))


def _answer(**changes: object) -> str:
    value: dict[str, object] = {
        "source_version_id": str(SOURCE),
        "document_type": "concealed_work_act",
        "document_type_quote": "Акт освидетельствования скрытых работ",
        "document_type_locator_id": str(LOCATOR),
        "work_scope": "монтаж кабельной линии",
        "work_quote": "Монтаж кабельной линии",
        "work_locator_id": str(LOCATOR),
        "uncertainty": None,
    }
    value.update(changes)
    return json.dumps(value, ensure_ascii=False)


def test_exact_source_quotes_are_accepted_without_claiming_audit_completion() -> None:
    result = parse_id_document_interpretation(
        _answer(), source_version_id=str(SOURCE), fragments=_fragments()
    )
    assert result["document_type"] == "concealed_work_act"
    assert result["work_scope"] == "монтаж кабельной линии"


@pytest.mark.parametrize(
    "changed",
    [
        {"source_version_id": "90000000-0000-4000-8000-000000000001"},
        {"document_type_quote": "Подписанный акт"},
        {"work_locator_id": "90000000-0000-4000-8000-000000000001"},
        {"document_type": "not_a_real_type"},
        {"work_scope": None},
    ],
)
def test_foreign_or_invented_evidence_is_rejected(changed: dict[str, object]) -> None:
    with pytest.raises(QwenSemanticFailure):
        parse_id_document_interpretation(
            _answer(**changed), source_version_id=str(SOURCE), fragments=_fragments()
        )


def test_unknown_is_explicit_and_not_forced_into_a_form() -> None:
    result = parse_id_document_interpretation(
        _answer(
            document_type="unknown",
            document_type_quote=None,
            document_type_locator_id=None,
            work_scope=None,
            work_quote=None,
            work_locator_id=None,
            uncertainty="Document type cannot be established from this excerpt",
        ),
        source_version_id=str(SOURCE),
        fragments=_fragments(),
    )
    assert result["document_type"] == "unknown"
