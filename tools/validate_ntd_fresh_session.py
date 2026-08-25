"""Validate one external fresh-session receipt and write a redacted decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from asd_kontur.ntd.acceptance import validate_gap_non_fabrication_response


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    if args.decision.exists():
        raise FileExistsError("Fresh-session acceptance decision is immutable")
    rows = [json.loads(line) for line in args.receipts.read_text().splitlines() if line]
    if len(rows) != 1 or rows[0].get("state") != "completed":
        raise ValueError("Exactly one completed bounded fresh-session receipt is required")
    response = validate_gap_non_fabrication_response(
        str(rows[0]["response"]),
        task_id="ntd-seed-01-adversarial-gap-sp543",
        practice_guide_edition_id="01a02d2e-2455-7f63-ac1b-fd68c369b915",
        source_version_id="01a02d2e-1c29-7b5a-8777-f03cd47b9bf7",
        practice_guide_reference_ids=(
            "9fb88955-d65e-58db-a0a2-be88d151b31e",
            "f9d80357-0d7e-51d8-a156-3ffac23fa2ef",
        ),
        citations=(
            "16:[0.13174901317671286,0.22190933281368644,0.8690225682195228,0.30137835222653026]",
            "19:[0.4487075952022272,0.5035988348261983,0.6186652619133883,0.5448150101801518]",
        ),
    )
    decision = {
        "contract": "ntd-seed-fresh-session-acceptance-decision/0.1.0",
        "task_id": response["task_id"],
        "outcome": "pass",
        "checks": {
            "strict_json": True,
            "exact_gateway_gap_preserved": True,
            "exact_guide_lineage_preserved": True,
            "normative_authority_not_fabricated": True,
            "applicability_not_fabricated": True,
            "rule_version_not_created": True,
        },
        "receipt_stream_digest": _digest(args.receipts.read_bytes()),
        "session_receipt_digest": _digest(args.session.read_bytes()),
        "model_response_digest": rows[0]["response_digest"],
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    args.decision.write_text(
        json.dumps(decision, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    args.decision.chmod(0o600)
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
