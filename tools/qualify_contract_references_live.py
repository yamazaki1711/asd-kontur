"""Bounded, project-independent live Qwen qualification of contract references.

This does not create a workspace or advance a production queue. It exercises
the same validated task contract used by the supervised document worker.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.tender.qwen_contract_references import (
    CONTRACT_REFERENCE_PROFILE,
    QwenContractReferenceReviewer,
)


def _health(endpoint: str) -> dict[str, object]:
    origin = endpoint.removesuffix("/generate")
    request = urllib.request.Request(origin + "/health", method="GET")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=5
    ) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("qwen_health_invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8790/generate")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = _health(args.endpoint)
    if before.get("status") != "QWEN_READY_IDLE":
        raise RuntimeError("qwen_not_idle_for_bounded_qualification")

    reviewer = QwenContractReferenceReviewer(args.endpoint, timeout_seconds=180)
    cases = (
        (
            "unresolved_attachment",
            "Appendix C sets the delivery timetable for the contractor.",
            ("Draft contract.txt",),
            "unresolved",
        ),
        (
            "matched_attachment",
            "Appendix C sets the delivery timetable for the contractor.",
            ("Draft contract.txt", "Appendix C - Delivery timetable.txt"),
            "matched",
        ),
        (
            "no_attachment_reference",
            "The contractor shall send notice within five business days.",
            ("Draft contract.txt",),
            "none",
        ),
    )
    outcomes: list[dict[str, object]] = []
    for name, source_text, source_names, expected in cases:
        fragments = [{"source_locator_id": f"synthetic-{name}", "page": 1, "text": source_text}]
        sources = [
            {"source_version_id": f"synthetic-source-{i}", "safe_display_name": title}
            for i, title in enumerate(source_names, start=1)
        ]
        started = time.monotonic()
        result = reviewer.review(fragments, admitted_sources=sources)
        references = result["references"]
        assert isinstance(references, list)
        decisions = [str(item["match_decision"]) for item in references]
        passed = decisions == ([] if expected == "none" else [expected])
        outcomes.append(
            {
                "case": name,
                "input_digest": semantic_digest({"fragments": fragments, "sources": sources}),
                "expected_decision": expected,
                "observed_decisions": decisions,
                "passed": passed,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "result": result,
            }
        )

    after = _health(args.endpoint)
    report: dict[str, object] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "task_profile": CONTRACT_REFERENCE_PROFILE,
        "model_before": before,
        "model_after": after,
        "cases": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
    }
    report["fingerprint"] = semantic_digest(report)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "cases": len(outcomes),
                "fingerprint": report["fingerprint"],
                "output": str(args.output),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
