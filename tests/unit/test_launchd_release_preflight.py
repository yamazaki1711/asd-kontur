"""A staged release cannot repeat the duplicate-executable launchd outage."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path


def _check(staged: Path, release: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "tools/check_launchd_release.py"),
            "--plist-dir",
            str(staged),
            "--release-dir",
            str(release),
            "--sha",
            "a" * 40,
            "--migration-head",
            "0129_contract_reference_review",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_preflight_rejects_duplicate_program_argument_and_wrong_sha(tmp_path: Path) -> None:
    release = tmp_path / "release"
    (release / ".venv/bin").mkdir(parents=True)
    (release / ".venv/bin/python").touch()
    (release / "frontend/dist").mkdir(parents=True)
    (release / "frontend/dist/index.html").touch()
    staged = tmp_path / "staged"
    staged.mkdir()
    modes = {
        "api": "serve-api",
        "worker": "run-worker",
        "project-orchestrator": "run-project-orchestrator",
        "assistant-worker": "run-assistant-worker",
    }
    for role, mode in modes.items():
        payload = {
            "ProgramArguments": [
                str(release / ".venv/bin/python"),
                "-m",
                "asd_kontur.application_spine.runtime",
                mode,
            ],
            "EnvironmentVariables": {
                "ASD_RELEASE_COMMIT": "a" * 40,
                "ASD_EXPECTED_MIGRATION_HEAD": "0129_contract_reference_review",
                "ASD_FRONTEND_DIST": str(release / "frontend/dist"),
            },
        }
        with (staged / f"ru.asd-kontur.spine.{role}.plist").open("wb") as output:
            plistlib.dump(payload, output)
    accepted = _check(staged, release)
    assert accepted.returncode == 0, accepted.stdout
    assert "4/4" in accepted.stdout

    api = staged / "ru.asd-kontur.spine.api.plist"
    with api.open("rb") as source:
        malformed = plistlib.load(source)
    malformed["ProgramArguments"].insert(1, str(release / ".venv/bin/python"))
    malformed["EnvironmentVariables"]["ASD_RELEASE_COMMIT"] = "b" * 40
    with api.open("wb") as output:
        plistlib.dump(malformed, output)
    rejected = _check(staged, release)
    assert rejected.returncode == 1
    assert rejected.stdout.splitlines() == [
        "FAIL api:arguments_mismatch",
        "FAIL api:sha_mismatch",
    ]
