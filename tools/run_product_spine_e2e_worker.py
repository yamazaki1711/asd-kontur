"""Crash/restart worker subprocess used by the live browser E2E."""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path

import sqlalchemy as sa

from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.worker import DocumentWorker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("claim-and-pause", "drain"))
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--expected", type=int, default=5)
    arguments = parser.parse_args()
    state_path = Path(os.environ["ASD_E2E_STATE_PATH"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    engine = sa.create_engine(str(state["worker_database_url"]), pool_pre_ping=True)
    repository = SpinePostgresRepository(engine)
    store = WorkspaceObjectStore(
        Path(str(state["object_store_root"])),
        chunk_bytes=int(state["upload_chunk_bytes"]),
        max_file_bytes=int(state["max_file_bytes"]),
    )
    try:
        if arguments.mode == "claim-and-pause":
            if arguments.marker is None or not arguments.marker.is_absolute():
                raise RuntimeError("an absolute marker is required")
            claimed = repository.claim_next_job(
                worker_identity="browser-e2e-crashed-worker",
                lease_seconds=int(state["lease_seconds"]),
            )
            if claimed is None:
                raise RuntimeError("no job available to interrupt")
            repository.mark_job_running(
                claimed,
                worker_identity="browser-e2e-crashed-worker",
            )
            arguments.marker.write_text(str(claimed.job_id), encoding="utf-8")
            signal.pause()
            return
        worker = DocumentWorker(
            repository,
            store,
            worker_identity="browser-e2e-restarted-worker",
            lease_seconds=int(state["lease_seconds"]),
        )
        processed = 0
        while worker.run_once() is not None:
            processed += 1
        if processed != arguments.expected:
            raise RuntimeError(f"expected {arguments.expected} recovered jobs, got {processed}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
