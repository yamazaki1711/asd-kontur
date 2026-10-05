from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from asd_kontur.assistant.reasoning import TOOL_NAMES
from asd_kontur.knowledge.gateway import ASSISTANT_TOOLS, HARNESS_TOOLS


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_ntd_consultant_contract_pack_is_exact_and_separates_authority(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.9"
    registry = _load(root / "registry.json")
    for entry in registry["schemas"]:
        path = root / entry["path"]
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == entry["digest"]
        Draft202012Validator.check_schema(_load(path))
    corpus_schema = _load(root / "schemas" / "ntd-consultant-corpus.schema.json")
    corpus = _load(root / "fixtures" / "valid" / "ntd-consultant-corpus.json")
    Draft202012Validator(corpus_schema).validate(corpus)
    assert corpus["sp70"] == {
        "designation": "СП 70.13330.2012",
        "inventory_outcome": "document_present_searchable",
        "verified_provisions": 0,
        "edition_currency": "not_checked",
    }
    tool_schema = _load(root / "schemas" / "professional-assistant-tool.schema.json")
    assert set(tool_schema["properties"]["tool"]["enum"]) == TOOL_NAMES
    assert TOOL_NAMES <= ASSISTANT_TOOLS
    assert not ASSISTANT_TOOLS.intersection(HARNESS_TOOLS)
    assert corpus["construction_consultant_quality_ready"] is False
