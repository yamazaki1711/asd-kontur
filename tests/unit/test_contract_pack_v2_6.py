from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
PACK = ROOT / "contracts" / "v2.6"


def test_pilot_usable_e2e_delta_is_exact_and_valid() -> None:
    registry = json.loads((PACK / "registry.json").read_text(encoding="utf-8"))
    schema_entry = registry["schemas"][0]
    schema_bytes = (PACK / schema_entry["path"]).read_bytes()
    assert "sha256:" + hashlib.sha256(schema_bytes).hexdigest() == schema_entry["digest"]
    schema = json.loads(schema_bytes)
    fixture = json.loads((PACK / registry["fixtures"]["valid"][0]).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(fixture)
    assert fixture["product_denominator"] == 143
    assert len(fixture["mode_results"]) == 4
    assert len(fixture["exports"]) == 9
    assert fixture["trial_readiness"]["state"] == "pending_external_acceptance"
    assert len(fixture["trial_readiness"]["required_criteria"]) == 11
    assert fixture["oks_ready"] is False
    assert fixture["product_ready"] is False
