from __future__ import annotations

from pathlib import Path

PROHIBITED_PROJECT_NAMES = ("тм-35", "левашово", "игнатьево")
SECRET_MARKERS = (
    "-----begin open" + "ssh private key-----",
    "-----begin rsa private key-----",
    "ghp_" + "abcdefghijklmnopqrstuvwxyz",
    "sk-" + "abcdefghijklmnopqrstuvwxyz",
)


def test_contracts_and_test_fixtures_are_object_independent(repository_root: Path) -> None:
    roots = (repository_root / "contracts", repository_root / "tests")
    matches: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".py", ".md"}:
                continue
            if path == Path(__file__):
                continue
            text = path.read_text(encoding="utf-8").lower()
            if any(name in text for name in PROHIBITED_PROJECT_NAMES):
                matches.append(str(path.relative_to(repository_root)))
    assert matches == []


def test_repository_contains_no_private_key_or_live_token_shape(
    repository_root: Path,
) -> None:
    matches: list[str] = []
    ignored_roots = {".git", ".venv"}
    for path in repository_root.rglob("*"):
        relative = path.relative_to(repository_root)
        if not path.is_file() or any(part in ignored_roots for part in relative.parts):
            continue
        if path == Path(__file__):
            continue
        if path.suffix not in {".json", ".py", ".md", ".toml", ".yml", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if any(marker in text for marker in SECRET_MARKERS):
            matches.append(str(relative))
    assert matches == []
