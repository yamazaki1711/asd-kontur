from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from asd_kontur.knowledge.gateway import ASSISTANT_TOOLS, HARNESS_TOOLS


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_professional_assistant_contract_pack_is_exact_and_valid(
    repository_root: Path,
) -> None:
    root = repository_root / "contracts" / "v2.8"
    registry = _load(root / "registry.json")
    for schema_entry in registry["schemas"]:
        schema_path = root / schema_entry["path"]
        assert (
            "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
            == schema_entry["digest"]
        )
        Draft202012Validator.check_schema(_load(schema_path))
    schema_entry = registry["schemas"][0]
    schema_path = root / schema_entry["path"]
    schema = _load(schema_path)
    fixture = _load(root / "fixtures" / "valid" / "professional-assistant-delta.json")
    Draft202012Validator(schema).validate(fixture)
    assert fixture["assistant"]["implementation_count"] == 1
    assert fixture["assistant"]["modes"] == ["Tender", "Support", "Audit", "Restoration"]
    assert fixture["memory"]["practice_units"] == 21_105
    assert fixture["memory"]["verified_normative_provisions"] == 1_294
    assert fixture["assistant"]["gateway_tool_count"] == 14
    assert fixture["assistant"]["max_search_steps"] == 4
    assert fixture["assistant"]["fixed_source_quota"] is False
    assert fixture["construction_consultant_quality_ready"] is False
    assert fixture["domain_harness_ready"] is False
    assert fixture["external_acceptance"] == "pending"
    assistant_tool = _load(root / "schemas" / "professional-assistant-tool.schema.json")
    Draft202012Validator(assistant_tool).validate(
        {
            "tool": "consultant.search_ntd",
            "mode": "Support",
            "arguments": {"query": "контроль бетона", "limit": 3},
        }
    )
    assert all(
        name.startswith("consultant.")
        for name in ASSISTANT_TOOLS
        if name != "knowledge.get_professional_assistant_context"
    )
    assert not ASSISTANT_TOOLS.intersection(HARNESS_TOOLS)
