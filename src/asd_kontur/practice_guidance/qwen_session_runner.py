"""Isolated MLX session runner used by the platform guide ingestion service.

The canonical application does not import MLX. This module is launched with a
configured development runtime and keeps one model load for a bounded job
manifest. Request/result files live in external staging and are never domain
contracts or Git artifacts.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _battery_temperature_celsius() -> float | None:
    completed = subprocess.run(
        ["ioreg", "-r", "-c", "AppleSmartBattery", "-l"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    match = re.search(r'"Temperature"\s*=\s*(\d+)', completed.stdout)
    if match is None:
        return None
    return int(match.group(1)) / 100


def _thermal_warning() -> bool:
    completed = subprocess.run(
        ["pmset", "-g", "therm"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    output = completed.stdout + completed.stderr
    return "No thermal warning level has been recorded" not in output


def _thermal_gate(max_battery_celsius: float) -> dict[str, object]:
    battery = _battery_temperature_celsius()
    warning = _thermal_warning()
    if warning or (battery is not None and battery >= max_battery_celsius):
        raise RuntimeError("THERMAL_GUARD_BLOCKED")
    return {"thermal_warning": warning, "battery_celsius": battery}


def _read_jobs(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("A bounded runner request requires a non-empty jobs list")
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Every runner job must be an object")
        if not isinstance(job.get("job_id"), str) or not isinstance(job.get("prompt"), str):
            raise ValueError("Runner job identity and prompt are required")
        images = job.get("image_paths", [])
        if not isinstance(images, list) or not all(isinstance(value, str) for value in images):
            raise ValueError("Runner image paths must be an explicit string list")
    return jobs


def _completed_job_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("state") == "completed":
            completed.add(str(value.get("job_id")))
    return completed


def _attempt_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("job_id"), str):
            job_id = str(value["job_id"])
            counts[job_id] = counts.get(job_id, 0) + 1
    return counts


def _competing_heavy_processes() -> list[dict[str, object]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss=,command="],
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )
    rows: list[tuple[int, int, int, str]] = []
    parents: dict[int, int] = {}
    for line in completed.stdout.splitlines():
        fields = line.strip().split(maxsplit=3)
        if len(fields) != 4:
            continue
        pid, parent_pid, rss, command = (
            int(fields[0]),
            int(fields[1]),
            int(fields[2]),
            fields[3],
        )
        rows.append((pid, parent_pid, rss, command))
        parents[pid] = parent_pid
    ancestors = {os.getpid()}
    ancestor = os.getpid()
    while ancestor in parents and parents[ancestor] not in ancestors:
        ancestor = parents[ancestor]
        ancestors.add(ancestor)
    competing: list[dict[str, object]] = []
    markers = ("mlx_vlm.server", "qwen_session_runner.py", "_mlx_vlm_")
    for pid, _parent_pid, rss, command in rows:
        if pid in ancestors or not any(marker in command for marker in markers):
            continue
        competing.append(
            {"pid": pid, "resident_kib": rss, "command_digest": _sha256(command.encode())}
        )
    return competing


def _append_receipt(path: Path, value: dict[str, object]) -> None:
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(
    *,
    model_path: Path,
    request_path: Path,
    receipt_path: Path,
    max_tokens: int,
    max_battery_celsius: float,
    max_job_seconds: int,
    profile_path: Path | None,
    session_receipt_path: Path | None,
) -> None:
    jobs = _read_jobs(request_path)
    competing = _competing_heavy_processes()
    if competing:
        raise RuntimeError("HEAVY_MODEL_SESSION_ALREADY_ACTIVE")
    completed = _completed_job_ids(receipt_path)
    attempt_counts = _attempt_counts(receipt_path)
    profile: dict[str, object] | None = None
    profile_digest: str | None = None
    if profile_path is not None:
        profile_value = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(profile_value, dict):
            raise ValueError("Execution profile must be a JSON object")
        if profile_value.get("quantization") != "bf16":
            raise ValueError("Bounded BF16 execution requires an exact BF16 profile")
        if profile_value.get("deterministic_decoding") is not True:
            raise ValueError("Bounded BF16 execution requires deterministic decoding")
        profile = profile_value
        profile_digest = _sha256(profile_path.read_bytes())
    session_started_at = datetime.now(UTC)
    session_started_monotonic = time.monotonic()
    initial_thermal = _thermal_gate(max_battery_celsius)
    mlx_vlm = importlib.import_module("mlx_vlm")
    prompt_utils = importlib.import_module("mlx_vlm.prompt_utils")
    model, processor = mlx_vlm.load(str(model_path))
    config = model.config
    loaded_model_identity = str(getattr(config, "_name_or_path", model_path))
    for job in jobs:
        job_id = str(job["job_id"])
        if job_id in completed:
            continue
        attempt_number = attempt_counts.get(job_id, 0) + 1
        request_digest = _sha256(
            json.dumps(job, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        attempt_id = _sha256(
            f"{job_id}:{attempt_number}:{request_digest}:{profile_digest}".encode()
        )
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        thermal = _thermal_gate(max_battery_celsius)
        images = [str(value) for value in job.get("image_paths", [])]
        for image_path in images:
            if not Path(image_path).is_file():
                raise FileNotFoundError(image_path)
        prompt = prompt_utils.apply_chat_template(
            processor,
            config,
            str(job["prompt"]),
            num_images=len(images),
        )

        def timeout_handler(_signum: int, _frame: object) -> None:
            raise TimeoutError("QWEN_JOB_TIMEOUT")

        previous_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, max_job_seconds)
        try:
            result = mlx_vlm.generate(
                model,
                processor,
                prompt,
                image=images or None,
                max_tokens=max_tokens,
                temperature=0.0,
                verbose=False,
            )
        except Exception as error:
            _append_receipt(
                receipt_path,
                {
                    "job_id": job_id,
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "state": "failed",
                    "request_digest": request_digest,
                    "response_digest": _sha256(b""),
                    "response": "",
                    "error_code": type(error).__name__,
                    "thermal": thermal,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_seconds": round(time.monotonic() - started_monotonic, 6),
                    "execution_profile_digest": profile_digest,
                    "model_identity": profile.get("model_identity") if profile else None,
                    "model_revision": profile.get("model_revision") if profile else None,
                },
            )
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
        text = str(result.text)
        _append_receipt(
            receipt_path,
            {
                "job_id": job_id,
                "attempt_id": attempt_id,
                "attempt_number": attempt_number,
                "state": "completed",
                "request_digest": request_digest,
                "response_digest": _sha256(text.encode("utf-8")),
                "response": text,
                "thermal": thermal,
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_seconds": round(time.monotonic() - started_monotonic, 6),
                "execution_profile_digest": profile_digest,
                "model_identity": profile.get("model_identity") if profile else None,
                "model_revision": profile.get("model_revision") if profile else None,
            },
        )
    if session_receipt_path is not None:
        if profile is None or profile_digest is None:
            raise ValueError("A session receipt requires an exact execution profile")
        if session_receipt_path.exists():
            raise FileExistsError("Immutable session receipt already exists")
        session_payload = {
            "contract": "local-mlx-session-receipt/0.2.0",
            "process_id": os.getpid(),
            "provider": profile.get("provider"),
            "model_identity": profile.get("model_identity"),
            "model_revision": profile.get("model_revision"),
            "model_digest": profile.get("model_digest"),
            "model_path": str(model_path.resolve()),
            "loaded_model_identity": loaded_model_identity,
            "execution_profile": profile.get("execution_profile"),
            "execution_profile_digest": profile_digest,
            "prompt_version": profile.get("prompt_version"),
            "schema_version": profile.get("schema_version"),
            "verification_policy_version": profile.get("verification_policy_version"),
            "runtime": {
                "mlx_vlm": importlib.metadata.version("mlx-vlm"),
                "mlx": importlib.metadata.version("mlx"),
                "transformers": importlib.metadata.version("transformers"),
            },
            "request_manifest_digest": _sha256(request_path.read_bytes()),
            "receipt_stream_digest": _sha256(receipt_path.read_bytes()),
            "job_count": len(jobs),
            "temperature": 0,
            "max_tokens": max_tokens,
            "max_job_seconds": max_job_seconds,
            "initial_thermal": initial_thermal,
            "competing_heavy_processes": competing,
            "started_at": session_started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_seconds": round(time.monotonic() - session_started_monotonic, 6),
        }
        session_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        session_receipt_path.write_text(
            json.dumps(session_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--receipts", required=True, type=Path)
    parser.add_argument("--max-tokens", required=True, type=int)
    parser.add_argument("--max-battery-celsius", type=float, default=45.0)
    parser.add_argument("--max-job-seconds", type=int, default=900)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--session-receipt", type=Path)
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path(tempfile.gettempdir()) / "asd-kontur-qwen-heavy-session.lock",
    )
    args = parser.parse_args()
    if (args.profile is None) != (args.session_receipt is None):
        parser.error("--profile and --session-receipt must be supplied together")
    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_file.open("a+b") as lock_stream:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("HEAVY_MODEL_SESSION_ALREADY_ACTIVE") from error
        run(
            model_path=args.model,
            request_path=args.request,
            receipt_path=args.receipts,
            max_tokens=args.max_tokens,
            max_battery_celsius=args.max_battery_celsius,
            max_job_seconds=args.max_job_seconds,
            profile_path=args.profile,
            session_receipt_path=args.session_receipt,
        )


if __name__ == "__main__":
    main()
