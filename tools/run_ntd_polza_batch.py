"""Run a bounded, resumable batch of durable public-NTD raster recovery jobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from asd_kontur.ntd.processing_jobs import (
    NtdProcessingJobRepository,
    terminal_state_for_failure,
    utc_now,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--object-root", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--lease-owner", required=True)
    parser.add_argument("--enqueue-only", action="store_true")
    parser.add_argument("--cancel-unqualified-profile", action="store_true")
    arguments = parser.parse_args()
    if arguments.limit < 1 or arguments.limit > 50:
        raise ValueError("NTD_POLZA_BATCH_LIMIT_OUT_OF_RANGE")
    _require_private_directory(arguments.object_root)
    _require_private_directory(arguments.receipt_dir)
    engine = sa.create_engine(arguments.database_url)
    repository = NtdProcessingJobRepository(engine)
    try:
        stale = repository.reconcile_expired(reconciled_at=utc_now())
        duplicates = repository.reconcile_duplicate_page_jobs(reconciled_at=utc_now())
        if arguments.cancel_unqualified_profile:
            cancelled = repository.cancel_queued_for_unqualified_profile(cancelled_at=utc_now())
            print(
                json.dumps(
                    {
                        "schema": "ntd-polza-raster-batch-cancellation-v1",
                        "cancelled": cancelled,
                        "failure_code": "POLZA_BATCH_PROFILE_NOT_QUALIFIED",
                        "stale_jobs_reconciled": stale,
                        "duplicate_jobs_reconciled": duplicates,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        eligible, inserted = repository.enqueue_pending_raster_pages(eligible_at=utc_now())
        results: list[dict[str, Any]] = []
        processing_limit = 0 if arguments.enqueue_only else arguments.limit
        for _ in range(processing_limit):
            claimed_at = utc_now()
            job = repository.claim_next(
                lease_owner=arguments.lease_owner,
                claimed_at=claimed_at,
                lease_duration=timedelta(minutes=10),
            )
            if job is None:
                break
            repository.heartbeat(job, lease_owner=arguments.lease_owner, heartbeat_at=utc_now())
            command = [
                sys.executable,
                "tools/run_ntd_polza_canary.py",
                "--database-url",
                arguments.database_url,
                "--object-root",
                str(arguments.object_root),
                "--receipt-dir",
                str(arguments.receipt_dir),
                "--designation",
                job.designation,
                "--page-index",
                str(job.page_index),
            ]
            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[1],
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                timeout=540,
                check=False,
            )
            output = _last_json_object(completed.stdout)
            if completed.returncode == 0 and output.get("status") == "candidate":
                state = "succeeded"
                failure_code = None
            else:
                failure_code = str(output.get("failure_code") or "NTD_POLZA_BATCH_CHILD_FAILED")
                state = terminal_state_for_failure(failure_code)
                output = {
                    **output,
                    "child_exit_code": completed.returncode,
                    "stderr_digest_only": bool(completed.stderr),
                }
            terminal = repository.terminalize(
                job,
                lease_owner=arguments.lease_owner,
                state=state,
                failure_code=failure_code,
                output=output,
                started_at=claimed_at,
                completed_at=utc_now(),
            )
            results.append(
                {
                    "job_id": str(terminal.job_id),
                    "designation": job.designation,
                    "page_index": job.page_index,
                    "state": terminal.state,
                    "failure_code": terminal.failure_code,
                    "terminal_receipt_fingerprint": terminal.terminal_receipt_fingerprint,
                    "request_digest": output.get("request_digest"),
                    "response_digest": output.get("response_digest"),
                    "reused": output.get("reused"),
                }
            )
        print(
            json.dumps(
                {
                    "schema": "ntd-polza-raster-batch-result-v1",
                    "eligible_page_count": eligible,
                    "jobs_inserted": inserted,
                    "stale_jobs_reconciled": stale,
                    "duplicate_jobs_reconciled": duplicates,
                    "processed": len(results),
                    "results": results,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if all(value["state"] == "succeeded" for value in results) else 2
    finally:
        engine.dispose()


def _last_json_object(value: str) -> dict[str, Any]:
    for line in reversed(value.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"failure_code": "NTD_POLZA_BATCH_CHILD_OUTPUT_INVALID"}


def _require_private_directory(path: Path) -> None:
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("NTD_EXTERNAL_DIRECTORY_INVALID")
    if path.stat().st_mode & 0o077:
        raise ValueError("NTD_EXTERNAL_DIRECTORY_NOT_PRIVATE")


if __name__ == "__main__":
    raise SystemExit(main())
