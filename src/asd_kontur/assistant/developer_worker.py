import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from types import MappingProxyType

PROFILE = "qwen3.8-27b-developer-worker@1.0.0"
MAX_GENERATION_TOKENS = 6000


def validate_generation_tokens(max_tokens: int) -> None:
    if not 64 <= max_tokens <= MAX_GENERATION_TOKENS:
        raise ValueError("developer_worker_max_tokens_invalid")


@dataclass(frozen=True, slots=True)
class DeveloperRequest:
    task_id: str
    objective: str
    allowed_files: tuple[str, ...]
    readonly_files: tuple[str, ...]
    invariants: tuple[str, ...]
    acceptance: tuple[str, ...]
    context_files: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.objective.strip():
            raise ValueError("empty_task_or_objective")
        if not self.allowed_files or len(self.allowed_files) > 12:
            raise ValueError("too_many_allowed_files")
        if not (1 <= len(self.invariants) <= 12):
            raise ValueError("invalid_invariants_count")
        if not (1 <= len(self.acceptance) <= 12):
            raise ValueError("invalid_acceptance_count")
        if len(set((*self.allowed_files, *self.readonly_files))) != len(
            (*self.allowed_files, *self.readonly_files)
        ):
            raise ValueError("duplicate_file_scope")
        for path in self.allowed_files + self.readonly_files:
            if not self._is_valid_path(path):
                raise ValueError("invalid_path_format")
        context = dict(self.context_files)
        if not all(
            isinstance(path, str) and isinstance(value, str) for path, value in context.items()
        ):
            raise ValueError("invalid_context_files")
        for path in context:
            if path not in self.allowed_files and path not in self.readonly_files:
                raise ValueError("context_key_not_allowed")
        total = sum(len(value) for value in context.values())
        if total > 160000:
            raise ValueError("context_too_large")
        object.__setattr__(self, "context_files", MappingProxyType(context))

    @staticmethod
    def _is_valid_path(p: str) -> bool:
        parts = p.split("/")
        return (
            bool(p) and not p.startswith("/") and all(part not in {"", ".", ".."} for part in parts)
        )

    @property
    def digest(self) -> str:
        data = {
            "task_id": self.task_id,
            "objective": self.objective,
            "allowed_files": list(self.allowed_files),
            "readonly_files": list(self.readonly_files),
            "invariants": list(self.invariants),
            "acceptance": list(self.acceptance),
            "context_files": dict(self.context_files),
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def prompt(self) -> str:
        return (
            f"Role: {PROFILE}\n"
            "Isolated worker. No file write, shell, git, network, SQL, consultant, harness.\n"
            f"Task: {self.task_id}\n"
            f"Objective: {self.objective}\n"
            f"Allowed: {', '.join(self.allowed_files)}\n"
            f"Readonly: {', '.join(self.readonly_files)}\n"
            f"Invariants: {json.dumps(self.invariants, ensure_ascii=False)}\n"
            f"Acceptance: {json.dumps(self.acceptance, ensure_ascii=False)}\n"
            f"Context: {json.dumps(dict(self.context_files), ensure_ascii=False)}\n"
            "Supplied context is authoritative. Old/context hunk lines must be copied "
            "byte-for-byte. Hunk counts and locations must be verified. Absent "
            "symbols/schemas/tables/context must not be invented. New files must be "
            "complete. Explicit invariants override habits. Inability to produce an "
            "exact patch must return blocked with an empty diff.\n"
            "Return one JSON object only: no prose and no markdown fence. Exact schema: "
            '{"plan":["non-empty step"],"unified_diff":"git unified diff",'
            '"tests":["full test command"],"assumptions":[],"terminal_outcome":"proposed"}. '
            "plan and tests are non-empty arrays of non-empty strings; assumptions is an array "
            "of strings; terminal_outcome is proposed or blocked. For blocked use an empty diff."
        )


@dataclass(frozen=True, slots=True)
class DeveloperProposal:
    plan: tuple[str, ...]
    unified_diff: str
    tests: tuple[str, ...]
    assumptions: tuple[str, ...]
    terminal_outcome: str

    @property
    def digest(self) -> str:
        data = {
            "plan": list(self.plan),
            "unified_diff": self.unified_diff,
            "tests": list(self.tests),
            "assumptions": list(self.assumptions),
            "terminal_outcome": self.terminal_outcome,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_proposal(raw: str, allowed_files: tuple[str, ...]) -> DeveloperProposal:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("invalid_json") from error
    if not isinstance(data, dict):
        raise ValueError("invalid_json_type")
    required = {"plan", "unified_diff", "tests", "assumptions", "terminal_outcome"}
    if set(data.keys()) != required:
        raise ValueError("invalid_keys")
    outcome = data["terminal_outcome"]
    if not isinstance(outcome, str) or outcome not in ("proposed", "blocked"):
        raise ValueError("invalid_outcome")
    plan = _string_list(data["plan"], "plan", allow_empty=False)
    tests = _string_list(data["tests"], "tests", allow_empty=False)
    assumptions = _string_list(data["assumptions"], "assumptions", allow_empty=True)
    diff = data["unified_diff"]
    if not isinstance(diff, str) or len(diff) > 120000:
        raise ValueError("invalid_diff")
    if any(marker in diff for marker in ("\x00", "GIT binary patch", "Binary files ")):
        raise ValueError("binary_content")
    if outcome == "blocked":
        if diff.strip():
            raise ValueError("blocked_diff_not_empty")
    else:
        _validate_diff(diff, frozenset(allowed_files))
    return DeveloperProposal(
        plan=plan,
        unified_diff=diff,
        tests=tests,
        assumptions=assumptions,
        terminal_outcome=outcome,
    )


def _string_list(value: object, name: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"invalid_{name}")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"invalid_{name}")
    return tuple(value)


def _validate_diff(diff: str, allowed_files: frozenset[str]) -> None:
    starts = [match.start() for match in re.finditer(r"(?m)^diff --git ", diff)]
    if not starts or diff[: starts[0]].strip():
        raise ValueError("invalid_diff_preamble")
    starts.append(len(diff))
    for start, end in pairwise(starts):
        block = diff[start:end]
        lines = block.splitlines()
        header = re.fullmatch(r"diff --git a/(\S+) b/(\S+)", lines[0])
        if header is None or header.group(1) != header.group(2):
            raise ValueError("invalid_diff_header")
        path = header.group(2)
        if path not in allowed_files:
            raise ValueError("diff_file_not_allowed")
        first_hunk = next(
            (index for index, line in enumerate(lines) if line.startswith("@@")), len(lines)
        )
        prologue = lines[1:first_hunk]
        old_headers = [line for line in prologue if line.startswith("--- ")]
        new_headers = [line for line in prologue if line.startswith("+++ ")]
        if len(old_headers) != 1 or len(new_headers) != 1:
            raise ValueError("invalid_file_headers")
        if new_headers[0] != f"+++ b/{path}":
            raise ValueError("invalid_new_file_header")
        if old_headers[0] not in {f"--- a/{path}", "--- /dev/null"}:
            raise ValueError("invalid_old_file_header")
