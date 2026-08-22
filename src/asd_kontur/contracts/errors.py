"""Typed Contract Pack validation failures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContractErrorCode(StrEnum):
    INVALID_SCHEMA = "CONTRACT_INVALID_SCHEMA"
    INCOMPATIBLE_VERSION = "CONTRACT_INCOMPATIBLE_VERSION"
    UNKNOWN_VERSION = "CONTRACT_UNKNOWN_VERSION"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    WORKSPACE_MISMATCH = "WORKSPACE_MISMATCH"
    AUTH_UNAUTHORIZED = "AUTH_UNAUTHORIZED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    CANDIDATE_INVALID = "CANDIDATE_INVALID"
    RENDER_PRINT_FAILURE = "RENDER_PRINT_FAILURE"
    GEOMETRY_BLOCKED = "GEOMETRY_BLOCKED"
    RESET_INCOMPLETE = "RESET_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: ContractErrorCode
    message: str
    instance_path: str = "$"
    schema_path: str | None = None
    invariant: str | None = None
    validation_layer: str = "schema"


class ContractValidationError(ValueError):
    """Raised for registry or contract-selection failures, never swallowed."""

    def __init__(self, issue: ValidationIssue) -> None:
        self.issue = issue
        super().__init__(f"{issue.code}: {issue.message}")
