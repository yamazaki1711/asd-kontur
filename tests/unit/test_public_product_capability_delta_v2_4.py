from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_public_product_delta_is_additive_and_honest(repository_root: Path) -> None:
    root = repository_root / "contracts" / "v2.4"
    schema_path = root / "schemas" / "capability-readiness-delta.schema.json"
    schema = _load(schema_path)
    fixture = _load(root / "fixtures" / "valid" / "capability-readiness-delta.json")
    registry = _load(root / "registry.json")
    Draft202012Validator(schema).validate(fixture)

    assert fixture["denominator"] == 143
    assert sum(fixture["effective_distribution"].values()) == 143
    assert fixture["trial_ready"] is False
    assert fixture["oks_ready"] is False
    assert fixture["product_ready"] is False
    deltas = fixture["readiness_delta"]
    ids = [item["capability_id"] for item in deltas]
    assert len(ids) == len(set(ids)) == 18
    assert all(item["current"] == "PARTIAL" for item in deltas)
    assert "field.secure-android-client" not in ids

    base = _load(repository_root / "contracts/v2.0/fixtures/valid/product-capability-registry.json")
    base_ids = {item["capability_id"] for item in base["capabilities"]}
    assert set(ids) <= base_ids

    effective = {item["capability_id"]: item["current_readiness"] for item in base["capabilities"]}
    spine = _load(
        repository_root / "contracts/v2.1/fixtures/valid/product-spine-contract-fixture.json"
    )
    for item in spine["capability_readiness_delta"]:
        assert effective[item["capability_id"]] == item["prior"]
        effective[item["capability_id"]] = item["current"]
    extension = _load(
        repository_root / "contracts/v2.3/fixtures/valid/capability-registry-extension.json"
    )
    for item in extension["additions"]:
        effective[item["capability_id"]] = item["current_readiness"]
    assert Counter(effective.values()) == Counter(extension["readiness_distribution"])

    for item in deltas:
        assert effective[item["capability_id"]] == item["prior"]
        effective[item["capability_id"]] = item["current"]
    assert Counter(effective.values()) == Counter(fixture["effective_distribution"])

    expected_digest = "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert registry["schemas"][0]["digest"] == expected_digest
