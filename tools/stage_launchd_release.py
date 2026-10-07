"""Stage four launchd roles without ever mutating the loaded source plists.

The generated directory is new and private. This command does not migrate a
database or boot out/bootstrap any service; that remains a controlled cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
from datetime import UTC, datetime
from pathlib import Path

from check_launchd_release import check_release

_ROLES = {
    "api": "serve-api",
    "worker": "run-worker",
    "assistant-worker": "run-assistant-worker",
    "project-orchestrator": "run-project-orchestrator",
}
_MODULE = "asd_kontur.application_spine.runtime"


def stage_release(
    *,
    source_dir: Path,
    output_dir: Path,
    release_dir: Path,
    sha: str,
    migration_head: str,
    openapi_digest: str,
) -> None:
    if not output_dir.is_absolute() or output_dir.exists() or output_dir == source_dir:
        raise ValueError("new_absolute_staging_directory_required")
    if not all((source_dir / f"ru.asd-kontur.spine.{role}.plist").is_file() for role in _ROLES):
        raise ValueError("source_plists_incomplete")
    python = release_dir / ".venv/bin/python"
    frontend = release_dir / "frontend/dist"
    index = frontend / "index.html"
    if not python.is_file() or not index.is_file():
        raise ValueError("staged_release_incomplete")
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise ValueError("release_sha_invalid")
    if len(openapi_digest) != 64 or any(
        character not in "0123456789abcdef" for character in openapi_digest
    ):
        raise ValueError("openapi_digest_invalid")
    if not migration_head.startswith("0") or len(migration_head) > 100:
        raise ValueError("migration_head_invalid")

    # Validate all inputs before creating anything; no source plist is ever opened for writing.
    originals: dict[str, dict[str, object]] = {}
    for role, mode in _ROLES.items():
        source = source_dir / f"ru.asd-kontur.spine.{role}.plist"
        with source.open("rb") as stream:
            payload = plistlib.load(stream)
        if not isinstance(payload, dict):
            raise ValueError(f"{role}:source_plist_invalid")
        arguments = payload.get("ProgramArguments")
        if (
            not isinstance(arguments, list)
            or len(arguments) != 4
            or arguments[1:] != ["-m", _MODULE, mode]
        ):
            raise ValueError(f"{role}:source_arguments_invalid")
        environment = payload.get("EnvironmentVariables")
        if not isinstance(environment, dict) or not all(
            isinstance(environment.get(key), str)
            for key in (
                "ASD_RELEASE_COMMIT",
                "ASD_EXPECTED_MIGRATION_HEAD",
                "ASD_FRONTEND_DIST",
                "ASD_FRONTEND_BUILD_DIGEST",
                "ASD_OPENAPI_DIGEST",
                "ASD_DEPLOYED_AT",
            )
        ):
            raise ValueError(f"{role}:source_environment_invalid")
        originals[role] = payload

    output_dir.mkdir(mode=0o700, parents=False)
    frontend_digest = hashlib.sha256(index.read_bytes()).hexdigest()
    deployed_at = datetime.now(UTC).isoformat()
    for role, mode in _ROLES.items():
        payload = originals[role]
        environment = dict(payload["EnvironmentVariables"])
        environment.update(
            {
                "ASD_RELEASE_COMMIT": sha,
                "ASD_EXPECTED_MIGRATION_HEAD": migration_head,
                "ASD_FRONTEND_DIST": str(frontend),
                "ASD_FRONTEND_BUILD_DIGEST": frontend_digest,
                "ASD_OPENAPI_DIGEST": openapi_digest,
                "ASD_DEPLOYED_AT": deployed_at,
            }
        )
        payload["EnvironmentVariables"] = environment
        payload["ProgramArguments"] = [str(python), "-m", _MODULE, mode]
        target = output_dir / f"ru.asd-kontur.spine.{role}.plist"
        with target.open("wb") as stream:
            plistlib.dump(payload, stream)
        os.chmod(target, 0o600)
    failures = check_release(
        plist_dir=output_dir,
        release_dir=release_dir,
        sha=sha,
        migration_head=migration_head,
    )
    if failures:
        raise ValueError("staged_plist_preflight_failed:" + ",".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plist-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--openapi-digest", required=True)
    args = parser.parse_args()
    stage_release(
        source_dir=args.source_plist_dir,
        output_dir=args.output_dir,
        release_dir=args.release_dir,
        sha=args.sha,
        migration_head=args.migration_head,
        openapi_digest=args.openapi_digest,
    )
    print("PASS private launchd staging: 4/4 roles; source plists unchanged")


if __name__ == "__main__":
    main()
