from __future__ import annotations

# ruff: noqa: RUF001 -- Russian contract text is intentional.
import json
from collections.abc import Mapping

import pytest

from asd_kontur.assistant.developer_worker import (
    DeveloperRequest,
    parse_proposal,
    validate_generation_tokens,
)


def _request(**changes: object) -> DeveloperRequest:
    values: dict[str, object] = {
        "task_id": "DW-001",
        "objective": "Исправить ограниченный дефект",
        "allowed_files": ("src/a.py",),
        "readonly_files": ("src/context.py",),
        "invariants": ("Не менять другие файлы",),
        "acceptance": ("pytest проходит",),
        "context_files": {"src/a.py": "old", "src/context.py": "reference"},
    }
    values.update(changes)
    return DeveloperRequest(**values)  # type: ignore[arg-type]


def _proposal(*, diff: str, outcome: str = "proposed", **changes: object) -> str:
    values: dict[str, object] = {
        "plan": ["Изменить файл"],
        "unified_diff": diff,
        "tests": [".venv/bin/pytest tests/unit/test_qwen_developer_worker.py"],
        "assumptions": [],
        "terminal_outcome": outcome,
    }
    values.update(changes)
    return json.dumps(values, ensure_ascii=False)


EXISTING_DIFF = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1 +1 @@
-old
+new
"""

NEW_DIFF = """diff --git a/src/new.py b/src/new.py
new file mode 100644
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1 @@
+new
"""


def test_request_is_immutable_and_has_order_independent_digest() -> None:
    first = _request(context_files={"src/a.py": "old", "src/context.py": "reference"})
    second = _request(context_files={"src/context.py": "reference", "src/a.py": "old"})
    assert first.digest == second.digest
    assert isinstance(first.context_files, Mapping)
    with pytest.raises(TypeError):
        first.context_files["src/a.py"] = "changed"  # type: ignore[index]
    with pytest.raises(AttributeError):
        first.objective = "changed"  # type: ignore[misc]


def test_prompt_pins_isolated_role_and_complete_task_contract() -> None:
    prompt = _request().prompt()
    assert "qwen3.8-27b-developer-worker@1.0.0" in prompt
    for value in (
        "No file write, shell, git, network, SQL, consultant, harness",
        "DW-001",
        "Исправить ограниченный дефект",
        "src/a.py",
        "src/context.py",
        "Не менять другие файлы",
        "pytest проходит",
    ):
        assert value in prompt

    for key in ("plan", "unified_diff", "tests", "assumptions", "terminal_outcome"):
        assert key in prompt


@pytest.mark.parametrize("path", ("", "/tmp/a.py", "../a.py", "a/../b", "a/./b", "a//b"))
def test_request_rejects_non_repo_relative_paths(path: str) -> None:
    with pytest.raises(ValueError, match="invalid_path_format"):
        _request(allowed_files=(path,))


def test_request_rejects_scope_and_context_limit_violations() -> None:
    with pytest.raises(ValueError, match="duplicate_file_scope"):
        _request(allowed_files=("src/a.py",), readonly_files=("src/a.py",))
    with pytest.raises(ValueError, match="context_key_not_allowed"):
        _request(context_files={"secret.txt": "no"})
    with pytest.raises(ValueError, match="context_too_large"):
        _request(context_files={"src/a.py": "x" * 160001})


def test_valid_existing_new_and_blocked_proposals_have_stable_digests() -> None:
    existing = parse_proposal(_proposal(diff=EXISTING_DIFF), ("src/a.py",))
    reordered = json.loads(_proposal(diff=EXISTING_DIFF))
    reordered = {key: reordered[key] for key in reversed(tuple(reordered))}
    assert existing.digest == parse_proposal(json.dumps(reordered), ("src/a.py",)).digest
    assert parse_proposal(_proposal(diff=NEW_DIFF), ("src/new.py",)).terminal_outcome == "proposed"
    blocked = parse_proposal(_proposal(diff="", outcome="blocked"), ("src/a.py",))
    assert blocked.terminal_outcome == "blocked"


@pytest.mark.parametrize(
    ("raw", "error"),
    (
        ("answer before JSON", "invalid_json"),
        ("```json\n{}\n```", "invalid_json"),
        (_proposal(diff=EXISTING_DIFF, extra=True), "invalid_keys"),
        (_proposal(diff=EXISTING_DIFF, plan="not-list"), "invalid_plan"),
        (_proposal(diff=EXISTING_DIFF, plan=[]), "invalid_plan"),
        (_proposal(diff=EXISTING_DIFF, tests=[1]), "invalid_tests"),
        (_proposal(diff=EXISTING_DIFF, tests=[]), "invalid_tests"),
        (_proposal(diff=EXISTING_DIFF, assumptions="none"), "invalid_assumptions"),
        (_proposal(diff=EXISTING_DIFF, outcome="done"), "invalid_outcome"),
        (_proposal(diff=EXISTING_DIFF, outcome="blocked"), "blocked_diff_not_empty"),
        (_proposal(diff="GIT binary patch"), "binary_content"),
        (_proposal(diff="Binary files a/x and b/x differ"), "binary_content"),
        (_proposal(diff="plain text"), "invalid_diff_preamble"),
        (_proposal(diff=EXISTING_DIFF.replace("src/a.py", "src/b.py")), "diff_file_not_allowed"),
        (
            _proposal(diff=EXISTING_DIFF.replace("+++ b/src/a.py", "+++ /dev/null")),
            "invalid_new_file_header",
        ),
        (_proposal(diff="--- a/src/a.py\n" + EXISTING_DIFF), "invalid_diff_preamble"),
    ),
)
def test_proposal_parser_fails_closed(raw: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_proposal(raw, ("src/a.py",))


def test_developer_worker_generation_budget_is_bounded() -> None:
    validate_generation_tokens(64)
    validate_generation_tokens(6000)
    with pytest.raises(ValueError, match="developer_worker_max_tokens_invalid"):
        validate_generation_tokens(63)
    with pytest.raises(ValueError, match="developer_worker_max_tokens_invalid"):
        validate_generation_tokens(6001)
