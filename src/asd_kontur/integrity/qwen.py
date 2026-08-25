"""One bounded model-independent boundary smoke with an exact local BF16 profile."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .models import IntegrityFailure, canonical_digest, file_digest, write_immutable_json

SMOKE_CONTRACT = "system-integrity-qwen-smoke/1.9.0"


def smoke_context() -> dict[str, Any]:
    matrix = {
        "matrix_id": "33cc38b2-cf9a-58f7-bb69-ae663c742cd2",
        "version": 1,
        "work_package_ids": [
            "5bafaf18-ab1e-52b4-bcf5-2573b283a17c",
            "707ff4a3-a454-5404-ad5b-f0bf9fe6f07a",
            "29ae70a6-dbeb-5ee1-a1d8-c5f0b0af3059",
        ],
        "calculated_status": "knowledge_incomplete",
    }
    matrix_fingerprint = canonical_digest(matrix)
    context = {
        "contract_version": "1.9.0",
        "matrix": matrix,
        "matrix_fingerprint": matrix_fingerprint,
        "authority_layers": {
            "workspace_facts": [
                "project-definition:synthetic-multi-work:v1",
                "work-package:earthworks:v1",
                "work-package:reinforced-concrete:v1",
                "work-package:pipeline-installation:v1",
            ],
            "methodological_practice": ["practice-guide-edition:synthetic-pin:v1"],
            "normative_authority": [],
            "deterministic_rules": ["rule-version:synthetic-qualified:v1"],
        },
        "evidence_locators": [
            "synthetic-pd:page=7;section=PZ",
            "synthetic-estimate:line=1",
        ],
        "knowledge_gaps": ["official_ntd_subset_empty"],
        "fabrication_prohibited": True,
    }
    context["context_pack_fingerprint"] = canonical_digest(context)
    return context


def build_prompt(context: dict[str, Any]) -> str:
    expected = {
        "contract": SMOKE_CONTRACT,
        "context_pack_fingerprint": context["context_pack_fingerprint"],
        "matrix_fingerprint": context["matrix_fingerprint"],
        "referenced_identities": sorted(
            identity for values in context["authority_layers"].values() for identity in values
        ),
        "authority_layers": context["authority_layers"],
        "evidence_locators": context["evidence_locators"],
        "calculated_status": "knowledge_incomplete",
        "knowledge_gaps": ["official_ntd_subset_empty"],
        "fabrication_prohibited": True,
    }
    return (
        "You are executing a deterministic ASD-KONTUR boundary qualification. "
        "Return exactly one syntactically valid JSON object and no markdown, commentary, "
        "or extra keys. "
        "Copy only identities, locators, statuses, and gaps present in the supplied ContextPack. "
        "Do not invent a normative provision. Preserve the separation of workspace facts, "
        "methodological practice, normative authority, and deterministic rules. "
        "The exact required output is defined by this compact schema/example; reproduce its values "
        "from the ContextPack without changing order-insensitive identity sets.\n"
        f"CONTEXT_PACK={json.dumps(context, ensure_ascii=False, sort_keys=True)}\n"
        f"REQUIRED_OUTPUT_SHAPE={json.dumps(expected, ensure_ascii=False, sort_keys=True)}"
    )


def validate_response(raw: str, context: dict[str, Any]) -> dict[str, Any]:
    if raw != raw.strip():
        raise IntegrityFailure("MODEL_RESPONSE_INTEGRITY_FAILED", "response has outer whitespace")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise IntegrityFailure(
            "MODEL_RESPONSE_INTEGRITY_FAILED",
            "response is not strict JSON",
            evidence={"line": error.lineno, "column": error.colno},
        ) from error
    if not isinstance(value, dict):
        raise IntegrityFailure("MODEL_RESPONSE_INTEGRITY_FAILED", "response must be an object")
    required_keys = {
        "contract",
        "context_pack_fingerprint",
        "matrix_fingerprint",
        "referenced_identities",
        "authority_layers",
        "evidence_locators",
        "calculated_status",
        "knowledge_gaps",
        "fabrication_prohibited",
    }
    if set(value) != required_keys:
        raise IntegrityFailure(
            "MODEL_RESPONSE_INTEGRITY_FAILED",
            "response keys differ from the exact contract",
            evidence={"keys": sorted(value)},
        )
    expected_layers = context["authority_layers"]
    expected_identities = sorted(
        identity for values in expected_layers.values() for identity in values
    )
    invariants = {
        "contract": value["contract"] == SMOKE_CONTRACT,
        "context_pack_fingerprint": value["context_pack_fingerprint"]
        == context["context_pack_fingerprint"],
        "matrix_fingerprint": value["matrix_fingerprint"] == context["matrix_fingerprint"],
        "referenced_identities": sorted(value["referenced_identities"]) == expected_identities,
        "authority_layers": value["authority_layers"] == expected_layers,
        "evidence_locators": value["evidence_locators"] == context["evidence_locators"],
        "calculated_status": value["calculated_status"] == "knowledge_incomplete",
        "knowledge_gaps": value["knowledge_gaps"] == ["official_ntd_subset_empty"],
        "fabrication_prohibited": value["fabrication_prohibited"] is True,
        "normative_authority_empty": value["authority_layers"]["normative_authority"] == [],
    }
    failed = sorted(key for key, passed in invariants.items() if not passed)
    if failed:
        raise IntegrityFailure(
            "MODEL_STRUCTURAL_VALIDATION_FAILED",
            "model output violated deterministic structural invariants",
            evidence={"failed_invariants": failed},
        )
    return value


def run_bf16_smoke(
    *,
    repository_root: Path,
    receipt_directory: Path,
    runtime_python: Path,
    model_path: Path,
    exact_model_digest: str,
) -> dict[str, Any]:
    if not runtime_python.is_file() or not os.access(runtime_python, os.X_OK):
        raise IntegrityFailure("MLX_RUNTIME_UNAVAILABLE", "exact MLX runtime is unavailable")
    if not model_path.is_dir():
        raise IntegrityFailure("MODEL_PROFILE_UNAVAILABLE", "exact BF16 model path is unavailable")
    context = smoke_context()
    request_path = receipt_directory / "qwen-request.json"
    profile_path = receipt_directory / "qwen-profile.json"
    raw_receipts_path = receipt_directory / "qwen-raw-receipts.jsonl"
    session_path = receipt_directory / "qwen-session.json"
    write_immutable_json(
        request_path,
        {
            "jobs": [
                {
                    "job_id": "system-integrity-boundary-smoke",
                    "prompt": build_prompt(context),
                    "image_paths": [],
                }
            ]
        },
    )
    profile = {
        "contract": "local-mlx-execution-profile/0.2.0",
        "provider": "local-mlx",
        "model_identity": "Qwen3.8-27B",
        "model_revision": "Qwen3.8-27B-MLX-bf16",
        "model_digest": exact_model_digest,
        "quantization": "bf16",
        "execution_profile": "system-integrity-bf16-smoke-v0.1",
        "prompt_version": "system-integrity-boundary-v0.1",
        "schema_version": "system-integrity-qwen-smoke/1.9.0",
        "verification_policy_version": "system-integrity-structural-v0.1",
        "deterministic_decoding": True,
        "temperature": 0,
    }
    write_immutable_json(profile_path, profile)
    environment = dict(os.environ)
    runner_path = repository_root / "src/asd_kontur/practice_guidance/qwen_session_runner.py"
    if not runner_path.is_file():
        raise IntegrityFailure("MLX_RUNNER_UNAVAILABLE", "standalone MLX runner is unavailable")
    completed = subprocess.run(
        [
            str(runtime_python),
            str(runner_path),
            "--model",
            str(model_path),
            "--request",
            str(request_path),
            "--receipts",
            str(raw_receipts_path),
            "--max-tokens",
            "700",
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
        timeout=1200,
        env=environment,
    )
    process_log_path = receipt_directory / "qwen-process.log"
    process_log_descriptor = os.open(
        process_log_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(process_log_descriptor, "w", encoding="utf-8") as process_log:
        process_log.write(completed.stdout)
        process_log.write("\n[stderr]\n")
        process_log.write(completed.stderr)
        process_log.flush()
        os.fsync(process_log.fileno())
    if completed.returncode:
        raise IntegrityFailure(
            "BF16_SMOKE_EXECUTION_FAILED",
            "bounded BF16 model process failed",
            evidence={
                "returncode": completed.returncode,
                "process_log_digest": file_digest(process_log_path),
            },
        )
    lines = raw_receipts_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise IntegrityFailure("MODEL_RECEIPT_RECONCILIATION_FAILED", "expected one model receipt")
    receipt = json.loads(lines[0])
    if receipt.get("state") != "completed" or receipt.get("attempt_number") != 1:
        raise IntegrityFailure(
            "MODEL_RECEIPT_RECONCILIATION_FAILED", "model attempt was not one-shot complete"
        )
    validated = validate_response(str(receipt["response"]), context)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    if session.get("temperature") != 0 or session.get("model_digest") != exact_model_digest:
        raise IntegrityFailure("MODEL_PROFILE_MISMATCH", "session did not use the exact profile")
    if session.get("competing_heavy_processes"):
        raise IntegrityFailure(
            "HEAVY_MODEL_SESSION_ALREADY_ACTIVE", "competing MLX process detected"
        )
    return {
        "status": "pass",
        "contract": SMOKE_CONTRACT,
        "context_pack_fingerprint": context["context_pack_fingerprint"],
        "matrix_fingerprint": context["matrix_fingerprint"],
        "response_structural_fingerprint": canonical_digest(validated),
        "request_digest": receipt["request_digest"],
        "response_digest": receipt["response_digest"],
        "session_receipt_digest": file_digest(session_path),
        "model_digest": exact_model_digest,
        "runtime": session["runtime"],
        "temperature": 0,
    }
