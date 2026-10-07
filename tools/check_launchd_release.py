"""Reject malformed staged public launchd plists before a controlled cutover.

Only non-secret release identity and executable topology are inspected. This
preflight does not start, stop or mutate a service.
"""

from __future__ import annotations

import argparse
import plistlib
from pathlib import Path

_MODULE = "asd_kontur.application_spine.runtime"
_ROLES = {
    "api": "serve-api",
    "worker": "run-worker",
    "project-orchestrator": "run-project-orchestrator",
    "assistant-worker": "run-assistant-worker",
}


def check_release(
    *, plist_dir: Path, release_dir: Path, sha: str, migration_head: str
) -> list[str]:
    """Return stable failure codes without disclosing plist environment values."""

    failures: list[str] = []
    python = release_dir / ".venv/bin/python"
    frontend = release_dir / "frontend/dist"
    if not python.is_file():
        failures.append("release_python_unavailable")
    if not (frontend / "index.html").is_file():
        failures.append("release_frontend_unavailable")
    for role, mode in _ROLES.items():
        path = plist_dir / f"ru.asd-kontur.spine.{role}.plist"
        if not path.is_file():
            failures.append(f"{role}:plist_unavailable")
            continue
        try:
            with path.open("rb") as source:
                payload = plistlib.load(source)
        except (OSError, ValueError, TypeError):
            failures.append(f"{role}:plist_invalid")
            continue
        expected_arguments = [str(python), "-m", _MODULE, mode]
        if payload.get("ProgramArguments") != expected_arguments:
            failures.append(f"{role}:arguments_mismatch")
        environment = payload.get("EnvironmentVariables")
        if not isinstance(environment, dict):
            failures.append(f"{role}:environment_unavailable")
            continue
        if environment.get("ASD_RELEASE_COMMIT") != sha:
            failures.append(f"{role}:sha_mismatch")
        if environment.get("ASD_EXPECTED_MIGRATION_HEAD") != migration_head:
            failures.append(f"{role}:migration_mismatch")
        if environment.get("ASD_FRONTEND_DIST") != str(frontend):
            failures.append(f"{role}:frontend_mismatch")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plist-dir", required=True, type=Path)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--migration-head", required=True)
    args = parser.parse_args()
    failures = check_release(
        plist_dir=args.plist_dir,
        release_dir=args.release_dir,
        sha=args.sha,
        migration_head=args.migration_head,
    )
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("PASS release plist topology: 4/4 application roles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
