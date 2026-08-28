from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
PACK = ROOT / "contracts" / "v2.5"


def test_industrial_intake_project_understanding_delta_is_exact_and_valid() -> None:
    registry = json.loads((PACK / "registry.json").read_text(encoding="utf-8"))
    schema_entry = registry["schemas"][0]
    schema_path = PACK / schema_entry["path"]
    schema_bytes = schema_path.read_bytes()
    assert "sha256:" + hashlib.sha256(schema_bytes).hexdigest() == schema_entry["digest"]
    schema = json.loads(schema_bytes)
    fixture = json.loads((PACK / registry["fixtures"]["valid"][0]).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(fixture)
    identities = [item["capability_id"] for item in fixture["capabilities"]]
    assert len(identities) == len(set(identities)) == 29
    assert sum(value for value in fixture["effective_distribution"].values()) == 143
    assert sum(item.startswith("intake.") for item in identities) == 17
    assert sum(item.startswith("project-understanding.") for item in identities) == 12
    assert fixture["trial_ready"] is False
    assert fixture["oks_ready"] is False
    assert fixture["product_ready"] is False


def test_qualified_synthetic_corpus_is_reproducible(tmp_path: Path) -> None:
    manifests = []
    for index in (1, 2):
        target = tmp_path / f"corpus-{index}"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/build_industrial_intake_synthetic_corpus.py"),
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        manifests.append(json.loads((target / "corpus-manifest.json").read_text(encoding="utf-8")))
    assert manifests[0]["logical_fingerprint"] == manifests[1]["logical_fingerprint"]
    assert manifests[0]["files"] == manifests[1]["files"]
