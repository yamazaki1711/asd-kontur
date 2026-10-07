"""Execute owner-authorized, exact-ID workspace lifecycle cleanup.

This is an operations client for WorkspaceResetService, not a SQL deletion
shortcut. A private journal permits continuation after a completed prepare.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from asd_kontur.application_spine.config import SpineSettings
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.application_spine.postgres import SpinePostgresRepository
from asd_kontur.application_spine.reset import WorkspaceResetService
from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import PostgresLifecycleRepository


def _manifest(path: Path, expected_digest: str) -> dict[str, object]:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise RuntimeError("cleanup_manifest_invalid")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise RuntimeError("cleanup_manifest_digest_mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema") != (
        "asd-kontur-explicit-workspace-cleanup@1"
    ):
        raise RuntimeError("cleanup_manifest_schema_invalid")
    ids = value.get("unwanted_workspace_ids")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise RuntimeError("cleanup_manifest_targets_invalid")
    for identity in [*ids, value.get("retain_workspace_id"), value.get("organization_id")]:
        UUID(str(identity))
    if value["retain_workspace_id"] in ids:
        raise RuntimeError("cleanup_manifest_retained_targeted")
    return value


def _save_journal(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(".next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _load_journal(path: Path, manifest_digest: str) -> dict[str, object]:
    if not path.exists():
        return {"manifest_sha256": manifest_digest, "workspaces": {}}
    if path.is_symlink():
        raise RuntimeError("cleanup_journal_symlink")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("manifest_sha256") != manifest_digest or not isinstance(
        value.get("workspaces"), dict
    ):
        raise RuntimeError("cleanup_journal_manifest_mismatch")
    return value


def _assert_inventory(
    repository: SpinePostgresRepository,
    manifest: dict[str, object],
    *,
    allow_partial: bool,
) -> tuple[str, ...]:
    owner = str(manifest["owner_identity_id"])
    retain = str(manifest["retain_workspace_id"])
    targets = {str(value) for value in manifest["unwanted_workspace_ids"]}
    rows = repository.list_workspaces(owner_identity_id=owner)
    actual = {str(row.workspace_id) for row in rows}
    expected = targets | {retain}
    if retain not in actual or not actual <= expected:
        raise RuntimeError("cleanup_authorized_inventory_conflict")
    if not allow_partial and (
        actual != expected or len(actual) != manifest["expected_authorized_workspace_count_before"]
    ):
        raise RuntimeError("cleanup_authorized_inventory_not_exact")
    retained = next(row for row in rows if str(row.workspace_id) == retain)
    if (
        str(retained.organization_id) != manifest["organization_id"]
        or retained.display_name != manifest["retain_display_name"]
        or retained.lifecycle_state != "ACTIVE"
    ):
        raise RuntimeError("cleanup_retained_workspace_mismatch")
    for row in rows:
        if str(row.workspace_id) in targets and (
            str(row.organization_id) != manifest["organization_id"]
            or "Control" not in row.display_name
            or row.lifecycle_state not in {"ACTIVE", "RESET_PLANNING"}
        ):
            raise RuntimeError(f"cleanup_target_metadata_mismatch:{row.workspace_id}")
    return tuple(str(row.workspace_id) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--launch-agent-plist", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    manifest = _manifest(args.manifest, args.manifest_sha256)
    with args.launch_agent_plist.open("rb") as source:
        deployed = plistlib.load(source)["EnvironmentVariables"]
    required = (
        "ASD_DATABASE_URL",
        "ASD_LIFECYCLE_DATABASE_URL",
        "ASD_DESTRUCTION_DATABASE_URL",
        "ASD_WORKER_DATABASE_URL",
        "ASD_OBJECT_STORE_ROOT",
        "ASD_ARCHIVE_STORE_ROOT",
        "ASD_AUTH_AUDIT_PEPPER",
    )
    for key in required:
        if key not in deployed:
            raise RuntimeError(f"cleanup_deployed_configuration_missing:{key}")
    environment = {
        str(key): str(value) for key, value in deployed.items() if str(key).startswith("ASD_")
    }
    if make_url(environment["ASD_DATABASE_URL"]).database != manifest["database_name"]:
        raise RuntimeError("cleanup_deployed_database_mismatch")
    if (
        Path(environment["ASD_OBJECT_STORE_ROOT"]).resolve()
        != Path(str(manifest["object_store_root"])).resolve()
    ):
        raise RuntimeError("cleanup_deployed_object_root_mismatch")
    # Construct settings from the pinned service configuration, never from an
    # operator shell that might point at another database or storage root.
    prior = {key: os.environ.get(key) for key in environment}
    try:
        os.environ.update(environment)
        settings = SpineSettings.from_env()
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    engine = sa.create_engine(settings.database_url, pool_pre_ping=True)
    lifecycle_engine = sa.create_engine(settings.lifecycle_database_url, pool_pre_ping=True)
    destruction_engine = sa.create_engine(settings.destruction_database_url, pool_pre_ping=True)
    try:
        repository = SpinePostgresRepository(engine)
        journal_path = args.manifest.parent / "journal.json"
        journal = _load_journal(journal_path, args.manifest_sha256)
        inventory = _assert_inventory(repository, manifest, allow_partial=journal_path.exists())
        print(
            json.dumps(
                {
                    "authorized_count": len(inventory),
                    "target_count": len(manifest["unwanted_workspace_ids"]),
                }
            )
        )
        if not args.execute:
            return 0
        service = WorkspaceResetService(
            repository=repository,
            lifecycle=PostgresLifecycleRepository(lifecycle_engine),
            lifecycle_engine=lifecycle_engine,
            destruction_engine=destruction_engine,
            object_store=WorkspaceObjectStore(
                settings.object_store_root,
                chunk_bytes=settings.upload_chunk_bytes,
                max_file_bytes=settings.max_file_bytes,
            ),
            archive_store_root=settings.archive_store_root,
        )
        states = journal["workspaces"]
        assert isinstance(states, dict)
        for raw_id in manifest["unwanted_workspace_ids"]:
            workspace_id = UUID(str(raw_id))
            state = states.get(str(workspace_id))
            if isinstance(state, dict) and state.get("state") == "destroyed":
                continue
            if state is None:
                states[str(workspace_id)] = {"state": "preparing"}
                _save_journal(journal_path, journal)
                challenge = service.prepare(
                    owner_identity_id=str(manifest["owner_identity_id"]),
                    workspace_id=workspace_id,
                    correlation_id=uuid7(),
                )
                state = {
                    "state": "prepared",
                    "challenge_id": str(challenge.challenge_id),
                    "confirmation_text": challenge.confirmation_text,
                }
                states[str(workspace_id)] = state
                _save_journal(journal_path, journal)
            if not isinstance(state, dict) or state.get("state") != "prepared":
                raise RuntimeError(f"cleanup_requires_recovery:{workspace_id}")
            service.execute(
                owner_identity_id=str(manifest["owner_identity_id"]),
                workspace_id=workspace_id,
                challenge_id=UUID(str(state["challenge_id"])),
                confirmation_text=str(state["confirmation_text"]),
                correlation_id=uuid7(),
            )
            states[str(workspace_id)] = {"state": "destroyed"}
            _save_journal(journal_path, journal)
            _assert_inventory(repository, manifest, allow_partial=True)
            print(json.dumps({"destroyed_workspace_id": str(workspace_id)}))
        remaining = _assert_inventory(repository, manifest, allow_partial=True)
        if remaining != (str(manifest["retain_workspace_id"]),):
            raise RuntimeError("cleanup_remaining_workspace_mismatch")
        print(json.dumps({"outcome": "all_manifest_workspaces_destroyed", "remaining_count": 1}))
        return 0
    finally:
        engine.dispose()
        lifecycle_engine.dispose()
        destruction_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
