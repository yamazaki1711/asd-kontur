"""Bounded live-model check of the reusable contract-analysis task contract.

This creates no workspace, touches no production queue, and contains only
synthetic changed-party clauses. It is not full application acceptance.
"""

# ruff: noqa: RUF001 -- Synthetic Russian contract clauses intentionally contain Cyrillic.

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.tender.qwen_contract_analysis import (
    CONTRACT_ANALYSIS_PROFILE,
    QwenContractAnalyzer,
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

    cases = (
        (
            "customer_controlled_payment",
            "7.4. Заказчик оплачивает принятые работы после поступления средств от инвестора. "
            "До поступления указанных средств обязанность Заказчика по оплате не возникает.",
            True,
        ),
        (
            "ordinary_warranty",
            "9.2. Подрядчик устраняет за свой счёт недостатки работ, возникшие по его вине, "
            "в течение гарантийного срока 24 месяца со дня приёмки.",
            False,
        ),
    )
    analyzer = QwenContractAnalyzer(args.endpoint, timeout_seconds=240)
    outcomes: list[dict[str, object]] = []
    for name, source_text, expect_risk in cases:
        fragments = [{"source_locator_id": f"synthetic-{name}", "page": 1, "text": source_text}]
        started = time.monotonic()
        result = analyzer.analyze(fragments)
        clauses = result["clauses"]
        risks = result["risks"]
        assert isinstance(clauses, list) and isinstance(risks, list)
        passed = bool(clauses) and bool(risks) == expect_risk
        outcomes.append(
            {
                "case": name,
                "input_digest": semantic_digest(fragments),
                "expected_risk": expect_risk,
                "observed_risk_count": len(risks),
                "observed_clause_count": len(clauses),
                "passed": passed,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "result": result,
            }
        )

    report: dict[str, object] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "task_profile": CONTRACT_ANALYSIS_PROFILE,
        "model_before": before,
        "model_after": _health(args.endpoint),
        "cases": outcomes,
        "passed": all(bool(item["passed"]) for item in outcomes),
        "limitation": (
            "Task-contract qualification only; no workspace or autonomous pipeline claim."
        ),
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
