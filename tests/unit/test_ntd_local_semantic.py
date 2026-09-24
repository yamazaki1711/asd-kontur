from __future__ import annotations

import json

import pytest

from asd_kontur.document_understanding.qwen_semantic import QwenSemanticFailure
from asd_kontur.ntd.local_semantic import _parse_semantics


def _valid() -> dict[str, object]:
    return {
        "provision_kind": "clause",
        "normalized_proposition": {"text": "Исполнитель должен вести журнал."},
        "subject": {"kind": "исполнитель"},
        "predicate": {"action": "вести"},
        "object_value": {"document": "журнал"},
        "modality": "mandatory",
        "conditions": {},
        "exclusions": {},
        "applicability": {"work": "монолитные работы"},
        "units_dimensions": {},
        "referenced_designations": [],
        "uncertainty_codes": [],
    }


def test_local_ntd_semantics_requires_complete_schema() -> None:
    value = _valid()
    value.pop("conditions")

    with pytest.raises(QwenSemanticFailure, match="invalid_shape"):
        _parse_semantics(json.dumps(value, ensure_ascii=False))


def test_local_ntd_semantics_accepts_bounded_candidate() -> None:
    value = _valid()

    assert _parse_semantics(json.dumps(value, ensure_ascii=False)) == value


def test_local_ntd_semantics_rejects_unqualified_modality() -> None:
    value = _valid()
    value["modality"] = "always_true"

    with pytest.raises(QwenSemanticFailure, match="invalid_enum"):
        _parse_semantics(json.dumps(value, ensure_ascii=False))
