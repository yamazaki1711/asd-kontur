"""Typed fail-closed errors for workspace lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LifecycleErrorCode(StrEnum):
    INVALID_TRANSITION = "lifecycle.invalid_transition"
    CONCURRENCY_CONFLICT = "lifecycle.concurrency_conflict"
    IDEMPOTENCY_CONFLICT = "lifecycle.idempotency_conflict"
    AUTHORITY_DENIED = "lifecycle.authority_denied"
    POLICY_BLOCKED = "lifecycle.policy_blocked"
    LEGAL_HOLD_ACTIVE = "lifecycle.legal_hold_active"
    INVENTORY_CHANGED = "lifecycle.inventory_changed"
    PLAN_INVALID = "lifecycle.plan_invalid"
    ADAPTER_UNAVAILABLE = "lifecycle.adapter_unavailable"
    ADAPTER_INCOMPLETE = "lifecycle.adapter_incomplete"
    INTEGRITY_MISMATCH = "lifecycle.integrity_mismatch"
    RESIDUE_DETECTED = "lifecycle.residue_detected"
    CROSS_WORKSPACE_RESIDUE = "lifecycle.cross_workspace_residue"
    ARCHIVE_INVALID = "lifecycle.archive_invalid"
    IMPORT_BLOCKED = "lifecycle.import_blocked"
    WRITE_FENCED = "lifecycle.write_fenced"
    CONTENTFUL_ATTESTATION = "lifecycle.contentful_attestation"


@dataclass(frozen=True, slots=True)
class LifecycleFailure:
    code: LifecycleErrorCode
    safe_message: str
    details: dict[str, Any] | None = None


class LifecycleError(RuntimeError):
    def __init__(
        self,
        code: LifecycleErrorCode,
        safe_message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.failure = LifecycleFailure(code, safe_message, details)

    @property
    def code(self) -> LifecycleErrorCode:
        return self.failure.code
