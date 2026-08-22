"""Deterministic shared state machine for all four product modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from .errors import LifecycleError, LifecycleErrorCode
from .models import Authority, LifecycleState


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    workspace_id: UUID
    prior_state: LifecycleState
    new_state: LifecycleState
    prior_version: int
    new_version: int
    operation_key: str


class LifecycleStateMachine:
    _transitions: ClassVar[dict[LifecycleState, frozenset[LifecycleState]]] = {
        LifecycleState.PROVISIONING: frozenset({LifecycleState.ACTIVE}),
        LifecycleState.ACTIVE: frozenset({LifecycleState.FREEZING}),
        LifecycleState.FREEZING: frozenset(
            {LifecycleState.FROZEN, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.FROZEN: frozenset({LifecycleState.FINALIZING}),
        LifecycleState.FINALIZING: frozenset(
            {LifecycleState.FINALIZED, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.FINALIZED: frozenset({LifecycleState.EXPORTING}),
        LifecycleState.EXPORTING: frozenset(
            {LifecycleState.EXPORTED, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.EXPORTED: frozenset({LifecycleState.ARCHIVING}),
        LifecycleState.ARCHIVING: frozenset(
            {LifecycleState.ARCHIVED, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.ARCHIVED: frozenset({LifecycleState.CLOSED}),
        LifecycleState.CLOSED: frozenset({LifecycleState.REOPENING, LifecycleState.RESET_PLANNING}),
        LifecycleState.REOPENING: frozenset(
            {LifecycleState.ACTIVE, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.RESET_PLANNING: frozenset(
            {LifecycleState.RESET_AUTHORIZED, LifecycleState.CLOSED}
        ),
        LifecycleState.RESET_AUTHORIZED: frozenset(
            {LifecycleState.PURGING, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.PURGING: frozenset(
            {LifecycleState.VERIFYING_RESET, LifecycleState.RECOVERY_REQUIRED}
        ),
        LifecycleState.VERIFYING_RESET: frozenset(
            {
                LifecycleState.RESET_VERIFIED,
                LifecycleState.RECOVERY_REQUIRED,
                LifecycleState.QUARANTINED,
            }
        ),
        LifecycleState.RESET_VERIFIED: frozenset({LifecycleState.DESTROYING}),
        LifecycleState.DESTROYING: frozenset(
            {
                LifecycleState.DESTROYED,
                LifecycleState.RECOVERY_REQUIRED,
                LifecycleState.QUARANTINED,
            }
        ),
        LifecycleState.RECOVERY_REQUIRED: frozenset(
            {
                LifecycleState.PURGING,
                LifecycleState.DESTROYING,
                LifecycleState.RECOVERY_REQUIRED,
                LifecycleState.QUARANTINED,
            }
        ),
        LifecycleState.QUARANTINED: frozenset({LifecycleState.RECOVERY_REQUIRED}),
        LifecycleState.DESTROYED: frozenset(),
    }

    _capabilities: ClassVar[dict[LifecycleState, str]] = {
        LifecycleState.ACTIVE: "workspace.provision",
        LifecycleState.FREEZING: "workspace.freeze",
        LifecycleState.FROZEN: "workspace.freeze",
        LifecycleState.FINALIZING: "workspace.finalize",
        LifecycleState.FINALIZED: "workspace.finalize",
        LifecycleState.EXPORTING: "workspace.export",
        LifecycleState.EXPORTED: "workspace.export",
        LifecycleState.ARCHIVING: "workspace.archive",
        LifecycleState.ARCHIVED: "workspace.archive",
        LifecycleState.CLOSED: "workspace.close",
        LifecycleState.REOPENING: "workspace.reopen",
        LifecycleState.RESET_PLANNING: "workspace.reset.plan",
        LifecycleState.RESET_AUTHORIZED: "workspace.reset.authorize",
        LifecycleState.PURGING: "workspace.purge.execute",
        LifecycleState.VERIFYING_RESET: "workspace.reset.verify",
        LifecycleState.RESET_VERIFIED: "workspace.reset.verify",
        LifecycleState.DESTROYING: "workspace.destroy.execute",
        LifecycleState.DESTROYED: "workspace.destroy.verify",
        LifecycleState.RECOVERY_REQUIRED: "workspace.recovery",
        LifecycleState.QUARANTINED: "workspace.quarantine",
    }

    @classmethod
    def decide(
        cls,
        *,
        workspace_id: UUID,
        current_state: LifecycleState,
        current_version: int,
        expected_version: int,
        target_state: LifecycleState,
        operation_key: str,
        actor: Authority,
        legal_hold_active: bool = False,
    ) -> TransitionDecision:
        if current_version != expected_version:
            raise LifecycleError(
                LifecycleErrorCode.CONCURRENCY_CONFLICT,
                "The expected lifecycle version is stale.",
            )
        if target_state not in cls._transitions[current_state]:
            raise LifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                f"Transition {current_state} -> {target_state} is not allowed.",
            )
        required = cls._capabilities[target_state]
        if required not in actor.capabilities:
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                f"Capability {required} is required.",
            )
        if legal_hold_active and target_state in {
            LifecycleState.RESET_AUTHORIZED,
            LifecycleState.PURGING,
            LifecycleState.DESTROYING,
            LifecycleState.DESTROYED,
        }:
            raise LifecycleError(
                LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                "A current legal hold blocks the destructive transition.",
            )
        return TransitionDecision(
            workspace_id,
            current_state,
            target_state,
            current_version,
            current_version + 1,
            operation_key,
        )

    @classmethod
    def is_writable(cls, state: LifecycleState) -> bool:
        return state in {LifecycleState.PROVISIONING, LifecycleState.ACTIVE}
