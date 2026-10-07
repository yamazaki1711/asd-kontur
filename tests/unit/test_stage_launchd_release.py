"""Release staging cannot mutate loaded launchd plists or duplicate arguments."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    source = root / "source"
    source.mkdir()
    release = root / "release"
    python = release / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"synthetic executable")
    index = release / "frontend/dist/index.html"
    index.parent.mkdir(parents=True)
    index.write_text("<html>changed release</html>", encoding="utf-8")
    for role, mode in (
        ("api", "serve-api"),
        ("worker", "run-worker"),
        ("assistant-worker", "run-assistant-worker"),
        ("project-orchestrator", "run-project-orchestrator"),
    ):
        payload = {
            "Label": f"ru.asd-kontur.spine.{role}",
            "ProgramArguments": [
                "/previous/.venv/bin/python", "-m",
                "asd_kontur.application_spine.runtime", mode,
            ],
            "EnvironmentVariables": {
                "ASD_RELEASE_COMMIT": "a" * 40,
                "ASD_EXPECTED_MIGRATION_HEAD": "0134_old",
                "ASD_FRONTEND_DIST": "/previous/frontend/dist",
                "ASD_FRONTEND_BUILD_DIGEST": "old",
                "ASD_OPENAPI_DIGEST": "old",
                "ASD_DEPLOYED_AT": "old",
                "ASD_AUTH_AUDIT_PEPPER": "synthetic-secret-must-not-be-printed",
            },
        }
        with (source / f"ru.asd-kontur.spine.{role}.plist").open("wb") as stream:
            plistlib.dump(payload, stream)
    return source, release, root / "staged"


def _run(source: Path, release: Path, staged: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "tools/stage_launchd_release.py"),
            "--source-plist-dir", str(source),
            "--output-dir", str(staged),
            "--release-dir", str(release),
            "--sha", "b" * 40,
            "--migration-head", "0135_new",
            "--openapi-digest", "c" * 64,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_stages_new_private_plists_without_touching_source(tmp_path: Path) -> None:
    source, release, staged = _fixture(tmp_path)
    before = {item.name: item.read_bytes() for item in source.iterdir()}
    result = _run(source, release, staged)
    assert result.returncode == 0
    assert "synthetic-secret" not in result.stdout + result.stderr
    assert before == {item.name: item.read_bytes() for item in source.iterdir()}
    for item in staged.iterdir():
        with item.open("rb") as stream:
            payload = plistlib.load(stream)
        assert len(payload["ProgramArguments"]) == 4
        assert payload["ProgramArguments"][0] == str(release / ".venv/bin/python")
        assert payload["EnvironmentVariables"]["ASD_RELEASE_COMMIT"] == "b" * 40
        assert payload["EnvironmentVariables"]["ASD_AUTH_AUDIT_PEPPER"] == (
            "synthetic-secret-must-not-be-printed"
        )
        assert item.stat().st_mode & 0o777 == 0o600
    assert staged.stat().st_mode & 0o777 == 0o700
    assert _run(source, release, staged).returncode != 0


def test_malformed_source_does_not_create_output(tmp_path: Path) -> None:
    source, release, staged = _fixture(tmp_path)
    target = source / "ru.asd-kontur.spine.api.plist"
    with target.open("rb") as stream:
        payload = plistlib.load(stream)
    payload["ProgramArguments"].append("unexpected")
    with target.open("wb") as stream:
        plistlib.dump(payload, stream)
    assert _run(source, release, staged).returncode != 0
    assert not staged.exists()
