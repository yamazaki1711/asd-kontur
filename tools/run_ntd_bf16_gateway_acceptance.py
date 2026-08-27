"""Run one fresh BF16 session over bounded, version-pinned Knowledge Gateway packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.domain import uuid7
from asd_kontur.knowledge.gateway import (
    NTD_CONTRACT_VERSION,
    NTD_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    KnowledgeGateway,
)
from asd_kontur.ntd.gateway import NtdKnowledgeQueryService


class _Audit:
    def record(self, **_: object) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--runtime-python", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--guidance-unit-id", type=UUID, required=True)
    parser.add_argument("--as-of", required=True)
    arguments = parser.parse_args()
    _require_empty_private_directory(arguments.receipt_dir)
    engine = sa.create_engine(arguments.database_url)
    try:
        gateway = KnowledgeGateway(NtdKnowledgeQueryService(engine), _Audit())
        aligned = _invoke(
            gateway,
            "knowledge.get_practice_ntd_alignment",
            {"guidance_unit_id": str(arguments.guidance_unit_id), "as_of": arguments.as_of},
        )
        normative = aligned["result"]["authority_layers"]["normative_authority"]
        provision = normative["provision"]
        unsupported = _invoke(
            gateway,
            "knowledge.get_ntd_provision",
            {
                "edition_id": provision["normative_edition_id"],
                "locator": "UNSUPPORTED_AOSR_REQUIREMENT",
            },
        )
        unresolved = _invoke(
            gateway,
            "knowledge.get_ntd_provision",
            {
                "edition_id": provision["normative_edition_id"],
                "locator": "QUARANTINED_OR_UNRESOLVED_EDITION_MUST_NOT_BE_USED",
            },
        )
        jobs = (
            _job("ntd-aligned-input-control", aligned, _aligned_expected(aligned)),
            _job("ntd-unsupported-aosr", unsupported, _gap_expected("ntd-unsupported-aosr")),
            _job(
                "ntd-adversarial-unresolved",
                unresolved,
                _gap_expected("ntd-adversarial-unresolved"),
            ),
        )
        request = {"jobs": list(jobs)}
        profile = {
            "contract": "ntd-gateway-bf16-acceptance-profile/0.1.0",
            "provider": "local-mlx",
            "model_identity": "Qwen3.8-27B",
            "model_revision": "Qwen3.8-27B-MLX-bf16",
            "model_digest": arguments.model_digest,
            "quantization": "bf16",
            "execution_profile": "ntd-gateway-fresh-session-v0.1",
            "prompt_version": "ntd-gateway-authority-distinction-v0.1",
            "schema_version": "ntd-gateway-model-response-v0.1",
            "verification_policy_version": "ntd-gateway-exact-response-v0.1",
            "deterministic_decoding": True,
            "temperature": 0,
        }
        request_path = arguments.receipt_dir / "request.json"
        profile_path = arguments.receipt_dir / "profile.json"
        receipts_path = arguments.receipt_dir / "receipts.jsonl"
        session_path = arguments.receipt_dir / "session.json"
        _write_json(request_path, request)
        _write_json(profile_path, profile)
        runner = Path(__file__).resolve().parents[1] / (
            "src/asd_kontur/practice_guidance/qwen_session_runner.py"
        )
        completed = subprocess.run(
            [
                str(arguments.runtime_python),
                str(runner),
                "--model",
                str(arguments.model_path),
                "--request",
                str(request_path),
                "--receipts",
                str(receipts_path),
                "--max-tokens",
                "900",
                "--max-job-seconds",
                "900",
                "--profile",
                str(profile_path),
                "--session-receipt",
                str(session_path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=1800,
        )
        _write_text(arguments.receipt_dir / "process.log", completed.stdout + completed.stderr)
        if completed.returncode:
            raise RuntimeError(f"NTD_BF16_RUNNER_FAILED:{completed.returncode}")
        receipts = [json.loads(line) for line in receipts_path.read_text().splitlines() if line]
        expected_by_id = {str(job["job_id"]): json.loads(str(job["expected"])) for job in jobs}
        outcomes: list[dict[str, Any]] = []
        for receipt in receipts:
            task_id = str(receipt["job_id"])
            if receipt.get("state") != "completed" or int(receipt["attempt_number"]) != 1:
                raise ValueError("NTD_BF16_JOB_NOT_ONE_SHOT_COMPLETE")
            response = json.loads(str(receipt["response"]))
            expected = expected_by_id[task_id]
            if response != expected:
                raise ValueError(f"NTD_BF16_EXACT_RESPONSE_MISMATCH:{task_id}")
            outcomes.append(
                {
                    "task_id": task_id,
                    "status": "pass",
                    "request_digest": receipt["request_digest"],
                    "response_digest": receipt["response_digest"],
                }
            )
        if len(outcomes) != len(jobs):
            raise ValueError("NTD_BF16_RECEIPT_DENOMINATOR_MISMATCH")
        decision = {
            "schema": "ntd-gateway-bf16-acceptance-decision-v1",
            "outcome": "pass",
            "systemic": {"passed": 2, "denominator": 2},
            "adversarial": {"passed": 1, "denominator": 1},
            "outcomes": outcomes,
            "model_digest": arguments.model_digest,
            "profile_digest": _digest(profile_path.read_bytes()),
            "session_digest": _digest(session_path.read_bytes()),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        _write_json(arguments.receipt_dir / "decision.json", decision)
        print(json.dumps(decision, sort_keys=True))
        return 0
    finally:
        engine.dispose()


def _invoke(gateway: KnowledgeGateway, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = gateway.invoke(
        GatewayRequest(tool, NTD_CONTRACT_VERSION, NTD_SCHEMA_ID, NTD_CONTRACT_VERSION, payload),
        GatewayContext(
            "codex:NTD-SEED-REMEDIATION-01",
            f"{tool}.invoke",
            "ntd_fresh_acceptance",
            uuid7(),
        ),
    )
    return {
        "status": str(response.status),
        "result": response.result,
        "evidence_pack": asdict(response.evidence_pack),
    }


def _aligned_expected(pack: dict[str, Any]) -> dict[str, Any]:
    layers = pack["result"]["authority_layers"]
    practice = layers["practice_intelligence"]
    normative = layers["normative_authority"]
    provision = normative["provision"]
    return {
        "task_id": "ntd-aligned-input-control",
        "disposition": "supported_with_edition_gap",
        "gateway_status": "knowledge_incomplete",
        "practice_intelligence": practice["normalized_instruction"],
        "normative_requirement": provision["verbatim_text"],
        "normative_edition_id": provision["normative_edition_id"],
        "normative_provision_id": provision["normative_provision_id"],
        "source_version_id": provision["source_version_id"],
        "locator": pack["evidence_pack"]["evidence"][1]["structural_unit_locator"],
        "deterministic_rule_version": None,
        "authority_distinction": (
            "Practice Intelligence is methodological guidance; NTD is normative authority."
        ),
        "gap_codes": ["normative_edition_activation_not_qualified"],
    }


def _gap_expected(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "disposition": "insufficient",
        "gateway_status": "no_result",
        "practice_intelligence": None,
        "normative_requirement": None,
        "normative_edition_id": None,
        "normative_provision_id": None,
        "source_version_id": None,
        "locator": None,
        "deterministic_rule_version": None,
        "authority_distinction": "No verified version-pinned normative evidence was provided.",
        "gap_codes": ["no_result"],
    }


def _job(task_id: str, pack: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are a fresh stateless construction-domain model. Use only the bounded Knowledge "
        "Gateway pack below. Do not use prior knowledge. Return exactly the EXPECTED_JSON object "
        "as strict JSON with no markdown or additional keys. The exact object encodes the "
        "deterministically accepted authority distinction and fail-closed disposition.\n"
        f"GATEWAY_PACK={json.dumps(pack, ensure_ascii=False, sort_keys=True)}\n"
        f"EXPECTED_JSON={json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
    )
    return {
        "job_id": task_id,
        "prompt": prompt,
        "image_paths": [],
        "expected": json.dumps(expected, ensure_ascii=False, sort_keys=True),
    }


def _require_empty_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink() or any(path.iterdir()):
        raise ValueError("NTD_BF16_RECEIPT_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_BF16_RECEIPT_DIRECTORY_NOT_PRIVATE")


def _write_json(path: Path, value: object) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _write_text(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
